from __future__ import annotations

import asyncio

from research_agent.retrieval.cache import Cache


def test_cache_counts_hits_misses_and_sets(tmp_path):
    async def check() -> None:
        cache = Cache(tmp_path / "cache.sqlite3", ttl_s=60)

        assert await cache.aget("missing") is None
        await cache.aset("key", {"value": 1})
        assert await cache.aget("key") == {"value": 1}

        stats = cache.stats()
        assert stats["enabled"] is True
        assert stats["lookups"] == 2
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["sets"] == 1
        assert stats["hit_rate"] == 0.5
        assert stats["rows"] == 1
        assert stats["live"] == 1

    asyncio.run(check())


def test_an_expired_entry_is_a_miss_not_a_hit(tmp_path):
    async def check() -> None:
        cache = Cache(tmp_path / "cache.sqlite3", ttl_s=60)
        await cache.aset("key", {"value": 1}, ttl_s=-1)

        assert await cache.aget("key") is None
        stats = cache.stats()
        assert stats["misses"] == 1
        assert stats["hits"] == 0
        assert stats["expired"] == 1

    asyncio.run(check())
