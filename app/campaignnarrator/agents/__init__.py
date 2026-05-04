"""Agents for Campaign Narrator."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

__all__ = ["NarratorAgent", "RulesAgent"]

if TYPE_CHECKING:
    from campaignnarrator.agents.narrator_agent import NarratorAgent
    from campaignnarrator.agents.rules_agent import RulesAgent


def __getattr__(name: str) -> Any:
    """Lazy-import heavy agent modules to avoid circular imports at startup."""
    if name == "NarratorAgent":
        return import_module("campaignnarrator.agents.narrator_agent").NarratorAgent
    if name == "RulesAgent":
        return import_module("campaignnarrator.agents.rules_agent").RulesAgent
    raise AttributeError(name)
