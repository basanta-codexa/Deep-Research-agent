from __future__ import annotations

import asyncio

from research_agent.evidence import EvidenceStore
from research_agent.llm import LLMResponse, Message, Usage
from research_agent.writer import (
    ReportWriter,
    _collapse_brackets,
    build_brief,
    check_draft,
    extract_ids,
    renumber,
)

ALLOWED = {"ev_11111111", "ev_22222222"}

VALID = """# Asyncio gather failure handling

## Summary
Gather propagates the first exception to the caller [ev_11111111].

## What happens to the results
The remaining coroutines keep running and their values are not returned [ev_11111111][ev_22222222].

## How to keep the results
Pass return_exceptions=True and inspect the returned list [ev_22222222].

## Limitations
- Only two pages were read, both community tutorials.
"""


def codes(problems) -> set[str]:
    return {problem.code for problem in problems}


def test_valid_draft_passes():
    assert check_draft(VALID, ALLOWED) == []


def test_unknown_citation_is_an_error():
    draft = VALID.replace("[ev_22222222]", "[ev_deadbeef]", 1)
    assert "unknown_citation" in codes(check_draft(draft, ALLOWED))


def test_raw_url_in_prose_is_an_error():
    draft = VALID.replace(
        "The remaining coroutines keep running",
        "See https://example.com/made-up for details; the coroutines keep running",
    )
    assert "raw_url" in codes(check_draft(draft, ALLOWED))


def test_uncited_factual_paragraph_is_an_error():
    draft = VALID.replace(
        "The remaining coroutines keep running and their values are not returned [ev_11111111][ev_22222222].",
        "The remaining coroutines keep running and their values are simply not returned to anybody.",
    )
    assert "uncited_paragraph" in codes(check_draft(draft, ALLOWED))


def test_fenced_code_block_is_not_a_factual_paragraph():
    draft = VALID.replace(
        "Pass return_exceptions=True and inspect the returned list [ev_22222222].",
        "Pass return_exceptions=True and inspect the returned list [ev_22222222].\n\n"
        "```python\n"
        "results = await asyncio.gather(*tasks, return_exceptions=True)\n"
        "```",
    )
    assert check_draft(draft, ALLOWED) == []


def test_prose_after_a_code_fence_is_still_checked():
    draft = VALID.replace(
        "Pass return_exceptions=True and inspect the returned list [ev_22222222].",
        "Pass return_exceptions=True and inspect the returned list [ev_22222222].\n\n"
        "```python\n"
        "x = 1\n"
        "```\n\n"
        "This trailing paragraph makes a claim with no citation at all.",
    )
    assert "uncited_paragraph" in codes(check_draft(draft, ALLOWED))


def test_limitations_are_exempt_from_citation():
    draft = VALID.replace(
        "- Only two pages were read, both community tutorials.",
        "- Nothing here is verified against CPython source, and this sentence is long enough to matter.",
    )
    assert check_draft(draft, ALLOWED) == []


def test_missing_required_sections():
    draft = "# Title\n\n## Summary\nShort [ev_11111111].\n"
    found = codes(check_draft(draft, ALLOWED))
    assert "missing_section" in found


def test_extract_ids_handles_grouped_brackets():
    text = "a [ev_11111111] b [ev_22222222, ev_11111111] c [not an id]"
    assert extract_ids(text) == ["ev_11111111", "ev_22222222"]


def test_extract_ids_accepts_full_width_brackets():
    assert extract_ids("claim \u3010ev_11111111\u3011") == ["ev_11111111"]
    assert extract_ids("claim \uff3bev_22222222\uff3d") == ["ev_22222222"]


def test_full_width_citations_are_not_a_silent_pass():
    """Regression: 【ev_...】 used to yield a draft that cited nothing but passed."""
    draft = VALID.replace("[ev_11111111]", "\u3010ev_11111111\u3011")
    assert check_draft(draft, ALLOWED) == []
    assert extract_ids(draft) == ["ev_11111111", "ev_22222222"]


def test_draft_with_no_ids_is_an_error():
    draft = VALID.replace("[ev_11111111]", "").replace("[ev_22222222]", "")
    assert "no_citations" in codes(check_draft(draft, ALLOWED))


def test_unbracketed_ids_do_not_count_as_citations():
    draft = VALID.replace("[ev_11111111]", "ev_11111111")
    draft = draft.replace("[ev_22222222]", "ev_22222222")
    assert "no_citations" in codes(check_draft(draft, ALLOWED))


def test_renumber_numbers_sources_not_quotes():
    store = EvidenceStore()
    store.register_source("https://a.example/1", "First quote about alpha here.")
    store.register_source("https://b.example/2", "Second quote about beta here.")
    one = store.add("alpha claim", "First quote about alpha here.", "https://a.example/1")
    two = store.add("beta claim", "Second quote about beta here.", "https://b.example/2")
    assert one is not None and two is not None

    body = f"Alpha [  {one.id} ]. Beta [{two.id}]. Again [{one.id}]."
    numbered, url_order, _ = renumber(body, store)

    assert "[1]" in numbered and "[2]" in numbered
    assert len(url_order) == 2
    assert "[ 1 ]".replace(" ", "") in numbered.replace(" ", "")


def test_renumber_maps_two_quotes_from_one_source_to_one_number():
    store = EvidenceStore()
    store.register_source(
        "https://a.example/1", "First quote about alpha. Second quote about beta."
    )
    one = store.add("alpha", "First quote about alpha.", "https://a.example/1")
    two = store.add("beta", "Second quote about beta.", "https://a.example/1")
    assert one is not None and two is not None

    numbered, url_order, _ = renumber(f"[{one.id}][{two.id}]", store)
    assert url_order == [("https://a.example/1", 1)]
    assert numbered == "[1][1]"


def test_collapse_brackets_merges_adjacent_citations():
    assert _collapse_brackets("[1][1]") == "[1]"
    assert _collapse_brackets("[1][2]") == "[1, 2]"
    assert _collapse_brackets("[1, 2][3]") == "[1, 2, 3]"
    assert _collapse_brackets("[1] text [2]") == "[1] text [2]"


# --------------------------------------------------------------------------- #
# writer end-to-end with a fake model
# --------------------------------------------------------------------------- #
class FakeClient:
    model = "fake"

    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.calls = 0
        self.budgets: list[int | None] = []
        self.reasoning_efforts: list[str | None] = []

    async def chat(self, messages, **kwargs):
        self.calls += 1
        self.budgets.append(kwargs.get("max_tokens"))
        self.reasoning_efforts.append(kwargs.get("reasoning_effort"))
        text = self.replies.pop(0) if self.replies else ""
        return LLMResponse(
            message=Message.assistant(text),
            model="fake",
            usage=Usage(prompt_tokens=10, completion_tokens=10, total_tokens=20),
        )


def make_store():
    store = EvidenceStore()
    store.register_source(
        "https://docs.python.org/3/library/time.html",
        "time.time() returns the time in seconds since the epoch. "
        "time.perf_counter() returns a monotonic clock with the highest resolution.",
    )
    one = store.add(
        "time.time() is wall-clock time",
        "time.time() returns the time in seconds since the epoch.",
        "https://docs.python.org/3/library/time.html",
    )
    two = store.add(
        "perf_counter is monotonic",
        "time.perf_counter() returns a monotonic clock with the highest resolution.",
        "https://docs.python.org/3/library/time.html",
    )
    assert one is not None and two is not None
    for item in (one, two):
        item.support = "supported"
    return store, one, two


def test_writer_normalises_full_width_brackets_before_citing():
    store, one, two = make_store()
    draft = f"""# Timing short code paths

## Summary
time.time() is wall-clock time and can jump 【{one.id}】.

## Why it is a poor clock
The clock can move when it is adjusted 【{two.id}】.

## What to use instead
time.perf_counter() is monotonic and high resolution 【{one.id}】.

## Limitations
- Two standard-library pages only.
"""
    report = asyncio.run(
        ReportWriter(FakeClient([draft])).write(question="Which clock?", store=store)
    )
    assert report.ok is True
    assert "【" not in report.markdown
    assert "[1]" in report.markdown
    assert report.cited_ids == [one.id, two.id]
    assert report.unused_ids == []


def test_writer_rejects_a_report_that_cites_nothing():
    store, one, _ = make_store()
    draft = f"""# Timing short code paths

## Summary
time.time() is wall-clock time and can jump.

## Why it is a poor clock
The clock can move when it is adjusted.

## What to use instead
time.perf_counter() is monotonic and high resolution.

## Limitations
- Two standard-library pages only.
"""
    report = asyncio.run(
        ReportWriter(FakeClient([draft]), repair_attempts=0).write(
            question="Which clock?", store=store
        )
    )
    assert report.ok is False
    assert "no_citations" in {problem.code for problem in report.errors}


def draft_citing(one, two) -> str:
    return VALID.replace("ev_11111111", one.id).replace("ev_22222222", two.id)


def test_writer_retries_an_empty_completion_with_a_larger_budget():
    store, one, two = make_store()
    client = FakeClient(["", draft_citing(one, two)])

    report = asyncio.run(
        ReportWriter(client).write(question="Which clock?", store=store)
    )

    assert report.ok is True
    assert client.calls == 2
    assert client.budgets[0] == 1800
    assert client.budgets[1] > client.budgets[0]
    assert report.errors == []


def test_writer_asks_for_low_reasoning_by_default():
    store, one, two = make_store()
    client = FakeClient([draft_citing(one, two)])

    report = asyncio.run(
        ReportWriter(client).write(question="Which clock?", store=store)
    )

    assert report.ok is True
    assert client.reasoning_efforts == ["low"]


def test_an_empty_completion_is_an_error_not_a_repairable_draft():
    store, _, _ = make_store()
    client = FakeClient(["", ""])

    report = asyncio.run(
        ReportWriter(client, repair_attempts=1).write(
            question="Which clock?", store=store
        )
    )

    assert report.ok is False
    assert "empty_draft" in {problem.code for problem in report.errors}
    # Initial call plus one larger-budget retry, and no repair turn after that.
    assert client.calls == 2
    assert report.repaired is False


def test_repair_gets_more_output_budget_than_the_first_draft():
    store, one, two = make_store()
    uncited = """# Timing short code paths

## Summary
time.time() is wall-clock time.

## Why it is a poor clock
The clock can move when it is adjusted.

## What to use instead
time.perf_counter() is monotonic.

## Limitations
- Two standard-library pages only.
"""
    client = FakeClient([uncited, draft_citing(one, two)])

    report = asyncio.run(
        ReportWriter(client).write(question="Which clock?", store=store)
    )

    assert report.ok is True
    assert report.repaired is True
    assert client.calls == 2
    assert client.budgets[1] > client.budgets[0]


def test_brief_never_contains_urls():
    store = EvidenceStore()
    store.register_source("https://docs.python.org/3/x", "The quote lives here.")
    item = store.add("claim", "The quote lives here.", "https://docs.python.org/3/x")
    assert item is not None
    brief = build_brief(store.citable())
    assert "http" not in brief
    assert item.id in brief
    assert "docs.python.org" in brief
