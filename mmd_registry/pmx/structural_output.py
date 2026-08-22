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
those exact module-local hooks. CP16 exposes execution only through a reviewed
service wrapper; this raw writer and its transaction helper remain implementation
details.

This module does not resize index widths, repair documents, expose a CLI mutation
command, or modify the certified preview contract. A structural serialization
result exists
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

CP08 extends only the certified-preview/serialization adapter so texture insertion can
reuse this exact transaction authority. CP10 reuses the same adapter and transaction
authority for zero-surface material insertion. CP12 reuses the same verified path for
semantic bone insertion. CP13 reuses the same verified path for bounded semantic morph
insertion. CP14 reuses it for bounded semantic rigid-body insertion. The legacy
transform classes and public raw structural-output surface remain unchanged;
insertion-specific helpers stay private.
"""

from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from mmd_registry.pmx.collection_transform import PmxStructuralTransformIntent
from mmd_registry.pmx.document import PmxDocument
from mmd_registry.pmx.editing import output as _edit_output
from mmd_registry.pmx.editing.errors import (
    PmxEditPathError,
    PmxEditVerificationError,
)
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.structural_coordinated_insertion import (
    PmxCoordinatedInsertionPayloads,
    PmxCoordinatedInsertionPreview,
    preview_pmx_coordinated_insertions,
)
from mmd_registry.pmx.structural_invariants import (
    PmxStructuralInvariantCertificate,
)
from mmd_registry.pmx.structural_bone_insertion import (
    PmxBoneInsertionPayload,
    PmxBoneInsertionPreview,
    preview_pmx_bone_insertions,
)
from mmd_registry.pmx.structural_material_insertion import (
    PmxMaterialInsertionPayload,
    PmxMaterialInsertionPreview,
    preview_pmx_material_insertions,
)
from mmd_registry.pmx.structural_morph_insertion import (
    PmxMorphInsertionPayload,
    PmxMorphInsertionPreview,
    preview_pmx_morph_insertions,
)
from mmd_registry.pmx.structural_rigid_body_insertion import (
    PmxRigidBodyInsertionPayload,
    PmxRigidBodyInsertionPreview,
    preview_pmx_rigid_body_insertions,
)
from mmd_registry.pmx.structural_preview import (
    PMX_STRUCTURAL_PREVIEW_SCHEMA_VERSION,
    PmxStructuralPreview,
    preview_pmx_structural_transform,
)
from mmd_registry.pmx.structural_texture_insertion import (
    PmxTextureInsertionPayload,
    PmxTextureInsertionPreview,
    preview_pmx_texture_insertions,
)
from mmd_registry.pmx.structural_vertex_insertion import (
    PmxVertexInsertionPayload,
    PmxVertexInsertionPreview,
    preview_pmx_vertex_insertions,
)
from mmd_registry.pmx.writer import serialize_pmx


_LOWERCASE_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


_StructuralStageCallback = Callable[[str], None]


def _notify_structural_stage(
    callback: _StructuralStageCallback | None,
    stage: str,
) -> None:
    """Record one bounded execution stage for service-side failure provenance."""

    if callback is not None:
        callback(stage)


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


_StructuralPreview = (
    PmxStructuralPreview
    | PmxTextureInsertionPreview
    | PmxMaterialInsertionPreview
    | PmxBoneInsertionPreview
    | PmxMorphInsertionPreview
    | PmxRigidBodyInsertionPreview
    | PmxVertexInsertionPreview
    | PmxCoordinatedInsertionPreview
)


def _derive_verified_structural_serialization(
    preview_factory: Callable[[], _StructuralPreview],
    stage_callback: _StructuralStageCallback | None,
) -> tuple[
    _StructuralPreview,
    bytes,
    PmxStructuralInvariantCertificate,
    str,
]:
    """Serialize one certified preview and independently verify its exact meaning."""

    if not callable(preview_factory):
        raise TypeError("preview_factory must be callable.")
    if stage_callback is not None and not callable(stage_callback):
        raise TypeError("stage_callback must be callable or None.")

    _notify_structural_stage(stage_callback, "structural_certification")
    preview = preview_factory()
    if not isinstance(
        preview,
        (
            PmxStructuralPreview,
            PmxTextureInsertionPreview,
            PmxMaterialInsertionPreview,
            PmxBoneInsertionPreview,
            PmxMorphInsertionPreview,
            PmxRigidBodyInsertionPreview,
            PmxVertexInsertionPreview,
            PmxCoordinatedInsertionPreview,
        ),
    ):
        raise TypeError(
            "preview_factory must return a supported certified structural preview."
        )
    intended_document = preview.certificate.document

    _notify_structural_stage(stage_callback, "serialization")
    serialized = serialize_pmx(intended_document)

    _notify_structural_stage(stage_callback, "reparse")
    try:
        reparsed_document = load_pmx(io.BytesIO(serialized))
    except Exception as error:
        raise PmxStructuralOutputVerificationError(
            f"serialized structural PMX could not be reparsed: {error}"
        ) from error

    _notify_structural_stage(stage_callback, "reparse_certification")
    try:
        reparsed_certificate = PmxStructuralInvariantCertificate(
            document=reparsed_document
        )
    except Exception as error:
        raise PmxStructuralOutputVerificationError(
            "reparsed structural PMX failed complete invariant certification: "
            f"{error}"
        ) from error

    _notify_structural_stage(stage_callback, "semantic_compare")
    if reparsed_document != intended_document:
        raise PmxStructuralOutputVerificationError(
            "serialized structural PMX does not match the intended certified document."
        )

    return (
        preview,
        serialized,
        reparsed_certificate,
        hashlib.sha256(serialized).hexdigest(),
    )


def _verified_serialization_report(
    preview: _StructuralPreview,
    output_sha256: str,
    output_size_bytes: int,
) -> dict[str, object]:
    """Promote preview evidence only after deterministic serialization verification."""

    report = preview.to_dict()
    output = report["output"]
    if not isinstance(output, dict):
        raise AssertionError("structural preview output evidence must be a dictionary.")
    report["output"] = {
        **output,
        "written": False,
        "sha256": output_sha256,
        "size_bytes": output_size_bytes,
    }
    report["verification"] = {
        "invariants": "passed",
        "reference_model": "passed",
        "serialization": "passed",
        "semantic": "passed",
    }
    return report


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
        self._derive_verified_evidence(None)

    @classmethod
    def _with_stage_callback(
        cls,
        source_document: PmxDocument,
        intent: PmxStructuralTransformIntent,
        stage_callback: _StructuralStageCallback,
    ) -> "PmxStructuralSerializationResult":
        result = object.__new__(cls)
        object.__setattr__(result, "source_document", source_document)
        object.__setattr__(result, "intent", intent)
        result._derive_verified_evidence(stage_callback)
        return result

    def _derive_verified_evidence(
        self,
        stage_callback: _StructuralStageCallback | None,
    ) -> None:
        if not isinstance(self.source_document, PmxDocument):
            raise TypeError("source_document must be a PmxDocument instance.")
        if not isinstance(self.intent, PmxStructuralTransformIntent):
            raise TypeError("intent must be a PmxStructuralTransformIntent value.")
        if stage_callback is not None and not callable(stage_callback):
            raise TypeError("stage_callback must be callable or None.")

        preview, serialized, reparsed_certificate, output_sha256 = (
            _derive_verified_structural_serialization(
                lambda: preview_pmx_structural_transform(
                    self.source_document,
                    self.intent,
                ),
                stage_callback,
            )
        )
        if not isinstance(preview, PmxStructuralPreview):
            raise AssertionError(
                "legacy structural serialization returned wrong preview."
            )

        object.__setattr__(self, "preview", preview)
        object.__setattr__(self, "serialized_bytes", serialized)
        object.__setattr__(self, "reparsed_certificate", reparsed_certificate)
        object.__setattr__(self, "output_sha256", output_sha256)

    @property
    def output_size_bytes(self) -> int:
        return len(self.serialized_bytes)

    @property
    def status(self) -> str:
        return self.preview.status

    def to_dict(self) -> dict[str, object]:
        """Return deterministic JSON-ready verified-serialization evidence."""

        return _verified_serialization_report(
            self.preview,
            self.output_sha256,
            self.output_size_bytes,
        )


@dataclass(frozen=True, slots=True)
class _PmxTextureInsertionSerializationResult:
    """Verified serialization evidence for the CP08 texture insertion path."""

    source_document: PmxDocument
    insertions: tuple[PmxTextureInsertionPayload, ...]
    preview: PmxTextureInsertionPreview = field(init=False)
    serialized_bytes: bytes = field(init=False, repr=False)
    reparsed_certificate: PmxStructuralInvariantCertificate = field(init=False)
    output_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        self._derive_verified_evidence(None)

    @classmethod
    def _with_stage_callback(
        cls,
        source_document: PmxDocument,
        insertions: tuple[PmxTextureInsertionPayload, ...],
        stage_callback: _StructuralStageCallback,
    ) -> "_PmxTextureInsertionSerializationResult":
        result = object.__new__(cls)
        object.__setattr__(result, "source_document", source_document)
        object.__setattr__(result, "insertions", insertions)
        result._derive_verified_evidence(stage_callback)
        return result

    def _derive_verified_evidence(
        self,
        stage_callback: _StructuralStageCallback | None,
    ) -> None:
        if not isinstance(self.source_document, PmxDocument):
            raise TypeError("source_document must be a PmxDocument instance.")
        if type(self.insertions) is not tuple:
            raise TypeError("insertions must be a tuple.")
        if not self.insertions:
            raise ValueError(
                "texture insertion execution requires at least one insertion."
            )
        if not all(
            isinstance(insertion, PmxTextureInsertionPayload)
            for insertion in self.insertions
        ):
            raise TypeError(
                "insertions must contain only PmxTextureInsertionPayload values."
            )
        if stage_callback is not None and not callable(stage_callback):
            raise TypeError("stage_callback must be callable or None.")

        preview, serialized, reparsed_certificate, output_sha256 = (
            _derive_verified_structural_serialization(
                lambda: preview_pmx_texture_insertions(
                    self.source_document,
                    self.insertions,
                ),
                stage_callback,
            )
        )
        if not isinstance(preview, PmxTextureInsertionPreview):
            raise AssertionError(
                "texture insertion serialization returned wrong preview."
            )

        object.__setattr__(self, "preview", preview)
        object.__setattr__(self, "serialized_bytes", serialized)
        object.__setattr__(self, "reparsed_certificate", reparsed_certificate)
        object.__setattr__(self, "output_sha256", output_sha256)

    @property
    def output_size_bytes(self) -> int:
        return len(self.serialized_bytes)

    @property
    def status(self) -> str:
        return self.preview.status

    def to_dict(self) -> dict[str, object]:
        """Return deterministic JSON-ready verified-serialization evidence."""

        return _verified_serialization_report(
            self.preview,
            self.output_sha256,
            self.output_size_bytes,
        )


@dataclass(frozen=True, slots=True)
class _PmxMaterialInsertionSerializationResult:
    """Verified serialization evidence for the CP10 material insertion path."""

    source_document: PmxDocument
    insertions: tuple[PmxMaterialInsertionPayload, ...]
    preview: PmxMaterialInsertionPreview = field(init=False)
    serialized_bytes: bytes = field(init=False, repr=False)
    reparsed_certificate: PmxStructuralInvariantCertificate = field(init=False)
    output_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        self._derive_verified_evidence(None)

    @classmethod
    def _with_stage_callback(
        cls,
        source_document: PmxDocument,
        insertions: tuple[PmxMaterialInsertionPayload, ...],
        stage_callback: _StructuralStageCallback,
    ) -> "_PmxMaterialInsertionSerializationResult":
        result = object.__new__(cls)
        object.__setattr__(result, "source_document", source_document)
        object.__setattr__(result, "insertions", insertions)
        result._derive_verified_evidence(stage_callback)
        return result

    def _derive_verified_evidence(
        self,
        stage_callback: _StructuralStageCallback | None,
    ) -> None:
        if not isinstance(self.source_document, PmxDocument):
            raise TypeError("source_document must be a PmxDocument instance.")
        if type(self.insertions) is not tuple:
            raise TypeError("insertions must be a tuple.")
        if not self.insertions:
            raise ValueError(
                "material insertion execution requires at least one insertion."
            )
        if not all(
            isinstance(insertion, PmxMaterialInsertionPayload)
            for insertion in self.insertions
        ):
            raise TypeError(
                "insertions must contain only PmxMaterialInsertionPayload values."
            )
        if stage_callback is not None and not callable(stage_callback):
            raise TypeError("stage_callback must be callable or None.")

        preview, serialized, reparsed_certificate, output_sha256 = (
            _derive_verified_structural_serialization(
                lambda: preview_pmx_material_insertions(
                    self.source_document,
                    self.insertions,
                ),
                stage_callback,
            )
        )
        if not isinstance(preview, PmxMaterialInsertionPreview):
            raise AssertionError(
                "material insertion serialization returned wrong preview."
            )

        object.__setattr__(self, "preview", preview)
        object.__setattr__(self, "serialized_bytes", serialized)
        object.__setattr__(self, "reparsed_certificate", reparsed_certificate)
        object.__setattr__(self, "output_sha256", output_sha256)

    @property
    def output_size_bytes(self) -> int:
        return len(self.serialized_bytes)

    @property
    def status(self) -> str:
        return self.preview.status

    def to_dict(self) -> dict[str, object]:
        """Return deterministic JSON-ready verified-serialization evidence."""

        return _verified_serialization_report(
            self.preview,
            self.output_sha256,
            self.output_size_bytes,
        )


@dataclass(frozen=True, slots=True)
class _PmxBoneInsertionSerializationResult:
    """Verified serialization evidence for the CP12 bone insertion path."""

    source_document: PmxDocument
    insertions: tuple[PmxBoneInsertionPayload, ...]
    preview: PmxBoneInsertionPreview = field(init=False)
    serialized_bytes: bytes = field(init=False, repr=False)
    reparsed_certificate: PmxStructuralInvariantCertificate = field(init=False)
    output_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        self._derive_verified_evidence(None)

    @classmethod
    def _with_stage_callback(
        cls,
        source_document: PmxDocument,
        insertions: tuple[PmxBoneInsertionPayload, ...],
        stage_callback: _StructuralStageCallback,
    ) -> "_PmxBoneInsertionSerializationResult":
        result = object.__new__(cls)
        object.__setattr__(result, "source_document", source_document)
        object.__setattr__(result, "insertions", insertions)
        result._derive_verified_evidence(stage_callback)
        return result

    def _derive_verified_evidence(
        self,
        stage_callback: _StructuralStageCallback | None,
    ) -> None:
        if not isinstance(self.source_document, PmxDocument):
            raise TypeError("source_document must be a PmxDocument instance.")
        if type(self.insertions) is not tuple:
            raise TypeError("insertions must be a tuple.")
        if not self.insertions:
            raise ValueError(
                "bone insertion execution requires at least one insertion."
            )
        if not all(
            isinstance(insertion, PmxBoneInsertionPayload)
            for insertion in self.insertions
        ):
            raise TypeError(
                "insertions must contain only PmxBoneInsertionPayload values."
            )
        if stage_callback is not None and not callable(stage_callback):
            raise TypeError("stage_callback must be callable or None.")

        preview, serialized, reparsed_certificate, output_sha256 = (
            _derive_verified_structural_serialization(
                lambda: preview_pmx_bone_insertions(
                    self.source_document,
                    self.insertions,
                ),
                stage_callback,
            )
        )
        if not isinstance(preview, PmxBoneInsertionPreview):
            raise AssertionError(
                "bone insertion serialization returned wrong preview."
            )

        object.__setattr__(self, "preview", preview)
        object.__setattr__(self, "serialized_bytes", serialized)
        object.__setattr__(self, "reparsed_certificate", reparsed_certificate)
        object.__setattr__(self, "output_sha256", output_sha256)

    @property
    def output_size_bytes(self) -> int:
        return len(self.serialized_bytes)

    @property
    def status(self) -> str:
        return self.preview.status

    def to_dict(self) -> dict[str, object]:
        """Return deterministic JSON-ready verified-serialization evidence."""

        return _verified_serialization_report(
            self.preview,
            self.output_sha256,
            self.output_size_bytes,
        )


@dataclass(frozen=True, slots=True)
class _PmxMorphInsertionSerializationResult:
    """Verified serialization evidence for the CP13 morph insertion path."""

    source_document: PmxDocument
    insertions: tuple[PmxMorphInsertionPayload, ...]
    preview: PmxMorphInsertionPreview = field(init=False)
    serialized_bytes: bytes = field(init=False, repr=False)
    reparsed_certificate: PmxStructuralInvariantCertificate = field(init=False)
    output_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        self._derive_verified_evidence(None)

    @classmethod
    def _with_stage_callback(
        cls,
        source_document: PmxDocument,
        insertions: tuple[PmxMorphInsertionPayload, ...],
        stage_callback: _StructuralStageCallback,
    ) -> "_PmxMorphInsertionSerializationResult":
        result = object.__new__(cls)
        object.__setattr__(result, "source_document", source_document)
        object.__setattr__(result, "insertions", insertions)
        result._derive_verified_evidence(stage_callback)
        return result

    def _derive_verified_evidence(
        self,
        stage_callback: _StructuralStageCallback | None,
    ) -> None:
        if not isinstance(self.source_document, PmxDocument):
            raise TypeError("source_document must be a PmxDocument instance.")
        if type(self.insertions) is not tuple:
            raise TypeError("insertions must be a tuple.")
        if not self.insertions:
            raise ValueError(
                "morph insertion execution requires at least one insertion."
            )
        if not all(
            isinstance(insertion, PmxMorphInsertionPayload)
            for insertion in self.insertions
        ):
            raise TypeError(
                "insertions must contain only PmxMorphInsertionPayload values."
            )
        if stage_callback is not None and not callable(stage_callback):
            raise TypeError("stage_callback must be callable or None.")

        preview, serialized, reparsed_certificate, output_sha256 = (
            _derive_verified_structural_serialization(
                lambda: preview_pmx_morph_insertions(
                    self.source_document,
                    self.insertions,
                ),
                stage_callback,
            )
        )
        if not isinstance(preview, PmxMorphInsertionPreview):
            raise AssertionError(
                "morph insertion serialization returned wrong preview."
            )

        object.__setattr__(self, "preview", preview)
        object.__setattr__(self, "serialized_bytes", serialized)
        object.__setattr__(self, "reparsed_certificate", reparsed_certificate)
        object.__setattr__(self, "output_sha256", output_sha256)

    @property
    def output_size_bytes(self) -> int:
        return len(self.serialized_bytes)

    @property
    def status(self) -> str:
        return self.preview.status

    def to_dict(self) -> dict[str, object]:
        """Return deterministic JSON-ready verified-serialization evidence."""

        return _verified_serialization_report(
            self.preview,
            self.output_sha256,
            self.output_size_bytes,
        )


@dataclass(frozen=True, slots=True)
class _PmxRigidBodyInsertionSerializationResult:
    """Verified serialization evidence for the CP14 rigid-body insertion path."""

    source_document: PmxDocument
    insertions: tuple[PmxRigidBodyInsertionPayload, ...]
    preview: PmxRigidBodyInsertionPreview = field(init=False)
    serialized_bytes: bytes = field(init=False, repr=False)
    reparsed_certificate: PmxStructuralInvariantCertificate = field(init=False)
    output_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        self._derive_verified_evidence(None)

    @classmethod
    def _with_stage_callback(
        cls,
        source_document: PmxDocument,
        insertions: tuple[PmxRigidBodyInsertionPayload, ...],
        stage_callback: _StructuralStageCallback,
    ) -> "_PmxRigidBodyInsertionSerializationResult":
        result = object.__new__(cls)
        object.__setattr__(result, "source_document", source_document)
        object.__setattr__(result, "insertions", insertions)
        result._derive_verified_evidence(stage_callback)
        return result

    def _derive_verified_evidence(
        self,
        stage_callback: _StructuralStageCallback | None,
    ) -> None:
        if not isinstance(self.source_document, PmxDocument):
            raise TypeError("source_document must be a PmxDocument instance.")
        if type(self.insertions) is not tuple:
            raise TypeError("insertions must be a tuple.")
        if not self.insertions:
            raise ValueError(
                "rigid-body insertion execution requires at least one insertion."
            )
        if not all(
            isinstance(insertion, PmxRigidBodyInsertionPayload)
            for insertion in self.insertions
        ):
            raise TypeError(
                "insertions must contain only PmxRigidBodyInsertionPayload values."
            )
        if stage_callback is not None and not callable(stage_callback):
            raise TypeError("stage_callback must be callable or None.")

        preview, serialized, reparsed_certificate, output_sha256 = (
            _derive_verified_structural_serialization(
                lambda: preview_pmx_rigid_body_insertions(
                    self.source_document,
                    self.insertions,
                ),
                stage_callback,
            )
        )
        if not isinstance(preview, PmxRigidBodyInsertionPreview):
            raise AssertionError(
                "rigid-body insertion serialization returned wrong preview."
            )

        object.__setattr__(self, "preview", preview)
        object.__setattr__(self, "serialized_bytes", serialized)
        object.__setattr__(self, "reparsed_certificate", reparsed_certificate)
        object.__setattr__(self, "output_sha256", output_sha256)

    @property
    def output_size_bytes(self) -> int:
        return len(self.serialized_bytes)

    @property
    def status(self) -> str:
        return self.preview.status

    def to_dict(self) -> dict[str, object]:
        return _verified_serialization_report(
            self.preview,
            self.output_sha256,
            self.output_size_bytes,
        )


@dataclass(frozen=True, slots=True)
class _PmxVertexInsertionSerializationResult:
    """Verified serialization evidence for the CP16 vertex insertion path."""

    source_document: PmxDocument
    insertions: tuple[PmxVertexInsertionPayload, ...]
    preview: PmxVertexInsertionPreview = field(init=False)
    serialized_bytes: bytes = field(init=False, repr=False)
    reparsed_certificate: PmxStructuralInvariantCertificate = field(init=False)
    output_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        self._derive_verified_evidence(None)

    @classmethod
    def _with_stage_callback(
        cls,
        source_document: PmxDocument,
        insertions: tuple[PmxVertexInsertionPayload, ...],
        stage_callback: _StructuralStageCallback,
    ) -> "_PmxVertexInsertionSerializationResult":
        result = object.__new__(cls)
        object.__setattr__(result, "source_document", source_document)
        object.__setattr__(result, "insertions", insertions)
        result._derive_verified_evidence(stage_callback)
        return result

    def _derive_verified_evidence(
        self,
        stage_callback: _StructuralStageCallback | None,
    ) -> None:
        if not isinstance(self.source_document, PmxDocument):
            raise TypeError("source_document must be a PmxDocument instance.")
        if type(self.insertions) is not tuple:
            raise TypeError("insertions must be a tuple.")
        if not self.insertions:
            raise ValueError("vertex insertion execution requires at least one insertion.")
        if not all(
            isinstance(insertion, PmxVertexInsertionPayload)
            for insertion in self.insertions
        ):
            raise TypeError(
                "insertions must contain only PmxVertexInsertionPayload values."
            )
        if stage_callback is not None and not callable(stage_callback):
            raise TypeError("stage_callback must be callable or None.")

        preview, serialized, reparsed_certificate, output_sha256 = (
            _derive_verified_structural_serialization(
                lambda: preview_pmx_vertex_insertions(
                    self.source_document,
                    self.insertions,
                ),
                stage_callback,
            )
        )
        if not isinstance(preview, PmxVertexInsertionPreview):
            raise AssertionError(
                "vertex insertion serialization returned wrong preview."
            )

        object.__setattr__(self, "preview", preview)
        object.__setattr__(self, "serialized_bytes", serialized)
        object.__setattr__(self, "reparsed_certificate", reparsed_certificate)
        object.__setattr__(self, "output_sha256", output_sha256)

    @property
    def output_size_bytes(self) -> int:
        return len(self.serialized_bytes)

    @property
    def status(self) -> str:
        return self.preview.status

    def to_dict(self) -> dict[str, object]:
        return _verified_serialization_report(
            self.preview,
            self.output_sha256,
            self.output_size_bytes,
        )


@dataclass(frozen=True, slots=True)
class _PmxCoordinatedInsertionSerializationResult:
    """Verified serialization evidence for the CP17 coordinated insertion path."""

    source_document: PmxDocument
    payloads: PmxCoordinatedInsertionPayloads
    preview: PmxCoordinatedInsertionPreview = field(init=False)
    serialized_bytes: bytes = field(init=False, repr=False)
    reparsed_certificate: PmxStructuralInvariantCertificate = field(init=False)
    output_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        self._derive_verified_evidence(None)

    @classmethod
    def _with_stage_callback(
        cls,
        source_document: PmxDocument,
        payloads: PmxCoordinatedInsertionPayloads,
        stage_callback: _StructuralStageCallback,
    ) -> "_PmxCoordinatedInsertionSerializationResult":
        result = object.__new__(cls)
        object.__setattr__(result, "source_document", source_document)
        object.__setattr__(result, "payloads", payloads)
        result._derive_verified_evidence(stage_callback)
        return result

    def _derive_verified_evidence(
        self,
        stage_callback: _StructuralStageCallback | None,
    ) -> None:
        if not isinstance(self.source_document, PmxDocument):
            raise TypeError("source_document must be a PmxDocument instance.")
        if not isinstance(self.payloads, PmxCoordinatedInsertionPayloads):
            raise TypeError(
                "payloads must be a PmxCoordinatedInsertionPayloads value."
            )
        if stage_callback is not None and not callable(stage_callback):
            raise TypeError("stage_callback must be callable or None.")

        preview, serialized, reparsed_certificate, output_sha256 = (
            _derive_verified_structural_serialization(
                lambda: preview_pmx_coordinated_insertions(
                    self.source_document,
                    self.payloads,
                ),
                stage_callback,
            )
        )
        if not isinstance(preview, PmxCoordinatedInsertionPreview):
            raise AssertionError(
                "coordinated insertion serialization returned wrong preview."
            )

        object.__setattr__(self, "preview", preview)
        object.__setattr__(self, "serialized_bytes", serialized)
        object.__setattr__(self, "reparsed_certificate", reparsed_certificate)
        object.__setattr__(self, "output_sha256", output_sha256)

    @property
    def output_size_bytes(self) -> int:
        return len(self.serialized_bytes)

    @property
    def status(self) -> str:
        return self.preview.status

    def to_dict(self) -> dict[str, object]:
        return _verified_serialization_report(
            self.preview,
            self.output_sha256,
            self.output_size_bytes,
        )


def _verify_pmx_coordinated_insertion_serialization(
    document: PmxDocument,
    payloads: PmxCoordinatedInsertionPayloads,
    *,
    _stage_callback: _StructuralStageCallback | None = None,
) -> _PmxCoordinatedInsertionSerializationResult:
    if _stage_callback is None:
        return _PmxCoordinatedInsertionSerializationResult(
            source_document=document,
            payloads=payloads,
        )
    if not callable(_stage_callback):
        raise TypeError("_stage_callback must be callable or None.")
    return _PmxCoordinatedInsertionSerializationResult._with_stage_callback(
        document,
        payloads,
        _stage_callback,
    )


def verify_pmx_structural_serialization(
    document: PmxDocument,
    intent: PmxStructuralTransformIntent,
    *,
    _stage_callback: _StructuralStageCallback | None = None,
) -> PmxStructuralSerializationResult:
    """Return verified deterministic bytes without touching the filesystem."""

    if _stage_callback is None:
        return PmxStructuralSerializationResult(
            source_document=document,
            intent=intent,
        )
    if not callable(_stage_callback):
        raise TypeError("_stage_callback must be callable or None.")
    return PmxStructuralSerializationResult._with_stage_callback(
        document,
        intent,
        _stage_callback,
    )


def _verify_pmx_texture_insertion_serialization(
    document: PmxDocument,
    insertions: tuple[PmxTextureInsertionPayload, ...],
    *,
    _stage_callback: _StructuralStageCallback | None = None,
) -> _PmxTextureInsertionSerializationResult:
    """Return verified insertion bytes without exposing another mutation authority."""

    if _stage_callback is None:
        return _PmxTextureInsertionSerializationResult(
            source_document=document,
            insertions=insertions,
        )
    if not callable(_stage_callback):
        raise TypeError("_stage_callback must be callable or None.")
    return _PmxTextureInsertionSerializationResult._with_stage_callback(
        document,
        insertions,
        _stage_callback,
    )


def _verify_pmx_material_insertion_serialization(
    document: PmxDocument,
    insertions: tuple[PmxMaterialInsertionPayload, ...],
    *,
    _stage_callback: _StructuralStageCallback | None = None,
) -> _PmxMaterialInsertionSerializationResult:
    """Return verified material-insertion bytes through the shared safety kernel."""

    if _stage_callback is None:
        return _PmxMaterialInsertionSerializationResult(
            source_document=document,
            insertions=insertions,
        )
    if not callable(_stage_callback):
        raise TypeError("_stage_callback must be callable or None.")
    return _PmxMaterialInsertionSerializationResult._with_stage_callback(
        document,
        insertions,
        _stage_callback,
    )


def _verify_pmx_bone_insertion_serialization(
    document: PmxDocument,
    insertions: tuple[PmxBoneInsertionPayload, ...],
    *,
    _stage_callback: _StructuralStageCallback | None = None,
) -> _PmxBoneInsertionSerializationResult:
    """Return verified bone-insertion bytes through the shared safety kernel."""

    if _stage_callback is None:
        return _PmxBoneInsertionSerializationResult(
            source_document=document,
            insertions=insertions,
        )
    if not callable(_stage_callback):
        raise TypeError("_stage_callback must be callable or None.")
    return _PmxBoneInsertionSerializationResult._with_stage_callback(
        document,
        insertions,
        _stage_callback,
    )


def _verify_pmx_morph_insertion_serialization(
    document: PmxDocument,
    insertions: tuple[PmxMorphInsertionPayload, ...],
    *,
    _stage_callback: _StructuralStageCallback | None = None,
) -> _PmxMorphInsertionSerializationResult:
    """Return verified morph-insertion bytes through the shared safety kernel."""

    if _stage_callback is None:
        return _PmxMorphInsertionSerializationResult(
            source_document=document,
            insertions=insertions,
        )
    if not callable(_stage_callback):
        raise TypeError("_stage_callback must be callable or None.")
    return _PmxMorphInsertionSerializationResult._with_stage_callback(
        document,
        insertions,
        _stage_callback,
    )


def _verify_pmx_rigid_body_insertion_serialization(
    document: PmxDocument,
    insertions: tuple[PmxRigidBodyInsertionPayload, ...],
    *,
    _stage_callback: _StructuralStageCallback | None = None,
) -> _PmxRigidBodyInsertionSerializationResult:
    """Return verified rigid-body insertion bytes through the shared kernel."""

    if _stage_callback is None:
        return _PmxRigidBodyInsertionSerializationResult(
            source_document=document,
            insertions=insertions,
        )
    if not callable(_stage_callback):
        raise TypeError("_stage_callback must be callable or None.")
    return _PmxRigidBodyInsertionSerializationResult._with_stage_callback(
        document,
        insertions,
        _stage_callback,
    )


def _verify_pmx_vertex_insertion_serialization(
    document: PmxDocument,
    insertions: tuple[PmxVertexInsertionPayload, ...],
    *,
    _stage_callback: _StructuralStageCallback | None = None,
) -> _PmxVertexInsertionSerializationResult:
    """Return verified vertex-insertion bytes through the shared safety kernel."""

    if _stage_callback is None:
        return _PmxVertexInsertionSerializationResult(
            source_document=document,
            insertions=insertions,
        )
    if not callable(_stage_callback):
        raise TypeError("_stage_callback must be callable or None.")
    return _PmxVertexInsertionSerializationResult._with_stage_callback(
        document,
        insertions,
        _stage_callback,
    )


@dataclass(frozen=True, slots=True, init=False)
class PmxStructuralWriteResult:
    """Report whose supported creation path follows successful atomic commit."""

    input_path: Path
    output_path: Path
    source_sha256: str
    source_size_bytes: int
    serialization: (
        PmxStructuralSerializationResult
        | _PmxTextureInsertionSerializationResult
        | _PmxMaterialInsertionSerializationResult
        | _PmxBoneInsertionSerializationResult
        | _PmxMorphInsertionSerializationResult
        | _PmxRigidBodyInsertionSerializationResult
        | _PmxVertexInsertionSerializationResult
        | _PmxCoordinatedInsertionSerializationResult
    )

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
        serialization: (
            PmxStructuralSerializationResult
            | _PmxTextureInsertionSerializationResult
            | _PmxMaterialInsertionSerializationResult
            | _PmxBoneInsertionSerializationResult
            | _PmxMorphInsertionSerializationResult
            | _PmxRigidBodyInsertionSerializationResult
            | _PmxVertexInsertionSerializationResult
            | _PmxCoordinatedInsertionSerializationResult
        ),
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
        if not isinstance(
            serialization,
            (
                PmxStructuralSerializationResult,
                _PmxTextureInsertionSerializationResult,
                _PmxMaterialInsertionSerializationResult,
                _PmxBoneInsertionSerializationResult,
                _PmxMorphInsertionSerializationResult,
                _PmxRigidBodyInsertionSerializationResult,
                _PmxVertexInsertionSerializationResult,
                _PmxCoordinatedInsertionSerializationResult,
            ),
        ):
            raise TypeError(
                "serialization must be a verified structural serialization value."
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


def _write_verified_structural_transaction(
    input_path: str | Path,
    output_path: str | Path,
    serialization_factory: Callable[
        [PmxDocument, _StructuralStageCallback | None],
        (
            PmxStructuralSerializationResult
            | _PmxTextureInsertionSerializationResult
            | _PmxMaterialInsertionSerializationResult
            | _PmxBoneInsertionSerializationResult
            | _PmxMorphInsertionSerializationResult
            | _PmxRigidBodyInsertionSerializationResult
            | _PmxVertexInsertionSerializationResult
            | _PmxCoordinatedInsertionSerializationResult
        ),
    ],
    *,
    overwrite: bool = False,
    _stage_callback: _StructuralStageCallback | None = None,
) -> PmxStructuralWriteResult:
    """Run the one structural filesystem transaction around verified serialization."""

    if not callable(serialization_factory):
        raise TypeError("serialization_factory must be callable.")
    if not isinstance(overwrite, bool):
        raise TypeError("overwrite must be a boolean.")
    if _stage_callback is not None and not callable(_stage_callback):
        raise TypeError("_stage_callback must be callable or None.")

    _notify_structural_stage(_stage_callback, "path_resolution")
    try:
        requested_source, source, destination = _edit_output._resolve_edit_paths(
            input_path,
            output_path,
            overwrite=overwrite,
        )
    except PmxEditPathError as error:
        _translate_edit_path_error(error)
        raise AssertionError("unreachable")

    _notify_structural_stage(_stage_callback, "source_snapshot")
    source_identity = _edit_output._file_identity(source)
    source_bytes = source.read_bytes()
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()

    _notify_structural_stage(_stage_callback, "source_parse")
    source_document = load_pmx(io.BytesIO(source_bytes))

    _notify_structural_stage(_stage_callback, "intent_resolution")
    serialization = serialization_factory(source_document, _stage_callback)
    if not isinstance(
        serialization,
        (
            PmxStructuralSerializationResult,
            _PmxTextureInsertionSerializationResult,
            _PmxMaterialInsertionSerializationResult,
            _PmxBoneInsertionSerializationResult,
            _PmxMorphInsertionSerializationResult,
            _PmxRigidBodyInsertionSerializationResult,
            _PmxVertexInsertionSerializationResult,
            _PmxCoordinatedInsertionSerializationResult,
        ),
    ):
        raise TypeError(
            "serialization_factory must return verified structural serialization."
        )

    _notify_structural_stage(_stage_callback, "output_commit")
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


def _write_pmx_structural_transaction(
    input_path: str | Path,
    output_path: str | Path,
    intent_factory: Callable[[PmxDocument], PmxStructuralTransformIntent],
    *,
    overwrite: bool = False,
    _stage_callback: _StructuralStageCallback | None = None,
) -> PmxStructuralWriteResult:
    """Execute one legacy structural write against one captured source snapshot."""

    if not callable(intent_factory):
        raise TypeError("intent_factory must be callable.")

    def serialize_legacy(
        source_document: PmxDocument,
        stage_callback: _StructuralStageCallback | None,
    ) -> PmxStructuralSerializationResult:
        intent = intent_factory(source_document)
        if not isinstance(intent, PmxStructuralTransformIntent):
            raise TypeError(
                "intent_factory must return a PmxStructuralTransformIntent value."
            )
        return verify_pmx_structural_serialization(
            source_document,
            intent,
            _stage_callback=stage_callback,
        )

    return _write_verified_structural_transaction(
        input_path,
        output_path,
        serialize_legacy,
        overwrite=overwrite,
        _stage_callback=_stage_callback,
    )


def _write_pmx_texture_insertion_transaction(
    input_path: str | Path,
    output_path: str | Path,
    insertions: tuple[PmxTextureInsertionPayload, ...],
    *,
    overwrite: bool = False,
    _stage_callback: _StructuralStageCallback | None = None,
) -> PmxStructuralWriteResult:
    """Execute CP08 texture insertion through the shared structural transaction."""

    if type(insertions) is not tuple:
        raise TypeError("insertions must be a tuple.")
    if not insertions:
        raise ValueError("texture insertion execution requires at least one insertion.")
    if not all(
        isinstance(insertion, PmxTextureInsertionPayload) for insertion in insertions
    ):
        raise TypeError(
            "insertions must contain only PmxTextureInsertionPayload values."
        )

    def serialize_insertions(
        source_document: PmxDocument,
        stage_callback: _StructuralStageCallback | None,
    ) -> _PmxTextureInsertionSerializationResult:
        return _verify_pmx_texture_insertion_serialization(
            source_document,
            insertions,
            _stage_callback=stage_callback,
        )

    return _write_verified_structural_transaction(
        input_path,
        output_path,
        serialize_insertions,
        overwrite=overwrite,
        _stage_callback=_stage_callback,
    )


def _write_pmx_material_insertion_transaction(
    input_path: str | Path,
    output_path: str | Path,
    insertions: tuple[PmxMaterialInsertionPayload, ...],
    *,
    overwrite: bool = False,
    _stage_callback: _StructuralStageCallback | None = None,
) -> PmxStructuralWriteResult:
    """Execute CP10 material insertion through the shared structural transaction."""

    if type(insertions) is not tuple:
        raise TypeError("insertions must be a tuple.")
    if not insertions:
        raise ValueError("material insertion execution requires at least one insertion.")
    if not all(
        isinstance(insertion, PmxMaterialInsertionPayload) for insertion in insertions
    ):
        raise TypeError(
            "insertions must contain only PmxMaterialInsertionPayload values."
        )

    def serialize_insertions(
        source_document: PmxDocument,
        stage_callback: _StructuralStageCallback | None,
    ) -> _PmxMaterialInsertionSerializationResult:
        return _verify_pmx_material_insertion_serialization(
            source_document,
            insertions,
            _stage_callback=stage_callback,
        )

    return _write_verified_structural_transaction(
        input_path,
        output_path,
        serialize_insertions,
        overwrite=overwrite,
        _stage_callback=_stage_callback,
    )


def _write_pmx_bone_insertion_transaction(
    input_path: str | Path,
    output_path: str | Path,
    insertions: tuple[PmxBoneInsertionPayload, ...],
    *,
    overwrite: bool = False,
    _stage_callback: _StructuralStageCallback | None = None,
) -> PmxStructuralWriteResult:
    """Execute CP12 bone insertion through the shared structural transaction."""

    if type(insertions) is not tuple:
        raise TypeError("insertions must be a tuple.")
    if not insertions:
        raise ValueError("bone insertion execution requires at least one insertion.")
    if not all(
        isinstance(insertion, PmxBoneInsertionPayload) for insertion in insertions
    ):
        raise TypeError(
            "insertions must contain only PmxBoneInsertionPayload values."
        )

    def serialize_insertions(
        source_document: PmxDocument,
        stage_callback: _StructuralStageCallback | None,
    ) -> _PmxBoneInsertionSerializationResult:
        return _verify_pmx_bone_insertion_serialization(
            source_document,
            insertions,
            _stage_callback=stage_callback,
        )

    return _write_verified_structural_transaction(
        input_path,
        output_path,
        serialize_insertions,
        overwrite=overwrite,
        _stage_callback=_stage_callback,
    )


def _write_pmx_morph_insertion_transaction(
    input_path: str | Path,
    output_path: str | Path,
    insertions: tuple[PmxMorphInsertionPayload, ...],
    *,
    overwrite: bool = False,
    _stage_callback: _StructuralStageCallback | None = None,
) -> PmxStructuralWriteResult:
    """Execute CP13 morph insertion through the shared structural transaction."""

    if type(insertions) is not tuple:
        raise TypeError("insertions must be a tuple.")
    if not insertions:
        raise ValueError("morph insertion execution requires at least one insertion.")
    if not all(
        isinstance(insertion, PmxMorphInsertionPayload) for insertion in insertions
    ):
        raise TypeError(
            "insertions must contain only PmxMorphInsertionPayload values."
        )

    def serialize_insertions(
        source_document: PmxDocument,
        stage_callback: _StructuralStageCallback | None,
    ) -> _PmxMorphInsertionSerializationResult:
        return _verify_pmx_morph_insertion_serialization(
            source_document,
            insertions,
            _stage_callback=stage_callback,
        )

    return _write_verified_structural_transaction(
        input_path,
        output_path,
        serialize_insertions,
        overwrite=overwrite,
        _stage_callback=_stage_callback,
    )


def _write_pmx_rigid_body_insertion_transaction(
    input_path: str | Path,
    output_path: str | Path,
    insertions: tuple[PmxRigidBodyInsertionPayload, ...],
    *,
    overwrite: bool = False,
    _stage_callback: _StructuralStageCallback | None = None,
) -> PmxStructuralWriteResult:
    """Execute CP14 rigid-body insertion through the shared transaction."""

    if type(insertions) is not tuple:
        raise TypeError("insertions must be a tuple.")
    if not insertions:
        raise ValueError(
            "rigid-body insertion execution requires at least one insertion."
        )
    if not all(
        isinstance(insertion, PmxRigidBodyInsertionPayload)
        for insertion in insertions
    ):
        raise TypeError(
            "insertions must contain only PmxRigidBodyInsertionPayload values."
        )

    def serialize_insertions(
        source_document: PmxDocument,
        stage_callback: _StructuralStageCallback | None,
    ) -> _PmxRigidBodyInsertionSerializationResult:
        return _verify_pmx_rigid_body_insertion_serialization(
            source_document,
            insertions,
            _stage_callback=stage_callback,
        )

    return _write_verified_structural_transaction(
        input_path,
        output_path,
        serialize_insertions,
        overwrite=overwrite,
        _stage_callback=_stage_callback,
    )


def _write_pmx_vertex_insertion_transaction(
    input_path: str | Path,
    output_path: str | Path,
    insertions: tuple[PmxVertexInsertionPayload, ...],
    *,
    overwrite: bool = False,
    _stage_callback: _StructuralStageCallback | None = None,
) -> PmxStructuralWriteResult:
    """Execute CP16 vertex insertion through the shared structural transaction."""

    if type(insertions) is not tuple:
        raise TypeError("insertions must be a tuple.")
    if not insertions:
        raise ValueError("vertex insertion execution requires at least one insertion.")
    if not all(
        isinstance(insertion, PmxVertexInsertionPayload)
        for insertion in insertions
    ):
        raise TypeError(
            "insertions must contain only PmxVertexInsertionPayload values."
        )

    def serialize_insertions(
        source_document: PmxDocument,
        stage_callback: _StructuralStageCallback | None,
    ) -> _PmxVertexInsertionSerializationResult:
        return _verify_pmx_vertex_insertion_serialization(
            source_document,
            insertions,
            _stage_callback=stage_callback,
        )

    return _write_verified_structural_transaction(
        input_path,
        output_path,
        serialize_insertions,
        overwrite=overwrite,
        _stage_callback=_stage_callback,
    )


def _write_pmx_coordinated_insertion_transaction(
    input_path: str | Path,
    output_path: str | Path,
    payload_factory: Callable[[PmxDocument], PmxCoordinatedInsertionPayloads],
    *,
    overwrite: bool = False,
    _stage_callback: _StructuralStageCallback | None = None,
) -> PmxStructuralWriteResult:
    """Execute CP17 multi-target insertion through the shared transaction kernel."""

    if not callable(payload_factory):
        raise TypeError("payload_factory must be callable.")

    def serialize_insertions(
        source_document: PmxDocument,
        stage_callback: _StructuralStageCallback | None,
    ) -> _PmxCoordinatedInsertionSerializationResult:
        payloads = payload_factory(source_document)
        if not isinstance(payloads, PmxCoordinatedInsertionPayloads):
            raise TypeError(
                "payload_factory must return PmxCoordinatedInsertionPayloads."
            )
        return _verify_pmx_coordinated_insertion_serialization(
            source_document,
            payloads,
            _stage_callback=stage_callback,
        )

    return _write_verified_structural_transaction(
        input_path,
        output_path,
        serialize_insertions,
        overwrite=overwrite,
        _stage_callback=_stage_callback,
    )


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

    return _write_pmx_structural_transaction(
        input_path,
        output_path,
        lambda _source_document: intent,
        overwrite=overwrite,
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
