"""Unit tests for BackstoryAgent."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from campaignnarrator.agents.backstory_agent import BackstoryAgent


def _make_agent(text: str = "You grew up by the sea.") -> BackstoryAgent:
    mock_adapter = MagicMock()
    mock_adapter.generate_text.return_value = text
    return BackstoryAgent(adapter=mock_adapter)


def test_draft_returns_text() -> None:
    agent = _make_agent("You grew up by the sea.")
    result = agent.draft(
        fragments="grew up by the sea, lost family to raiders",
        character_name="Aldric",
        race="Human",
        class_name="fighter",
    )
    assert result == "You grew up by the sea."


def test_draft_raises_on_empty_response() -> None:
    agent = _make_agent("   ")
    with pytest.raises(ValueError, match="empty backstory"):
        agent.draft(
            fragments="something",
            character_name="Aldric",
            race="Human",
            class_name="fighter",
        )
