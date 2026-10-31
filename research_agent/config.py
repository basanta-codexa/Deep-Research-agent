"""Runtime configuration, read from environment variables.

Rule: configuration is read once, at the edge of the program, and passed down as
an object. No module-level globals, no ``os.getenv`` scattered through the code.
That is what makes the eval harness able to run the same code against five
different models in a loop.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Provider = Literal["ollama", "groq", "openai"]

# (default model, default base url) per provider.
PROVIDER_DEFAULTS: dict[str, tuple[str, str]] = {
    "ollama": ("qwen3.5:4b", "http://localhost:11434"),
    "groq": ("openai/gpt-oss-120b", "https://api.groq.com/openai/v1"),
    "openai": ("gpt-4.1-mini", "https://api.openai.com/v1"),
}

_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def load_dotenv(path: Path = _ENV_FILE) -> None:
    """Minimal .env reader. Real environment variables always win.

    That precedence matters: CI sets RA_MODEL=..., and your local .env must not
    silently override it. Also keeps secrets out of the repo (see .gitignore).
    """
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value else default


def _env_any(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


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
        load_dotenv()
        provider = _env_str("RA_PROVIDER", "ollama")
        default_model, default_url = PROVIDER_DEFAULTS.get(
            provider, PROVIDER_DEFAULTS["ollama"]
        )
        return cls(
            provider=provider,  # type: ignore[arg-type]
            model=_env_str("RA_MODEL", default_model),
            base_url=os.getenv("RA_BASE_URL") or default_url,
            api_key=cls._resolve_api_key(provider),
            temperature=_env_float("RA_TEMPERATURE", 0.2),
            max_tokens=int(os.getenv("RA_MAX_TOKENS") or 0) or None,
            think=_env_bool("RA_THINK", False),
            num_ctx=int(os.getenv("RA_NUM_CTX") or 8192),
            cache_path=_env_str("RA_CACHE_PATH", "cache/agent.sqlite3"),
            cache_ttl_s=int(os.getenv("RA_CACHE_TTL") or 86_400),
            request_timeout=_env_float("RA_TIMEOUT", 20.0),
        )

    @staticmethod
    def _resolve_api_key(provider: str) -> str | None:
        explicit = _env_any("RA_API_KEY")
        if explicit:
            return explicit
        if provider == "groq":
            return _env_any("GROQ_API_KEY", "groq_api_key")
        if provider == "openai":
            return _env_any("OPENAI_API_KEY", "openai_api_key")
        return None

    def provider_default_url(self) -> str:
        return PROVIDER_DEFAULTS.get(
            self.provider, PROVIDER_DEFAULTS["ollama"]
        )[1]

    def safe_summary(self) -> str:
        """Loggable config. Never print the key itself."""
        key = "***" if self.api_key else "none"
        return (
            f"provider={self.provider} model={self.model} "
            f"base_url={self.base_url} api_key={key}"
        )
