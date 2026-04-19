"""Application settings loaded from environment variables and optional .env file."""

from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for CampaignNarrator.

    All fields are read from environment variables (case-insensitive).
    A .env file in the working directory is loaded if present; values
    set directly in the environment always take precedence.

    Fields:
        embedding_provider: "ollama" or "stub". Controls which EmbeddingAdapter
            ApplicationFactory constructs. Use "stub" in acceptance tests.
        embedding_model: Model name passed to the embedding provider.
            Default matches the nomic-embed-text model used by OllamaEmbeddingAdapter.
        embedding_base_url: Base URL for the Ollama embedding endpoint.
        lancedb_path: Absolute or relative path to the LanceDB data directory.
            Empty string (default) causes ApplicationFactory to derive the path
            from data_root: {data_root}/memory/lancedb/.
    """

    embedding_provider: Literal["stub", "ollama"] = "ollama"
    embedding_model: str = "nomic-embed-text"
    embedding_base_url: str = "http://localhost:11434"
    lancedb_path: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
