"""Certified in-memory PMX vertex insertion preview for v0.9.2 CP15.

This internal target-specific layer accepts only typed semantic vertex payloads,
validates source-domain bone references, version constraints, float32 payloads,
reader limits, and unsigned vertex-index capacity before planning. It reuses the
CP06 insertion reference-shift evidence, delegates every existing incoming
vertex-reference owner to its established remap module, and materializes new
``PmxVertex`` records without serialization or filesystem I/O.

CP15 is preview-only. New-to-new bone references, mixed target insertion,
new surface topology, automatic index-width resizing, raw section payloads, and
public writer authority remain out of scope.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field, replace
from typing import Final, TypeAlias

from mmd_registry.pmx.document import (
    PmxBdef1,
    PmxBdef2,
    PmxBdef4,
    PmxDocument,
    PmxQdef,
    PmxSdef,
    PmxVertex,
)
from mmd_registry.pmx.editing.numeric import canonicalize_pmx_float32
from mmd_registry.pmx.geometry_material_remap import (
    remap_surface_vertex_references_for_insertion,
)
from mmd_registry.pmx.morph_display_remap import (
    remap_vertex_morph_references_for_insertion,
)
from mmd_registry.pmx.physics_reference_remap import (
    remap_soft_body_vertex_references_for_insertion,
)
from mmd_registry.pmx.reference_diagnostics import (
    PmxReferenceDiagnostic,
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
from mmd_registry.pmx.reference_queries import _analyze_reference_impacts
from mmd_registry.pmx.sections.geometry import MAX_PMX_VERTEX_COUNT
from mmd_registry.pmx.structural_insert_intent import (
    PmxCollectionInsertionIntent,
    PmxStructuralInsertPosition,
)
from mmd_registry.pmx.structural_invariants import PmxStructuralInvariantCertificate
from mmd_registry.pmx.structural_preview import PmxStructuralReferenceImpactAudit
from mmd_registry.pmx.structural_reference_shift import (
    PmxCollectionReferenceShiftPlan,
    plan_collection_reference_shift,
)


PMX_VERTEX_INSERTION_PREVIEW_SCHEMA_VERSION: Final[int] = 1


class PmxStructuralVertexInsertionError(ValueError):
    """Raised when a vertex insertion cannot be certified under the CP15 contract."""


def _is_plain_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _require_plain_int(value: object, field_name: str) -> int:
    if not _is_plain_int(value):
        raise TypeError(f"{field_name} must be an integer.")
    return value


def _require_source_bone_index(value: object, field_name: str) -> int:
    index = _require_plain_int(value, field_name)
    if index < -1:
        raise ValueError(f"{field_name} cannot be smaller than -1.")
    return index


def _require_finite_float(value: object, field_name: str) -> None:
    if not isinstance(value, float):
        raise TypeError(f"{field_name} must be a float.")
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite.")


def _require_float_tuple(
    value: object,
    *,
    field_name: str,
    length: int,
) -> None:
    if type(value) is not tuple:
        raise TypeError(f"{field_name} must be a tuple.")
    if len(value) != length:
        raise ValueError(f"{field_name} must contain exactly {length} values.")
    for item in value:
        _require_finite_float(item, f"{field_name} value")


def _require_bone_index_tuple(
    value: object,
    *,
    field_name: str,
    length: int,
) -> None:
    if type(value) is not tuple:
        raise TypeError(f"{field_name} must be a tuple.")
    if len(value) != length:
        raise ValueError(f"{field_name} must contain exactly {length} values.")
    for item in value:
        _require_source_bone_index(item, f"{field_name} value")


def _canonical_pmx_float32(value: float, field_name: str) -> float:
    try:
        return canonicalize_pmx_float32(value)
    except TypeError:
        raise
    except ValueError:
        raise PmxStructuralVertexInsertionError(
            f"{field_name} must be representable as a finite PMX float32 value."
        ) from None


def _canonical_pmx_float_tuple(
    value: tuple[float, ...],
    *,
    field_name: str,
) -> tuple[float, ...]:
    return tuple(
        _canonical_pmx_float32(item, f"{field_name} value") for item in value
    )


@dataclass(frozen=True, slots=True)
class PmxVertexBdef1InsertionPayload:
    bone_index: int

    def __post_init__(self) -> None:
        _require_source_bone_index(self.bone_index, "bone_index")

    def to_dict(self) -> dict[str, object]:
        return {"type": "bdef1", "bone_index": self.bone_index}

    def to_deform(self) -> PmxBdef1:
        return PmxBdef1(bone_index=self.bone_index)


@dataclass(frozen=True, slots=True)
class PmxVertexBdef2InsertionPayload:
    bone_indices: tuple[int, int]
    bone_1_weight: float

    def __post_init__(self) -> None:
        _require_bone_index_tuple(
            self.bone_indices,
            field_name="bone_indices",
            length=2,
        )
        _require_finite_float(self.bone_1_weight, "bone_1_weight")

    def to_dict(self) -> dict[str, object]:
        return {
            "type": "bdef2",
            "bone_indices": list(self.bone_indices),
            "bone_1_weight": self.bone_1_weight,
        }

    def to_deform(self) -> PmxBdef2:
        return PmxBdef2(
            bone_indices=self.bone_indices,
            bone_1_weight=_canonical_pmx_float32(
                self.bone_1_weight,
                "deform.bone_1_weight",
            ),
        )


@dataclass(frozen=True, slots=True)
class PmxVertexBdef4InsertionPayload:
    bone_indices: tuple[int, int, int, int]
    weights: tuple[float, float, float, float]

    def __post_init__(self) -> None:
        _require_bone_index_tuple(
            self.bone_indices,
            field_name="bone_indices",
            length=4,
        )
        _require_float_tuple(self.weights, field_name="weights", length=4)

    def to_dict(self) -> dict[str, object]:
        return {
            "type": "bdef4",
            "bone_indices": list(self.bone_indices),
            "weights": list(self.weights),
        }

    def to_deform(self) -> PmxBdef4:
        return PmxBdef4(
            bone_indices=self.bone_indices,
            weights=_canonical_pmx_float_tuple(
                self.weights,
                field_name="deform.weights",
            ),
        )


@dataclass(frozen=True, slots=True)
class PmxVertexSdefInsertionPayload:
    bone_indices: tuple[int, int]
    bone_1_weight: float
    c: tuple[float, float, float]
    r0: tuple[float, float, float]
    r1: tuple[float, float, float]

    def __post_init__(self) -> None:
        _require_bone_index_tuple(
            self.bone_indices,
            field_name="bone_indices",
            length=2,
        )
        _require_finite_float(self.bone_1_weight, "bone_1_weight")
        for field_name in ("c", "r0", "r1"):
            _require_float_tuple(
                getattr(self, field_name),
                field_name=field_name,
                length=3,
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "type": "sdef",
            "bone_indices": list(self.bone_indices),
            "bone_1_weight": self.bone_1_weight,
            "c": list(self.c),
            "r0": list(self.r0),
            "r1": list(self.r1),
        }

    def to_deform(self) -> PmxSdef:
        return PmxSdef(
            bone_indices=self.bone_indices,
            bone_1_weight=_canonical_pmx_float32(
                self.bone_1_weight,
                "deform.bone_1_weight",
            ),
            c=_canonical_pmx_float_tuple(self.c, field_name="deform.c"),
            r0=_canonical_pmx_float_tuple(self.r0, field_name="deform.r0"),
            r1=_canonical_pmx_float_tuple(self.r1, field_name="deform.r1"),
        )


@dataclass(frozen=True, slots=True)
class PmxVertexQdefInsertionPayload:
    bone_indices: tuple[int, int, int, int]
    weights: tuple[float, float, float, float]

    def __post_init__(self) -> None:
        _require_bone_index_tuple(
            self.bone_indices,
            field_name="bone_indices",
            length=4,
        )
        _require_float_tuple(self.weights, field_name="weights", length=4)

    def to_dict(self) -> dict[str, object]:
        return {
            "type": "qdef",
            "bone_indices": list(self.bone_indices),
            "weights": list(self.weights),
        }

    def to_deform(self) -> PmxQdef:
        return PmxQdef(
            bone_indices=self.bone_indices,
            weights=_canonical_pmx_float_tuple(
                self.weights,
                field_name="deform.weights",
            ),
        )


PmxVertexDeformInsertionPayload: TypeAlias = (
    PmxVertexBdef1InsertionPayload
    | PmxVertexBdef2InsertionPayload
    | PmxVertexBdef4InsertionPayload
    | PmxVertexSdefInsertionPayload
    | PmxVertexQdefInsertionPayload
)


@dataclass(frozen=True, slots=True)
class PmxVertexInsertionPayload:
    """Internal semantic vertex payload paired with one CP05 insertion position."""

    vertex_position: tuple[float, float, float]
    normal: tuple[float, float, float]
    uv: tuple[float, float]
    additional_uvs: tuple[tuple[float, float, float, float], ...]
    deform: PmxVertexDeformInsertionPayload
    edge_scale: float
    position: PmxStructuralInsertPosition

    def __post_init__(self) -> None:
        _require_float_tuple(
            self.vertex_position,
            field_name="vertex_position",
            length=3,
        )
        _require_float_tuple(self.normal, field_name="normal", length=3)
        _require_float_tuple(self.uv, field_name="uv", length=2)
        if type(self.additional_uvs) is not tuple:
            raise TypeError("additional_uvs must be a tuple.")
        if len(self.additional_uvs) > 4:
            raise ValueError("additional_uvs cannot contain more than 4 vectors.")
        for index, additional_uv in enumerate(self.additional_uvs):
            _require_float_tuple(
                additional_uv,
                field_name=f"additional_uvs[{index}]",
                length=4,
            )
        if not isinstance(
            self.deform,
            (
                PmxVertexBdef1InsertionPayload,
                PmxVertexBdef2InsertionPayload,
                PmxVertexBdef4InsertionPayload,
                PmxVertexSdefInsertionPayload,
                PmxVertexQdefInsertionPayload,
            ),
        ):
            raise TypeError("deform must be a supported vertex insertion payload.")
        _require_finite_float(self.edge_scale, "edge_scale")
        if not isinstance(self.position, PmxStructuralInsertPosition):
            raise TypeError("position must be a PmxStructuralInsertPosition value.")

    def to_dict(self) -> dict[str, object]:
        return {
            "vertex_position": list(self.vertex_position),
            "normal": list(self.normal),
            "uv": list(self.uv),
            "additional_uvs": [list(value) for value in self.additional_uvs],
            "deform": self.deform.to_dict(),
            "edge_scale": self.edge_scale,
            "position": self.position.to_dict(),
        }

    def to_vertex(self) -> PmxVertex:
        return PmxVertex(
            position=_canonical_pmx_float_tuple(
                self.vertex_position,
                field_name="vertex_position",
            ),
            normal=_canonical_pmx_float_tuple(self.normal, field_name="normal"),
            uv=_canonical_pmx_float_tuple(self.uv, field_name="uv"),
            additional_uvs=tuple(
                _canonical_pmx_float_tuple(
                    value,
                    field_name=f"additional_uvs[{index}]",
                )
                for index, value in enumerate(self.additional_uvs)
            ),
            deform=self.deform.to_deform(),
            edge_scale=_canonical_pmx_float32(self.edge_scale, "edge_scale"),
        )


def _target_counts_to_dict(graph: PmxReferenceGraph) -> dict[str, int]:
    counts = graph.target_counts
    return {
        "vertex": counts.vertex,
        "texture": counts.texture,
        "material": counts.material,
        "bone": counts.bone,
        "morph": counts.morph,
        "rigid_body": counts.rigid_body,
    }


def _iter_deform_bone_indices(
    deform: PmxVertexDeformInsertionPayload,
) -> tuple[int, ...]:
    if isinstance(deform, PmxVertexBdef1InsertionPayload):
        return (deform.bone_index,)
    if isinstance(
        deform,
        (
            PmxVertexBdef2InsertionPayload,
            PmxVertexBdef4InsertionPayload,
            PmxVertexSdefInsertionPayload,
            PmxVertexQdefInsertionPayload,
        ),
    ):
        return tuple(deform.bone_indices)
    raise TypeError("unsupported vertex deform insertion payload.")


def _validate_source_bone_references(
    deform: PmxVertexDeformInsertionPayload,
    *,
    bone_count: int,
) -> None:
    for index, bone_index in enumerate(_iter_deform_bone_indices(deform)):
        if bone_index == -1:
            continue
        if bone_index < -1 or bone_index >= bone_count:
            raise PmxStructuralVertexInsertionError(
                f"deform bone reference {index} must reference an existing "
                "source bone or use -1."
            )


def _validate_float32_payload(insertion: PmxVertexInsertionPayload) -> None:
    _canonical_pmx_float_tuple(
        insertion.vertex_position,
        field_name="vertex_position",
    )
    _canonical_pmx_float_tuple(insertion.normal, field_name="normal")
    _canonical_pmx_float_tuple(insertion.uv, field_name="uv")
    for index, additional_uv in enumerate(insertion.additional_uvs):
        _canonical_pmx_float_tuple(
            additional_uv,
            field_name=f"additional_uvs[{index}]",
        )
    _canonical_pmx_float32(insertion.edge_scale, "edge_scale")

    deform = insertion.deform
    if isinstance(deform, PmxVertexBdef2InsertionPayload):
        _canonical_pmx_float32(deform.bone_1_weight, "deform.bone_1_weight")
    elif isinstance(deform, (PmxVertexBdef4InsertionPayload, PmxVertexQdefInsertionPayload)):
        _canonical_pmx_float_tuple(deform.weights, field_name="deform.weights")
    elif isinstance(deform, PmxVertexSdefInsertionPayload):
        _canonical_pmx_float32(deform.bone_1_weight, "deform.bone_1_weight")
        _canonical_pmx_float_tuple(deform.c, field_name="deform.c")
        _canonical_pmx_float_tuple(deform.r0, field_name="deform.r0")
        _canonical_pmx_float_tuple(deform.r1, field_name="deform.r1")
    elif not isinstance(deform, PmxVertexBdef1InsertionPayload):
        raise TypeError("unsupported vertex deform insertion payload.")


def _validate_payload_for_source(
    document: PmxDocument,
    insertion: PmxVertexInsertionPayload,
) -> None:
    if len(insertion.additional_uvs) != document.header.additional_uv_count:
        raise PmxStructuralVertexInsertionError(
            "additional_uvs must exactly match the source PMX header "
            "additional_uv_count."
        )
    if isinstance(insertion.deform, PmxVertexQdefInsertionPayload):
        if document.header.version < 2.1:
            raise PmxStructuralVertexInsertionError("QDEF insertion requires PMX 2.1.")
    _validate_source_bone_references(
        insertion.deform,
        bone_count=len(document.bones),
    )
    _validate_float32_payload(insertion)


def _require_reader_safe_count(
    document: PmxDocument,
    insertions: tuple[PmxVertexInsertionPayload, ...],
) -> int:
    result_count = len(document.vertices) + len(insertions)
    if result_count > MAX_PMX_VERTEX_COUNT:
        raise PmxStructuralVertexInsertionError(
            "resulting vertex count exceeds the PMX vertex parser safety limit."
        )
    return result_count


def _build_vertex_shift_plan(
    document: PmxDocument,
    insertions: tuple[PmxVertexInsertionPayload, ...],
) -> PmxCollectionReferenceShiftPlan:
    expected_result_count = _require_reader_safe_count(document, insertions)
    for insertion in insertions:
        _validate_payload_for_source(document, insertion)

    intent = PmxCollectionInsertionIntent(
        target_kind=PmxReferenceTargetKind.VERTEX,
        positions=tuple(insertion.position for insertion in insertions),
    )
    shift = plan_collection_reference_shift(
        intent,
        current_count=len(document.vertices),
        index_width=document.header.index_sizes.vertex,
    )
    if shift.result_count != expected_result_count:
        raise AssertionError(
            "vertex reference-shift result count disagrees with the reader-safe "
            "result count."
        )
    return shift


def _materialize_vertices(
    source_vertices: tuple[PmxVertex, ...],
    insertions: tuple[PmxVertexInsertionPayload, ...],
    shift: PmxCollectionReferenceShiftPlan,
) -> tuple[PmxVertex, ...]:
    if shift.current_count != len(source_vertices):
        raise ValueError("vertex shift current_count does not match source vertex count.")
    if shift.insert_count != len(insertions):
        raise ValueError(
            "vertex shift insert_count does not match vertex insertion payload count."
        )

    slots: list[PmxVertex | None] = [None] * shift.result_count
    for old_index, new_index in enumerate(shift.remap.targets):
        if new_index is None:
            raise AssertionError("vertex insertion shift cannot remove source vertices.")
        if slots[new_index] is not None:
            raise AssertionError("vertex insertion shift assigned a duplicate old slot.")
        slots[new_index] = source_vertices[old_index]

    for request_index, insertion in enumerate(insertions):
        new_index = shift.new_index_for_insertion(request_index)
        if slots[new_index] is not None:
            raise AssertionError("vertex insertion payload overlaps an old vertex slot.")
        slots[new_index] = insertion.to_vertex()

    if any(value is None for value in slots):
        raise AssertionError("vertex insertion materialization left an unfilled slot.")
    return tuple(value for value in slots if value is not None)


def _calculate_intent_sha256(
    insertions: tuple[PmxVertexInsertionPayload, ...],
    shift: PmxCollectionReferenceShiftPlan,
) -> str:
    canonical = {
        "vertex_insertions": [insertion.to_dict() for insertion in insertions],
        "reference_shift": shift.to_dict(),
    }
    payload = json.dumps(
        canonical,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _payload_sha256(insertion: PmxVertexInsertionPayload) -> str:
    payload = json.dumps(
        insertion.to_dict(),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _reference_impact_audits(
    source_graph: PmxReferenceGraph,
    shift: PmxCollectionReferenceShiftPlan,
) -> tuple[PmxStructuralReferenceImpactAudit, ...]:
    specs = tuple(
        (
            PmxReferenceNode(
                kind=PmxReferenceTargetKind.VERTEX,
                index=old_index,
            ),
            new_index,
        )
        for old_index, new_index in enumerate(shift.remap.targets)
        if new_index is not None and new_index != old_index
    )
    impacts = _analyze_reference_impacts(
        source_graph,
        tuple(node for node, _new_index in specs),
    )
    return tuple(
        PmxStructuralReferenceImpactAudit(
            node=node,
            new_index=new_index,
            impact=impact,
        )
        for (node, new_index), impact in zip(specs, impacts, strict=True)
    )


@dataclass(frozen=True, slots=True)
class PmxVertexInsertionPreview:
    """Deterministic certified preview for one or more semantic vertex insertions."""

    source_document: PmxDocument
    insertions: tuple[PmxVertexInsertionPayload, ...]
    shift: PmxCollectionReferenceShiftPlan = field(init=False)
    certificate: PmxStructuralInvariantCertificate = field(init=False)
    reference_impacts: tuple[PmxStructuralReferenceImpactAudit, ...] = field(init=False)
    source_reference_diagnostics: tuple[PmxReferenceDiagnostic, ...] = field(init=False)
    intent_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.source_document, PmxDocument):
            raise TypeError("source_document must be a PmxDocument instance.")
        if type(self.insertions) is not tuple:
            raise TypeError("insertions must be a tuple.")
        if not self.insertions:
            raise ValueError("vertex insertion preview requires at least one insertion.")
        if not all(
            isinstance(insertion, PmxVertexInsertionPayload)
            for insertion in self.insertions
        ):
            raise TypeError(
                "insertions must contain only PmxVertexInsertionPayload values."
            )

        shift = _build_vertex_shift_plan(self.source_document, self.insertions)
        vertices = _materialize_vertices(
            self.source_document.vertices,
            self.insertions,
            shift,
        )
        surface_indices = remap_surface_vertex_references_for_insertion(
            self.source_document.surface_indices,
            shift,
        )
        morphs = remap_vertex_morph_references_for_insertion(
            self.source_document.morphs,
            shift,
            pmx_version=self.source_document.header.version,
            additional_uv_count=self.source_document.header.additional_uv_count,
        )
        soft_bodies = remap_soft_body_vertex_references_for_insertion(
            self.source_document.soft_bodies,
            shift,
            pmx_version=self.source_document.header.version,
        )

        geometry = replace(
            self.source_document.geometry,
            vertices=vertices,
            surface_indices=surface_indices,
        )
        intended_document = replace(
            self.source_document,
            geometry=geometry,
            morphs=morphs,
            soft_bodies=soft_bodies,
        )
        certificate = PmxStructuralInvariantCertificate(document=intended_document)

        source_graph = extract_pmx_reference_graph(self.source_document)
        source_diagnostics = diagnose_reference_graph(source_graph)
        reference_impacts = _reference_impact_audits(source_graph, shift)

        object.__setattr__(self, "shift", shift)
        object.__setattr__(self, "certificate", certificate)
        object.__setattr__(self, "reference_impacts", reference_impacts)
        object.__setattr__(
            self,
            "source_reference_diagnostics",
            source_diagnostics,
        )
        object.__setattr__(
            self,
            "intent_sha256",
            _calculate_intent_sha256(self.insertions, shift),
        )

    @property
    def status(self) -> str:
        return "changes_pending"

    def to_dict(self) -> dict[str, object]:
        source_graph = extract_pmx_reference_graph(self.source_document)
        direct_reference_edge_count = sum(
            len(item.impact.inbound_edges) + len(item.impact.outbound_edges)
            for item in self.reference_impacts
        )
        return {
            "preview_schema_version": PMX_VERTEX_INSERTION_PREVIEW_SCHEMA_VERSION,
            "status": self.status,
            "dry_run": True,
            "source": {
                "target_counts": _target_counts_to_dict(source_graph),
                "reference_edge_count": len(source_graph.edges),
                "reference_diagnostic_count": len(
                    self.source_reference_diagnostics
                ),
            },
            "intent": {
                "sha256": self.intent_sha256,
                "changed_kinds": ["vertex"],
                "collection_count": 1,
                "insert_count": self.shift.insert_count,
            },
            "output": {
                "written": False,
                "target_counts": _target_counts_to_dict(
                    self.certificate.reference_graph
                ),
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
                    "changed_kinds": ["vertex"],
                    "changed_collection_count": 1,
                    "changed_node_count": len(self.reference_impacts),
                    "removed_record_count": 0,
                    "reindexed_record_count": len(self.reference_impacts),
                    "inserted_record_count": self.shift.insert_count,
                    "direct_reference_edge_count": direct_reference_edge_count,
                    "direct_reference_impact_complete": all(
                        item.impact.is_complete for item in self.reference_impacts
                    ),
                    "source_reference_diagnostic_count": len(
                        self.source_reference_diagnostics
                    ),
                },
                "vertex_insertion": {
                    **self.shift.to_dict(),
                    "payloads": [
                        {
                            "request_index": request_index,
                            "new_index": self.shift.new_index_for_insertion(
                                request_index
                            ),
                            "payload_sha256": _payload_sha256(insertion),
                            "deform_type": insertion.deform.to_dict()["type"],
                            "additional_uv_count": len(insertion.additional_uvs),
                        }
                        for request_index, insertion in enumerate(self.insertions)
                    ],
                },
                "reference_impacts": [
                    item.to_dict() for item in self.reference_impacts
                ],
                "source_reference_diagnostics": [
                    item.to_dict() for item in self.source_reference_diagnostics
                ],
            },
        }


def preview_pmx_vertex_insertions(
    document: PmxDocument,
    insertions: tuple[PmxVertexInsertionPayload, ...],
) -> PmxVertexInsertionPreview:
    """Return one certified in-memory vertex insertion preview without I/O."""

    return PmxVertexInsertionPreview(
        source_document=document,
        insertions=insertions,
    )


__all__ = (
    "PmxStructuralVertexInsertionError",
    "PmxVertexBdef1InsertionPayload",
    "PmxVertexBdef2InsertionPayload",
    "PmxVertexBdef4InsertionPayload",
    "PmxVertexSdefInsertionPayload",
    "PmxVertexQdefInsertionPayload",
    "PmxVertexInsertionPayload",
    "PmxVertexInsertionPreview",
    "preview_pmx_vertex_insertions",
)
