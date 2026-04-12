"""Unit tests for the Pydantic AI adapter."""

from __future__ import annotations

from dataclasses import dataclass

import campaignnarrator.adapters.pydantic_ai_adapter as adapter_module
import pytest
from campaignnarrator.adapters.pydantic_ai_adapter import PydanticAIAdapter


@dataclass
class _FakeRunResult:
    output: object


class _FakeAgent:
    def __init__(
        self,
        model: object,
        *,
        output_type: object = str,
        instructions: str,
    ) -> None:
        self.model = model
        self.output_type = output_type
        self.instructions = instructions
        self.calls: list[dict[str, object]] = []
        self.output: object = ""

    def run_sync(
        self,
        user_prompt: str,
        *,
        model_settings: dict[str, object] | None = None,
    ) -> _FakeRunResult:
        self.calls.append(
            {"user_prompt": user_prompt, "model_settings": model_settings or {}}
        )
        return _FakeRunResult(self.output)


class _FakeModel:
    def __init__(self, model_name: str, *, provider: object) -> None:
        self.model_name = model_name
        self.provider = provider


class _FakeProvider:
    def __init__(self, *, api_key: str, base_url: str | None = None) -> None:
        self.api_key = api_key
        self.base_url = base_url


def test_from_env_configures_the_pydantic_ai_model_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Environment configuration should flow into Pydantic AI provider/model setup."""

    expected_timeout_seconds = 7.5

    monkeypatch.setattr(adapter_module, "OpenAIProvider", _FakeProvider)
    monkeypatch.setattr(adapter_module, "OpenAIResponsesModel", _FakeModel)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.4")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", str(expected_timeout_seconds))

    adapter = PydanticAIAdapter.from_env()

    assert isinstance(adapter.provider, _FakeProvider)
    assert adapter.provider.api_key == "test-key"
    assert adapter.provider.base_url == "https://example.invalid/v1"
    assert isinstance(adapter.pydantic_model, _FakeModel)
    assert adapter.pydantic_model.model_name == "gpt-5.4"
    assert adapter.model == "gpt-5.4"
    assert adapter.timeout_seconds == expected_timeout_seconds


def test_generate_structured_json_parses_pydantic_ai_text_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Structured output should preserve the app's direct JSON object contract."""

    agents: list[_FakeAgent] = []

    def _agent_factory(
        model: object,
        *,
        output_type: object = str,
        instructions: str,
    ) -> _FakeAgent:
        agent = _FakeAgent(
            model,
            output_type=output_type,
            instructions=instructions,
        )
        agent.output = '{"outcome": "roll_requested"}'
        agents.append(agent)
        return agent

    monkeypatch.setattr(adapter_module, "Agent", _agent_factory)
    monkeypatch.setattr(adapter_module, "OpenAIProvider", _FakeProvider)
    monkeypatch.setattr(adapter_module, "OpenAIResponsesModel", _FakeModel)

    adapter = PydanticAIAdapter(
        api_key="test-key",
        model="gpt-5.4",
        base_url="https://example.invalid/v1",
        timeout_seconds=3.25,
    )

    payload = adapter.generate_structured_json(
        instructions="You are a rules adjudicator.",
        input_text="I try to calm the goblin scout.",
        schema_name="rules_adjudication",
        json_schema={
            "type": "object",
            "properties": {"outcome": {"type": "string"}},
            "required": ["outcome"],
            "additionalProperties": False,
        },
    )

    assert payload == {"outcome": "roll_requested"}
    assert agents[0].output_type is str
    assert agents[0].instructions == (
        "You are a rules adjudicator.\n\nReturn JSON for schema `rules_adjudication`."
    )
    assert agents[0].calls == [
        {
            "user_prompt": "I try to calm the goblin scout.",
            "model_settings": {"timeout": 3.25},
        }
    ]


def test_generate_text_returns_plain_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """Text generation should expose the Pydantic AI output verbatim."""

    agents: list[_FakeAgent] = []

    def _agent_factory(
        model: object,
        *,
        output_type: object = str,
        instructions: str,
    ) -> _FakeAgent:
        agent = _FakeAgent(
            model,
            output_type=output_type,
            instructions=instructions,
        )
        agent.output = "Talia addresses the wary goblin."
        agents.append(agent)
        return agent

    monkeypatch.setattr(adapter_module, "Agent", _agent_factory)
    monkeypatch.setattr(adapter_module, "OpenAIProvider", _FakeProvider)
    monkeypatch.setattr(adapter_module, "OpenAIResponsesModel", _FakeModel)

    adapter = PydanticAIAdapter(api_key="test-key", model="gpt-5.4")

    output = adapter.generate_text(
        instructions="You are a narrator.",
        input_text="Summarize the result.",
    )

    assert output == "Talia addresses the wary goblin."
    assert agents[0].output_type is str
    assert agents[0].instructions == "You are a narrator."
    assert agents[0].calls == [
        {"user_prompt": "Summarize the result.", "model_settings": {}}
    ]


def test_generate_structured_json_rejects_non_object_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Structured output should fail closed if Pydantic AI returns a non-object."""

    def _agent_factory(
        model: object,
        *,
        output_type: object = str,
        instructions: str,
    ) -> _FakeAgent:
        agent = _FakeAgent(
            model,
            output_type=output_type,
            instructions=instructions,
        )
        agent.output = '"not-json-object"'
        return agent

    monkeypatch.setattr(adapter_module, "Agent", _agent_factory)
    monkeypatch.setattr(adapter_module, "OpenAIProvider", _FakeProvider)
    monkeypatch.setattr(adapter_module, "OpenAIResponsesModel", _FakeModel)

    adapter = PydanticAIAdapter(api_key="test-key", model="gpt-5.4")

    with pytest.raises(TypeError, match="not object"):
        adapter.generate_structured_json(
            instructions="You are a rules adjudicator.",
            input_text="I try to calm the goblin scout.",
        )
