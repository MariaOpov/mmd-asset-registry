"""Public bounded DTO for CP09 material insertion preview requests."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from mmd_registry.services.structural_reference import (
    PmxStructuralNewReference,
    _require_optional_new_id,
)


def _is_plain_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)



def _require_texture_reference(value: object, field_name: str) -> None:
    if isinstance(value, PmxStructuralNewReference):
        if value.target_kind != "texture":
            raise ValueError(f"{field_name} new reference must target texture.")
        return
    if not _is_plain_int(value):
        raise TypeError(
            f"{field_name} must be an integer or PmxStructuralNewReference."
        )
    if value < -1:
        raise ValueError(f"{field_name} cannot be smaller than -1.")

def _require_finite_float(value: object, field_name: str) -> None:
    if not isinstance(value, float):
        raise TypeError(f"{field_name} must be a float.")
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite.")


def _require_float_tuple(
    value: object,
    *,
    field_name: str,
    length: int,
) -> None:
    if type(value) is not tuple:
        raise TypeError(f"{field_name} must be a tuple.")
    if len(value) != length:
        raise ValueError(f"{field_name} must contain exactly {length} values.")
    for item in value:
        _require_finite_float(item, f"{field_name} value")


@dataclass(frozen=True, slots=True)
class PmxStructuralMaterialInsertion:
    """One bounded zero-surface PMX material insertion request."""

    local_name: str
    universal_name: str = ""
    memo: str = ""
    texture_index: int | PmxStructuralNewReference = -1
    sphere_texture_index: int | PmxStructuralNewReference = -1
    sphere_mode: int = 0
    toon_reference_mode: Literal["texture", "shared"] = "texture"
    toon_reference_index: int | PmxStructuralNewReference = -1
    diffuse: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)
    specular: tuple[float, float, float] = (0.0, 0.0, 0.0)
    specular_strength: float = 0.0
    ambient: tuple[float, float, float] = (0.5, 0.5, 0.5)
    drawing_flags: int = 0
    edge_color: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    edge_scale: float = 1.0
    position: Literal["append", "insert_before"] = "append"
    source_index: int | None = None
    new_id: str | None = None

    def __post_init__(self) -> None:
        _require_optional_new_id(self.new_id)
        for field_name in ("local_name", "universal_name", "memo"):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"{field_name} must be a string.")

        for field_name in ("texture_index", "sphere_texture_index"):
            _require_texture_reference(getattr(self, field_name), field_name)

        if not _is_plain_int(self.sphere_mode):
            raise TypeError("sphere_mode must be an integer.")
        if self.sphere_mode not in (0, 1, 2, 3):
            raise ValueError("sphere_mode must be a value from 0 through 3.")

        if self.toon_reference_mode not in ("texture", "shared"):
            raise ValueError(
                "toon_reference_mode must be either 'texture' or 'shared'."
            )
        if self.toon_reference_mode == "shared":
            if not _is_plain_int(self.toon_reference_index):
                raise TypeError(
                    "shared toon_reference_index must be an integer."
                )
            if not 0 <= self.toon_reference_index <= 9:
                raise ValueError(
                    "shared toon_reference_index must be a value from 0 through 9."
                )
        else:
            _require_texture_reference(
                self.toon_reference_index,
                "toon_reference_index",
            )

        _require_float_tuple(self.diffuse, field_name="diffuse", length=4)
        _require_float_tuple(self.specular, field_name="specular", length=3)
        _require_finite_float(self.specular_strength, "specular_strength")
        _require_float_tuple(self.ambient, field_name="ambient", length=3)
        _require_float_tuple(self.edge_color, field_name="edge_color", length=4)
        _require_finite_float(self.edge_scale, "edge_scale")

        if not _is_plain_int(self.drawing_flags):
            raise TypeError("drawing_flags must be an integer.")
        if not 0 <= self.drawing_flags <= 0xFF:
            raise ValueError("drawing_flags must fit in one unsigned byte.")

        if not isinstance(self.position, str):
            raise TypeError("position must be a string.")
        if self.position not in ("append", "insert_before"):
            raise ValueError("position must be either 'append' or 'insert_before'.")

        if self.position == "append":
            if self.source_index is not None:
                raise ValueError("append insertion cannot define source_index.")
            return

        if type(self.source_index) is not int:
            raise TypeError("insert_before source_index must be an integer.")
        if self.source_index < 0:
            raise ValueError("insert_before source_index cannot be negative.")


__all__ = ("PmxStructuralMaterialInsertion",)
