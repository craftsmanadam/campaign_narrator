"""Embedding adapter protocol and implementations."""

from __future__ import annotations

import random
from typing import Protocol, runtime_checkable

import httpx


class EmbeddingError(Exception):
    """Raised when an embedding provider call fails."""


class _EmptyEmbeddingError(EmbeddingError):
    """Raised when an embedding provider returns an empty vector."""

    def __init__(self) -> None:
        """Raise with a fixed 'empty embedding' message."""
        super().__init__("empty embedding")


class _HttpStatusEmbeddingError(EmbeddingError):
    """Raised when Ollama returns an HTTP error status."""

    def __init__(self, exc: Exception) -> None:
        """Raise wrapping the original HTTP exception in the message."""
        super().__init__(f"Ollama HTTP error: {exc}")


@runtime_checkable
class EmbeddingAdapter(Protocol):
    """Protocol for text embedding providers."""

    dimensions: int

    def embed(self, text: str) -> list[float]:
        """Return a fixed-length float vector representing the text."""
        ...


class StubEmbeddingAdapter:
    """Deterministic pseudo-random embeddings for testing.

    Uses Python's random.Random seeded on the input text so that the same
    text always produces the same vector. Produces 768-dim float32-range
    values in [-1.0, 1.0] — matching the nomic-embed-text output dimension
    so LanceDB table schemas remain compatible when switching to real embeddings.
    """

    dimensions: int = 768

    def embed(self, text: str) -> list[float]:
        """Return a deterministic 768-dim vector seeded on text."""
        rng = random.Random(text)
        return [rng.uniform(-1.0, 1.0) for _ in range(self.dimensions)]


class OllamaEmbeddingAdapter:
    """Calls the Ollama REST API to generate nomic-embed-text embeddings.

    Raises EmbeddingError on HTTP failure or empty embedding response.
    base_url trailing slashes are stripped to prevent double-slash URLs.
    """

    dimensions: int = 768

    def __init__(self, base_url: str, model: str) -> None:
        """Store Ollama base URL (trailing slash stripped) and model name."""
        self._base_url = base_url.rstrip("/")
        self._model = model

    def embed(self, text: str) -> list[float]:
        """Embed text via Ollama. Raises EmbeddingError on any failure."""
        try:
            response = httpx.post(
                f"{self._base_url}/api/embeddings",
                json={"model": self._model, "prompt": text},
                timeout=30.0,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise _HttpStatusEmbeddingError(exc) from exc
        except httpx.RequestError as exc:
            raise EmbeddingError(str(exc)) from exc

        embedding: list[float] = response.json().get("embedding", [])
        if not embedding:
            raise _EmptyEmbeddingError
        return embedding
