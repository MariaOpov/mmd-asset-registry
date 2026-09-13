"""Private RGB intent normalization for Smart material color drafts."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final, TypeAlias

from mmd_registry.pmx.editing.numeric import canonicalize_pmx_float32


SmartMaterialColorInput: TypeAlias = str | tuple[float, float, float]

_COLOR_PRESETS: Final[tuple[tuple[str, tuple[float, float, float]], ...]] = (
    ("blue", (0.0, 0.0, 1.0)),
    ("red", (1.0, 0.0, 0.0)),
    ("green", (0.0, 1.0, 0.0)),
    ("purple", (0.5, 0.0, 0.5)),
)


@dataclass(frozen=True, slots=True)
class SmartMaterialColorIntent:
    """One normalized finite RGB-only Smart material color intent."""

    rgb: tuple[float, float, float]

    def __post_init__(self) -> None:
        if type(self.rgb) is not tuple or len(self.rgb) != 3:
            raise TypeError("rgb must be a three-float tuple.")
        for component in self.rgb:
            if type(component) is not float:
                raise TypeError("rgb must contain only floats.")
            if not math.isfinite(component):
                raise ValueError("rgb components must be finite.")
            if not 0.0 <= component <= 1.0:
                raise ValueError("rgb components must be within [0.0, 1.0].")


def _preset_rgb(name: str) -> tuple[float, float, float] | None:
    for preset_name, rgb in _COLOR_PRESETS:
        if name == preset_name:
            return rgb
    return None


def normalize_smart_material_color(
    value: SmartMaterialColorInput,
) -> SmartMaterialColorIntent:
    """Validate and canonicalize one exact preset or custom normalized RGB."""

    rgb: tuple[float, float, float]
    if type(value) is str:
        preset = _preset_rgb(value)
        if preset is None:
            raise ValueError("unknown Smart material color preset.")
        rgb = preset
    elif type(value) is tuple:
        if len(value) != 3:
            raise ValueError("custom RGB must contain exactly three components.")
        if any(type(component) is not float for component in value):
            raise TypeError("custom RGB components must be floats.")
        rgb = value
    else:
        raise TypeError(
            "color must be a lowercase preset name or a three-float tuple."
        )

    canonical: list[float] = []
    for component in rgb:
        if not math.isfinite(component):
            raise ValueError("RGB components must be finite.")
        if not 0.0 <= component <= 1.0:
            raise ValueError("RGB components must be within [0.0, 1.0].")
        canonical.append(canonicalize_pmx_float32(component))

    return SmartMaterialColorIntent(rgb=tuple(canonical))
