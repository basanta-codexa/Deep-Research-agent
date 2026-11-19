from .cache import Cache, CacheBackend, NullCache
from .fetch import Document, FetchError, fetch
from .search import (
    CachedSearch,
    DuckDuckGoBackend,
    SearchBackend,
    SearchError,
    SearchResult,
)

__all__ = [
    "Cache",
    "CacheBackend",
    "CachedSearch",
    "NullCache",
    "Document",
    "DuckDuckGoBackend",
    "FetchError",
    "SearchBackend",
    "SearchError",
    "SearchResult",
    "fetch",
]
