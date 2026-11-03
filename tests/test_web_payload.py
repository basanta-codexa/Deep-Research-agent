from __future__ import annotations

from research_agent.evidence import EvidenceStore
from research_agent.pipeline import PipelineResult
from research_agent.writer import Report
from web.payload import build_payload

URL = "https://docs.python.org/3/glossary.html#term-global-interpreter-lock"
TEXT = (
    "The global interpreter lock, or GIL, is a mutex that protects access to "
    "Python objects. It prevents multiple threads from executing Python "
    "bytecodes at once. This simplifies memory management at the cost of "
    "CPU-bound parallelism."
)
QUOTE = "It prevents multiple threads from executing Python bytecodes at once."
CLAIM = "The GIL lets only one thread run Python bytecode at a time."


def _result(*, with_span: bool = True) -> tuple[PipelineResult, object]:
    store = EvidenceStore()
    store.register_source(URL, TEXT, "Python Glossary")
    item = store.add(claim=CLAIM, quote=QUOTE, url=URL)
    assert item is not None
    item.support = "supported"
    item.support_reason = "The quote says exactly what the claim says."
    item.trust = "primary"
    if not with_span:
        item.span_start = None
        item.span_end = None
        item.match = "missing"

    body = f"The GIL serializes bytecode execution [{item.id}]."
    report = Report(
        markdown=f"# The GIL\n\n{body}\n",
        body=body,
        cited_ids=[item.id],
        word_count=5,
    )
    result = PipelineResult(question="What is the GIL?", store=store, report=report)
    return result, item


def test_payload_carries_the_exact_span():
    result, item = _result()
    payload = build_payload(result)

    source = payload["sources"][0]
    passage = source["passages"][0]

    assert source["number"] == 1
    assert source["url"] == URL
    assert passage["span"]["start"] == item.span_start
    assert passage["span"]["end"] == item.span_end
    assert source["text"][passage["span"]["start"] : passage["span"]["end"]] == QUOTE
    assert passage["quote"] == QUOTE
    assert passage["support"] == "supported"
    assert passage["trust"] == "primary"


def test_html_uses_the_same_numbering_as_the_payload():
    result, _ = _result()
    payload = build_payload(result)
    assert 'data-refs="1"' in payload["html"]
    assert payload["stats"]["cited_passages"] == 1
    assert payload["stats"]["cited_sources"] == 1


def test_missing_stored_span_is_relocated_from_the_quote():
    result, _ = _result(with_span=False)
    payload = build_payload(result)
    passage = payload["sources"][0]["passages"][0]
    assert passage["span"] is not None
    text = payload["sources"][0]["text"]
    assert text[passage["span"]["start"] : passage["span"]["end"]] == QUOTE


def test_only_cited_sources_are_sent():
    result, item = _result()
    other = result.store.add(
        claim="CPython uses reference counting for most memory management.",
        quote="This simplifies memory management",
        url="https://example.com/other",
    )
    assert other is not None
    result.store.register_source("https://example.com/other", "This simplifies memory management.")

    payload = build_payload(result)
    assert [source["number"] for source in payload["sources"]] == [1]
    assert all("example.com" not in source["url"] for source in payload["sources"])


def test_cost_is_none_when_no_trace_was_recorded():
    result, _ = _result()
    payload = build_payload(result)
    assert payload["cost_usd"] is None
    assert payload["trace"] == {}


def test_verdicts_are_zero_filled():
    result, _ = _result()
    payload = build_payload(result)
    assert payload["verdicts"] == {
        "supported": 0,
        "partial": 0,
        "unsupported": 0,
        "contradicted": 0,
    }
