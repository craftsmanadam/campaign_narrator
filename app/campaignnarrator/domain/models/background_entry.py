"""Background entry domain model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BackgroundEntry:
    """Minimal background entry loaded from the compendium."""

    background_id: str
    name: str
    reference: str | None
