from __future__ import annotations

from research_agent.evidence import EvidenceStore
from research_agent.writer import (
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


def test_brief_never_contains_urls():
    store = EvidenceStore()
    store.register_source("https://docs.python.org/3/x", "The quote lives here.")
    item = store.add("claim", "The quote lives here.", "https://docs.python.org/3/x")
    assert item is not None
    brief = build_brief(store.citable())
    assert "http" not in brief
    assert item.id in brief
    assert "docs.python.org" in brief
