"""Internal CP17 coordinated multi-target insertion planning and preview.

The coordinator never accepts final PMX indices as request dependency language.
It plans every target collection against the captured source domain, resolves
request-local identities to deterministic final indices, then delegates actual
section mutation to the already-certified target-specific insertion previews.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Final

from mmd_registry.pmx.document import PmxDocument
from mmd_registry.pmx.reference_diagnostics import diagnose_reference_graph
from mmd_registry.pmx.reference_graph import extract_pmx_reference_graph
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.pmx.structural_bone_insertion import (
    PmxBoneInsertionPayload,
    PmxBoneInsertionPreview,
    preview_pmx_bone_insertions,
)
from mmd_registry.pmx.structural_insert_intent import (
    PmxCollectionInsertionIntent,
    PmxStructuralInsertPosition,
    PmxStructuralInsertionIntent,
)
from mmd_registry.pmx.structural_invariants import PmxStructuralInvariantCertificate
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
from mmd_registry.pmx.structural_reference_shift import (
    PmxCollectionReferenceShiftPlan,
    plan_collection_reference_shift,
)
from mmd_registry.pmx.structural_rigid_body_insertion import (
    PmxRigidBodyInsertionPayload,
    PmxRigidBodyInsertionPreview,
    preview_pmx_rigid_body_insertions,
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


PMX_COORDINATED_INSERTION_PREVIEW_SCHEMA_VERSION: Final[int] = 1


@dataclass(frozen=True, slots=True)
class PmxCoordinatedInsertionCollectionSpec:
    """One source-domain insertion collection plus optional request-local IDs."""

    target_kind: PmxReferenceTargetKind
    positions: tuple[PmxStructuralInsertPosition, ...]
    new_ids: tuple[str | None, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.target_kind, PmxReferenceTargetKind):
            raise TypeError("target_kind must be a PmxReferenceTargetKind value.")
        if type(self.positions) is not tuple:
            raise TypeError("positions must be a tuple.")
        if not self.positions:
            raise ValueError("positions must contain at least one insertion.")
        if not all(
            isinstance(position, PmxStructuralInsertPosition)
            for position in self.positions
        ):
            raise TypeError(
                "positions must contain only PmxStructuralInsertPosition values."
            )
        if type(self.new_ids) is not tuple:
            raise TypeError("new_ids must be a tuple.")
        if len(self.new_ids) != len(self.positions):
            raise ValueError("new_ids length must match positions length.")
        if any(value is not None and not isinstance(value, str) for value in self.new_ids):
            raise TypeError("new_ids must contain only strings or None.")


@dataclass(frozen=True, slots=True)
class PmxCoordinatedNewIdentity:
    """One resolved request-local identity; kept internal and privacy bounded."""

    target_kind: PmxReferenceTargetKind
    new_id: str
    request_index: int
    final_index: int


@dataclass(frozen=True, slots=True)
class PmxCoordinatedReferencePlan:
    """Immutable source/new/final domain separation for one coordinated request."""

    source_counts: tuple[tuple[PmxReferenceTargetKind, int], ...]
    shifts: tuple[PmxCollectionReferenceShiftPlan, ...]
    identities: tuple[PmxCoordinatedNewIdentity, ...]

    def _source_count(self, target_kind: PmxReferenceTargetKind) -> int:
        for kind, count in self.source_counts:
            if kind is target_kind:
                return count
        raise AssertionError(f"missing source count for {target_kind.value}")

    def shift_for(
        self,
        target_kind: PmxReferenceTargetKind,
    ) -> PmxCollectionReferenceShiftPlan | None:
        for shift in self.shifts:
            if shift.target_kind is target_kind:
                return shift
        return None

    @property
    def changed_kinds(self) -> tuple[PmxReferenceTargetKind, ...]:
        return tuple(shift.target_kind for shift in self.shifts)

    def resolve_source_reference(
        self,
        target_kind: PmxReferenceTargetKind,
        value: object,
        *,
        allow_sentinel: bool,
        field_name: str,
    ) -> int:
        if type(value) is not int:
            raise TypeError(f"{field_name} source reference must be an integer.")
        if allow_sentinel and value == -1:
            return -1
        count = self._source_count(target_kind)
        if value < 0 or value >= count:
            raise ValueError(
                f"{field_name} must reference the captured source "
                f"{target_kind.value} domain."
            )
        shift = self.shift_for(target_kind)
        if shift is None:
            return value
        mapped = shift.remap.targets[value]
        if mapped is None:
            raise AssertionError(
                "insertion-only shift unexpectedly removed a source record."
            )
        return mapped

    def resolve_new_reference(
        self,
        target_kind: PmxReferenceTargetKind,
        new_id: str,
        *,
        field_name: str,
    ) -> int:
        for identity in self.identities:
            if identity.new_id != new_id:
                continue
            if identity.target_kind is not target_kind:
                raise ValueError(
                    f"{field_name} new reference targets {target_kind.value} but "
                    f"new_id {new_id!r} belongs to {identity.target_kind.value}."
                )
            return identity.final_index
        raise ValueError(
            f"{field_name} references unknown request-local new_id {new_id!r}."
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "changed_kinds": [kind.value for kind in self.changed_kinds],
            "new_identity_count": len(self.identities),
            "collections": [shift.to_dict() for shift in self.shifts],
        }


def _source_count(
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
    raise AssertionError(f"unsupported target kind: {target_kind!r}")


def _index_width(
    document: PmxDocument,
    target_kind: PmxReferenceTargetKind,
) -> int:
    sizes = document.header.index_sizes
    if target_kind is PmxReferenceTargetKind.VERTEX:
        return sizes.vertex
    if target_kind is PmxReferenceTargetKind.TEXTURE:
        return sizes.texture
    if target_kind is PmxReferenceTargetKind.MATERIAL:
        return sizes.material
    if target_kind is PmxReferenceTargetKind.BONE:
        return sizes.bone
    if target_kind is PmxReferenceTargetKind.MORPH:
        return sizes.morph
    if target_kind is PmxReferenceTargetKind.RIGID_BODY:
        return sizes.rigid_body
    raise AssertionError(f"unsupported target kind: {target_kind!r}")


def plan_pmx_coordinated_insertion_references(
    document: PmxDocument,
    specs: tuple[PmxCoordinatedInsertionCollectionSpec, ...],
) -> PmxCoordinatedReferencePlan:
    """Plan all insertions against the original source before resolving references."""

    if not isinstance(document, PmxDocument):
        raise TypeError("document must be a PmxDocument instance.")
    if type(specs) is not tuple:
        raise TypeError("specs must be a tuple.")
    if not specs:
        raise ValueError("coordinated insertion requires at least one collection spec.")
    if not all(isinstance(spec, PmxCoordinatedInsertionCollectionSpec) for spec in specs):
        raise TypeError(
            "specs must contain only PmxCoordinatedInsertionCollectionSpec values."
        )

    insertion_intent = PmxStructuralInsertionIntent(
        collection_insertions=tuple(
            PmxCollectionInsertionIntent(
                target_kind=spec.target_kind,
                positions=spec.positions,
            )
            for spec in specs
        )
    )

    shifts: list[PmxCollectionReferenceShiftPlan] = []
    spec_by_kind = {spec.target_kind: spec for spec in specs}
    for insertion in insertion_intent.collection_insertions:
        shifts.append(
            plan_collection_reference_shift(
                insertion,
                current_count=_source_count(document, insertion.target_kind),
                index_width=_index_width(document, insertion.target_kind),
            )
        )

    seen_ids: set[str] = set()
    identities: list[PmxCoordinatedNewIdentity] = []
    for shift in shifts:
        spec = spec_by_kind[shift.target_kind]
        for request_index, new_id in enumerate(spec.new_ids):
            if new_id is None:
                continue
            if new_id in seen_ids:
                raise ValueError(
                    f"request-local new_id {new_id!r} must be globally unique."
                )
            seen_ids.add(new_id)
            identities.append(
                PmxCoordinatedNewIdentity(
                    target_kind=shift.target_kind,
                    new_id=new_id,
                    request_index=request_index,
                    final_index=shift.new_index_for_insertion(request_index),
                )
            )

    return PmxCoordinatedReferencePlan(
        source_counts=tuple(
            (kind, _source_count(document, kind)) for kind in PmxReferenceTargetKind
        ),
        shifts=tuple(shifts),
        identities=tuple(identities),
    )


@dataclass(frozen=True, slots=True)
class PmxCoordinatedInsertionPayloads:
    """Resolved internal payloads for one multi-target transaction."""

    reference_plan: PmxCoordinatedReferencePlan
    texture_insertions: tuple[PmxTextureInsertionPayload, ...] = ()
    material_insertions: tuple[PmxMaterialInsertionPayload, ...] = ()
    bone_insertions: tuple[PmxBoneInsertionPayload, ...] = ()
    vertex_insertions: tuple[PmxVertexInsertionPayload, ...] = ()
    rigid_body_insertions: tuple[PmxRigidBodyInsertionPayload, ...] = ()
    morph_insertions: tuple[PmxMorphInsertionPayload, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.reference_plan, PmxCoordinatedReferencePlan):
            raise TypeError("reference_plan must be a PmxCoordinatedReferencePlan value.")
        specifications = (
            ("texture_insertions", self.texture_insertions, PmxTextureInsertionPayload),
            ("material_insertions", self.material_insertions, PmxMaterialInsertionPayload),
            ("bone_insertions", self.bone_insertions, PmxBoneInsertionPayload),
            ("vertex_insertions", self.vertex_insertions, PmxVertexInsertionPayload),
            (
                "rigid_body_insertions",
                self.rigid_body_insertions,
                PmxRigidBodyInsertionPayload,
            ),
            ("morph_insertions", self.morph_insertions, PmxMorphInsertionPayload),
        )
        for field_name, values, expected_type in specifications:
            if type(values) is not tuple:
                raise TypeError(f"{field_name} must be a tuple.")
            if not all(isinstance(value, expected_type) for value in values):
                raise TypeError(
                    f"{field_name} must contain only {expected_type.__name__} values."
                )
        if self.changed_collection_count < 2:
            raise ValueError(
                "coordinated insertion requires at least two insertion target families."
            )
        if set(self.reference_plan.changed_kinds) != set(self.changed_kinds):
            raise ValueError(
                "reference plan changed kinds must exactly match payload changed kinds."
            )

    @property
    def changed_kinds(self) -> tuple[PmxReferenceTargetKind, ...]:
        pairs = (
            (PmxReferenceTargetKind.TEXTURE, self.texture_insertions),
            (PmxReferenceTargetKind.MATERIAL, self.material_insertions),
            (PmxReferenceTargetKind.BONE, self.bone_insertions),
            (PmxReferenceTargetKind.VERTEX, self.vertex_insertions),
            (PmxReferenceTargetKind.RIGID_BODY, self.rigid_body_insertions),
            (PmxReferenceTargetKind.MORPH, self.morph_insertions),
        )
        return tuple(kind for kind, values in pairs if values)

    @property
    def changed_collection_count(self) -> int:
        return len(self.changed_kinds)

    @property
    def total_insert_count(self) -> int:
        return sum(
            len(values)
            for values in (
                self.texture_insertions,
                self.material_insertions,
                self.bone_insertions,
                self.vertex_insertions,
                self.rigid_body_insertions,
                self.morph_insertions,
            )
        )

    def canonical_payload(self) -> dict[str, object]:
        return {
            "texture": [value.to_dict() for value in self.texture_insertions],
            "material": [value.to_dict() for value in self.material_insertions],
            "bone": [value.to_dict() for value in self.bone_insertions],
            "vertex": [value.to_dict() for value in self.vertex_insertions],
            "rigid_body": [value.to_dict() for value in self.rigid_body_insertions],
            "morph": [value.to_dict() for value in self.morph_insertions],
            "reference_plan": self.reference_plan.to_dict(),
        }


_PmxInsertionStagePreview = (
    PmxTextureInsertionPreview
    | PmxMaterialInsertionPreview
    | PmxBoneInsertionPreview
    | PmxVertexInsertionPreview
    | PmxRigidBodyInsertionPreview
    | PmxMorphInsertionPreview
)


@dataclass(frozen=True, slots=True)
class PmxCoordinatedInsertionPreview:
    """Certified final document after deterministic cross-section insertion stages."""

    source_document: PmxDocument
    payloads: PmxCoordinatedInsertionPayloads
    stage_previews: tuple[_PmxInsertionStagePreview, ...] = field(init=False)
    certificate: PmxStructuralInvariantCertificate = field(init=False)
    intent_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.source_document, PmxDocument):
            raise TypeError("source_document must be a PmxDocument instance.")
        if not isinstance(self.payloads, PmxCoordinatedInsertionPayloads):
            raise TypeError("payloads must be a PmxCoordinatedInsertionPayloads value.")

        current = self.source_document
        previews: list[_PmxInsertionStagePreview] = []

        if self.payloads.texture_insertions:
            preview = preview_pmx_texture_insertions(current, self.payloads.texture_insertions)
            previews.append(preview)
            current = preview.certificate.document
        if self.payloads.material_insertions:
            preview = preview_pmx_material_insertions(current, self.payloads.material_insertions)
            previews.append(preview)
            current = preview.certificate.document
        if self.payloads.bone_insertions:
            preview = preview_pmx_bone_insertions(current, self.payloads.bone_insertions)
            previews.append(preview)
            current = preview.certificate.document
        if self.payloads.vertex_insertions:
            preview = preview_pmx_vertex_insertions(current, self.payloads.vertex_insertions)
            previews.append(preview)
            current = preview.certificate.document
        if self.payloads.rigid_body_insertions:
            preview = preview_pmx_rigid_body_insertions(
                current,
                self.payloads.rigid_body_insertions,
            )
            previews.append(preview)
            current = preview.certificate.document
        if self.payloads.morph_insertions:
            preview = preview_pmx_morph_insertions(current, self.payloads.morph_insertions)
            previews.append(preview)
            current = preview.certificate.document

        if len(previews) != self.payloads.changed_collection_count:
            raise AssertionError("coordinated stage count does not match changed kinds.")

        canonical = json.dumps(
            self.payloads.canonical_payload(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        object.__setattr__(self, "stage_previews", tuple(previews))
        object.__setattr__(
            self,
            "certificate",
            PmxStructuralInvariantCertificate(document=current),
        )
        object.__setattr__(
            self,
            "intent_sha256",
            hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        )

    @property
    def status(self) -> str:
        return "changes_pending"

    def to_dict(self) -> dict[str, object]:
        source_graph = extract_pmx_reference_graph(self.source_document)
        source_diagnostics = diagnose_reference_graph(source_graph)
        output_graph = self.certificate.reference_graph
        source_counts = source_graph.target_counts
        output_counts = output_graph.target_counts

        return {
            "preview_schema_version": PMX_COORDINATED_INSERTION_PREVIEW_SCHEMA_VERSION,
            "status": self.status,
            "dry_run": True,
            "source": {
                "target_counts": {
                    "vertex": source_counts.vertex,
                    "texture": source_counts.texture,
                    "material": source_counts.material,
                    "bone": source_counts.bone,
                    "morph": source_counts.morph,
                    "rigid_body": source_counts.rigid_body,
                },
                "reference_edge_count": len(source_graph.edges),
                "reference_diagnostic_count": len(source_diagnostics),
            },
            "intent": {
                "sha256": self.intent_sha256,
                "changed_kinds": [kind.value for kind in self.payloads.changed_kinds],
                "collection_count": self.payloads.changed_collection_count,
                "insert_count": self.payloads.total_insert_count,
            },
            "output": {
                "written": False,
                "target_counts": {
                    "vertex": output_counts.vertex,
                    "texture": output_counts.texture,
                    "material": output_counts.material,
                    "bone": output_counts.bone,
                    "morph": output_counts.morph,
                    "rigid_body": output_counts.rigid_body,
                },
                "reference_edge_count": self.certificate.edge_count,
                "reference_diagnostic_count": 0,
            },
            "verification": {
                "invariants": "passed",
                "reference_model": "passed",
                "serialization": "not_performed",
            },
            "audit": {
                "summary": {
                    "changed_kinds": [kind.value for kind in self.payloads.changed_kinds],
                    "changed_collection_count": self.payloads.changed_collection_count,
                    "inserted_record_count": self.payloads.total_insert_count,
                    "stage_count": len(self.stage_previews),
                    "new_identity_count": len(self.payloads.reference_plan.identities),
                },
                "reference_resolution": self.payloads.reference_plan.to_dict(),
                "stage_kinds": [kind.value for kind in self.payloads.changed_kinds],
            },
        }


def preview_pmx_coordinated_insertions(
    document: PmxDocument,
    payloads: PmxCoordinatedInsertionPayloads,
) -> PmxCoordinatedInsertionPreview:
    return PmxCoordinatedInsertionPreview(
        source_document=document,
        payloads=payloads,
    )


__all__ = (
    "PMX_COORDINATED_INSERTION_PREVIEW_SCHEMA_VERSION",
    "PmxCoordinatedInsertionCollectionSpec",
    "PmxCoordinatedReferencePlan",
    "PmxCoordinatedInsertionPayloads",
    "PmxCoordinatedInsertionPreview",
    "plan_pmx_coordinated_insertion_references",
    "preview_pmx_coordinated_insertions",
)
