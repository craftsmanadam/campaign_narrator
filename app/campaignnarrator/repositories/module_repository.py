"""Module (story arc) persistence repository."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from campaignnarrator.domain.models import ModuleState


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
        "encounters": list(m.encounters),
        "current_encounter_index": m.current_encounter_index,
        "completed": m.completed,
    }


def _module_from_seed(seed: object) -> ModuleState:
    if not isinstance(seed, Mapping):
        raise TypeError("invalid module seed")  # noqa: TRY003
    return ModuleState(
        module_id=str(seed["module_id"]),
        campaign_id=str(seed["campaign_id"]),
        title=str(seed["title"]),
        summary=str(seed["summary"]),
        guiding_milestone_id=str(seed["guiding_milestone_id"]),
        encounters=tuple(str(e) for e in seed.get("encounters", [])),
        current_encounter_index=int(seed["current_encounter_index"]),
        completed=bool(seed.get("completed", False)),
    )
