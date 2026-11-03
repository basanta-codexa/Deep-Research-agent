from __future__ import annotations

import json

from research_agent.evidence import Evidence, EvidenceStore, locate_quote

SOURCE = "https://docs.python.org/3/library/asyncio-task.html"


def test_locate_exact_returns_original_offsets():
    text = "Before. The quick brown fox jumps. After."
    span = locate_quote(text, "The quick brown fox jumps.")
    assert span.match == "exact"
    assert text[span.start : span.end] == "The quick brown fox jumps."


def test_locate_normalized_handles_quotes_case_and_whitespace():
    text = "He said \u201cdon\u2019t\u201d  do it.\nNext line follows here."
    span = locate_quote(text, '"don\'t" DO IT. next line follows here.')
    assert span.match == "normalized"
    # offsets point into the ORIGINAL text, not the normalised copy
    assert text[span.start : span.end].startswith("\u201cdon\u2019t\u201d")
    assert "do it." in text[span.start : span.end]


def test_locate_fragments_allows_ellipsis_but_still_verbatim():
    text = "Alpha beta gamma delta. Epsilon zeta eta theta."
    span = locate_quote(text, "Alpha beta gamma delta. ... Epsilon zeta eta theta.")
    assert span.match == "fragments"
    assert span.start < span.end


def test_locate_fragment_with_rewritten_words_is_missing():
    text = "Alpha beta gamma delta. Epsilon zeta eta theta."
    span = locate_quote(text, "Alpha beta gamma delta. ... Epsilon zeta eta OMEGA.")
    assert span.match == "missing"
    assert span.start is None


def test_locate_missing_quote():
    assert locate_quote("some page text", "a sentence that is not there").match == "missing"


def test_add_verifies_quote_against_registered_source():
    store = EvidenceStore()
    store.register_source(SOURCE, "By default the exception is propagated to the caller.")
    item = store.add(
        claim="The default behaviour propagates the exception",
        quote="the exception is propagated to the caller",
        url=SOURCE,
    )
    assert item is not None
    assert item.verified and item.match == "exact"
    assert item.span_start is not None


def test_add_flags_quote_outside_the_window_but_present_in_full_page():
    store = EvidenceStore(full_sources={SOURCE: "Header. The full page mentions cancellation here. Footer."})
    store.register_source(SOURCE, "Only this window was shown to the model.")
    item = store.add(
        claim="Cancellation is mentioned",
        quote="The full page mentions cancellation here.",
        url=SOURCE,
    )
    assert item is not None
    assert item.match == "outside_window"
    assert not item.verified
    assert item.exists_in_source


def test_exact_duplicate_is_merged():
    store = EvidenceStore()
    store.register_source(SOURCE, "A sentence that is quotable here.")
    first = store.add("claim one", "A sentence that is quotable here.", SOURCE)
    second = store.add("claim one", "A  sentence  that is quotable here.", SOURCE)
    assert first is not None and second is None
    assert store.duplicates == 1
    assert len(store) == 1


def test_near_duplicate_claim_from_same_url_is_merged():
    store = EvidenceStore()
    store.register_source(
        SOURCE, "First sentence about gather. Second sentence about callers."
    )
    store.add(
        "asyncio gather propagates the first exception to the caller",
        "First sentence about gather.",
        SOURCE,
    )
    second = store.add(
        "asyncio gather propagates the first exception to the caller directly",
        "Second sentence about callers.",
        SOURCE,
    )
    assert second is None
    assert store.near_duplicates == 1


def test_same_claim_from_different_url_is_not_merged():
    store = EvidenceStore()
    store.register_source(SOURCE, "Shared sentence here.")
    store.register_source("https://example.com/x", "Shared sentence here.")
    store.add("claim", "Shared sentence here.", SOURCE)
    item = store.add("claim", "Shared sentence here.", "https://example.com/x")
    assert item is not None
    assert len(store) == 2


def test_citable_requires_provenance_and_support():
    store = EvidenceStore()
    store.register_source(SOURCE, "The first exception is propagated to the caller.")
    item = store.add("claim", "The first exception is propagated to the caller.", SOURCE)
    assert item is not None and item in store.citable()

    item.support = "unsupported"
    assert item not in store.citable()
    item.support = "contradicted"
    assert item not in store.citable()
    item.support = "unjudged"
    assert item not in store.citable()
    item.support = "partial"
    assert item in store.citable()


def test_unverified_item_is_never_citable():
    store = EvidenceStore()
    item = store.add("claim", "a quote that is nowhere", SOURCE)
    assert item is not None and item.match == "missing"
    assert item not in store.citable()


def test_save_and_load_round_trip(tmp_path):
    store = EvidenceStore()
    store.register_source(SOURCE, "The first exception is propagated to the caller.")
    item = store.add("claim", "The first exception is propagated to the caller.", SOURCE)
    assert item is not None
    item.support = "supported"
    item.trust = "primary"

    path = store.save(tmp_path / "evidence.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["evidence"][0]["verified"] is True  # property, not just a field

    loaded = EvidenceStore.load(path)
    copy = loaded.get(item.id)
    assert copy is not None
    assert copy.support == "supported"
    assert copy.trust == "primary"
    assert copy.span_start == item.span_start
    assert loaded.get(item.id) in loaded.citable()


def test_evidence_dataclass_defaults_are_writer_safe():
    item = Evidence(id="ev_00000000", claim="c", quote="q", url="u")
    assert item.support == "unchecked"
    assert item.trust == "unknown"
    assert not item.verified
