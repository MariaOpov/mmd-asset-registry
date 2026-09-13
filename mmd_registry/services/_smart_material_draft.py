"""Private source-bound Smart material grouping, capability, and color draft."""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from enum import Enum

from mmd_registry.pmx import load_pmx
from mmd_registry.pmx.document import PmxDocument
from mmd_registry.pmx.editing.operations import UpdateMaterial
from mmd_registry.pmx.editing.plan import PmxEditPlan
from mmd_registry.services import _smart_inspection
from mmd_registry.services._smart_inspection import SmartInspectionResult
from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringMaterialCatalogEntry,
)
from mmd_registry.smart_part_confidence import SmartPartConfidence
from mmd_registry.smart_parts import (
    SmartPartEvidence,
    SmartPartEvidenceKind,
    SmartPartKind,
)
from mmd_registry._smart_material_color import (
    SmartMaterialColorInput,
    normalize_smart_material_color,
)


@dataclass(frozen=True, slots=True)
class SmartMaterialGroup:
    """Exact material targets for one resolved Smart Part."""

    part_kind: SmartPartKind
    material_indices: tuple[int, ...]
    evidence: tuple[SmartPartEvidence, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.part_kind, SmartPartKind):
            raise TypeError("part_kind must be a SmartPartKind value.")
        if type(self.material_indices) is not tuple:
            raise TypeError("material_indices must be a tuple.")
        if any(type(index) is not int or index < 0 for index in self.material_indices):
            raise ValueError("material_indices must contain nonnegative integers.")
        if self.material_indices != tuple(sorted(set(self.material_indices))):
            raise ValueError("material_indices must be unique and ascending.")
        if type(self.evidence) is not tuple:
            raise TypeError("evidence must be a tuple.")
        if not all(isinstance(item, SmartPartEvidence) for item in self.evidence):
            raise TypeError("evidence must contain only SmartPartEvidence values.")
        if any(
            item.source_kind is not SmartPartEvidenceKind.MATERIAL
            for item in self.evidence
        ):
            raise ValueError("evidence must contain only exact material evidence.")
        if tuple(sorted({item.source_index for item in self.evidence})) != self.material_indices:
            raise ValueError("material_indices must match exact material evidence.")


class SmartMaterialCapabilityStatus(str, Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class SmartMaterialCapability:
    """One explainable model-specific Smart material capability result."""

    part_kind: SmartPartKind
    capability_kind: str
    status: SmartMaterialCapabilityStatus
    reason: str
    material_indices: tuple[int, ...]
    evidence: tuple[SmartPartEvidence, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.part_kind, SmartPartKind):
            raise TypeError("part_kind must be a SmartPartKind value.")
        if self.capability_kind != "material_color":
            raise ValueError("only material_color is supported in v0.9.5.6.")
        if not isinstance(self.status, SmartMaterialCapabilityStatus):
            raise TypeError("status must be a SmartMaterialCapabilityStatus value.")
        if type(self.reason) is not str or not self.reason:
            raise ValueError("reason must be a non-empty string.")
        if type(self.material_indices) is not tuple:
            raise TypeError("material_indices must be a tuple.")
        if self.material_indices != tuple(sorted(set(self.material_indices))):
            raise ValueError("material_indices must be unique and ascending.")
        if type(self.evidence) is not tuple:
            raise TypeError("evidence must be a tuple.")

    @property
    def supported(self) -> bool:
        return self.status is SmartMaterialCapabilityStatus.SUPPORTED

    @property
    def blocked(self) -> bool:
        return self.status is SmartMaterialCapabilityStatus.BLOCKED


class SmartMaterialDraftError(RuntimeError):
    """Stable fail-closed Smart material draft failure."""

    def __init__(self, reason: str, message: str) -> None:
        if type(reason) is not str or not reason:
            raise ValueError("reason must be a non-empty string.")
        if type(message) is not str or not message:
            raise ValueError("message must be a non-empty string.")
        self.reason = reason
        super().__init__(message)


def group_smart_materials(
    result: SmartInspectionResult,
    part_kind: SmartPartKind,
) -> SmartMaterialGroup:
    """Project one resolved Smart Part to exact material source identities."""

    if not isinstance(result, SmartInspectionResult):
        raise TypeError("result must be a SmartInspectionResult.")
    if not isinstance(part_kind, SmartPartKind):
        raise TypeError("part_kind must be a SmartPartKind value.")

    matching_parts = tuple(part for part in result.parts if part.kind is part_kind)
    if len(matching_parts) > 1:
        raise RuntimeError("Smart inspection returned duplicate resolved part kinds.")

    evidence = ()
    if matching_parts:
        evidence = tuple(
            item
            for item in matching_parts[0].evidence
            if item.source_kind is SmartPartEvidenceKind.MATERIAL
        )

    return SmartMaterialGroup(
        part_kind=part_kind,
        material_indices=tuple(sorted({item.source_index for item in evidence})),
        evidence=evidence,
    )


def _requested_kind_is_ambiguous(
    result: SmartInspectionResult,
    part_kind: SmartPartKind,
) -> bool:
    for assessment in result.assessments:
        if assessment.confidence is not SmartPartConfidence.AMBIGUOUS:
            continue
        if any(candidate.kind is part_kind for candidate in assessment.candidates):
            return True
    return False


def discover_smart_material_capability(
    result: SmartInspectionResult,
    part_kind: SmartPartKind,
) -> SmartMaterialCapability:
    """Discover material_color permission from exact evidence, not confidence."""

    group = group_smart_materials(result, part_kind)

    if _requested_kind_is_ambiguous(result, part_kind):
        status = SmartMaterialCapabilityStatus.BLOCKED
        reason = "ambiguous_semantic_selection"
    elif group.material_indices:
        status = SmartMaterialCapabilityStatus.SUPPORTED
        reason = "exact_material_evidence"
    else:
        status = SmartMaterialCapabilityStatus.UNSUPPORTED
        reason = "no_exact_material_evidence"

    return SmartMaterialCapability(
        part_kind=part_kind,
        capability_kind="material_color",
        status=status,
        reason=reason,
        material_indices=group.material_indices,
        evidence=group.evidence,
    )


def _material_catalog_entries(
    result: SmartInspectionResult,
) -> dict[int, PmxStructuralAuthoringMaterialCatalogEntry]:
    entries: dict[int, PmxStructuralAuthoringMaterialCatalogEntry] = {}
    for entry in result.entries:
        if not isinstance(entry, PmxStructuralAuthoringMaterialCatalogEntry):
            continue
        if entry.source_index in entries and entries[entry.source_index] != entry:
            raise SmartMaterialDraftError(
                "source_evidence_mismatch",
                "Conflicting exact material catalog identities were detected.",
            )
        entries[entry.source_index] = entry
    return entries


def _validate_material_group_against_document(
    document: PmxDocument,
    result: SmartInspectionResult,
    group: SmartMaterialGroup,
) -> None:
    catalog = _material_catalog_entries(result)

    for material_index in group.material_indices:
        if material_index >= len(document.materials):
            raise SmartMaterialDraftError(
                "source_evidence_mismatch",
                "Smart material evidence points outside the source material table.",
            )
        entry = catalog.get(material_index)
        if entry is None:
            raise SmartMaterialDraftError(
                "source_evidence_mismatch",
                "Smart material evidence has no matching source catalog entry.",
            )

        material = document.materials[material_index]
        observed = (
            material.local_name,
            material.universal_name,
            material.texture_index,
            material.sphere_texture_index,
            material.surface_index_count,
        )
        certified = (
            entry.local_name,
            entry.universal_name,
            entry.texture_index,
            entry.sphere_texture_index,
            entry.surface_index_count,
        )
        if observed != certified:
            raise SmartMaterialDraftError(
                "source_evidence_mismatch",
                "Smart material evidence does not match the parsed source material.",
            )


def _inspect_source_bytes(
    source_bytes: bytes,
) -> tuple[PmxDocument, SmartInspectionResult]:
    if type(source_bytes) is not bytes:
        raise TypeError("source_bytes must be bytes.")

    document = load_pmx(io.BytesIO(source_bytes))
    entries = _smart_inspection._collect_semantic_entries(document)
    return document, _smart_inspection._analyze_entries(entries)


def build_smart_material_color_draft(
    source_bytes: bytes,
    part_kind: SmartPartKind,
    color: SmartMaterialColorInput,
) -> PmxEditPlan:
    """Compose one source-bound RGB-only draft through existing edit authority."""

    if not isinstance(part_kind, SmartPartKind):
        raise TypeError("part_kind must be a SmartPartKind value.")

    document, result = _inspect_source_bytes(source_bytes)
    capability = discover_smart_material_capability(result, part_kind)

    if capability.blocked:
        raise SmartMaterialDraftError(
            "ambiguous_semantic_selection",
            "Smart material color draft is blocked by ambiguous semantic evidence.",
        )
    if not capability.supported:
        raise SmartMaterialDraftError(
            "unsupported_material_color",
            "Smart material color is unsupported without exact material evidence.",
        )

    group = group_smart_materials(result, part_kind)
    _validate_material_group_against_document(document, result, group)
    intent = normalize_smart_material_color(color)

    operations = tuple(
        UpdateMaterial(
            material_index=material_index,
            diffuse=(
                intent.rgb[0],
                intent.rgb[1],
                intent.rgb[2],
                document.materials[material_index].diffuse[3],
            ),
        )
        for material_index in group.material_indices
    )

    return PmxEditPlan(
        operations=operations,
        expected_source_sha256=hashlib.sha256(source_bytes).hexdigest(),
    )
