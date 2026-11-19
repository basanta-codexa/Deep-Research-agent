from __future__ import annotations

import asyncio

import pytest

from research_agent.llm import LLMError, PermanentLLMError
from research_agent.llm.transport import post_json


class FakeResponse:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text
        self.headers: dict[str, str] = {}

    def json(self) -> dict:
        return {}


class FakeHttp:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response

    async def post(self, *args, **kwargs) -> FakeResponse:
        return self.response


def test_exhausted_retries_keep_the_last_status_for_diagnosis():
    with pytest.raises(LLMError) as caught:
        asyncio.run(
            post_json(
                FakeHttp(FakeResponse(429, "free-models-per-day")),
                "/chat/completions",
                {},
                max_retries=0,
            )
        )

    assert "HTTP 429" in str(caught.value)
    assert "free-models-per-day" in str(caught.value)


def test_non_retryable_error_is_permanent():
    with pytest.raises(PermanentLLMError) as caught:
        asyncio.run(
            post_json(
                FakeHttp(FakeResponse(402, "insufficient credits")),
                "/chat/completions",
                {},
                max_retries=3,
            )
        )

    assert "HTTP 402" in str(caught.value)
