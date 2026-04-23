"""Module (story arc) persistence repository."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from campaignnarrator.domain.models import EncounterTemplate, ModuleState


class ModuleRepository:
    """Persist and load ModuleState to/from per-module JSON files."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)
        self._modules_dir = self._root / "state" / "modules"

    def load(self, module_id: str) -> ModuleState | None:
        """Load a module by ID. Returns None if absent."""
        path = self._modules_dir / f"{module_id}.json"
        if not path.exists():
            return None
        return _module_from_seed(json.loads(path.read_text()))

    def save(self, module: ModuleState) -> None:
        """Persist a module to disk."""
        self._modules_dir.mkdir(parents=True, exist_ok=True)
        path = self._modules_dir / f"{module.module_id}.json"
        path.write_text(
            json.dumps(_module_to_json(module), indent=2, sort_keys=True) + "\n"
        )


def _module_to_json(m: ModuleState) -> dict[str, object]:
    return {
        "module_id": m.module_id,
        "campaign_id": m.campaign_id,
        "title": m.title,
        "summary": m.summary,
        "guiding_milestone_id": m.guiding_milestone_id,
        "completed_encounter_ids": list(m.completed_encounter_ids),
        "completed_encounter_summaries": list(m.completed_encounter_summaries),
        "next_encounter_seed": m.next_encounter_seed,  # deprecated — removed in Plan 4
        "completed": m.completed,
        "planned_encounters": [t.model_dump() for t in m.planned_encounters],
        "next_encounter_index": m.next_encounter_index,
    }


def _module_from_seed(seed: object) -> ModuleState:
    if not isinstance(seed, Mapping):
        raise TypeError("invalid module seed")  # noqa: TRY003
    raw = dict(seed)
    raw.pop("next_encounter_seed", None)  # deprecated — not forwarded to ModuleState
    planned_raw = raw.pop("planned_encounters", [])
    return ModuleState(
        module_id=str(raw["module_id"]),
        campaign_id=str(raw["campaign_id"]),
        title=str(raw["title"]),
        summary=str(raw["summary"]),
        guiding_milestone_id=str(raw["guiding_milestone_id"]),
        completed_encounter_ids=tuple(
            str(e) for e in raw.get("completed_encounter_ids", [])
        ),
        completed_encounter_summaries=tuple(
            str(s) for s in raw.get("completed_encounter_summaries", [])
        ),
        completed=bool(raw.get("completed", False)),
        planned_encounters=tuple(
            EncounterTemplate.model_validate(t) for t in planned_raw
        ),
        next_encounter_index=int(raw.get("next_encounter_index", 0)),
    )
