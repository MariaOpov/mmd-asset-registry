"""Private v0.9.5.9 Smart Material Appearance capability representation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum

from mmd_registry.pmx.editing.numeric import canonicalize_pmx_float32

from mmd_registry.services._smart_inspection import SmartInspectionResult
from mmd_registry.pmx.editing.operations import UpdateMaterial
from mmd_registry.pmx.editing.plan import PmxEditPlan
from mmd_registry.pmx.editing.preview import PmxEditPreview
import mmd_registry.services._smart_material_preview as smart_material_preview
from mmd_registry.services._smart_material_draft import (
    SmartMaterialCapabilityStatus,
    SmartMaterialDraftError,
    _inspect_source_bytes,
    _validate_material_group_against_document,
    discover_smart_material_capability,
    group_smart_materials,
)
from mmd_registry.smart_parts import (
    SmartPartEvidence,
    SmartPartEvidenceKind,
    SmartPartKind,
)


class SmartMaterialAppearanceCapabilityKind(str, Enum):
    """Exact v0.9.5.9 appearance capabilities authorized by CP04."""

    TRANSPARENCY = "transparency"
    MATERIAL_SPECULAR = "material_specular"
    MATERIAL_EDGE = "material_edge"


_STATUS_REASON = {
    SmartMaterialCapabilityStatus.SUPPORTED: "exact_material_evidence",
    SmartMaterialCapabilityStatus.UNSUPPORTED: "no_exact_material_evidence",
    SmartMaterialCapabilityStatus.BLOCKED: "ambiguous_semantic_selection",
}


def _evidence_sort_key(
    item: SmartPartEvidence,
) -> tuple[str, int, str]:
    return (
        item.source_kind.value,
        item.source_index,
        item.reason,
    )


@dataclass(frozen=True, slots=True)
class SmartMaterialAppearanceCapability:
    """One immutable model-specific Smart Material Appearance capability."""

    part_kind: SmartPartKind
    capability_kind: SmartMaterialAppearanceCapabilityKind
    status: SmartMaterialCapabilityStatus
    reason: str
    material_indices: tuple[int, ...]
    evidence: tuple[SmartPartEvidence, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.part_kind, SmartPartKind):
            raise TypeError("part_kind must be a SmartPartKind value.")
        if not isinstance(
            self.capability_kind,
            SmartMaterialAppearanceCapabilityKind,
        ):
            raise TypeError(
                "capability_kind must be a "
                "SmartMaterialAppearanceCapabilityKind value."
            )
        if not isinstance(self.status, SmartMaterialCapabilityStatus):
            raise TypeError(
                "status must reuse SmartMaterialCapabilityStatus authority."
            )
        if type(self.reason) is not str or not self.reason:
            raise ValueError("reason must be a non-empty string.")

        expected_reason = _STATUS_REASON[self.status]
        if self.reason != expected_reason:
            raise ValueError(
                "reason must exactly match the frozen capability status."
            )

        if type(self.material_indices) is not tuple:
            raise TypeError("material_indices must be a tuple.")
        if any(
            type(index) is not int or index < 0
            for index in self.material_indices
        ):
            raise ValueError(
                "material_indices must contain nonnegative exact integers."
            )
        if self.material_indices != tuple(
            sorted(set(self.material_indices))
        ):
            raise ValueError(
                "material_indices must be unique and ascending."
            )

        if type(self.evidence) is not tuple:
            raise TypeError("evidence must be a tuple.")
        if not all(
            isinstance(item, SmartPartEvidence)
            for item in self.evidence
        ):
            raise TypeError(
                "evidence must contain only SmartPartEvidence values."
            )
        if any(
            item.source_kind is not SmartPartEvidenceKind.MATERIAL
            for item in self.evidence
        ):
            raise ValueError(
                "evidence must contain only exact material evidence."
            )
        if len(set(self.evidence)) != len(self.evidence):
            raise ValueError("evidence must be exact-duplicate-free.")
        if self.evidence != tuple(
            sorted(self.evidence, key=_evidence_sort_key)
        ):
            raise ValueError("evidence must use canonical order.")

        evidence_indices = tuple(
            sorted({item.source_index for item in self.evidence})
        )
        if evidence_indices != self.material_indices:
            raise ValueError(
                "material_indices must match exact material evidence."
            )

        if self.status is SmartMaterialCapabilityStatus.SUPPORTED:
            if not self.material_indices:
                raise ValueError(
                    "supported capability requires exact material evidence."
                )
        elif self.status is SmartMaterialCapabilityStatus.UNSUPPORTED:
            if self.material_indices or self.evidence:
                raise ValueError(
                    "unsupported capability cannot carry exact material evidence."
                )

    @property
    def supported(self) -> bool:
        return self.status is SmartMaterialCapabilityStatus.SUPPORTED

    @property
    def blocked(self) -> bool:
        return self.status is SmartMaterialCapabilityStatus.BLOCKED

def _canonical_appearance_float(
    value: object,
    *,
    field_name: str,
) -> float:
    if type(value) is not float:
        raise TypeError(f"{field_name} must be exactly a float.")
    return canonicalize_pmx_float32(value)


def _canonical_appearance_tuple(
    value: object,
    *,
    length: int,
    field_name: str,
) -> tuple[float, ...]:
    if type(value) is not tuple:
        raise TypeError(f"{field_name} must be a tuple.")
    if len(value) != length:
        raise ValueError(
            f"{field_name} must contain exactly {length} floats."
        )
    return tuple(
        _canonical_appearance_float(
            component,
            field_name=f"{field_name} component",
        )
        for component in value
    )


@dataclass(frozen=True, slots=True)
class SmartMaterialTransparencyIntent:
    """Normalized source-preserving transparency alpha intent."""

    alpha: float

    def __post_init__(self) -> None:
        if type(self.alpha) is not float:
            raise TypeError("alpha must be exactly a float.")
        if not 0.0 <= self.alpha <= 1.0:
            raise ValueError("alpha must be within [0.0, 1.0].")
        object.__setattr__(
            self,
            "alpha",
            canonicalize_pmx_float32(self.alpha),
        )


@dataclass(frozen=True, slots=True)
class SmartMaterialSpecularIntent:
    """Normalized specular color and/or strength intent."""

    specular: tuple[float, float, float] | None = None
    strength: float | None = None

    def __post_init__(self) -> None:
        if self.specular is None and self.strength is None:
            raise ValueError(
                "specular intent must target at least one field."
            )

        if self.specular is not None:
            canonical_specular = _canonical_appearance_tuple(
                self.specular,
                length=3,
                field_name="specular",
            )
            object.__setattr__(
                self,
                "specular",
                canonical_specular,
            )

        if self.strength is not None:
            object.__setattr__(
                self,
                "strength",
                _canonical_appearance_float(
                    self.strength,
                    field_name="strength",
                ),
            )


@dataclass(frozen=True, slots=True)
class SmartMaterialEdgeIntent:
    """Normalized edge color and/or scale intent."""

    color: tuple[float, float, float, float] | None = None
    scale: float | None = None

    def __post_init__(self) -> None:
        if self.color is None and self.scale is None:
            raise ValueError(
                "edge intent must target at least one field."
            )

        if self.color is not None:
            canonical_color = _canonical_appearance_tuple(
                self.color,
                length=4,
                field_name="color",
            )
            object.__setattr__(
                self,
                "color",
                canonical_color,
            )

        if self.scale is not None:
            object.__setattr__(
                self,
                "scale",
                _canonical_appearance_float(
                    self.scale,
                    field_name="scale",
                ),
            )

def resolve_smart_material_appearance_capability(
    result: SmartInspectionResult,
    part_kind: SmartPartKind,
    capability_kind: SmartMaterialAppearanceCapabilityKind,
) -> SmartMaterialAppearanceCapability:
    """Project existing exact Smart material authority to one appearance primitive."""

    if not isinstance(capability_kind, SmartMaterialAppearanceCapabilityKind):
        raise TypeError(
            "capability_kind must be a "
            "SmartMaterialAppearanceCapabilityKind value."
        )

    existing = discover_smart_material_capability(result, part_kind)
    return SmartMaterialAppearanceCapability(
        part_kind=existing.part_kind,
        capability_kind=capability_kind,
        status=existing.status,
        reason=existing.reason,
        material_indices=existing.material_indices,
        evidence=existing.evidence,
    )

SmartMaterialAppearanceIntent = (
    SmartMaterialTransparencyIntent
    | SmartMaterialSpecularIntent
    | SmartMaterialEdgeIntent
)


def _appearance_capability_kind_for_intent(
    intent: SmartMaterialAppearanceIntent,
) -> SmartMaterialAppearanceCapabilityKind:
    if isinstance(intent, SmartMaterialTransparencyIntent):
        return SmartMaterialAppearanceCapabilityKind.TRANSPARENCY
    if isinstance(intent, SmartMaterialSpecularIntent):
        return SmartMaterialAppearanceCapabilityKind.MATERIAL_SPECULAR
    if isinstance(intent, SmartMaterialEdgeIntent):
        return SmartMaterialAppearanceCapabilityKind.MATERIAL_EDGE
    raise TypeError(
        "intent must be a scoped Smart Material Appearance intent."
    )


def build_smart_material_appearance_draft(
    source_bytes: bytes,
    part_kind: SmartPartKind,
    intent: SmartMaterialAppearanceIntent,
) -> PmxEditPlan:
    """Compose one source-bound appearance primitive through existing authority."""

    capability_kind = _appearance_capability_kind_for_intent(intent)
    document, result = _inspect_source_bytes(source_bytes)
    capability = resolve_smart_material_appearance_capability(
        result,
        part_kind,
        capability_kind,
    )

    if capability.blocked:
        raise SmartMaterialDraftError(
            "ambiguous_semantic_selection",
            "Smart Material Appearance draft is blocked by ambiguous semantic evidence.",
        )
    if not capability.supported:
        raise SmartMaterialDraftError(
            "unsupported_appearance_capability",
            "Smart Material Appearance is unsupported without exact material evidence.",
        )

    group = group_smart_materials(result, part_kind)
    _validate_material_group_against_document(
        document,
        result,
        group,
    )

    operations: list[UpdateMaterial] = []
    for material_index in capability.material_indices:
        if isinstance(intent, SmartMaterialTransparencyIntent):
            source_diffuse = document.materials[material_index].diffuse
            operation = UpdateMaterial(
                material_index=material_index,
                diffuse=(
                    source_diffuse[0],
                    source_diffuse[1],
                    source_diffuse[2],
                    intent.alpha,
                ),
            )
        elif isinstance(intent, SmartMaterialSpecularIntent):
            operation = UpdateMaterial(
                material_index=material_index,
                specular=intent.specular,
                specular_strength=intent.strength,
            )
        else:
            operation = UpdateMaterial(
                material_index=material_index,
                edge_color=intent.color,
                edge_scale=intent.scale,
            )
        operations.append(operation)

    return PmxEditPlan(
        operations=tuple(operations),
        expected_source_sha256=hashlib.sha256(source_bytes).hexdigest(),
    )

def preview_smart_material_appearance_draft(
    source_bytes: bytes,
    draft: PmxEditPlan,
) -> PmxEditPreview:
    """Preview one appearance draft through the existing Smart preview bridge."""

    return smart_material_preview.preview_smart_material_color_draft(
        source_bytes,
        draft,
    )
