"""The evidence store: the only material the writer is allowed to use.

Before this step, "the evidence" was whatever text happened to be in a sub-agent's
conversation. That is not evidence, it's context. Here it becomes a first-class
object with four properties:

  1. **Atomic** — one claim, one quote, one source.
  2. **Deduplicated** — eight agents reading four pages produce one copy, not eight.
  3. **Addressable** — every quote has character offsets into the text we fetched.
  4. **Verifiable** — if the quote is not in the page, we say so immediately,
     without asking a model.

Point 4 is the whole project thesis in miniature: the quote is checked against
the page, so a citation can be mechanically true or false.

Note on honesty: we verify the quote exists in the text the agent *read*. We do
not (yet) verify that the quote *supports the claim* — that is step 9.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from .subagent import SubAgentResult

_PUNCT = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u00a0": " ",
    }
)
_TOKEN = re.compile(r"[a-z0-9]{4,}")
_ELLIPSIS = re.compile(r"\.\.\.|\u2026|\s+\[\.\.\.\]\s+")
_CONF_RANK = {"low": 1, "medium": 2, "high": 3}
_EVIDENCE_FIELDS = {
    "id",
    "claim",
    "quote",
    "url",
    "title",
    "sub_questions",
    "confidence",
    "span_start",
    "span_end",
    "match",
    "support",
    "support_reason",
    "trust",
    "created_at",
}


# --------------------------------------------------------------------------- #
# Quote location
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class Span:
    start: int | None
    end: int | None
    match: str  # "exact" | "normalized" | "missing"

    @property
    def ok(self) -> bool:
        return self.match != "missing"


def _normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Lowercase, collapse whitespace, unify quotes — keeping index mapping.

    The map is the important part: after normalization the match position is
    meaningless, so we translate it back to offsets in the original text.
    """
    chars: list[str] = []
    origin: list[int] = []
    previous_space = False
    for index, char in enumerate(text):
        if char.isspace():
            if previous_space:
                continue
            char = " "
            previous_space = True
        else:
            previous_space = False
            char = char.translate(_PUNCT)
        chars.append(char.lower())
        origin.append(index)
    return "".join(chars), origin


def _find(text: str, needle: str) -> tuple[int, int, str] | None:
    """Exact search first, then normalized (whitespace/case/quote marks)."""
    position = text.find(needle)
    if position != -1:
        return position, position + len(needle), "exact"

    norm_text, origin = _normalize_with_map(text)
    norm_needle = _normalize_with_map(needle)[0].strip()
    if not norm_needle:
        return None
    position = norm_text.find(norm_needle)
    if position == -1:
        return None
    return origin[position], origin[position + len(norm_needle) - 1] + 1, "normalized"


def locate_quote(text: str, quote: str) -> Span:
    """Find `quote` in `text`, tolerating whitespace and editorial ellipses.

    Three ways a real quote fails a naive check:

      * typographic quotes / non-breaking spaces  → normalized match
      * "…" where the author elided a clause       → fragments match
      * the quote is in the page but outside the   → caller retries against the
        2,600-char window we showed the model        full page, see EvidenceStore
    """
    if not text or not quote:
        return Span(None, None, "missing")

    hit = _find(text, quote)
    if hit is not None:
        return Span(*hit)

    # Ellipsis: verify every retained fragment, in order, and keep the span that
    # covers them. Each fragment must still be verbatim — elision is allowed,
    # rewriting is not.
    fragments = [part.strip() for part in _ELLIPSIS.split(quote)]
    fragments = [part for part in fragments if len(part) >= 15]
    if len(fragments) >= 2:
        cursor = 0
        start: int | None = None
        end: int | None = None
        for fragment in fragments:
            hit = _find(text[cursor:], fragment)
            if hit is None:
                start = None
                break
            frag_start, frag_end, _ = hit
            frag_start += cursor
            frag_end += cursor
            if start is None:
                start = frag_start
            end = frag_end
            cursor = frag_end
        if start is not None and end is not None:
            return Span(start, end, "fragments")

    return Span(None, None, "missing")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.lower()))


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


# --------------------------------------------------------------------------- #
# The record
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class Evidence:
    id: str
    claim: str
    quote: str
    url: str
    title: str = ""
    sub_questions: list[str] = field(default_factory=list)
    confidence: str = "medium"
    span_start: int | None = None
    span_end: int | None = None
    match: str = "missing"
    # Filled in by step 9. "unchecked" exists so earlier stages can run alone;
    # the full pipeline always judges before writing.
    support: str = "unchecked"  # supported | partial | unsupported | contradicted
    support_reason: str = ""
    trust: str = "unknown"  # primary | community | aggregator | unknown
    created_at: float = field(default_factory=time.time)

    @property
    def verified(self) -> bool:
        """The quote was found in the text the agent actually read."""
        return self.match in {"exact", "normalized", "fragments"}

    @property
    def exists_in_source(self) -> bool:
        """The quote is in the page, even if it was outside the window we read.

        This is the dangerous middle ground: a real quote the model produced from
        memory rather than from the text it was shown. True sentence, false
        provenance — so it is not citable, but it is not "fabricated" either.
        """
        return self.verified or self.match == "outside_window"

    def to_dict(self) -> dict:
        # `verified` is a property, so asdict() would drop it — but downstream
        # consumers (the writer, the report) should not have to re-derive it.
        return {**asdict(self), "verified": self.verified}


class EvidenceStore:
    def __init__(self, full_sources: dict[str, str] | None = None) -> None:
        self._items: dict[str, Evidence] = {}
        self._sources: dict[str, str] = {}
        # Full page text, keyed by URL. The window we showed the model is a
        # truncation, not the truth; when a quote is not in the window we check
        # the page before calling it fabricated.
        self._full_sources = full_sources or {}
        self.titles: dict[str, str] = {}
        self.findings_seen = 0
        self.duplicates = 0
        self.near_duplicates = 0
        self.unverified = 0
        self.outside_window = 0

    # -- sources -------------------------------------------------------- #
    def register_source(self, url: str, text: str, title: str = "") -> None:
        if not url or not text:
            return
        if len(text) >= len(self._sources.get(url, "")):
            self._sources[url] = text
        if title:
            self.titles.setdefault(url, title)

    def source_text(self, url: str) -> str:
        return self._sources.get(url, "")

    # -- adding --------------------------------------------------------- #
    def add(
        self,
        claim: str,
        quote: str,
        url: str,
        sub_question: str = "",
        confidence: str = "medium",
        title: str = "",
    ) -> Evidence | None:
        """Add one finding. Returns the stored record, or None if it was a dupe."""
        claim = claim.strip()
        quote = quote.strip()
        if not claim or not quote:
            return None
        self.findings_seen += 1

        key = self._key(url, quote)
        existing = self._items.get(key)
        if existing is not None:
            self.duplicates += 1
            self._merge(existing, claim, sub_question, confidence)
            return None

        claim_tokens = _tokens(claim)
        for item in self._items.values():
            if item.url != url:
                continue
            if _jaccard(claim_tokens, _tokens(item.claim)) >= 0.85:
                self.near_duplicates += 1
                self._merge(item, claim, sub_question, confidence)
                return None

        span = locate_quote(self.source_text(url), quote)
        if not span.ok:
            # Not in the window — but is it in the page we fetched?
            page = self._full_sources.get(url, "")
            if page:
                full_span = locate_quote(page, quote)
                if full_span.ok:
                    span = Span(full_span.start, full_span.end, "outside_window")
                    self.outside_window += 1
        if not span.ok:
            self.unverified += 1

        record = Evidence(
            id=f"ev_{key[:8]}",
            claim=claim,
            quote=quote,
            url=url,
            title=title or self.titles.get(url, ""),
            sub_questions=[sub_question] if sub_question else [],
            confidence=confidence if confidence in _CONF_RANK else "medium",
            span_start=span.start,
            span_end=span.end,
            match=span.match,
        )
        self._items[key] = record
        return record

    def extend_from_results(self, results: Iterable[SubAgentResult]) -> None:
        for result in results:
            for url, text in result.source_texts.items():
                self.register_source(url, text, result.source_titles.get(url, ""))
            for finding in result.findings:
                self.add(
                    claim=finding.claim,
                    quote=finding.quote,
                    url=finding.url,
                    sub_question=result.question,
                    confidence=finding.confidence,
                )

    def _merge(
        self, item: Evidence, claim: str, sub_question: str, confidence: str
    ) -> None:
        if sub_question and sub_question not in item.sub_questions:
            item.sub_questions.append(sub_question)
        if _CONF_RANK.get(confidence, 0) > _CONF_RANK.get(item.confidence, 0):
            item.confidence = confidence
        if len(claim) > len(item.claim):
            item.claim = claim

    @staticmethod
    def _key(url: str, quote: str) -> str:
        normalized, _ = _normalize_with_map(quote[:400])
        return hashlib.sha1(f"{url}|{normalized}".encode("utf-8")).hexdigest()

    # -- access --------------------------------------------------------- #
    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self):
        return iter(self._items.values())

    @property
    def items(self) -> list[Evidence]:
        return list(self._items.values())

    @property
    def verified_items(self) -> list[Evidence]:
        return [item for item in self._items.values() if item.verified]

    def citable(self) -> list[Evidence]:
        """Only evidence the writer is allowed to cite.

        Two independent gates:
          * provenance — the quote must be in the text the agent read
          * support    — the quote must not contradict or fail to back the claim

        `unchecked` is allowed because stages can be run standalone; the full
        pipeline always verifies before writing.
        """
        return [
            item
            for item in self._items.values()
            if item.verified and item.support not in {
                "unsupported",
                "contradicted",
                "unjudged",
            }
        ]

    def get(self, evidence_id: str) -> Evidence | None:
        for item in self._items.values():
            if item.id == evidence_id:
                return item
        return None

    def coverage(self, questions: Sequence[str]) -> dict[str, int]:
        counts = {question: 0 for question in questions}
        for item in self._items.values():
            for question in item.sub_questions:
                if question in counts:
                    counts[question] += 1
        return counts

    def stats(self) -> dict:
        return {
            "findings_seen": self.findings_seen,
            "evidence_kept": len(self._items),
            "duplicates_exact": self.duplicates,
            "duplicates_near": self.near_duplicates,
            "unverified_quotes": self.unverified,
            "outside_window": self.outside_window,
            "sources": len(self._sources),
        }

    # -- publishing ----------------------------------------------------- #
    @classmethod
    def load(cls, path: str | Path) -> EvidenceStore:
        """Rebuild a store from a saved artifact.

        Spans are persisted, so a report can be regenerated without re-fetching
        anything — but sources are not stored, so quotes cannot be re-verified.
        """
        payload = json.loads(Path(path).read_text("utf-8"))
        store = cls()
        for raw in payload.get("evidence", []):
            fields = {key: value for key, value in raw.items() if key in _EVIDENCE_FIELDS}
            item = Evidence(**fields)
            store._items[store._key(item.url, item.quote)] = item
        store.findings_seen = payload.get("stats", {}).get("findings_seen", len(store))
        return store

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at": time.time(),
            "stats": self.stats(),
            "evidence": [item.to_dict() for item in self._items.values()],
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), "utf-8")
        return path

    def to_markdown(self) -> str:
        lines = [
            "| id | claim | source | verified | match | span | support | trust |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for item in self._items.values():
            span = (
                f"{item.span_start}-{item.span_end}"
                if item.span_start is not None
                else "-"
            )
            claim = item.claim.replace("|", "/")[:90]
            url = item.url.replace("|", "/")
            lines.append(
                f"| {item.id} | {claim} | {url} | "
                f"{'yes' if item.verified else 'NO'} | {item.match} | {span} | "
                f"{item.support} | {item.trust} |"
            )
        return "\n".join(lines)
