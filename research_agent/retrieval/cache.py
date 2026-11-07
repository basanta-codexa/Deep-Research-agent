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
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    expires_at REAL NOT NULL
);
"""


class Cache:
    def __init__(self, path: str | Path = "cache/agent.sqlite3", ttl_s: int = 86_400):
        self.path = Path(path)
        self.ttl_s = ttl_s
        self.path.parent.mkdir(parents=True, exist_ok=True)
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
        return await asyncio.to_thread(self._get, key)

    async def aset(self, key: str, value: Any, ttl_s: int | None = None) -> None:
        await asyncio.to_thread(self._set, key, value, ttl_s or self.ttl_s)

    def stats(self) -> dict[str, Any]:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM kv").fetchone()[0]
            live = conn.execute(
                "SELECT COUNT(*) FROM kv WHERE expires_at > ?", (time.time(),)
            ).fetchone()[0]
        return {"path": str(self.path), "rows": total, "live": live}


class NullCache:
    """A cache-shaped no-op for the `--no-cache` ablation.

    The retrieval layer only needs `aget`/`aset`; keeping the same shape means
    the ablation changes caching, not the search path. It never touches disk.
    """

    def __init__(self) -> None:
        self.path = None
        self.ttl_s = 0

    async def aget(self, key: str) -> Any | None:
        return None

    async def aset(self, key: str, value: Any, ttl_s: int | None = None) -> None:
        return None

    def stats(self) -> dict[str, Any]:
        return {"path": None, "rows": 0, "live": 0, "enabled": False}
