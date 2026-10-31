"""Search: one interface, swappable backends.

The agent never learns which search engine you use. That matters because search
APIs die, rate-limit, and change pricing more often than any other dependency in
this project.

DuckDuckGo is the default because it needs no API key, which keeps the project
runnable by anyone who clones it.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

from ddgs import DDGS

from .cache import Cache


class SearchError(Exception):
    """Backend refused or failed. Callers turn this into tool text."""


@dataclass(slots=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    rank: int = 0

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "rank": self.rank,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SearchResult":
        return cls(
            title=data["title"],
            url=data["url"],
            snippet=data["snippet"],
            rank=data.get("rank", 0),
        )


class SearchBackend(Protocol):
    name: str

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        ...


class DuckDuckGoBackend:
    """No API key, no cost. `ddgs` scrapes HTML, so it is rate-limited by IP."""

    name = "duckduckgo"

    def __init__(self, timeout: float = 20.0, retries: int = 1) -> None:
        self.timeout = timeout
        self.retries = retries

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        def _blocking_call() -> list[dict]:
            return DDGS(timeout=int(self.timeout)).text(query, max_results=max_results)

        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                # `ddgs` is synchronous HTTP. Calling it directly would freeze the
                # event loop for the whole request — including any other
                # sub-agents running concurrently (step 6). to_thread moves it off.
                rows = await asyncio.to_thread(_blocking_call)
                break
            except Exception as exc:
                last = exc
                if attempt < self.retries:
                    await asyncio.sleep(1.5 * (attempt + 1))
        else:
            raise SearchError(f"search failed: {type(last).__name__}: {last}")

        return [
            SearchResult(
                title=(row.get("title") or "").strip(),
                url=row.get("href") or row.get("url") or "",
                snippet=(row.get("body") or "").strip(),
                rank=i + 1,
            )
            for i, row in enumerate(rows)
            if row.get("href") or row.get("url")
        ]


class CachedSearch:
    """Decorator around a backend: same interface, adds a persistent cache."""

    def __init__(self, backend: SearchBackend, cache: Cache, ttl_s: int = 3_600):
        self.backend = backend
        self.cache = cache
        self.ttl_s = ttl_s
        self.name = f"{backend.name}+cache"

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        key = f"search:{self.backend.name}:{max_results}:{query.strip().lower()}"
        cached = await self.cache.aget(key)
        if cached is not None:
            return [SearchResult.from_dict(row) for row in cached]

        results = await self.backend.search(query, max_results)
        await self.cache.aset(
            key, [r.to_dict() for r in results], ttl_s=self.ttl_s
        )
        return results
