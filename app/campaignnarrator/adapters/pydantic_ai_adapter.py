"""Pydantic AI adapter for model-backed generation."""

from __future__ import annotations

import json
import os
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider


class PydanticAIAdapter:
    """Provide text and structured output through Pydantic AI."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.provider = OpenAIProvider(api_key=api_key, base_url=base_url)
        self.pydantic_model = OpenAIResponsesModel(model, provider=self.provider)
        self.model = model
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> PydanticAIAdapter:
        """Build an adapter from environment configuration."""

        api_key = os.getenv("OPENAI_API_KEY")
        model = os.getenv("OPENAI_MODEL")
        if not api_key or not model:
            raise ValueError

        base_url = os.getenv("OPENAI_BASE_URL")
        timeout_raw = os.getenv("OPENAI_TIMEOUT_SECONDS")
        timeout_seconds = float(timeout_raw) if timeout_raw is not None else None
        return cls(
            api_key=api_key,
            model=model,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )

    def generate_structured_json(
        self,
        *,
        instructions: str,
        input_text: str,
        schema_name: str | None = None,
        json_schema: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        """Request JSON text through Pydantic AI and return the decoded object."""

        del json_schema

        agent = Agent(
            self.pydantic_model,
            output_type=str,
            instructions=self._structured_instructions(instructions, schema_name),
        )
        result = agent.run_sync(
            input_text,
            model_settings=self._model_settings(),
        )
        payload = json.loads(result.output)
        if not isinstance(payload, dict):
            raise TypeError("not object")  # noqa: TRY003
        return payload

    def generate_text(self, *, instructions: str, input_text: str) -> str:
        """Request plain text output from Pydantic AI."""

        agent = Agent(
            self.pydantic_model,
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

    def _model_settings(self) -> dict[str, float]:
        if self.timeout_seconds is None:
            return {}
        return {"timeout": self.timeout_seconds}

    def _structured_instructions(
        self,
        instructions: str,
        schema_name: str | None,
    ) -> str:
        if schema_name is None:
            return instructions
        return f"{instructions}\n\nReturn JSON for schema `{schema_name}`."
