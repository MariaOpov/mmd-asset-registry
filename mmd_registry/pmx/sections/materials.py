"""Typed reading for complete PMX material records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, cast

from mmd_registry.binary_reader import BinaryReader
from mmd_registry.pmx.document import (
    PmxHeader,
    PmxMaterial,
    PmxSphereMode,
    PmxToonReferenceMode,
    PmxVector3,
    PmxVector4,
)
from mmd_registry.pmx.errors import raise_pmx_error
from mmd_registry.pmx.sections.geometry import MAX_PMX_SURFACE_INDEX_COUNT
from mmd_registry.pmx.sections.header import MAX_PMX_NAME_BYTES


MAX_PMX_MATERIAL_COUNT: Final[int] = 100_000
MAX_PMX_MATERIAL_MEMO_BYTES: Final[int] = 1024 * 1024


@dataclass(slots=True)
class PmxMaterialReadState:
    """Incremental material data for legacy scanner projections."""

    material_count: int | None = None
    materials: tuple[PmxMaterial, ...] = ()


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


def _minimum_pmx_material_size(header: PmxHeader) -> int:
    """Return the smallest possible PMX material-record size."""

    text_length_fields = 8
    shading_and_edge_fields = 65
    texture_indices = header.index_sizes.texture * 2
    sphere_and_toon_fields = 3
    memo_length_field = 4
    surface_count_field = 4

    return (
        text_length_fields
        + shading_and_edge_fields
        + texture_indices
        + sphere_and_toon_fields
        + memo_length_field
        + surface_count_field
    )


def _validate_material_texture_index(
    value: int,
    *,
    texture_count: int,
    record_index: int,
    label: str,
    offset: int,
) -> None:
    """Validate a material texture index, permitting the -1 sentinel."""

    if value < -1 or value >= texture_count:
        if texture_count == 0:
            expected = "expected only -1 because no textures are declared"
        else:
            expected = f"expected -1 or a value from 0 through {texture_count - 1}"

        raise_pmx_error(
            section="materials",
            record_index=record_index,
            offset=offset,
            operation=f"validating {label}",
            reason=(
                f"index {value} is invalid for texture count "
                f"{texture_count}; {expected}."
            ),
        )


def _read_pmx_material(
    reader: BinaryReader,
    *,
    record_index: int,
    header: PmxHeader,
    texture_count: int,
) -> PmxMaterial:
    """Read one complete PMX material record."""

    require_even_length = header.encoding == "utf-16-le"
    texture_index_size = header.index_sizes.texture

    with reader.context(
        "materials",
        record_index=record_index,
    ):
        local_name = reader.read_length_prefixed_text(
            "local material name",
            encoding=header.encoding,
            max_length=MAX_PMX_NAME_BYTES,
            require_even_length=require_even_length,
        )
        universal_name = reader.read_length_prefixed_text(
            "universal material name",
            encoding=header.encoding,
            max_length=MAX_PMX_NAME_BYTES,
            require_even_length=require_even_length,
        )
        diffuse = cast(
            PmxVector4,
            _read_float_tuple(
                reader,
                length=4,
                label="material diffuse color",
            ),
        )
        specular = cast(
            PmxVector3,
            _read_float_tuple(
                reader,
                length=3,
                label="material specular color",
            ),
        )
        specular_strength = reader.read_float32("material specular strength")
        ambient = cast(
            PmxVector3,
            _read_float_tuple(
                reader,
                length=3,
                label="material ambient color",
            ),
        )
        drawing_flags = reader.read_uint8("material drawing flags")
        edge_color = cast(
            PmxVector4,
            _read_float_tuple(
                reader,
                length=4,
                label="material edge color",
            ),
        )
        edge_scale = reader.read_float32("material edge scale")

        texture_index_offset = reader.offset
        texture_index = reader.read_index(
            texture_index_size,
            signed=True,
            label="material texture index",
        )
        _validate_material_texture_index(
            texture_index,
            texture_count=texture_count,
            record_index=record_index,
            label="material texture index",
            offset=texture_index_offset,
        )

        sphere_texture_index_offset = reader.offset
        sphere_texture_index = reader.read_index(
            texture_index_size,
            signed=True,
            label="material sphere texture index",
        )
        _validate_material_texture_index(
            sphere_texture_index,
            texture_count=texture_count,
            record_index=record_index,
            label="material sphere texture index",
            offset=sphere_texture_index_offset,
        )

        sphere_mode_offset = reader.offset
        sphere_mode_value = reader.read_uint8("material sphere mode")

        if sphere_mode_value > 3:
            raise_pmx_error(
                section="materials",
                record_index=record_index,
                offset=sphere_mode_offset,
                operation="validating material sphere mode",
                reason=(
                    f"invalid sphere mode {sphere_mode_value}; "
                    "expected a value from 0 through 3."
                ),
            )

        sphere_mode = cast(PmxSphereMode, sphere_mode_value)
        toon_mode_offset = reader.offset
        toon_mode = reader.read_uint8("material toon reference mode")

        if toon_mode == 0:
            toon_reference_mode: PmxToonReferenceMode = "texture"
            toon_reference_offset = reader.offset
            toon_reference_index = reader.read_index(
                texture_index_size,
                signed=True,
                label="material toon texture index",
            )
            _validate_material_texture_index(
                toon_reference_index,
                texture_count=texture_count,
                record_index=record_index,
                label="material toon texture index",
                offset=toon_reference_offset,
            )
        elif toon_mode == 1:
            toon_reference_mode = "shared"
            toon_reference_offset = reader.offset
            toon_reference_index = reader.read_uint8("material shared toon index")

            if toon_reference_index > 9:
                raise_pmx_error(
                    section="materials",
                    record_index=record_index,
                    offset=toon_reference_offset,
                    operation="validating shared toon index",
                    reason=(
                        f"invalid shared toon index {toon_reference_index}; "
                        "expected a value from 0 through 9."
                    ),
                )
        else:
            raise_pmx_error(
                section="materials",
                record_index=record_index,
                offset=toon_mode_offset,
                operation="validating material toon reference mode",
                reason=f"invalid toon reference mode {toon_mode}; expected 0 or 1.",
            )

        memo = reader.read_length_prefixed_text(
            "material memo",
            encoding=header.encoding,
            max_length=MAX_PMX_MATERIAL_MEMO_BYTES,
            require_even_length=require_even_length,
        )
        surface_count_offset = reader.offset
        material_surface_index_count = reader.read_bounded_count(
            "material surface index count",
            max_count=MAX_PMX_SURFACE_INDEX_COUNT,
        )

        if material_surface_index_count % 3 != 0:
            raise_pmx_error(
                section="materials",
                record_index=record_index,
                offset=surface_count_offset,
                operation="validating material surface index count",
                reason=(
                    f"surface index count {material_surface_index_count} "
                    "must be divisible by 3."
                ),
            )

    return PmxMaterial(
        local_name=local_name,
        universal_name=universal_name,
        diffuse=diffuse,
        specular=specular,
        specular_strength=specular_strength,
        ambient=ambient,
        drawing_flags=drawing_flags,
        edge_color=edge_color,
        edge_scale=edge_scale,
        texture_index=texture_index,
        sphere_texture_index=sphere_texture_index,
        sphere_mode=sphere_mode,
        toon_reference_mode=toon_reference_mode,
        toon_reference_index=toon_reference_index,
        memo=memo,
        surface_index_count=material_surface_index_count,
    )


def read_pmx_materials(
    reader: BinaryReader,
    *,
    header: PmxHeader,
    texture_count: int,
    surface_index_count: int,
    state: PmxMaterialReadState | None = None,
) -> tuple[PmxMaterial, ...]:
    """Read all PMX materials and validate their surface coverage."""

    if not isinstance(header, PmxHeader):
        raise TypeError("header must be a PmxHeader instance.")

    for value, field_name in (
        (texture_count, "texture_count"),
        (surface_index_count, "surface_index_count"),
    ):
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError(f"{field_name} must be an integer.")

        if value < 0:
            raise ValueError(f"{field_name} cannot be negative.")

    read_state = state if state is not None else PmxMaterialReadState()
    count_offset = reader.offset

    with reader.context("materials"):
        material_count = reader.read_bounded_count(
            "material count",
            max_count=MAX_PMX_MATERIAL_COUNT,
            minimum_item_size=_minimum_pmx_material_size(header),
        )

    read_state.material_count = material_count
    materials: list[PmxMaterial] = []
    total_surface_indices = 0

    for record_index in range(material_count):
        material = _read_pmx_material(
            reader,
            record_index=record_index,
            header=header,
            texture_count=texture_count,
        )
        materials.append(material)
        total_surface_indices += material.surface_index_count

        if total_surface_indices > surface_index_count:
            raise_pmx_error(
                section="materials",
                record_index=record_index,
                offset=reader.offset,
                operation="validating material surface coverage",
                reason=(
                    f"cumulative material surface index count "
                    f"{total_surface_indices} exceeds model surface "
                    f"index count {surface_index_count}."
                ),
            )

    material_records = tuple(materials)
    read_state.materials = material_records

    if total_surface_indices != surface_index_count:
        raise_pmx_error(
            section="materials",
            offset=count_offset,
            operation="validating material surface coverage",
            reason=(
                f"materials cover {total_surface_indices} surface indices, "
                f"but the model declares {surface_index_count}."
            ),
        )

    return material_records
