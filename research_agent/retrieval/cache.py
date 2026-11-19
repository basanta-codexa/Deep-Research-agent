"""A SQLite cache with TTLs.

Why cache at all in an agent?

  * The same URL gets fetched repeatedly (sub-agents overlap, runs get re-tried).
  * Search engines rate-limit. Repeating a query 20 times per eval run will get
    you blocked.
  * Eval runs must be comparable. If every run sees different web pages, you
    are measuring the internet, not your prompt change.

SQLite because it needs zero infrastructure, survives process restarts, and is
easy to inspect with any GUI. `cache/` is gitignored.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Protocol

_SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    expires_at REAL NOT NULL
);
"""


class CacheBackend(Protocol):
    """What the retrieval layer needs. `Cache` and `NullCache` both satisfy it."""

    async def aget(self, key: str) -> Any | None: ...

    async def aset(self, key: str, value: Any, ttl_s: int | None = None) -> None: ...

    def stats(self) -> dict[str, Any]: ...


class Cache:
    def __init__(self, path: str | Path = "cache/agent.sqlite3", ttl_s: int = 86_400):
        self.path = Path(path)
        self.ttl_s = ttl_s
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Per-run counters. Without them an eval cannot say whether the cache
        # was warm, so a `--no-cache` delta has no attribution.
        self.hits = 0
        self.misses = 0
        self.sets = 0
        self._init_db()

    # -- sync internals; public API is async ----------------------------- #
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @staticmethod
    def _hash(key: str) -> str:
        # Keys can be entire URLs with query strings. Hash keeps rows small and
        # makes the primary key a fixed size.
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def _get(self, key: str) -> Any | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value, expires_at FROM kv WHERE key = ?", (self._hash(key),)
            ).fetchone()
        if row is None:
            return None
        value, expires_at = row
        if expires_at < time.time():
            return None
        return json.loads(value)

    def _set(self, key: str, value: Any, ttl_s: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO kv (key, value, expires_at) VALUES (?, ?, ?)",
                (self._hash(key), json.dumps(value), time.time() + ttl_s),
            )

    # -- async API: sqlite3 blocks, so it must not run on the event loop --- #
    async def aget(self, key: str) -> Any | None:
        value = await asyncio.to_thread(self._get, key)
        if value is None:
            self.misses += 1
        else:
            self.hits += 1
        return value

    async def aset(self, key: str, value: Any, ttl_s: int | None = None) -> None:
        await asyncio.to_thread(self._set, key, value, ttl_s or self.ttl_s)
        self.sets += 1

    def stats(self) -> dict[str, Any]:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM kv").fetchone()[0]
            live = conn.execute(
                "SELECT COUNT(*) FROM kv WHERE expires_at > ?", (time.time(),)
            ).fetchone()[0]
        lookups = self.hits + self.misses
        return {
            "path": str(self.path),
            "enabled": True,
            "rows": total,
            "live": live,
            "expired": total - live,
            "lookups": lookups,
            "hits": self.hits,
            "misses": self.misses,
            "sets": self.sets,
            "hit_rate": round(self.hits / lookups, 4) if lookups else None,
        }


class NullCache:
    """A cache-shaped no-op for the `--no-cache` ablation.

    The retrieval layer only needs `aget`/`aset`; keeping the same shape means
    the ablation changes caching, not the search path. It never touches disk.
    It still *counts* lookups, so the run can prove the switch took effect:
    every lookup is a miss and no write is stored.
    """

    def __init__(self) -> None:
        self.path = None
        self.ttl_s = 0
        self.hits = 0
        self.misses = 0
        self.sets = 0

    async def aget(self, key: str) -> Any | None:
        self.misses += 1
        return None

    async def aset(self, key: str, value: Any, ttl_s: int | None = None) -> None:
        self.sets += 1

    def stats(self) -> dict[str, Any]:
        return {
            "path": None,
            "enabled": False,
            "rows": 0,
            "live": 0,
            "expired": 0,
            "lookups": self.hits + self.misses,
            "hits": self.hits,
            "misses": self.misses,
            "sets": self.sets,
            "hit_rate": None,
        }
