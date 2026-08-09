"""Typed reading for complete PMX morph records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, cast

from mmd_registry.binary_reader import BinaryReader
from mmd_registry.pmx.document import (
    PmxBoneMorphOffset,
    PmxFlipMorphOffset,
    PmxGroupMorphOffset,
    PmxHeader,
    PmxImpulseMorphOffset,
    PmxMaterialMorphOffset,
    PmxMaterialMorphOperation,
    PmxMorph,
    PmxMorphOffset,
    PmxMorphPanel,
    PmxMorphType,
    PmxUvMorphOffset,
    PmxVector3,
    PmxVector4,
    PmxVertexMorphOffset,
)
from mmd_registry.pmx.errors import raise_pmx_error
from mmd_registry.pmx.sections.header import MAX_PMX_NAME_BYTES


MAX_PMX_MORPH_COUNT: Final[int] = 200_000
MAX_PMX_MORPH_OFFSET_COUNT: Final[int] = 2_000_000
MAX_PMX_TOTAL_MORPH_OFFSET_COUNT: Final[int] = 5_000_000


@dataclass(slots=True)
class PmxMorphReadState:
    """Incremental morph data for legacy scanner projections."""

    morph_count: int | None = None
    morphs: tuple[PmxMorph, ...] = ()


def _read_vec3(reader: BinaryReader, label: str) -> PmxVector3:
    """Read one ordered PMX vec3."""

    return (
        reader.read_float32(f"{label} x"),
        reader.read_float32(f"{label} y"),
        reader.read_float32(f"{label} z"),
    )


def _read_vec4(reader: BinaryReader, label: str) -> PmxVector4:
    """Read one ordered PMX vec4."""

    return (
        reader.read_float32(f"{label} x"),
        reader.read_float32(f"{label} y"),
        reader.read_float32(f"{label} z"),
        reader.read_float32(f"{label} w"),
    )


def _decode_morph_panel(
    panel: int,
    *,
    offset: int,
    record_index: int,
) -> tuple[PmxMorphPanel, str]:
    """Validate and decode one PMX morph panel value."""

    panel_names = {
        0: "system",
        1: "eyebrow",
        2: "eye",
        3: "mouth",
        4: "other",
    }

    try:
        panel_name = panel_names[panel]
    except KeyError:
        raise_pmx_error(
            section="morphs",
            record_index=record_index,
            offset=offset,
            operation="validating morph panel",
            reason=f"invalid panel {panel}; expected a value from 0 through 4.",
        )

    return cast(PmxMorphPanel, panel), panel_name


def _decode_morph_type(
    morph_type: int,
    *,
    header: PmxHeader,
    offset: int,
    record_index: int,
) -> tuple[PmxMorphType, str]:
    """Validate and decode one PMX morph type."""

    morph_type_names = {
        0: "group",
        1: "vertex",
        2: "bone",
        3: "uv",
        4: "additional_uv_1",
        5: "additional_uv_2",
        6: "additional_uv_3",
        7: "additional_uv_4",
        8: "material",
        9: "flip",
        10: "impulse",
    }

    if morph_type not in morph_type_names:
        raise_pmx_error(
            section="morphs",
            record_index=record_index,
            offset=offset,
            operation="validating morph type",
            reason=(
                f"invalid morph type {morph_type}; "
                "expected a value from 0 through 10."
            ),
        )

    if morph_type in {9, 10} and header.version < 2.1:
        raise_pmx_error(
            section="morphs",
            record_index=record_index,
            offset=offset,
            operation="validating morph type",
            reason=(
                f"morph type {morph_type} ({morph_type_names[morph_type]}) "
                "requires PMX 2.1."
            ),
        )

    if 4 <= morph_type <= 7:
        required_uv_count = morph_type - 3
        if header.additional_uv_count < required_uv_count:
            raise_pmx_error(
                section="morphs",
                record_index=record_index,
                offset=offset,
                operation="validating additional UV morph type",
                reason=(
                    f"morph type {morph_type} requires additional UV "
                    f"layer {required_uv_count}, but the model declares "
                    f"{header.additional_uv_count} additional UV layers."
                ),
            )

    return cast(PmxMorphType, morph_type), morph_type_names[morph_type]


def _minimum_morph_size() -> int:
    """Return the smallest possible PMX morph-record size."""

    return 8 + 1 + 1 + 4


def _minimum_morph_offset_size(
    morph_type: int,
    *,
    header: PmxHeader,
) -> int:
    """Return the fixed size for one morph offset."""

    index_sizes = header.index_sizes

    if morph_type in {0, 9}:
        return index_sizes.morph + 4
    if morph_type == 1:
        return index_sizes.vertex + 12
    if morph_type == 2:
        return index_sizes.bone + 28
    if 3 <= morph_type <= 7:
        return index_sizes.vertex + 16
    if morph_type == 8:
        return index_sizes.material + 113
    if morph_type == 10:
        return index_sizes.rigid_body + 25

    raise ValueError(f"Unsupported PMX morph type: {morph_type}")


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
    """Validate an index for a PMX section whose count is known."""

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


def _read_group_offset(
    reader: BinaryReader,
    *,
    header: PmxHeader,
    morph_count: int,
    section: str,
    offset_index: int,
) -> PmxGroupMorphOffset:
    """Read one PMX group-morph offset."""

    reference_offset = reader.offset
    morph_index = reader.read_index(
        header.index_sizes.morph,
        signed=True,
        label="group morph index",
    )
    _validate_index_range(
        morph_index,
        count=morph_count,
        section=section,
        record_index=offset_index,
        label="group morph index",
        offset=reference_offset,
        allow_sentinel=False,
    )
    return PmxGroupMorphOffset(
        morph_index=morph_index,
        weight=reader.read_float32("group morph weight"),
    )


def _read_vertex_offset(
    reader: BinaryReader,
    *,
    header: PmxHeader,
    vertex_count: int,
    section: str,
    offset_index: int,
) -> PmxVertexMorphOffset:
    """Read one PMX vertex-morph offset."""

    reference_offset = reader.offset
    vertex_index = reader.read_index(
        header.index_sizes.vertex,
        signed=False,
        label="vertex morph vertex index",
    )
    _validate_index_range(
        vertex_index,
        count=vertex_count,
        section=section,
        record_index=offset_index,
        label="vertex morph vertex index",
        offset=reference_offset,
        allow_sentinel=False,
    )
    return PmxVertexMorphOffset(
        vertex_index=vertex_index,
        translation=_read_vec3(reader, "vertex morph translation"),
    )


def _read_bone_offset(
    reader: BinaryReader,
    *,
    header: PmxHeader,
    bone_count: int,
    section: str,
    offset_index: int,
) -> PmxBoneMorphOffset:
    """Read one PMX bone-morph offset."""

    reference_offset = reader.offset
    bone_index = reader.read_index(
        header.index_sizes.bone,
        signed=True,
        label="bone morph bone index",
    )
    _validate_index_range(
        bone_index,
        count=bone_count,
        section=section,
        record_index=offset_index,
        label="bone morph bone index",
        offset=reference_offset,
        allow_sentinel=False,
    )
    return PmxBoneMorphOffset(
        bone_index=bone_index,
        translation=_read_vec3(reader, "bone morph translation"),
        rotation=_read_vec4(reader, "bone morph rotation"),
    )


def _read_uv_offset(
    reader: BinaryReader,
    *,
    header: PmxHeader,
    vertex_count: int,
    section: str,
    offset_index: int,
) -> PmxUvMorphOffset:
    """Read one base-UV or additional-UV morph offset."""

    reference_offset = reader.offset
    vertex_index = reader.read_index(
        header.index_sizes.vertex,
        signed=False,
        label="UV morph vertex index",
    )
    _validate_index_range(
        vertex_index,
        count=vertex_count,
        section=section,
        record_index=offset_index,
        label="UV morph vertex index",
        offset=reference_offset,
        allow_sentinel=False,
    )
    return PmxUvMorphOffset(
        vertex_index=vertex_index,
        uv_offset=_read_vec4(reader, "UV morph offset"),
    )


def _read_material_offset(
    reader: BinaryReader,
    *,
    header: PmxHeader,
    material_count: int,
    section: str,
    offset_index: int,
) -> PmxMaterialMorphOffset:
    """Read one PMX material-morph offset."""

    reference_offset = reader.offset
    material_index = reader.read_index(
        header.index_sizes.material,
        signed=True,
        label="material morph material index",
    )
    _validate_index_range(
        material_index,
        count=material_count,
        section=section,
        record_index=offset_index,
        label="material morph material index",
        offset=reference_offset,
        allow_sentinel=True,
    )

    operation_offset = reader.offset
    operation_value = reader.read_uint8("material morph operation")
    if operation_value == 0:
        operation: PmxMaterialMorphOperation = "multiply"
    elif operation_value == 1:
        operation = "add"
    else:
        raise_pmx_error(
            section=section,
            record_index=offset_index,
            offset=operation_offset,
            operation="validating material morph operation",
            reason=f"invalid operation {operation_value}; expected 0 or 1.",
        )

    return PmxMaterialMorphOffset(
        material_index=material_index,
        operation=operation,
        diffuse=_read_vec4(reader, "material morph diffuse"),
        specular=_read_vec3(reader, "material morph specular"),
        specular_strength=reader.read_float32("material morph specular strength"),
        ambient=_read_vec3(reader, "material morph ambient"),
        edge_color=_read_vec4(reader, "material morph edge color"),
        edge_scale=reader.read_float32("material morph edge scale"),
        texture_tint=_read_vec4(reader, "material morph texture tint"),
        sphere_tint=_read_vec4(reader, "material morph sphere tint"),
        toon_tint=_read_vec4(reader, "material morph toon tint"),
    )


def _read_flip_offset(
    reader: BinaryReader,
    *,
    header: PmxHeader,
    morph_count: int,
    section: str,
    offset_index: int,
) -> PmxFlipMorphOffset:
    """Read one PMX 2.1 flip-morph offset."""

    reference_offset = reader.offset
    morph_index = reader.read_index(
        header.index_sizes.morph,
        signed=True,
        label="flip morph index",
    )
    _validate_index_range(
        morph_index,
        count=morph_count,
        section=section,
        record_index=offset_index,
        label="flip morph index",
        offset=reference_offset,
        allow_sentinel=False,
    )
    return PmxFlipMorphOffset(
        morph_index=morph_index,
        weight=reader.read_float32("flip morph weight"),
    )


def _read_impulse_offset(
    reader: BinaryReader,
    *,
    header: PmxHeader,
    section: str,
    offset_index: int,
) -> PmxImpulseMorphOffset:
    """Read one PMX 2.1 rigid-body impulse morph record."""

    reference_offset = reader.offset
    rigid_body_index = reader.read_index(
        header.index_sizes.rigid_body,
        signed=True,
        label="impulse morph rigid-body index",
    )
    if rigid_body_index < 0:
        raise_pmx_error(
            section=section,
            record_index=offset_index,
            offset=reference_offset,
            operation="validating impulse morph rigid-body index",
            reason=f"index {rigid_body_index} cannot be negative.",
        )

    local_flag_offset = reader.offset
    local_flag = reader.read_uint8("impulse morph local flag")
    if local_flag not in {0, 1}:
        raise_pmx_error(
            section=section,
            record_index=offset_index,
            offset=local_flag_offset,
            operation="validating impulse morph local flag",
            reason=f"invalid flag {local_flag}; expected 0 or 1.",
        )

    return PmxImpulseMorphOffset(
        rigid_body_index=rigid_body_index,
        local=bool(local_flag),
        velocity=_read_vec3(reader, "impulse morph velocity"),
        angular_torque=_read_vec3(reader, "impulse morph angular torque"),
    )


def _read_morph_offset(
    reader: BinaryReader,
    *,
    header: PmxHeader,
    morph_type: PmxMorphType,
    vertex_count: int,
    bone_count: int,
    material_count: int,
    morph_count: int,
    morph_record_index: int,
    offset_index: int,
) -> PmxMorphOffset:
    """Read one type-specific PMX morph offset."""

    section = f"morphs[{morph_record_index}].offsets"

    with reader.context(section, record_index=offset_index):
        if morph_type == 0:
            return _read_group_offset(
                reader,
                header=header,
                morph_count=morph_count,
                section=section,
                offset_index=offset_index,
            )
        if morph_type == 1:
            return _read_vertex_offset(
                reader,
                header=header,
                vertex_count=vertex_count,
                section=section,
                offset_index=offset_index,
            )
        if morph_type == 2:
            return _read_bone_offset(
                reader,
                header=header,
                bone_count=bone_count,
                section=section,
                offset_index=offset_index,
            )
        if 3 <= morph_type <= 7:
            return _read_uv_offset(
                reader,
                header=header,
                vertex_count=vertex_count,
                section=section,
                offset_index=offset_index,
            )
        if morph_type == 8:
            return _read_material_offset(
                reader,
                header=header,
                material_count=material_count,
                section=section,
                offset_index=offset_index,
            )
        if morph_type == 9:
            return _read_flip_offset(
                reader,
                header=header,
                morph_count=morph_count,
                section=section,
                offset_index=offset_index,
            )
        if morph_type == 10:
            return _read_impulse_offset(
                reader,
                header=header,
                section=section,
                offset_index=offset_index,
            )

    raise AssertionError(f"Unhandled PMX morph type: {morph_type}")


def _read_morph(
    reader: BinaryReader,
    *,
    header: PmxHeader,
    vertex_count: int,
    bone_count: int,
    material_count: int,
    morph_count: int,
    record_index: int,
) -> PmxMorph:
    """Read one PMX morph and its bounded offset records."""

    require_even_length = header.encoding == "utf-16-le"

    with reader.context("morphs", record_index=record_index):
        local_name = reader.read_length_prefixed_text(
            "local morph name",
            encoding=header.encoding,
            max_length=MAX_PMX_NAME_BYTES,
            require_even_length=require_even_length,
        )
        universal_name = reader.read_length_prefixed_text(
            "universal morph name",
            encoding=header.encoding,
            max_length=MAX_PMX_NAME_BYTES,
            require_even_length=require_even_length,
        )

        panel_offset = reader.offset
        panel, panel_name = _decode_morph_panel(
            reader.read_uint8("morph panel"),
            offset=panel_offset,
            record_index=record_index,
        )

        type_offset = reader.offset
        morph_type, morph_type_name = _decode_morph_type(
            reader.read_uint8("morph type"),
            header=header,
            offset=type_offset,
            record_index=record_index,
        )

        offset_count = reader.read_bounded_count(
            "morph offset count",
            max_count=MAX_PMX_MORPH_OFFSET_COUNT,
            minimum_item_size=_minimum_morph_offset_size(
                morph_type,
                header=header,
            ),
        )

    offsets = tuple(
        _read_morph_offset(
            reader,
            header=header,
            morph_type=morph_type,
            vertex_count=vertex_count,
            bone_count=bone_count,
            material_count=material_count,
            morph_count=morph_count,
            morph_record_index=record_index,
            offset_index=offset_index,
        )
        for offset_index in range(offset_count)
    )

    return PmxMorph(
        local_name=local_name,
        universal_name=universal_name,
        panel=panel,
        panel_name=panel_name,
        morph_type=morph_type,
        morph_type_name=morph_type_name,
        offsets=offsets,
    )


def _validate_count_argument(value: object, label: str) -> int:
    """Require one nonnegative, non-boolean prior-section count."""

    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{label} must be an integer.")
    if value < 0:
        raise ValueError(f"{label} cannot be negative.")
    return value


def read_pmx_morphs(
    reader: BinaryReader,
    *,
    header: PmxHeader,
    vertex_count: int,
    bone_count: int,
    material_count: int,
    state: PmxMorphReadState | None = None,
    max_total_offset_count: int = MAX_PMX_TOTAL_MORPH_OFFSET_COUNT,
) -> tuple[PmxMorph, ...]:
    """Read the complete ordered PMX morph section."""

    if not isinstance(header, PmxHeader):
        raise TypeError("header must be a PmxHeader instance.")

    vertex_count = _validate_count_argument(vertex_count, "vertex_count")
    bone_count = _validate_count_argument(bone_count, "bone_count")
    material_count = _validate_count_argument(material_count, "material_count")
    max_total_offset_count = _validate_count_argument(
        max_total_offset_count,
        "max_total_offset_count",
    )
    read_state = state if state is not None else PmxMorphReadState()

    with reader.context("morphs"):
        morph_count = reader.read_bounded_count(
            "morph count",
            max_count=MAX_PMX_MORPH_COUNT,
            minimum_item_size=_minimum_morph_size(),
        )

    read_state.morph_count = morph_count
    morphs: list[PmxMorph] = []
    total_offset_count = 0

    for record_index in range(morph_count):
        morph = _read_morph(
            reader,
            header=header,
            vertex_count=vertex_count,
            bone_count=bone_count,
            material_count=material_count,
            morph_count=morph_count,
            record_index=record_index,
        )
        morphs.append(morph)
        total_offset_count += len(morph.offsets)

        if total_offset_count > max_total_offset_count:
            raise_pmx_error(
                section="morphs",
                record_index=record_index,
                offset=reader.offset,
                operation="validating total morph offset count",
                reason=(
                    f"cumulative morph offset count {total_offset_count} "
                    f"exceeds the safety limit of {max_total_offset_count}."
                ),
            )

    morph_records = tuple(morphs)
    read_state.morphs = morph_records
    return morph_records
