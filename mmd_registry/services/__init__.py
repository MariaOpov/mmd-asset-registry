"""Typed side-effect-controlled service boundary for reusable PMX clients."""

from __future__ import annotations

from dataclasses import dataclass
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
from mmd_registry.pmx.document import PmxDocument
from mmd_registry.pmx.editing.output import PmxEditWriteResult, write_pmx_edit
from mmd_registry.pmx.editing.plan import PmxEditPlan
from mmd_registry.pmx.editing.preview import PmxEditPreview, dry_run_pmx_edit
from mmd_registry.pmx.errors import PmxValidationError, PmxValidationIssue
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
)
