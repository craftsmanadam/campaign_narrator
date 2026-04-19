"""Campaign persistence repository."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from campaignnarrator.domain.models import CampaignEvent, CampaignState, Milestone


class CampaignRepository:
    """Persist and load CampaignState; append and read CampaignEvents."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)
        self._campaign_path = self._root / "state" / "campaign.json"
        self._events_dir = self._root / "memory"

    def exists(self) -> bool:
        """Return True if a campaign file is present on disk."""
        return self._campaign_path.exists()

    def load(self) -> CampaignState | None:
        """Load the campaign from disk. Returns None if absent."""
        if not self._campaign_path.exists():
            return None
        return _campaign_from_seed(json.loads(self._campaign_path.read_text()))

    def save(self, campaign: CampaignState) -> None:
        """Persist the campaign to disk."""
        self._campaign_path.parent.mkdir(parents=True, exist_ok=True)
        self._campaign_path.write_text(
            json.dumps(_campaign_to_json(campaign), indent=2, sort_keys=True) + "\n"
        )

    def append_event(self, event: CampaignEvent) -> None:
        """Append a campaign event to the campaign-scoped JSONL log."""
        log_path = self._events_dir / f"campaign_{event.campaign_id}_events.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(_event_to_json(event), separators=(",", ":")) + "\n")

    def load_events(self, campaign_id: str) -> list[CampaignEvent]:
        """Return all events for this campaign in append order."""
        log_path = self._events_dir / f"campaign_{campaign_id}_events.jsonl"
        if not log_path.exists():
            return []
        return [
            _event_from_seed(json.loads(line))
            for line in log_path.read_text().splitlines()
            if line.strip()
        ]


# --- Serialisation helpers ---


def _campaign_to_json(c: CampaignState) -> dict[str, object]:
    return {
        "campaign_id": c.campaign_id,
        "name": c.name,
        "setting": c.setting,
        "narrator_personality": c.narrator_personality,
        "hidden_goal": c.hidden_goal,
        "bbeg_name": c.bbeg_name,
        "bbeg_description": c.bbeg_description,
        "milestones": [_milestone_to_json(m) for m in c.milestones],
        "current_milestone_index": c.current_milestone_index,
        "starting_level": c.starting_level,
        "target_level": c.target_level,
        "player_brief": c.player_brief,
        "player_actor_id": c.player_actor_id,
        "bbeg_actor_id": c.bbeg_actor_id,
        "current_module_id": c.current_module_id,
    }


def _milestone_to_json(m: Milestone) -> dict[str, object]:
    return {
        "milestone_id": m.milestone_id,
        "title": m.title,
        "description": m.description,
        "completed": m.completed,
    }


def _event_to_json(e: CampaignEvent) -> dict[str, object]:
    return {
        "campaign_id": e.campaign_id,
        "event_type": e.event_type,
        "summary": e.summary,
        "timestamp": e.timestamp,
        "module_id": e.module_id,
        "encounter_id": e.encounter_id,
    }


def _campaign_from_seed(seed: object) -> CampaignState:
    if not isinstance(seed, Mapping):
        raise TypeError("invalid campaign seed")  # noqa: TRY003
    return CampaignState(
        campaign_id=str(seed["campaign_id"]),
        name=str(seed["name"]),
        setting=str(seed["setting"]),
        narrator_personality=str(seed["narrator_personality"]),
        hidden_goal=str(seed["hidden_goal"]),
        bbeg_name=str(seed["bbeg_name"]),
        bbeg_description=str(seed["bbeg_description"]),
        milestones=tuple(_milestone_from_seed(m) for m in seed.get("milestones", [])),
        current_milestone_index=int(seed["current_milestone_index"]),
        starting_level=int(seed["starting_level"]),
        target_level=int(seed["target_level"]),
        player_brief=str(seed["player_brief"]),
        player_actor_id=str(seed["player_actor_id"]),
        bbeg_actor_id=(
            str(seed["bbeg_actor_id"])
            if seed.get("bbeg_actor_id") is not None
            else None
        ),
        current_module_id=(
            str(seed["current_module_id"])
            if seed.get("current_module_id") is not None
            else None
        ),
    )


def _milestone_from_seed(seed: object) -> Milestone:
    if not isinstance(seed, Mapping):
        raise TypeError("invalid milestone seed")  # noqa: TRY003
    return Milestone(
        milestone_id=str(seed["milestone_id"]),
        title=str(seed["title"]),
        description=str(seed["description"]),
        completed=bool(seed.get("completed", False)),
    )


def _event_from_seed(seed: Mapping[str, object]) -> CampaignEvent:
    return CampaignEvent(
        campaign_id=str(seed["campaign_id"]),
        event_type=str(seed["event_type"]),
        summary=str(seed["summary"]),
        timestamp=str(seed["timestamp"]),
        module_id=str(seed["module_id"]) if seed.get("module_id") is not None else None,
        encounter_id=(
            str(seed["encounter_id"]) if seed.get("encounter_id") is not None else None
        ),
    )
