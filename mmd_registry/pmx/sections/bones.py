"""Typed reading for complete PMX bone and IK records."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from mmd_registry.binary_reader import BinaryReader
from mmd_registry.pmx.document import (
    PMX_BONE_FLAG_EXTERNAL_PARENT,
    PMX_BONE_FLAG_FIXED_AXIS,
    PMX_BONE_FLAG_IK,
    PMX_BONE_FLAG_INHERIT_ROTATION,
    PMX_BONE_FLAG_INHERIT_TRANSLATION,
    PMX_BONE_FLAG_LOCAL_AXES,
    PMX_BONE_FLAG_TAIL_INDEX,
    PmxBone,
    PmxBoneTailMode,
    PmxHeader,
    PmxIk,
    PmxIkLink,
    PmxVector3,
    decode_pmx_bone_flags,
)
from mmd_registry.pmx.errors import raise_pmx_error
from mmd_registry.pmx.sections.header import MAX_PMX_NAME_BYTES


MAX_PMX_BONE_COUNT: Final[int] = 200_000
MAX_PMX_IK_LOOP_COUNT: Final[int] = 1_000_000
MAX_PMX_IK_LINK_COUNT: Final[int] = 100_000
MAX_PMX_TOTAL_IK_LINK_COUNT: Final[int] = 1_000_000


@dataclass(slots=True)
class PmxBoneReadState:
    """Incremental bone data for legacy scanner projections."""

    bone_count: int | None = None
    bones: tuple[PmxBone, ...] = ()


def _read_int32(
    reader: BinaryReader,
    label: str,
) -> int:
    """Read one little-endian signed 32-bit PMX integer."""

    return int.from_bytes(
        reader.read_exact(4, label),
        byteorder="little",
        signed=True,
    )


def _read_uint16(
    reader: BinaryReader,
    label: str,
) -> int:
    """Read one little-endian unsigned 16-bit PMX integer."""

    return int.from_bytes(
        reader.read_exact(2, label),
        byteorder="little",
        signed=False,
    )


def _read_vec3(
    reader: BinaryReader,
    label: str,
) -> PmxVector3:
    """Read one ordered PMX vec3."""

    return (
        reader.read_float32(f"{label} x"),
        reader.read_float32(f"{label} y"),
        reader.read_float32(f"{label} z"),
    )


def _minimum_pmx_bone_size(header: PmxHeader) -> int:
    """Return the smallest possible PMX bone-record size."""

    text_length_fields = 8
    position_size = 12
    parent_index_size = header.index_sizes.bone
    transform_layer_size = 4
    flags_size = 2
    minimum_tail_size = min(header.index_sizes.bone, 12)

    return (
        text_length_fields
        + position_size
        + parent_index_size
        + transform_layer_size
        + flags_size
        + minimum_tail_size
    )


def validate_pmx_bone_index(
    value: int,
    *,
    bone_count: int,
    section: str,
    record_index: int,
    label: str,
    offset: int,
    allow_sentinel: bool,
) -> None:
    """Validate one signed PMX bone index."""

    minimum_value = -1 if allow_sentinel else 0

    if value < minimum_value or value >= bone_count:
        if bone_count == 0:
            expected = (
                "expected only -1 because no bones are declared"
                if allow_sentinel
                else "no valid bone index exists"
            )
        elif allow_sentinel:
            expected = f"expected -1 or a value from 0 through {bone_count - 1}"
        else:
            expected = f"expected a value from 0 through {bone_count - 1}"

        raise_pmx_error(
            section=section,
            record_index=record_index,
            offset=offset,
            operation=f"validating {label}",
            reason=(
                f"index {value} is invalid for bone count {bone_count}; {expected}."
            ),
        )


def _read_pmx_ik(
    reader: BinaryReader,
    *,
    bone_index_size: int,
    bone_count: int,
    bone_record_index: int,
) -> PmxIk:
    """Read one PMX inverse-kinematics definition."""

    target_offset = reader.offset
    target_bone_index = reader.read_index(
        bone_index_size,
        signed=True,
        label="IK target bone index",
    )
    validate_pmx_bone_index(
        target_bone_index,
        bone_count=bone_count,
        section="bones",
        record_index=bone_record_index,
        label="IK target bone index",
        offset=target_offset,
        allow_sentinel=False,
    )

    loop_count_offset = reader.offset
    loop_count = _read_int32(reader, "IK loop count")

    if loop_count < 0:
        raise_pmx_error(
            section="bones",
            record_index=bone_record_index,
            offset=loop_count_offset,
            operation="validating IK loop count",
            reason=f"value {loop_count} cannot be negative.",
        )

    if loop_count > MAX_PMX_IK_LOOP_COUNT:
        raise_pmx_error(
            section="bones",
            record_index=bone_record_index,
            offset=loop_count_offset,
            operation="validating IK loop count",
            reason=(
                f"value {loop_count} exceeds the safety limit "
                f"of {MAX_PMX_IK_LOOP_COUNT}."
            ),
        )

    angle_limit_offset = reader.offset
    angle_limit = reader.read_float32("IK angle limit")

    if not math.isfinite(angle_limit):
        raise_pmx_error(
            section="bones",
            record_index=bone_record_index,
            offset=angle_limit_offset,
            operation="validating IK angle limit",
            reason="value must be a finite floating-point number.",
        )

    with reader.context(
        "bones",
        record_index=bone_record_index,
    ):
        link_count = reader.read_bounded_count(
            "IK link count",
            max_count=MAX_PMX_IK_LINK_COUNT,
            minimum_item_size=(bone_index_size + 1),
        )

    links: list[PmxIkLink] = []

    for link_index in range(link_count):
        link_section = f"bones[{bone_record_index}].ik_links"

        with reader.context(
            link_section,
            record_index=link_index,
        ):
            link_bone_offset = reader.offset
            link_bone_index = reader.read_index(
                bone_index_size,
                signed=True,
                label="IK link bone index",
            )
            validate_pmx_bone_index(
                link_bone_index,
                bone_count=bone_count,
                section=link_section,
                record_index=link_index,
                label="IK link bone index",
                offset=link_bone_offset,
                allow_sentinel=False,
            )

            limit_flag_offset = reader.offset
            limit_flag = reader.read_uint8("IK link angle-limit flag")

            if limit_flag not in {0, 1}:
                raise_pmx_error(
                    section=link_section,
                    record_index=link_index,
                    offset=limit_flag_offset,
                    operation="validating IK link angle-limit flag",
                    reason=f"invalid flag {limit_flag}; expected 0 or 1.",
                )

            if limit_flag == 1:
                lower_limit = _read_vec3(reader, "IK link lower angle limit")
                upper_limit = _read_vec3(reader, "IK link upper angle limit")
            else:
                lower_limit = None
                upper_limit = None

        links.append(
            PmxIkLink(
                bone_index=link_bone_index,
                angle_limits_enabled=(limit_flag == 1),
                lower_limit=lower_limit,
                upper_limit=upper_limit,
            )
        )

    return PmxIk(
        target_bone_index=target_bone_index,
        loop_count=loop_count,
        angle_limit=angle_limit,
        links=tuple(links),
    )


def _read_pmx_bone(
    reader: BinaryReader,
    *,
    header: PmxHeader,
    record_index: int,
    bone_count: int,
) -> PmxBone:
    """Read one complete PMX bone and all flag-controlled fields."""

    bone_index_size = header.index_sizes.bone
    require_even_length = header.encoding == "utf-16-le"

    with reader.context(
        "bones",
        record_index=record_index,
    ):
        local_name = reader.read_length_prefixed_text(
            "local bone name",
            encoding=header.encoding,
            max_length=MAX_PMX_NAME_BYTES,
            require_even_length=require_even_length,
        )
        universal_name = reader.read_length_prefixed_text(
            "universal bone name",
            encoding=header.encoding,
            max_length=MAX_PMX_NAME_BYTES,
            require_even_length=require_even_length,
        )
        position = _read_vec3(reader, "bone position")

        parent_offset = reader.offset
        parent_bone_index = reader.read_index(
            bone_index_size,
            signed=True,
            label="parent bone index",
        )
        validate_pmx_bone_index(
            parent_bone_index,
            bone_count=bone_count,
            section="bones",
            record_index=record_index,
            label="parent bone index",
            offset=parent_offset,
            allow_sentinel=True,
        )

        transform_layer = _read_int32(reader, "bone transform layer")
        flags = _read_uint16(reader, "bone flags")

        if flags & PMX_BONE_FLAG_TAIL_INDEX:
            tail_mode: PmxBoneTailMode = "bone"
            tail_offset = None
            tail_index_offset = reader.offset
            tail_bone_index = reader.read_index(
                bone_index_size,
                signed=True,
                label="tail bone index",
            )
            validate_pmx_bone_index(
                tail_bone_index,
                bone_count=bone_count,
                section="bones",
                record_index=record_index,
                label="tail bone index",
                offset=tail_index_offset,
                allow_sentinel=True,
            )
        else:
            tail_mode = "offset"
            tail_bone_index = None
            tail_offset = _read_vec3(reader, "bone tail offset")

        inherit_parent_bone_index = None
        inherit_weight = None

        if flags & (
            PMX_BONE_FLAG_INHERIT_ROTATION | PMX_BONE_FLAG_INHERIT_TRANSLATION
        ):
            inherit_index_offset = reader.offset
            inherit_parent_bone_index = reader.read_index(
                bone_index_size,
                signed=True,
                label="inherit parent bone index",
            )
            validate_pmx_bone_index(
                inherit_parent_bone_index,
                bone_count=bone_count,
                section="bones",
                record_index=record_index,
                label="inherit parent bone index",
                offset=inherit_index_offset,
                allow_sentinel=True,
            )
            inherit_weight = reader.read_float32("bone inherit weight")

        fixed_axis = None
        if flags & PMX_BONE_FLAG_FIXED_AXIS:
            fixed_axis = _read_vec3(reader, "bone fixed axis")

        local_axis_x = None
        local_axis_z = None
        if flags & PMX_BONE_FLAG_LOCAL_AXES:
            local_axis_x = _read_vec3(reader, "bone local x axis")
            local_axis_z = _read_vec3(reader, "bone local z axis")

        external_parent_key = None
        if flags & PMX_BONE_FLAG_EXTERNAL_PARENT:
            external_parent_key = _read_int32(reader, "external parent key")

        ik = None
        if flags & PMX_BONE_FLAG_IK:
            ik = _read_pmx_ik(
                reader,
                bone_index_size=bone_index_size,
                bone_count=bone_count,
                bone_record_index=record_index,
            )

    return PmxBone(
        local_name=local_name,
        universal_name=universal_name,
        position=position,
        parent_bone_index=parent_bone_index,
        transform_layer=transform_layer,
        flags=flags,
        flag_names=decode_pmx_bone_flags(flags),
        tail_mode=tail_mode,
        tail_bone_index=tail_bone_index,
        tail_offset=tail_offset,
        inherit_parent_bone_index=inherit_parent_bone_index,
        inherit_weight=inherit_weight,
        fixed_axis=fixed_axis,
        local_axis_x=local_axis_x,
        local_axis_z=local_axis_z,
        external_parent_key=external_parent_key,
        ik=ik,
    )


def read_pmx_bones(
    reader: BinaryReader,
    *,
    header: PmxHeader,
    state: PmxBoneReadState | None = None,
) -> tuple[PmxBone, ...]:
    """Read the complete ordered PMX bone section."""

    if not isinstance(header, PmxHeader):
        raise TypeError("header must be a PmxHeader instance.")

    read_state = state if state is not None else PmxBoneReadState()

    with reader.context("bones"):
        bone_count = reader.read_bounded_count(
            "bone count",
            max_count=MAX_PMX_BONE_COUNT,
            minimum_item_size=_minimum_pmx_bone_size(header),
        )

    read_state.bone_count = bone_count
    bones: list[PmxBone] = []
    total_ik_links = 0

    for record_index in range(bone_count):
        bone = _read_pmx_bone(
            reader,
            header=header,
            record_index=record_index,
            bone_count=bone_count,
        )
        bones.append(bone)

        if bone.ik is not None:
            total_ik_links += len(bone.ik.links)

            if total_ik_links > MAX_PMX_TOTAL_IK_LINK_COUNT:
                raise_pmx_error(
                    section="bones",
                    record_index=record_index,
                    offset=reader.offset,
                    operation="validating total IK link count",
                    reason=(
                        f"cumulative IK link count {total_ik_links} "
                        "exceeds the safety limit of "
                        f"{MAX_PMX_TOTAL_IK_LINK_COUNT}."
                    ),
                )

    bone_records = tuple(bones)
    read_state.bones = bone_records
    return bone_records
