"""Typed reading for complete PMX joint records."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final, cast

from mmd_registry.binary_reader import BinaryReader
from mmd_registry.pmx.document import (
    PmxHeader,
    PmxJoint,
    PmxJointType,
    PmxVector3,
)
from mmd_registry.pmx.errors import raise_pmx_error
from mmd_registry.pmx.sections.header import MAX_PMX_NAME_BYTES


MAX_PMX_JOINT_COUNT: Final[int] = 200_000


@dataclass(slots=True)
class PmxJointReadState:
    """Incremental joint data for legacy scanner projections."""

    joint_count: int | None = None
    joints: tuple[PmxJoint, ...] = ()


def _read_vec3(reader: BinaryReader, label: str) -> PmxVector3:
    """Read one ordered PMX vec3."""

    return (
        reader.read_float32(f"{label} x"),
        reader.read_float32(f"{label} y"),
        reader.read_float32(f"{label} z"),
    )


def _minimum_joint_size(header: PmxHeader) -> int:
    """Return the fixed minimum size of one PMX joint record."""

    return 8 + 1 + header.index_sizes.rigid_body * 2 + 8 * 12


def _validate_finite_vec3(
    value: PmxVector3,
    *,
    record_index: int,
    label: str,
    offset: int,
) -> None:
    """Validate one finite PMX joint vec3."""

    for component_index, component in enumerate(value):
        component_label = f"{label} {('x', 'y', 'z')[component_index]}"
        if not math.isfinite(component):
            raise_pmx_error(
                section="joints",
                record_index=record_index,
                offset=offset + component_index * 4,
                operation=f"validating {component_label}",
                reason=f"{component_label} must be finite.",
            )


def _validate_index_range(
    value: int,
    *,
    count: int,
    record_index: int,
    label: str,
    offset: int,
) -> None:
    """Validate one rigid-body reference permitting the -1 sentinel."""

    if value < -1 or value >= count:
        if count == 0:
            expected = "expected only -1 because no records are declared"
        else:
            expected = f"expected -1 or a value from 0 through {count - 1}"

        raise_pmx_error(
            section="joints",
            record_index=record_index,
            offset=offset,
            operation=f"validating {label}",
            reason=(
                f"index {value} is invalid for record count {count}; {expected}."
            ),
        )


def _decode_joint_type(
    value: int,
    *,
    header: PmxHeader,
    record_index: int,
    offset: int,
) -> tuple[PmxJointType, str]:
    """Validate and decode one PMX joint type."""

    type_names = {
        0: "spring_6dof",
        1: "6dof",
        2: "point_to_point",
        3: "cone_twist",
        4: "slider",
        5: "hinge",
    }
    try:
        type_name = type_names[value]
    except KeyError:
        raise_pmx_error(
            section="joints",
            record_index=record_index,
            offset=offset,
            operation="validating joint type",
            reason=f"invalid joint type {value}; expected a value from 0 through 5.",
        )

    if header.version == 2.0 and value != 0:
        raise_pmx_error(
            section="joints",
            record_index=record_index,
            offset=offset,
            operation="validating joint type",
            reason=(
                f"joint type {value} ({type_name}) requires PMX 2.1; "
                "PMX 2.0 supports only type 0 (spring_6dof)."
            ),
        )

    return cast(PmxJointType, value), type_name


def _validate_limit_pair(
    minimum: PmxVector3,
    maximum: PmxVector3,
    *,
    record_index: int,
    label: str,
    minimum_offset: int,
) -> None:
    """Validate component-wise PMX joint lower and upper limits."""

    for component_index, (minimum_value, maximum_value) in enumerate(
        zip(minimum, maximum)
    ):
        if minimum_value <= maximum_value:
            continue

        component_name = ("x", "y", "z")[component_index]
        raise_pmx_error(
            section="joints",
            record_index=record_index,
            offset=minimum_offset + component_index * 4,
            operation=f"validating {label} limits",
            reason=(
                f"{label} minimum {component_name} value {minimum_value} "
                f"exceeds maximum {component_name} value {maximum_value}."
            ),
        )


def _read_joint(
    reader: BinaryReader,
    *,
    header: PmxHeader,
    rigid_body_count: int,
    record_index: int,
) -> PmxJoint:
    """Read and validate one PMX joint record."""

    require_even_length = header.encoding == "utf-16-le"

    with reader.context("joints", record_index=record_index):
        local_name = reader.read_length_prefixed_text(
            "local joint name",
            encoding=header.encoding,
            max_length=MAX_PMX_NAME_BYTES,
            require_even_length=require_even_length,
        )
        universal_name = reader.read_length_prefixed_text(
            "universal joint name",
            encoding=header.encoding,
            max_length=MAX_PMX_NAME_BYTES,
            require_even_length=require_even_length,
        )

        joint_type_offset = reader.offset
        joint_type, joint_type_name = _decode_joint_type(
            reader.read_uint8("joint type"),
            header=header,
            record_index=record_index,
            offset=joint_type_offset,
        )

        rigid_body_a_offset = reader.offset
        rigid_body_a_index = reader.read_index(
            header.index_sizes.rigid_body,
            signed=True,
            label="joint rigid-body A index",
        )
        _validate_index_range(
            rigid_body_a_index,
            count=rigid_body_count,
            record_index=record_index,
            label="joint rigid-body A index",
            offset=rigid_body_a_offset,
        )

        rigid_body_b_offset = reader.offset
        rigid_body_b_index = reader.read_index(
            header.index_sizes.rigid_body,
            signed=True,
            label="joint rigid-body B index",
        )
        _validate_index_range(
            rigid_body_b_index,
            count=rigid_body_count,
            record_index=record_index,
            label="joint rigid-body B index",
            offset=rigid_body_b_offset,
        )

        vector_fields: list[tuple[PmxVector3, int]] = []
        for vector_label in (
            "joint position",
            "joint rotation",
            "joint translation limit minimum",
            "joint translation limit maximum",
            "joint rotation limit minimum",
            "joint rotation limit maximum",
            "joint translation spring",
            "joint rotation spring",
        ):
            vector_offset = reader.offset
            vector_value = _read_vec3(reader, vector_label)
            _validate_finite_vec3(
                vector_value,
                record_index=record_index,
                label=vector_label,
                offset=vector_offset,
            )
            vector_fields.append((vector_value, vector_offset))

    _validate_limit_pair(
        vector_fields[2][0],
        vector_fields[3][0],
        record_index=record_index,
        label="joint translation limit",
        minimum_offset=vector_fields[2][1],
    )
    _validate_limit_pair(
        vector_fields[4][0],
        vector_fields[5][0],
        record_index=record_index,
        label="joint rotation limit",
        minimum_offset=vector_fields[4][1],
    )

    return PmxJoint(
        local_name=local_name,
        universal_name=universal_name,
        joint_type=joint_type,
        joint_type_name=joint_type_name,
        rigid_body_a_index=rigid_body_a_index,
        rigid_body_b_index=rigid_body_b_index,
        position=vector_fields[0][0],
        rotation=vector_fields[1][0],
        translation_limit_minimum=vector_fields[2][0],
        translation_limit_maximum=vector_fields[3][0],
        rotation_limit_minimum=vector_fields[4][0],
        rotation_limit_maximum=vector_fields[5][0],
        translation_spring=vector_fields[6][0],
        rotation_spring=vector_fields[7][0],
    )


def _validate_count_argument(value: object, label: str) -> int:
    """Require one nonnegative, non-boolean prior-section count."""

    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{label} must be an integer.")
    if value < 0:
        raise ValueError(f"{label} cannot be negative.")
    return value


def read_pmx_joints(
    reader: BinaryReader,
    *,
    header: PmxHeader,
    rigid_body_count: int,
    state: PmxJointReadState | None = None,
) -> tuple[PmxJoint, ...]:
    """Read the complete ordered PMX joint section."""

    if not isinstance(header, PmxHeader):
        raise TypeError("header must be a PmxHeader instance.")
    rigid_body_count = _validate_count_argument(
        rigid_body_count,
        "rigid_body_count",
    )
    read_state = state if state is not None else PmxJointReadState()

    with reader.context("joints"):
        joint_count = reader.read_bounded_count(
            "joint count",
            max_count=MAX_PMX_JOINT_COUNT,
            minimum_item_size=_minimum_joint_size(header),
        )

    read_state.joint_count = joint_count
    records = tuple(
        _read_joint(
            reader,
            header=header,
            rigid_body_count=rigid_body_count,
            record_index=record_index,
        )
        for record_index in range(joint_count)
    )
    read_state.joints = records
    return records
