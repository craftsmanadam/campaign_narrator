"""Unit tests for state update helpers."""

from campaignnarrator.tools.state_updates import apply_potion_of_healing


def test_potion_of_healing_consumes_item_and_caps_hit_points() -> None:
    """Potion healing should remove one potion and respect the max HP cap."""

    player_character = {
        "hp": {"current": 12, "max": 18},
        "inventory": ["potion-of-healing", "rope"],
    }

    updated = apply_potion_of_healing(player_character, healing_amount=8)

    assert updated["hp"] == {"current": 18, "max": 18}
    assert updated["inventory"] == ["rope"]
