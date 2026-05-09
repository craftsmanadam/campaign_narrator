"""Unit tests for campaignnarrator.tools.npc_generator."""

from pathlib import Path

from campaignnarrator.domain.models import ActorType, EncounterNpc
from campaignnarrator.tools.npc_generator import build_npc_actor


class TestBuildNpcActor:
    def test_simple_npc_gets_placeholder_stats(self) -> None:
        npc = EncounterNpc(
            template_npc_id="mira",
            display_name="Mira",
            role="innkeeper",
            description="A tired woman.",
            monster_name=None,
            stat_source="simple_npc",
            cr=0.0,
        )
        actor = build_npc_actor(npc, actor_id="npc:mira", index_path=None)
        assert actor.actor_id == "npc:mira"
        assert actor.name == "Mira"
        expected_hp = 1
        expected_ac = 10
        assert actor.hp_max == expected_hp
        assert actor.armor_class == expected_ac

    def test_monster_compendium_falls_back_to_simple_on_key_error(
        self, tmp_path: Path
    ) -> None:
        npc = EncounterNpc(
            template_npc_id="goblin-a",
            display_name="Goblin Scout",
            role="scout",
            description="Small green creature.",
            monster_name="NonExistentMonster",
            stat_source="monster_compendium",
            cr=0.25,
        )
        # index_path exists but monster not found → fallback
        fake_index = tmp_path / "monster_index.json"
        fake_index.write_text("{}")
        actor = build_npc_actor(npc, actor_id="npc:goblin-a", index_path=fake_index)
        assert actor.actor_id == "npc:goblin-a"
        expected_hp = 1
        assert actor.hp_max == expected_hp  # fallback stats

    def test_monster_compendium_falls_back_when_no_index(self) -> None:
        """Without an index path, the function falls back to simple NPC stats."""
        npc = EncounterNpc(
            template_npc_id="goblin-b",
            display_name="Goblin",
            role="fighter",
            description="A goblin.",
            monster_name="Goblin",
            stat_source="monster_compendium",
            cr=0.25,
        )
        actor = build_npc_actor(npc, actor_id="npc:goblin-b", index_path=None)
        assert actor.actor_id == "npc:goblin-b"
        expected_hp = 1
        assert actor.hp_max == expected_hp

    def test_is_ally_false_produces_npc_actor_type(self) -> None:
        npc = EncounterNpc(
            template_npc_id="guard-a",
            display_name="Guard",
            role="enemy",
            description="A hostile guard.",
            monster_name=None,
            stat_source="simple_npc",
            cr=0.0,
            is_ally=False,
        )
        actor = build_npc_actor(npc, actor_id="npc:guard-a", index_path=None)
        assert actor.actor_type == ActorType.NPC

    def test_is_ally_true_produces_ally_actor_type(self) -> None:
        npc = EncounterNpc(
            template_npc_id="jessa",
            display_name="Jessa",
            role="survivor",
            description="A friendly survivor.",
            monster_name=None,
            stat_source="simple_npc",
            cr=0.0,
            is_ally=True,
        )
        actor = build_npc_actor(npc, actor_id="npc:jessa", index_path=None)
        assert actor.actor_type == ActorType.ALLY
