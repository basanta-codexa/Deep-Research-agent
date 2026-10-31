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
    "create_client",
]


def create_client(settings: Settings) -> LLMClient:
    """Build the adapter named by config. The only place provider names appear."""
    if settings.provider == "ollama":
        return OllamaClient(
            model=settings.model,
            base_url=settings.base_url or "http://localhost:11434",
            think=settings.think,
        )
    if settings.provider == "openai":
        raise NotImplementedError(
            "OpenAI-compatible adapter lands in a later step. "
            "Set RA_PROVIDER=ollama for now."
        )
    raise ValueError(f"unknown provider: {settings.provider!r}")
