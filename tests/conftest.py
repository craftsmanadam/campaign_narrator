"""Shared test fixtures for all test suites."""

from __future__ import annotations

import pytest


class ScriptedIO:
    """PlayerIO implementation driven by a pre-defined sequence of player inputs.

    Returns 'exit' when the input list is exhausted so the social encounter
    loop terminates cleanly. Use this fixture instead of a real stream to
    prevent tests from hanging on stdin.
    """

    def __init__(self, inputs: list[str], *, on_exhaust: str = "exit") -> None:
        self._inputs = list(inputs)
        self._on_exhaust = on_exhaust
        self._displayed: list[str] = []

    def prompt(self, text: str) -> str:
        self._displayed.append(text)
        if not self._inputs:
            return self._on_exhaust
        return self._inputs.pop(0)

    def prompt_optional(self, text: str) -> str:
        """Return next input or empty string; blank is a valid response."""
        self._displayed.append(text)
        if not self._inputs:
            return ""
        return self._inputs.pop(0)

    def prompt_multiline(self, text: str) -> str:
        """Return next input as a single value; multiline content is pre-joined."""
        self._displayed.append(text)
        if not self._inputs:
            return self._on_exhaust
        return self._inputs.pop(0)

    def display(self, text: str) -> None:
        self._displayed.append(text)

    @property
    def displayed(self) -> list[str]:
        return list(self._displayed)


@pytest.fixture
def scripted_io() -> type[ScriptedIO]:
    """Expose ScriptedIO class as a fixture for parametric construction."""
    return ScriptedIO
