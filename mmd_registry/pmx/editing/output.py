"""Verified atomic filesystem output for declarative PMX editing."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from mmd_registry.pmx import load_pmx, serialize_pmx, validate_pmx_document
from mmd_registry.pmx.editing.errors import (
    PmxEditPathError,
    PmxEditVerificationError,
)
from mmd_registry.pmx.editing.plan import PmxEditPlan
from mmd_registry.pmx.editing.preview import (
    PMX_EDIT_PREVIEW_SCHEMA_VERSION,
    PmxEditPreview,
    dry_run_pmx_edit,
)


_LOWERCASE_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True, slots=True)
class PmxEditWriteResult:
    """Stable report for one verified and committed PMX edit."""

    input_path: Path
    output_path: Path
    preview: PmxEditPreview
    output_sha256: str
    output_size_bytes: int

    def __post_init__(self) -> None:
        if not isinstance(self.input_path, Path):
            raise TypeError("input_path must be a Path instance.")
        if not isinstance(self.output_path, Path):
            raise TypeError("output_path must be a Path instance.")
        if not isinstance(self.preview, PmxEditPreview):
            raise TypeError("preview must be a PmxEditPreview instance.")
        if not isinstance(self.output_sha256, str):
            raise TypeError("output_sha256 must be a string.")
        if _LOWERCASE_SHA256.fullmatch(self.output_sha256) is None:
            raise ValueError(
                "output_sha256 must be exactly 64 lowercase hexadecimal "
                "characters."
            )
        if not isinstance(self.output_size_bytes, int) or isinstance(
            self.output_size_bytes,
            bool,
        ):
            raise TypeError("output_size_bytes must be an integer.")
        if self.output_size_bytes < 0:
            raise ValueError("output_size_bytes cannot be negative.")

    @property
    def status(self) -> str:
        """Return a clear write/no-op outcome."""

        return "no_changes" if self.preview.audit.changed_fields == 0 else "written"

    def to_dict(self) -> dict[str, object]:
        """Return one deterministic GUI-friendly write report."""

        return {
            "preview_schema_version": PMX_EDIT_PREVIEW_SCHEMA_VERSION,
            "status": self.status,
            "dry_run": False,
            "source": {
                "path": self.input_path.as_posix(),
                "sha256": self.preview.source_sha256,
                "size_bytes": self.preview.source_size_bytes,
            },
            "plan": {
                "sha256": self.preview.plan_sha256,
                "schema_version": self.preview.plan_schema_version,
                "operation_count": self.preview.operation_count,
            },
            "output": {
                "written": True,
                "path": self.output_path.as_posix(),
                "sha256": self.output_sha256,
                "size_bytes": self.output_size_bytes,
            },
            "verification": {
                "semantic": "passed",
                "input_unchanged": True,
            },
            "audit": self.preview.audit.to_dict(),
        }


def _hash_file(path: Path) -> str:
    """Return one streaming SHA-256 digest."""

    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_identity(path: Path) -> tuple[int, int]:
    """Return the stable filesystem identity used for pre-commit verification."""

    stat_result = path.stat()
    return (stat_result.st_dev, stat_result.st_ino)


def _validate_destination_state(
    source: Path,
    destination: Path,
    *,
    overwrite: bool,
) -> None:
    """Reject aliases and unsafe existing destinations."""

    if destination == source:
        raise PmxEditPathError(
            "Input and output must be different files; in-place PMX editing "
            "is not supported."
        )
    if destination.is_symlink():
        raise PmxEditPathError(
            f"Output path must not be a symbolic link: {destination}"
        )
    if not destination.exists():
        return
    if not destination.is_file():
        raise PmxEditPathError(f"Output path is not a file: {destination}")

    try:
        aliases_source = source.samefile(destination)
    except OSError as error:
        raise PmxEditPathError(
            f"Unable to verify input/output file identity: {error}"
        ) from error
    if aliases_source:
        raise PmxEditPathError(
            "Input and output refer to the same file; symlink and hardlink "
            "aliases are not supported."
        )
    if not overwrite:
        raise PmxEditPathError(
            f"Output file already exists: {destination}. "
            "Use --overwrite to replace this separate output file."
        )


def _resolve_edit_paths(
    input_path: str | Path,
    output_path: str | Path,
    *,
    overwrite: bool,
) -> tuple[Path, Path, Path]:
    """Resolve source and destination without following the final output."""

    requested_source = Path(input_path)
    requested_destination = Path(output_path)
    if not requested_source.exists():
        raise PmxEditPathError(
            f"Input file does not exist: {requested_source}"
        )
    if not requested_source.is_file():
        raise PmxEditPathError(
            f"Input path is not a file: {requested_source}"
        )
    if requested_source.suffix.lower() != ".pmx":
        raise PmxEditPathError("Input file must use the .pmx extension.")
    if requested_destination.suffix.lower() != ".pmx":
        raise PmxEditPathError("Output file must use the .pmx extension.")

    source = requested_source.resolve(strict=True)
    destination_parent = requested_destination.parent.resolve(strict=False)
    if not destination_parent.exists():
        raise PmxEditPathError(
            f"Output directory does not exist: {destination_parent}"
        )
    if not destination_parent.is_dir():
        raise PmxEditPathError(
            f"Output parent is not a directory: {destination_parent}"
        )
    destination = destination_parent / requested_destination.name
    _validate_destination_state(source, destination, overwrite=overwrite)
    return requested_source, source, destination


def _verify_source_unchanged(
    requested_source: Path,
    source: Path,
    expected_sha256: str,
    expected_identity: tuple[int, int],
) -> None:
    """Require the original source path and content immediately pre-commit."""

    try:
        current_source = requested_source.resolve(strict=True)
    except OSError as error:
        raise PmxEditVerificationError(
            f"source path changed before output commit: {error}"
        ) from error
    try:
        current_identity = _file_identity(current_source)
    except OSError as error:
        raise PmxEditVerificationError(
            f"source identity could not be verified before output commit: {error}"
        ) from error
    if current_identity != expected_identity:
        raise PmxEditVerificationError(
            "source file identity changed before output commit."
        )

    try:
        same_file = source.samefile(current_source)
    except OSError as error:
        raise PmxEditVerificationError(
            f"source identity could not be verified before output commit: {error}"
        ) from error
    if not same_file:
        raise PmxEditVerificationError(
            "source path changed before output commit."
        )
    try:
        current_sha256 = _hash_file(current_source)
    except OSError as error:
        raise PmxEditVerificationError(
            f"source content could not be verified before output commit: {error}"
        ) from error
    if current_sha256 != expected_sha256:
        raise PmxEditVerificationError(
            "source SHA-256 changed before output commit."
        )


def _commit_verified_bytes(
    data: bytes,
    *,
    requested_source: Path,
    source: Path,
    destination: Path,
    source_sha256: str,
    source_identity: tuple[int, int],
    overwrite: bool,
) -> None:
    """Commit verified bytes atomically without exposing a partial output."""

    expected_output_sha256 = hashlib.sha256(data).hexdigest()
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            temporary_path = Path(file.name)
            file.write(data)
            file.flush()
            os.fsync(file.fileno())

        if _hash_file(temporary_path) != expected_output_sha256:
            raise PmxEditVerificationError(
                "temporary PMX does not match the verified serialized payload."
            )
        _verify_source_unchanged(
            requested_source,
            source,
            source_sha256,
            source_identity,
        )
        _validate_destination_state(
            source,
            destination,
            overwrite=overwrite,
        )

        if overwrite:
            os.replace(temporary_path, destination)
            temporary_path = None
        else:
            try:
                os.link(temporary_path, destination)
            except FileExistsError as error:
                raise PmxEditPathError(
                    f"Output file already exists: {destination}. "
                    "Use --overwrite to replace this separate output file."
                ) from error
            temporary_path.unlink()
            temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def write_pmx_edit(
    input_path: str | Path,
    output_path: str | Path,
    plan: PmxEditPlan,
    *,
    overwrite: bool = False,
) -> PmxEditWriteResult:
    """Apply, verify, and atomically write one distinct PMX output."""

    if not isinstance(plan, PmxEditPlan):
        raise TypeError("plan must be a PmxEditPlan instance.")
    if not isinstance(overwrite, bool):
        raise TypeError("overwrite must be a boolean.")

    requested_source, source, destination = _resolve_edit_paths(
        input_path,
        output_path,
        overwrite=overwrite,
    )
    source_identity = _file_identity(source)
    source_bytes = source.read_bytes()
    preview = dry_run_pmx_edit(source_bytes, plan)

    serialized_document = serialize_pmx(preview.document)
    reparsed_document = load_pmx(io.BytesIO(serialized_document))
    validate_pmx_document(reparsed_document)
    if reparsed_document != preview.document:
        raise PmxEditVerificationError(
            "serialized PMX does not match the intended edited document."
        )

    output_sha256 = hashlib.sha256(serialized_document).hexdigest()
    _commit_verified_bytes(
        serialized_document,
        requested_source=requested_source,
        source=source,
        destination=destination,
        source_sha256=preview.source_sha256,
        source_identity=source_identity,
        overwrite=overwrite,
    )
    return PmxEditWriteResult(
        input_path=source,
        output_path=destination,
        preview=preview,
        output_sha256=output_sha256,
        output_size_bytes=len(serialized_document),
    )


def _render_changed_count(count: int, singular: str, plural: str) -> str:
    """Render one stable category count."""

    unit = singular if count == 1 else plural
    return f"{count} {unit} changed"


def render_pmx_edit_write_text(result: PmxEditWriteResult) -> str:
    """Render one compact Unicode-safe successful write report."""

    if not isinstance(result, PmxEditWriteResult):
        raise TypeError("result must be a PmxEditWriteResult instance.")
    audit = result.preview.audit
    status = (
        "no changes"
        if audit.changed_fields == 0
        else _render_changed_count(audit.changed_fields, "field", "fields")
    )
    lines = (
        "PMX EDIT RESULT",
        f"Status: {status}",
        "Model: "
        + _render_changed_count(audit.category_count("model"), "field", "fields"),
        "Textures: "
        + _render_changed_count(audit.category_count("texture"), "path", "paths"),
        "Materials: "
        + _render_changed_count(
            audit.category_count("material"), "field", "fields"
        ),
        f"Input: {result.input_path.as_posix()}",
        f"Output: {result.output_path.as_posix()}",
        f"Source SHA-256: {result.preview.source_sha256}",
        f"Output SHA-256: {result.output_sha256}",
        "Semantic verification: passed",
        "Source unchanged: yes",
        "Output written: yes",
    )
    return "\n".join(lines) + "\n"


def render_pmx_edit_write_json(
    result: PmxEditWriteResult,
    *,
    indent: int | None = 2,
) -> str:
    """Render one stable Unicode-safe JSON write report."""

    if not isinstance(result, PmxEditWriteResult):
        raise TypeError("result must be a PmxEditWriteResult instance.")
    if indent is not None:
        if not isinstance(indent, int) or isinstance(indent, bool):
            raise TypeError("indent must be an integer or None.")
        if indent < 0:
            raise ValueError("indent cannot be negative.")
    return (
        json.dumps(
            result.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            indent=indent,
        )
        + "\n"
    )
