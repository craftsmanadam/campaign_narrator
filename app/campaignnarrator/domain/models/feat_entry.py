"""Feat entry domain model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FeatEntry:
    """Minimal feat entry loaded from the compendium."""

    feat_id: str
    name: str
    summary: str
    reference: str | None
