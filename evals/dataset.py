"""The eval dataset: questions, not answers.

Each row is a research question plus two *proxies*:

  must_include      tokens a competent answer should contain (API names, terms)
  must_not_include  phrases that signal a known misconception

They are proxies, not ground truth. "Did the report mention `return_exceptions`"
is cheap, deterministic, and cannot tell you whether the sentence is true —
that is what the support judge is for. Keeping the two separate matters: when a
metric is a proxy, say so, or you will optimise the proxy and call it quality.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

DEFAULT_PATH = Path(__file__).with_name("dataset.jsonl")


class DatasetError(ValueError):
    pass


class EvalItem(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,60}$")
    question: str = Field(min_length=15)
    category: str = Field(min_length=2)
    must_include: list[str] = Field(default_factory=list)
    must_not_include: list[str] = Field(default_factory=list)
    notes: str = ""


def load_dataset(path: str | Path = DEFAULT_PATH) -> list[EvalItem]:
    path = Path(path)
    items: list[EvalItem] = []
    seen: set[str] = set()

    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = EvalItem.model_validate_json(line)
        except ValidationError as exc:
            raise DatasetError(f"{path}:{lineno}: {exc}") from exc
        if item.id in seen:
            raise DatasetError(f"{path}:{lineno}: duplicate id {item.id!r}")
        seen.add(item.id)
        items.append(item)

    if not items:
        raise DatasetError(f"{path}: dataset is empty")
    return items


def category_counts(items: list[EvalItem]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        counts[item.category] = counts.get(item.category, 0) + 1
    return dict(sorted(counts.items()))


def dump_dataset(items: list[EvalItem]) -> str:
    return "\n".join(
        json.dumps(item.model_dump(), ensure_ascii=False) for item in items
    )
