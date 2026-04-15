"""Unit tests for StateRepository facade."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from campaignnarrator.domain.models import (
    ActorState,
    ActorType,
    EncounterPhase,
    EncounterState,
    GameState,
)
from campaignnarrator.repositories.actor_repository import ActorRepository
from campaignnarrator.repositories.encounter_repository import EncounterRepository
from campaignnarrator.repositories.state_repository import StateRepository

from tests.fixtures.fighter_talia import TALIA


def _minimal_actor() -> ActorState:
    return ActorState(
        actor_id="pc:talia",
        name="Talia",
        actor_type=ActorType.PC,
        hp_current=12,
        hp_max=12,
        armor_class=15,
        strength=10,
        dexterity=10,
        constitution=10,
        intelligence=10,
        wisdom=10,
        charisma=10,
        proficiency_bonus=2,
        initiative_bonus=0,
        speed=30,
        attacks_per_action=1,
        action_options=(),
        ac_breakdown=(),
    )


def _minimal_encounter() -> EncounterState:
    return EncounterState(
        encounter_id="goblin-camp",
        phase=EncounterPhase.SOCIAL,
        setting="A ruined roadside camp.",
        actors={"pc:talia": _minimal_actor()},
    )


class FakeCompendiumRepository:
    def __init__(self, texts: dict[str, str]) -> None:
        self._texts = texts

    def load_reference_text(self, reference: str) -> str:
        if reference not in self._texts:
            raise FileNotFoundError(reference)
        return self._texts[reference]


def test_load_returns_game_state_with_player_and_encounter(tmp_path: Path) -> None:
    actor_repo = ActorRepository(tmp_path)
    actor_repo.save(_minimal_actor())
    encounter_repo = EncounterRepository(tmp_path)
    encounter_repo.save(_minimal_encounter())
    repo = StateRepository(actor_repo=actor_repo, encounter_repo=encounter_repo)

    game_state = repo.load()

    assert game_state.player.actor_id == "pc:talia"
    assert game_state.encounter is not None
    assert game_state.encounter.encounter_id == "goblin-camp"


def test_load_returns_none_encounter_when_no_active_encounter(tmp_path: Path) -> None:
    actor_repo = ActorRepository(tmp_path)
    actor_repo.save(_minimal_actor())
    encounter_repo = EncounterRepository(tmp_path)
    repo = StateRepository(actor_repo=actor_repo, encounter_repo=encounter_repo)

    game_state = repo.load()

    assert game_state.encounter is None


def test_load_enriches_player_references_when_compendium_provided(
    tmp_path: Path,
) -> None:
    compendium = FakeCompendiumRepository(
        {
            "DND.SRD.Wiki-0.5.2/Feats.md#Alert": "Alert feat text",
        }
    )
    actor_repo = ActorRepository(tmp_path)
    actor_repo.save(TALIA)
    encounter_repo = EncounterRepository(tmp_path)
    repo = StateRepository(
        actor_repo=actor_repo,
        encounter_repo=encounter_repo,
        compendium=compendium,
    )

    game_state = repo.load()

    assert "Alert feat text" in game_state.player.references


def test_load_returns_empty_references_when_no_compendium(tmp_path: Path) -> None:
    actor_repo = ActorRepository(tmp_path)
    actor_repo.save(TALIA)
    encounter_repo = EncounterRepository(tmp_path)
    repo = StateRepository(actor_repo=actor_repo, encounter_repo=encounter_repo)

    game_state = repo.load()

    assert game_state.player.references == ()


def test_save_strips_references_from_player_before_persisting(tmp_path: Path) -> None:
    actor_with_refs = replace(TALIA, references=("feat text",))
    actor_repo = ActorRepository(tmp_path)
    actor_repo.save(TALIA)
    encounter_repo = EncounterRepository(tmp_path)
    encounter_repo.save(_minimal_encounter())
    repo = StateRepository(actor_repo=actor_repo, encounter_repo=encounter_repo)

    game_state = GameState(player=actor_with_refs, encounter=_minimal_encounter())
    repo.save(game_state)

    reloaded = repo.load()
    assert reloaded.player.references == ()


def test_save_with_none_encounter_does_not_write_encounter_file(
    tmp_path: Path,
) -> None:
    actor_repo = ActorRepository(tmp_path)
    actor_repo.save(_minimal_actor())
    encounter_repo = EncounterRepository(tmp_path)
    repo = StateRepository(actor_repo=actor_repo, encounter_repo=encounter_repo)

    game_state = GameState(player=_minimal_actor(), encounter=None)
    repo.save(game_state)

    assert encounter_repo.load_active() is None


def test_enrich_skips_missing_compendium_references(tmp_path: Path) -> None:
    compendium = FakeCompendiumRepository({})  # no entries
    actor_repo = ActorRepository(tmp_path)
    actor_repo.save(TALIA)  # TALIA has feat references that won't be found
    encounter_repo = EncounterRepository(tmp_path)
    repo = StateRepository(
        actor_repo=actor_repo,
        encounter_repo=encounter_repo,
        compendium=compendium,
    )

    game_state = repo.load()

    assert game_state.player.references == ()
