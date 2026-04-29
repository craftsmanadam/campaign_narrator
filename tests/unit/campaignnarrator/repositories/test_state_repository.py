"""Unit tests for StateRepository facade."""

from __future__ import annotations

from pathlib import Path

from campaignnarrator.domain.models import (
    ActorState,
    ActorType,
    EncounterPhase,
    EncounterState,
    GameState,
)
from campaignnarrator.repositories.encounter_repository import EncounterRepository
from campaignnarrator.repositories.player_repository import PlayerRepository
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
        actor_ids=("pc:talia",),
        player_actor_id="pc:talia",
    )


class FakeCompendiumRepository:
    def __init__(self, texts: dict[str, str]) -> None:
        self._texts = texts

    def load_reference_text(self, reference: str) -> str:
        if reference not in self._texts:
            raise FileNotFoundError(reference)
        return self._texts[reference]


def test_load_returns_game_state_with_player_and_encounter(tmp_path: Path) -> None:
    player_repo = PlayerRepository(tmp_path)
    player_repo.save(_minimal_actor())
    encounter_repo = EncounterRepository(tmp_path)
    encounter_repo.save(_minimal_encounter())
    repo = StateRepository(player_repo=player_repo, encounter_repo=encounter_repo)

    game_state = repo.load()

    assert game_state.encounter is not None
    assert game_state.encounter.encounter_id == "goblin-camp"


def test_load_returns_none_encounter_when_no_active_encounter(tmp_path: Path) -> None:
    player_repo = PlayerRepository(tmp_path)
    player_repo.save(_minimal_actor())
    encounter_repo = EncounterRepository(tmp_path)
    repo = StateRepository(player_repo=player_repo, encounter_repo=encounter_repo)

    game_state = repo.load()

    assert game_state.encounter is None


def test_load_player_enriches_references_when_compendium_provided(
    tmp_path: Path,
) -> None:
    compendium = FakeCompendiumRepository(
        {
            "DND.SRD.Wiki-0.5.2/Feats.md#Alert": "Alert feat text",
        }
    )
    player_repo = PlayerRepository(tmp_path)
    player_repo.save(TALIA)
    encounter_repo = EncounterRepository(tmp_path)
    repo = StateRepository(
        player_repo=player_repo,
        encounter_repo=encounter_repo,
        compendium=compendium,
    )

    player = repo.load_player()

    assert "Alert feat text" in player.references


def test_load_player_returns_empty_references_when_no_compendium(
    tmp_path: Path,
) -> None:
    player_repo = PlayerRepository(tmp_path)
    player_repo.save(TALIA)
    encounter_repo = EncounterRepository(tmp_path)
    repo = StateRepository(player_repo=player_repo, encounter_repo=encounter_repo)

    player = repo.load_player()

    assert player.references == ()


def test_save_strips_references_from_player_before_persisting(tmp_path: Path) -> None:
    player_repo = PlayerRepository(tmp_path)
    player_repo.save(TALIA)
    encounter_repo = EncounterRepository(tmp_path)
    encounter_repo.save(_minimal_encounter())
    repo = StateRepository(player_repo=player_repo, encounter_repo=encounter_repo)

    game_state = GameState(encounter=_minimal_encounter())
    repo.save(game_state)

    reloaded_player = repo.load_player()
    assert reloaded_player.references == ()


def test_save_with_none_encounter_does_not_write_encounter_file(
    tmp_path: Path,
) -> None:
    player_repo = PlayerRepository(tmp_path)
    player_repo.save(_minimal_actor())
    encounter_repo = EncounterRepository(tmp_path)
    repo = StateRepository(player_repo=player_repo, encounter_repo=encounter_repo)

    game_state = GameState(encounter=None)
    repo.save(game_state)

    assert encounter_repo.load_active() is None


def test_enrich_skips_missing_compendium_references(tmp_path: Path) -> None:
    compendium = FakeCompendiumRepository({})  # no entries
    player_repo = PlayerRepository(tmp_path)
    player_repo.save(TALIA)  # TALIA has feat references that won't be found
    encounter_repo = EncounterRepository(tmp_path)
    repo = StateRepository(
        player_repo=player_repo,
        encounter_repo=encounter_repo,
        compendium=compendium,
    )

    player = repo.load_player()

    assert player.references == ()


def test_load_player_returns_actor_from_player_repo(tmp_path: Path) -> None:
    """load_player() reads from player_repo and returns the player ActorState."""
    player_repo = PlayerRepository(tmp_path)
    player_repo.save(_minimal_actor())
    repo = StateRepository(player_repo, EncounterRepository(tmp_path))
    player = repo.load_player()
    assert player.actor_id == _minimal_actor().actor_id


def test_load_encounter_returns_none_when_no_active_encounter(tmp_path: Path) -> None:
    """load_encounter() returns None when there is no active.json."""
    repo = StateRepository(PlayerRepository(tmp_path), EncounterRepository(tmp_path))
    assert repo.load_encounter() is None


def test_save_player_persists_actor(tmp_path: Path) -> None:
    """save_player() writes the actor to player_repo."""
    player_repo = PlayerRepository(tmp_path)
    repo = StateRepository(player_repo, EncounterRepository(tmp_path))
    repo.save_player(_minimal_actor())
    loaded = player_repo.load()
    assert loaded.actor_id == _minimal_actor().actor_id


def test_save_encounter_persists_encounter(tmp_path: Path) -> None:
    """save_encounter() writes the encounter to encounter_repo."""
    enc_repo = EncounterRepository(tmp_path)
    repo = StateRepository(PlayerRepository(tmp_path), enc_repo)
    enc = _minimal_encounter()
    repo.save_encounter(enc)
    loaded = enc_repo.load_active()
    assert loaded is not None
    assert loaded.encounter_id == enc.encounter_id
