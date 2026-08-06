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
    """Scan PMX header, geometry, textures, and materials."""

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
            except BinaryParseError as error:
                result.errors.append(str(error))
            finally:
                result.bytes_consumed = reader.offset

    except OSError as error:
        result.errors.append(f"Unable to read PMX model file: {error}.")

    return result
