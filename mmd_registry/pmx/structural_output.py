"""CP18 verified structural serialization and safe filesystem output.

This internal layer closes the CP15-CP18 structural pipeline:

    transform -> certify -> preview -> serialize -> reparse -> certify -> compare
              -> verified bytes -> safe distinct-path publication

CP18 intentionally reuses the mature v0.8 edit-output filesystem safety kernel
instead of copying its path/race/atomic-write implementation.  The adapter calls
the existing private ``_resolve_edit_paths``, ``_file_identity``, and
``_commit_verified_bytes`` hooks and translates their edit-specific path and
verification exceptions into structural-output exceptions.

That private dependency is deliberate and temporary: changing or extracting the
v0.8 hooks here would invalidate existing negative-safety tests that monkeypatch
those exact module-local hooks.  CP19 owns the service/capability boundary and
may introduce a shared public-neutral abstraction later without weakening the
frozen v0.8 behavior.

CP18 does not resize index widths, repair documents, expose a service/CLI API,
or modify the CP17 preview contract.  A structural serialization result exists
only after:

* CP17 produced a CP16-certified intended document;
* deterministic ``serialize_pmx`` completed;
* the bytes reparsed successfully;
* the reparsed document independently passed CP16 certification; and
* reparsed document equality matched the intended certified document exactly.

Only then may those verified bytes be passed to the reused v0.8 atomic output
kernel. Direct write-result construction is intentionally blocked so ordinary
callers use the supported successful-commit path. This is an API-integrity
guard, not a Python security boundary against deliberate private-method or
object-model bypass. Structural no-op intents still follow this full
verification path and,
when a filesystem write is requested, produce a distinct verified output file.
"""

from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

from mmd_registry.pmx.collection_transform import PmxStructuralTransformIntent
from mmd_registry.pmx.document import PmxDocument
from mmd_registry.pmx.editing import output as _edit_output
from mmd_registry.pmx.editing.errors import (
    PmxEditPathError,
    PmxEditVerificationError,
)
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.structural_invariants import (
    PmxStructuralInvariantCertificate,
)
from mmd_registry.pmx.structural_preview import (
    PMX_STRUCTURAL_PREVIEW_SCHEMA_VERSION,
    PmxStructuralPreview,
    preview_pmx_structural_transform,
)
from mmd_registry.pmx.writer import serialize_pmx


_LOWERCASE_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class PmxStructuralOutputPathError(ValueError):
    """Raised when structural input/output paths violate safe-write policy."""


class PmxStructuralOutputVerificationError(RuntimeError):
    """Raised when structural serialization or output verification fails."""


def _require_sha256(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    if _LOWERCASE_SHA256.fullmatch(value) is None:
        raise ValueError(
            f"{field_name} must be exactly 64 lowercase hexadecimal characters."
        )
    return value


@dataclass(frozen=True, slots=True)
class PmxStructuralSerializationResult:
    """Self-derived verified in-memory PMX serialization evidence."""

    source_document: PmxDocument
    intent: PmxStructuralTransformIntent
    preview: PmxStructuralPreview = field(init=False)
    serialized_bytes: bytes = field(init=False, repr=False)
    reparsed_certificate: PmxStructuralInvariantCertificate = field(init=False)
    output_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.source_document, PmxDocument):
            raise TypeError("source_document must be a PmxDocument instance.")
        if not isinstance(self.intent, PmxStructuralTransformIntent):
            raise TypeError("intent must be a PmxStructuralTransformIntent value.")

        preview = preview_pmx_structural_transform(
            self.source_document,
            self.intent,
        )
        intended_document = preview.certificate.document
        serialized = serialize_pmx(intended_document)

        try:
            reparsed_document = load_pmx(io.BytesIO(serialized))
        except Exception as error:
            raise PmxStructuralOutputVerificationError(
                f"serialized structural PMX could not be reparsed: {error}"
            ) from error

        try:
            reparsed_certificate = PmxStructuralInvariantCertificate(
                document=reparsed_document
            )
        except Exception as error:
            raise PmxStructuralOutputVerificationError(
                "reparsed structural PMX failed complete invariant certification: "
                f"{error}"
            ) from error

        if reparsed_document != intended_document:
            raise PmxStructuralOutputVerificationError(
                "serialized structural PMX does not match the intended "
                "certified document."
            )

        output_sha256 = hashlib.sha256(serialized).hexdigest()
        object.__setattr__(self, "preview", preview)
        object.__setattr__(self, "serialized_bytes", serialized)
        object.__setattr__(
            self,
            "reparsed_certificate",
            reparsed_certificate,
        )
        object.__setattr__(self, "output_sha256", output_sha256)

    @property
    def output_size_bytes(self) -> int:
        return len(self.serialized_bytes)

    @property
    def status(self) -> str:
        return self.preview.status

    def to_dict(self) -> dict[str, object]:
        """Return deterministic JSON-ready verified-serialization evidence."""

        report = self.preview.to_dict()
        report["output"] = {
            **report["output"],
            "written": False,
            "sha256": self.output_sha256,
            "size_bytes": self.output_size_bytes,
        }
        report["verification"] = {
            "invariants": "passed",
            "reference_model": "passed",
            "serialization": "passed",
            "semantic": "passed",
        }
        return report


def verify_pmx_structural_serialization(
    document: PmxDocument,
    intent: PmxStructuralTransformIntent,
) -> PmxStructuralSerializationResult:
    """Return verified deterministic bytes without touching the filesystem."""

    return PmxStructuralSerializationResult(
        source_document=document,
        intent=intent,
    )


@dataclass(frozen=True, slots=True, init=False)
class PmxStructuralWriteResult:
    """Report whose supported creation path follows successful atomic commit."""

    input_path: Path
    output_path: Path
    source_sha256: str
    source_size_bytes: int
    serialization: PmxStructuralSerializationResult

    def __init__(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        raise TypeError(
            "PmxStructuralWriteResult cannot be constructed directly; "
            "use write_pmx_structural_transform()."
        )

    @classmethod
    def _from_committed(
        cls,
        *,
        input_path: Path,
        output_path: Path,
        source_sha256: str,
        source_size_bytes: int,
        serialization: PmxStructuralSerializationResult,
    ) -> "PmxStructuralWriteResult":
        if not isinstance(input_path, Path):
            raise TypeError("input_path must be a Path instance.")
        if not isinstance(output_path, Path):
            raise TypeError("output_path must be a Path instance.")
        _require_sha256(source_sha256, "source_sha256")
        if type(source_size_bytes) is not int:
            raise TypeError("source_size_bytes must be an integer.")
        if source_size_bytes < 0:
            raise ValueError("source_size_bytes cannot be negative.")
        if not isinstance(serialization, PmxStructuralSerializationResult):
            raise TypeError(
                "serialization must be a PmxStructuralSerializationResult value."
            )

        result = object.__new__(cls)
        object.__setattr__(result, "input_path", input_path)
        object.__setattr__(result, "output_path", output_path)
        object.__setattr__(result, "source_sha256", source_sha256)
        object.__setattr__(result, "source_size_bytes", source_size_bytes)
        object.__setattr__(result, "serialization", serialization)
        return result

    @property
    def status(self) -> str:
        return (
            "no_changes"
            if self.serialization.preview.status == "no_changes"
            else "written"
        )

    @property
    def output_sha256(self) -> str:
        return self.serialization.output_sha256

    @property
    def output_size_bytes(self) -> int:
        return self.serialization.output_size_bytes

    def to_dict(self) -> dict[str, object]:
        """Return deterministic JSON-ready committed-output evidence."""

        report = self.serialization.to_dict()
        source = report["source"]
        output = report["output"]
        verification = report["verification"]
        assert isinstance(source, dict)
        assert isinstance(output, dict)
        assert isinstance(verification, dict)

        report["status"] = self.status
        report["dry_run"] = False
        report["source"] = {
            **source,
            "path": self.input_path.as_posix(),
            "sha256": self.source_sha256,
            "size_bytes": self.source_size_bytes,
        }
        report["output"] = {
            **output,
            "written": True,
            "path": self.output_path.as_posix(),
        }
        report["verification"] = {
            **verification,
            "input_unchanged": True,
        }
        return report


def _translate_edit_path_error(error: PmxEditPathError) -> None:
    raise PmxStructuralOutputPathError(str(error)) from None


def _translate_edit_verification_error(
    error: PmxEditVerificationError,
) -> None:
    raise PmxStructuralOutputVerificationError(str(error)) from None


def write_pmx_structural_transform(
    input_path: str | Path,
    output_path: str | Path,
    intent: PmxStructuralTransformIntent,
    *,
    overwrite: bool = False,
) -> PmxStructuralWriteResult:
    """Transform, verify, and atomically write one distinct structural PMX output."""

    if not isinstance(intent, PmxStructuralTransformIntent):
        raise TypeError("intent must be a PmxStructuralTransformIntent value.")
    if not isinstance(overwrite, bool):
        raise TypeError("overwrite must be a boolean.")

    try:
        requested_source, source, destination = _edit_output._resolve_edit_paths(
            input_path,
            output_path,
            overwrite=overwrite,
        )
    except PmxEditPathError as error:
        _translate_edit_path_error(error)
        raise AssertionError("unreachable")

    source_identity = _edit_output._file_identity(source)
    source_bytes = source.read_bytes()
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    source_document = load_pmx(io.BytesIO(source_bytes))

    serialization = verify_pmx_structural_serialization(
        source_document,
        intent,
    )

    try:
        _edit_output._commit_verified_bytes(
            serialization.serialized_bytes,
            requested_source=requested_source,
            source=source,
            destination=destination,
            source_sha256=source_sha256,
            source_identity=source_identity,
            overwrite=overwrite,
        )
    except PmxEditPathError as error:
        _translate_edit_path_error(error)
        raise AssertionError("unreachable")
    except PmxEditVerificationError as error:
        _translate_edit_verification_error(error)
        raise AssertionError("unreachable")

    return PmxStructuralWriteResult._from_committed(
        input_path=source,
        output_path=destination,
        source_sha256=source_sha256,
        source_size_bytes=len(source_bytes),
        serialization=serialization,
    )


__all__ = (
    "PMX_STRUCTURAL_PREVIEW_SCHEMA_VERSION",
    "PmxStructuralOutputPathError",
    "PmxStructuralOutputVerificationError",
    "PmxStructuralSerializationResult",
    "PmxStructuralWriteResult",
    "verify_pmx_structural_serialization",
    "write_pmx_structural_transform",
)
