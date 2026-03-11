# src/player/fatigue_level.py
from enum import Enum


class FatigueLevel(Enum):
    FRESH = "fresh"
    GOOD = "good"
    TIRED = "tired"
    EXHAUSTED = "exhausted"
    ZERO = "ZERO"

