"""StateRepository facade over actor, encounter, and compendium repositories."""

from __future__ import annotations

import contextlib
from dataclasses import replace

from campaignnarrator.domain.models import ActorState, GameState
from campaignnarrator.repositories.actor_repository import ActorRepository
from campaignnarrator.repositories.compendium_repository import CompendiumRepository
from campaignnarrator.repositories.encounter_repository import EncounterRepository


class StateRepository:
    """Facade: the single interface the orchestrator uses for all game state."""

    def __init__(
        self,
        actor_repo: ActorRepository,
        encounter_repo: EncounterRepository,
        compendium: CompendiumRepository | None = None,
    ) -> None:
        self._actor_repo = actor_repo
        self._encounter_repo = encounter_repo
        self._compendium = compendium

    def load(self) -> GameState:
        """Load current game state with enriched player references."""
        player = self._actor_repo.load_player()
        if self._compendium is not None:
            player = _enrich_actor_references(player, self._compendium)
        encounter = self._encounter_repo.load_active()
        return GameState(player=player, encounter=encounter)

    def save(self, state: GameState) -> None:
        """Persist game state. Strips transient references before saving."""
        self._actor_repo.save(_strip_actor_references(state.player))
        if state.encounter is not None:
            self._encounter_repo.save(state.encounter)


def _enrich_actor_references(
    actor: ActorState,
    compendium: CompendiumRepository,
) -> ActorState:
    texts: list[str] = []
    for feat in actor.feats:
        if feat.reference is not None:
            with contextlib.suppress(FileNotFoundError):
                texts.append(compendium.load_reference_text(feat.reference))
    for resource in actor.resources:
        if resource.reference is not None:
            with contextlib.suppress(FileNotFoundError):
                texts.append(compendium.load_reference_text(resource.reference))
    for item in actor.inventory:
        if item.reference is not None:
            with contextlib.suppress(FileNotFoundError):
                texts.append(compendium.load_reference_text(item.reference))
    return replace(actor, references=tuple(texts))


def _strip_actor_references(actor: ActorState) -> ActorState:
    return replace(actor, references=())
