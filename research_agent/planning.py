"""The planner: one question in, 3-5 independently searchable sub-questions out.

This is the first specialised agent in the project. It has one job, its own
prompt, its own output schema, and no tools. Keeping it separate from the
research loop means you can evaluate it on its own ("did the plan cover the
question?") instead of guessing from a bad final report.

Structured output is done the honest way: json_mode + pydantic validation +
one repair attempt. Providers' "JSON mode" only guarantees *syntactically* valid
JSON, never the shape you asked for.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field, ValidationError

from .llm import LLMClient, Message

PLANNER_PROMPT = """You are a research planner. Turn the user's question into \
3-5 sub-questions that, taken together, fully answer it.

Rules:
- Each sub-question must be answerable by one web search plus reading 1-2 pages.
- Sub-questions must not overlap; each must add a distinct piece of the answer.
- Order them so that earlier findings inform later ones.
- search_query must be literal search-engine words (3-8 words). No quotes, no
  boolean operators, no site: filter unless the user named a site.
- Anything you had to assume goes in `assumptions`. If the question cannot be
  answered as written, plan the closest answerable version and say why.

Return JSON only. It must match this schema exactly:
{schema}"""


class SubQuestion(BaseModel):
    question: str = Field(description="A self-contained question in plain English.")
    search_query: str = Field(
        description="Literal words to type into a search engine. 3-8 words."
    )
    why: str = Field(description="What evidence this supplies for the final answer.")


class Plan(BaseModel):
    restated: str = Field(description="The question restated precisely, one sentence.")
    sub_questions: list[SubQuestion] = Field(min_length=3, max_length=5)
    assumptions: list[str] = Field(default_factory=list)

    def queries(self) -> list[str]:
        return [sq.search_query for sq in self.sub_questions]


class PlanError(Exception):
    """The model could not produce a valid plan after the repair attempt."""


class Planner:
    def __init__(
        self,
        client: LLMClient,
        *,
        temperature: float = 0.2,
        max_tokens: int = 900,
        repair_attempts: int = 1,
    ) -> None:
        self.client = client
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.repair_attempts = repair_attempts

    async def plan(self, question: str) -> tuple[Plan, int, int]:
        """Return (plan, prompt_tokens, completion_tokens)."""
        schema = json.dumps(Plan.model_json_schema(), indent=1)
        messages = [
            Message.system(PLANNER_PROMPT.format(schema=schema)),
            Message.user(question),
        ]
        budget = self.max_tokens
        prompt_tokens = completion_tokens = 0
        last_error: Exception | None = None

        for attempt in range(self.repair_attempts + 1):
            response = await self.client.chat(
                messages,
                temperature=self.temperature,
                max_tokens=budget,
                json_mode=True,
            )
            prompt_tokens += response.usage.prompt_tokens
            completion_tokens += response.usage.completion_tokens
            text = response.message.content.strip()

            if response.truncated:
                # Cut off mid-JSON. Retrying the same budget just truncates
                # again, so double it and go.
                last_error = PlanError(
                    f"response truncated at {budget} tokens (finish_reason="
                    f"{response.finish_reason!r})"
                )
                budget *= 2
                continue

            try:
                return Plan.model_validate_json(text), prompt_tokens, completion_tokens
            except (ValidationError, ValueError) as exc:
                last_error = exc
                # Repair: show the model its own output and the exact complaint.
                # More effective than a generic "try again" by a wide margin.
                messages.append(Message.assistant(text))
                messages.append(
                    Message.user(
                        "That JSON was rejected by the schema validator:\n"
                        f"{exc}\n\nReturn corrected JSON only, matching the schema."
                    )
                )
                budget *= 2

        raise PlanError(f"could not produce a valid plan: {last_error}")
