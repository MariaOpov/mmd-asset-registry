"""Typed side-effect-controlled service boundary for reusable PMX clients."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

from mmd_registry.capabilities import (
    PmxCapabilityManifest,
    get_capabilities,
)
from mmd_registry.diagnostics import (
    PmxServiceError,
    PmxServiceOperation,
    diagnostic_from_service_error,
)
from mmd_registry.pmx.collection_transform import (
    PmxCollectionTransform,
    PmxStructuralTransformIntent,
)
from mmd_registry.pmx.document import PmxDocument
from mmd_registry.pmx.editing.output import PmxEditWriteResult, write_pmx_edit
from mmd_registry.pmx.editing.plan import PmxEditPlan
from mmd_registry.pmx.editing.preview import PmxEditPreview, dry_run_pmx_edit
from mmd_registry.pmx.errors import PmxValidationError, PmxValidationIssue
from mmd_registry.pmx.index_remap import PmxIndexRemap
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.reference_diagnostics import (
    PmxReferenceDiagnostic,
    PmxReferenceDiagnosticCode,
    diagnose_reference_graph,
)
from mmd_registry.pmx.reference_graph import (
    PmxReferenceGraph,
    extract_pmx_reference_graph,
)
from mmd_registry.pmx.reference_model import (
    PmxReferenceNode,
    PmxReferenceTargetKind,
)
from mmd_registry.pmx.reference_queries import (
    PmxReferenceImpact,
    analyze_reference_impact,
)
from mmd_registry.pmx.structural_preview import (
    PmxStructuralPreview as _PmxStructuralPreview,
    preview_pmx_structural_transform as _preview_pmx_structural_transform,
)
from mmd_registry.pmx.validation import validate_pmx_document


@dataclass(frozen=True, slots=True)
class PmxDocumentMetadata:
    """Immutable model metadata exposed without leaking a CLI representation."""

    version: float
    encoding: str
    local_name: str
    universal_name: str
    local_comments: str
    universal_comments: str

    def __post_init__(self) -> None:
        if not isinstance(self.version, float):
            raise TypeError("version must be a float.")
        for field_name in (
            "encoding",
            "local_name",
            "universal_name",
            "local_comments",
            "universal_comments",
        ):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"{field_name} must be a string.")


@dataclass(frozen=True, slots=True)
class PmxDocumentValidationResult:
    """Immutable deterministic semantic-validation outcome."""

    issues: tuple[PmxValidationIssue, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.issues, tuple):
            raise TypeError("issues must be a tuple.")
        if not all(isinstance(issue, PmxValidationIssue) for issue in self.issues):
            raise TypeError("issues must contain only PmxValidationIssue values.")

    @property
    def is_valid(self) -> bool:
        """Return whether semantic validation found no issue."""

        return not self.issues

    def to_dict(self) -> dict[str, object]:
        """Return a deterministic JSON-ready validation payload."""

        return {
            "is_valid": self.is_valid,
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class PmxReferenceAnalysisResult:
    """Immutable reference-analysis snapshot for reusable public clients."""

    graph: PmxReferenceGraph
    diagnostics: tuple[PmxReferenceDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.graph, PmxReferenceGraph):
            raise TypeError("graph must be a PmxReferenceGraph value.")
        if type(self.diagnostics) is not tuple:
            raise TypeError("diagnostics must be a tuple.")
        if not all(
            isinstance(item, PmxReferenceDiagnostic)
            for item in self.diagnostics
        ):
            raise TypeError(
                "diagnostics must contain only PmxReferenceDiagnostic values."
            )

        expected_diagnostics = diagnose_reference_graph(self.graph)
        if self.diagnostics != expected_diagnostics:
            raise ValueError(
                "diagnostics must exactly match diagnostics derived from graph."
            )

    @property
    def is_clean(self) -> bool:
        """Whether extraction produced no invalid or unsupported evidence."""

        return not self.diagnostics

    @property
    def relationship_counts(self) -> tuple[tuple[str, int], ...]:
        """Return deterministic counts of valid edges by relationship ID."""

        counts: dict[str, int] = {}
        for edge in self.graph.edges:
            counts[edge.relationship_id] = counts.get(edge.relationship_id, 0) + 1
        return tuple(sorted(counts.items()))

    def to_dict(self) -> dict[str, object]:
        """Return a deterministic JSON-ready analysis summary."""

        counts = self.graph.target_counts
        return {
            "is_clean": self.is_clean,
            "target_counts": {
                "vertex": counts.vertex,
                "texture": counts.texture,
                "material": counts.material,
                "bone": counts.bone,
                "morph": counts.morph,
                "rigid_body": counts.rigid_body,
            },
            "edge_count": len(self.graph.edges),
            "relationship_counts": dict(self.relationship_counts),
            "invalid_target_count": len(self.graph.invalid_targets),
            "unsupported_state_count": len(self.graph.unsupported_states),
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }


@dataclass(frozen=True, slots=True)
class PmxStructuralCollectionEdit:
    """One preview-only delete/reorder request for a structural target collection."""

    target_kind: PmxReferenceTargetKind
    old_indices_in_new_order: tuple[int, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.target_kind, PmxReferenceTargetKind):
            raise TypeError("target_kind must be a PmxReferenceTargetKind value.")
        if type(self.old_indices_in_new_order) is not tuple:
            raise TypeError("old_indices_in_new_order must be a tuple.")
        if any(type(index) is not int for index in self.old_indices_in_new_order):
            raise TypeError(
                "old_indices_in_new_order must contain only integer indices."
            )
        if any(index < 0 for index in self.old_indices_in_new_order):
            raise ValueError("old_indices_in_new_order cannot contain negative indices.")
        if len(set(self.old_indices_in_new_order)) != len(
            self.old_indices_in_new_order
        ):
            raise ValueError("old_indices_in_new_order cannot contain duplicates.")


@dataclass(frozen=True, slots=True)
class PmxStructuralPreviewRequest:
    """Immutable public request for reference-safe structural preview only."""

    collection_edits: tuple[PmxStructuralCollectionEdit, ...] = ()

    def __post_init__(self) -> None:
        if type(self.collection_edits) is not tuple:
            raise TypeError("collection_edits must be a tuple.")
        if not all(
            isinstance(edit, PmxStructuralCollectionEdit)
            for edit in self.collection_edits
        ):
            raise TypeError(
                "collection_edits must contain only PmxStructuralCollectionEdit values."
            )
        kinds = tuple(edit.target_kind for edit in self.collection_edits)
        if len(set(kinds)) != len(kinds):
            raise ValueError("collection_edits cannot repeat one target_kind.")


@dataclass(frozen=True, slots=True)
class PmxStructuralPreviewResult:
    """Service-facing structural preview without exporting CP17 implementation types."""

    _preview: _PmxStructuralPreview = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self._preview, _PmxStructuralPreview):
            raise TypeError("_preview must be an internal PmxStructuralPreview value.")

    @property
    def status(self) -> str:
        """Return the stable preview status."""

        return self._preview.status

    @property
    def document(self) -> PmxDocument:
        """Return the certified intended document represented by this preview."""

        return self._preview.certificate.document

    def to_dict(self) -> dict[str, object]:
        """Return deterministic JSON-ready preview evidence."""

        return self._preview.to_dict()


_STRUCTURAL_TARGET_ORDER = tuple(PmxReferenceTargetKind)


def _structural_target_rank(target_kind: PmxReferenceTargetKind) -> int:
    return _STRUCTURAL_TARGET_ORDER.index(target_kind)


def _structural_target_size(
    document: PmxDocument,
    target_kind: PmxReferenceTargetKind,
) -> int:
    if target_kind is PmxReferenceTargetKind.VERTEX:
        return len(document.vertices)
    if target_kind is PmxReferenceTargetKind.TEXTURE:
        return len(document.texture_paths)
    if target_kind is PmxReferenceTargetKind.MATERIAL:
        return len(document.materials)
    if target_kind is PmxReferenceTargetKind.BONE:
        return len(document.bones)
    if target_kind is PmxReferenceTargetKind.MORPH:
        return len(document.morphs)
    if target_kind is PmxReferenceTargetKind.RIGID_BODY:
        return len(document.rigid_bodies)
    raise AssertionError(f"unsupported structural target kind: {target_kind!r}")


def _build_structural_preview_intent(
    document: PmxDocument,
    request: PmxStructuralPreviewRequest,
) -> PmxStructuralTransformIntent:
    transforms: list[PmxCollectionTransform] = []
    edits = sorted(
        request.collection_edits,
        key=lambda edit: _structural_target_rank(edit.target_kind),
    )
    for edit in edits:
        old_size = _structural_target_size(document, edit.target_kind)
        for old_index in edit.old_indices_in_new_order:
            if old_index >= old_size:
                raise ValueError(
                    f"{edit.target_kind.value} old index {old_index} "
                    f"is out of range for collection size {old_size}."
                )

        targets: list[int | None] = [None] * old_size
        for new_index, old_index in enumerate(edit.old_indices_in_new_order):
            targets[old_index] = new_index

        transforms.append(
            PmxCollectionTransform(
                kind=edit.target_kind,
                remap=PmxIndexRemap(
                    targets=tuple(targets),
                    new_size=len(edit.old_indices_in_new_order),
                ),
            )
        )

    return PmxStructuralTransformIntent(transforms=tuple(transforms))


def preview_structural_edit(
    document: PmxDocument,
    request: PmxStructuralPreviewRequest,
) -> PmxStructuralPreviewResult:
    """Return a deterministic reference-safe structural preview without writing."""

    try:
        if not isinstance(document, PmxDocument):
            raise TypeError("document must be a PmxDocument instance.")
        if not isinstance(request, PmxStructuralPreviewRequest):
            raise TypeError("request must be a PmxStructuralPreviewRequest instance.")
        intent = _build_structural_preview_intent(document, request)
        return PmxStructuralPreviewResult(
            _preview_pmx_structural_transform(document, intent)
        )
    except Exception as error:
        failure = PmxServiceError(
            diagnostic_from_service_error(
                PmxServiceOperation.PREVIEW_STRUCTURAL_EDIT,
                error,
            )
        )
    raise failure from None


def load_document(source: str | Path | BinaryIO) -> PmxDocument:
    """Load one typed PMX document or raise one structured service failure."""

    try:
        return load_pmx(source)
    except Exception as error:
        failure = PmxServiceError(
            diagnostic_from_service_error(
                PmxServiceOperation.LOAD_DOCUMENT,
                error,
            )
        )
    raise failure from None


def inspect_document(document: PmxDocument) -> PmxDocumentMetadata:
    """Return immutable metadata or raise one structured service failure."""

    try:
        if not isinstance(document, PmxDocument):
            raise TypeError("document must be a PmxDocument instance.")
        model_info = document.model_info
        return PmxDocumentMetadata(
            version=document.header.version,
            encoding=document.header.encoding,
            local_name=model_info.local_name,
            universal_name=model_info.universal_name,
            local_comments=model_info.local_comments,
            universal_comments=model_info.universal_comments,
        )
    except Exception as error:
        failure = PmxServiceError(
            diagnostic_from_service_error(
                PmxServiceOperation.INSPECT_DOCUMENT,
                error,
            )
        )
    raise failure from None


def validate_document(document: PmxDocument) -> PmxDocumentValidationResult:
    """Return a deterministic result or raise one structured service failure."""

    try:
        if not isinstance(document, PmxDocument):
            raise TypeError("document must be a PmxDocument instance.")
        try:
            validate_pmx_document(document)
        except PmxValidationError as error:
            return PmxDocumentValidationResult(issues=(error.issue,))
        return PmxDocumentValidationResult()
    except Exception as error:
        failure = PmxServiceError(
            diagnostic_from_service_error(
                PmxServiceOperation.VALIDATE_DOCUMENT,
                error,
            )
        )
    raise failure from None


def analyze_references(document: PmxDocument) -> PmxReferenceAnalysisResult:
    """Extract one deterministic reference snapshot without prevalidation."""

    try:
        if not isinstance(document, PmxDocument):
            raise TypeError("document must be a PmxDocument instance.")
        graph = extract_pmx_reference_graph(document)
        return PmxReferenceAnalysisResult(
            graph=graph,
            diagnostics=diagnose_reference_graph(graph),
        )
    except Exception as error:
        failure = PmxServiceError(
            diagnostic_from_service_error(
                PmxServiceOperation.ANALYZE_REFERENCES,
                error,
            )
        )
    raise failure from None


def analyze_reference_node(
    analysis: PmxReferenceAnalysisResult,
    node: PmxReferenceNode,
) -> PmxReferenceImpact:
    """Return conservative direct impact from an existing analysis snapshot."""

    try:
        if not isinstance(analysis, PmxReferenceAnalysisResult):
            raise TypeError(
                "analysis must be a PmxReferenceAnalysisResult instance."
            )
        if not isinstance(node, PmxReferenceNode):
            raise TypeError("node must be a PmxReferenceNode instance.")
        return analyze_reference_impact(analysis.graph, node)
    except Exception as error:
        failure = PmxServiceError(
            diagnostic_from_service_error(
                PmxServiceOperation.ANALYZE_REFERENCE_NODE,
                error,
            )
        )
    raise failure from None


def preview_edit(source_bytes: bytes, plan: PmxEditPlan) -> PmxEditPreview:
    """Return a verified edit preview or one structured service failure."""

    try:
        return dry_run_pmx_edit(source_bytes, plan)
    except Exception as error:
        failure = PmxServiceError(
            diagnostic_from_service_error(
                PmxServiceOperation.PREVIEW_EDIT,
                error,
            )
        )
    raise failure from None


def apply_edit(
    input_path: str | Path,
    output_path: str | Path,
    plan: PmxEditPlan,
    *,
    overwrite: bool = False,
) -> PmxEditWriteResult:
    """Safely write one verified edit or raise a structured service failure."""

    try:
        return write_pmx_edit(
            input_path,
            output_path,
            plan,
            overwrite=overwrite,
        )
    except Exception as error:
        failure = PmxServiceError(
            diagnostic_from_service_error(
                PmxServiceOperation.APPLY_EDIT,
                error,
            )
        )
    raise failure from None


__all__ = (
    "PmxDocumentMetadata",
    "PmxDocumentValidationResult",
    "apply_edit",
    "get_capabilities",
    "inspect_document",
    "load_document",
    "preview_edit",
    "validate_document",
    "PmxReferenceAnalysisResult",
    "PmxReferenceDiagnostic",
    "PmxReferenceDiagnosticCode",
    "PmxReferenceImpact",
    "PmxReferenceNode",
    "PmxReferenceTargetKind",
    "analyze_reference_node",
    "analyze_references",
    "PmxStructuralCollectionEdit",
    "PmxStructuralPreviewRequest",
    "PmxStructuralPreviewResult",
    "preview_structural_edit",
)
