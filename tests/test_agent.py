from __future__ import annotations

import asyncio
import time

from research_agent.agent import Agent
from research_agent.llm import ToolCall
from research_agent.tools.registry import Tool


async def hang(seconds: float) -> str:
    """Wait for the requested time.

    Args:
        seconds: How long to sleep.
    """
    await asyncio.sleep(seconds)
    return "finished"


def test_a_hung_tool_becomes_a_readable_error_instead_of_blocking_the_agent():
    agent = Agent(None, [Tool.from_function(hang)], tool_timeout=0.05)

    started = time.perf_counter()
    output = asyncio.run(
        agent._execute(
            ToolCall(id="call_1", name="hang", arguments={"seconds": 10})
        )
    )

    assert output.startswith("ERROR:")
    assert "timed out" in output
    assert time.perf_counter() - started < 2.0
