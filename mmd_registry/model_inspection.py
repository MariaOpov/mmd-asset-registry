"""Safe PMX and PMD model-header inspection."""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO, Final, Literal


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
    file: BinaryIO,
    size: int,
    label: str,
) -> bytes:
    """Read exactly size bytes or raise a clear truncated-file failure."""

    data = file.read(size)

    if len(data) != size:
        raise _InspectionFailure(
            f"Truncated file while reading {label}: "
            f"expected {size} bytes, found {len(data)}."
        )

    return data


def _read_supported_version(
    file: BinaryIO,
    format_name: str,
    supported_versions: tuple[float, ...],
) -> float:
    """Read and normalize a supported little-endian float version."""

    raw_version = struct.unpack(
        "<f",
        _read_exact(file, 4, f"{format_name} version"),
    )[0]

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
    file: BinaryIO,
    result: ModelInspectionResult,
) -> None:
    """Inspect the PMX header and first model-name field."""

    result.version = _read_supported_version(
        file,
        "PMX",
        SUPPORTED_PMX_VERSIONS,
    )

    global_count = _read_exact(file, 1, "PMX global-count field")[0]

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
        file,
        global_count,
        "PMX global settings",
    )
    encoding_flag = globals_data[0]

    if encoding_flag == 0:
        encoding = "utf-16-le"
    elif encoding_flag == 1:
        encoding = "utf-8"
    else:
        raise _InspectionFailure(f"Invalid PMX text-encoding flag: {encoding_flag}.")

    result.encoding = encoding

    model_name_length = struct.unpack(
        "<i",
        _read_exact(file, 4, "PMX model-name length"),
    )[0]

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
        file,
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
    file: BinaryIO,
    result: ModelInspectionResult,
) -> None:
    """Inspect the PMD header and fixed-width model-name field."""

    result.version = _read_supported_version(
        file,
        "PMD",
        SUPPORTED_PMD_VERSIONS,
    )
    result.encoding = "cp932"

    model_name_data = _read_exact(
        file,
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
            prefix = file.read(4)

            if len(prefix) < 3:
                raise _InspectionFailure(
                    "File is too short to contain an MMD model signature."
                )

            if prefix == PMX_MAGIC:
                result.detected_format = "pmx"
                result.magic = "PMX "
                _inspect_pmx(file, result)
            elif prefix[:3] == PMD_MAGIC:
                result.detected_format = "pmd"
                result.magic = "Pmd"
                file.seek(3)
                _inspect_pmd(file, result)
            else:
                result.magic = prefix.decode(
                    "ascii",
                    errors="replace",
                )
                raise _InspectionFailure(
                    f"Invalid MMD model magic/signature: {prefix.hex(' ')}."
                )
    except _InspectionFailure as error:
        result.errors.append(str(error))
    except OSError as error:
        result.errors.append(f"Unable to read model file: {error}.")

    _check_extension(path, result)
    return result
