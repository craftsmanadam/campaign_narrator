"""Thin wrapper around the real multi_dice dependency."""

from __future__ import annotations

import os
import random

import multi_dice


def roll(expression: str) -> int:
    """Roll dice using the external multi_dice implementation."""

    seed = os.getenv("CAMPAIGNNARRATOR_DICE_SEED")
    if seed is not None:
        random.seed(seed)
    return multi_dice.roll(expression)
