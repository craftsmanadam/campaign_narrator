"""Thin wrapper around the OpenAI Responses API."""

from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI


class OpenAIAdapter:
    """Provide text and structured JSON completions through the Responses API."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url is not None:
            client_kwargs["base_url"] = base_url
        if timeout_seconds is not None:
            client_kwargs["timeout"] = timeout_seconds
        self._client = OpenAI(**client_kwargs)
        self.model = model
        self._timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> OpenAIAdapter:
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
        schema_name: str,
        json_schema: dict[str, object],
    ) -> dict[str, Any]:
        """Request JSON output that must match the supplied JSON schema."""

        response = self._client.responses.create(
            model=self.model,
            instructions=instructions,
            input=input_text,
            text={
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "schema": json_schema,
                    "strict": True,
                }
            },
            **self._timeout_kwargs(),
        )
        return self._parse_json_response(response.output_text)

    def generate_text(self, *, instructions: str, input_text: str) -> str:
        """Request plain text output from the model."""

        response = self._client.responses.create(
            model=self.model,
            instructions=instructions,
            input=input_text,
            text={"format": {"type": "text"}},
            **self._timeout_kwargs(),
        )
        output_text = response.output_text
        if not output_text.strip():
            raise ValueError("empty output")  # noqa: TRY003
        return output_text

    def _timeout_kwargs(self) -> dict[str, float]:
        if self._timeout_seconds is None:
            return {}
        return {"timeout": self._timeout_seconds}

    def _parse_json_response(self, output_text: str) -> dict[str, Any]:
        if not output_text.strip():
            raise ValueError("empty output")  # noqa: TRY003
        payload = json.loads(output_text)
        if not isinstance(payload, dict):
            raise TypeError("not object")  # noqa: TRY003
        return payload
