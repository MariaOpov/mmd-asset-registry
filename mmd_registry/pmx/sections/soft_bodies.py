"""Typed reading for complete PMX 2.1 soft-body records."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final, cast

from mmd_registry.binary_reader import BinaryReader
from mmd_registry.pmx.document import (
    PmxHeader,
    PmxSoftBody,
    PmxSoftBodyAerodynamicsModel,
    PmxSoftBodyAnchor,
    PmxSoftBodyClusterConfig,
    PmxSoftBodyConfig,
    PmxSoftBodyIterationConfig,
    PmxSoftBodyMaterialConfig,
    PmxSoftBodyShape,
)
from mmd_registry.pmx.errors import raise_pmx_error
from mmd_registry.pmx.sections.header import MAX_PMX_NAME_BYTES


MAX_PMX_SOFT_BODY_COUNT: Final[int] = 100_000
MAX_PMX_SOFT_BODY_ANCHOR_COUNT: Final[int] = 500_000
MAX_PMX_TOTAL_SOFT_BODY_ANCHOR_COUNT: Final[int] = 1_000_000
MAX_PMX_SOFT_BODY_PIN_COUNT: Final[int] = 500_000
MAX_PMX_TOTAL_SOFT_BODY_PIN_COUNT: Final[int] = 1_000_000
MAX_PMX_SOFT_BODY_PARAMETER_COUNT: Final[int] = 1_000_000


@dataclass(slots=True)
class PmxSoftBodyReadState:
    """Incremental soft-body data for legacy scanner projections."""

    soft_body_count: int | None = None
    soft_bodies: tuple[PmxSoftBody, ...] = ()


def _read_int32(reader: BinaryReader, label: str) -> int:
    """Read one little-endian signed 32-bit integer."""

    return int.from_bytes(
        reader.read_exact(4, label),
        byteorder="little",
        signed=True,
    )


def _read_uint16(reader: BinaryReader, label: str) -> int:
    """Read one little-endian unsigned 16-bit integer."""

    return int.from_bytes(
        reader.read_exact(2, label),
        byteorder="little",
        signed=False,
    )


def _minimum_soft_body_size(header: PmxHeader) -> int:
    """Return the fixed minimum size of one PMX 2.1 soft body."""

    return (
        8
        + 1
        + header.index_sizes.material
        + 4
        + 8
        + 8
        + 4
        + 12 * 4
        + 6 * 4
        + 4 * 4
        + 3 * 4
        + 8
    )


def _validate_index_range(
    value: int,
    *,
    count: int,
    section: str,
    record_index: int,
    label: str,
    offset: int,
    allow_sentinel: bool,
) -> None:
    """Validate one reference to a previously read PMX section."""

    minimum_value = -1 if allow_sentinel else 0
    if value < minimum_value or value >= count:
        if count == 0:
            expected = (
                "expected only -1 because no records are declared"
                if allow_sentinel
                else "no valid index exists"
            )
        elif allow_sentinel:
            expected = f"expected -1 or a value from 0 through {count - 1}"
        else:
            expected = f"expected a value from 0 through {count - 1}"

        raise_pmx_error(
            section=section,
            record_index=record_index,
            offset=offset,
            operation=f"validating {label}",
            reason=(
                f"index {value} is invalid for record count {count}; {expected}."
            ),
        )


def _decode_shape(
    value: int,
    *,
    record_index: int,
    offset: int,
) -> tuple[PmxSoftBodyShape, str]:
    """Validate and decode one PMX 2.1 soft-body shape."""

    shape_names = {0: "tri_mesh", 1: "rope"}
    try:
        shape_name = shape_names[value]
    except KeyError:
        raise_pmx_error(
            section="soft_bodies",
            record_index=record_index,
            offset=offset,
            operation="validating soft-body shape",
            reason=f"invalid soft-body shape {value}; expected 0 or 1.",
        )
    return cast(PmxSoftBodyShape, value), shape_name


def _decode_flags(
    value: int,
    *,
    record_index: int,
    offset: int,
) -> tuple[str, ...]:
    """Validate and decode PMX 2.1 soft-body flag bits."""

    unknown_bits = value & ~0x07
    if unknown_bits:
        raise_pmx_error(
            section="soft_bodies",
            record_index=record_index,
            offset=offset,
            operation="validating soft-body flags",
            reason=f"soft-body flags contain unknown bits 0x{unknown_bits:02x}.",
        )

    definitions = (
        (0x01, "generate_bending_links"),
        (0x02, "generate_clusters"),
        (0x04, "randomize_constraints"),
    )
    return tuple(name for bit, name in definitions if value & bit)


def _decode_aerodynamics_model(
    value: int,
    *,
    record_index: int,
    offset: int,
) -> tuple[PmxSoftBodyAerodynamicsModel, str]:
    """Validate and decode a PMX 2.1 aerodynamics model."""

    model_names = {
        0: "vertex_point",
        1: "vertex_two_sided",
        2: "vertex_one_sided",
        3: "face_two_sided",
        4: "face_one_sided",
    }
    try:
        model_name = model_names[value]
    except KeyError:
        raise_pmx_error(
            section="soft_bodies",
            record_index=record_index,
            offset=offset,
            operation="validating soft-body aerodynamics model",
            reason=(
                f"invalid soft-body aerodynamics model {value}; "
                "expected a value from 0 through 4."
            ),
        )
    return cast(PmxSoftBodyAerodynamicsModel, value), model_name


def _read_float(
    reader: BinaryReader,
    *,
    record_index: int,
    label: str,
    nonnegative: bool,
) -> float:
    """Read and validate one soft-body float field."""

    offset = reader.offset
    value = reader.read_float32(label)
    if not math.isfinite(value):
        raise_pmx_error(
            section="soft_bodies",
            record_index=record_index,
            offset=offset,
            operation=f"validating {label}",
            reason=f"{label} must be finite.",
        )
    if nonnegative and value < 0.0:
        raise_pmx_error(
            section="soft_bodies",
            record_index=record_index,
            offset=offset,
            operation=f"validating {label}",
            reason=f"{label} cannot be negative: {value}.",
        )
    return value


def _read_parameter_count(
    reader: BinaryReader,
    *,
    record_index: int,
    label: str,
) -> int:
    """Read one bounded nonnegative PMX soft-body integer parameter."""

    offset = reader.offset
    value = _read_int32(reader, label)
    if value < 0:
        raise_pmx_error(
            section="soft_bodies",
            record_index=record_index,
            offset=offset,
            operation=f"validating {label}",
            reason=f"{label} cannot be negative: {value}.",
        )
    if value > MAX_PMX_SOFT_BODY_PARAMETER_COUNT:
        raise_pmx_error(
            section="soft_bodies",
            record_index=record_index,
            offset=offset,
            operation=f"validating {label}",
            reason=(
                f"{label} {value} exceeds the safety limit of "
                f"{MAX_PMX_SOFT_BODY_PARAMETER_COUNT}."
            ),
        )
    return value


def _read_anchor(
    reader: BinaryReader,
    *,
    header: PmxHeader,
    rigid_body_count: int,
    vertex_count: int,
    soft_body_index: int,
    anchor_index: int,
) -> PmxSoftBodyAnchor:
    """Read and validate one PMX 2.1 soft-body anchor."""

    section = f"soft_bodies[{soft_body_index}].anchors"
    with reader.context(section, record_index=anchor_index):
        rigid_body_offset = reader.offset
        rigid_body_index = reader.read_index(
            header.index_sizes.rigid_body,
            signed=True,
            label="soft-body anchor rigid-body index",
        )
        _validate_index_range(
            rigid_body_index,
            count=rigid_body_count,
            section=section,
            record_index=anchor_index,
            label="soft-body anchor rigid-body index",
            offset=rigid_body_offset,
            allow_sentinel=False,
        )

        vertex_offset = reader.offset
        vertex_index = reader.read_index(
            header.index_sizes.vertex,
            signed=False,
            label="soft-body anchor vertex index",
        )
        _validate_index_range(
            vertex_index,
            count=vertex_count,
            section=section,
            record_index=anchor_index,
            label="soft-body anchor vertex index",
            offset=vertex_offset,
            allow_sentinel=False,
        )

        near_mode_offset = reader.offset
        near_mode_value = reader.read_uint8("soft-body anchor near-mode flag")
        if near_mode_value not in (0, 1):
            raise_pmx_error(
                section=section,
                record_index=anchor_index,
                offset=near_mode_offset,
                operation="validating soft-body anchor near-mode flag",
                reason=(
                    "invalid soft-body anchor near-mode flag "
                    f"{near_mode_value}; expected 0 or 1."
                ),
            )

    return PmxSoftBodyAnchor(
        rigid_body_index=rigid_body_index,
        vertex_index=vertex_index,
        near_mode=bool(near_mode_value),
    )


def _read_soft_body(
    reader: BinaryReader,
    *,
    header: PmxHeader,
    material_count: int,
    rigid_body_count: int,
    vertex_count: int,
    record_index: int,
) -> PmxSoftBody:
    """Read and validate one PMX 2.1 soft-body record."""

    require_even_length = header.encoding == "utf-16-le"

    with reader.context("soft_bodies", record_index=record_index):
        local_name = reader.read_length_prefixed_text(
            "local soft-body name",
            encoding=header.encoding,
            max_length=MAX_PMX_NAME_BYTES,
            require_even_length=require_even_length,
        )
        universal_name = reader.read_length_prefixed_text(
            "universal soft-body name",
            encoding=header.encoding,
            max_length=MAX_PMX_NAME_BYTES,
            require_even_length=require_even_length,
        )

        shape_offset = reader.offset
        shape, shape_name = _decode_shape(
            reader.read_uint8("soft-body shape"),
            record_index=record_index,
            offset=shape_offset,
        )

        material_offset = reader.offset
        material_index = reader.read_index(
            header.index_sizes.material,
            signed=True,
            label="soft-body material index",
        )
        _validate_index_range(
            material_index,
            count=material_count,
            section="soft_bodies",
            record_index=record_index,
            label="soft-body material index",
            offset=material_offset,
            allow_sentinel=True,
        )

        collision_group_offset = reader.offset
        collision_group = reader.read_uint8("soft-body collision group")
        if collision_group > 15:
            raise_pmx_error(
                section="soft_bodies",
                record_index=record_index,
                offset=collision_group_offset,
                operation="validating soft-body collision group",
                reason=(
                    f"soft-body collision group {collision_group} is "
                    "outside the supported range 0 through 15."
                ),
            )

        collision_mask = _read_uint16(reader, "soft-body collision mask")

        flags_offset = reader.offset
        flags = reader.read_uint8("soft-body flags")
        flag_names = _decode_flags(
            flags,
            record_index=record_index,
            offset=flags_offset,
        )

        bending_link_distance = _read_parameter_count(
            reader,
            record_index=record_index,
            label="soft-body bending-link distance",
        )
        cluster_count = _read_parameter_count(
            reader,
            record_index=record_index,
            label="soft-body cluster count",
        )
        total_mass = _read_float(
            reader,
            record_index=record_index,
            label="soft-body total mass",
            nonnegative=True,
        )
        collision_margin = _read_float(
            reader,
            record_index=record_index,
            label="soft-body collision margin",
            nonnegative=True,
        )

        aerodynamics_offset = reader.offset
        aerodynamics_model, aerodynamics_model_name = _decode_aerodynamics_model(
            _read_int32(reader, "soft-body aerodynamics model"),
            record_index=record_index,
            offset=aerodynamics_offset,
        )

        config_values = tuple(
            _read_float(
                reader,
                record_index=record_index,
                label=label,
                nonnegative=False,
            )
            for label in (
                "soft-body velocity correction factor",
                "soft-body damping coefficient",
                "soft-body drag coefficient",
                "soft-body lift coefficient",
                "soft-body pressure coefficient",
                "soft-body volume conservation coefficient",
                "soft-body dynamic friction coefficient",
                "soft-body pose matching coefficient",
                "soft-body rigid contact hardness",
                "soft-body kinetic contact hardness",
                "soft-body soft contact hardness",
                "soft-body anchor hardness",
            )
        )
        cluster_values = tuple(
            _read_float(
                reader,
                record_index=record_index,
                label=label,
                nonnegative=False,
            )
            for label in (
                "soft-body soft-rigid cluster hardness",
                "soft-body soft-kinetic cluster hardness",
                "soft-body soft-soft cluster hardness",
                "soft-body soft-rigid impulse split",
                "soft-body soft-kinetic impulse split",
                "soft-body soft-soft impulse split",
            )
        )
        iteration_values = tuple(
            _read_parameter_count(
                reader,
                record_index=record_index,
                label=label,
            )
            for label in (
                "soft-body velocity iteration count",
                "soft-body position iteration count",
                "soft-body drift iteration count",
                "soft-body cluster iteration count",
            )
        )
        material_values = tuple(
            _read_float(
                reader,
                record_index=record_index,
                label=label,
                nonnegative=False,
            )
            for label in (
                "soft-body linear stiffness",
                "soft-body area-angular stiffness",
                "soft-body volume stiffness",
            )
        )

        anchor_count = reader.read_bounded_count(
            "soft-body anchor count",
            max_count=MAX_PMX_SOFT_BODY_ANCHOR_COUNT,
            minimum_item_size=(
                header.index_sizes.rigid_body + header.index_sizes.vertex + 1
            ),
        )
        anchors = tuple(
            _read_anchor(
                reader,
                header=header,
                rigid_body_count=rigid_body_count,
                vertex_count=vertex_count,
                soft_body_index=record_index,
                anchor_index=anchor_index,
            )
            for anchor_index in range(anchor_count)
        )

        pinned_vertex_count = reader.read_bounded_count(
            "soft-body pinned-vertex count",
            max_count=MAX_PMX_SOFT_BODY_PIN_COUNT,
            minimum_item_size=header.index_sizes.vertex,
        )
        pinned_vertex_indices: list[int] = []
        for pin_index in range(pinned_vertex_count):
            section = f"soft_bodies[{record_index}].pinned_vertices"
            with reader.context(section, record_index=pin_index):
                pin_offset = reader.offset
                vertex_index = reader.read_index(
                    header.index_sizes.vertex,
                    signed=False,
                    label="soft-body pinned vertex index",
                )
                _validate_index_range(
                    vertex_index,
                    count=vertex_count,
                    section=section,
                    record_index=pin_index,
                    label="soft-body pinned vertex index",
                    offset=pin_offset,
                    allow_sentinel=False,
                )
                pinned_vertex_indices.append(vertex_index)

    return PmxSoftBody(
        local_name=local_name,
        universal_name=universal_name,
        shape=shape,
        shape_name=shape_name,
        material_index=material_index,
        collision_group=collision_group,
        collision_mask=collision_mask,
        flags=flags,
        flag_names=flag_names,
        bending_link_distance=bending_link_distance,
        cluster_count=cluster_count,
        total_mass=total_mass,
        collision_margin=collision_margin,
        config=PmxSoftBodyConfig(
            aerodynamics_model=aerodynamics_model,
            aerodynamics_model_name=aerodynamics_model_name,
            velocity_correction_factor=config_values[0],
            damping_coefficient=config_values[1],
            drag_coefficient=config_values[2],
            lift_coefficient=config_values[3],
            pressure_coefficient=config_values[4],
            volume_conservation_coefficient=config_values[5],
            dynamic_friction_coefficient=config_values[6],
            pose_matching_coefficient=config_values[7],
            rigid_contact_hardness=config_values[8],
            kinetic_contact_hardness=config_values[9],
            soft_contact_hardness=config_values[10],
            anchor_hardness=config_values[11],
        ),
        cluster_config=PmxSoftBodyClusterConfig(
            soft_rigid_hardness=cluster_values[0],
            soft_kinetic_hardness=cluster_values[1],
            soft_soft_hardness=cluster_values[2],
            soft_rigid_impulse_split=cluster_values[3],
            soft_kinetic_impulse_split=cluster_values[4],
            soft_soft_impulse_split=cluster_values[5],
        ),
        iteration_config=PmxSoftBodyIterationConfig(
            velocity=iteration_values[0],
            position=iteration_values[1],
            drift=iteration_values[2],
            cluster=iteration_values[3],
        ),
        material_config=PmxSoftBodyMaterialConfig(
            linear_stiffness=material_values[0],
            area_angular_stiffness=material_values[1],
            volume_stiffness=material_values[2],
        ),
        anchors=anchors,
        pinned_vertex_indices=tuple(pinned_vertex_indices),
    )


def _validate_count_argument(value: object, label: str) -> int:
    """Require one nonnegative, non-boolean prior-section count."""

    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{label} must be an integer.")
    if value < 0:
        raise ValueError(f"{label} cannot be negative.")
    return value


def read_pmx_soft_bodies(
    reader: BinaryReader,
    *,
    header: PmxHeader,
    material_count: int,
    rigid_body_count: int,
    vertex_count: int,
    state: PmxSoftBodyReadState | None = None,
    max_total_anchor_count: int = MAX_PMX_TOTAL_SOFT_BODY_ANCHOR_COUNT,
    max_total_pin_count: int = MAX_PMX_TOTAL_SOFT_BODY_PIN_COUNT,
) -> tuple[PmxSoftBody, ...]:
    """Read the optional complete ordered PMX 2.1 soft-body section."""

    if not isinstance(header, PmxHeader):
        raise TypeError("header must be a PmxHeader instance.")
    material_count = _validate_count_argument(material_count, "material_count")
    rigid_body_count = _validate_count_argument(
        rigid_body_count,
        "rigid_body_count",
    )
    vertex_count = _validate_count_argument(vertex_count, "vertex_count")
    max_total_anchor_count = _validate_count_argument(
        max_total_anchor_count,
        "max_total_anchor_count",
    )
    max_total_pin_count = _validate_count_argument(
        max_total_pin_count,
        "max_total_pin_count",
    )
    read_state = state if state is not None else PmxSoftBodyReadState()

    if header.version == 2.0:
        read_state.soft_body_count = 0
        read_state.soft_bodies = ()
        return ()

    with reader.context("soft_bodies"):
        count_offset = reader.offset
        soft_body_count = reader.read_bounded_count(
            "soft-body count",
            max_count=MAX_PMX_SOFT_BODY_COUNT,
            minimum_item_size=_minimum_soft_body_size(header),
        )

    read_state.soft_body_count = soft_body_count
    soft_bodies: list[PmxSoftBody] = []
    total_anchor_count = 0
    total_pin_count = 0

    for record_index in range(soft_body_count):
        soft_body = _read_soft_body(
            reader,
            header=header,
            material_count=material_count,
            rigid_body_count=rigid_body_count,
            vertex_count=vertex_count,
            record_index=record_index,
        )
        total_anchor_count += len(soft_body.anchors)
        total_pin_count += len(soft_body.pinned_vertex_indices)

        if total_anchor_count > max_total_anchor_count:
            raise_pmx_error(
                section="soft_bodies",
                record_index=record_index,
                offset=count_offset,
                operation="validating total soft-body anchor count",
                reason=(
                    f"soft bodies declare {total_anchor_count} total anchors, "
                    "exceeding the safety limit of "
                    f"{max_total_anchor_count}."
                ),
            )
        if total_pin_count > max_total_pin_count:
            raise_pmx_error(
                section="soft_bodies",
                record_index=record_index,
                offset=count_offset,
                operation="validating total soft-body pinned-vertex count",
                reason=(
                    f"soft bodies declare {total_pin_count} total pinned "
                    "vertices, exceeding the safety limit of "
                    f"{max_total_pin_count}."
                ),
            )
        soft_bodies.append(soft_body)

    records = tuple(soft_bodies)
    read_state.soft_bodies = records
    return records
