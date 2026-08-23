"""Internal complete in-memory preview for structural transactions.

CP16 joins the source-bound composition, resolved payloads, dependency order,
and existing certified target kernels.  Planning and payload preparation finish
before this module materializes any target.  CP17 adds deterministic in-memory
source binding, bounded semantic plan evidence, and canonical plan hashing.  It
still performs no filesystem access or publication.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Final

from mmd_registry.pmx.document import PmxDocument
from mmd_registry.pmx.collection_transform import PmxStructuralTransformIntent
from mmd_registry.pmx.errors import PmxValidationError
from mmd_registry.pmx.reference_model import (
    PmxReferenceSourceSection,
    PmxReferenceTargetKind,
)
from mmd_registry.pmx.structural_bone_insertion import (
    PmxBoneInsertionPayload,
    _build_bone_shift_plan,
    preview_pmx_bone_insertions,
)
from mmd_registry.pmx.structural_invariants import (
    PmxStructuralInvariantCertificate,
    PmxStructuralInvariantError,
)
from mmd_registry.pmx.structural_material_insertion import (
    PmxMaterialInsertionPayload,
    _build_material_shift_plan,
    preview_pmx_material_insertions,
)
from mmd_registry.pmx.structural_morph_insertion import (
    PmxMorphInsertionPayload,
    _build_morph_shift_plan,
    preview_pmx_morph_insertions,
)
from mmd_registry.pmx.structural_orchestrator import transform_pmx_document
from mmd_registry.pmx.structural_rigid_body_insertion import (
    PmxRigidBodyInsertionPayload,
    _build_rigid_body_shift_plan,
    preview_pmx_rigid_body_insertions,
)
from mmd_registry.pmx.structural_reference_shift import (
    PmxCollectionReferenceShiftPlan,
)
from mmd_registry.pmx.structural_texture_insertion import (
    PmxTextureInsertionPayload,
    _build_texture_shift_plan,
    preview_pmx_texture_insertions,
)
from mmd_registry.pmx.structural_transaction_composition import (
    PmxStructuralTransactionComposition,
)
from mmd_registry.pmx.structural_vertex_insertion import (
    PmxVertexInsertionPayload,
    _build_vertex_shift_plan,
    preview_pmx_vertex_insertions,
)
from mmd_registry.pmx.writer import serialize_pmx


_PLAN_SCHEMA: Final[str] = "mmd_registry.structural_transaction.plan.v1"
_TARGET_KIND_ORDER = tuple(PmxReferenceTargetKind)
_TARGET_KIND_RANK = {
    target_kind: rank for rank, target_kind in enumerate(_TARGET_KIND_ORDER)
}
_SOURCE_SECTION_RANK = {
    section: rank for rank, section in enumerate(PmxReferenceSourceSection)
}
_OWNER_TARGETS = {
    PmxReferenceSourceSection.VERTICES: PmxReferenceTargetKind.VERTEX,
    PmxReferenceSourceSection.MATERIALS: PmxReferenceTargetKind.MATERIAL,
    PmxReferenceSourceSection.BONES: PmxReferenceTargetKind.BONE,
    PmxReferenceSourceSection.MORPHS: PmxReferenceTargetKind.MORPH,
    PmxReferenceSourceSection.RIGID_BODIES: (
        PmxReferenceTargetKind.RIGID_BODY
    ),
}
_STAGE_PROVENANCE = {
    "transaction_normalization": "transaction_plan",
    "reference_resolution": "transaction_plan",
    "dependency_resolution": "transaction_plan",
    "capacity_preflight": "transaction_plan",
    "transform": "structural_pipeline",
    "structural_certification": "structural_pipeline",
}


def _canonical_json_bytes(value: object) -> bytes:
    """Return the contract-fixed UTF-8 canonical JSON representation."""

    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _semantic_payload_sha256(payload: object) -> str:
    """Hash one validated typed payload without exposing its private data."""

    to_dict = getattr(payload, "to_dict", None)
    if not callable(to_dict):
        raise AssertionError("transaction payload has no semantic evidence encoder")
    evidence = to_dict()
    if not isinstance(evidence, dict):
        raise AssertionError("transaction payload evidence must be an object")
    return _canonical_sha256(evidence)


class PmxStructuralTransactionPreviewError(ValueError):
    """One bounded internal blocker with deterministic stage provenance."""

    def __init__(
        self,
        stage: str,
        *,
        operation_index: int | None = None,
        target_kind: PmxReferenceTargetKind | None = None,
        new_id: str | None = None,
        relationship_id: str | None = None,
    ) -> None:
        if stage not in _STAGE_PROVENANCE:
            raise ValueError("stage must be a supported transaction stage.")
        if operation_index is not None and (
            type(operation_index) is not int or operation_index < 0
        ):
            raise ValueError("operation_index must be nonnegative or None.")
        if target_kind is not None and not isinstance(
            target_kind,
            PmxReferenceTargetKind,
        ):
            raise TypeError(
                "target_kind must be a PmxReferenceTargetKind value or None."
            )
        if new_id is not None and not isinstance(new_id, str):
            raise TypeError("new_id must be a string or None.")
        if relationship_id is not None and not isinstance(
            relationship_id,
            str,
        ):
            raise TypeError("relationship_id must be a string or None.")
        self.stage = stage
        self.operation_index = operation_index
        self.target_kind = target_kind
        self.new_id = new_id
        self.relationship_id = relationship_id
        super().__init__("Structural transaction preview was blocked.")

    @property
    def provenance(self) -> str:
        return _STAGE_PROVENANCE[self.stage]


@dataclass(frozen=True, slots=True)
class PmxStructuralTransactionOperationDescriptor:
    """Bounded request-order evidence retained before normalization."""

    request_ordinal: int
    category: str
    target_kind: PmxReferenceTargetKind
    position: str | None = None
    source_index: int | None = None
    new_id: str | None = None

    def __post_init__(self) -> None:
        if type(self.request_ordinal) is not int or self.request_ordinal < 0:
            raise ValueError("request_ordinal must be a nonnegative integer.")
        if self.category not in ("collection_transform", "insertion"):
            raise ValueError(
                "category must be collection_transform or insertion."
            )
        if not isinstance(self.target_kind, PmxReferenceTargetKind):
            raise TypeError("target_kind must be a PmxReferenceTargetKind value.")
        if self.category == "collection_transform":
            if any(
                value is not None
                for value in (self.position, self.source_index, self.new_id)
            ):
                raise ValueError(
                    "collection-transform descriptors cannot define insertion fields."
                )
            return
        if self.position not in ("append", "insert_before"):
            raise ValueError("insertion position must be append or insert_before.")
        if self.position == "append" and self.source_index is not None:
            raise ValueError("append descriptors cannot define source_index.")
        if self.position == "insert_before" and (
            type(self.source_index) is not int or self.source_index < 0
        ):
            raise ValueError(
                "insert_before descriptors require nonnegative source_index."
            )
        if self.new_id is not None and not isinstance(self.new_id, str):
            raise TypeError("new_id must be a string or None.")

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "request_ordinal": self.request_ordinal,
            "category": self.category,
            "target_kind": self.target_kind.value,
        }
        if self.category == "insertion":
            payload["position"] = self.position
            payload["source_index"] = self.source_index
            payload["new_id"] = self.new_id
        return payload


@dataclass(frozen=True, slots=True)
class PmxStructuralTransactionLocalReferenceEvidence:
    """One resolved request-local reference without exposing a payload object."""

    request_ordinal: int
    field_name: str
    relationship_id: str
    target_kind: PmxReferenceTargetKind
    new_id: str
    final_index: int

    def __post_init__(self) -> None:
        if type(self.request_ordinal) is not int or self.request_ordinal < 0:
            raise ValueError("request_ordinal must be nonnegative.")
        for field_name in ("field_name", "relationship_id", "new_id"):
            value = getattr(self, field_name)
            if type(value) is not str or not value:
                raise ValueError(f"{field_name} must be a non-empty string.")
        if not isinstance(self.target_kind, PmxReferenceTargetKind):
            raise TypeError("target_kind must be a PmxReferenceTargetKind value.")
        if type(self.final_index) is not int or self.final_index < 0:
            raise ValueError("final_index must be nonnegative.")

    def to_dict(self) -> dict[str, object]:
        return {
            "request_ordinal": self.request_ordinal,
            "field": self.field_name,
            "relationship_id": self.relationship_id,
            "target_kind": self.target_kind.value,
            "new_id": self.new_id,
            "final_index": self.final_index,
        }


@dataclass(frozen=True, slots=True)
class PmxStructuralTransactionExistingReferenceEvidence:
    """One surviving source reference whose target index is remapped."""

    relationship_id: str
    source_section: PmxReferenceSourceSection
    source_record_index: int
    target_kind: PmxReferenceTargetKind
    old_target_index: int
    final_target_index: int

    def to_dict(self) -> dict[str, object]:
        return {
            "relationship_id": self.relationship_id,
            "source_section": self.source_section.value,
            "source_record_index": self.source_record_index,
            "target_kind": self.target_kind.value,
            "old_target_index": self.old_target_index,
            "final_target_index": self.final_target_index,
        }


@dataclass(frozen=True, slots=True)
class PmxStructuralTransactionPayloads:
    """All validated internal insertion payloads prepared before materialization."""

    vertex: tuple[PmxVertexInsertionPayload, ...] = ()
    texture: tuple[PmxTextureInsertionPayload, ...] = ()
    material: tuple[PmxMaterialInsertionPayload, ...] = ()
    bone: tuple[PmxBoneInsertionPayload, ...] = ()
    morph: tuple[PmxMorphInsertionPayload, ...] = ()
    rigid_body: tuple[PmxRigidBodyInsertionPayload, ...] = ()

    def __post_init__(self) -> None:
        specifications = (
            ("vertex", PmxVertexInsertionPayload),
            ("texture", PmxTextureInsertionPayload),
            ("material", PmxMaterialInsertionPayload),
            ("bone", PmxBoneInsertionPayload),
            ("morph", PmxMorphInsertionPayload),
            ("rigid_body", PmxRigidBodyInsertionPayload),
        )
        for field_name, expected_type in specifications:
            values = getattr(self, field_name)
            if type(values) is not tuple:
                raise TypeError(f"{field_name} payloads must be a tuple.")
            if not all(isinstance(value, expected_type) for value in values):
                raise TypeError(
                    f"{field_name} payloads must contain only "
                    f"{expected_type.__name__} values."
                )

    def for_target(
        self,
        target_kind: PmxReferenceTargetKind,
    ) -> tuple[object, ...]:
        if not isinstance(target_kind, PmxReferenceTargetKind):
            raise TypeError("target_kind must be a PmxReferenceTargetKind value.")
        return getattr(self, target_kind.value)


@dataclass(frozen=True, slots=True)
class _CountOnlyCollection:
    """Expose only a planned final collection length during payload preflight."""

    count: int

    def __len__(self) -> int:
        return self.count


@dataclass(frozen=True, slots=True)
class _PayloadPreflightDocumentView:
    """Minimal non-materialized source view consumed by released validators."""

    header: object
    vertices: object
    texture_paths: object
    materials: object
    bones: object
    morphs: object
    rigid_bodies: object


_TARGET_COLLECTION_ATTRIBUTES = {
    PmxReferenceTargetKind.VERTEX: "vertices",
    PmxReferenceTargetKind.TEXTURE: "texture_paths",
    PmxReferenceTargetKind.MATERIAL: "materials",
    PmxReferenceTargetKind.BONE: "bones",
    PmxReferenceTargetKind.MORPH: "morphs",
    PmxReferenceTargetKind.RIGID_BODY: "rigid_bodies",
}


def _surviving_source_collection(
    document: PmxDocument,
    composition: PmxStructuralTransactionComposition,
    target_kind: PmxReferenceTargetKind,
) -> tuple[object, ...]:
    attribute = _TARGET_COLLECTION_ATTRIBUTES[target_kind]
    source = getattr(document, attribute)
    placement = composition.placement_for(target_kind)
    if placement is None:
        return source
    return tuple(
        source[old_index]
        for old_index in placement.transform.old_indices_in_new_order
    )


def _payload_preflight_document_view(
    document: PmxDocument,
    composition: PmxStructuralTransactionComposition,
    target_kind: PmxReferenceTargetKind,
) -> _PayloadPreflightDocumentView:
    final_counts = dict(composition.preflight.final_counts)
    collections: dict[str, object] = {}
    for kind, attribute in _TARGET_COLLECTION_ATTRIBUTES.items():
        collections[attribute] = (
            _surviving_source_collection(document, composition, kind)
            if kind is target_kind
            else _CountOnlyCollection(final_counts[kind])
        )
    return _PayloadPreflightDocumentView(
        header=document.header,
        **collections,
    )


def _preflight_target_payloads(
    document: PmxDocument,
    composition: PmxStructuralTransactionComposition,
    target_kind: PmxReferenceTargetKind,
    payloads: tuple[object, ...],
) -> PmxCollectionReferenceShiftPlan:
    view = _payload_preflight_document_view(
        document,
        composition,
        target_kind,
    )
    if target_kind is PmxReferenceTargetKind.TEXTURE:
        return _build_texture_shift_plan(view, payloads)
    if target_kind is PmxReferenceTargetKind.MATERIAL:
        return _build_material_shift_plan(view, payloads)
    if target_kind is PmxReferenceTargetKind.BONE:
        return _build_bone_shift_plan(view, payloads)
    if target_kind is PmxReferenceTargetKind.VERTEX:
        return _build_vertex_shift_plan(view, payloads)
    if target_kind is PmxReferenceTargetKind.RIGID_BODY:
        return _build_rigid_body_shift_plan(view, payloads)
    if target_kind is PmxReferenceTargetKind.MORPH:
        return _build_morph_shift_plan(view, payloads)
    raise AssertionError(f"unhandled target kind {target_kind.value}")


def _preflight_transaction_payloads(
    document: PmxDocument,
    composition: PmxStructuralTransactionComposition,
    payloads: PmxStructuralTransactionPayloads,
) -> None:
    """Complete every target payload check before any target materialization."""

    for target_kind in _TARGET_KIND_ORDER:
        target_payloads = payloads.for_target(target_kind)
        if not target_payloads:
            continue
        try:
            shift = _preflight_target_payloads(
                document,
                composition,
                target_kind,
                target_payloads,
            )
        except (TypeError, ValueError) as error:
            raise PmxStructuralTransactionPreviewError(
                "capacity_preflight",
                target_kind=target_kind,
            ) from error
        placement = composition.placement_for(target_kind)
        if placement is None:
            raise AssertionError(
                f"{target_kind.value} payload preflight has no "
                "authoritative transaction placement."
            )
        expected_survivor_targets = tuple(
            placement.remap.target_for(old_index)
            for old_index in placement.transform.old_indices_in_new_order
        )
        expected_new_targets = tuple(
            binding.final_index for binding in placement.bindings
        )
        if (
            shift.remap.targets != expected_survivor_targets
            or shift.new_indices_in_request_order != expected_new_targets
            or shift.result_count != placement.remap.new_size
        ):
            raise AssertionError(
                f"{target_kind.value} payload preflight disagrees with "
                "the authoritative transaction placement."
            )


def _environment_dict(
    entries: tuple[tuple[PmxReferenceTargetKind, int], ...],
) -> dict[str, int]:
    return {target_kind.value: value for target_kind, value in entries}


def _validate_source_binding(
    document: PmxDocument,
    composition: PmxStructuralTransactionComposition,
) -> None:
    captured_counts = _environment_dict(composition.source_counts)
    actual_counts = {
        target_kind.value: len(
            getattr(document, _TARGET_COLLECTION_ATTRIBUTES[target_kind])
        )
        for target_kind in _TARGET_KIND_ORDER
    }
    if captured_counts != actual_counts:
        raise ValueError(
            "transaction source counts must match the captured document"
        )
    if (
        _environment_dict(composition.index_widths)
        != document.header.index_sizes.to_dict()
    ):
        raise ValueError(
            "transaction index widths must match the captured document"
        )


def _owner_survives(
    composition: PmxStructuralTransactionComposition,
    section: PmxReferenceSourceSection,
    record_index: int,
) -> bool:
    owner_target = _OWNER_TARGETS.get(section)
    if owner_target is None:
        return True
    placement = composition.placement_for(owner_target)
    if placement is None:
        return True
    return placement.remap.target_for(record_index) is not None


def _preflight_existing_references(
    source_certificate: PmxStructuralInvariantCertificate,
    composition: PmxStructuralTransactionComposition,
) -> tuple[PmxStructuralTransactionExistingReferenceEvidence, ...]:
    remapped: list[PmxStructuralTransactionExistingReferenceEvidence] = []
    for edge in source_certificate.reference_graph.edges:
        if not _owner_survives(
            composition,
            edge.source.section,
            edge.source.record_index,
        ):
            continue
        placement = composition.placement_for(edge.target.kind)
        if placement is None:
            continue
        final_index = placement.remap.target_for(edge.target.index)
        if final_index is None:
            raise PmxStructuralTransactionPreviewError(
                "reference_resolution",
                target_kind=edge.target.kind,
                relationship_id=edge.relationship_id,
            )
        if final_index == edge.target.index:
            continue
        remapped.append(
            PmxStructuralTransactionExistingReferenceEvidence(
                relationship_id=edge.relationship_id,
                source_section=edge.source.section,
                source_record_index=edge.source.record_index,
                target_kind=edge.target.kind,
                old_target_index=edge.target.index,
                final_target_index=final_index,
            )
        )
    return tuple(remapped)


def _validate_preview_inputs(
    composition: PmxStructuralTransactionComposition,
    descriptors: tuple[PmxStructuralTransactionOperationDescriptor, ...],
    payloads: PmxStructuralTransactionPayloads,
    local_references: tuple[
        PmxStructuralTransactionLocalReferenceEvidence,
        ...,
    ],
) -> None:
    if type(descriptors) is not tuple:
        raise TypeError("operation_descriptors must be a tuple.")
    if tuple(item.request_ordinal for item in descriptors) != tuple(
        range(len(descriptors))
    ):
        raise ValueError(
            "operation_descriptors must cover request ordinals in request order."
        )
    if not all(
        isinstance(item, PmxStructuralTransactionOperationDescriptor)
        for item in descriptors
    ):
        raise TypeError(
            "operation_descriptors must contain only descriptor values."
        )
    insertion_descriptors = tuple(
        item for item in descriptors if item.category == "insertion"
    )
    if tuple(
        (item.request_ordinal, item.target_kind)
        for item in insertion_descriptors
    ) != tuple(
        (item.request_ordinal, item.target_kind)
        for item in composition.operations
    ):
        raise ValueError(
            "insertion descriptors must match the composition operations."
        )
    transform_targets = tuple(
        item.target_kind
        for item in descriptors
        if item.category == "collection_transform"
    )
    if set(transform_targets) != {item.kind for item in composition.transforms}:
        raise ValueError(
            "collection-transform descriptors must match composition transforms."
        )
    for target_kind in _TARGET_KIND_ORDER:
        expected = sum(
            operation.target_kind is target_kind
            for operation in composition.operations
        )
        if len(payloads.for_target(target_kind)) != expected:
            raise ValueError(
                f"{target_kind.value} payload count must match planned insertions."
            )
    if type(local_references) is not tuple or not all(
        isinstance(item, PmxStructuralTransactionLocalReferenceEvidence)
        for item in local_references
    ):
        raise TypeError(
            "local_references must contain only immutable evidence values."
        )


def _materialize_target(
    document: PmxDocument,
    target_kind: PmxReferenceTargetKind,
    payloads: tuple[object, ...],
) -> PmxStructuralInvariantCertificate:
    if target_kind is PmxReferenceTargetKind.TEXTURE:
        return preview_pmx_texture_insertions(document, payloads).certificate
    if target_kind is PmxReferenceTargetKind.MATERIAL:
        return preview_pmx_material_insertions(document, payloads).certificate
    if target_kind is PmxReferenceTargetKind.BONE:
        return preview_pmx_bone_insertions(document, payloads).certificate
    if target_kind is PmxReferenceTargetKind.VERTEX:
        return preview_pmx_vertex_insertions(document, payloads).certificate
    if target_kind is PmxReferenceTargetKind.RIGID_BODY:
        return preview_pmx_rigid_body_insertions(document, payloads).certificate
    if target_kind is PmxReferenceTargetKind.MORPH:
        return preview_pmx_morph_insertions(document, payloads).certificate
    raise AssertionError(f"unhandled target kind {target_kind.value}")


@dataclass(frozen=True, slots=True)
class PmxStructuralTransactionPreview:
    """One complete certified intended document plus CP16 semantic evidence."""

    source_document: PmxDocument
    composition: PmxStructuralTransactionComposition
    operation_descriptors: tuple[
        PmxStructuralTransactionOperationDescriptor,
        ...,
    ]
    payloads: PmxStructuralTransactionPayloads = field(repr=False)
    local_references: tuple[
        PmxStructuralTransactionLocalReferenceEvidence,
        ...,
    ] = ()
    certificate: PmxStructuralInvariantCertificate = field(init=False)
    remapped_existing_references: tuple[
        PmxStructuralTransactionExistingReferenceEvidence,
        ...,
    ] = field(init=False)
    source_sha256: str = field(init=False)
    plan_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.source_document, PmxDocument):
            raise TypeError("source_document must be a PmxDocument instance.")
        if not isinstance(
            self.composition,
            PmxStructuralTransactionComposition,
        ):
            raise TypeError(
                "composition must be a PmxStructuralTransactionComposition value."
            )
        if not isinstance(self.payloads, PmxStructuralTransactionPayloads):
            raise TypeError("payloads must be prepared transaction payloads.")
        _validate_preview_inputs(
            self.composition,
            self.operation_descriptors,
            self.payloads,
            self.local_references,
        )
        _validate_source_binding(self.source_document, self.composition)

        try:
            source_certificate = PmxStructuralInvariantCertificate(
                document=self.source_document
            )
        except (PmxValidationError, PmxStructuralInvariantError) as error:
            raise PmxStructuralTransactionPreviewError(
                "structural_certification"
            ) from error

        remapped = _preflight_existing_references(
            source_certificate,
            self.composition,
        )
        _preflight_transaction_payloads(
            self.source_document,
            self.composition,
            self.payloads,
        )

        try:
            intended_document = transform_pmx_document(
                self.source_document,
                PmxStructuralTransformIntent(self.composition.transforms),
            )
        except Exception as error:
            raise PmxStructuralTransactionPreviewError("transform") from error

        try:
            certificate = PmxStructuralInvariantCertificate(
                document=intended_document
            )
        except (PmxValidationError, PmxStructuralInvariantError) as error:
            raise PmxStructuralTransactionPreviewError(
                "structural_certification"
            ) from error

        for target_kind in self.composition.dependency.materialization_order:
            target_payloads = self.payloads.for_target(target_kind)
            if not target_payloads:
                continue
            try:
                certificate = _materialize_target(
                    certificate.document,
                    target_kind,
                    target_payloads,
                )
            except (PmxValidationError, PmxStructuralInvariantError) as error:
                raise PmxStructuralTransactionPreviewError(
                    "structural_certification",
                    target_kind=target_kind,
                ) from error
            except Exception as error:
                raise PmxStructuralTransactionPreviewError(
                    "transform",
                    target_kind=target_kind,
                ) from error

        final_counts = tuple(
            (kind, certificate.reference_graph.target_counts.count_for(kind))
            for kind in _TARGET_KIND_ORDER
        )
        if final_counts != self.composition.preflight.final_counts:
            raise AssertionError(
                "certified intended-document counts disagree with preflight."
            )

        object.__setattr__(self, "certificate", certificate)
        object.__setattr__(self, "remapped_existing_references", remapped)
        object.__setattr__(
            self,
            "source_sha256",
            hashlib.sha256(serialize_pmx(self.source_document)).hexdigest(),
        )
        object.__setattr__(
            self,
            "plan_sha256",
            _canonical_sha256(self._plan_evidence()),
        )

    @property
    def status(self) -> str:
        return (
            "no_changes"
            if not self.composition.changed_targets
            else "changes_pending"
        )

    @property
    def normalized_operations(
        self,
    ) -> tuple[PmxStructuralTransactionOperationDescriptor, ...]:
        transform_by_target = {
            item.target_kind: item
            for item in self.operation_descriptors
            if item.category == "collection_transform"
        }
        insertion_by_ordinal = {
            item.request_ordinal: item
            for item in self.operation_descriptors
            if item.category == "insertion"
        }
        normalized: list[PmxStructuralTransactionOperationDescriptor] = []
        for target_kind in _TARGET_KIND_ORDER:
            transform = transform_by_target.get(target_kind)
            if transform is not None:
                normalized.append(transform)
            placement = self.composition.placement_for(target_kind)
            if placement is None:
                continue
            normalized.extend(
                insertion_by_ordinal[binding.request_ordinal]
                for binding in sorted(
                    placement.bindings,
                    key=lambda item: (item.final_index, item.request_ordinal),
                )
            )
        return tuple(normalized)

    def _payloads_by_request_ordinal(self) -> dict[int, object]:
        payloads_by_ordinal: dict[int, object] = {}
        for target_kind in _TARGET_KIND_ORDER:
            descriptors = tuple(
                descriptor
                for descriptor in self.operation_descriptors
                if descriptor.category == "insertion"
                and descriptor.target_kind is target_kind
            )
            payloads = self.payloads.for_target(target_kind)
            if len(descriptors) != len(payloads):
                raise AssertionError(
                    f"{target_kind.value} descriptor/payload counts disagree"
                )
            for descriptor, payload in zip(descriptors, payloads, strict=True):
                payloads_by_ordinal[descriptor.request_ordinal] = payload
        return payloads_by_ordinal

    def _normalized_operation_evidence(self) -> list[dict[str, object]]:
        payloads_by_ordinal = self._payloads_by_request_ordinal()
        evidence: list[dict[str, object]] = []
        for descriptor in self.normalized_operations:
            item = descriptor.to_dict()
            if descriptor.category == "insertion":
                item["payload_sha256"] = _semantic_payload_sha256(
                    payloads_by_ordinal[descriptor.request_ordinal]
                )
            evidence.append(item)
        return evidence

    def _plan_collection_evidence(self) -> list[dict[str, object]]:
        descriptors_by_ordinal = {
            descriptor.request_ordinal: descriptor
            for descriptor in self.operation_descriptors
            if descriptor.category == "insertion"
        }
        collections: list[dict[str, object]] = []
        for placement in self.composition.placements:
            transform = placement.transform
            insertions: list[dict[str, object]] = []
            for binding in sorted(
                placement.bindings,
                key=lambda item: (item.final_index, item.request_ordinal),
            ):
                descriptor = descriptors_by_ordinal[binding.request_ordinal]
                insertions.append(
                    {
                        "request_ordinal": binding.request_ordinal,
                        "position": descriptor.position,
                        "source_index": descriptor.source_index,
                        "final_index": binding.final_index,
                        "new_id": descriptor.new_id,
                    }
                )
            collections.append(
                {
                    "target_kind": placement.target_kind.value,
                    "survivor_old_indices": list(
                        transform.old_indices_in_new_order
                    ),
                    "combined_remap": list(placement.remap.targets),
                    "new_only_positions": list(
                        placement.remap.new_indices_without_old_source
                    ),
                    "insertions": insertions,
                }
            )
        return collections

    def _plan_reference_evidence(self) -> dict[str, object]:
        local_references = sorted(
            self.local_references,
            key=lambda item: (
                item.request_ordinal,
                item.field_name,
                item.relationship_id,
                _TARGET_KIND_RANK[item.target_kind],
                item.new_id,
                item.final_index,
            ),
        )
        existing_references = sorted(
            self.remapped_existing_references,
            key=lambda item: (
                _SOURCE_SECTION_RANK[item.source_section],
                item.source_record_index,
                item.relationship_id,
                _TARGET_KIND_RANK[item.target_kind],
                item.old_target_index,
                item.final_target_index,
            ),
        )
        return {
            "resolved_local": [item.to_dict() for item in local_references],
            "remapped_existing": [
                item.to_dict() for item in existing_references
            ],
        }

    def _plan_evidence(self) -> dict[str, object]:
        dependency = self.composition.dependency
        preflight = self.composition.preflight
        return {
            "schema": _PLAN_SCHEMA,
            "source": {
                "semantic_sha256": self.source_sha256,
                "pmx_version": self.source_document.header.version,
                "declared_index_widths": _environment_dict(
                    self.composition.index_widths
                ),
                "captured_counts": _environment_dict(
                    self.composition.source_counts
                ),
            },
            "operations": {
                "original_count": len(self.operation_descriptors),
                "normalized": self._normalized_operation_evidence(),
            },
            "collections": self._plan_collection_evidence(),
            "identities": [
                {
                    "target_kind": item.target_kind.value,
                    "new_id": item.new_id,
                    "request_ordinal": item.operation_index,
                    "final_index": item.final_index,
                }
                for item in self.composition.identities
            ],
            "references": self._plan_reference_evidence(),
            "dependencies": {
                "nodes": [item.value for item in dependency.nodes],
                "edges": [
                    {
                        "provider": edge.provider_target.value,
                        "consumer": edge.consumer_target.value,
                    }
                    for edge in dependency.edges
                ],
                "materialization_order": [
                    item.value for item in dependency.materialization_order
                ],
            },
            "counts": {
                "final": _environment_dict(preflight.final_counts),
            },
            "preflight": {
                "status": "passed",
                "all_representable": preflight.all_representable,
                "targets": [item.to_dict() for item in preflight.analyses],
            },
        }

    def _collection_effects(self) -> list[dict[str, object]]:
        effects: list[dict[str, object]] = []
        explicit_targets = {
            item.target_kind
            for item in self.operation_descriptors
            if item.category == "collection_transform"
        }
        for placement in self.composition.placements:
            transform = placement.transform
            effects.append(
                {
                    "target_kind": placement.target_kind.value,
                    "explicit_transform": placement.target_kind
                    in explicit_targets,
                    "is_noop": transform.is_noop and not placement.operations,
                    "deleted_old_indices": list(
                        transform.removed_old_indices
                    ),
                    "old_indices_in_survivor_order": list(
                        transform.old_indices_in_new_order
                    ),
                    "reordered": transform.has_reorder,
                    "insertions": [
                        {
                            "request_ordinal": binding.request_ordinal,
                            "final_index": binding.final_index,
                        }
                        for binding in placement.bindings
                    ],
                }
            )
        return effects

    def to_dict(self) -> dict[str, object]:
        dependency = self.composition.dependency
        preflight = self.composition.preflight
        plan = self._plan_evidence()
        plan["sha256"] = self.plan_sha256
        return {
            "plan": plan,
            "status": self.status,
            "dry_run": True,
            "operations": {
                "original_count": len(self.operation_descriptors),
                "request_order": [
                    item.to_dict() for item in self.operation_descriptors
                ],
                "normalized_order": [
                    item.to_dict() for item in self.normalized_operations
                ],
            },
            "effects": {
                "changed_targets": [
                    item.value for item in self.composition.changed_targets
                ],
                "collections": self._collection_effects(),
                "inserted_count": len(self.composition.operations),
                "deleted_count": sum(
                    len(item.transform.removed_old_indices)
                    for item in self.composition.placements
                ),
                "reordered_target_count": sum(
                    item.transform.has_reorder
                    for item in self.composition.placements
                ),
            },
            "references": {
                "declared_identities": [
                    {
                        "target_kind": item.target_kind.value,
                        "new_id": item.new_id,
                        "request_ordinal": item.operation_index,
                        "final_index": item.final_index,
                    }
                    for item in self.composition.identities
                ],
                "resolved_local": [
                    item.to_dict() for item in self.local_references
                ],
                "remapped_existing": [
                    item.to_dict()
                    for item in self.remapped_existing_references
                ],
            },
            "dependencies": {
                "edges": [
                    {
                        "provider": edge.provider_target.value,
                        "consumer": edge.consumer_target.value,
                    }
                    for edge in dependency.edges
                ],
                "materialization_order": [
                    item.value for item in dependency.materialization_order
                ],
            },
            "counts": {
                "captured": _environment_dict(self.composition.source_counts),
                "final": _environment_dict(preflight.final_counts),
            },
            "capacity": {
                "status": "passed",
                "all_representable": preflight.all_representable,
                "targets": [
                    {
                        "target_kind": item.target_kind.value,
                        "declared_width": item.index_width,
                        "final_count": item.result_count,
                        "representable": item.representable,
                    }
                    for item in preflight.analyses
                ],
            },
            "output": {
                "written": False,
                "source_touched": False,
                "destination_touched": False,
            },
            "verification": {
                "invariants": "passed",
                "reference_model": "passed",
                "serialization": "not_performed",
            },
        }


def preview_pmx_structural_transaction(
    document: PmxDocument,
    composition: PmxStructuralTransactionComposition,
    operation_descriptors: tuple[
        PmxStructuralTransactionOperationDescriptor,
        ...,
    ],
    payloads: PmxStructuralTransactionPayloads,
    local_references: tuple[
        PmxStructuralTransactionLocalReferenceEvidence,
        ...,
    ] = (),
) -> PmxStructuralTransactionPreview:
    """Return one complete certified intended transaction document."""

    return PmxStructuralTransactionPreview(
        source_document=document,
        composition=composition,
        operation_descriptors=operation_descriptors,
        payloads=payloads,
        local_references=local_references,
    )


__all__ = (
    "PmxStructuralTransactionLocalReferenceEvidence",
    "PmxStructuralTransactionOperationDescriptor",
    "PmxStructuralTransactionPayloads",
    "PmxStructuralTransactionPreview",
    "PmxStructuralTransactionPreviewError",
    "preview_pmx_structural_transaction",
)
