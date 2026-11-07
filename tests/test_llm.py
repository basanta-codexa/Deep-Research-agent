from __future__ import annotations

import asyncio

from research_agent.llm import Message, OpenAICompatClient


def _reply() -> dict:
    return {
        "choices": [
            {
                "message": {"content": "ok"},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "total_tokens": 2,
        },
    }


def test_openrouter_reasoning_effort_uses_nested_reasoning_object(monkeypatch):
    captured: dict = {}

    async def fake_post(http, path, payload, *, max_retries, headers=None):
        captured.update(payload)
        return _reply()

    monkeypatch.setattr(
        "research_agent.llm.openai_compat.post_json", fake_post
    )
    client = OpenAICompatClient(
        model="openai/gpt-oss-20b",
        base_url="https://openrouter.ai/api/v1",
        api_key="test-key",
        name="openrouter",
    )

    async def call():
        try:
            return await client.chat(
                [Message.user("hi")], reasoning_effort="low"
            )
        finally:
            await client.aclose()

    response = asyncio.run(call())

    assert response.message.content == "ok"
    assert captured["reasoning"] == {"effort": "low"}
    assert "reasoning_effort" not in captured


def test_openai_reasoning_effort_uses_top_level_field(monkeypatch):
    captured: dict = {}

    async def fake_post(http, path, payload, *, max_retries, headers=None):
        captured.update(payload)
        return _reply()

    monkeypatch.setattr(
        "research_agent.llm.openai_compat.post_json", fake_post
    )
    client = OpenAICompatClient(
        model="o3-mini",
        base_url="https://api.openai.com/v1",
        api_key="test-key",
        name="openai",
    )

    async def call():
        try:
            return await client.chat(
                [Message.user("hi")], reasoning_effort="low"
            )
        finally:
            await client.aclose()

    asyncio.run(call())

    assert captured["reasoning_effort"] == "low"
    assert "reasoning" not in captured


def test_non_reasoning_model_does_not_receive_an_unknown_parameter(monkeypatch):
    captured: dict = {}

    async def fake_post(http, path, payload, *, max_retries, headers=None):
        captured.update(payload)
        return _reply()

    monkeypatch.setattr(
        "research_agent.llm.openai_compat.post_json", fake_post
    )
    client = OpenAICompatClient(
        model="gpt-4.1-mini",
        base_url="https://api.openai.com/v1",
        api_key="test-key",
        name="openai",
    )

    async def call():
        try:
            return await client.chat(
                [Message.user("hi")], reasoning_effort="low"
            )
        finally:
            await client.aclose()

    asyncio.run(call())

    assert "reasoning_effort" not in captured
    assert "reasoning" not in captured
