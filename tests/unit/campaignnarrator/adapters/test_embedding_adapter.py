"""Unit tests for embedding adapters."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest
from campaignnarrator.adapters.embedding_adapter import (
    EmbeddingError,
    OllamaEmbeddingAdapter,
    StubEmbeddingAdapter,
)

_EXPECTED_DIMENSIONS = StubEmbeddingAdapter.dimensions


def test_stub_adapter_dimensions_is_768() -> None:
    adapter = StubEmbeddingAdapter()
    assert adapter.dimensions == _EXPECTED_DIMENSIONS


def test_stub_adapter_embed_returns_768_floats() -> None:
    adapter = StubEmbeddingAdapter()
    result = adapter.embed("Malachar stood at the docks.")
    assert len(result) == _EXPECTED_DIMENSIONS
    assert all(isinstance(v, float) for v in result)


def test_stub_adapter_embed_is_deterministic() -> None:
    """Same text always produces the same vector."""
    adapter = StubEmbeddingAdapter()
    text = "The fog-shrouded docks loomed ahead."
    first = adapter.embed(text)
    second = adapter.embed(text)
    assert first == second


def test_stub_adapter_different_texts_produce_different_vectors() -> None:
    adapter = StubEmbeddingAdapter()
    a = adapter.embed("Malachar stood at the docks.")
    b = adapter.embed("The barmaid served ale.")
    assert a != b


def test_stub_adapter_values_are_in_valid_float_range() -> None:
    adapter = StubEmbeddingAdapter()
    result = adapter.embed("any text")
    assert all(-1.0 <= v <= 1.0 for v in result)


def _make_ollama(base_url: str = "http://localhost:11434") -> OllamaEmbeddingAdapter:
    return OllamaEmbeddingAdapter(base_url=base_url, model="nomic-embed-text")


def test_ollama_adapter_dimensions_is_768() -> None:
    assert _make_ollama().dimensions == _EXPECTED_DIMENSIONS


def test_ollama_adapter_embed_calls_correct_endpoint() -> None:
    fake_vector = [0.1] * _EXPECTED_DIMENSIONS
    mock_response = MagicMock()
    mock_response.json.return_value = {"embedding": fake_vector}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.post", return_value=mock_response) as mock_post:
        result = _make_ollama().embed("Malachar stood at the docks.")

    mock_post.assert_called_once_with(
        "http://localhost:11434/api/embeddings",
        json={"model": "nomic-embed-text", "prompt": "Malachar stood at the docks."},
        timeout=30.0,
    )
    assert result == fake_vector


def test_ollama_adapter_embed_returns_embedding_list() -> None:
    fake_vector = [0.5] * _EXPECTED_DIMENSIONS
    mock_response = MagicMock()
    mock_response.json.return_value = {"embedding": fake_vector}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.post", return_value=mock_response):
        result = _make_ollama().embed("any text")

    assert result == fake_vector


def test_ollama_adapter_raises_embedding_error_on_http_failure() -> None:
    with (
        patch("httpx.post", side_effect=httpx.RequestError("connection refused")),
        pytest.raises(EmbeddingError, match="connection refused"),
    ):
        _make_ollama().embed("any text")


def test_ollama_adapter_raises_embedding_error_on_http_status_error() -> None:
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500", request=MagicMock(), response=MagicMock()
    )
    with (
        patch("httpx.post", return_value=mock_response),
        pytest.raises(EmbeddingError, match="Ollama HTTP error"),
    ):
        _make_ollama().embed("any text")


def test_ollama_adapter_raises_embedding_error_on_empty_response() -> None:
    mock_response = MagicMock()
    mock_response.json.return_value = {"embedding": []}
    mock_response.raise_for_status = MagicMock()

    with (
        patch("httpx.post", return_value=mock_response),
        pytest.raises(EmbeddingError, match="empty embedding"),
    ):
        _make_ollama().embed("any text")


def test_ollama_adapter_strips_trailing_slash_from_base_url() -> None:
    fake_vector = [0.1] * _EXPECTED_DIMENSIONS
    mock_response = MagicMock()
    mock_response.json.return_value = {"embedding": fake_vector}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.post", return_value=mock_response) as mock_post:
        OllamaEmbeddingAdapter(
            base_url="http://localhost:11434/", model="nomic-embed-text"
        ).embed("text")

    called_url = mock_post.call_args[0][0]
    assert called_url == "http://localhost:11434/api/embeddings"
