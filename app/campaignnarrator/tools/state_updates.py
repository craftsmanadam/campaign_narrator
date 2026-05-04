"""Shared type-coercion helpers for campaign tool functions."""

from __future__ import annotations


def require_int(value: object, label: str) -> int:
    """Raise TypeError if *value* is not an int; otherwise return it."""
    if not isinstance(value, int):
        msg = f"invalid {label}: {value}"
        raise TypeError(msg)
    return value
