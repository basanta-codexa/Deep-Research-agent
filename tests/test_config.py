from __future__ import annotations

from research_agent.config import JUDGE_DEFAULTS, PROVIDER_DEFAULTS, Settings


def test_openrouter_provider_defaults():
    model, url = PROVIDER_DEFAULTS["openrouter"]
    assert model == "openai/gpt-oss-20b"
    assert url == "https://openrouter.ai/api/v1"
    assert JUDGE_DEFAULTS["openrouter"] == "openai/gpt-oss-20b"


def test_openrouter_key_is_resolved_from_env(monkeypatch):
    monkeypatch.delenv("RA_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    assert Settings._resolve_api_key("openrouter") == "test-key"


def test_openrouter_lowercase_key_is_resolved(monkeypatch):
    monkeypatch.delenv("RA_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("openrouter_api_key", "test-key")

    assert Settings._resolve_api_key("openrouter") == "test-key"
