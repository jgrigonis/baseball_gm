# src/util/clamp.py
"""
Clamp a value between a minimum and maximum.
"""


def clamp(val: float, lo: float = 0.0, hi: float = 1.0, precision: int = 0) -> float:
    """
    Clamp a value between a minimum and maximum.
    """
    if precision == 0:
        return max(lo, min(hi, val))
    else:
        return max(lo, min(hi, round(val, precision)))
