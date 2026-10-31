"""Runtime configuration, read from environment variables.

Rule: configuration is read once, at the edge of the program, and passed down as
an object. No module-level globals, no ``os.getenv`` scattered through the code.
That is what makes the eval harness able to run the same code against five
different models in a loop.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

Provider = Literal["ollama", "openai"]


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value else default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {raw!r}") from exc


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class Settings:
    provider: Provider = "ollama"
    model: str = "qwen3.5:4b"
    base_url: str | None = None
    api_key: str | None = None
    temperature: float = 0.2
    max_tokens: int | None = None
    # Local reasoning models expose a "thinking" stream. Off by default:
    # thinking tokens are billed as output and we do not use them yet.
    think: bool = False
    # Ollama's default context is 4096 tokens, which a research agent blows
    # through in two steps. Bigger = more memory, slower prompt processing.
    num_ctx: int = 8192
    # Retrieval
    cache_path: str = "cache/agent.sqlite3"
    cache_ttl_s: int = 86_400
    request_timeout: float = 20.0

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            provider=_env_str("RA_PROVIDER", "ollama"),  # type: ignore[arg-type]
            model=_env_str("RA_MODEL", "qwen3.5:4b"),
            base_url=os.getenv("RA_BASE_URL") or None,
            api_key=os.getenv("RA_API_KEY") or None,
            temperature=_env_float("RA_TEMPERATURE", 0.2),
            max_tokens=int(os.getenv("RA_MAX_TOKENS") or 0) or None,
            think=_env_bool("RA_THINK", False),
            num_ctx=int(os.getenv("RA_NUM_CTX") or 8192),
            cache_path=_env_str("RA_CACHE_PATH", "cache/agent.sqlite3"),
            cache_ttl_s=int(os.getenv("RA_CACHE_TTL") or 86_400),
            request_timeout=_env_float("RA_TIMEOUT", 20.0),
        )
