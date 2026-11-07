"""Prices, kept honest by being explicit about what is unknown.

Three rules:

  1. **Unknown is not free.** A model that is not in the table returns `None`,
     and the trace says "unpriced" instead of "$0.00". A wrong zero is worse
     than a missing number: it silently deletes a cost from every report.
  2. **These are what *this deployment* pays**, not vendor list prices. A free
     tier really is 0.0, and that is the number that belongs in the trace.
  3. **Override beats the table.** `RA_PRICE_INPUT` / `RA_PRICE_OUTPUT` are USD
     per million tokens and apply to every model, for when you switch tiers or
     providers without editing code.

Prices change; the table is data, not truth. Re-check it before quoting a dollar
figure anywhere.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .llm import Usage


@dataclass(frozen=True, slots=True)
class Price:
    """USD per million tokens."""

    input_per_mtok: float
    output_per_mtok: float


# provider, or "provider:model" for a per-model price.
PRICES: dict[str, Price] = {
    # Local inference has no API bill. Electricity is somebody else's problem.
    "ollama": Price(0.0, 0.0),
    # Groq free tier. Paid tier: set RA_PRICE_INPUT / RA_PRICE_OUTPUT.
    "groq": Price(0.0, 0.0),
    # OpenRouter list prices, USD per million tokens (checked 2026-11-07).
    "openrouter:openai/gpt-oss-20b": Price(0.03, 0.13),
    "openrouter:openai/gpt-oss-120b": Price(0.013, 0.049),
    # Example paid entries; delete or edit for your account.
    "openai:gpt-4o-mini": Price(0.15, 0.60),
    "openai:gpt-4o": Price(2.50, 10.00),
}


def _override() -> Price | None:
    """Global override from the environment. Both halves are required."""
    raw_in = os.getenv("RA_PRICE_INPUT")
    raw_out = os.getenv("RA_PRICE_OUTPUT")
    if not raw_in or not raw_out:
        return None
    try:
        return Price(float(raw_in), float(raw_out))
    except ValueError:
        return None


def lookup(provider: str, model: str) -> Price | None:
    """Price for this call, or None when we genuinely do not know."""
    override = _override()
    if override is not None:
        return override
    if (specific := PRICES.get(f"{provider}:{model}")) is not None:
        return specific
    return PRICES.get(provider)


def estimate_cost(price: Price, prompt_tokens: int, completion_tokens: int) -> float:
    return (
        prompt_tokens / 1_000_000 * price.input_per_mtok
        + completion_tokens / 1_000_000 * price.output_per_mtok
    )


def apply_cost(
    provider: str, model: str, usage: Usage
) -> tuple[Usage, bool]:
    """Fill `usage.cost_usd`; return (usage, priced?).

    The flag matters: the trace aggregates unpriced calls and refuses to print a
    total that silently excludes them.
    """
    price = lookup(provider, model)
    if price is None:
        return usage, False
    usage.cost_usd = estimate_cost(price, usage.prompt_tokens, usage.completion_tokens)
    return usage, True
