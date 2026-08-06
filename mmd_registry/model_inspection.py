"""Safe PMX and PMD model-header inspection."""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO, Final, Literal

from mmd_registry.binary_reader import (
    BinaryParseError,
    BinaryReader,
)


PMX_MAGIC: Final[bytes] = b"PMX "
PMD_MAGIC: Final[bytes] = b"Pmd"

SUPPORTED_PMX_VERSIONS: Final[tuple[float, ...]] = (2.0, 2.1)
SUPPORTED_PMD_VERSIONS: Final[tuple[float, ...]] = (1.0,)

MIN_PMX_GLOBAL_COUNT: Final[int] = 8
MAX_PMX_GLOBAL_COUNT: Final[int] = 64
MAX_MODEL_NAME_BYTES: Final[int] = 64 * 1024

ModelFormat = Literal["pmx", "pmd"]
InspectionStatus = Literal["ok", "warning", "error"]


class _InspectionFailure(Exception):
    """Internal exception for expected malformed-file failures."""


@dataclass(slots=True)
class ModelInspectionResult:
    """Header inspection result for one MMD model file."""

    detected_format: ModelFormat | None = None
    magic: str | None = None
    version: float | None = None
    model_name: str | None = None
    encoding: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def status(self) -> InspectionStatus:
        """Return the overall inspection status."""

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
            "model_name": self.model_name,
            "encoding": self.encoding,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def _read_exact(
    reader: BinaryReader,
    size: int,
    label: str,
) -> bytes:
    """Read exactly size bytes while preserving inspection error wording."""

    available = reader.remaining

    if size > available:
        raise _InspectionFailure(
            f"Truncated file while reading {label}: "
            f"expected {size} bytes, found {available}."
        )

    try:
        return reader.read_exact(size, label)
    except BinaryParseError as error:
        raise _InspectionFailure(str(error)) from error


def _read_float32(
    reader: BinaryReader,
    label: str,
) -> float:
    """Read one little-endian float32 with inspection-compatible errors."""

    return struct.unpack(
        "<f",
        _read_exact(reader, 4, label),
    )[0]


def _read_int32(
    reader: BinaryReader,
    label: str,
) -> int:
    """Read one little-endian signed int32."""

    return struct.unpack(
        "<i",
        _read_exact(reader, 4, label),
    )[0]


def _read_uint8(
    reader: BinaryReader,
    label: str,
) -> int:
    """Read one unsigned byte."""

    return _read_exact(reader, 1, label)[0]


def _read_supported_version(
    reader: BinaryReader,
    format_name: str,
    supported_versions: tuple[float, ...],
) -> float:
    """Read and normalize a supported little-endian float version."""

    raw_version = _read_float32(
        reader,
        f"{format_name} version",
    )

    if not math.isfinite(raw_version):
        raise _InspectionFailure(f"{format_name} header contains a non-finite version.")

    for supported_version in supported_versions:
        if math.isclose(
            raw_version,
            supported_version,
            rel_tol=0.0,
            abs_tol=1e-4,
        ):
            return supported_version

    raise _InspectionFailure(f"Unsupported {format_name} version: {raw_version:.6g}.")


def _decode_text(
    data: bytes,
    encoding: str,
    label: str,
) -> str:
    """Decode header text strictly and report malformed byte sequences."""

    try:
        return data.decode(encoding).rstrip("\x00")
    except UnicodeDecodeError as error:
        raise _InspectionFailure(
            f"Unable to decode {label} using {encoding}: {error}."
        ) from error


def _inspect_pmx(
    reader: BinaryReader,
    result: ModelInspectionResult,
) -> None:
    """Inspect the PMX header and first model-name field."""

    with reader.context("header"):
        result.version = _read_supported_version(
            reader,
            "PMX",
            SUPPORTED_PMX_VERSIONS,
        )

        global_count = _read_uint8(
            reader,
            "PMX global-count field",
        )

        if global_count < MIN_PMX_GLOBAL_COUNT:
            raise _InspectionFailure(
                f"PMX global-count value {global_count} is smaller than "
                f"the required minimum of {MIN_PMX_GLOBAL_COUNT}."
            )

        if global_count > MAX_PMX_GLOBAL_COUNT:
            raise _InspectionFailure(
                f"PMX global-count value {global_count} exceeds the safety "
                f"limit of {MAX_PMX_GLOBAL_COUNT}."
            )

        globals_data = _read_exact(
            reader,
            global_count,
            "PMX global settings",
        )
        encoding_flag = globals_data[0]

        if encoding_flag == 0:
            encoding = "utf-16-le"
        elif encoding_flag == 1:
            encoding = "utf-8"
        else:
            raise _InspectionFailure(
                f"Invalid PMX text-encoding flag: {encoding_flag}."
            )

        result.encoding = encoding

    with reader.context("model_info"):
        model_name_length = _read_int32(
            reader,
            "PMX model-name length",
        )

        if model_name_length < 0:
            raise _InspectionFailure(
                f"PMX model-name length cannot be negative: {model_name_length}."
            )

        if model_name_length > MAX_MODEL_NAME_BYTES:
            raise _InspectionFailure(
                f"PMX model-name length {model_name_length} exceeds the "
                f"safety limit of {MAX_MODEL_NAME_BYTES} bytes."
            )

        if encoding == "utf-16-le" and model_name_length % 2 != 0:
            raise _InspectionFailure(
                "PMX UTF-16LE model-name length must be an even number of bytes."
            )

        model_name_data = _read_exact(
            reader,
            model_name_length,
            "PMX model name",
        )
        result.model_name = _decode_text(
            model_name_data,
            encoding,
            "PMX model name",
        )

        if not result.model_name:
            result.warnings.append("PMX model name is empty.")


def _inspect_pmd(
    reader: BinaryReader,
    result: ModelInspectionResult,
) -> None:
    """Inspect the PMD header and fixed-width model-name field."""

    with reader.context("header"):
        result.version = _read_supported_version(
            reader,
            "PMD",
            SUPPORTED_PMD_VERSIONS,
        )
        result.encoding = "cp932"

    with reader.context("model_info"):
        model_name_data = _read_exact(
            reader,
            20,
            "PMD model name",
        )
        model_name_data = model_name_data.split(b"\x00", 1)[0]
        result.model_name = _decode_text(
            model_name_data,
            result.encoding,
            "PMD model name",
        ).rstrip()

        if not result.model_name:
            result.warnings.append("PMD model name is empty.")


def _check_extension(
    file_path: Path,
    result: ModelInspectionResult,
) -> None:
    """Report when .pmx/.pmd extension disagrees with detected content."""

    if result.detected_format is None:
        return

    suffix = file_path.suffix.lower()

    if suffix not in {".pmx", ".pmd"}:
        return

    expected_suffix = f".{result.detected_format}"

    if suffix != expected_suffix:
        result.errors.append(
            f"File extension '{suffix}' does not match detected "
            f"{result.detected_format.upper()} content."
        )


def _read_signature(
    reader: BinaryReader,
    result: ModelInspectionResult,
) -> ModelFormat:
    """Read and identify a PMX or PMD signature without over-reading."""

    if reader.size < 3:
        raise _InspectionFailure("File is too short to contain an MMD model signature.")

    with reader.context("signature"):
        prefix = _read_exact(
            reader,
            3,
            "MMD model signature",
        )

        if prefix == PMD_MAGIC:
            result.magic = "Pmd"
            return "pmd"

        if reader.remaining == 0:
            result.magic = prefix.decode(
                "ascii",
                errors="replace",
            )
            raise _InspectionFailure(
                f"Invalid MMD model magic/signature: {prefix.hex(' ')}."
            )

        prefix += _read_exact(
            reader,
            1,
            "MMD model signature",
        )

        if prefix == PMX_MAGIC:
            result.magic = "PMX "
            return "pmx"

        result.magic = prefix.decode(
            "ascii",
            errors="replace",
        )
        raise _InspectionFailure(
            f"Invalid MMD model magic/signature: {prefix.hex(' ')}."
        )


def inspect_model_header(
    file_path: str | Path,
) -> ModelInspectionResult:
    """Safely inspect a PMX or PMD model header.

    Malformed and truncated files are represented as result errors rather
    than being allowed to crash the caller.
    """

    path = Path(file_path)
    result = ModelInspectionResult()

    try:
        with path.open("rb") as file:
            reader = BinaryReader(
                file,
                format_name="MMD",
            )

            detected_format = _read_signature(
                reader,
                result,
            )
            result.detected_format = detected_format

            if detected_format == "pmx":
                _inspect_pmx(reader, result)
            else:
                _inspect_pmd(reader, result)

    except _InspectionFailure as error:
        result.errors.append(str(error))
    except BinaryParseError as error:
        result.errors.append(str(error))
    except OSError as error:
        result.errors.append(f"Unable to read model file: {error}.")

    _check_extension(path, result)
    return result
