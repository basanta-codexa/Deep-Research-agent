"""What the browser receives when a run finishes.

The report is only half the story. The other half is the *audit trail*: for
every citation number we send the page text the agent actually read, plus the
character offsets of the exact quote. That is what makes the UI's highlight
honest — the browser is not re-searching for the quote, it is told where it is.

Contract with the writer:
  * ``renumber(report.body, store)`` is the same function the report used, so
    citation numbers in the HTML and numbers in this payload cannot drift.
  * every cited id is looked up and its stored span is sent. A record missing
    from the store is dropped rather than rendered as a dead link. The writer
    only cites citable evidence, but this layer does not assume it: an
    uncitable record would still show its verdict instead of a broken drawer.
"""

from __future__ import annotations

from typing import Any

from research_agent.evidence import Evidence, EvidenceStore, locate_quote
from research_agent.pipeline import PipelineResult
from research_agent.writer import domain, renumber

from .render import render_markdown

_VERDICTS = ("supported", "partial", "unsupported", "contradicted")


def build_payload(result: PipelineResult) -> dict[str, Any]:
    report = result.report
    if report is None:
        raise ValueError("cannot build a UI payload without a report")

    store = result.store
    _, url_order, id_number = renumber(report.body, store)
    # `markdown` is normally already numbered by the writer; this second pass
    # is a no-op there but keeps hand-built reports (tests, saved artifacts)
    # from leaking raw [ev_...] ids into the HTML.
    markdown = renumber(report.markdown, store)[0]

    sources: dict[int, dict[str, Any]] = {}
    for url, number in url_order:
        sources[number] = {
            "number": number,
            "url": url,
            "domain": domain(url),
            "title": store.titles.get(url) or _first_title(store, url) or domain(url),
            # The text the agent read. Spans index into this string, so the
            # browser can highlight without guessing. Bounded by read_source's
            # window (<= 8k chars per page).
            "text": store.source_text(url),
            "passages": [],
        }

    for evidence_id in report.cited_ids:
        item = store.get(evidence_id)
        if item is None:
            continue
        number = id_number.get(evidence_id, 0)
        source = sources.get(number)
        if source is None:
            continue
        source["passages"].append(_passage(item, number, source["text"]))

    ordered = [sources[number] for number in sorted(sources) if sources[number]["passages"]]

    verdicts = {name: 0 for name in _VERDICTS}
    if result.verification is not None:
        verdicts.update(result.verification.counts())

    trace = result.trace.summary() if result.trace is not None else {}
    stats = store.stats()

    return {
        "question": result.question,
        "html": render_markdown(markdown),
        "markdown": markdown,
        "sources": ordered,
        "stats": {
            **stats,
            "cited_passages": sum(len(source["passages"]) for source in ordered),
            "cited_sources": len(ordered),
            "words": report.word_count,
            "verdicts": verdicts,
            "contradictions": len(result.verification.contradictions)
            if result.verification is not None
            else 0,
        },
        "verdicts": verdicts,
        "usage": {
            "prompt": result.usage.prompt_tokens,
            "completion": result.usage.completion_tokens,
            "total": result.usage.total_tokens,
        },
        "timings": {key: round(value, 3) for key, value in result.timings.items()},
        "trace": trace,
        "cost_usd": trace.get("cost_usd"),
        "unpriced_models": trace.get("unpriced_models", []),
        "run": {
            "provider": result.trace.attributes.get("provider", "")
            if result.trace is not None
            else "",
            "model": result.trace.attributes.get("model", "")
            if result.trace is not None
            else "",
            "judge_model": result.trace.attributes.get("judge_model", "")
            if result.trace is not None
            else "",
            "trace_id": result.trace.trace_id if result.trace is not None else "",
        },
    }


def _first_title(store: EvidenceStore, url: str) -> str:
    for item in store.items:
        if item.url == url and item.title:
            return item.title
    return ""


def _passage(item: Evidence, number: int, text: str) -> dict[str, Any]:
    start, end = item.span_start, item.span_end

    # Belt and braces: if a stored span is missing (older artifact, edited
    # source), or no longer lines up with the quote, locate it again. Spans are
    # computed against the longest text registered for a URL; if a later fetch
    # replaced that text, the old offsets would silently point at the wrong
    # characters. Re-checking is cheap and keeps the highlight honest.
    if text and start is not None and end is not None:
        snippet = text[max(0, start) : max(0, end)]
        if snippet != item.quote and " ".join(snippet.split()) != " ".join(item.quote.split()):
            located = locate_quote(text, item.quote)
            if located.ok:
                start, end = located.start, located.end
    if (start is None or end is None) and text:
        located = locate_quote(text, item.quote)
        if located.ok:
            start, end = located.start, located.end

    if text and start is not None and end is not None:
        start = max(0, min(start, len(text)))
        end = max(start, min(end, len(text)))

    span = None
    if start is not None and end is not None:
        span = {"start": start, "end": end, "length": end - start}

    return {
        "id": item.id,
        "number": number,
        "claim": item.claim,
        "quote": item.quote,
        "support": item.support,
        "support_reason": item.support_reason,
        "trust": item.trust,
        "match": item.match,
        "confidence": item.confidence,
        "span": span,
    }
