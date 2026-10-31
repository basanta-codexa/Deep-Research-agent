"""Ollama adapter — talks raw HTTP to ``POST /api/chat``.

We deliberately do NOT use the ``ollama`` python package here. Two reasons:

1. An SDK is just JSON over HTTP with a nicer name. Seeing the payload removes
   the magic, and you cannot debug what you cannot see.
2. It makes provider #2 (OpenAI-compatible) a 40-line copy, because both use the
   same ``LLMClient`` shape.
"""

from __future__ import annotations

import json
import time
import uuid
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


class OllamaClient(LLMClient):
    name = "ollama"

    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:11434",
        *,
        timeout: float = 180.0,
        max_retries: int = 2,
        think: bool = False,
        num_ctx: int = 8192,
    ) -> None:
        self.model = model
        self.max_retries = max_retries
        self.think = think
        self.num_ctx = num_ctx
        self._http = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
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
            "stream": False,  # we want one complete response, not a token stream
            # Always sent explicitly. Ollama's default is model-dependent, and a
            # thinking model will spend your whole output budget inside a
            # `thinking` field we never read, returning empty `content`.
            "think": self.think,
            "options": {"temperature": temperature, "num_ctx": self.num_ctx},
        }
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens
        if json_mode:
            payload["format"] = "json"
        if tools:
            payload["tools"] = list(tools)

        started = time.perf_counter()
        data = await self._post("/api/chat", payload)
        latency_ms = (time.perf_counter() - started) * 1000.0
        return self._parse(data, latency_ms)

    async def aclose(self) -> None:
        await self._http.aclose()

    # ------------------------------------------------------------------ #
    # Translation: our types -> Ollama wire format
    # ------------------------------------------------------------------ #
    @staticmethod
    def _to_wire(m: Message) -> dict[str, Any]:
        wire: dict[str, Any] = {"role": m.role, "content": m.content}
        if m.tool_calls:
            wire["tool_calls"] = [
                {"function": {"name": tc.name, "arguments": tc.arguments}}
                for tc in m.tool_calls
            ]
        if m.tool_call_id:
            wire["tool_call_id"] = m.tool_call_id
        if m.tool_name:
            wire["tool_name"] = m.tool_name
        return wire

    # ------------------------------------------------------------------ #
    # Translation: Ollama wire format -> our types
    # ------------------------------------------------------------------ #
    def _parse(self, data: dict[str, Any], latency_ms: float) -> LLMResponse:
        msg = data.get("message") or {}
        tool_calls: list[ToolCall] = []

        for i, tc in enumerate(msg.get("tool_calls") or []):
            fn = tc.get("function") or {}
            args = fn.get("arguments")
            # Ollama sometimes returns arguments as a JSON *string*. Normalize.
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError as exc:
                    raise LLMError(
                        f"model emitted unparseable tool arguments: {args!r}"
                    ) from exc
            if not isinstance(args, dict):
                args = {}
            tool_calls.append(
                ToolCall(
                    # Ollama does not give tool calls an id, but OpenAI-style
                    # protocols require one to match results to calls. We mint one.
                    id=tc.get("id") or f"call_{i}_{uuid.uuid4().hex[:8]}",
                    name=fn.get("name", ""),
                    arguments=args,
                )
            )

        prompt_tokens = int(data.get("prompt_eval_count") or 0)
        completion_tokens = int(data.get("eval_count") or 0)

        return LLMResponse(
            message=Message.assistant(msg.get("content") or "", tool_calls),
            model=data.get("model", self.model),
            usage=Usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                cost_usd=0.0,  # local inference is free
            ),
            finish_reason=data.get("done_reason"),
            latency_ms=latency_ms,
            raw=data,
        )

    # ------------------------------------------------------------------ #
    # Transport: retries, timeouts, error classification
    # ------------------------------------------------------------------ #
    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await post_json(
            self._http, path, payload, max_retries=self.max_retries
        )
