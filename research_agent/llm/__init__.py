"""LLM layer public surface + the one factory function.

Code outside this package imports from here:

    from research_agent.llm import create_client
    client = create_client(settings)
"""

from __future__ import annotations

from ..config import Settings
from .base import (
    LLMClient,
    LLMError,
    LLMResponse,
    Message,
    PermanentLLMError,
    ToolCall,
    TransientLLMError,
    Usage,
)
from .ollama import OllamaClient
from .openai_compat import OpenAICompatClient

__all__ = [
    "LLMClient",
    "LLMError",
    "LLMResponse",
    "Message",
    "PermanentLLMError",
    "ToolCall",
    "TransientLLMError",
    "Usage",
    "OllamaClient",
    "OpenAICompatClient",
    "create_client",
]


def create_client(settings: Settings) -> LLMClient:
    """Build the adapter named by config. The only place provider names appear."""
    if settings.provider == "ollama":
        return OllamaClient(
            model=settings.model,
            base_url=settings.base_url or "http://localhost:11434",
            think=settings.think,
            num_ctx=settings.num_ctx,
        )
    if settings.provider in ("groq", "openai"):
        if not settings.api_key:
            raise ValueError(
                f"provider {settings.provider!r} needs an API key. Set RA_API_KEY "
                f"or {settings.provider.upper()}_API_KEY in the environment or .env"
            )
        return OpenAICompatClient(
            model=settings.model,
            base_url=settings.base_url or settings.provider_default_url(),
            api_key=settings.api_key,
            name=settings.provider,
        )
    raise ValueError(f"unknown provider: {settings.provider!r}")
