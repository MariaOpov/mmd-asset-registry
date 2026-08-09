"""Typed reading for complete PMX rigid-body records."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final, cast

from mmd_registry.binary_reader import BinaryReader
from mmd_registry.pmx.document import (
    PmxHeader,
    PmxRigidBody,
    PmxRigidBodyPhysicsMode,
    PmxRigidBodyShape,
    PmxVector3,
)
from mmd_registry.pmx.errors import raise_pmx_error
from mmd_registry.pmx.sections.bones import validate_pmx_bone_index
from mmd_registry.pmx.sections.header import MAX_PMX_NAME_BYTES


MAX_PMX_RIGID_BODY_COUNT: Final[int] = 200_000


@dataclass(slots=True)
class PmxRigidBodyReadState:
    """Incremental rigid-body data for legacy scanner projections."""

    rigid_body_count: int | None = None
    rigid_bodies: tuple[PmxRigidBody, ...] = ()


def _read_uint16(reader: BinaryReader, label: str) -> int:
    """Read one little-endian unsigned 16-bit integer."""

    return int.from_bytes(
        reader.read_exact(2, label),
        byteorder="little",
        signed=False,
    )


def _read_vec3(reader: BinaryReader, label: str) -> PmxVector3:
    """Read one ordered PMX vec3."""

    return (
        reader.read_float32(f"{label} x"),
        reader.read_float32(f"{label} y"),
        reader.read_float32(f"{label} z"),
    )


def _minimum_rigid_body_size(header: PmxHeader) -> int:
    """Return the fixed minimum size of one PMX rigid-body record."""

    return 8 + header.index_sizes.bone + 1 + 2 + 1 + 36 + 20 + 1


def _validate_finite_scalar(
    value: float,
    *,
    section: str,
    record_index: int,
    label: str,
    offset: int,
    nonnegative: bool,
) -> None:
    """Validate one finite PMX physics scalar."""

    if not math.isfinite(value):
        raise_pmx_error(
            section=section,
            record_index=record_index,
            offset=offset,
            operation=f"validating {label}",
            reason=f"{label} must be finite.",
        )

    if nonnegative and value < 0.0:
        raise_pmx_error(
            section=section,
            record_index=record_index,
            offset=offset,
            operation=f"validating {label}",
            reason=f"{label} cannot be negative: {value}.",
        )


def _validate_finite_vec3(
    value: PmxVector3,
    *,
    record_index: int,
    label: str,
    offset: int,
    nonnegative: bool,
) -> None:
    """Validate one finite PMX rigid-body vec3."""

    for component_index, component in enumerate(value):
        component_label = f"{label} {('x', 'y', 'z')[component_index]}"
        _validate_finite_scalar(
            component,
            section="rigid_bodies",
            record_index=record_index,
            label=component_label,
            offset=offset + component_index * 4,
            nonnegative=nonnegative,
        )


def _decode_shape(
    value: int,
    *,
    record_index: int,
    offset: int,
) -> tuple[PmxRigidBodyShape, str]:
    """Validate and decode one PMX rigid-body shape."""

    shape_names = {0: "sphere", 1: "box", 2: "capsule"}
    try:
        shape_name = shape_names[value]
    except KeyError:
        raise_pmx_error(
            section="rigid_bodies",
            record_index=record_index,
            offset=offset,
            operation="validating rigid-body shape",
            reason=(
                f"invalid rigid-body shape {value}; expected "
                "0 for sphere, 1 for box, or 2 for capsule."
            ),
        )
    return cast(PmxRigidBodyShape, value), shape_name


def _decode_physics_mode(
    value: int,
    *,
    record_index: int,
    offset: int,
) -> tuple[PmxRigidBodyPhysicsMode, str]:
    """Validate and decode one PMX rigid-body physics mode."""

    mode_names = {
        0: "bone_follow",
        1: "physics",
        2: "physics_with_bone_alignment",
    }
    try:
        mode_name = mode_names[value]
    except KeyError:
        raise_pmx_error(
            section="rigid_bodies",
            record_index=record_index,
            offset=offset,
            operation="validating rigid-body physics mode",
            reason=f"invalid physics mode {value}; expected a value from 0 through 2.",
        )
    return cast(PmxRigidBodyPhysicsMode, value), mode_name


def _read_rigid_body(
    reader: BinaryReader,
    *,
    header: PmxHeader,
    bone_count: int,
    record_index: int,
) -> PmxRigidBody:
    """Read and validate one PMX rigid-body record."""

    require_even_length = header.encoding == "utf-16-le"

    with reader.context("rigid_bodies", record_index=record_index):
        local_name = reader.read_length_prefixed_text(
            "local rigid-body name",
            encoding=header.encoding,
            max_length=MAX_PMX_NAME_BYTES,
            require_even_length=require_even_length,
        )
        universal_name = reader.read_length_prefixed_text(
            "universal rigid-body name",
            encoding=header.encoding,
            max_length=MAX_PMX_NAME_BYTES,
            require_even_length=require_even_length,
        )

        bone_index_offset = reader.offset
        bone_index = reader.read_index(
            header.index_sizes.bone,
            signed=True,
            label="rigid-body bone index",
        )
        validate_pmx_bone_index(
            bone_index,
            bone_count=bone_count,
            section="rigid_bodies",
            record_index=record_index,
            label="rigid-body bone index",
            offset=bone_index_offset,
            allow_sentinel=True,
        )

        collision_group_offset = reader.offset
        collision_group = reader.read_uint8("rigid-body collision group")
        if collision_group > 15:
            raise_pmx_error(
                section="rigid_bodies",
                record_index=record_index,
                offset=collision_group_offset,
                operation="validating rigid-body collision group",
                reason=(
                    f"collision group {collision_group} is invalid; "
                    "expected a value from 0 through 15."
                ),
            )

        collision_mask = _read_uint16(reader, "rigid-body collision mask")

        shape_offset = reader.offset
        shape, shape_name = _decode_shape(
            reader.read_uint8("rigid-body shape"),
            record_index=record_index,
            offset=shape_offset,
        )

        size_offset = reader.offset
        size = _read_vec3(reader, "rigid-body size")
        _validate_finite_vec3(
            size,
            record_index=record_index,
            label="rigid-body size",
            offset=size_offset,
            nonnegative=True,
        )

        position_offset = reader.offset
        position = _read_vec3(reader, "rigid-body position")
        _validate_finite_vec3(
            position,
            record_index=record_index,
            label="rigid-body position",
            offset=position_offset,
            nonnegative=False,
        )

        rotation_offset = reader.offset
        rotation = _read_vec3(reader, "rigid-body rotation")
        _validate_finite_vec3(
            rotation,
            record_index=record_index,
            label="rigid-body rotation",
            offset=rotation_offset,
            nonnegative=False,
        )

        scalar_values: list[float] = []
        for scalar_label in (
            "rigid-body mass",
            "rigid-body linear damping",
            "rigid-body angular damping",
            "rigid-body restitution",
            "rigid-body friction",
        ):
            scalar_offset = reader.offset
            scalar_value = reader.read_float32(scalar_label)
            _validate_finite_scalar(
                scalar_value,
                section="rigid_bodies",
                record_index=record_index,
                label=scalar_label,
                offset=scalar_offset,
                nonnegative=True,
            )
            scalar_values.append(scalar_value)

        physics_mode_offset = reader.offset
        physics_mode, physics_mode_name = _decode_physics_mode(
            reader.read_uint8("rigid-body physics mode"),
            record_index=record_index,
            offset=physics_mode_offset,
        )

    return PmxRigidBody(
        local_name=local_name,
        universal_name=universal_name,
        bone_index=bone_index,
        collision_group=collision_group,
        collision_mask=collision_mask,
        shape=shape,
        shape_name=shape_name,
        size=size,
        position=position,
        rotation=rotation,
        mass=scalar_values[0],
        linear_damping=scalar_values[1],
        angular_damping=scalar_values[2],
        restitution=scalar_values[3],
        friction=scalar_values[4],
        physics_mode=physics_mode,
        physics_mode_name=physics_mode_name,
    )


def _validate_count_argument(value: object, label: str) -> int:
    """Require one nonnegative, non-boolean prior-section count."""

    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{label} must be an integer.")
    if value < 0:
        raise ValueError(f"{label} cannot be negative.")
    return value


def read_pmx_rigid_bodies(
    reader: BinaryReader,
    *,
    header: PmxHeader,
    bone_count: int,
    state: PmxRigidBodyReadState | None = None,
) -> tuple[PmxRigidBody, ...]:
    """Read the complete ordered PMX rigid-body section."""

    if not isinstance(header, PmxHeader):
        raise TypeError("header must be a PmxHeader instance.")
    bone_count = _validate_count_argument(bone_count, "bone_count")
    read_state = state if state is not None else PmxRigidBodyReadState()

    with reader.context("rigid_bodies"):
        rigid_body_count = reader.read_bounded_count(
            "rigid-body count",
            max_count=MAX_PMX_RIGID_BODY_COUNT,
            minimum_item_size=_minimum_rigid_body_size(header),
        )

    read_state.rigid_body_count = rigid_body_count
    records = tuple(
        _read_rigid_body(
            reader,
            header=header,
            bone_count=bone_count,
            record_index=record_index,
        )
        for record_index in range(rigid_body_count)
    )
    read_state.rigid_bodies = records
    return records
