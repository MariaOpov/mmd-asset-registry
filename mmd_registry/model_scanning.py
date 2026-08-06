"""Safe structural metadata scanning for PMX and PMD model files."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Literal

from mmd_registry.binary_reader import (
    BinaryParseError,
    BinaryReader,
    VALID_INDEX_SIZES,
)


PMX_MAGIC: Final[bytes] = b"PMX "

SUPPORTED_PMX_VERSIONS: Final[tuple[float, ...]] = (
    2.0,
    2.1,
)

MIN_PMX_GLOBAL_COUNT: Final[int] = 8
MAX_PMX_GLOBAL_COUNT: Final[int] = 64

MAX_PMX_NAME_BYTES: Final[int] = 64 * 1024
MAX_PMX_COMMENT_BYTES: Final[int] = 1024 * 1024
MAX_PMX_VERTEX_COUNT: Final[int] = 2_000_000
MAX_PMX_SURFACE_INDEX_COUNT: Final[int] = 12_000_000
MAX_PMX_TEXTURE_COUNT: Final[int] = 100_000
MAX_PMX_TEXTURE_PATH_BYTES: Final[int] = 64 * 1024
MAX_PMX_MATERIAL_COUNT: Final[int] = 100_000
MAX_PMX_MATERIAL_MEMO_BYTES: Final[int] = 1024 * 1024
MAX_PMX_BONE_COUNT: Final[int] = 200_000
MAX_PMX_IK_LOOP_COUNT: Final[int] = 1_000_000
MAX_PMX_IK_LINK_COUNT: Final[int] = 100_000
MAX_PMX_TOTAL_IK_LINK_COUNT: Final[int] = 1_000_000
MAX_PMX_MORPH_COUNT: Final[int] = 200_000
MAX_PMX_MORPH_OFFSET_COUNT: Final[int] = 2_000_000
MAX_PMX_TOTAL_MORPH_OFFSET_COUNT: Final[int] = 5_000_000

PMX_BONE_FLAG_TAIL_INDEX: Final[int] = 0x0001
PMX_BONE_FLAG_ROTATABLE: Final[int] = 0x0002
PMX_BONE_FLAG_TRANSLATABLE: Final[int] = 0x0004
PMX_BONE_FLAG_VISIBLE: Final[int] = 0x0008
PMX_BONE_FLAG_ENABLED: Final[int] = 0x0010
PMX_BONE_FLAG_IK: Final[int] = 0x0020
PMX_BONE_FLAG_LOCAL_APPEND: Final[int] = 0x0080
PMX_BONE_FLAG_INHERIT_ROTATION: Final[int] = 0x0100
PMX_BONE_FLAG_INHERIT_TRANSLATION: Final[int] = 0x0200
PMX_BONE_FLAG_FIXED_AXIS: Final[int] = 0x0400
PMX_BONE_FLAG_LOCAL_AXES: Final[int] = 0x0800
PMX_BONE_FLAG_AFTER_PHYSICS: Final[int] = 0x1000
PMX_BONE_FLAG_EXTERNAL_PARENT: Final[int] = 0x2000

ScanStatus = Literal["ok", "warning", "error"]


@dataclass(frozen=True, slots=True)
class PmxIndexSizes:
    """Index widths declared by the PMX global settings."""

    vertex: int
    texture: int
    material: int
    bone: int
    morph: int
    rigid_body: int

    def to_dict(self) -> dict[str, int]:
        """Return a JSON-serializable representation."""

        return {
            "vertex": self.vertex,
            "texture": self.texture,
            "material": self.material,
            "bone": self.bone,
            "morph": self.morph,
            "rigid_body": self.rigid_body,
        }


@dataclass(frozen=True, slots=True)
class PmxModelInfo:
    """The four length-prefixed text fields in PMX model information."""

    local_name: str
    universal_name: str
    local_comments: str
    universal_comments: str

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-serializable representation."""

        return {
            "local_name": self.local_name,
            "universal_name": self.universal_name,
            "local_comments": self.local_comments,
            "universal_comments": self.universal_comments,
        }


@dataclass(frozen=True, slots=True)
class PmxMaterial:
    """Structural metadata extracted from one PMX material record."""

    local_name: str
    universal_name: str
    texture_index: int
    sphere_texture_index: int
    sphere_mode: int
    toon_reference_mode: Literal["texture", "shared"]
    toon_reference_index: int
    memo: str
    surface_index_count: int

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "local_name": self.local_name,
            "universal_name": self.universal_name,
            "texture_index": self.texture_index,
            "sphere_texture_index": self.sphere_texture_index,
            "sphere_mode": self.sphere_mode,
            "toon_reference_mode": self.toon_reference_mode,
            "toon_reference_index": self.toon_reference_index,
            "memo": self.memo,
            "surface_index_count": self.surface_index_count,
        }


@dataclass(frozen=True, slots=True)
class PmxIkLink:
    """Structural metadata for one PMX inverse-kinematics link."""

    bone_index: int
    angle_limits_enabled: bool
    lower_limit: tuple[float, float, float] | None
    upper_limit: tuple[float, float, float] | None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "bone_index": self.bone_index,
            "angle_limits_enabled": self.angle_limits_enabled,
            "lower_limit": (
                list(self.lower_limit) if self.lower_limit is not None else None
            ),
            "upper_limit": (
                list(self.upper_limit) if self.upper_limit is not None else None
            ),
        }


@dataclass(frozen=True, slots=True)
class PmxIk:
    """Structural metadata for one PMX bone IK definition."""

    target_bone_index: int
    loop_count: int
    angle_limit: float
    links: tuple[PmxIkLink, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "target_bone_index": self.target_bone_index,
            "loop_count": self.loop_count,
            "angle_limit": self.angle_limit,
            "link_count": len(self.links),
            "links": [link.to_dict() for link in self.links],
        }


@dataclass(frozen=True, slots=True)
class PmxBone:
    """Structural metadata extracted from one PMX bone record."""

    local_name: str
    universal_name: str
    position: tuple[float, float, float]
    parent_bone_index: int
    transform_layer: int
    flags: int
    flag_names: tuple[str, ...]
    tail_mode: Literal["bone", "offset"]
    tail_bone_index: int | None
    tail_offset: tuple[float, float, float] | None
    inherit_parent_bone_index: int | None
    inherit_weight: float | None
    fixed_axis: tuple[float, float, float] | None
    local_axis_x: tuple[float, float, float] | None
    local_axis_z: tuple[float, float, float] | None
    external_parent_key: int | None
    ik: PmxIk | None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "local_name": self.local_name,
            "universal_name": self.universal_name,
            "position": list(self.position),
            "parent_bone_index": self.parent_bone_index,
            "transform_layer": self.transform_layer,
            "flags": self.flags,
            "flag_names": list(self.flag_names),
            "tail_mode": self.tail_mode,
            "tail_bone_index": self.tail_bone_index,
            "tail_offset": (
                list(self.tail_offset) if self.tail_offset is not None else None
            ),
            "inherit_parent_bone_index": (self.inherit_parent_bone_index),
            "inherit_weight": self.inherit_weight,
            "fixed_axis": (
                list(self.fixed_axis) if self.fixed_axis is not None else None
            ),
            "local_axis_x": (
                list(self.local_axis_x) if self.local_axis_x is not None else None
            ),
            "local_axis_z": (
                list(self.local_axis_z) if self.local_axis_z is not None else None
            ),
            "external_parent_key": self.external_parent_key,
            "ik": (self.ik.to_dict() if self.ik is not None else None),
        }


@dataclass(frozen=True, slots=True)
class PmxGroupMorphOffset:
    """One group-morph reference and influence weight."""

    morph_index: int
    weight: float

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "morph_index": self.morph_index,
            "weight": self.weight,
        }


@dataclass(frozen=True, slots=True)
class PmxVertexMorphOffset:
    """One vertex-morph displacement."""

    vertex_index: int
    translation: tuple[float, float, float]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "vertex_index": self.vertex_index,
            "translation": list(self.translation),
        }


@dataclass(frozen=True, slots=True)
class PmxBoneMorphOffset:
    """One bone-morph translation and quaternion rotation."""

    bone_index: int
    translation: tuple[float, float, float]
    rotation: tuple[float, float, float, float]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "bone_index": self.bone_index,
            "translation": list(self.translation),
            "rotation": list(self.rotation),
        }


@dataclass(frozen=True, slots=True)
class PmxUvMorphOffset:
    """One base-UV or additional-UV morph displacement."""

    vertex_index: int
    uv_offset: tuple[float, float, float, float]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "vertex_index": self.vertex_index,
            "uv_offset": list(self.uv_offset),
        }


@dataclass(frozen=True, slots=True)
class PmxMaterialMorphOffset:
    """One material-morph operation and its color/scalar values."""

    material_index: int
    operation: Literal["multiply", "add"]
    diffuse: tuple[float, float, float, float]
    specular: tuple[float, float, float]
    specular_strength: float
    ambient: tuple[float, float, float]
    edge_color: tuple[float, float, float, float]
    edge_scale: float
    texture_tint: tuple[float, float, float, float]
    sphere_tint: tuple[float, float, float, float]
    toon_tint: tuple[float, float, float, float]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "material_index": self.material_index,
            "operation": self.operation,
            "diffuse": list(self.diffuse),
            "specular": list(self.specular),
            "specular_strength": self.specular_strength,
            "ambient": list(self.ambient),
            "edge_color": list(self.edge_color),
            "edge_scale": self.edge_scale,
            "texture_tint": list(self.texture_tint),
            "sphere_tint": list(self.sphere_tint),
            "toon_tint": list(self.toon_tint),
        }


@dataclass(frozen=True, slots=True)
class PmxFlipMorphOffset:
    """One PMX 2.1 flip-morph reference and influence weight."""

    morph_index: int
    weight: float

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "morph_index": self.morph_index,
            "weight": self.weight,
        }


@dataclass(frozen=True, slots=True)
class PmxImpulseMorphOffset:
    """One PMX 2.1 rigid-body impulse morph record."""

    rigid_body_index: int
    local: bool
    velocity: tuple[float, float, float]
    angular_torque: tuple[float, float, float]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "rigid_body_index": self.rigid_body_index,
            "local": self.local,
            "velocity": list(self.velocity),
            "angular_torque": list(self.angular_torque),
        }


PmxMorphOffset = (
    PmxGroupMorphOffset
    | PmxVertexMorphOffset
    | PmxBoneMorphOffset
    | PmxUvMorphOffset
    | PmxMaterialMorphOffset
    | PmxFlipMorphOffset
    | PmxImpulseMorphOffset
)


@dataclass(frozen=True, slots=True)
class PmxMorph:
    """Structural metadata extracted from one PMX morph record."""

    local_name: str
    universal_name: str
    panel: int
    panel_name: str
    morph_type: int
    morph_type_name: str
    offsets: tuple[PmxMorphOffset, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "local_name": self.local_name,
            "universal_name": self.universal_name,
            "panel": self.panel,
            "panel_name": self.panel_name,
            "morph_type": self.morph_type,
            "morph_type_name": self.morph_type_name,
            "offset_count": len(self.offsets),
            "offsets": [offset.to_dict() for offset in self.offsets],
        }


@dataclass(slots=True)
class PmxHeaderScanResult:
    """Result of scanning PMX header, model information, and early sections."""

    detected_format: Literal["pmx"] | None = None
    magic: str | None = None
    version: float | None = None
    encoding: str | None = None
    global_count: int | None = None
    additional_uv_count: int | None = None
    index_sizes: PmxIndexSizes | None = None
    model_info: PmxModelInfo | None = None
    vertex_count: int | None = None
    surface_index_count: int | None = None
    triangle_count: int | None = None
    texture_count: int | None = None
    texture_paths: list[str] = field(default_factory=list)
    material_count: int | None = None
    materials: list[PmxMaterial] = field(default_factory=list)
    bone_count: int | None = None
    bones: list[PmxBone] = field(default_factory=list)
    morph_count: int | None = None
    morphs: list[PmxMorph] = field(default_factory=list)
    file_size: int | None = None
    bytes_consumed: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def status(self) -> ScanStatus:
        """Return the overall scan status."""

        if self.errors:
            return "error"

        if self.warnings:
            return "warning"

        return "ok"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "status": self.status,
            "detected_format": self.detected_format,
            "magic": self.magic,
            "version": self.version,
            "encoding": self.encoding,
            "global_count": self.global_count,
            "additional_uv_count": self.additional_uv_count,
            "index_sizes": (
                self.index_sizes.to_dict() if self.index_sizes is not None else None
            ),
            "model_info": (
                self.model_info.to_dict() if self.model_info is not None else None
            ),
            "vertex_count": self.vertex_count,
            "surface_index_count": self.surface_index_count,
            "triangle_count": self.triangle_count,
            "texture_count": self.texture_count,
            "texture_paths": list(self.texture_paths),
            "material_count": self.material_count,
            "materials": [material.to_dict() for material in self.materials],
            "bone_count": self.bone_count,
            "bones": [bone.to_dict() for bone in self.bones],
            "morph_count": self.morph_count,
            "morphs": [morph.to_dict() for morph in self.morphs],
            "file_size": self.file_size,
            "bytes_consumed": self.bytes_consumed,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def _raise_pmx_error(
    *,
    section: str,
    offset: int,
    operation: str,
    reason: str,
    record_index: int | None = None,
) -> None:
    """Raise one contextual PMX parse error."""

    raise BinaryParseError(
        format_name="PMX",
        section=section,
        record_index=record_index,
        offset=offset,
        operation=operation,
        reason=reason,
    )


def _normalize_pmx_version(
    raw_version: float,
    *,
    offset: int,
) -> float:
    """Validate and normalize a supported PMX float version."""

    if not math.isfinite(raw_version):
        _raise_pmx_error(
            section="header",
            offset=offset,
            operation="validating PMX version",
            reason="version must be a finite floating-point number.",
        )

    for supported_version in SUPPORTED_PMX_VERSIONS:
        if math.isclose(
            raw_version,
            supported_version,
            rel_tol=0.0,
            abs_tol=1e-4,
        ):
            return supported_version

    _raise_pmx_error(
        section="header",
        offset=offset,
        operation="validating PMX version",
        reason=f"unsupported PMX version: {raw_version:.6g}.",
    )


def _validate_global_count(
    global_count: int,
    *,
    offset: int,
) -> None:
    """Validate the PMX global-settings byte count."""

    if global_count < MIN_PMX_GLOBAL_COUNT:
        _raise_pmx_error(
            section="header",
            offset=offset,
            operation="validating PMX global count",
            reason=(
                f"value {global_count} is smaller than the required "
                f"minimum of {MIN_PMX_GLOBAL_COUNT}."
            ),
        )

    if global_count > MAX_PMX_GLOBAL_COUNT:
        _raise_pmx_error(
            section="header",
            offset=offset,
            operation="validating PMX global count",
            reason=(
                f"value {global_count} exceeds the safety limit "
                f"of {MAX_PMX_GLOBAL_COUNT}."
            ),
        )


def _decode_encoding_flag(
    encoding_flag: int,
    *,
    offset: int,
) -> str:
    """Return the Python codec selected by a PMX encoding flag."""

    if encoding_flag == 0:
        return "utf-16-le"

    if encoding_flag == 1:
        return "utf-8"

    _raise_pmx_error(
        section="header",
        offset=offset,
        operation="validating PMX text encoding",
        reason=f"invalid PMX text-encoding flag: {encoding_flag}.",
    )


def _validate_additional_uv_count(
    additional_uv_count: int,
    *,
    offset: int,
) -> None:
    """Validate the PMX additional-UV vector count."""

    if additional_uv_count > 4:
        _raise_pmx_error(
            section="header",
            offset=offset,
            operation="validating PMX additional UV count",
            reason=(
                f"value {additional_uv_count} is invalid; "
                "expected a value from 0 through 4."
            ),
        )


def _validate_index_size(
    value: int,
    *,
    label: str,
    offset: int,
) -> int:
    """Validate one PMX index-width declaration."""

    if value not in VALID_INDEX_SIZES:
        _raise_pmx_error(
            section="header",
            offset=offset,
            operation=f"validating {label}",
            reason=(
                f"invalid index size {value}; expected one of "
                f"{sorted(VALID_INDEX_SIZES)}."
            ),
        )

    return value


def _read_model_info(
    reader: BinaryReader,
    encoding: str,
) -> PmxModelInfo:
    """Read all four PMX model-information text fields."""

    require_even_length = encoding == "utf-16-le"

    with reader.context("model_info"):
        local_name = reader.read_length_prefixed_text(
            "local model name",
            encoding=encoding,
            max_length=MAX_PMX_NAME_BYTES,
            require_even_length=require_even_length,
        )
        universal_name = reader.read_length_prefixed_text(
            "universal model name",
            encoding=encoding,
            max_length=MAX_PMX_NAME_BYTES,
            require_even_length=require_even_length,
        )
        local_comments = reader.read_length_prefixed_text(
            "local model comments",
            encoding=encoding,
            max_length=MAX_PMX_COMMENT_BYTES,
            require_even_length=require_even_length,
        )
        universal_comments = reader.read_length_prefixed_text(
            "universal model comments",
            encoding=encoding,
            max_length=MAX_PMX_COMMENT_BYTES,
            require_even_length=require_even_length,
        )

    return PmxModelInfo(
        local_name=local_name,
        universal_name=universal_name,
        local_comments=local_comments,
        universal_comments=universal_comments,
    )


def _minimum_pmx_vertex_size(
    *,
    additional_uv_count: int,
    bone_index_size: int,
) -> int:
    """Return the smallest possible PMX vertex-record size."""

    fixed_vector_bytes = 32 + (additional_uv_count * 16)

    return fixed_vector_bytes + 1 + bone_index_size + 4


def _skip_pmx_vertex(
    reader: BinaryReader,
    *,
    record_index: int,
    version: float,
    additional_uv_count: int,
    bone_index_size: int,
) -> None:
    """Safely skip one PMX vertex while validating its deform layout."""

    with reader.context(
        "vertices",
        record_index=record_index,
    ):
        vector_data_size = 32 + (additional_uv_count * 16)

        reader.skip(
            vector_data_size,
            ("vertex position, normal, UV, and additional UV data"),
        )

        deform_offset = reader.offset
        deform_type = reader.read_uint8("vertex deform type")

        if deform_type == 0:
            reader.skip_items(
                1,
                bone_index_size,
                "BDEF1 bone index",
            )

        elif deform_type == 1:
            reader.skip_items(
                2,
                bone_index_size,
                "BDEF2 bone indices",
            )
            reader.skip(
                4,
                "BDEF2 bone weight",
            )

        elif deform_type == 2:
            reader.skip_items(
                4,
                bone_index_size,
                "BDEF4 bone indices",
            )
            reader.skip(
                16,
                "BDEF4 bone weights",
            )

        elif deform_type == 3:
            reader.skip_items(
                2,
                bone_index_size,
                "SDEF bone indices",
            )
            reader.skip(
                4,
                "SDEF bone weight",
            )
            reader.skip(
                36,
                "SDEF C, R0, and R1 vectors",
            )

        elif deform_type == 4:
            if version < 2.1:
                _raise_pmx_error(
                    section="vertices",
                    record_index=record_index,
                    offset=deform_offset,
                    operation="validating vertex deform type",
                    reason=("QDEF deform type requires PMX 2.1."),
                )

            reader.skip_items(
                4,
                bone_index_size,
                "QDEF bone indices",
            )
            reader.skip(
                16,
                "QDEF bone weights",
            )

        else:
            _raise_pmx_error(
                section="vertices",
                record_index=record_index,
                offset=deform_offset,
                operation="validating vertex deform type",
                reason=(f"invalid PMX vertex deform type: {deform_type}."),
            )

        reader.skip(
            4,
            "vertex edge scale",
        )


def _scan_pmx_vertices(
    reader: BinaryReader,
    result: PmxHeaderScanResult,
) -> None:
    """Read the vertex count and safely skip every PMX vertex."""

    if result.index_sizes is None:
        _raise_pmx_error(
            section="vertices",
            offset=reader.offset,
            operation="starting vertex scan",
            reason="PMX index sizes are unavailable.",
        )

    if result.version is None:
        _raise_pmx_error(
            section="vertices",
            offset=reader.offset,
            operation="starting vertex scan",
            reason="PMX version is unavailable.",
        )

    if result.additional_uv_count is None:
        _raise_pmx_error(
            section="vertices",
            offset=reader.offset,
            operation="starting vertex scan",
            reason="PMX additional UV count is unavailable.",
        )

    index_sizes = result.index_sizes
    version = result.version
    additional_uv_count = result.additional_uv_count

    minimum_vertex_size = _minimum_pmx_vertex_size(
        additional_uv_count=additional_uv_count,
        bone_index_size=index_sizes.bone,
    )

    with reader.context("vertices"):
        vertex_count = reader.read_bounded_count(
            "vertex count",
            max_count=MAX_PMX_VERTEX_COUNT,
            minimum_item_size=minimum_vertex_size,
        )

    result.vertex_count = vertex_count

    for record_index in range(vertex_count):
        _skip_pmx_vertex(
            reader,
            record_index=record_index,
            version=version,
            additional_uv_count=additional_uv_count,
            bone_index_size=index_sizes.bone,
        )


def _scan_pmx_surface_indices(
    reader: BinaryReader,
    result: PmxHeaderScanResult,
) -> None:
    """Read and safely skip the PMX triangle-index section."""

    if result.index_sizes is None:
        _raise_pmx_error(
            section="surface_indices",
            offset=reader.offset,
            operation="starting surface-index scan",
            reason="PMX index sizes are unavailable.",
        )

    index_sizes = result.index_sizes
    count_offset = reader.offset

    with reader.context("surface_indices"):
        surface_index_count = reader.read_bounded_count(
            "surface index count",
            max_count=MAX_PMX_SURFACE_INDEX_COUNT,
            minimum_item_size=index_sizes.vertex,
        )

    if surface_index_count % 3 != 0:
        _raise_pmx_error(
            section="surface_indices",
            offset=count_offset,
            operation="validating surface index count",
            reason=(
                f"surface index count {surface_index_count} must be divisible by 3."
            ),
        )

    result.surface_index_count = surface_index_count
    result.triangle_count = surface_index_count // 3

    with reader.context("surface_indices"):
        reader.skip_items(
            surface_index_count,
            index_sizes.vertex,
            "surface vertex indices",
        )


def _scan_pmx_geometry(
    reader: BinaryReader,
    result: PmxHeaderScanResult,
) -> None:
    """Scan PMX vertex and surface-index sections."""

    _scan_pmx_vertices(
        reader,
        result,
    )
    _scan_pmx_surface_indices(
        reader,
        result,
    )


def _scan_pmx_textures(
    reader: BinaryReader,
    result: PmxHeaderScanResult,
) -> None:
    """Read raw PMX texture paths without resolving dependencies."""

    if result.encoding is None:
        _raise_pmx_error(
            section="textures",
            offset=reader.offset,
            operation="starting texture scan",
            reason="PMX text encoding is unavailable.",
        )

    encoding = result.encoding
    require_even_length = encoding == "utf-16-le"

    with reader.context("textures"):
        texture_count = reader.read_bounded_count(
            "texture count",
            max_count=MAX_PMX_TEXTURE_COUNT,
            minimum_item_size=4,
        )

    texture_paths: list[str] = []

    for record_index in range(texture_count):
        with reader.context(
            "textures",
            record_index=record_index,
        ):
            texture_path = reader.read_length_prefixed_text(
                "texture path",
                encoding=encoding,
                max_length=MAX_PMX_TEXTURE_PATH_BYTES,
                require_even_length=require_even_length,
            )

        texture_paths.append(texture_path)

    result.texture_count = texture_count
    result.texture_paths = texture_paths


def _minimum_pmx_material_size(
    *,
    texture_index_size: int,
) -> int:
    """Return the smallest possible PMX material-record size."""

    text_length_fields = 8
    shading_and_edge_fields = 65
    texture_indices = texture_index_size * 2
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

        _raise_pmx_error(
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
    result: PmxHeaderScanResult,
    *,
    record_index: int,
) -> PmxMaterial:
    """Read one PMX material while retaining structural metadata."""

    if result.encoding is None:
        _raise_pmx_error(
            section="materials",
            record_index=record_index,
            offset=reader.offset,
            operation="reading material",
            reason="PMX text encoding is unavailable.",
        )

    if result.index_sizes is None:
        _raise_pmx_error(
            section="materials",
            record_index=record_index,
            offset=reader.offset,
            operation="reading material",
            reason="PMX index sizes are unavailable.",
        )

    if result.texture_count is None:
        _raise_pmx_error(
            section="materials",
            record_index=record_index,
            offset=reader.offset,
            operation="reading material",
            reason="PMX texture count is unavailable.",
        )

    encoding = result.encoding
    texture_index_size = result.index_sizes.texture
    texture_count = result.texture_count
    require_even_length = encoding == "utf-16-le"

    with reader.context(
        "materials",
        record_index=record_index,
    ):
        local_name = reader.read_length_prefixed_text(
            "local material name",
            encoding=encoding,
            max_length=MAX_PMX_NAME_BYTES,
            require_even_length=require_even_length,
        )
        universal_name = reader.read_length_prefixed_text(
            "universal material name",
            encoding=encoding,
            max_length=MAX_PMX_NAME_BYTES,
            require_even_length=require_even_length,
        )

        reader.skip(16, "material diffuse color")
        reader.skip(12, "material specular color")
        reader.skip(4, "material specular strength")
        reader.skip(12, "material ambient color")
        reader.read_uint8("material drawing flags")
        reader.skip(16, "material edge color")
        reader.skip(4, "material edge scale")

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
        sphere_mode = reader.read_uint8("material sphere mode")

        if sphere_mode > 3:
            _raise_pmx_error(
                section="materials",
                record_index=record_index,
                offset=sphere_mode_offset,
                operation="validating material sphere mode",
                reason=(
                    f"invalid sphere mode {sphere_mode}; "
                    "expected a value from 0 through 3."
                ),
            )

        toon_mode_offset = reader.offset
        toon_mode = reader.read_uint8("material toon reference mode")

        if toon_mode == 0:
            toon_reference_mode: Literal["texture", "shared"] = "texture"
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
                _raise_pmx_error(
                    section="materials",
                    record_index=record_index,
                    offset=toon_reference_offset,
                    operation="validating shared toon index",
                    reason=(
                        f"invalid shared toon index "
                        f"{toon_reference_index}; expected a "
                        "value from 0 through 9."
                    ),
                )

        else:
            _raise_pmx_error(
                section="materials",
                record_index=record_index,
                offset=toon_mode_offset,
                operation="validating material toon reference mode",
                reason=(f"invalid toon reference mode {toon_mode}; expected 0 or 1."),
            )

        memo = reader.read_length_prefixed_text(
            "material memo",
            encoding=encoding,
            max_length=MAX_PMX_MATERIAL_MEMO_BYTES,
            require_even_length=require_even_length,
        )

        surface_count_offset = reader.offset
        surface_index_count = reader.read_bounded_count(
            "material surface index count",
            max_count=MAX_PMX_SURFACE_INDEX_COUNT,
        )

        if surface_index_count % 3 != 0:
            _raise_pmx_error(
                section="materials",
                record_index=record_index,
                offset=surface_count_offset,
                operation=("validating material surface index count"),
                reason=(
                    f"surface index count {surface_index_count} must be divisible by 3."
                ),
            )

    return PmxMaterial(
        local_name=local_name,
        universal_name=universal_name,
        texture_index=texture_index,
        sphere_texture_index=sphere_texture_index,
        sphere_mode=sphere_mode,
        toon_reference_mode=toon_reference_mode,
        toon_reference_index=toon_reference_index,
        memo=memo,
        surface_index_count=surface_index_count,
    )


def _scan_pmx_materials(
    reader: BinaryReader,
    result: PmxHeaderScanResult,
) -> None:
    """Read PMX materials and validate their surface coverage."""

    if result.index_sizes is None:
        _raise_pmx_error(
            section="materials",
            offset=reader.offset,
            operation="starting material scan",
            reason="PMX index sizes are unavailable.",
        )

    if result.surface_index_count is None:
        _raise_pmx_error(
            section="materials",
            offset=reader.offset,
            operation="starting material scan",
            reason="PMX surface index count is unavailable.",
        )

    count_offset = reader.offset
    minimum_material_size = _minimum_pmx_material_size(
        texture_index_size=result.index_sizes.texture,
    )

    with reader.context("materials"):
        material_count = reader.read_bounded_count(
            "material count",
            max_count=MAX_PMX_MATERIAL_COUNT,
            minimum_item_size=minimum_material_size,
        )

    result.material_count = material_count
    materials: list[PmxMaterial] = []
    total_surface_indices = 0

    for record_index in range(material_count):
        material = _read_pmx_material(
            reader,
            result,
            record_index=record_index,
        )
        materials.append(material)
        total_surface_indices += material.surface_index_count

        if total_surface_indices > result.surface_index_count:
            _raise_pmx_error(
                section="materials",
                record_index=record_index,
                offset=reader.offset,
                operation="validating material surface coverage",
                reason=(
                    f"cumulative material surface index count "
                    f"{total_surface_indices} exceeds model surface "
                    f"index count {result.surface_index_count}."
                ),
            )

    result.materials = materials

    if total_surface_indices != result.surface_index_count:
        _raise_pmx_error(
            section="materials",
            offset=count_offset,
            operation="validating material surface coverage",
            reason=(
                f"materials cover {total_surface_indices} surface "
                f"indices, but the model declares "
                f"{result.surface_index_count}."
            ),
        )


def _read_pmx_int32(
    reader: BinaryReader,
    label: str,
) -> int:
    """Read one little-endian signed 32-bit PMX integer."""

    return int.from_bytes(
        reader.read_exact(4, label),
        byteorder="little",
        signed=True,
    )


def _read_pmx_uint16(
    reader: BinaryReader,
    label: str,
) -> int:
    """Read one little-endian unsigned 16-bit PMX integer."""

    return int.from_bytes(
        reader.read_exact(2, label),
        byteorder="little",
        signed=False,
    )


def _read_pmx_vec3(
    reader: BinaryReader,
    label: str,
) -> tuple[float, float, float]:
    """Read one PMX vec3 as three little-endian floats."""

    return (
        reader.read_float32(f"{label} x"),
        reader.read_float32(f"{label} y"),
        reader.read_float32(f"{label} z"),
    )


def _decode_pmx_bone_flags(flags: int) -> tuple[str, ...]:
    """Return stable names for recognized PMX bone flags."""

    flag_definitions = (
        (PMX_BONE_FLAG_TAIL_INDEX, "tail_index"),
        (PMX_BONE_FLAG_ROTATABLE, "rotatable"),
        (PMX_BONE_FLAG_TRANSLATABLE, "translatable"),
        (PMX_BONE_FLAG_VISIBLE, "visible"),
        (PMX_BONE_FLAG_ENABLED, "enabled"),
        (PMX_BONE_FLAG_IK, "ik"),
        (PMX_BONE_FLAG_LOCAL_APPEND, "local_append"),
        (PMX_BONE_FLAG_INHERIT_ROTATION, "inherit_rotation"),
        (
            PMX_BONE_FLAG_INHERIT_TRANSLATION,
            "inherit_translation",
        ),
        (PMX_BONE_FLAG_FIXED_AXIS, "fixed_axis"),
        (PMX_BONE_FLAG_LOCAL_AXES, "local_axes"),
        (PMX_BONE_FLAG_AFTER_PHYSICS, "after_physics"),
        (PMX_BONE_FLAG_EXTERNAL_PARENT, "external_parent"),
    )

    return tuple(name for bit, name in flag_definitions if flags & bit)


def _minimum_pmx_bone_size(
    *,
    bone_index_size: int,
) -> int:
    """Return the smallest possible PMX bone-record size."""

    text_length_fields = 8
    position_size = 12
    parent_index_size = bone_index_size
    transform_layer_size = 4
    flags_size = 2
    minimum_tail_size = min(
        bone_index_size,
        12,
    )

    return (
        text_length_fields
        + position_size
        + parent_index_size
        + transform_layer_size
        + flags_size
        + minimum_tail_size
    )


def _validate_pmx_bone_index(
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

        _raise_pmx_error(
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
    _validate_pmx_bone_index(
        target_bone_index,
        bone_count=bone_count,
        section="bones",
        record_index=bone_record_index,
        label="IK target bone index",
        offset=target_offset,
        allow_sentinel=False,
    )

    loop_count_offset = reader.offset
    loop_count = _read_pmx_int32(
        reader,
        "IK loop count",
    )

    if loop_count < 0:
        _raise_pmx_error(
            section="bones",
            record_index=bone_record_index,
            offset=loop_count_offset,
            operation="validating IK loop count",
            reason=(f"value {loop_count} cannot be negative."),
        )

    if loop_count > MAX_PMX_IK_LOOP_COUNT:
        _raise_pmx_error(
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
    angle_limit = reader.read_float32(
        "IK angle limit",
    )

    if not math.isfinite(angle_limit):
        _raise_pmx_error(
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
            _validate_pmx_bone_index(
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
                _raise_pmx_error(
                    section=link_section,
                    record_index=link_index,
                    offset=limit_flag_offset,
                    operation=("validating IK link angle-limit flag"),
                    reason=(f"invalid flag {limit_flag}; expected 0 or 1."),
                )

            if limit_flag == 1:
                lower_limit = _read_pmx_vec3(
                    reader,
                    "IK link lower angle limit",
                )
                upper_limit = _read_pmx_vec3(
                    reader,
                    "IK link upper angle limit",
                )
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
    result: PmxHeaderScanResult,
    *,
    record_index: int,
    bone_count: int,
) -> PmxBone:
    """Read one PMX bone and all flag-controlled fields."""

    if result.encoding is None:
        _raise_pmx_error(
            section="bones",
            record_index=record_index,
            offset=reader.offset,
            operation="reading bone",
            reason="PMX text encoding is unavailable.",
        )

    if result.index_sizes is None:
        _raise_pmx_error(
            section="bones",
            record_index=record_index,
            offset=reader.offset,
            operation="reading bone",
            reason="PMX index sizes are unavailable.",
        )

    encoding = result.encoding
    bone_index_size = result.index_sizes.bone
    require_even_length = encoding == "utf-16-le"

    with reader.context(
        "bones",
        record_index=record_index,
    ):
        local_name = reader.read_length_prefixed_text(
            "local bone name",
            encoding=encoding,
            max_length=MAX_PMX_NAME_BYTES,
            require_even_length=require_even_length,
        )
        universal_name = reader.read_length_prefixed_text(
            "universal bone name",
            encoding=encoding,
            max_length=MAX_PMX_NAME_BYTES,
            require_even_length=require_even_length,
        )
        position = _read_pmx_vec3(
            reader,
            "bone position",
        )

        parent_offset = reader.offset
        parent_bone_index = reader.read_index(
            bone_index_size,
            signed=True,
            label="parent bone index",
        )
        _validate_pmx_bone_index(
            parent_bone_index,
            bone_count=bone_count,
            section="bones",
            record_index=record_index,
            label="parent bone index",
            offset=parent_offset,
            allow_sentinel=True,
        )

        transform_layer = _read_pmx_int32(
            reader,
            "bone transform layer",
        )
        flags = _read_pmx_uint16(
            reader,
            "bone flags",
        )

        if flags & PMX_BONE_FLAG_TAIL_INDEX:
            tail_mode: Literal["bone", "offset"] = "bone"
            tail_offset = None
            tail_index_offset = reader.offset
            tail_bone_index = reader.read_index(
                bone_index_size,
                signed=True,
                label="tail bone index",
            )
            _validate_pmx_bone_index(
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
            tail_offset = _read_pmx_vec3(
                reader,
                "bone tail offset",
            )

        inherit_parent_bone_index = None
        inherit_weight = None

        if flags & (PMX_BONE_FLAG_INHERIT_ROTATION | PMX_BONE_FLAG_INHERIT_TRANSLATION):
            inherit_index_offset = reader.offset
            inherit_parent_bone_index = reader.read_index(
                bone_index_size,
                signed=True,
                label="inherit parent bone index",
            )
            _validate_pmx_bone_index(
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
            fixed_axis = _read_pmx_vec3(
                reader,
                "bone fixed axis",
            )

        local_axis_x = None
        local_axis_z = None
        if flags & PMX_BONE_FLAG_LOCAL_AXES:
            local_axis_x = _read_pmx_vec3(
                reader,
                "bone local x axis",
            )
            local_axis_z = _read_pmx_vec3(
                reader,
                "bone local z axis",
            )

        external_parent_key = None
        if flags & PMX_BONE_FLAG_EXTERNAL_PARENT:
            external_parent_key = _read_pmx_int32(
                reader,
                "external parent key",
            )

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
        flag_names=_decode_pmx_bone_flags(flags),
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


def _scan_pmx_bones(
    reader: BinaryReader,
    result: PmxHeaderScanResult,
) -> None:
    """Read PMX bones and validate all available bone references."""

    if result.index_sizes is None:
        _raise_pmx_error(
            section="bones",
            offset=reader.offset,
            operation="starting bone scan",
            reason="PMX index sizes are unavailable.",
        )

    bone_index_size = result.index_sizes.bone
    minimum_bone_size = _minimum_pmx_bone_size(
        bone_index_size=bone_index_size,
    )

    with reader.context("bones"):
        bone_count = reader.read_bounded_count(
            "bone count",
            max_count=MAX_PMX_BONE_COUNT,
            minimum_item_size=minimum_bone_size,
        )

    result.bone_count = bone_count
    bones: list[PmxBone] = []
    total_ik_links = 0

    for record_index in range(bone_count):
        bone = _read_pmx_bone(
            reader,
            result,
            record_index=record_index,
            bone_count=bone_count,
        )
        bones.append(bone)

        if bone.ik is not None:
            total_ik_links += len(bone.ik.links)

            if total_ik_links > MAX_PMX_TOTAL_IK_LINK_COUNT:
                _raise_pmx_error(
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

    result.bones = bones


def _read_pmx_vec4(
    reader: BinaryReader,
    label: str,
) -> tuple[float, float, float, float]:
    """Read one PMX vec4 as four little-endian floats."""

    return (
        reader.read_float32(f"{label} x"),
        reader.read_float32(f"{label} y"),
        reader.read_float32(f"{label} z"),
        reader.read_float32(f"{label} w"),
    )


def _decode_pmx_morph_panel(
    panel: int,
    *,
    offset: int,
    record_index: int,
) -> str:
    """Validate and decode one PMX morph panel value."""

    panel_names = {
        0: "system",
        1: "eyebrow",
        2: "eye",
        3: "mouth",
        4: "other",
    }

    try:
        return panel_names[panel]
    except KeyError:
        _raise_pmx_error(
            section="morphs",
            record_index=record_index,
            offset=offset,
            operation="validating morph panel",
            reason=(f"invalid panel {panel}; expected a value from 0 through 4."),
        )


def _decode_pmx_morph_type(
    morph_type: int,
    *,
    version: float,
    additional_uv_count: int,
    offset: int,
    record_index: int,
) -> str:
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
        _raise_pmx_error(
            section="morphs",
            record_index=record_index,
            offset=offset,
            operation="validating morph type",
            reason=(
                f"invalid morph type {morph_type}; expected a value from 0 through 10."
            ),
        )

    if morph_type in {9, 10} and version < 2.1:
        _raise_pmx_error(
            section="morphs",
            record_index=record_index,
            offset=offset,
            operation="validating morph type",
            reason=(
                f"morph type {morph_type} "
                f"({morph_type_names[morph_type]}) requires PMX 2.1."
            ),
        )

    if 4 <= morph_type <= 7:
        required_uv_count = morph_type - 3
        if additional_uv_count < required_uv_count:
            _raise_pmx_error(
                section="morphs",
                record_index=record_index,
                offset=offset,
                operation="validating additional UV morph type",
                reason=(
                    f"morph type {morph_type} requires additional UV "
                    f"layer {required_uv_count}, but the model declares "
                    f"{additional_uv_count} additional UV layers."
                ),
            )

    return morph_type_names[morph_type]


def _minimum_pmx_morph_size() -> int:
    """Return the smallest possible PMX morph-record size."""

    text_length_fields = 8
    panel_size = 1
    type_size = 1
    offset_count_size = 4
    return text_length_fields + panel_size + type_size + offset_count_size


def _minimum_pmx_morph_offset_size(
    morph_type: int,
    *,
    index_sizes: PmxIndexSizes,
) -> int:
    """Return the smallest fixed size for one morph offset."""

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


def _validate_pmx_index_range(
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

        _raise_pmx_error(
            section=section,
            record_index=record_index,
            offset=offset,
            operation=f"validating {label}",
            reason=(f"index {value} is invalid for record count {count}; {expected}."),
        )


def _read_pmx_group_morph_offset(
    reader: BinaryReader,
    *,
    result: PmxHeaderScanResult,
    morph_count: int,
    section: str,
    offset_index: int,
) -> PmxGroupMorphOffset:
    """Read one PMX group-morph offset."""

    assert result.index_sizes is not None
    reference_offset = reader.offset
    morph_index = reader.read_index(
        result.index_sizes.morph,
        signed=True,
        label="group morph index",
    )
    _validate_pmx_index_range(
        morph_index,
        count=morph_count,
        section=section,
        record_index=offset_index,
        label="group morph index",
        offset=reference_offset,
        allow_sentinel=False,
    )
    weight = reader.read_float32("group morph weight")
    return PmxGroupMorphOffset(
        morph_index=morph_index,
        weight=weight,
    )


def _read_pmx_vertex_morph_offset(
    reader: BinaryReader,
    *,
    result: PmxHeaderScanResult,
    section: str,
    offset_index: int,
) -> PmxVertexMorphOffset:
    """Read one PMX vertex-morph offset."""

    assert result.index_sizes is not None
    assert result.vertex_count is not None
    reference_offset = reader.offset
    vertex_index = reader.read_index(
        result.index_sizes.vertex,
        signed=False,
        label="vertex morph vertex index",
    )
    _validate_pmx_index_range(
        vertex_index,
        count=result.vertex_count,
        section=section,
        record_index=offset_index,
        label="vertex morph vertex index",
        offset=reference_offset,
        allow_sentinel=False,
    )
    translation = _read_pmx_vec3(
        reader,
        "vertex morph translation",
    )
    return PmxVertexMorphOffset(
        vertex_index=vertex_index,
        translation=translation,
    )


def _read_pmx_bone_morph_offset(
    reader: BinaryReader,
    *,
    result: PmxHeaderScanResult,
    section: str,
    offset_index: int,
) -> PmxBoneMorphOffset:
    """Read one PMX bone-morph offset."""

    assert result.index_sizes is not None
    assert result.bone_count is not None
    reference_offset = reader.offset
    bone_index = reader.read_index(
        result.index_sizes.bone,
        signed=True,
        label="bone morph bone index",
    )
    _validate_pmx_index_range(
        bone_index,
        count=result.bone_count,
        section=section,
        record_index=offset_index,
        label="bone morph bone index",
        offset=reference_offset,
        allow_sentinel=False,
    )
    translation = _read_pmx_vec3(
        reader,
        "bone morph translation",
    )
    rotation = _read_pmx_vec4(
        reader,
        "bone morph rotation",
    )
    return PmxBoneMorphOffset(
        bone_index=bone_index,
        translation=translation,
        rotation=rotation,
    )


def _read_pmx_uv_morph_offset(
    reader: BinaryReader,
    *,
    result: PmxHeaderScanResult,
    section: str,
    offset_index: int,
) -> PmxUvMorphOffset:
    """Read one base-UV or additional-UV morph offset."""

    assert result.index_sizes is not None
    assert result.vertex_count is not None
    reference_offset = reader.offset
    vertex_index = reader.read_index(
        result.index_sizes.vertex,
        signed=False,
        label="UV morph vertex index",
    )
    _validate_pmx_index_range(
        vertex_index,
        count=result.vertex_count,
        section=section,
        record_index=offset_index,
        label="UV morph vertex index",
        offset=reference_offset,
        allow_sentinel=False,
    )
    uv_offset = _read_pmx_vec4(
        reader,
        "UV morph offset",
    )
    return PmxUvMorphOffset(
        vertex_index=vertex_index,
        uv_offset=uv_offset,
    )


def _read_pmx_material_morph_offset(
    reader: BinaryReader,
    *,
    result: PmxHeaderScanResult,
    section: str,
    offset_index: int,
) -> PmxMaterialMorphOffset:
    """Read one PMX material-morph offset."""

    assert result.index_sizes is not None
    assert result.material_count is not None
    reference_offset = reader.offset
    material_index = reader.read_index(
        result.index_sizes.material,
        signed=True,
        label="material morph material index",
    )
    _validate_pmx_index_range(
        material_index,
        count=result.material_count,
        section=section,
        record_index=offset_index,
        label="material morph material index",
        offset=reference_offset,
        allow_sentinel=True,
    )

    operation_offset = reader.offset
    operation_value = reader.read_uint8("material morph operation")
    if operation_value == 0:
        operation: Literal["multiply", "add"] = "multiply"
    elif operation_value == 1:
        operation = "add"
    else:
        _raise_pmx_error(
            section=section,
            record_index=offset_index,
            offset=operation_offset,
            operation="validating material morph operation",
            reason=(f"invalid operation {operation_value}; expected 0 or 1."),
        )

    return PmxMaterialMorphOffset(
        material_index=material_index,
        operation=operation,
        diffuse=_read_pmx_vec4(reader, "material morph diffuse"),
        specular=_read_pmx_vec3(reader, "material morph specular"),
        specular_strength=reader.read_float32("material morph specular strength"),
        ambient=_read_pmx_vec3(reader, "material morph ambient"),
        edge_color=_read_pmx_vec4(reader, "material morph edge color"),
        edge_scale=reader.read_float32("material morph edge scale"),
        texture_tint=_read_pmx_vec4(
            reader,
            "material morph texture tint",
        ),
        sphere_tint=_read_pmx_vec4(
            reader,
            "material morph sphere tint",
        ),
        toon_tint=_read_pmx_vec4(
            reader,
            "material morph toon tint",
        ),
    )


def _read_pmx_flip_morph_offset(
    reader: BinaryReader,
    *,
    result: PmxHeaderScanResult,
    morph_count: int,
    section: str,
    offset_index: int,
) -> PmxFlipMorphOffset:
    """Read one PMX 2.1 flip-morph offset."""

    assert result.index_sizes is not None
    reference_offset = reader.offset
    morph_index = reader.read_index(
        result.index_sizes.morph,
        signed=True,
        label="flip morph index",
    )
    _validate_pmx_index_range(
        morph_index,
        count=morph_count,
        section=section,
        record_index=offset_index,
        label="flip morph index",
        offset=reference_offset,
        allow_sentinel=False,
    )
    weight = reader.read_float32("flip morph weight")
    return PmxFlipMorphOffset(
        morph_index=morph_index,
        weight=weight,
    )


def _read_pmx_impulse_morph_offset(
    reader: BinaryReader,
    *,
    result: PmxHeaderScanResult,
    section: str,
    offset_index: int,
) -> PmxImpulseMorphOffset:
    """Read one PMX 2.1 impulse-morph offset.

    The rigid-body section appears later in a PMX file, so its upper
    index bound is validated when rigid-body scanning is implemented.
    Negative indices are invalid and rejected here.
    """

    assert result.index_sizes is not None
    reference_offset = reader.offset
    rigid_body_index = reader.read_index(
        result.index_sizes.rigid_body,
        signed=True,
        label="impulse morph rigid-body index",
    )
    if rigid_body_index < 0:
        _raise_pmx_error(
            section=section,
            record_index=offset_index,
            offset=reference_offset,
            operation="validating impulse morph rigid-body index",
            reason=(f"index {rigid_body_index} cannot be negative."),
        )

    local_flag_offset = reader.offset
    local_flag = reader.read_uint8("impulse morph local flag")
    if local_flag not in {0, 1}:
        _raise_pmx_error(
            section=section,
            record_index=offset_index,
            offset=local_flag_offset,
            operation="validating impulse morph local flag",
            reason=(f"invalid flag {local_flag}; expected 0 or 1."),
        )

    return PmxImpulseMorphOffset(
        rigid_body_index=rigid_body_index,
        local=(local_flag == 1),
        velocity=_read_pmx_vec3(
            reader,
            "impulse morph velocity",
        ),
        angular_torque=_read_pmx_vec3(
            reader,
            "impulse morph angular torque",
        ),
    )


def _read_pmx_morph_offset(
    reader: BinaryReader,
    result: PmxHeaderScanResult,
    *,
    morph_type: int,
    morph_count: int,
    morph_record_index: int,
    offset_index: int,
) -> PmxMorphOffset:
    """Read one type-specific PMX morph offset."""

    section = f"morphs[{morph_record_index}].offsets"

    with reader.context(
        section,
        record_index=offset_index,
    ):
        if morph_type == 0:
            return _read_pmx_group_morph_offset(
                reader,
                result=result,
                morph_count=morph_count,
                section=section,
                offset_index=offset_index,
            )

        if morph_type == 1:
            return _read_pmx_vertex_morph_offset(
                reader,
                result=result,
                section=section,
                offset_index=offset_index,
            )

        if morph_type == 2:
            return _read_pmx_bone_morph_offset(
                reader,
                result=result,
                section=section,
                offset_index=offset_index,
            )

        if 3 <= morph_type <= 7:
            return _read_pmx_uv_morph_offset(
                reader,
                result=result,
                section=section,
                offset_index=offset_index,
            )

        if morph_type == 8:
            return _read_pmx_material_morph_offset(
                reader,
                result=result,
                section=section,
                offset_index=offset_index,
            )

        if morph_type == 9:
            return _read_pmx_flip_morph_offset(
                reader,
                result=result,
                morph_count=morph_count,
                section=section,
                offset_index=offset_index,
            )

        if morph_type == 10:
            return _read_pmx_impulse_morph_offset(
                reader,
                result=result,
                section=section,
                offset_index=offset_index,
            )

    raise AssertionError(f"Unhandled PMX morph type: {morph_type}")


def _read_pmx_morph(
    reader: BinaryReader,
    result: PmxHeaderScanResult,
    *,
    record_index: int,
    morph_count: int,
) -> PmxMorph:
    """Read one PMX morph and its bounded offset records."""

    if result.encoding is None:
        _raise_pmx_error(
            section="morphs",
            record_index=record_index,
            offset=reader.offset,
            operation="reading morph",
            reason="PMX text encoding is unavailable.",
        )

    if result.index_sizes is None:
        _raise_pmx_error(
            section="morphs",
            record_index=record_index,
            offset=reader.offset,
            operation="reading morph",
            reason="PMX index sizes are unavailable.",
        )

    if result.version is None or result.additional_uv_count is None:
        _raise_pmx_error(
            section="morphs",
            record_index=record_index,
            offset=reader.offset,
            operation="reading morph",
            reason="PMX header metadata is unavailable.",
        )

    require_even_length = result.encoding == "utf-16-le"

    with reader.context(
        "morphs",
        record_index=record_index,
    ):
        local_name = reader.read_length_prefixed_text(
            "local morph name",
            encoding=result.encoding,
            max_length=MAX_PMX_NAME_BYTES,
            require_even_length=require_even_length,
        )
        universal_name = reader.read_length_prefixed_text(
            "universal morph name",
            encoding=result.encoding,
            max_length=MAX_PMX_NAME_BYTES,
            require_even_length=require_even_length,
        )

        panel_offset = reader.offset
        panel = reader.read_uint8("morph panel")
        panel_name = _decode_pmx_morph_panel(
            panel,
            offset=panel_offset,
            record_index=record_index,
        )

        type_offset = reader.offset
        morph_type = reader.read_uint8("morph type")
        morph_type_name = _decode_pmx_morph_type(
            morph_type,
            version=result.version,
            additional_uv_count=result.additional_uv_count,
            offset=type_offset,
            record_index=record_index,
        )

        minimum_offset_size = _minimum_pmx_morph_offset_size(
            morph_type,
            index_sizes=result.index_sizes,
        )
        offset_count = reader.read_bounded_count(
            "morph offset count",
            max_count=MAX_PMX_MORPH_OFFSET_COUNT,
            minimum_item_size=minimum_offset_size,
        )

    offsets = tuple(
        _read_pmx_morph_offset(
            reader,
            result,
            morph_type=morph_type,
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


def _scan_pmx_morphs(
    reader: BinaryReader,
    result: PmxHeaderScanResult,
) -> None:
    """Read PMX morphs and validate all currently resolvable references."""

    if result.index_sizes is None:
        _raise_pmx_error(
            section="morphs",
            offset=reader.offset,
            operation="starting morph scan",
            reason="PMX index sizes are unavailable.",
        )

    with reader.context("morphs"):
        morph_count = reader.read_bounded_count(
            "morph count",
            max_count=MAX_PMX_MORPH_COUNT,
            minimum_item_size=_minimum_pmx_morph_size(),
        )

    result.morph_count = morph_count
    morphs: list[PmxMorph] = []
    total_offset_count = 0

    for record_index in range(morph_count):
        morph = _read_pmx_morph(
            reader,
            result,
            record_index=record_index,
            morph_count=morph_count,
        )
        morphs.append(morph)
        total_offset_count += len(morph.offsets)

        if total_offset_count > MAX_PMX_TOTAL_MORPH_OFFSET_COUNT:
            _raise_pmx_error(
                section="morphs",
                record_index=record_index,
                offset=reader.offset,
                operation="validating total morph offset count",
                reason=(
                    f"cumulative morph offset count "
                    f"{total_offset_count} exceeds the safety limit "
                    f"of {MAX_PMX_TOTAL_MORPH_OFFSET_COUNT}."
                ),
            )

    result.morphs = morphs


def _scan_pmx_header(
    reader: BinaryReader,
    result: PmxHeaderScanResult,
) -> None:
    """Scan PMX signature, globals, index sizes, and model information."""

    with reader.context("signature"):
        magic_offset = reader.offset
        magic = reader.read_exact(
            len(PMX_MAGIC),
            "PMX signature",
        )

    result.magic = magic.decode(
        "ascii",
        errors="replace",
    )

    if magic != PMX_MAGIC:
        _raise_pmx_error(
            section="signature",
            offset=magic_offset,
            operation="validating PMX signature",
            reason=(f"invalid PMX magic/signature: {magic.hex(' ')}."),
        )

    result.detected_format = "pmx"

    with reader.context("header"):
        version_offset = reader.offset
        raw_version = reader.read_float32("PMX version")
        result.version = _normalize_pmx_version(
            raw_version,
            offset=version_offset,
        )

        global_count_offset = reader.offset
        global_count = reader.read_uint8("PMX global-count field")
        _validate_global_count(
            global_count,
            offset=global_count_offset,
        )
        result.global_count = global_count

        globals_offset = reader.offset
        globals_data = reader.read_exact(
            global_count,
            "PMX global settings",
        )

    encoding_flag = globals_data[0]
    additional_uv_count = globals_data[1]

    result.encoding = _decode_encoding_flag(
        encoding_flag,
        offset=globals_offset,
    )
    _validate_additional_uv_count(
        additional_uv_count,
        offset=globals_offset + 1,
    )
    result.additional_uv_count = additional_uv_count

    result.index_sizes = PmxIndexSizes(
        vertex=_validate_index_size(
            globals_data[2],
            label="vertex index size",
            offset=globals_offset + 2,
        ),
        texture=_validate_index_size(
            globals_data[3],
            label="texture index size",
            offset=globals_offset + 3,
        ),
        material=_validate_index_size(
            globals_data[4],
            label="material index size",
            offset=globals_offset + 4,
        ),
        bone=_validate_index_size(
            globals_data[5],
            label="bone index size",
            offset=globals_offset + 5,
        ),
        morph=_validate_index_size(
            globals_data[6],
            label="morph index size",
            offset=globals_offset + 6,
        ),
        rigid_body=_validate_index_size(
            globals_data[7],
            label="rigid-body index size",
            offset=globals_offset + 7,
        ),
    )

    extra_global_count = global_count - MIN_PMX_GLOBAL_COUNT

    if extra_global_count:
        result.warnings.append(
            f"PMX header contains {extra_global_count} "
            "unrecognized extra global-setting bytes."
        )

    result.model_info = _read_model_info(
        reader,
        result.encoding,
    )

    if not result.model_info.local_name:
        result.warnings.append("PMX local model name is empty.")


def scan_pmx_header(
    file_path: str | Path,
) -> PmxHeaderScanResult:
    """Safely scan the PMX header and complete model-information block.

    This function intentionally stops before the vertex section.
    """

    path = Path(file_path)
    result = PmxHeaderScanResult()

    try:
        with path.open("rb") as file:
            reader = BinaryReader(
                file,
                format_name="PMX",
            )
            result.file_size = reader.size

            try:
                _scan_pmx_header(
                    reader,
                    result,
                )
            except BinaryParseError as error:
                result.errors.append(str(error))
            finally:
                result.bytes_consumed = reader.offset

    except OSError as error:
        result.errors.append(f"Unable to read PMX model file: {error}.")

    return result


def scan_pmx_structure(
    file_path: str | Path,
) -> PmxHeaderScanResult:
    """Scan PMX header through the morph section."""

    path = Path(file_path)
    result = PmxHeaderScanResult()

    try:
        with path.open("rb") as file:
            reader = BinaryReader(
                file,
                format_name="PMX",
            )
            result.file_size = reader.size

            try:
                _scan_pmx_header(
                    reader,
                    result,
                )
                _scan_pmx_geometry(
                    reader,
                    result,
                )
                _scan_pmx_textures(
                    reader,
                    result,
                )
                _scan_pmx_materials(
                    reader,
                    result,
                )
                _scan_pmx_bones(
                    reader,
                    result,
                )
                _scan_pmx_morphs(
                    reader,
                    result,
                )
            except BinaryParseError as error:
                result.errors.append(str(error))
            finally:
                result.bytes_consumed = reader.offset

    except OSError as error:
        result.errors.append(f"Unable to read PMX model file: {error}.")

    return result
