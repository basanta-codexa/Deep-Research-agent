"""Structured output, in one place.

Three different stages ask a model for JSON: the planner wants a plan, the
sub-agent wants findings, the verifier wants a verdict. Each of them used to call
`chat(json_mode=True)` and hope. Two things went wrong with that:

  1. **JSON mode can stall.** On Groq, `response_format={"type": "json_object"}`
     hung past 90s on a prompt that answered in 8s without it.
  2. **JSON mode can fail server-side.** `json_validate_failed` is returned
     instead of the bad text, so there is nothing for our parser to repair.

The prompt already asks for JSON and our parsers tolerate fences and preamble, so
plain mode is the fast path. JSON mode is the *last* rung of a ladder:

    plain  ->  plain with a sharper instruction  ->  provider-enforced JSON

Every rung is a real call, so usage is accumulated across attempts: an eval that
ignores the retries would under-report cost.
"""

from __future__ import annotations

import json
import re
from typing import Callable, Sequence, TypeVar

from .llm import LLMClient, Message, Usage

T = TypeVar("T")

STRICT_HINT = "Return only the JSON object. No prose, no fences."

_FENCE = re.compile(r"^\s*```[a-zA-Z0-9_-]*\s*\n(.*?)\n\s*```\s*$", re.DOTALL)
_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def strip_fences(text: str) -> str:
    """Remove one wrapping ``` block, if present."""
    text = (text or "").strip()
    match = _FENCE.match(text)
    return match.group(1).strip() if match else text


def json_candidate(text: str) -> str:
    """Best-effort extraction of a JSON object from a chatty reply."""
    cleaned = strip_fences(text)
    try:
        json.loads(cleaned)
        return cleaned
    except ValueError:
        pass
    match = _OBJECT.search(cleaned)
    return match.group(0).strip() if match else cleaned


class StructuredError(RuntimeError):
    """No rung produced parseable output.

    Carries the usage burned on the failed attempts: a harness that only counts
    successful calls reports a cost lower than what the provider billed.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.usage = Usage()


async def complete_json(
    client: LLMClient,
    messages: Sequence[Message],
    *,
    parse: Callable[[str], T],
    max_tokens: int,
    temperature: float = 0.0,
    json_fallback: bool = True,
) -> tuple[T, Usage]:
    """Run the ladder and return (parsed, total usage).

    `parse` must raise on bad input; that is what triggers the next rung.
    """
    rungs: list[tuple[str, Sequence[Message], bool]] = [
        ("plain", (), False),
        ("plain+strict", (Message.user(STRICT_HINT),), False),
    ]
    if json_fallback:
        rungs.append(("json_mode", (), True))

    attempts: list[str] = []
    usage = Usage()
    last_error: Exception | None = None
    budget = max_tokens

    for label, extra, json_mode in rungs:
        try:
            response = await client.chat(
                list(messages) + list(extra),
                temperature=temperature,
                max_tokens=budget,
                json_mode=json_mode,
            )
        except Exception as exc:  # provider or transport failure
            attempts.append(f"{label}: {type(exc).__name__}: {exc}")
            last_error = exc
            continue

        usage += response.usage
        content = response.message.content or ""
        if not content.strip():
            # Reasoning models can spend the whole budget on hidden tokens and
            # return empty content. Retrying at the same size just repeats the
            # stall; give the next rung room to finish.
            attempts.append(
                f"{label}: empty completion (finish_reason="
                f"{response.finish_reason!r}, budget={budget})"
            )
            budget = max(budget * 2, 1000)
            continue
        if response.truncated:
            # Cut off mid-JSON, same lesson as the planner: double and go.
            attempts.append(
                f"{label}: truncated at {budget} tokens (finish_reason="
                f"{response.finish_reason!r})"
            )
            budget = max(budget * 2, 1000)
            continue

        try:
            return parse(content), usage
        except Exception as exc:  # the model answered, in the wrong shape
            attempts.append(f"{label}: unparseable ({type(exc).__name__}: {exc})")
            last_error = exc

    error = StructuredError("; ".join(attempts) or "no attempts made")
    error.usage = usage
    raise error from last_error
