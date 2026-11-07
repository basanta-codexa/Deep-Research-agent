"""The one message dialect the rest of the agent is allowed to speak.

Every LLM provider has a slightly different wire format (Ollama's ``/api/chat``,
OpenAI's ``/v1/chat/completions``, Anthropic's ``/v1/messages``). If that
difference leaks into our agent loop, every new provider means editing the loop.

So: adapters translate *into* these types and *out of* these types. Nothing
outside ``research_agent/llm/`` should ever see a raw provider dict.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal, Sequence

Role = Literal["system", "user", "assistant", "tool"]


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class ToolCall:
    """A model's request to run a tool. Arguments are already parsed JSON."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class Message:
    """One turn in a conversation, normalized across providers."""

    role: Role
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    # Only used when role == "tool": which call this result answers.
    tool_call_id: str | None = None
    tool_name: str | None = None

    # -- constructors: make intent obvious at call sites -------------------- #
    @classmethod
    def system(cls, content: str) -> "Message":
        return cls(role="system", content=content)

    @classmethod
    def user(cls, content: str) -> "Message":
        return cls(role="user", content=content)

    @classmethod
    def assistant(
        cls, content: str = "", tool_calls: list[ToolCall] | None = None
    ) -> "Message":
        return cls(role="assistant", content=content, tool_calls=tool_calls or [])

    @classmethod
    def tool_result(cls, tool_call_id: str, tool_name: str, content: str) -> "Message":
        return cls(
            role="tool",
            content=content,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
        )


@dataclass(slots=True)
class Usage:
    """Token accounting. We track it from day one because agent cost is unbounded."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            cost_usd=self.cost_usd + other.cost_usd,
        )

    def __iadd__(self, other: "Usage") -> "Usage":
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.total_tokens += other.total_tokens
        self.cost_usd += other.cost_usd
        return self

    def __str__(self) -> str:
        return (
            f"{self.prompt_tokens} in / {self.completion_tokens} out "
            f"/ {self.total_tokens} total"
        )


@dataclass(slots=True)
class LLMResponse:
    """What every adapter must return."""

    message: Message
    model: str
    usage: Usage = field(default_factory=Usage)
    finish_reason: str | None = None
    latency_ms: float = 0.0
    # Untouched provider payload, kept for debugging only.
    raw: dict[str, Any] | None = None

    @property
    def truncated(self) -> bool:
        """True when the provider stopped us, not the model.

        Ollama says "length", OpenAI-compatible APIs say "length" or
        "max_tokens". Reasoning models make this common: they burn the output
        budget on hidden reasoning and return empty content.
        """
        return self.finish_reason in {"length", "max_tokens", "limit"}


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class LLMError(Exception):
    """Base class for anything that goes wrong talking to a model."""


class TransientLLMError(LLMError):
    """Worth retrying: 429s, 5xx, dropped connections, timeouts."""


class PermanentLLMError(LLMError):
    """Retrying will not help: bad request, bad key, unknown model."""


# --------------------------------------------------------------------------- #
# The interface
# --------------------------------------------------------------------------- #
class LLMClient(ABC):
    """Minimal contract every provider adapter implements.

    Deliberately small. Anything a real agent needs (streaming, structured
    output, tool calling) goes through ``chat``; provider-specific extras stay
    inside the adapter so they cannot infect the agent loop.
    """

    name: str = "abstract"
    model: str = ""

    @abstractmethod
    async def chat(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        json_mode: bool = False,
        reasoning_effort: str | None = None,
    ) -> LLMResponse:
        """Send a conversation, get back one assistant message.

        ``reasoning_effort`` is an optional hint for reasoning models. Adapters
        that do not support it must ignore it; callers must not rely on it
        changing the answer. The writer uses ``low`` because a hidden reasoning
        burn can consume the whole output budget and return an empty draft.
        """

    async def aclose(self) -> None:
        """Release network resources. Default: nothing to release."""
        return None
