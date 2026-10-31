from .cache import Cache
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
    "CachedSearch",
    "Document",
    "DuckDuckGoBackend",
    "FetchError",
    "SearchBackend",
    "SearchError",
    "SearchResult",
    "fetch",
]
