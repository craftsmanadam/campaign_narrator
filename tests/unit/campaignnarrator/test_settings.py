"""Unit tests for application settings."""

from __future__ import annotations

import pytest
from campaignnarrator.settings import Settings


def test_settings_embedding_provider_default() -> None:
    s = Settings()
    assert s.embedding_provider == "ollama"


def test_settings_embedding_model_default() -> None:
    s = Settings()
    assert s.embedding_model == "nomic-embed-text"


def test_settings_embedding_base_url_default() -> None:
    s = Settings()
    assert s.embedding_base_url == "http://localhost:11434"


def test_settings_lancedb_path_default_is_empty_string() -> None:
    """Empty string signals ApplicationFactory to derive path from data_root."""
    s = Settings()
    assert s.lancedb_path == ""


def test_settings_embedding_provider_overridden_by_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "stub")
    s = Settings()
    assert s.embedding_provider == "stub"


def test_settings_embedding_model_overridden_by_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-3-small")
    s = Settings()
    assert s.embedding_model == "text-embedding-3-small"


def test_settings_embedding_base_url_overridden_by_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMBEDDING_BASE_URL", "http://myhost:11434")
    s = Settings()
    assert s.embedding_base_url == "http://myhost:11434"


def test_settings_lancedb_path_overridden_by_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANCEDB_PATH", "/custom/path/lancedb")
    s = Settings()
    assert s.lancedb_path == "/custom/path/lancedb"


def test_settings_ignores_unrelated_env_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """extra='ignore' means OPENAI_* and other vars do not cause validation errors."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.4")
    monkeypatch.setenv("CAMPAIGNNARRATOR_DICE_SEED", "7")
    s = Settings()
    assert s.embedding_provider == "ollama"


def test_settings_data_root_default() -> None:
    """data_root defaults to tmp/data_store when DATA_ROOT is not set."""
    s = Settings()
    assert s.data_root == "tmp/data_store"


def test_settings_data_root_overridden_by_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATA_ROOT", "custom/path")
    s = Settings()
    assert s.data_root == "custom/path"
