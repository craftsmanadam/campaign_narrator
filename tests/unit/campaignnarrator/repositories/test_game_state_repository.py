"""Unit tests for GameStateRepository."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from campaignnarrator.domain.models import (
    ActorRegistry,
    CampaignState,
    EncounterState,
    GameState,
    ModuleState,
)
from campaignnarrator.repositories.game_state_repository import GameStateRepository
from campaignnarrator.repositories.player_repository import PlayerRepository

from tests.fixtures.fighter_talia import TALIA


def _make_repo(tmp_path: Path) -> GameStateRepository:
    mock_player_repo = MagicMock(spec=PlayerRepository)
    mock_player_repo.load.return_value = TALIA
    return GameStateRepository(
        state_path=tmp_path / "state" / "game_state.json",
        player_repo=mock_player_repo,
    )


def _make_campaign_state(
    *,
    campaign_id: str = "camp-1",
    current_module_id: str | None = None,
) -> CampaignState:
    return CampaignState(
        campaign_id=campaign_id,
        name="Test Campaign",
        setting="A test world.",
        narrator_personality="Neutral.",
        hidden_goal="Test goal.",
        bbeg_name="Test Boss",
        bbeg_description="A test villain.",
        milestones=(),
        current_milestone_index=0,
        starting_level=1,
        target_level=5,
        player_brief="Test brief.",
        player_actor_id=TALIA.actor_id,
        current_module_id=current_module_id,
    )


def _make_module_state(module_id: str = "module-001") -> ModuleState:
    return ModuleState(
        module_id=module_id,
        campaign_id="camp-1",
        title="Test Module",
        summary="Test summary.",
        guiding_milestone_id="m1",
    )


def _make_repo_with_campaign(
    tmp_path: Path,
    *,
    module_id: str = "module-001",
) -> GameStateRepository:
    """Seed game_state.json with campaign+module; return a fresh repo."""
    seed = _make_repo(tmp_path)
    seed.load()
    campaign = _make_campaign_state(current_module_id=module_id)
    module = _make_module_state(module_id)
    registry = ActorRegistry(actors={TALIA.actor_id: TALIA})
    seed.persist(GameState(campaign=campaign, module=module, actor_registry=registry))
    return _make_repo(tmp_path)


def _state_path(tmp_path: Path) -> Path:
    return tmp_path / "state" / "game_state.json"


# --- load() ---


def test_load_returns_game_state(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    gs = repo.load()
    assert isinstance(gs, GameState)


def test_load_merges_player_into_registry(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    gs = repo.load()
    assert TALIA.actor_id in gs.actor_registry.actors


def test_load_populates_campaign_when_present(tmp_path: Path) -> None:
    repo = _make_repo_with_campaign(tmp_path)
    gs = repo.load()
    assert gs.campaign is not None


def test_load_populates_module_when_campaign_present(tmp_path: Path) -> None:
    repo = _make_repo_with_campaign(tmp_path)
    gs = repo.load()
    assert gs.module is not None
    assert gs.module.module_id == "module-001"


def test_load_campaign_is_none_when_no_state_file(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    gs = repo.load()
    assert gs.campaign is None


def test_load_module_is_none_when_no_campaign(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    gs = repo.load()
    assert gs.module is None


def test_load_module_is_none_when_current_module_id_is_none(tmp_path: Path) -> None:
    seed = _make_repo(tmp_path)
    seed.load()
    campaign = _make_campaign_state(current_module_id=None)
    registry = ActorRegistry(actors={TALIA.actor_id: TALIA})
    seed.persist(GameState(campaign=campaign, module=None, actor_registry=registry))
    gs = _make_repo(tmp_path).load()
    assert gs.module is None


def test_load_campaign_value_matches_file(tmp_path: Path) -> None:
    repo = _make_repo_with_campaign(tmp_path)
    gs = repo.load()
    assert gs.campaign is not None
    assert gs.campaign.campaign_id == "camp-1"
    assert gs.campaign.name == "Test Campaign"


def test_load_module_value_matches_file(tmp_path: Path) -> None:
    repo = _make_repo_with_campaign(tmp_path)
    gs = repo.load()
    assert gs.module is not None
    assert gs.module.module_id == "module-001"
    assert gs.module.title == "Test Module"


def test_load_returns_player_in_registry_when_state_file_corrupt(
    tmp_path: Path,
) -> None:
    path = _state_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not valid json", encoding="utf-8")
    gs = _make_repo(tmp_path).load()
    assert TALIA.actor_id in gs.actor_registry.actors


# --- persist() ---


def test_persist_writes_to_disk(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    repo.load()
    new_state = GameState(actor_registry=ActorRegistry(actors={TALIA.actor_id: TALIA}))
    repo.persist(new_state)
    assert _state_path(tmp_path).exists()


def test_persist_saves_player_via_player_repo(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    repo.load()
    gs = GameState(actor_registry=ActorRegistry(actors={TALIA.actor_id: TALIA}))
    repo.persist(gs)
    repo._player_repo.save.assert_called_once_with(TALIA)


def test_persist_saves_npc_only_to_state_file(tmp_path: Path) -> None:
    npc = replace(TALIA, actor_id="npc:goblin", name="Goblin")
    repo = _make_repo(tmp_path)
    repo.load()
    registry = ActorRegistry(actors={TALIA.actor_id: TALIA, npc.actor_id: npc})
    repo.persist(GameState(actor_registry=registry))
    data = json.loads(_state_path(tmp_path).read_text())
    actor_ids = list(data.get("actor_registry", {}).get("actors", {}).keys())
    assert npc.actor_id in actor_ids
    assert TALIA.actor_id not in actor_ids


def test_persist_raises_if_player_missing_from_registry(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    repo.load()
    with pytest.raises(RuntimeError, match="missing from registry"):
        repo.persist(GameState(actor_registry=ActorRegistry(actors={})))


def test_persist_writes_campaign_to_state_file(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    repo.load()
    campaign = _make_campaign_state()
    registry = ActorRegistry(actors={TALIA.actor_id: TALIA})
    repo.persist(GameState(campaign=campaign, actor_registry=registry))
    data = json.loads(_state_path(tmp_path).read_text())
    assert data["campaign"] is not None
    assert data["campaign"]["campaign_id"] == "camp-1"


def test_persist_writes_null_campaign_when_none(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    repo.load()
    registry = ActorRegistry(actors={TALIA.actor_id: TALIA})
    repo.persist(GameState(campaign=None, actor_registry=registry))
    data = json.loads(_state_path(tmp_path).read_text())
    assert data["campaign"] is None


def test_persist_writes_module_to_state_file(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    repo.load()
    module = _make_module_state("mod-1")
    registry = ActorRegistry(actors={TALIA.actor_id: TALIA})
    repo.persist(GameState(module=module, actor_registry=registry))
    data = json.loads(_state_path(tmp_path).read_text())
    assert data["module"] is not None
    assert data["module"]["module_id"] == "mod-1"


def test_persist_writes_null_module_when_none(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    repo.load()
    registry = ActorRegistry(actors={TALIA.actor_id: TALIA})
    repo.persist(GameState(module=None, actor_registry=registry))
    data = json.loads(_state_path(tmp_path).read_text())
    assert data["module"] is None


def test_persist_writes_encounter_to_state_file(tmp_path: Path) -> None:
    encounter = MagicMock(spec=EncounterState)
    encounter.to_dict.return_value = {"encounter_id": "test-enc"}
    registry = ActorRegistry(actors={TALIA.actor_id: TALIA})
    repo = _make_repo(tmp_path)
    repo.load()
    repo.persist(GameState(encounter=encounter, actor_registry=registry))
    data = json.loads(_state_path(tmp_path).read_text())
    assert data["encounter"] is not None
    assert data["encounter"]["encounter_id"] == "test-enc"


def test_persist_writes_null_encounter_when_none(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    repo.load()
    registry = ActorRegistry(actors={TALIA.actor_id: TALIA})
    repo.persist(GameState(encounter=None, actor_registry=registry))
    data = json.loads(_state_path(tmp_path).read_text())
    assert data["encounter"] is None


# --- destroy_campaign() ---


def test_destroy_campaign_load_still_works_after_destroy(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    repo.load()
    repo.destroy_campaign("camp-1")
    gs = repo.load()
    assert gs.campaign is None


def test_destroy_campaign_deletes_state_file(tmp_path: Path) -> None:
    repo = _make_repo_with_campaign(tmp_path)
    assert _state_path(tmp_path).exists()
    repo.destroy_campaign("camp-1")
    assert not _state_path(tmp_path).exists()


def test_destroy_campaign_is_idempotent_when_no_file(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    repo.destroy_campaign("camp-1")  # must not raise


# --- persist / load round-trips ---


def test_persist_and_load_round_trip_current_module_id(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    repo.load()
    campaign = _make_campaign_state(current_module_id="mod-rt")
    module = _make_module_state("mod-rt")
    registry = ActorRegistry(actors={TALIA.actor_id: TALIA})
    repo.persist(GameState(campaign=campaign, module=module, actor_registry=registry))
    gs2 = _make_repo(tmp_path).load()
    assert gs2.campaign is not None
    assert gs2.campaign.current_module_id == "mod-rt"
    assert gs2.module is not None
    assert gs2.module.module_id == "mod-rt"


def test_persist_and_load_round_trip_null_current_module_id(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    repo.load()
    campaign = _make_campaign_state(current_module_id=None)
    registry = ActorRegistry(actors={TALIA.actor_id: TALIA})
    repo.persist(GameState(campaign=campaign, actor_registry=registry))
    gs2 = _make_repo(tmp_path).load()
    assert gs2.campaign is not None
    assert gs2.campaign.current_module_id is None
    assert gs2.module is None
