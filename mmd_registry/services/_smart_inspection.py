"""Read-only orchestration for v0.9.5.5 Smart Inspect."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import mmd_registry.services as _service_root
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.services.structural_authoring_catalog import (
    PMX_STRUCTURAL_AUTHORING_CATALOG_MAX_LIMIT,
    PmxStructuralAuthoringCatalogEntry,
    inspect_structural_authoring_catalog,
)
from mmd_registry.smart_part_confidence import (
    SmartPartConfidenceAssessment,
    assess_smart_parts,
)
from mmd_registry.smart_part_detection import detect_smart_parts
from mmd_registry.smart_part_explainability import (
    SmartPartExplanation,
    explain_smart_parts,
)
from mmd_registry.smart_parts import SmartPart


_SEMANTIC_TARGET_KINDS: tuple[PmxReferenceTargetKind, ...] = (
    PmxReferenceTargetKind.TEXTURE,
    PmxReferenceTargetKind.MATERIAL,
    PmxReferenceTargetKind.BONE,
    PmxReferenceTargetKind.MORPH,
)


@dataclass(frozen=True, slots=True)
class SmartInspectionResult:
    """Immutable read-only Smart semantic inspection result."""

    entries: tuple[PmxStructuralAuthoringCatalogEntry, ...]
    parts: tuple[SmartPart, ...]
    explanations: tuple[SmartPartExplanation, ...]
    assessments: tuple[SmartPartConfidenceAssessment, ...]

    def __post_init__(self) -> None:
        if type(self.entries) is not tuple:
            raise TypeError("entries must be a tuple.")
        if type(self.parts) is not tuple:
            raise TypeError("parts must be a tuple.")
        if type(self.explanations) is not tuple:
            raise TypeError("explanations must be a tuple.")
        if type(self.assessments) is not tuple:
            raise TypeError("assessments must be a tuple.")


def _collect_semantic_entries(document: object) -> tuple[PmxStructuralAuthoringCatalogEntry, ...]:
    entries: list[PmxStructuralAuthoringCatalogEntry] = []

    for target_kind in _SEMANTIC_TARGET_KINDS:
        offset = 0

        while True:
            page = inspect_structural_authoring_catalog(
                document,  # type: ignore[arg-type]
                target_kind,
                offset=offset,
                limit=PMX_STRUCTURAL_AUTHORING_CATALOG_MAX_LIMIT,
            )
            entries.extend(page.entries)
            next_offset = offset + page.returned_count

            if next_offset >= page.total_count:
                break
            if page.returned_count == 0:
                raise RuntimeError(
                    "Structural authoring catalog pagination made no progress."
                )

            offset = next_offset

    return tuple(entries)


def _analyze_entries(
    entries: tuple[PmxStructuralAuthoringCatalogEntry, ...],
) -> SmartInspectionResult:
    return SmartInspectionResult(
        entries=entries,
        parts=detect_smart_parts(entries),
        explanations=explain_smart_parts(entries),
        assessments=assess_smart_parts(entries),
    )


def inspect_smart_parts(source: str | Path) -> SmartInspectionResult:
    """Load one PMX and return deterministic read-only Smart semantic analysis."""

    document = _service_root.load_document(source)
    return _analyze_entries(_collect_semantic_entries(document))
