"""GameStateRepository: single facade for all structured game state."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from campaignnarrator.domain.models import ActorRegistry, GameState
from campaignnarrator.repositories.player_repository import PlayerRepository

_logger = logging.getLogger(__name__)


class _PlayerMissingFromRegistryError(RuntimeError):
    """Player actor was not found in the registry during persist()."""

    def __init__(self, player_actor_id: str) -> None:
        super().__init__(
            f"Player actor {player_actor_id!r} missing from registry "
            "during persist(). Registry must contain the player at all times."
        )


class GameStateRepository:
    """Single-file facade over all structured game state.

    Serialises campaign, module, encounter, and NPC registry into one JSON
    blob at state_path. Player state is kept separate via PlayerRepository
    because the player persists across campaign lifecycles.

    load()             — deserialises GameState from the blob
    persist(state)     — write blob + player to disk
    destroy_campaign() — delete the blob; player file is untouched
    """

    def __init__(
        self,
        *,
        state_path: Path,
        player_repo: PlayerRepository,
    ) -> None:
        self._state_path = state_path
        self._player_repo = player_repo
        self._player_actor_id: str | None = None

    def load(self) -> GameState:
        """Deserialise GameState from the blob.

        Returns an empty GameState (player only in registry) when no blob
        exists — correct initial state for a new game.
        """
        player = self._player_repo.load()
        self._player_actor_id = player.actor_id

        raw = self._read_blob()

        if raw is None:
            return GameState(actor_registry=ActorRegistry().with_actor(player))

        gs = GameState.from_json(raw)

        if player.actor_id not in gs.actor_registry.actors:
            return gs.with_actor_registry(gs.actor_registry.with_actor(player))
        return gs

    def persist(self, state: GameState) -> None:
        """Write the blob to disk and save the player via PlayerRepository.

        Splits the registry: player → PlayerRepository, NPCs → blob.
        """
        if self._player_actor_id is not None:
            player = state.actor_registry.actors.get(self._player_actor_id)
            if player is None:
                raise _PlayerMissingFromRegistryError(self._player_actor_id)
            self._player_repo.save(player)

        npc_actors = {
            actor_id: actor
            for actor_id, actor in state.actor_registry.actors.items()
            if actor_id != self._player_actor_id
        }
        npc_state = state.with_actor_registry(ActorRegistry(actors=npc_actors))

        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(
            json.dumps(npc_state.to_json(), indent=2, sort_keys=True) + "\n"
        )

    def destroy_campaign(self, campaign_id: str) -> None:
        """Delete the game state blob. Player file is untouched.

        Called only from StartupOrchestrator._destroy_campaign() alongside
        NarrativeMemoryRepository.clear_campaign() — never alone.
        """
        _logger.info("Destroying structured state for campaign_id=%s", campaign_id)
        self._player_actor_id = None
        self._state_path.unlink(missing_ok=True)

    def _read_blob(self) -> dict[str, object] | None:
        """Read and parse the state blob. Returns None if absent or corrupt."""
        if not self._state_path.exists():
            return None
        try:
            data = json.loads(self._state_path.read_text())
        except json.JSONDecodeError, OSError:
            _logger.warning("game_state.json is corrupt — starting with empty state")
            return None
        if not isinstance(data, dict):
            _logger.warning(
                "game_state.json has unexpected format — starting with empty state"
            )
            return None
        return data
