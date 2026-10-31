"""Web tools: the agent's window onto the internet.

Tools are built by a factory rather than defined at module level so that
settings, cache and backend can be injected. Nothing here reads a global.

Three tools, three jobs:

  web_search  → links + snippets   (cheap, for breadth)
  fetch_page  → one URL's text     (expensive, for depth)
  read_source → search + fetch     (composite: the reliable path)

`read_source` exists because search results are not always fetchable (Stack
Overflow returns 403 to anything that looks like a bot). Rather than asking the
model to notice and retry, the fallback lives in code, where it cannot be
forgotten.
"""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import Field

from ..config import Settings
from ..retrieval.cache import Cache
from ..retrieval.fetch import FetchError, fetch
from ..retrieval.search import (
    CachedSearch,
    DuckDuckGoBackend,
    SearchBackend,
    SearchError,
)
from .registry import Tool, tool

_WORD = re.compile(r"[a-z0-9]{4,}")
MIN_PARAGRAPH = 60


def relevant_window(text: str, focus: str, max_chars: int) -> str:
    """Pick paragraphs that match `focus` instead of blindly taking the head.

    A docs page's first 2000 characters are navigation and an intro. The answer
    is usually 10,000 characters down. Keyword overlap is crude, but it beats
    truncating by position and it costs nothing.
    """
    if len(text) <= max_chars:
        return text

    terms = set(_WORD.findall(focus.lower()))
    paragraphs = [p.strip() for p in text.split("\n") if len(p.strip()) >= MIN_PARAGRAPH]
    if not terms or not paragraphs:
        return text[:max_chars]

    scored = []
    for index, paragraph in enumerate(paragraphs):
        low = paragraph.lower()
        score = sum(1 for term in terms if term in low)
        scored.append((score, index, paragraph))
    scored.sort(key=lambda item: (-item[0], item[1]))

    head = text[:350]
    used = len(head)
    picked: list[str] = [head]
    for score, _, paragraph in scored:
        if score == 0:
            break
        if used + len(paragraph) + 1 > max_chars:
            continue
        picked.append(paragraph)
        used += len(paragraph) + 1
        if used >= max_chars * 0.92:
            break
    return "\n".join(picked)


def _build_tools(
    settings: Settings, cache: Cache, backend: SearchBackend
) -> dict[str, Tool]:
    @tool
    async def web_search(
        query: Annotated[str, Field(min_length=2, max_length=200)],
        max_results: Annotated[int, Field(ge=1, le=8)] = 5,
    ) -> str:
        """Search the web and return titles, URLs and snippets.

        This returns links, not page content: call fetch_page on the URLs you
        want to read. Results are ranked; the first 2-3 are usually the best.

        Args:
            query: What to search for. Specific, 3-8 words works best.
            max_results: How many results to return (1-8).
        """
        try:
            results = await backend.search(query, max_results)
        except SearchError as exc:
            return f"ERROR: {exc}"
        if not results:
            return f"No results for {query!r}. Try fewer or different words."

        blocks = [
            f"[{r.rank}] {r.title}\n    url: {r.url}\n    {r.snippet}" for r in results
        ]
        return "\n\n".join(blocks)

    @tool
    async def fetch_page(
        url: Annotated[str, Field(min_length=8, max_length=2000)],
    ) -> str:
        """Download one URL and return its readable text (boilerplate removed).

        Use this after web_search, on the specific URL you want to quote. The
        text is truncated, so long pages lose their tail.

        Args:
            url: Absolute http(s) URL, e.g. https://example.com/article.
        """
        try:
            document = await fetch(url, cache=cache, timeout=settings.request_timeout)
        except FetchError as exc:
            return f"ERROR: {exc}"

        header = [
            f"URL: {document.final_url}",
            f"TITLE: {document.title or '(untitled)'}",
            f"CHARS: {len(document.text)}"
            + (" (truncated download)" if document.truncated else ""),
        ]
        return "\n".join(header) + "\n---\n" + document.text

    @tool
    async def read_source(
        query: Annotated[str, Field(min_length=3, max_length=200)],
        focus: Annotated[str, Field(max_length=300)] = "",
        max_chars: Annotated[int, Field(ge=100, le=8000)] = 2600,
    ) -> str:
        """Search, then read the best page that actually loads.

        Tries up to four results in order and skips ones that error (403, 404,
        PDFs), so you always get text or a clear failure. This is the cheapest
        way to get quotable evidence.

        Args:
            query: Specific search words, 3-8 of them.
            focus: Words from your sub-question. The most relevant paragraphs are
                kept instead of just the page's opening lines.
            max_chars: Roughly how much text to return (600-8000).
        """
        try:
            results = await backend.search(query, 4)
        except SearchError as exc:
            return f"ERROR: {exc}"
        if not results:
            return f"ERROR: no search results for {query!r}"

        failures: list[str] = []
        budget = max(300, min(int(max_chars), 8000))  # clamp, never reject
        for result in results:
            try:
                document = await fetch(
                    result.url, cache=cache, timeout=settings.request_timeout
                )
            except FetchError as exc:
                failures.append(f"{result.url} -> {exc}")
                continue

            window = relevant_window(
                document.text, focus or f"{query} {result.title}", budget
            )
            return (
                f"URL: {document.final_url}\n"
                f"TITLE: {document.title or result.title}\n"
                f"PAGE_CHARS: {len(document.text)} (showing {len(window)})\n"
                f"---\n{window}"
            )

        return "ERROR: every result failed to load:\n" + "\n".join(failures)

    return {"web_search": web_search, "fetch_page": fetch_page, "read_source": read_source}


def make_web_tools(
    settings: Settings,
    *,
    cache: Cache | None = None,
    backend: SearchBackend | None = None,
) -> list[Tool]:
    """All three tools, for the top-level agent."""
    cache = cache or Cache(settings.cache_path, ttl_s=settings.cache_ttl_s)
    backend = backend or CachedSearch(
        DuckDuckGoBackend(timeout=settings.request_timeout), cache
    )
    return list(_build_tools(settings, cache, backend).values())


def make_subagent_tools(
    settings: Settings,
    *,
    cache: Cache | None = None,
    backend: SearchBackend | None = None,
) -> list[Tool]:
    """Just `read_source`. A sub-agent with one good tool wanders less than one
    with three mediocre ones. Fewer choices = fewer wrong choices."""
    cache = cache or Cache(settings.cache_path, ttl_s=settings.cache_ttl_s)
    backend = backend or CachedSearch(
        DuckDuckGoBackend(timeout=settings.request_timeout), cache
    )
    return [_build_tools(settings, cache, backend)["read_source"]]
