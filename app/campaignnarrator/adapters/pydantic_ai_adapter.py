"""Pydantic AI adapter for model-backed generation."""

from __future__ import annotations

import logging
import os
from dataclasses import replace

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.profiles import ModelProfile
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

_log = logging.getLogger(__name__)


def _ollama_structured_output_profile(model_name: str) -> ModelProfile | None:
    """Return an Ollama model profile that uses prompted structured output mode.

    Ollama rejects tool-call messages with null content (HTTP 400) and rejects
    complex JSON schemas in response_format: json_schema (HTTP 500).  Prompted
    mode embeds the schema in the system prompt and sends the simpler
    response_format: {"type": "json_object"}, which Ollama handles correctly.
    """
    base = OllamaProvider.model_profile(model_name)
    if base is None:
        return None
    return replace(base, default_structured_output_mode="prompted")


class PydanticAIAdapter:
    """Provide text output and expose model for agent construction."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        llm_provider: str = "ollama",
    ) -> None:
        """Wire the model backend based on llm_provider ('openai' or 'ollama')."""
        if llm_provider == "openai":
            provider: OllamaProvider | OpenAIProvider = OpenAIProvider(
                api_key=api_key, base_url=base_url
            )
            self._model = OpenAIChatModel(model, provider=provider)
        else:
            provider = OllamaProvider(
                base_url=base_url or "http://localhost:11434/v1",
                api_key=api_key,
            )
            self._model = OpenAIChatModel(
                model, provider=provider, profile=_ollama_structured_output_profile
            )
        self.provider = provider
        self.timeout_seconds = timeout_seconds

    @property
    def model(self) -> OpenAIChatModel:
        """Return the configured OpenAIChatModel for agent construction."""
        return self._model

    @classmethod
    def from_env(cls) -> PydanticAIAdapter:
        """Build an adapter from environment configuration."""
        api_key = os.getenv("OPENAI_API_KEY")
        model = os.getenv("OPENAI_MODEL")
        if not api_key or not model:
            raise ValueError(  # noqa: TRY003
                "OPENAI_API_KEY and OPENAI_MODEL must be set in the environment"
            )
        base_url = os.getenv("OPENAI_BASE_URL")
        timeout_raw = os.getenv("OPENAI_TIMEOUT_SECONDS")
        timeout_seconds = float(timeout_raw) if timeout_raw is not None else None
        llm_provider = os.getenv("LLM_PROVIDER", "ollama")
        return cls(
            api_key=api_key,
            model=model,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            llm_provider=llm_provider,
        )

    def generate_text(self, *, instructions: str, input_text: str) -> str:
        """Request plain text output from Pydantic AI."""
        _log.debug("generate_text input: %r", input_text[:200])
        agent = Agent(
            self._model,
            output_type=str,
            instructions=instructions,
        )
        result = agent.run_sync(
            input_text,
            model_settings=self._model_settings(),
        )
        output_text = result.output
        if not output_text.strip():
            _log.error(
                "generate_text returned empty output for input: %r", input_text[:200]
            )
            raise ValueError("empty output")  # noqa: TRY003
        _log.debug("generate_text output: %r", output_text[:200])
        return output_text

    def _model_settings(self) -> ModelSettings:
        """Return ModelSettings with timeout when set, empty dict otherwise."""
        if self.timeout_seconds is None:
            return {}
        return {"timeout": self.timeout_seconds}
