"""Unit tests for the state repository."""

from pathlib import Path

from campaignnarrator.repositories.state_repository import StateRepository


def test_state_repository_loads_and_saves_player_character(tmp_path: Path) -> None:
    """The repository should read and write the player character JSON file."""

    state_root = tmp_path / "state"
    state_root.mkdir(parents=True)
    (state_root / "player_character.json").write_text(
        '{"character_id": "pc-001", "hp": {"current": 18, "max": 18}, '
        '"inventory": ["rope"]}'
    )

    repository = StateRepository(state_root)

    player_character = repository.load_player_character()
    assert player_character["character_id"] == "pc-001"
    assert player_character["inventory"] == ["rope"]

    repository.save_player_character(
        {
            "character_id": "pc-001",
            "hp": {"current": 20, "max": 20},
            "inventory": ["rope", "torch"],
        }
    )

    assert repository.load_player_character()["hp"] == {"current": 20, "max": 20}
