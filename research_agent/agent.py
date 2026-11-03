"""The ReAct loop — the heart of the agent.

ReAct = Reason + Act. In practice it is a `while` with four obligations:

  1. ask the model what to do next
  2. if it wants a tool, run it and feed the result back
  3. if it does not want a tool, that is the final answer
  4. never loop forever, never crash on a bad tool call

Everything else in this project is downstream of this file.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Literal, Sequence

from .llm import LLMClient, Message, ToolCall, Usage
from .tools.registry import Tool, ToolRegistry
from .tracing import span

StopReason = Literal["final_answer", "max_steps", "loop_detected"]

DEFAULT_SYSTEM_PROMPT = """You are a careful research assistant working with tools.

Rules:
1. Use a tool whenever the answer depends on a fact or a calculation you do not
   know for certain. Never guess numbers.
2. Call one tool at a time and read its result before the next call.
3. Only use the tools listed. If a tool returns ERROR, fix the arguments or pick
   another tool — do not repeat the same failing call.
4. When you can answer, reply with plain text and NO tool call. That ends the
   task, so make that reply your complete final answer.
Be concise."""

DEFAULT_FINALIZE_PROMPT = (
    "This is your final step. Tools are now disabled. Reply with your final answer "
    "now. If a JSON format was requested, return that JSON and nothing else."
)

GRACE_PROMPT = (
    "You are out of tool calls. Everything you have read so far is above this "
    "message. Answer now using only that material. If a JSON format was "
    "requested, return that JSON and nothing else."
)


@dataclass(slots=True)
class Step:
    """One model turn, for inspection and later for tracing."""

    index: int
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_outputs: list[tuple[ToolCall, str]] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    latency_ms: float = 0.0


@dataclass(slots=True)
class AgentResult:
    answer: str
    stopped: StopReason
    steps: list[Step]
    usage: Usage
    messages: list[Message]
    elapsed_s: float


class Agent:
    def __init__(
        self,
        client: LLMClient,
        tools: Sequence[Tool] | ToolRegistry,
        *,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        max_steps: int = 6,
        temperature: float = 0.2,
        max_tokens: int | None = 400,
        max_tool_result_chars: int = 2000,
        repeat_limit: int = 3,
        force_final_answer: bool = True,
        grace_answer: bool = True,
        finalize_prompt: str = DEFAULT_FINALIZE_PROMPT,
        on_step: Callable[[Step], None] | None = None,
    ) -> None:
        self.client = client
        self.registry = (
            tools if isinstance(tools, ToolRegistry) else ToolRegistry(tools)
        )
        self._schemas = self.registry.schemas()
        self.system_prompt = system_prompt
        self.max_steps = max_steps
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_tool_result_chars = max_tool_result_chars
        self.repeat_limit = repeat_limit
        self.force_final_answer = force_final_answer
        self.grace_answer = grace_answer
        self.finalize_prompt = finalize_prompt
        self.on_step = on_step

    # ------------------------------------------------------------------ #
    async def run(self, question: str) -> AgentResult:
        messages: list[Message] = [
            Message.system(self.system_prompt),
            Message.user(question),
        ]
        steps: list[Step] = []
        usage = Usage()
        seen: Counter[str] = Counter()
        started = time.perf_counter()
        stopped: StopReason = "max_steps"
        answer = ""

        for index in range(1, self.max_steps + 1):
            last_step = index == self.max_steps
            if last_step and self.force_final_answer:
                # Nudge only. We keep the tools in the request because some
                # providers reject a tool-free call when the model tries to use
                # one anyway (Groq: 400 tool_use_failed). The hard stop is the
                # loop bound plus the grace call at the end of run().
                messages.append(Message.user(self.finalize_prompt))

            response = await self.client.chat(
                messages,
                tools=self._schemas,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            usage += response.usage
            messages.append(response.message)  # must include tool_calls

            step = Step(
                index=index,
                text=response.message.content,
                tool_calls=list(response.message.tool_calls),
                usage=response.usage,
                latency_ms=response.latency_ms,
            )
            steps.append(step)

            # ---- stop condition: the model answered without asking for a tool
            if not step.tool_calls:
                answer = step.text.strip()
                stopped = "final_answer"
                if self.on_step:
                    self.on_step(step)
                break

            # ---- loop detection: same call, same args, again and again
            for call in step.tool_calls:
                signature = f"{call.name}:{json.dumps(call.arguments, sort_keys=True)}"
                seen[signature] += 1
            if max(seen.values()) >= self.repeat_limit:
                stopped = "loop_detected"
                answer = step.text.strip()
                if self.on_step:
                    self.on_step(step)
                break

            # ---- act: run every requested call, in parallel, never raise
            outputs = await asyncio.gather(
                *(self._execute(call) for call in step.tool_calls)
            )
            for call, output in zip(step.tool_calls, outputs):
                step.tool_outputs.append((call, output))
                messages.append(Message.tool_result(call.id, call.name, output))

            if self.on_step:
                self.on_step(step)

        # ---- grace call: out of budget, but the model owes us an answer ----
        # One extra turn that cannot change the world (results are already
        # collected) but can be turned into the structured output we need.
        # Skipped when the model already answered or when it looped.
        if not answer and self.grace_answer and stopped != "loop_detected":
            messages.append(Message.user(GRACE_PROMPT))
            try:
                final = await self.client.chat(
                    messages,
                    tools=self._schemas,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )
            except Exception:
                final = None
            if final is not None:
                usage += final.usage
                messages.append(final.message)
                if not final.message.tool_calls and final.message.content.strip():
                    answer = final.message.content.strip()
                    stopped = "final_answer"

        return AgentResult(
            answer=answer,
            stopped=stopped,
            steps=steps,
            usage=usage,
            messages=messages,
            elapsed_s=time.perf_counter() - started,
        )

    # ------------------------------------------------------------------ #
    async def _execute(self, call: ToolCall) -> str:
        """Delegate to the registry: validate, run, and convert every failure
        into readable text. A tool error is information, not a crash."""
        with span(
            call.name,
            kind="tool",
            args=json.dumps(call.arguments, ensure_ascii=False)[:200],
        ) as item:
            output = await self.registry.execute(call.name, call.arguments)
            if item is not None:
                item.attributes["output_chars"] = len(output)
                if output.startswith("ERROR:"):
                    item.status = "error"
                    item.error = output[:200]
            return self._truncate(output)

    def _truncate(self, text: str) -> str:
        """Tool output is context budget. A 50KB page must not eat the window."""
        limit = self.max_tool_result_chars
        if len(text) <= limit:
            return text
        cut = text[:limit]
        return f"{cut}\n\n[...truncated {len(text) - limit} chars. Narrow your query.]"
