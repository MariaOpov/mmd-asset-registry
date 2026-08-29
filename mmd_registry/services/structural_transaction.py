"""Public immutable request and preview service for structural transactions."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Callable, TypeAlias

from mmd_registry.diagnostics import (
    PmxServiceDiagnostic,
    PmxServiceDiagnosticCode,
    PmxServiceError,
    PmxServiceOperation,
    diagnostic_from_service_error,
)
from mmd_registry.pmx.collection_transform import PmxCollectionTransform
from mmd_registry.pmx.document import PmxDocument
from mmd_registry.pmx.errors import PmxValidationError
from mmd_registry.pmx.index_remap import PmxIndexRemap
from mmd_registry.pmx.structural_insert_intent import PmxStructuralInsertPosition
from mmd_registry.pmx.structural_invariants import (
    PmxStructuralInvariantCertificate,
    PmxStructuralInvariantError,
)
from mmd_registry.pmx.structural_transaction_composition import (
    PmxStructuralTransactionComposition,
    compose_structural_transaction,
)
from mmd_registry.pmx.structural_transaction_insertion import (
    PmxStructuralTransactionInsertionOperation,
)
from mmd_registry.pmx.structural_transaction_placement import (
    PmxStructuralTransactionPlacementError,
)
from mmd_registry.pmx.structural_transaction_preflight import (
    PmxStructuralTransactionCapacityPreflightError,
)
from mmd_registry.pmx.structural_transaction_preview import (
    PmxStructuralTransactionLocalReferenceEvidence,
    PmxStructuralTransactionOperationDescriptor,
    PmxStructuralTransactionPayloads,
    PmxStructuralTransactionPreview,
    PmxStructuralTransactionPreviewError,
    _preflight_existing_references,
    preview_pmx_structural_transaction,
)
from mmd_registry.services import (
    PmxReferenceTargetKind,
    PmxStructuralCollectionEdit,
    PmxStructuralExecutionResult,
    PmxStructuralPreviewRequest,
    _build_bone_insertion_payloads,
    _build_material_insertion_payloads,
    _build_morph_insertion_payloads,
    _build_rigid_body_insertion_payloads,
    _build_texture_insertion_payloads,
    _build_vertex_insertion_payloads,
)
from mmd_registry.services.structural_bone import PmxStructuralBoneInsertion
from mmd_registry.services.structural_material import (
    PmxStructuralMaterialInsertion,
)
from mmd_registry.services.structural_morph import (
    PmxStructuralMorphBoneOffset,
    PmxStructuralMorphFlipOffset,
    PmxStructuralMorphGroupOffset,
    PmxStructuralMorphImpulseOffset,
    PmxStructuralMorphInsertion,
    PmxStructuralMorphMaterialOffset,
    PmxStructuralMorphUvOffset,
    PmxStructuralMorphVertexOffset,
)
from mmd_registry.services.structural_reference import PmxStructuralNewReference
from mmd_registry.services.structural_rigid_body import (
    PmxStructuralRigidBodyInsertion,
)
from mmd_registry.services.structural_texture import PmxStructuralTextureInsertion
from mmd_registry.services.structural_vertex import (
    PmxStructuralVertexBdef1,
    PmxStructuralVertexBdef2,
    PmxStructuralVertexBdef4,
    PmxStructuralVertexInsertion,
    PmxStructuralVertexQdef,
    PmxStructuralVertexSdef,
)


if TYPE_CHECKING:
    from mmd_registry.pmx.structural_output import (
        PmxStructuralWriteResult,
        _PmxStructuralTransactionSerializationResult,
        _PmxVerifiedStructuralTransactionSerializationResult,
    )


PmxStructuralTransactionOperation: TypeAlias = (
    PmxStructuralCollectionEdit
    | PmxStructuralTextureInsertion
    | PmxStructuralMaterialInsertion
    | PmxStructuralBoneInsertion
    | PmxStructuralMorphInsertion
    | PmxStructuralRigidBodyInsertion
    | PmxStructuralVertexInsertion
)


_TRANSACTION_OPERATION_TYPES: tuple[type[object], ...] = (
    PmxStructuralCollectionEdit,
    PmxStructuralTextureInsertion,
    PmxStructuralMaterialInsertion,
    PmxStructuralBoneInsertion,
    PmxStructuralMorphInsertion,
    PmxStructuralRigidBodyInsertion,
    PmxStructuralVertexInsertion,
)
_INSERTION_TARGET_TYPES = (
    (PmxStructuralVertexInsertion, PmxReferenceTargetKind.VERTEX),
    (PmxStructuralTextureInsertion, PmxReferenceTargetKind.TEXTURE),
    (PmxStructuralMaterialInsertion, PmxReferenceTargetKind.MATERIAL),
    (PmxStructuralBoneInsertion, PmxReferenceTargetKind.BONE),
    (PmxStructuralMorphInsertion, PmxReferenceTargetKind.MORPH),
    (PmxStructuralRigidBodyInsertion, PmxReferenceTargetKind.RIGID_BODY),
)
_REFERENCE_PLANNING_INDEX_WIDTHS = tuple(
    (target_kind, 4) for target_kind in PmxReferenceTargetKind
)


@dataclass(frozen=True, slots=True)
class PmxStructuralTransactionRequest:
    """One ordered tuple of bounded structural transaction operations."""

    operations: tuple[PmxStructuralTransactionOperation, ...] = ()

    def __post_init__(self) -> None:
        if type(self.operations) is not tuple:
            raise TypeError("operations must be a tuple.")
        if not all(
            isinstance(operation, _TRANSACTION_OPERATION_TYPES)
            for operation in self.operations
        ):
            raise TypeError(
                "operations must contain only PmxStructuralCollectionEdit "
                "or supported structural insertion values."
            )

        seen_collection_kinds: set[PmxReferenceTargetKind] = set()
        seen_new_ids: set[str] = set()
        for operation in self.operations:
            if isinstance(operation, PmxStructuralCollectionEdit):
                if operation.target_kind in seen_collection_kinds:
                    raise ValueError(
                        "operations cannot repeat one "
                        "PmxStructuralCollectionEdit target_kind."
                    )
                seen_collection_kinds.add(operation.target_kind)
                continue

            new_id = operation.new_id
            if new_id is None:
                continue
            if new_id in seen_new_ids:
                raise ValueError(
                    f"request-local new_id {new_id!r} must be globally unique."
                )
            seen_new_ids.add(new_id)


@dataclass(frozen=True, slots=True)
class PmxStructuralTransactionPreviewResult:
    """Public transaction preview without exposing an internal plan."""

    _preview: PmxStructuralTransactionPreview = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self._preview, PmxStructuralTransactionPreview):
            raise TypeError(
                "_preview must be an internal structural transaction preview."
            )

    @property
    def status(self) -> str:
        return self._preview.status

    @property
    def document(self) -> PmxDocument:
        return self._preview.certificate.document

    @property
    def plan_sha256(self) -> str:
        """Return the canonical source-bound structural transaction digest."""

        return self._preview.plan_sha256

    def to_dict(self) -> dict[str, object]:
        """Return deterministic source-bound CP17 preview evidence."""

        return self._preview.to_dict()


def _target_kind_for_insertion(operation: object) -> PmxReferenceTargetKind:
    for operation_type, target_kind in _INSERTION_TARGET_TYPES:
        if isinstance(operation, operation_type):
            return target_kind
    raise AssertionError("validated request exposed an unsupported insertion.")


def _source_counts(
    document: PmxDocument,
) -> tuple[tuple[PmxReferenceTargetKind, int], ...]:
    counts = {
        PmxReferenceTargetKind.VERTEX: len(document.vertices),
        PmxReferenceTargetKind.TEXTURE: len(document.texture_paths),
        PmxReferenceTargetKind.MATERIAL: len(document.materials),
        PmxReferenceTargetKind.BONE: len(document.bones),
        PmxReferenceTargetKind.MORPH: len(document.morphs),
        PmxReferenceTargetKind.RIGID_BODY: len(document.rigid_bodies),
    }
    return tuple((target_kind, counts[target_kind]) for target_kind in counts)


def _index_widths(
    document: PmxDocument,
) -> tuple[tuple[PmxReferenceTargetKind, int], ...]:
    widths = document.header.index_sizes
    return tuple(
        (target_kind, getattr(widths, target_kind.value))
        for target_kind in PmxReferenceTargetKind
    )


def _collection_transform(
    edit: PmxStructuralCollectionEdit,
    source_counts: tuple[tuple[PmxReferenceTargetKind, int], ...],
) -> PmxCollectionTransform:
    old_size = dict(source_counts)[edit.target_kind]
    for old_index in edit.old_indices_in_new_order:
        if old_index >= old_size:
            raise ValueError(
                f"{edit.target_kind.value} old index is outside source domain."
            )
    targets: list[int | None] = [None] * old_size
    for new_index, old_index in enumerate(edit.old_indices_in_new_order):
        targets[old_index] = new_index
    return PmxCollectionTransform(
        kind=edit.target_kind,
        remap=PmxIndexRemap(
            targets=tuple(targets),
            new_size=len(edit.old_indices_in_new_order),
        ),
    )


def _operation_position(operation: object) -> PmxStructuralInsertPosition:
    if operation.position == "append":
        return PmxStructuralInsertPosition.append()
    assert operation.position == "insert_before"
    assert operation.source_index is not None
    return PmxStructuralInsertPosition.insert_before(operation.source_index)


def _build_composition(
    document: PmxDocument,
    request: PmxStructuralTransactionRequest,
    *,
    index_widths: tuple[tuple[PmxReferenceTargetKind, int], ...] | None = None,
) -> tuple[
    PmxStructuralTransactionComposition,
    tuple[PmxStructuralTransactionOperationDescriptor, ...],
]:
    source_counts = _source_counts(document)
    transforms = tuple(
        _collection_transform(operation, source_counts)
        for operation in sorted(
            (
                operation
                for operation in request.operations
                if isinstance(operation, PmxStructuralCollectionEdit)
            ),
            key=lambda item: tuple(PmxReferenceTargetKind).index(
                item.target_kind
            ),
        )
    )
    insertion_operations: list[PmxStructuralTransactionInsertionOperation] = []
    descriptors: list[PmxStructuralTransactionOperationDescriptor] = []
    for request_ordinal, operation in enumerate(request.operations):
        if isinstance(operation, PmxStructuralCollectionEdit):
            descriptors.append(
                PmxStructuralTransactionOperationDescriptor(
                    request_ordinal=request_ordinal,
                    category="collection_transform",
                    target_kind=operation.target_kind,
                )
            )
            continue
        target_kind = _target_kind_for_insertion(operation)
        descriptors.append(
            PmxStructuralTransactionOperationDescriptor(
                request_ordinal=request_ordinal,
                category="insertion",
                target_kind=target_kind,
                position=operation.position,
                source_index=operation.source_index,
                new_id=operation.new_id,
            )
        )
        insertion_operations.append(
            PmxStructuralTransactionInsertionOperation(
                request_ordinal=request_ordinal,
                target_kind=target_kind,
                position=_operation_position(operation),
                new_id=operation.new_id,
            )
        )

    composition = compose_structural_transaction(
        source_counts=source_counts,
        index_widths=(
            _index_widths(document)
            if index_widths is None
            else index_widths
        ),
        transforms=transforms,
        operations=tuple(insertion_operations),
    )
    return composition, tuple(descriptors)


def _resolve_source_reference_before_target_insertion(
    composition: PmxStructuralTransactionComposition,
    target_kind: PmxReferenceTargetKind,
    value: object,
    *,
    allow_sentinel: bool,
    field_name: str,
) -> int:
    if type(value) is not int:
        raise TypeError(f"{field_name} source reference must be an integer.")
    if value == -1:
        if allow_sentinel:
            return -1
        raise ValueError(f"{field_name} does not allow the -1 sentinel.")
    source_count = dict(composition.source_counts)[target_kind]
    if value < 0 or value >= source_count:
        raise ValueError(f"{field_name} is outside the captured source domain.")
    placement = composition.placement_for(target_kind)
    if placement is None:
        return value
    survivor_index = placement.transform.remap.target_for(value)
    if survivor_index is None:
        raise ValueError(
            f"{field_name} references a deleted captured-source target."
        )
    return survivor_index


def _resolve_reference(
    composition: PmxStructuralTransactionComposition,
    value: object,
    target_kind: PmxReferenceTargetKind,
    *,
    current_target: PmxReferenceTargetKind,
    allow_sentinel: bool,
    field_name: str,
    relationship_id: str,
    request_ordinal: int,
    local_references: list[PmxStructuralTransactionLocalReferenceEvidence],
) -> int:
    try:
        if isinstance(value, PmxStructuralNewReference):
            if value.target_kind != target_kind.value:
                raise ValueError(f"{field_name} local target kind does not match.")
            final_index = composition.reference_resolver.resolve_new_reference(
                target_kind,
                value.new_id,
                field_name=field_name,
            )
            local_references.append(
                PmxStructuralTransactionLocalReferenceEvidence(
                    request_ordinal=request_ordinal,
                    field_name=field_name,
                    relationship_id=relationship_id,
                    target_kind=target_kind,
                    new_id=value.new_id,
                    final_index=final_index,
                )
            )
            return final_index
        if target_kind is current_target:
            return _resolve_source_reference_before_target_insertion(
                composition,
                target_kind,
                value,
                allow_sentinel=allow_sentinel,
                field_name=field_name,
            )
        return composition.reference_resolver.resolve_source_reference(
            target_kind,
            value,
            allow_sentinel=allow_sentinel,
            field_name=field_name,
        )
    except (TypeError, ValueError) as error:
        raise PmxStructuralTransactionPreviewError(
            "reference_resolution",
            operation_index=request_ordinal,
            target_kind=target_kind,
            new_id=(
                value.new_id
                if isinstance(value, PmxStructuralNewReference)
                else None
            ),
            relationship_id=relationship_id,
        ) from error


def _resolved_position(
    operation: PmxStructuralTransactionOperation,
    composition: PmxStructuralTransactionComposition,
    target_kind: PmxReferenceTargetKind,
) -> dict[str, object]:
    if operation.position == "append":
        return {"position": "append", "source_index": None}
    assert operation.source_index is not None
    placement = composition.placement_for(target_kind)
    assert placement is not None
    survivor_index = placement.transform.remap.target_for(operation.source_index)
    if survivor_index is None:
        raise ValueError("insertion anchor was deleted by the transaction.")
    return {"position": "insert_before", "source_index": survivor_index}


def _resolve_material(
    operation: PmxStructuralMaterialInsertion,
    request_ordinal: int,
    composition: PmxStructuralTransactionComposition,
    local_references: list[PmxStructuralTransactionLocalReferenceEvidence],
) -> PmxStructuralMaterialInsertion:
    arguments: dict[str, object] = {
        "texture_index": _resolve_reference(
            composition,
            operation.texture_index,
            PmxReferenceTargetKind.TEXTURE,
            current_target=PmxReferenceTargetKind.MATERIAL,
            allow_sentinel=True,
            field_name="material.texture_index",
            relationship_id="material.texture",
            request_ordinal=request_ordinal,
            local_references=local_references,
        ),
        "sphere_texture_index": _resolve_reference(
            composition,
            operation.sphere_texture_index,
            PmxReferenceTargetKind.TEXTURE,
            current_target=PmxReferenceTargetKind.MATERIAL,
            allow_sentinel=True,
            field_name="material.sphere_texture_index",
            relationship_id="material.sphere_texture",
            request_ordinal=request_ordinal,
            local_references=local_references,
        ),
    }
    if operation.toon_reference_mode == "texture":
        arguments["toon_reference_index"] = _resolve_reference(
            composition,
            operation.toon_reference_index,
            PmxReferenceTargetKind.TEXTURE,
            current_target=PmxReferenceTargetKind.MATERIAL,
            allow_sentinel=True,
            field_name="material.toon_reference_index",
            relationship_id="material.toon_texture",
            request_ordinal=request_ordinal,
            local_references=local_references,
        )
    arguments.update(
        _resolved_position(
            operation,
            composition,
            PmxReferenceTargetKind.MATERIAL,
        )
    )
    return replace(operation, **arguments)


def _resolve_vertex_deform(
    deform: object,
    request_ordinal: int,
    composition: PmxStructuralTransactionComposition,
    local_references: list[PmxStructuralTransactionLocalReferenceEvidence],
) -> object:
    if isinstance(deform, PmxStructuralVertexBdef1):
        return replace(
            deform,
            bone_index=_resolve_reference(
                composition,
                deform.bone_index,
                PmxReferenceTargetKind.BONE,
                current_target=PmxReferenceTargetKind.VERTEX,
                allow_sentinel=True,
                field_name="vertex.deform.bone_index",
                relationship_id="vertex.deform.bdef1.bone",
                request_ordinal=request_ordinal,
                local_references=local_references,
            ),
        )
    if isinstance(
        deform,
        (
            PmxStructuralVertexBdef2,
            PmxStructuralVertexBdef4,
            PmxStructuralVertexSdef,
            PmxStructuralVertexQdef,
        ),
    ):
        return replace(
            deform,
            bone_indices=tuple(
                _resolve_reference(
                    composition,
                    value,
                    PmxReferenceTargetKind.BONE,
                    current_target=PmxReferenceTargetKind.VERTEX,
                    allow_sentinel=True,
                    field_name=f"vertex.deform.bone_indices[{index}]",
                    relationship_id="vertex.deform.multi.bone",
                    request_ordinal=request_ordinal,
                    local_references=local_references,
                )
                for index, value in enumerate(deform.bone_indices)
            ),
        )
    raise AssertionError("validated vertex exposed an unsupported deform.")


def _resolve_vertex(
    operation: PmxStructuralVertexInsertion,
    request_ordinal: int,
    composition: PmxStructuralTransactionComposition,
    local_references: list[PmxStructuralTransactionLocalReferenceEvidence],
) -> PmxStructuralVertexInsertion:
    return replace(
        operation,
        deform=_resolve_vertex_deform(
            operation.deform,
            request_ordinal,
            composition,
            local_references,
        ),
        **_resolved_position(
            operation,
            composition,
            PmxReferenceTargetKind.VERTEX,
        ),
    )


def _resolve_bone(
    operation: PmxStructuralBoneInsertion,
    request_ordinal: int,
    composition: PmxStructuralTransactionComposition,
    local_references: list[PmxStructuralTransactionLocalReferenceEvidence],
) -> PmxStructuralBoneInsertion:
    def source(
        value: object,
        *,
        field: str,
        relationship: str,
        sentinel: bool,
    ) -> int:
        return _resolve_reference(
            composition,
            value,
            PmxReferenceTargetKind.BONE,
            current_target=PmxReferenceTargetKind.BONE,
            allow_sentinel=sentinel,
            field_name=field,
            relationship_id=relationship,
            request_ordinal=request_ordinal,
            local_references=local_references,
        )

    arguments: dict[str, object] = {
        "parent_bone_index": source(
            operation.parent_bone_index,
            field="bone.parent_bone_index",
            relationship="bone.parent",
            sentinel=True,
        ),
    }
    if operation.tail_bone_index is not None:
        arguments["tail_bone_index"] = source(
            operation.tail_bone_index,
            field="bone.tail_bone_index",
            relationship="bone.tail",
            sentinel=True,
        )
    if operation.inherit_parent_bone_index is not None:
        arguments["inherit_parent_bone_index"] = source(
            operation.inherit_parent_bone_index,
            field="bone.inherit_parent_bone_index",
            relationship="bone.inherit_parent",
            sentinel=True,
        )
    if operation.ik is not None:
        arguments["ik"] = replace(
            operation.ik,
            target_bone_index=source(
                operation.ik.target_bone_index,
                field="bone.ik.target_bone_index",
                relationship="bone.ik_target",
                sentinel=False,
            ),
            links=tuple(
                replace(
                    link,
                    bone_index=source(
                        link.bone_index,
                        field=f"bone.ik.links[{index}].bone_index",
                        relationship="bone.ik_link",
                        sentinel=False,
                    ),
                )
                for index, link in enumerate(operation.ik.links)
            ),
        )
    arguments.update(
        _resolved_position(
            operation,
            composition,
            PmxReferenceTargetKind.BONE,
        )
    )
    return replace(operation, **arguments)


def _resolve_rigid_body(
    operation: PmxStructuralRigidBodyInsertion,
    request_ordinal: int,
    composition: PmxStructuralTransactionComposition,
    local_references: list[PmxStructuralTransactionLocalReferenceEvidence],
) -> PmxStructuralRigidBodyInsertion:
    return replace(
        operation,
        bone_index=_resolve_reference(
            composition,
            operation.bone_index,
            PmxReferenceTargetKind.BONE,
            current_target=PmxReferenceTargetKind.RIGID_BODY,
            allow_sentinel=True,
            field_name="rigid_body.bone_index",
            relationship_id="rigid_body.bone",
            request_ordinal=request_ordinal,
            local_references=local_references,
        ),
        **_resolved_position(
            operation,
            composition,
            PmxReferenceTargetKind.RIGID_BODY,
        ),
    )


def _resolve_morph_offset(
    offset: object,
    offset_index: int,
    request_ordinal: int,
    composition: PmxStructuralTransactionComposition,
    local_references: list[PmxStructuralTransactionLocalReferenceEvidence],
) -> object:
    specifications = (
        (
            PmxStructuralMorphGroupOffset,
            "morph_index",
            PmxReferenceTargetKind.MORPH,
            False,
            "morph.group.morph",
        ),
        (
            PmxStructuralMorphVertexOffset,
            "vertex_index",
            PmxReferenceTargetKind.VERTEX,
            False,
            "morph.vertex.vertex",
        ),
        (
            PmxStructuralMorphBoneOffset,
            "bone_index",
            PmxReferenceTargetKind.BONE,
            False,
            "morph.bone.bone",
        ),
        (
            PmxStructuralMorphUvOffset,
            "vertex_index",
            PmxReferenceTargetKind.VERTEX,
            False,
            "morph.uv.vertex",
        ),
        (
            PmxStructuralMorphMaterialOffset,
            "material_index",
            PmxReferenceTargetKind.MATERIAL,
            True,
            "morph.material.material",
        ),
        (
            PmxStructuralMorphFlipOffset,
            "morph_index",
            PmxReferenceTargetKind.MORPH,
            False,
            "morph.flip.morph",
        ),
        (
            PmxStructuralMorphImpulseOffset,
            "rigid_body_index",
            PmxReferenceTargetKind.RIGID_BODY,
            False,
            "morph.impulse.rigid_body",
        ),
    )
    for offset_type, field_name, target_kind, sentinel, relationship in specifications:
        if not isinstance(offset, offset_type):
            continue
        return replace(
            offset,
            **{
                field_name: _resolve_reference(
                    composition,
                    getattr(offset, field_name),
                    target_kind,
                    current_target=PmxReferenceTargetKind.MORPH,
                    allow_sentinel=sentinel,
                    field_name=f"morph.offsets[{offset_index}].{field_name}",
                    relationship_id=relationship,
                    request_ordinal=request_ordinal,
                    local_references=local_references,
                )
            },
        )
    raise AssertionError("validated morph exposed an unsupported offset.")


def _resolve_morph(
    operation: PmxStructuralMorphInsertion,
    request_ordinal: int,
    composition: PmxStructuralTransactionComposition,
    local_references: list[PmxStructuralTransactionLocalReferenceEvidence],
) -> PmxStructuralMorphInsertion:
    return replace(
        operation,
        offsets=tuple(
            _resolve_morph_offset(
                offset,
                index,
                request_ordinal,
                composition,
                local_references,
            )
            for index, offset in enumerate(operation.offsets)
        ),
        **_resolved_position(
            operation,
            composition,
            PmxReferenceTargetKind.MORPH,
        ),
    )


def _resolve_operations(
    request: PmxStructuralTransactionRequest,
    composition: PmxStructuralTransactionComposition,
) -> tuple[
    PmxStructuralPreviewRequest,
    tuple[PmxStructuralTransactionLocalReferenceEvidence, ...],
]:
    grouped: dict[PmxReferenceTargetKind, list[object]] = {
        target_kind: [] for target_kind in PmxReferenceTargetKind
    }
    local_references: list[PmxStructuralTransactionLocalReferenceEvidence] = []
    for request_ordinal, operation in enumerate(request.operations):
        if isinstance(operation, PmxStructuralCollectionEdit):
            continue
        target_kind = _target_kind_for_insertion(operation)
        if isinstance(operation, PmxStructuralMaterialInsertion):
            resolved = _resolve_material(
                operation,
                request_ordinal,
                composition,
                local_references,
            )
        elif isinstance(operation, PmxStructuralVertexInsertion):
            resolved = _resolve_vertex(
                operation,
                request_ordinal,
                composition,
                local_references,
            )
        elif isinstance(operation, PmxStructuralBoneInsertion):
            resolved = _resolve_bone(
                operation,
                request_ordinal,
                composition,
                local_references,
            )
        elif isinstance(operation, PmxStructuralRigidBodyInsertion):
            resolved = _resolve_rigid_body(
                operation,
                request_ordinal,
                composition,
                local_references,
            )
        elif isinstance(operation, PmxStructuralMorphInsertion):
            resolved = _resolve_morph(
                operation,
                request_ordinal,
                composition,
                local_references,
            )
        else:
            resolved = replace(
                operation,
                **_resolved_position(operation, composition, target_kind),
            )
        grouped[target_kind].append(resolved)

    return (
        PmxStructuralPreviewRequest(
            vertex_insertions=tuple(grouped[PmxReferenceTargetKind.VERTEX]),
            texture_insertions=tuple(grouped[PmxReferenceTargetKind.TEXTURE]),
            material_insertions=tuple(grouped[PmxReferenceTargetKind.MATERIAL]),
            bone_insertions=tuple(grouped[PmxReferenceTargetKind.BONE]),
            morph_insertions=tuple(grouped[PmxReferenceTargetKind.MORPH]),
            rigid_body_insertions=tuple(
                grouped[PmxReferenceTargetKind.RIGID_BODY]
            ),
        ),
        tuple(local_references),
    )


def _build_payloads(
    request: PmxStructuralPreviewRequest,
) -> PmxStructuralTransactionPayloads:
    return PmxStructuralTransactionPayloads(
        vertex=(
            _build_vertex_insertion_payloads(request)
            if request.vertex_insertions
            else ()
        ),
        texture=(
            _build_texture_insertion_payloads(request)
            if request.texture_insertions
            else ()
        ),
        material=(
            _build_material_insertion_payloads(request)
            if request.material_insertions
            else ()
        ),
        bone=(
            _build_bone_insertion_payloads(request)
            if request.bone_insertions
            else ()
        ),
        morph=(
            _build_morph_insertion_payloads(request)
            if request.morph_insertions
            else ()
        ),
        rigid_body=(
            _build_rigid_body_insertion_payloads(request)
            if request.rigid_body_insertions
            else ()
        ),
    )


_TransactionStageCallback: TypeAlias = Callable[[str], None]
_TRANSACTION_FAILURE_PROVENANCE: tuple[tuple[str, str], ...] = (
    ("service_validation", "service_boundary"),
    ("path_resolution", "safe_output"),
    ("source_snapshot", "source_input"),
    ("source_parse", "source_input"),
    ("transaction_normalization", "transaction_plan"),
    ("reference_resolution", "transaction_plan"),
    ("dependency_resolution", "transaction_plan"),
    ("capacity_preflight", "transaction_plan"),
    ("transform", "structural_pipeline"),
    ("structural_certification", "structural_pipeline"),
    ("serialization", "structural_pipeline"),
    ("reparse", "structural_pipeline"),
    ("reparse_certification", "structural_pipeline"),
    ("semantic_compare", "structural_pipeline"),
    ("source_reverify", "safe_output"),
    ("output_commit", "safe_output"),
)


def _transaction_failure_provenance(stage: str) -> str:
    """Resolve one frozen transaction stage without mutable global state."""

    for candidate_stage, provenance in _TRANSACTION_FAILURE_PROVENANCE:
        if stage == candidate_stage:
            return provenance
    raise AssertionError(f"unsupported structural transaction stage: {stage!r}")


def _notify_transaction_stage(
    stage_callback: _TransactionStageCallback | None,
    stage: str,
) -> None:
    _transaction_failure_provenance(stage)
    if stage_callback is not None:
        stage_callback(stage)


def _service_error(error: Exception) -> PmxServiceError:
    if isinstance(error, PmxStructuralTransactionPreviewError):
        details: list[tuple[str, str | int | bool | None]] = [
            ("stage", error.stage),
            ("provenance", error.provenance),
            ("source_bytes_read", False),
            ("source_modified", False),
            ("destination_published", False),
        ]
        for key, value in (
            ("operation_index", error.operation_index),
            (
                "target_kind",
                error.target_kind.value
                if error.target_kind is not None
                else None,
            ),
            ("new_id", error.new_id),
            ("relationship_id", error.relationship_id),
        ):
            if value is not None:
                details.append((key, value))
        diagnostic = PmxServiceDiagnostic(
            code=PmxServiceDiagnosticCode.STRUCTURAL_PREVIEW_FAILED,
            operation=PmxServiceOperation.PREVIEW_STRUCTURAL_TRANSACTION,
            message="Structural transaction preview was blocked.",
            details=tuple(details),
        )
    elif isinstance(error, (TypeError, ValueError)):
        diagnostic = PmxServiceDiagnostic(
            code=PmxServiceDiagnosticCode.INVALID_ARGUMENT,
            operation=PmxServiceOperation.PREVIEW_STRUCTURAL_TRANSACTION,
            message="Invalid structural transaction preview input.",
            details=(
                ("stage", "service_validation"),
                ("provenance", "service_boundary"),
                ("source_bytes_read", False),
                ("source_modified", False),
                ("destination_published", False),
            ),
        )
    else:
        diagnostic = PmxServiceDiagnostic(
            code=PmxServiceDiagnosticCode.INTERNAL_ERROR,
            operation=PmxServiceOperation.PREVIEW_STRUCTURAL_TRANSACTION,
            message="Unexpected internal service failure.",
            details=(
                ("source_bytes_read", False),
                ("source_modified", False),
                ("destination_published", False),
            ),
        )
    return PmxServiceError(diagnostic)


def _execution_service_error(
    error: Exception,
    stage: str,
    *,
    source_bytes_read: bool,
) -> PmxServiceError:
    """Attach exact bounded transaction provenance to one execution failure."""

    if not isinstance(source_bytes_read, bool):
        raise TypeError("source_bytes_read must be a boolean.")
    authoritative_stage = stage
    if isinstance(error, PmxStructuralTransactionPreviewError):
        # Source certification is part of execution's captured-source parse
        # stage.  Later preview blockers retain their more specific authority.
        if not (
            stage == "source_parse"
            and error.stage == "structural_certification"
        ):
            authoritative_stage = error.stage
    provenance = _transaction_failure_provenance(authoritative_stage)
    diagnostic = diagnostic_from_service_error(
        PmxServiceOperation.APPLY_STRUCTURAL_TRANSACTION,
        error,
    )
    reserved_keys = {
        "stage",
        "provenance",
        "source_bytes_read",
        "source_modified",
        "destination_published",
    }
    if any(key in reserved_keys for key, _value in diagnostic.details):
        raise AssertionError(
            "diagnostic already contains transaction provenance details"
        )
    details: list[tuple[str, str | int | bool | None]] = [
        *diagnostic.details,
        ("stage", authoritative_stage),
        ("provenance", provenance),
        ("source_bytes_read", source_bytes_read),
        ("source_modified", False),
        ("destination_published", False),
    ]
    if isinstance(error, PmxStructuralTransactionPreviewError):
        for key, value in (
            ("operation_index", error.operation_index),
            (
                "target_kind",
                error.target_kind.value
                if error.target_kind is not None
                else None,
            ),
            ("new_id", error.new_id),
            ("relationship_id", error.relationship_id),
        ):
            if value is not None:
                details.append((key, value))
    return PmxServiceError(
        PmxServiceDiagnostic(
            code=diagnostic.code,
            operation=diagnostic.operation,
            message=diagnostic.message,
            details=tuple(details),
        )
    )


def _plan_structural_transaction(
    document: PmxDocument,
    request: PmxStructuralTransactionRequest,
) -> PmxStructuralTransactionPreview:
    """Build the sole typed plan shared by preview and future execution."""

    return _plan_structural_transaction_with_stage_callback(
        document,
        request,
        None,
    )


def _plan_structural_transaction_with_stage_callback(
    document: PmxDocument,
    request: PmxStructuralTransactionRequest,
    stage_callback: _TransactionStageCallback | None,
) -> PmxStructuralTransactionPreview:
    """Build the sole plan while reporting only contract-level stages."""

    if stage_callback is not None and not callable(stage_callback):
        raise TypeError("stage_callback must be callable or None.")
    if not isinstance(document, PmxDocument):
        raise TypeError("document must be a PmxDocument instance.")
    if not isinstance(request, PmxStructuralTransactionRequest):
        raise TypeError(
            "request must be a PmxStructuralTransactionRequest instance."
        )
    try:
        source_certificate = PmxStructuralInvariantCertificate(
            document=document
        )
    except (PmxValidationError, PmxStructuralInvariantError) as error:
        raise PmxStructuralTransactionPreviewError(
            "structural_certification"
        ) from error

    _notify_transaction_stage(stage_callback, "transaction_normalization")
    try:
        reference_composition, reference_descriptors = _build_composition(
            document,
            request,
            index_widths=_REFERENCE_PLANNING_INDEX_WIDTHS,
        )
    except PmxStructuralTransactionPlacementError as error:
        raise PmxStructuralTransactionPreviewError(
            "transaction_normalization"
        ) from error
    except PmxStructuralTransactionCapacityPreflightError as error:
        raise PmxStructuralTransactionPreviewError(
            "capacity_preflight"
        ) from error
    except (TypeError, ValueError) as error:
        raise PmxStructuralTransactionPreviewError(
            "transaction_normalization"
        ) from error

    _notify_transaction_stage(stage_callback, "reference_resolution")
    try:
        reference_request, reference_local_references = _resolve_operations(
            request,
            reference_composition,
        )
        _preflight_existing_references(
            source_certificate,
            reference_composition,
        )
    except PmxStructuralTransactionPreviewError:
        raise
    except (TypeError, ValueError) as error:
        raise PmxStructuralTransactionPreviewError(
            "reference_resolution"
        ) from error

    _notify_transaction_stage(stage_callback, "dependency_resolution")
    _notify_transaction_stage(stage_callback, "capacity_preflight")
    try:
        composition, descriptors = _build_composition(document, request)
    except PmxStructuralTransactionCapacityPreflightError as error:
        raise PmxStructuralTransactionPreviewError(
            "capacity_preflight"
        ) from error
    except PmxStructuralTransactionPlacementError as error:
        raise PmxStructuralTransactionPreviewError(
            "transaction_normalization"
        ) from error
    except (TypeError, ValueError) as error:
        raise PmxStructuralTransactionPreviewError(
            "transaction_normalization"
        ) from error

    try:
        resolved_request, local_references = _resolve_operations(
            request,
            composition,
        )
    except PmxStructuralTransactionPreviewError:
        raise
    except (TypeError, ValueError) as error:
        raise PmxStructuralTransactionPreviewError(
            "reference_resolution"
        ) from error
    if (
        descriptors != reference_descriptors
        or resolved_request != reference_request
        or local_references != reference_local_references
    ):
        raise AssertionError(
            "reference planning changed under declared capacity widths."
        )

    try:
        payloads = _build_payloads(resolved_request)
    except (TypeError, ValueError) as error:
        raise PmxStructuralTransactionPreviewError(
            "capacity_preflight"
        ) from error

    _notify_transaction_stage(stage_callback, "transform")
    return preview_pmx_structural_transaction(
        document,
        composition,
        descriptors,
        payloads,
        local_references,
    )


def _serialize_structural_transaction(
    document: PmxDocument,
    request: PmxStructuralTransactionRequest,
) -> _PmxStructuralTransactionSerializationResult:
    """Derive CP19 in-memory bytes from the sole transaction planner."""

    from mmd_registry.pmx.structural_output import (
        _PmxStructuralTransactionSerializationResult,
    )

    return _PmxStructuralTransactionSerializationResult(
        _plan_structural_transaction(document, request)
    )


def _serialize_structural_transaction_with_stage_callback(
    document: PmxDocument,
    request: PmxStructuralTransactionRequest,
    stage_callback: _TransactionStageCallback,
) -> _PmxStructuralTransactionSerializationResult:
    if not callable(stage_callback):
        raise TypeError("stage_callback must be callable.")
    from mmd_registry.pmx.structural_output import (
        _PmxStructuralTransactionSerializationResult,
    )

    preview = _plan_structural_transaction_with_stage_callback(
        document,
        request,
        stage_callback,
    )
    return _PmxStructuralTransactionSerializationResult._with_stage_callback(
        preview,
        stage_callback,
    )


def _verify_structural_transaction_serialization(
    document: PmxDocument,
    request: PmxStructuralTransactionRequest,
) -> _PmxVerifiedStructuralTransactionSerializationResult:
    """Prove CP20 whole-document equality without publication authority."""

    from mmd_registry.pmx.structural_output import (
        _PmxVerifiedStructuralTransactionSerializationResult,
    )

    return _PmxVerifiedStructuralTransactionSerializationResult(
        _serialize_structural_transaction(document, request)
    )


def _verify_structural_transaction_serialization_with_stage_callback(
    document: PmxDocument,
    request: PmxStructuralTransactionRequest,
    stage_callback: _TransactionStageCallback,
) -> _PmxVerifiedStructuralTransactionSerializationResult:
    if not callable(stage_callback):
        raise TypeError("stage_callback must be callable.")
    from mmd_registry.pmx.structural_output import (
        _PmxVerifiedStructuralTransactionSerializationResult,
    )

    serialization = _serialize_structural_transaction_with_stage_callback(
        document,
        request,
        stage_callback,
    )
    return _PmxVerifiedStructuralTransactionSerializationResult._with_stage_callback(
        serialization,
        stage_callback,
    )


def _write_structural_transaction(
    input_path: str | Path,
    output_path: str | Path,
    request: PmxStructuralTransactionRequest,
    *,
    overwrite: bool = False,
) -> PmxStructuralWriteResult:
    """Atomically publish only CP20-verified transaction serialization."""

    return _write_structural_transaction_with_stage_callback(
        input_path,
        output_path,
        request,
        overwrite=overwrite,
        stage_callback=None,
    )


def _write_structural_transaction_with_stage_callback(
    input_path: str | Path,
    output_path: str | Path,
    request: PmxStructuralTransactionRequest,
    *,
    overwrite: bool,
    stage_callback: _TransactionStageCallback | None,
    _source_sha256_validator: Callable[[str], None] | None = None,
) -> PmxStructuralWriteResult:
    """Run the private writer with optional transaction-stage translation."""

    if not isinstance(request, PmxStructuralTransactionRequest):
        raise TypeError(
            "request must be a PmxStructuralTransactionRequest instance."
        )
    if not isinstance(overwrite, bool):
        raise TypeError("overwrite must be a boolean.")
    if stage_callback is not None and not callable(stage_callback):
        raise TypeError("stage_callback must be callable or None.")
    if (
        _source_sha256_validator is not None
        and not callable(_source_sha256_validator)
    ):
        raise TypeError(
            "_source_sha256_validator must be callable or None."
        )

    from mmd_registry.pmx.structural_output import (
        PmxStructuralOutputVerificationError,
        _write_verified_structural_transaction,
    )

    if stage_callback is None:
        return _write_verified_structural_transaction(
            input_path,
            output_path,
            lambda document, _stage_callback: (
                _verify_structural_transaction_serialization(document, request)
            ),
            overwrite=overwrite,
            _source_sha256_validator=_source_sha256_validator,
        )

    last_stage: str | None = None

    def report_output_stage(stage: str) -> None:
        nonlocal last_stage
        if stage == "intent_resolution":
            return
        transaction_stage = (
            "source_reverify" if stage == "output_commit" else stage
        )
        _transaction_failure_provenance(transaction_stage)
        last_stage = transaction_stage
        stage_callback(transaction_stage)

    def serialize_transaction(
        document: PmxDocument,
        output_stage_callback: _TransactionStageCallback | None,
    ) -> _PmxVerifiedStructuralTransactionSerializationResult:
        if output_stage_callback is None:
            raise AssertionError("transaction execution requires stage reporting")
        return _verify_structural_transaction_serialization_with_stage_callback(
            document,
            request,
            output_stage_callback,
        )

    try:
        result = _write_verified_structural_transaction(
            input_path,
            output_path,
            serialize_transaction,
            overwrite=overwrite,
            _stage_callback=report_output_stage,
            _source_sha256_validator=_source_sha256_validator,
        )
    except Exception as error:
        if last_stage == "source_reverify" and not isinstance(
            error,
            PmxStructuralOutputVerificationError,
        ):
            last_stage = "output_commit"
            stage_callback(last_stage)
        raise
    stage_callback("output_commit")
    return result


def preview_structural_transaction(
    document: PmxDocument,
    request: PmxStructuralTransactionRequest,
) -> PmxStructuralTransactionPreviewResult:
    """Preview one bounded transaction without filesystem access or publication."""

    try:
        return PmxStructuralTransactionPreviewResult(
            _plan_structural_transaction(document, request)
        )
    except Exception as error:
        failure = _service_error(error)
    raise failure from None


def apply_structural_transaction(
    input_path: str | Path,
    output_path: str | Path,
    request: PmxStructuralTransactionRequest,
    *,
    overwrite: bool = False,
) -> PmxStructuralExecutionResult:
    """Execute and atomically publish one complete structural transaction."""

    failure_stage = "service_validation"
    source_bytes_read = False

    def record_stage(stage: str) -> None:
        nonlocal failure_stage, source_bytes_read
        _transaction_failure_provenance(stage)
        failure_stage = stage
        if stage == "source_parse":
            source_bytes_read = True

    try:
        if not isinstance(request, PmxStructuralTransactionRequest):
            raise TypeError(
                "request must be a PmxStructuralTransactionRequest instance."
            )
        if not isinstance(overwrite, bool):
            raise TypeError("overwrite must be a boolean.")
        result = _write_structural_transaction_with_stage_callback(
            input_path,
            output_path,
            request,
            overwrite=overwrite,
            stage_callback=record_stage,
        )
        return PmxStructuralExecutionResult(result)
    except Exception as error:
        failure = _execution_service_error(
            error,
            failure_stage,
            source_bytes_read=source_bytes_read,
        )
    raise failure from None


__all__ = (
    "PmxStructuralTransactionOperation",
    "PmxStructuralTransactionRequest",
    "PmxStructuralTransactionPreviewResult",
    "preview_structural_transaction",
    "apply_structural_transaction",
)
