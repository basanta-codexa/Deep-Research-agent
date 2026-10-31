"""Web tools: the agent's window onto the internet.

Tools are built by a factory rather than defined at module level so that
settings, cache and backend can be injected. Nothing here reads a global.
"""

from __future__ import annotations

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


def make_web_tools(
    settings: Settings,
    *,
    cache: Cache | None = None,
    backend: SearchBackend | None = None,
) -> list[Tool]:
    cache = cache or Cache(settings.cache_path, ttl_s=settings.cache_ttl_s)
    backend = backend or CachedSearch(
        DuckDuckGoBackend(timeout=settings.request_timeout), cache
    )

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
    async def fetch_page(url: Annotated[str, Field(min_length=8, max_length=2000)]) -> str:
        """Download one URL and return its readable text (boilerplate removed).

        Use this after web_search, on the specific URL you want to quote. The
        text is truncated, so long pages lose their tail — search again with a
        narrower query rather than assuming you saw everything.

        Args:
            url: Absolute http(s) URL, e.g. https://example.com/article.
        """
        try:
            document = await fetch(
                url, cache=cache, timeout=settings.request_timeout
            )
        except FetchError as exc:
            return f"ERROR: {exc}"

        header = [
            f"URL: {document.final_url}",
            f"TITLE: {document.title or '(untitled)'}",
            f"CHARS: {len(document.text)}"
            + (" (truncated download)" if document.truncated else ""),
        ]
        return "\n".join(header) + "\n---\n" + document.text

    return [web_search, fetch_page]
