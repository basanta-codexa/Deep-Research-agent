from __future__ import annotations

import asyncio
import json

import pytest

from research_agent.llm import LLMResponse, Message, Usage
from research_agent.structured import StructuredError, complete_json


class FakeClient:
    def __init__(
        self,
        replies: list[object],
        *,
        finish_reasons: list[str | None] | None = None,
    ) -> None:
        self.replies = list(replies)
        self.finish_reasons = list(finish_reasons or [])
        self.calls: list[dict] = []

    async def chat(
        self,
        messages,
        *,
        tools=None,
        temperature=0.2,
        max_tokens=None,
        json_mode=False,
    ):
        self.calls.append(
            {"messages": list(messages), "json_mode": json_mode, "max_tokens": max_tokens}
        )
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return LLMResponse(
            message=Message.assistant(str(reply)),
            model="fake",
            usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            finish_reason=(
                self.finish_reasons.pop(0) if self.finish_reasons else None
            ),
        )


MESSAGES = [Message.system("return json"), Message.user("question")]


def parse(text: str) -> dict:
    return json.loads(text)


def test_plain_mode_is_enough_when_the_model_complies():
    client = FakeClient(['{"verdict": "ok"}'])
    value, usage = asyncio.run(
        complete_json(client, MESSAGES, parse=parse, max_tokens=100)
    )
    assert value == {"verdict": "ok"}
    assert usage.total_tokens == 15
    assert len(client.calls) == 1
    assert client.calls[0]["json_mode"] is False


def test_unparseable_reply_triggers_a_sharper_plain_retry():
    client = FakeClient(["Sure! Here is my answer.", '{"verdict": "ok"}'])
    value, usage = asyncio.run(
        complete_json(client, MESSAGES, parse=parse, max_tokens=100)
    )
    assert value == {"verdict": "ok"}
    assert len(client.calls) == 2
    assert usage.total_tokens == 30
    assert "Return only the JSON object" in client.calls[1]["messages"][-1].content
    assert client.calls[1]["json_mode"] is False


def test_json_mode_is_the_last_rung():
    client = FakeClient(["no", "still no", '{"verdict": "ok"}'])
    value, usage = asyncio.run(
        complete_json(client, MESSAGES, parse=parse, max_tokens=100)
    )
    assert value == {"verdict": "ok"}
    assert [call["json_mode"] for call in client.calls] == [False, False, True]
    assert usage.total_tokens == 45


def test_json_mode_can_be_disabled():
    client = FakeClient(["no", "still no"])
    with pytest.raises(StructuredError):
        asyncio.run(
            complete_json(
                client, MESSAGES, parse=parse, max_tokens=100, json_fallback=False
            )
        )
    assert len(client.calls) == 2


def test_all_rungs_failing_raises_with_the_usage_it_burned():
    client = FakeClient(["no", "no", "no"])
    with pytest.raises(StructuredError) as info:
        asyncio.run(complete_json(client, MESSAGES, parse=parse, max_tokens=100))
    assert info.value.usage.total_tokens == 45
    assert "plain" in str(info.value)
    assert "json_mode" in str(info.value)


def test_strip_fences_and_json_candidate():
    from research_agent.structured import json_candidate, strip_fences

    assert strip_fences('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert strip_fences('{"a": 1}') == '{"a": 1}'
    assert json_candidate('Here you go:\n{"a": 1}\nthanks') == '{"a": 1}'
    assert json_candidate('```\n{"a": 1}\n```') == '{"a": 1}'


def test_provider_error_moves_to_the_next_rung():
    client = FakeClient([RuntimeError("400 json_validate_failed"), '{"ok": true}'])
    value, _ = asyncio.run(complete_json(client, MESSAGES, parse=parse, max_tokens=100))
    assert value == {"ok": True}
    assert len(client.calls) == 2


def test_empty_completion_retries_with_a_larger_budget():
    client = FakeClient(
        ["", '{"ok": true}'],
        finish_reasons=["stop", "stop"],
    )

    value, _ = asyncio.run(
        complete_json(client, MESSAGES, parse=parse, max_tokens=100)
    )

    assert value == {"ok": True}
    assert [call["max_tokens"] for call in client.calls] == [100, 1000]
    assert "Return only the JSON object" in client.calls[1]["messages"][-1].content


def test_truncated_json_retries_with_a_larger_budget():
    client = FakeClient(
        ['{"verdict": "trunca', '{"verdict": "ok"}'],
        finish_reasons=["length", "stop"],
    )

    value, _ = asyncio.run(
        complete_json(client, MESSAGES, parse=parse, max_tokens=100)
    )

    assert value == {"verdict": "ok"}
    assert [call["max_tokens"] for call in client.calls] == [100, 1000]
