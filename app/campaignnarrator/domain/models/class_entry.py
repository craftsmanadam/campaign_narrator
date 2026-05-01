"""Class entry domain model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ClassEntry:
    """Minimal class entry loaded from the compendium."""

    class_id: str
    name: str
    reference: str | None
