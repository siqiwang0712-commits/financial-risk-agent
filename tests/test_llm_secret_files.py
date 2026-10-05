from __future__ import annotations

import pytest
from finrisk.llm import StructuredLLMProvider, provider_from_env


def test_llm_file_secret_has_precedence(monkeypatch, tmp_path):
    secret = tmp_path / "provider-key"
    secret.write_text(" mounted-test-key\n", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "stale-inline-test-key")
    monkeypatch.setenv("OPENAI_API_KEY_FILE", str(secret))
    monkeypatch.setenv("FINRISK_LLM_PROVIDER", "openai")
    assert provider_from_env().api_key == "mounted-test-key"


def test_unreadable_llm_secret_does_not_fall_back(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "stale-inline-test-key")
    monkeypatch.setenv("OPENAI_API_KEY_FILE", str(tmp_path / "missing"))
    with pytest.raises(RuntimeError, match="refusing to fall back"):
        StructuredLLMProvider()


def test_explicit_provider_key_remains_supported(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY_FILE", str(tmp_path / "missing"))
    assert StructuredLLMProvider(api_key="explicit-test-key").api_key == "explicit-test-key"
