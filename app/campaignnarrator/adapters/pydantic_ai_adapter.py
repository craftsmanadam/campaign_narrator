"""Pydantic AI adapter for model-backed generation."""

from __future__ import annotations

import os

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings


class PydanticAIAdapter:
    """Provide text output and expose model for agent construction."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.provider = OpenAIProvider(api_key=api_key, base_url=base_url)
        self._model = OpenAIChatModel(model, provider=self.provider)
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
        return cls(
            api_key=api_key,
            model=model,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )

    def generate_text(self, *, instructions: str, input_text: str) -> str:
        """Request plain text output from Pydantic AI."""
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
            raise ValueError("empty output")  # noqa: TRY003
        return output_text

    def _model_settings(self) -> ModelSettings:
        if self.timeout_seconds is None:
            return {}
        return {"timeout": self.timeout_seconds}
