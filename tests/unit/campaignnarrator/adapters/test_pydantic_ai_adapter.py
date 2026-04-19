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


class _FakeOpenAIProvider:
    def __init__(self, *, api_key: str, base_url: str | None = None) -> None:
        self.api_key = api_key
        self.base_url = base_url


class _FakeOllamaProvider:
    def __init__(
        self, *, base_url: str | None = None, api_key: str | None = None
    ) -> None:
        self.base_url = base_url
        self.api_key = api_key


# Keep _FakeProvider as an alias used by generate_text tests (OpenAI-style signature)
_FakeProvider = _FakeOpenAIProvider


def test_from_env_configures_openai_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM_PROVIDER=openai should wire an OpenAIProvider with env credentials."""
    expected_timeout_seconds = 7.5

    monkeypatch.setattr(adapter_module, "OpenAIProvider", _FakeOpenAIProvider)
    monkeypatch.setattr(adapter_module, "OllamaProvider", _FakeOllamaProvider)
    monkeypatch.setattr(adapter_module, "OpenAIChatModel", _FakeModel)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.4")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", str(expected_timeout_seconds))
    monkeypatch.setenv("LLM_PROVIDER", "openai")

    adapter = PydanticAIAdapter.from_env()

    assert isinstance(adapter.provider, _FakeOpenAIProvider)
    assert adapter.provider.api_key == "test-key"
    assert adapter.provider.base_url == "https://example.invalid/v1"
    assert isinstance(adapter.model, _FakeModel)
    assert adapter.model.model_name == "gpt-5.4"
    assert adapter.timeout_seconds == expected_timeout_seconds


def test_from_env_configures_ollama_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM_PROVIDER=ollama should wire OllamaProvider for structured output."""
    monkeypatch.setattr(adapter_module, "OpenAIProvider", _FakeOpenAIProvider)
    monkeypatch.setattr(adapter_module, "OllamaProvider", _FakeOllamaProvider)
    monkeypatch.setattr(adapter_module, "OpenAIChatModel", _FakeModel)
    monkeypatch.setenv("OPENAI_API_KEY", "ollama")
    monkeypatch.setenv("OPENAI_MODEL", "orieg/gemma3-tools:12b-ft-v2")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")

    adapter = PydanticAIAdapter.from_env()

    assert isinstance(adapter.provider, _FakeOllamaProvider)
    assert adapter.provider.base_url == "http://localhost:11434/v1"
    assert isinstance(adapter.model, _FakeModel)
    assert adapter.model.model_name == "orieg/gemma3-tools:12b-ft-v2"


def test_generate_text_returns_plain_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """Text generation should expose the Pydantic AI output verbatim."""
    agents: list[_FakeAgent] = []

    def _agent_factory(
        model: object,
        *,
        output_type: object = str,
        instructions: str,
    ) -> _FakeAgent:
        agent = _FakeAgent(model, output_type=output_type, instructions=instructions)
        agent.output = "Talia addresses the wary goblin."
        agents.append(agent)
        return agent

    monkeypatch.setattr(adapter_module, "Agent", _agent_factory)
    monkeypatch.setattr(adapter_module, "OpenAIProvider", _FakeProvider)
    monkeypatch.setattr(adapter_module, "OllamaProvider", _FakeOllamaProvider)
    monkeypatch.setattr(adapter_module, "OpenAIChatModel", _FakeModel)

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


def test_generate_text_rejects_empty_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty text output should raise ValueError."""

    def _agent_factory(
        model: object, *, output_type: object = str, instructions: str
    ) -> _FakeAgent:
        agent = _FakeAgent(model, output_type=output_type, instructions=instructions)
        agent.output = "   "
        return agent

    monkeypatch.setattr(adapter_module, "Agent", _agent_factory)
    monkeypatch.setattr(adapter_module, "OpenAIProvider", _FakeProvider)
    monkeypatch.setattr(adapter_module, "OllamaProvider", _FakeOllamaProvider)
    monkeypatch.setattr(adapter_module, "OpenAIChatModel", _FakeModel)

    adapter = PydanticAIAdapter(api_key="test-key", model="gpt-5.4")

    with pytest.raises(ValueError, match="empty"):
        adapter.generate_text(instructions="narrator", input_text="go")


def test_generate_text_forwards_timeout_in_model_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Timeout configured on the adapter must reach run_sync as a model_settings entry."""  # noqa: E501
    agents: list[_FakeAgent] = []

    def _agent_factory(
        model: object, *, output_type: object = str, instructions: str
    ) -> _FakeAgent:
        agent = _FakeAgent(model, output_type=output_type, instructions=instructions)
        agent.output = "some output"
        agents.append(agent)
        return agent

    monkeypatch.setattr(adapter_module, "Agent", _agent_factory)
    monkeypatch.setattr(adapter_module, "OpenAIProvider", _FakeProvider)
    monkeypatch.setattr(adapter_module, "OllamaProvider", _FakeOllamaProvider)
    monkeypatch.setattr(adapter_module, "OpenAIChatModel", _FakeModel)

    adapter = PydanticAIAdapter(api_key="key", model="gpt-5.4", timeout_seconds=15.0)
    adapter.generate_text(instructions="narrator", input_text="go")

    assert agents[0].calls[0]["model_settings"] == {"timeout": 15.0}


def test_adapter_exposes_model_for_agent_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """adapter.model should return the OpenAIChatModel instance."""
    monkeypatch.setattr(adapter_module, "OpenAIProvider", _FakeProvider)
    monkeypatch.setattr(adapter_module, "OllamaProvider", _FakeOllamaProvider)
    monkeypatch.setattr(adapter_module, "OpenAIChatModel", _FakeModel)

    adapter = PydanticAIAdapter(api_key="key", model="gpt-5.4")

    assert isinstance(adapter.model, _FakeModel)
    assert adapter.model.model_name == "gpt-5.4"
