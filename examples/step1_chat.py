"""Step 1 smoke test: can we talk to a model through our own interface?

Run from the repo root:

    .\\venv\\Scripts\\python.exe -m examples.step1_chat

Two calls:
  1. plain chat            -> proves message translation + token accounting
  2. chat with a tool      -> proves tool schema pass-through + parsing
"""

from __future__ import annotations

import asyncio

from research_agent.config import Settings
from research_agent.llm import create_client
from research_agent.llm.base import Message

# Step 3 will generate schemas like this automatically from Python functions.
# For now it is hand-written, on purpose, so you can see what the model receives.
WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the web and return a list of result snippets.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {"type": "integer", "description": "1-10"},
            },
            "required": ["query"],
        },
    },
}


async def main() -> None:
    settings = Settings.from_env()
    client = create_client(settings)
    print(f"provider={client.name}  model={client.model}\n")

    try:
        # ---- 1. plain chat ------------------------------------------------ #
        resp = await client.chat(
            [
                Message.system("Answer in one short sentence."),
                Message.user("Why does an agent need a loop instead of one big prompt?"),
            ],
            temperature=settings.temperature,
            max_tokens=120,
        )
        print("--- plain chat ---")
        print(resp.message.content.strip())
        print(f"usage: {resp.usage}   latency: {resp.latency_ms:.0f} ms\n")

        # ---- 2. tool call -------------------------------------------------- #
        resp = await client.chat(
            [
                Message.system("You have tools. Use them when they fit the request."),
                Message.user("Search the web for 'small language model agents 2026'."),
            ],
            tools=[WEB_SEARCH_TOOL],
            temperature=settings.temperature,
            max_tokens=200,
        )
        print("--- tool call ---")
        if resp.message.tool_calls:
            for tc in resp.message.tool_calls:
                print(f"tool={tc.name}  args={tc.arguments}  id={tc.id}")
        else:
            print("model chose not to call a tool. content:")
            print(resp.message.content.strip())
        print(f"usage: {resp.usage}   latency: {resp.latency_ms:.0f} ms")
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
