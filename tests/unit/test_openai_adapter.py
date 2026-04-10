"""Unit tests for the OpenAI adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass

import campaignnarrator.adapters.openai_adapter as openai_adapter_module
import pytest
from campaignnarrator.adapters.openai_adapter import OpenAIAdapter


@dataclass
class _FakeResponse:
    output_text: str


class _FakeResponses:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.response_text = ""

    def create(self, **kwargs: object) -> _FakeResponse:
        self.calls.append(kwargs)
        return _FakeResponse(self.response_text)


class _FakeOpenAI:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.responses = _FakeResponses()


def test_from_env_configures_the_real_client_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Environment configuration should flow into the OpenAI client constructor."""

    created_clients: list[_FakeOpenAI] = []

    def _factory(**kwargs: object) -> _FakeOpenAI:
        client = _FakeOpenAI(**kwargs)
        created_clients.append(client)
        return client

    monkeypatch.setattr(openai_adapter_module, "OpenAI", _factory)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.4")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "7.5")

    adapter = OpenAIAdapter.from_env()

    assert created_clients[0].kwargs == {
        "api_key": "test-key",
        "base_url": "https://example.invalid/v1",
        "timeout": 7.5,
    }
    assert adapter.model == "gpt-5.4"


def test_generate_structured_json_shapes_the_responses_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Structured output should use the Responses API JSON schema format."""

    fake_client = _FakeOpenAI(api_key="test-key")
    fake_client.responses.response_text = json.dumps({"outcome": "roll_requested"})
    monkeypatch.setattr(openai_adapter_module, "OpenAI", lambda **kwargs: fake_client)

    adapter = OpenAIAdapter(
        api_key="test-key",
        model="gpt-5.4",
        base_url="https://example.invalid/v1",
        timeout_seconds=3.25,
    )

    payload = adapter.generate_structured_json(
        instructions="You are a rules adjudicator.",
        input_text="I drink my potion of healing.",
        schema_name="potion_of_healing_adjudication",
        json_schema={
            "type": "object",
            "properties": {"outcome": {"type": "string"}},
            "required": ["outcome"],
            "additionalProperties": False,
        },
    )

    assert payload == {"outcome": "roll_requested"}
    assert fake_client.responses.calls == [
        {
            "model": "gpt-5.4",
            "instructions": "You are a rules adjudicator.",
            "input": "I drink my potion of healing.",
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "potion_of_healing_adjudication",
                    "schema": {
                        "type": "object",
                        "properties": {"outcome": {"type": "string"}},
                        "required": ["outcome"],
                        "additionalProperties": False,
                    },
                    "strict": True,
                }
            },
            "timeout": 3.25,
        }
    ]


def test_generate_text_returns_plain_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Text generation should expose the model output verbatim."""

    fake_client = _FakeOpenAI(api_key="test-key")
    fake_client.responses.response_text = "Talia drinks the potion."
    monkeypatch.setattr(openai_adapter_module, "OpenAI", lambda **kwargs: fake_client)

    adapter = OpenAIAdapter(api_key="test-key", model="gpt-5.4")

    output = adapter.generate_text(
        instructions="You are a narrator.",
        input_text="Summarize the result.",
    )

    assert output == "Talia drinks the potion."
    assert fake_client.responses.calls == [
        {
            "model": "gpt-5.4",
            "instructions": "You are a narrator.",
            "input": "Summarize the result.",
            "text": {"format": {"type": "text"}},
        }
    ]


def test_generate_structured_json_rejects_malformed_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Structured output should fail closed if the model does not return JSON."""

    fake_client = _FakeOpenAI(api_key="test-key")
    fake_client.responses.response_text = "not-json"
    monkeypatch.setattr(openai_adapter_module, "OpenAI", lambda **kwargs: fake_client)

    adapter = OpenAIAdapter(api_key="test-key", model="gpt-5.4")

    with pytest.raises(ValueError, match="Expecting value"):
        adapter.generate_structured_json(
            instructions="You are a rules adjudicator.",
            input_text="I drink my potion of healing.",
            schema_name="potion_of_healing_adjudication",
            json_schema={
                "type": "object",
                "properties": {"outcome": {"type": "string"}},
                "required": ["outcome"],
                "additionalProperties": False,
            },
        )
