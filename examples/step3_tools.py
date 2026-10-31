"""Step 3 demo: schemas are derived, arguments are validated, adding a tool is cheap.

Run from the repo root:

    .\\venv\\Scripts\\python.exe -m examples.step3_tools

No model needed for parts 1-3, so they are instant. Part 4 runs the real agent.
"""

from __future__ import annotations

import asyncio
import json

from research_agent.agent import Agent, Step
from research_agent.config import Settings
from research_agent.llm import create_client
from research_agent.tools.builtin import DEMO_TOOLS, calculator
from research_agent.tools.registry import ToolRegistry

QUESTION = (
    "What is sqrt(169) plus sqrt(144)? Use the calculator tool. "
    "Give the final number."
)


def section(title: str) -> None:
    print(f"\n{'=' * 62}\n{title}\n{'=' * 62}")


def print_step(step: Step) -> None:
    print(f"\n-- step {step.index} -- ({step.latency_ms:.0f} ms)")
    if step.text.strip():
        print(f"   think : {step.text.strip()[:200]}")
    for call in step.tool_calls:
        print(f"   call  : {call.name}({call.arguments})")
    for _, output in step.tool_outputs:
        print(f"   result: {output.replace(chr(10), ' ')[:200]}")
    if not step.tool_calls:
        print("   (no tool call -> final answer)")


async def main() -> None:
    registry = ToolRegistry(DEMO_TOOLS)

    # ---------------------------------------------------------------- #
    section("1. Schema generated from the function")
    print("python signature : def calculator(expression: str) -> str")
    print("python docstring : -> description + per-argument help")
    print("\nwire schema the model receives:")
    print(json.dumps(calculator.schema(), indent=2))

    # ---------------------------------------------------------------- #
    section("2. Validation happens before the function runs")
    cases: list[dict] = [
        {},                                            # missing required field
        {"expression": 123},                           # wrong type
        {"expr": "1+1"},                               # right idea, wrong name
        {"expression": "1+1", "precision": 2},         # extra field
        {"expression": "sqrt(169) + sqrt(144)"},       # valid
    ]
    for args in cases:
        print(f"\n  args   : {args}")
        print(f"  result : {await registry.execute('calculator', args)}")

    # ---------------------------------------------------------------- #
    section("3. Duplicate names fail at registration, not at 3am")
    try:
        ToolRegistry([calculator, calculator])
    except ValueError as exc:
        print(f"  ValueError: {exc}")

    # ---------------------------------------------------------------- #
    section("4. The agent, with the same tools")
    settings = Settings.from_env()
    client = create_client(settings)
    agent = Agent(
        client, registry, max_steps=5, max_tokens=250, on_step=print_step
    )
    print(f"provider={client.name}  model={client.model}")
    print(f"question: {QUESTION}")
    try:
        result = await agent.run(QUESTION)
    finally:
        await client.aclose()

    print(f"\nanswer     : {result.answer or '(empty)'}")
    print(f"stopped    : {result.stopped}   steps: {len(result.steps)}")
    print(f"tokens     : {result.usage}")
    print(f"wall clock : {result.elapsed_s:.1f} s")


if __name__ == "__main__":
    asyncio.run(main())
