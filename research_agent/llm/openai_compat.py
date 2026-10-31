"""OpenAI-compatible adapter: OpenAI, Groq, Together, vLLM, LM Studio, Ollama /v1.

One adapter covers all of them because they share a wire format. This is the
payoff of step 1: provider #2 cost ~90 lines and zero changes to the agent.
"""

from __future__ import annotations

import json
import time
from typing import Any, Sequence

import httpx

from .base import (
    LLMClient,
    LLMError,
    LLMResponse,
    Message,
    ToolCall,
    Usage,
)
from .transport import post_json


class OpenAICompatClient(LLMClient):
    def __init__(
        self,
        model: str,
        *,
        base_url: str,
        api_key: str,
        name: str = "openai",
        timeout: float = 120.0,
        max_retries: int = 2,
    ) -> None:
        if not api_key:
            raise ValueError(f"{name}: an API key is required")
        self.name = name
        self.model = model
        self.max_retries = max_retries
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"), timeout=timeout
        )

    async def chat(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [self._to_wire(m) for m in messages],
            "temperature": temperature,
            "stream": False,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = list(tools)
            payload["tool_choice"] = "auto"
        if json_mode:
            # Providers require the word "JSON" somewhere in the prompt when
            # this flag is set. Our planner prompt says it explicitly.
            payload["response_format"] = {"type": "json_object"}

        started = time.perf_counter()
        data = await post_json(
            self._http,
            "/chat/completions",
            payload,
            max_retries=self.max_retries,
            headers=self._headers,
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        return self._parse(data, latency_ms)

    async def aclose(self) -> None:
        await self._http.aclose()

    # ------------------------------------------------------------------ #
    @staticmethod
    def _to_wire(m: Message) -> dict[str, Any]:
        if m.role == "tool":
            return {
                "role": "tool",
                "tool_call_id": m.tool_call_id or "",
                "content": m.content,
            }
        wire: dict[str, Any] = {"role": m.role, "content": m.content}
        if m.tool_calls:
            wire["content"] = m.content or None
            wire["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        # OpenAI expects a JSON *string* here; Ollama expects an
                        # object. This is exactly the kind of difference the
                        # adapter exists to absorb.
                        "arguments": json.dumps(tc.arguments),
                    },
                }
                for tc in m.tool_calls
            ]
        return wire

    def _parse(self, data: dict[str, Any], latency_ms: float) -> LLMResponse:
        try:
            choice = data["choices"][0]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"unexpected response shape: {str(data)[:300]}") from exc

        msg = choice.get("message") or {}
        tool_calls: list[ToolCall] = []
        for i, tc in enumerate(msg.get("tool_calls") or []):
            fn = tc.get("function") or {}
            raw_args = fn.get("arguments")
            if isinstance(raw_args, str):
                try:
                    raw_args = json.loads(raw_args) if raw_args.strip() else {}
                except json.JSONDecodeError as exc:
                    raise LLMError(
                        f"model emitted unparseable tool arguments: {raw_args!r}"
                    ) from exc
            if not isinstance(raw_args, dict):
                raw_args = {}
            tool_calls.append(
                ToolCall(
                    id=tc.get("id") or f"call_{i}",
                    name=fn.get("name", ""),
                    arguments=raw_args,
                )
            )

        usage = data.get("usage") or {}
        prompt = int(usage.get("prompt_tokens") or 0)
        completion = int(usage.get("completion_tokens") or 0)
        total = int(usage.get("total_tokens") or (prompt + completion))

        return LLMResponse(
            message=Message.assistant(msg.get("content") or "", tool_calls),
            model=data.get("model", self.model),
            usage=Usage(
                prompt_tokens=prompt,
                completion_tokens=completion,
                total_tokens=total,
                cost_usd=0.0,  # pricing table arrives with tracing (step 11)
            ),
            finish_reason=choice.get("finish_reason"),
            latency_ms=latency_ms,
            raw=data,
        )
