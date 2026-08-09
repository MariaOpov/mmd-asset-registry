"""PMX numeric representation helpers for safe editing."""

from __future__ import annotations

import math
import struct


def canonicalize_pmx_float32(value: float) -> float:
    """Return the exact finite IEEE-754 float32 value PMX will store."""

    if not isinstance(value, float):
        raise TypeError("value must be a float.")
    if not math.isfinite(value):
        raise ValueError("value must be finite.")

    try:
        encoded = struct.pack("<f", value)
    except (OverflowError, struct.error) as error:
        raise ValueError(
            "value is outside the finite IEEE-754 float32 range."
        ) from error

    canonical = struct.unpack("<f", encoded)[0]
    if not math.isfinite(canonical):
        raise ValueError(
            "value is outside the finite IEEE-754 float32 range."
        )
    return canonical
