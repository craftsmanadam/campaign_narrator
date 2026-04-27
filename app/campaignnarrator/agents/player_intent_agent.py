"""Agent that classifies player input into a typed PlayerIntent."""

from __future__ import annotations

import json
import logging

from pydantic_ai import Agent

from campaignnarrator.adapters.pydantic_ai_adapter import PydanticAIAdapter
from campaignnarrator.agents.prompts import PLAYER_INTENT_INSTRUCTIONS
from campaignnarrator.domain.models import (
    EncounterPhase,
    NpcPresence,
    NpcPresenceStatus,
    PlayerIntent,
)

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
        npc_presences: tuple[NpcPresence, ...] = (),
    ) -> PlayerIntent:
        """Return a PlayerIntent classifying the player's raw input."""
        payload: dict[str, object] = {
            "phase": phase.value,
            "setting": setting,
            "recent_events": list(recent_events),
            "actor_summaries": list(actor_summaries),
            "player_input": raw_text,
        }
        if npc_presences:
            npc_list = []
            for p in npc_presences:
                if p.status is NpcPresenceStatus.DEPARTED:
                    continue
                entry: dict[str, object] = {
                    "actor_id": p.actor_id,
                    "status": p.status.value,
                }
                if p.name_known:
                    entry["display_name"] = p.display_name
                else:
                    entry["description"] = p.description
                npc_list.append(entry)
            if npc_list:
                payload["npc_presences"] = npc_list
        result = self._agent.run_sync(
            json.dumps(payload, indent=2, sort_keys=True)
        ).output
        _log.debug(
            "Intent classified: category=%s check_hint=%r target_npc_id=%r reason=%r"
            " input=%r",
            result.category,
            result.check_hint,
            result.target_npc_id,
            result.reason,
            raw_text,
        )
        return result
