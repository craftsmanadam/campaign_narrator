"""Campaign orchestrator for the potion-of-healing steel thread."""

from __future__ import annotations

from collections.abc import Callable

from campaignnarrator.agents.narrator_agent import NarratorAgent
from campaignnarrator.agents.rules_agent import RulesAgent
from campaignnarrator.domain.models import Narration, PotionOfHealingResolution
from campaignnarrator.repositories.memory_repository import MemoryRepository
from campaignnarrator.repositories.state_repository import StateRepository
from campaignnarrator.tools.state_updates import apply_potion_of_healing

_SUPPORTED_PLAYER_INPUT = "i drink my potion of healing"


class CampaignOrchestrator:
    """Execute the supported potion-of-healing flow end to end."""

    def __init__(
        self,
        *,
        state_repository: StateRepository,
        rules_agent: RulesAgent,
        memory_repository: MemoryRepository,
        narrator_agent: NarratorAgent,
        roll_dice: Callable[[str], int],
    ) -> None:
        self._state_repository = state_repository
        self._rules_agent = rules_agent
        self._memory_repository = memory_repository
        self._narrator_agent = narrator_agent
        self._roll_dice = roll_dice

    def run(self, player_input: str) -> Narration:
        """Handle a raw player input string and return player-facing narration."""

        normalized_input = _normalize_input(player_input)
        if normalized_input != _SUPPORTED_PLAYER_INPUT:
            raise ValueError("unsupported player input")  # noqa: TRY003

        player_character = self._state_repository.load_player_character()
        actor = _actor_name(player_character)
        if not _has_potion_of_healing(player_character):
            raise ValueError("missing potion of healing")  # noqa: TRY003

        adjudication = self._rules_agent.adjudicate_potion_of_healing(actor=actor)
        if adjudication.roll_request is None:
            raise ValueError("missing roll request")  # noqa: TRY003

        roll_total = self._roll_dice(adjudication.roll_request.expression)
        updated_player_character = apply_potion_of_healing(
            player_character,
            healing_amount=roll_total,
        )
        hp_before = int(player_character["hp"]["current"])
        hp_after = int(updated_player_character["hp"]["current"])
        resolution = PotionOfHealingResolution(
            roll_total=roll_total,
            healing_amount=roll_total,
            hp_before=hp_before,
            hp_after=hp_after,
        )
        narration = self._narrator_agent.narrate(adjudication, resolution)
        self._state_repository.save_player_character(updated_player_character)
        self._memory_repository.append_event(
            {
                "type": "potion_of_healing_resolved",
                "actor": actor,
                "input": player_input,
                "roll_request": {
                    "owner": adjudication.roll_request.owner,
                    "visibility": adjudication.roll_request.visibility,
                    "expression": adjudication.roll_request.expression,
                    "purpose": adjudication.roll_request.purpose,
                },
                "roll_total": roll_total,
                "healing_amount": resolution.healing_amount,
                "hp_before": hp_before,
                "hp_after": hp_after,
            }
        )
        return narration


def _normalize_input(player_input: str) -> str:
    return " ".join(player_input.casefold().split())


def _actor_name(player_character: dict[str, object]) -> str:
    actor = player_character.get("name") or player_character.get("character_id")
    if not isinstance(actor, str) or not actor.strip():
        raise ValueError("missing actor name")  # noqa: TRY003
    return actor


def _has_potion_of_healing(player_character: dict[str, object]) -> bool:
    inventory = player_character.get("inventory")
    if not isinstance(inventory, list):
        return False
    return any(
        isinstance(item, str)
        and item.lower() in {"potion-of-healing", "potion of healing"}
        for item in inventory
    )
