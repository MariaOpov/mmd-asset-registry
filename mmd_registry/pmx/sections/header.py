"""Typed reading for the PMX signature, header, and model information."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final, cast

from mmd_registry.binary_reader import BinaryReader
from mmd_registry.pmx.document import (
    MAX_PMX_ADDITIONAL_UV_COUNT,
    MAX_PMX_GLOBAL_COUNT,
    MIN_PMX_GLOBAL_COUNT,
    PmxHeader,
    PmxIndexSizes,
    PmxModelInfo,
    PmxTextEncoding,
    PmxVersion,
    SUPPORTED_PMX_VERSIONS,
    VALID_PMX_INDEX_SIZES,
)
from mmd_registry.pmx.errors import raise_pmx_error


PMX_MAGIC: Final[bytes] = b"PMX "
MAX_PMX_NAME_BYTES: Final[int] = 64 * 1024
MAX_PMX_COMMENT_BYTES: Final[int] = 1024 * 1024


@dataclass(frozen=True, slots=True)
class PmxHeaderReadResult:
    """Complete typed output from reading the PMX header sections."""

    magic: bytes
    header: PmxHeader
    model_info: PmxModelInfo
    warnings: tuple[str, ...]


@dataclass(slots=True)
class PmxHeaderReadState:
    """Incremental header state used to preserve legacy error projections."""

    version: PmxVersion | None = None
    global_count: int | None = None
    encoding: PmxTextEncoding | None = None
    additional_uv_count: int | None = None
    index_sizes: PmxIndexSizes | None = None
    model_info: PmxModelInfo | None = None


def read_pmx_magic(reader: BinaryReader) -> tuple[bytes, int]:
    """Read the PMX signature and return it with its source offset."""

    with reader.context("signature"):
        magic_offset = reader.offset
        magic = reader.read_exact(
            len(PMX_MAGIC),
            "PMX signature",
        )

    return magic, magic_offset


def validate_pmx_magic(
    magic: bytes,
    *,
    offset: int,
) -> None:
    """Reject a signature that is not the exact PMX magic value."""

    if magic != PMX_MAGIC:
        raise_pmx_error(
            section="signature",
            offset=offset,
            operation="validating PMX signature",
            reason=f"invalid PMX magic/signature: {magic.hex(' ')}.",
        )


def _normalize_pmx_version(
    raw_version: float,
    *,
    offset: int,
) -> PmxVersion:
    """Validate and normalize a supported PMX float version."""

    if not math.isfinite(raw_version):
        raise_pmx_error(
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
            return cast(PmxVersion, supported_version)

    raise_pmx_error(
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
        raise_pmx_error(
            section="header",
            offset=offset,
            operation="validating PMX global count",
            reason=(
                f"value {global_count} is smaller than the required "
                f"minimum of {MIN_PMX_GLOBAL_COUNT}."
            ),
        )

    if global_count > MAX_PMX_GLOBAL_COUNT:
        raise_pmx_error(
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
) -> PmxTextEncoding:
    """Return the Python codec selected by a PMX encoding flag."""

    if encoding_flag == 0:
        return "utf-16-le"

    if encoding_flag == 1:
        return "utf-8"

    raise_pmx_error(
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

    if additional_uv_count > MAX_PMX_ADDITIONAL_UV_COUNT:
        raise_pmx_error(
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

    if value not in VALID_PMX_INDEX_SIZES:
        raise_pmx_error(
            section="header",
            offset=offset,
            operation=f"validating {label}",
            reason=(
                f"invalid index size {value}; expected one of "
                f"{sorted(VALID_PMX_INDEX_SIZES)}."
            ),
        )

    return value


def _read_model_info(
    reader: BinaryReader,
    encoding: PmxTextEncoding,
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


def read_pmx_header_body(
    reader: BinaryReader,
    *,
    magic: bytes = PMX_MAGIC,
    state: PmxHeaderReadState | None = None,
) -> PmxHeaderReadResult:
    """Read PMX header data after an already validated signature."""

    read_state = state if state is not None else PmxHeaderReadState()

    with reader.context("header"):
        version_offset = reader.offset
        raw_version = reader.read_float32("PMX version")
        version = _normalize_pmx_version(
            raw_version,
            offset=version_offset,
        )
        read_state.version = version

        global_count_offset = reader.offset
        global_count = reader.read_uint8("PMX global-count field")
        _validate_global_count(
            global_count,
            offset=global_count_offset,
        )
        read_state.global_count = global_count

        globals_offset = reader.offset
        globals_data = reader.read_exact(
            global_count,
            "PMX global settings",
        )

    encoding = _decode_encoding_flag(
        globals_data[0],
        offset=globals_offset,
    )
    read_state.encoding = encoding
    additional_uv_count = globals_data[1]
    _validate_additional_uv_count(
        additional_uv_count,
        offset=globals_offset + 1,
    )
    read_state.additional_uv_count = additional_uv_count

    index_sizes = PmxIndexSizes(
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
    read_state.index_sizes = index_sizes
    header = PmxHeader(
        version=version,
        encoding=encoding,
        additional_uv_count=additional_uv_count,
        index_sizes=index_sizes,
        extra_global_data=globals_data[MIN_PMX_GLOBAL_COUNT:],
    )
    model_info = _read_model_info(
        reader,
        encoding,
    )
    read_state.model_info = model_info
    warnings: list[str] = []

    if header.extra_global_data:
        warnings.append(
            f"PMX header contains {len(header.extra_global_data)} "
            "unrecognized extra global-setting bytes."
        )

    if not model_info.local_name:
        warnings.append("PMX local model name is empty.")

    return PmxHeaderReadResult(
        magic=magic,
        header=header,
        model_info=model_info,
        warnings=tuple(warnings),
    )


def read_pmx_header(reader: BinaryReader) -> PmxHeaderReadResult:
    """Read and validate a complete PMX header and model-information block."""

    magic, magic_offset = read_pmx_magic(reader)
    validate_pmx_magic(
        magic,
        offset=magic_offset,
    )
    return read_pmx_header_body(
        reader,
        magic=magic,
    )
