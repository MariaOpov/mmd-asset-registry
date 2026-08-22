"""Public bounded semantic DTOs for CP14 rigid-body insertion requests."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, TypeAlias

from mmd_registry.services.structural_reference import (
    PmxStructuralNewReference,
    _require_optional_new_id,
)


PmxStructuralRigidBodyShape: TypeAlias = Literal["sphere", "box", "capsule"]
PmxStructuralRigidBodyPhysicsMode: TypeAlias = Literal[
    "bone_follow",
    "physics",
    "physics_with_bone_alignment",
]


def _require_plain_int(value: object, field_name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be an integer.")
    return value


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
    nonnegative: bool = False,
) -> None:
    if type(value) is not tuple:
        raise TypeError(f"{field_name} must be a tuple.")
    if len(value) != length:
        raise ValueError(f"{field_name} must contain exactly {length} values.")
    for item in value:
        _require_finite_float(item, f"{field_name} value")
        if nonnegative and item < 0.0:
            raise ValueError(f"{field_name} values cannot be negative.")


@dataclass(frozen=True, slots=True)
class PmxStructuralRigidBodyInsertion:
    """One semantic rigid-body insertion with source-domain bone reference."""

    local_name: str
    universal_name: str = ""
    bone_index: int | PmxStructuralNewReference = -1
    collision_group: int = 0
    collision_mask: int = 0xFFFF
    shape: PmxStructuralRigidBodyShape = "sphere"
    size: tuple[float, float, float] = (1.0, 1.0, 1.0)
    body_position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    mass: float = 1.0
    linear_damping: float = 0.5
    angular_damping: float = 0.5
    restitution: float = 0.0
    friction: float = 0.5
    physics_mode: PmxStructuralRigidBodyPhysicsMode = "bone_follow"
    position: Literal["append", "insert_before"] = "append"
    source_index: int | None = None
    new_id: str | None = None

    def __post_init__(self) -> None:
        _require_optional_new_id(self.new_id)
        for field_name in ("local_name", "universal_name"):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"{field_name} must be a string.")

        if isinstance(self.bone_index, PmxStructuralNewReference):
            if self.bone_index.target_kind != "bone":
                raise ValueError("bone_index new reference must target bone.")
        else:
            bone_index = _require_plain_int(self.bone_index, "bone_index")
            if bone_index < -1:
                raise ValueError("bone_index cannot be smaller than -1.")

        collision_group = _require_plain_int(
            self.collision_group,
            "collision_group",
        )
        if not 0 <= collision_group <= 15:
            raise ValueError("collision_group must be a value from 0 through 15.")

        collision_mask = _require_plain_int(self.collision_mask, "collision_mask")
        if not 0 <= collision_mask <= 0xFFFF:
            raise ValueError(
                "collision_mask must fit in one unsigned 16-bit integer."
            )

        if self.shape not in ("sphere", "box", "capsule"):
            raise ValueError("shape must be sphere, box, or capsule.")
        if self.physics_mode not in (
            "bone_follow",
            "physics",
            "physics_with_bone_alignment",
        ):
            raise ValueError(
                "physics_mode must be bone_follow, physics, or "
                "physics_with_bone_alignment."
            )

        _require_float_tuple(
            self.size,
            field_name="size",
            length=3,
            nonnegative=True,
        )
        _require_float_tuple(
            self.body_position,
            field_name="body_position",
            length=3,
        )
        _require_float_tuple(
            self.rotation,
            field_name="rotation",
            length=3,
        )
        for field_name in (
            "mass",
            "linear_damping",
            "angular_damping",
            "restitution",
            "friction",
        ):
            value = getattr(self, field_name)
            _require_finite_float(value, field_name)
            if value < 0.0:
                raise ValueError(f"{field_name} cannot be negative.")

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
    "PmxStructuralRigidBodyInsertion",
)
