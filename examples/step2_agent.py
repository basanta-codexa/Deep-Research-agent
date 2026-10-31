"""Step 2 demo: watch the ReAct loop reason, act, and stop.

Run from the repo root:

    .\\venv\\Scripts\\python.exe -m examples.step2_agent
"""

from __future__ import annotations

import asyncio

from research_agent.agent import Agent, Step
from research_agent.config import Settings
from research_agent.llm import create_client
from research_agent.tools.builtin import DEMO_TOOLS

QUESTION = (
    "Acme Corp's Q3 2026 revenue is in the corpus. Find it, then compute the "
    "annualized run rate (four quarters at that rate). Give the figure in dollars."
)

ARITHMETIC_QUESTION = (
    "What is the square root of 144? You must use the calculator tool; do not "
    "compute it yourself."
)


def print_step(step: Step) -> None:
    print(f"\n-- step {step.index} -- ({step.latency_ms:.0f} ms, {step.usage})")
    if step.text.strip():
        print(f"  think : {step.text.strip()[:300]}")
    for call in step.tool_calls:
        print(f"  call  : {call.name}({call.arguments})")
    for call, output in step.tool_outputs:
        first = output.replace("\n", " ")[:220]
        print(f"  result: {first}")
    if not step.tool_calls:
        print("  (no tool call -> final answer)")


async def main() -> None:
    settings = Settings.from_env()
    client = create_client(settings)
    agent = Agent(client, DEMO_TOOLS, max_steps=6, max_tokens=300, on_step=print_step)

    print(f"provider={client.name}  model={client.model}")

    try:
        for question in (QUESTION, ARITHMETIC_QUESTION):
            print("\n" + "#" * 60)
            print(f"question: {question}")
            result = await agent.run(question)

            print("\n" + "=" * 60)
            print(f"answer      : {result.answer or '(empty)'}")
            print(f"stopped     : {result.stopped}")
            print(f"steps       : {len(result.steps)}")
            print(f"tokens      : {result.usage}")
            print(f"wall clock  : {result.elapsed_s:.1f} s")
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
