"""Agent that classifies player input into a typed PlayerIntent."""

from __future__ import annotations

import json
import logging

from pydantic_ai import Agent

from campaignnarrator.adapters.pydantic_ai_adapter import PydanticAIAdapter
from campaignnarrator.agents.prompts import PLAYER_INTENT_INSTRUCTIONS
from campaignnarrator.domain.models import EncounterPhase, PlayerIntent

_log = logging.getLogger(__name__)

_PLAYER_INTENT_INSTRUCTIONS = PLAYER_INTENT_INSTRUCTIONS


class PlayerIntentAgent:
    """Classify player input into a PlayerIntent with category and check_hint."""

    def __init__(
        self,
        *,
        adapter: object,
        _agent: object | None = None,
    ) -> None:
        if _agent is not None:
            self._agent = _agent
        else:
            if not isinstance(adapter, PydanticAIAdapter):
                adapter_type = type(adapter).__name__
                msg = f"adapter must be a PydanticAIAdapter, got {adapter_type}"
                raise TypeError(msg)
            self._agent = Agent(
                adapter.model,
                output_type=PlayerIntent,
                instructions=_PLAYER_INTENT_INSTRUCTIONS,
            )

    def classify(
        self,
        raw_text: str,
        *,
        phase: EncounterPhase,
        setting: str,
        recent_events: tuple[str, ...],
        actor_summaries: tuple[str, ...],
    ) -> PlayerIntent:
        """Return a PlayerIntent classifying the player's raw input."""
        result = self._agent.run_sync(
            json.dumps(
                {
                    "phase": phase.value,
                    "setting": setting,
                    "recent_events": list(recent_events),
                    "actor_summaries": list(actor_summaries),
                    "player_input": raw_text,
                },
                indent=2,
                sort_keys=True,
            )
        ).output
        _log.debug(
            "Intent classified: category=%s check_hint=%r reason=%r input=%r",
            result.category,
            result.check_hint,
            result.reason,
            raw_text,
        )
        return result
