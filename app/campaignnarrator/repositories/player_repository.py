"""Player persistence repository."""

from __future__ import annotations

import contextlib
import json
from collections.abc import Mapping
from pathlib import Path

from campaignnarrator.domain.models import ActorState
from campaignnarrator.repositories.compendium_repository import CompendiumRepository


class PlayerRepository:
    """Persist and load the player ActorState, with compendium reference enrichment."""

    def __init__(self, data_root: Path | str) -> None:
        """Resolve player file path and instantiate a CompendiumRepository."""
        root = Path(data_root)
        self._player_path = root / "state" / "actors" / "player.json"
        self._compendium = CompendiumRepository(root / "compendium")

    def load(self) -> ActorState:
        """Load and enrich the player actor from disk.

        Raises FileNotFoundError if the player file does not exist.
        Compendium reference texts are populated on every load.
        """
        if not self._player_path.exists():
            raise FileNotFoundError(  # noqa: TRY003
                f"player actor file not found: {self._player_path}"
            )
        player = ActorState.from_dict(json.loads(self._player_path.read_text()))
        return _enrich_player_references(player, self._compendium)

    def save(self, player: ActorState) -> None:
        """Strip transient references and persist player to disk."""
        self._player_path.parent.mkdir(parents=True, exist_ok=True)
        stripped = _strip_player_references(player)
        self._player_path.write_text(
            json.dumps(stripped.to_dict(), indent=2, sort_keys=True) + "\n"
        )


def _enrich_player_references(
    actor: ActorState,
    compendium: CompendiumRepository,
) -> ActorState:
    """Populate actor.references with compendium text for each feat/resource/item."""
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
    return actor.with_references(tuple(texts))


def _strip_player_references(actor: ActorState) -> ActorState:
    """Clear transient compendium references before persisting to disk."""
    return actor.with_references(())


def player_template_from_seed(
    seed: object,
    *,
    actor_id: str = "unknown",
) -> ActorState:
    """Load an ActorState from a raw dict seed.

    Kept for backward compatibility with character_template_repository.
    """
    if not isinstance(seed, Mapping):
        raise TypeError(f"invalid actor seed: {actor_id}.actor_id")  # noqa: TRY003
    return ActorState.from_dict(seed)
