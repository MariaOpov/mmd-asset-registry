"""Safe explicit PMX round-trip operation for CLI and future UI layers."""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

from mmd_registry.pmx.document import PmxDocument
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.validation import validate_pmx_document
from mmd_registry.pmx.writer import serialize_pmx, write_pmx


class PmxRoundTripPathError(ValueError):
    """A source or destination path violates round-trip safety policy."""


class PmxRoundTripVerificationError(RuntimeError):
    """Serialized PMX data failed an internal semantic verification."""


@dataclass(frozen=True, slots=True)
class PmxRoundTripResult:
    """Stable report for one successful PMX round-trip operation."""

    input_path: Path
    output_path: Path
    version: float
    encoding: str
    model_name: str
    section_counts: tuple[tuple[str, int], ...]
    input_size: int
    output_size: int
    input_sha256: str
    output_sha256: str

    @property
    def byte_identical(self) -> bool:
        """Return whether source and output have identical bytes."""

        return (
            self.input_size == self.output_size
            and self.input_sha256 == self.output_sha256
        )

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable deterministic result payload."""

        return {
            "status": "ok",
            "input_path": self.input_path.as_posix(),
            "output_path": self.output_path.as_posix(),
            "version": self.version,
            "encoding": self.encoding,
            "model_name": self.model_name,
            "section_counts": dict(self.section_counts),
            "semantic_equal": True,
            "byte_identical": self.byte_identical,
            "input_size": self.input_size,
            "output_size": self.output_size,
            "input_sha256": self.input_sha256,
            "output_sha256": self.output_sha256,
        }


def _hash_file(path: Path) -> str:
    """Return one streaming SHA-256 digest."""

    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _section_counts(document: PmxDocument) -> tuple[tuple[str, int], ...]:
    """Return ordered aggregate counts for the round-trip report."""

    return (
        ("vertices", len(document.vertices)),
        ("surface_indices", len(document.surface_indices)),
        ("triangles", len(document.surface_indices) // 3),
        ("textures", len(document.texture_paths)),
        ("materials", len(document.materials)),
        ("bones", len(document.bones)),
        ("morphs", len(document.morphs)),
        ("display_frames", len(document.display_frames)),
        ("rigid_bodies", len(document.rigid_bodies)),
        ("joints", len(document.joints)),
        ("soft_bodies", len(document.soft_bodies)),
        ("trailing_bytes", len(document.trailing_data)),
    )


def _resolve_paths(
    input_path: str | Path,
    output_path: str | Path,
    *,
    overwrite: bool,
) -> tuple[Path, Path]:
    """Resolve and validate source/destination policy before parsing."""

    source = Path(input_path)
    destination = Path(output_path)

    if not source.exists():
        raise PmxRoundTripPathError(f"Input file does not exist: {source}")
    if not source.is_file():
        raise PmxRoundTripPathError(f"Input path is not a file: {source}")
    if source.suffix.lower() != ".pmx":
        raise PmxRoundTripPathError("Input file must use the .pmx extension.")
    if destination.suffix.lower() != ".pmx":
        raise PmxRoundTripPathError("Output file must use the .pmx extension.")
    if destination.is_symlink():
        raise PmxRoundTripPathError(
            f"Output path must not be a symbolic link: {destination}"
        )

    source = source.resolve(strict=True)
    destination = destination.resolve(strict=False)
    same_file = source == destination
    if destination.exists():
        if not destination.is_file():
            raise PmxRoundTripPathError(
                f"Output path is not a file: {destination}"
            )
        try:
            same_file = source.samefile(destination)
        except OSError:
            pass

    if same_file:
        raise PmxRoundTripPathError(
            "Input and output must be different files; in-place PMX writing "
            "is not supported."
        )
    if destination.exists() and not overwrite:
        raise PmxRoundTripPathError(
            f"Output file already exists: {destination}. "
            "Use --overwrite to replace this separate output file."
        )
    if not destination.parent.exists():
        raise PmxRoundTripPathError(
            f"Output directory does not exist: {destination.parent}"
        )
    if not destination.parent.is_dir():
        raise PmxRoundTripPathError(
            f"Output parent is not a directory: {destination.parent}"
        )

    return source, destination


def roundtrip_pmx(
    input_path: str | Path,
    output_path: str | Path,
    *,
    overwrite: bool = False,
) -> PmxRoundTripResult:
    """Write a verified PMX copy without ever modifying the input file."""

    if not isinstance(overwrite, bool):
        raise TypeError("overwrite must be a boolean.")

    source, destination = _resolve_paths(
        input_path,
        output_path,
        overwrite=overwrite,
    )
    source_document = load_pmx(source)
    validate_pmx_document(source_document)

    serialized = serialize_pmx(source_document)
    verified_document = load_pmx(io.BytesIO(serialized))
    validate_pmx_document(verified_document)
    if verified_document != source_document:
        raise PmxRoundTripVerificationError(
            "Serialized PMX failed semantic parse/write/parse verification."
        )

    expected_output_sha256 = hashlib.sha256(serialized).hexdigest()
    write_pmx(source_document, destination, overwrite=overwrite)
    output_sha256 = _hash_file(destination)
    if output_sha256 != expected_output_sha256:
        raise PmxRoundTripVerificationError(
            "Written PMX does not match the verified serialized payload."
        )

    return PmxRoundTripResult(
        input_path=source,
        output_path=destination,
        version=source_document.header.version,
        encoding=source_document.header.encoding,
        model_name=source_document.model_info.local_name,
        section_counts=_section_counts(source_document),
        input_size=source.stat().st_size,
        output_size=destination.stat().st_size,
        input_sha256=_hash_file(source),
        output_sha256=output_sha256,
    )
