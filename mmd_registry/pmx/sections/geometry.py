"""Typed reading for PMX vertices, deforms, and surface indices."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, cast

from mmd_registry.binary_reader import BinaryReader
from mmd_registry.pmx.document import (
    PmxBdef1,
    PmxBdef2,
    PmxBdef4,
    PmxDeform,
    PmxGeometry,
    PmxHeader,
    PmxQdef,
    PmxSdef,
    PmxVector2,
    PmxVector3,
    PmxVector4,
    PmxVertex,
)
from mmd_registry.pmx.errors import raise_pmx_error


MAX_PMX_VERTEX_COUNT: Final[int] = 2_000_000
MAX_PMX_SURFACE_INDEX_COUNT: Final[int] = 12_000_000


@dataclass(slots=True)
class PmxGeometryReadState:
    """Incremental geometry counts for legacy scanner projections."""

    vertex_count: int | None = None
    surface_index_count: int | None = None
    triangle_count: int | None = None


def _read_float_tuple(
    reader: BinaryReader,
    *,
    length: int,
    label: str,
) -> tuple[float, ...]:
    """Read one fixed-size tuple of little-endian float32 values."""

    return tuple(
        reader.read_float32(f"{label} value {index}") for index in range(length)
    )


def _read_bone_indices(
    reader: BinaryReader,
    *,
    count: int,
    bone_index_size: int,
    label: str,
) -> tuple[int, ...]:
    """Read one ordered tuple of signed PMX bone indices."""

    return tuple(
        reader.read_index(
            bone_index_size,
            signed=True,
            label=f"{label} {index}",
        )
        for index in range(count)
    )


def _read_pmx_deform(
    reader: BinaryReader,
    *,
    record_index: int,
    header: PmxHeader,
) -> PmxDeform:
    """Read one version-aware PMX vertex deformation record."""

    deform_offset = reader.offset
    deform_type = reader.read_uint8("vertex deform type")
    bone_index_size = header.index_sizes.bone

    if deform_type == 0:
        return PmxBdef1(
            bone_index=reader.read_index(
                bone_index_size,
                signed=True,
                label="BDEF1 bone index",
            )
        )

    if deform_type == 1:
        bone_indices = cast(
            tuple[int, int],
            _read_bone_indices(
                reader,
                count=2,
                bone_index_size=bone_index_size,
                label="BDEF2 bone index",
            ),
        )
        return PmxBdef2(
            bone_indices=bone_indices,
            bone_1_weight=reader.read_float32("BDEF2 bone weight"),
        )

    if deform_type == 2:
        bone_indices = cast(
            tuple[int, int, int, int],
            _read_bone_indices(
                reader,
                count=4,
                bone_index_size=bone_index_size,
                label="BDEF4 bone index",
            ),
        )
        weights = cast(
            PmxVector4,
            _read_float_tuple(
                reader,
                length=4,
                label="BDEF4 bone weight",
            ),
        )
        return PmxBdef4(
            bone_indices=bone_indices,
            weights=weights,
        )

    if deform_type == 3:
        bone_indices = cast(
            tuple[int, int],
            _read_bone_indices(
                reader,
                count=2,
                bone_index_size=bone_index_size,
                label="SDEF bone index",
            ),
        )
        bone_1_weight = reader.read_float32("SDEF bone weight")
        c = cast(
            PmxVector3,
            _read_float_tuple(
                reader,
                length=3,
                label="SDEF C vector",
            ),
        )
        r0 = cast(
            PmxVector3,
            _read_float_tuple(
                reader,
                length=3,
                label="SDEF R0 vector",
            ),
        )
        r1 = cast(
            PmxVector3,
            _read_float_tuple(
                reader,
                length=3,
                label="SDEF R1 vector",
            ),
        )
        return PmxSdef(
            bone_indices=bone_indices,
            bone_1_weight=bone_1_weight,
            c=c,
            r0=r0,
            r1=r1,
        )

    if deform_type == 4:
        if header.version < 2.1:
            raise_pmx_error(
                section="vertices",
                record_index=record_index,
                offset=deform_offset,
                operation="validating vertex deform type",
                reason="QDEF deform type requires PMX 2.1.",
            )

        bone_indices = cast(
            tuple[int, int, int, int],
            _read_bone_indices(
                reader,
                count=4,
                bone_index_size=bone_index_size,
                label="QDEF bone index",
            ),
        )
        weights = cast(
            PmxVector4,
            _read_float_tuple(
                reader,
                length=4,
                label="QDEF bone weight",
            ),
        )
        return PmxQdef(
            bone_indices=bone_indices,
            weights=weights,
        )

    raise_pmx_error(
        section="vertices",
        record_index=record_index,
        offset=deform_offset,
        operation="validating vertex deform type",
        reason=f"invalid PMX vertex deform type: {deform_type}.",
    )


def _read_pmx_vertex(
    reader: BinaryReader,
    *,
    record_index: int,
    header: PmxHeader,
) -> PmxVertex:
    """Read one complete PMX vertex record."""

    with reader.context(
        "vertices",
        record_index=record_index,
    ):
        position = cast(
            PmxVector3,
            _read_float_tuple(
                reader,
                length=3,
                label="vertex position",
            ),
        )
        normal = cast(
            PmxVector3,
            _read_float_tuple(
                reader,
                length=3,
                label="vertex normal",
            ),
        )
        uv = cast(
            PmxVector2,
            _read_float_tuple(
                reader,
                length=2,
                label="vertex UV",
            ),
        )
        additional_uvs = tuple(
            cast(
                PmxVector4,
                _read_float_tuple(
                    reader,
                    length=4,
                    label=f"vertex additional UV {index}",
                ),
            )
            for index in range(header.additional_uv_count)
        )
        deform = _read_pmx_deform(
            reader,
            record_index=record_index,
            header=header,
        )
        edge_scale = reader.read_float32("vertex edge scale")

    return PmxVertex(
        position=position,
        normal=normal,
        uv=uv,
        additional_uvs=additional_uvs,
        deform=deform,
        edge_scale=edge_scale,
    )


def _minimum_pmx_vertex_size(header: PmxHeader) -> int:
    """Return the smallest possible PMX vertex-record size."""

    fixed_vector_bytes = 32 + (header.additional_uv_count * 16)
    return fixed_vector_bytes + 1 + header.index_sizes.bone + 4


def _read_pmx_vertices(
    reader: BinaryReader,
    *,
    header: PmxHeader,
    state: PmxGeometryReadState,
) -> tuple[PmxVertex, ...]:
    """Read the complete ordered PMX vertex section."""

    with reader.context("vertices"):
        vertex_count = reader.read_bounded_count(
            "vertex count",
            max_count=MAX_PMX_VERTEX_COUNT,
            minimum_item_size=_minimum_pmx_vertex_size(header),
        )

    state.vertex_count = vertex_count
    return tuple(
        _read_pmx_vertex(
            reader,
            record_index=record_index,
            header=header,
        )
        for record_index in range(vertex_count)
    )


def _read_pmx_surface_indices(
    reader: BinaryReader,
    *,
    header: PmxHeader,
    state: PmxGeometryReadState,
) -> tuple[int, ...]:
    """Read the complete ordered PMX triangle-index section."""

    count_offset = reader.offset

    with reader.context("surface_indices"):
        surface_index_count = reader.read_bounded_count(
            "surface index count",
            max_count=MAX_PMX_SURFACE_INDEX_COUNT,
            minimum_item_size=header.index_sizes.vertex,
        )

    if surface_index_count % 3 != 0:
        raise_pmx_error(
            section="surface_indices",
            offset=count_offset,
            operation="validating surface index count",
            reason=(
                f"surface index count {surface_index_count} "
                "must be divisible by 3."
            ),
        )

    state.surface_index_count = surface_index_count
    state.triangle_count = surface_index_count // 3

    with reader.context("surface_indices"):
        return tuple(
            reader.read_index(
                header.index_sizes.vertex,
                signed=False,
                label="surface vertex index",
            )
            for _ in range(surface_index_count)
        )


def read_pmx_geometry(
    reader: BinaryReader,
    *,
    header: PmxHeader,
    state: PmxGeometryReadState | None = None,
) -> PmxGeometry:
    """Read complete PMX vertex and surface-index sections."""

    if not isinstance(header, PmxHeader):
        raise TypeError("header must be a PmxHeader instance.")

    read_state = state if state is not None else PmxGeometryReadState()
    vertices = _read_pmx_vertices(
        reader,
        header=header,
        state=read_state,
    )
    surface_indices = _read_pmx_surface_indices(
        reader,
        header=header,
        state=read_state,
    )
    return PmxGeometry(
        vertices=vertices,
        surface_indices=surface_indices,
    )
