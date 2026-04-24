"""Actor persistence repository."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from campaignnarrator.domain.models import ActorState


class ActorRepository:
    """Persist and load the player ActorState to/from a JSON file."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)
        self._player_path = self._root / "actors" / "player.json"

    def load_player(self) -> ActorState:
        """Load the player actor from disk. Raises FileNotFoundError if not found."""
        if not self._player_path.exists():
            raise FileNotFoundError(  # noqa: TRY003
                f"player actor file not found: {self._player_path}"
            )
        return ActorState.from_dict(json.loads(self._player_path.read_text()))

    def save(self, actor: ActorState) -> None:
        """Persist actor to disk. Strips transient fields before writing."""
        self._player_path.parent.mkdir(parents=True, exist_ok=True)
        self._player_path.write_text(
            json.dumps(actor.to_dict(), indent=2, sort_keys=True) + "\n"
        )


def actor_state_from_seed(
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
