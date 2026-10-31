"""Shared HTTP machinery for every adapter.

Written once, when the second adapter appeared. Both Ollama and OpenAI-compatible
APIs fail the same way (429s, 5xx, dropped connections), so the retry policy
should not be copy-pasted into each one and allowed to drift.
"""

from __future__ import annotations

import asyncio
import random
from typing import Any

import httpx

from .base import LLMError, PermanentLLMError, TransientLLMError

RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


async def post_json(
    http: httpx.AsyncClient,
    path: str,
    payload: dict[str, Any],
    *,
    max_retries: int,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """POST, retry transient failures, raise classified errors, return JSON."""
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        retry_after: float | None = None
        try:
            response = await http.post(path, json=payload, headers=headers)
        except httpx.TransportError as exc:  # refused, reset, timeout
            last_error = exc
        else:
            if response.status_code in RETRYABLE_STATUS:
                last_error = TransientLLMError(
                    f"HTTP {response.status_code}: {response.text[:300]}"
                )
                header = response.headers.get("retry-after")
                if header:
                    try:
                        retry_after = float(header)
                    except ValueError:
                        retry_after = None
            elif response.status_code >= 400:
                raise PermanentLLMError(
                    f"HTTP {response.status_code}: {response.text[:500]}"
                )
            else:
                try:
                    data = response.json()
                except ValueError as exc:
                    raise PermanentLLMError(
                        f"expected JSON, got {response.text[:200]!r}"
                    ) from exc
                # Ollama: {"error": "..."}   OpenAI-style: {"error": {"message": ...}}
                if isinstance(data, dict) and data.get("error"):
                    raise PermanentLLMError(str(data["error"])[:500])
                return data

        if attempt < max_retries:
            # Exponential backoff *with jitter*. Without jitter, N sub-agents
            # hitting a 429 retry in lockstep and hammer the server together.
            #
            # 429 is special: a provider's limit is usually per minute, so a
            # 0.5s retry just burns another attempt against the same window.
            # Honour Retry-After when it is offered.
            delay = (
                retry_after
                if retry_after is not None
                else min(1.5 * (2**attempt), 20.0) + random.random() * 0.5
            )
            await asyncio.sleep(delay)

    raise LLMError(
        f"request to {path} failed after {max_retries + 1} attempts"
    ) from last_error
