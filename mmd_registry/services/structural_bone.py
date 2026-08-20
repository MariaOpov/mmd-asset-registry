"""Public bounded semantic DTOs for CP11 bone insertion preview requests."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal


_INT32_MIN = -(1 << 31)
_INT32_MAX = (1 << 31) - 1


def _is_plain_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _require_plain_int(value: object, field_name: str) -> int:
    if not _is_plain_int(value):
        raise TypeError(f"{field_name} must be an integer.")
    return value


def _require_int32(value: object, field_name: str) -> int:
    integer = _require_plain_int(value, field_name)
    if not _INT32_MIN <= integer <= _INT32_MAX:
        raise ValueError(f"{field_name} must fit in a signed 32-bit integer.")
    return integer


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
class PmxStructuralBoneIkLink:
    """One bounded source-domain IK link for an inserted bone."""

    bone_index: int
    lower_limit: tuple[float, float, float] | None = None
    upper_limit: tuple[float, float, float] | None = None

    def __post_init__(self) -> None:
        bone_index = _require_plain_int(self.bone_index, "bone_index")
        if bone_index < 0:
            raise ValueError("bone_index cannot be negative.")

        limits_present = (
            self.lower_limit is not None,
            self.upper_limit is not None,
        )
        if limits_present[0] != limits_present[1]:
            raise ValueError(
                "IK link lower_limit and upper_limit must either both be present "
                "or both be None."
            )
        if self.lower_limit is not None:
            _require_float_tuple(
                self.lower_limit,
                field_name="lower_limit",
                length=3,
            )
            assert self.upper_limit is not None
            _require_float_tuple(
                self.upper_limit,
                field_name="upper_limit",
                length=3,
            )


@dataclass(frozen=True, slots=True)
class PmxStructuralBoneIk:
    """One bounded source-domain IK definition for an inserted bone."""

    target_bone_index: int
    loop_count: int = 1
    angle_limit: float = 0.0
    links: tuple[PmxStructuralBoneIkLink, ...] = ()

    def __post_init__(self) -> None:
        target = _require_plain_int(self.target_bone_index, "target_bone_index")
        if target < 0:
            raise ValueError("target_bone_index cannot be negative.")

        loop_count = _require_plain_int(self.loop_count, "loop_count")
        if loop_count < 0:
            raise ValueError("loop_count cannot be negative.")
        if loop_count > _INT32_MAX:
            raise ValueError("loop_count must fit in a nonnegative signed 32-bit integer.")

        _require_finite_float(self.angle_limit, "angle_limit")

        if type(self.links) is not tuple:
            raise TypeError("links must be a tuple.")
        if not all(isinstance(link, PmxStructuralBoneIkLink) for link in self.links):
            raise TypeError(
                "links must contain only PmxStructuralBoneIkLink values."
            )


@dataclass(frozen=True, slots=True)
class PmxStructuralBoneInsertion:
    """One semantic PMX bone insertion request with source-domain references."""

    local_name: str
    universal_name: str = ""

    bone_position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    parent_bone_index: int = -1
    transform_layer: int = 0

    rotatable: bool = False
    translatable: bool = False
    visible: bool = False
    enabled: bool = False
    local_append: bool = False
    after_physics: bool = False

    tail_offset: tuple[float, float, float] | None = (0.0, 0.0, 0.0)
    tail_bone_index: int | None = None

    inherit_rotation: bool = False
    inherit_translation: bool = False
    inherit_parent_bone_index: int | None = None
    inherit_weight: float | None = None

    fixed_axis: tuple[float, float, float] | None = None
    local_axis_x: tuple[float, float, float] | None = None
    local_axis_z: tuple[float, float, float] | None = None

    external_parent_key: int | None = None
    ik: PmxStructuralBoneIk | None = None

    position: Literal["append", "insert_before"] = "append"
    source_index: int | None = None

    def __post_init__(self) -> None:
        for field_name in ("local_name", "universal_name"):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"{field_name} must be a string.")

        _require_float_tuple(
            self.bone_position,
            field_name="bone_position",
            length=3,
        )

        parent = _require_plain_int(self.parent_bone_index, "parent_bone_index")
        if parent < -1:
            raise ValueError("parent_bone_index cannot be smaller than -1.")
        _require_int32(self.transform_layer, "transform_layer")

        for field_name in (
            "rotatable",
            "translatable",
            "visible",
            "enabled",
            "local_append",
            "after_physics",
            "inherit_rotation",
            "inherit_translation",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be a boolean.")

        if (self.tail_offset is None) == (self.tail_bone_index is None):
            raise ValueError(
                "exactly one of tail_offset or tail_bone_index must be present."
            )
        if self.tail_offset is not None:
            _require_float_tuple(
                self.tail_offset,
                field_name="tail_offset",
                length=3,
            )
        else:
            assert self.tail_bone_index is not None
            tail_index = _require_plain_int(
                self.tail_bone_index,
                "tail_bone_index",
            )
            if tail_index < -1:
                raise ValueError("tail_bone_index cannot be smaller than -1.")

        has_inherit = self.inherit_rotation or self.inherit_translation
        if has_inherit:
            if self.inherit_parent_bone_index is None or self.inherit_weight is None:
                raise ValueError(
                    "inherit flags require inherit_parent_bone_index and inherit_weight."
                )
            inherit_parent = _require_plain_int(
                self.inherit_parent_bone_index,
                "inherit_parent_bone_index",
            )
            if inherit_parent < -1:
                raise ValueError(
                    "inherit_parent_bone_index cannot be smaller than -1."
                )
            _require_finite_float(self.inherit_weight, "inherit_weight")
        elif (
            self.inherit_parent_bone_index is not None
            or self.inherit_weight is not None
        ):
            raise ValueError(
                "inherit_parent_bone_index and inherit_weight require an inherit flag."
            )

        if self.fixed_axis is not None:
            _require_float_tuple(
                self.fixed_axis,
                field_name="fixed_axis",
                length=3,
            )

        local_axes_present = (
            self.local_axis_x is not None,
            self.local_axis_z is not None,
        )
        if local_axes_present[0] != local_axes_present[1]:
            raise ValueError(
                "local_axis_x and local_axis_z must either both be present or both be None."
            )
        if self.local_axis_x is not None:
            _require_float_tuple(
                self.local_axis_x,
                field_name="local_axis_x",
                length=3,
            )
            assert self.local_axis_z is not None
            _require_float_tuple(
                self.local_axis_z,
                field_name="local_axis_z",
                length=3,
            )

        if self.external_parent_key is not None:
            _require_int32(self.external_parent_key, "external_parent_key")

        if self.ik is not None and not isinstance(self.ik, PmxStructuralBoneIk):
            raise TypeError("ik must be a PmxStructuralBoneIk value or None.")

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


__all__ = (
    "PmxStructuralBoneIkLink",
    "PmxStructuralBoneIk",
    "PmxStructuralBoneInsertion",
)
