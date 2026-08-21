"""CP14 bounded semantic rigid-body insertion preview kernel.

Rigid-body insertion is additive only. Inserted rigid-body bone references target
the captured source bone domain or use the -1 sentinel. Existing impulse morph,
joint, and soft-body anchor references are shifted through the same certified
rigid-body insertion plan. No physics generation, index-width widening,
cross-target new-to-new references, or filesystem publication occurs here.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
from dataclasses import dataclass, field, replace
from typing import Final

from mmd_registry.pmx.document import PmxDocument, PmxRigidBody
from mmd_registry.pmx.physics_reference_remap import (
    remap_impulse_morph_rigid_body_references_for_insertion,
    remap_joint_rigid_body_references_for_insertion,
    remap_soft_body_rigid_body_references_for_insertion,
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
from mmd_registry.pmx.sections.header import MAX_PMX_NAME_BYTES
from mmd_registry.pmx.sections.rigid_bodies import MAX_PMX_RIGID_BODY_COUNT
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


PMX_RIGID_BODY_INSERTION_PREVIEW_SCHEMA_VERSION: Final[int] = 1

_SHAPE_NAMES: Final[tuple[str, ...]] = ("sphere", "box", "capsule")
_PHYSICS_MODE_NAMES: Final[tuple[str, ...]] = (
    "bone_follow",
    "physics",
    "physics_with_bone_alignment",
)


class PmxStructuralRigidBodyInsertionError(ValueError):
    """Raised when a CP14 rigid-body insertion cannot be safely certified."""


def _require_plain_int(value: object, field_name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be an integer.")
    return value


def _require_finite_float(value: object, field_name: str) -> None:
    if not isinstance(value, float):
        raise TypeError(f"{field_name} must be a float.")
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite.")


def _canonical_pmx_float32(value: float, field_name: str) -> float:
    _require_finite_float(value, field_name)
    try:
        encoded = struct.pack("<f", value)
    except (OverflowError, struct.error):
        raise PmxStructuralRigidBodyInsertionError(
            f"{field_name} must be representable as a finite PMX float32 value."
        ) from None
    canonical = struct.unpack("<f", encoded)[0]
    if not math.isfinite(canonical):
        raise PmxStructuralRigidBodyInsertionError(
            f"{field_name} must be representable as a finite PMX float32 value."
        )
    return canonical


def _canonical_pmx_float_tuple(
    value: tuple[float, ...],
    *,
    field_name: str,
) -> tuple[float, ...]:
    return tuple(
        _canonical_pmx_float32(item, f"{field_name} value") for item in value
    )


@dataclass(frozen=True, slots=True)
class PmxRigidBodyInsertionPayload:
    """Internal source-domain semantic rigid-body insertion payload."""

    local_name: str
    universal_name: str
    bone_index: int
    collision_group: int
    collision_mask: int
    shape: int
    size: tuple[float, float, float]
    body_position: tuple[float, float, float]
    rotation: tuple[float, float, float]
    mass: float
    linear_damping: float
    angular_damping: float
    restitution: float
    friction: float
    physics_mode: int
    position: PmxStructuralInsertPosition

    def __post_init__(self) -> None:
        for field_name in ("local_name", "universal_name"):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"{field_name} must be a string.")

        bone_index = _require_plain_int(self.bone_index, "bone_index")
        if bone_index < -1:
            raise ValueError("bone_index cannot be smaller than -1.")

        collision_group = _require_plain_int(self.collision_group, "collision_group")
        if not 0 <= collision_group <= 15:
            raise ValueError("collision_group must be a value from 0 through 15.")

        collision_mask = _require_plain_int(self.collision_mask, "collision_mask")
        if not 0 <= collision_mask <= 0xFFFF:
            raise ValueError(
                "collision_mask must fit in one unsigned 16-bit integer."
            )

        shape = _require_plain_int(self.shape, "shape")
        if shape not in (0, 1, 2):
            raise ValueError("shape must be a value from 0 through 2.")
        physics_mode = _require_plain_int(self.physics_mode, "physics_mode")
        if physics_mode not in (0, 1, 2):
            raise ValueError("physics_mode must be a value from 0 through 2.")

        for field_name, nonnegative in (
            ("size", True),
            ("body_position", False),
            ("rotation", False),
        ):
            value = getattr(self, field_name)
            if type(value) is not tuple or len(value) != 3:
                raise TypeError(f"{field_name} must be a 3-value tuple.")
            for item in value:
                _require_finite_float(item, f"{field_name} value")
                if nonnegative and item < 0.0:
                    raise ValueError(f"{field_name} values cannot be negative.")

        for field_name in (
            "mass",
            "linear_damping",
            "angular_damping",
            "restitution",
            "friction",
        ):
            value = getattr(self, field_name)
            _require_finite_float(value, field_name)
            if value < 0.0:
                raise ValueError(f"{field_name} cannot be negative.")

        if not isinstance(self.position, PmxStructuralInsertPosition):
            raise TypeError("position must be a PmxStructuralInsertPosition value.")

    def to_dict(self) -> dict[str, object]:
        return {
            "local_name": self.local_name,
            "universal_name": self.universal_name,
            "bone_index": self.bone_index,
            "collision_group": self.collision_group,
            "collision_mask": self.collision_mask,
            "shape": self.shape,
            "size": list(self.size),
            "body_position": list(self.body_position),
            "rotation": list(self.rotation),
            "mass": self.mass,
            "linear_damping": self.linear_damping,
            "angular_damping": self.angular_damping,
            "restitution": self.restitution,
            "friction": self.friction,
            "physics_mode": self.physics_mode,
            "position": self.position.to_dict(),
        }

    def to_rigid_body(self) -> PmxRigidBody:
        return PmxRigidBody(
            local_name=self.local_name,
            universal_name=self.universal_name,
            bone_index=self.bone_index,
            collision_group=self.collision_group,
            collision_mask=self.collision_mask,
            shape=self.shape,
            shape_name=_SHAPE_NAMES[self.shape],
            size=_canonical_pmx_float_tuple(self.size, field_name="size"),
            position=_canonical_pmx_float_tuple(
                self.body_position,
                field_name="body_position",
            ),
            rotation=_canonical_pmx_float_tuple(
                self.rotation,
                field_name="rotation",
            ),
            mass=_canonical_pmx_float32(self.mass, "mass"),
            linear_damping=_canonical_pmx_float32(
                self.linear_damping,
                "linear_damping",
            ),
            angular_damping=_canonical_pmx_float32(
                self.angular_damping,
                "angular_damping",
            ),
            restitution=_canonical_pmx_float32(self.restitution, "restitution"),
            friction=_canonical_pmx_float32(self.friction, "friction"),
            physics_mode=self.physics_mode,
            physics_mode_name=_PHYSICS_MODE_NAMES[self.physics_mode],
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


def _validate_text_for_source(
    text: str,
    *,
    encoding: str,
    label: str,
) -> None:
    try:
        encoded = text.encode(encoding, errors="strict")
    except UnicodeEncodeError:
        raise PmxStructuralRigidBodyInsertionError(
            f"{label} cannot be encoded using the source PMX text encoding."
        ) from None
    if len(encoded) > MAX_PMX_NAME_BYTES:
        raise PmxStructuralRigidBodyInsertionError(
            f"encoded {label} exceeds the PMX rigid-body parser safety limit."
        )


def _validate_payload_for_source(
    document: PmxDocument,
    insertion: PmxRigidBodyInsertionPayload,
) -> None:
    _validate_text_for_source(
        insertion.local_name,
        encoding=document.header.encoding,
        label="local_name",
    )
    _validate_text_for_source(
        insertion.universal_name,
        encoding=document.header.encoding,
        label="universal_name",
    )

    if insertion.bone_index != -1 and not (
        0 <= insertion.bone_index < len(document.bones)
    ):
        raise PmxStructuralRigidBodyInsertionError(
            "bone_index must reference an existing source bone or use -1."
        )

    canonical_size = _canonical_pmx_float_tuple(insertion.size, field_name="size")
    if any(value < 0.0 for value in canonical_size):
        raise PmxStructuralRigidBodyInsertionError(
            "size values cannot become negative after PMX float32 canonicalization."
        )
    _canonical_pmx_float_tuple(
        insertion.body_position,
        field_name="body_position",
    )
    _canonical_pmx_float_tuple(insertion.rotation, field_name="rotation")
    for field_name in (
        "mass",
        "linear_damping",
        "angular_damping",
        "restitution",
        "friction",
    ):
        value = _canonical_pmx_float32(
            getattr(insertion, field_name),
            field_name,
        )
        if value < 0.0:
            raise PmxStructuralRigidBodyInsertionError(
                f"{field_name} cannot become negative after PMX float32 "
                "canonicalization."
            )


def _build_rigid_body_shift_plan(
    document: PmxDocument,
    insertions: tuple[PmxRigidBodyInsertionPayload, ...],
) -> PmxCollectionReferenceShiftPlan:
    result_count = len(document.rigid_bodies) + len(insertions)
    if result_count > MAX_PMX_RIGID_BODY_COUNT:
        raise PmxStructuralRigidBodyInsertionError(
            "resulting rigid-body count exceeds the PMX rigid-body parser safety limit."
        )
    for insertion in insertions:
        _validate_payload_for_source(document, insertion)

    intent = PmxCollectionInsertionIntent(
        target_kind=PmxReferenceTargetKind.RIGID_BODY,
        positions=tuple(insertion.position for insertion in insertions),
    )
    shift = plan_collection_reference_shift(
        intent,
        current_count=len(document.rigid_bodies),
        index_width=document.header.index_sizes.rigid_body,
    )
    if shift.result_count != result_count:
        raise AssertionError(
            "rigid-body reference-shift count disagrees with reader-safe count."
        )
    return shift


def _materialize_rigid_bodies(
    source: tuple[PmxRigidBody, ...],
    insertions: tuple[PmxRigidBodyInsertionPayload, ...],
    shift: PmxCollectionReferenceShiftPlan,
) -> tuple[PmxRigidBody, ...]:
    if shift.current_count != len(source):
        raise ValueError(
            "rigid-body shift current_count does not match source rigid-body count."
        )
    if shift.insert_count != len(insertions):
        raise ValueError(
            "rigid-body shift insert_count does not match insertion payload count."
        )

    slots: list[PmxRigidBody | None] = [None] * shift.result_count
    for old_index, new_index in enumerate(shift.remap.targets):
        if new_index is None:
            raise AssertionError(
                "rigid-body insertion shift cannot remove source rigid bodies."
            )
        if slots[new_index] is not None:
            raise AssertionError(
                "rigid-body insertion shift assigned a duplicate old slot."
            )
        slots[new_index] = source[old_index]

    for request_index, insertion in enumerate(insertions):
        new_index = shift.new_index_for_insertion(request_index)
        if slots[new_index] is not None:
            raise AssertionError(
                "rigid-body insertion payload overlaps an old rigid-body slot."
            )
        slots[new_index] = insertion.to_rigid_body()

    if any(value is None for value in slots):
        raise AssertionError(
            "rigid-body insertion materialization left an unfilled slot."
        )
    return tuple(value for value in slots if value is not None)


def _calculate_intent_sha256(
    insertions: tuple[PmxRigidBodyInsertionPayload, ...],
    shift: PmxCollectionReferenceShiftPlan,
) -> str:
    canonical = {
        "rigid_body_insertions": [item.to_dict() for item in insertions],
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


def _payload_sha256(insertion: PmxRigidBodyInsertionPayload) -> str:
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
                kind=PmxReferenceTargetKind.RIGID_BODY,
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
class PmxRigidBodyInsertionPreview:
    """Deterministic certified preview for semantic rigid-body insertions."""

    source_document: PmxDocument
    insertions: tuple[PmxRigidBodyInsertionPayload, ...]
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
            raise ValueError(
                "rigid-body insertion preview requires at least one insertion."
            )
        if not all(
            isinstance(insertion, PmxRigidBodyInsertionPayload)
            for insertion in self.insertions
        ):
            raise TypeError(
                "insertions must contain only PmxRigidBodyInsertionPayload values."
            )

        shift = _build_rigid_body_shift_plan(self.source_document, self.insertions)
        rigid_bodies = _materialize_rigid_bodies(
            self.source_document.rigid_bodies,
            self.insertions,
            shift,
        )
        morphs = remap_impulse_morph_rigid_body_references_for_insertion(
            self.source_document.morphs,
            shift,
            pmx_version=self.source_document.header.version,
        )
        joints = remap_joint_rigid_body_references_for_insertion(
            self.source_document.joints,
            shift,
            pmx_version=self.source_document.header.version,
        )
        soft_bodies = remap_soft_body_rigid_body_references_for_insertion(
            self.source_document.soft_bodies,
            shift,
            pmx_version=self.source_document.header.version,
        )
        intended_document = replace(
            self.source_document,
            rigid_bodies=rigid_bodies,
            morphs=morphs,
            joints=joints,
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
            "preview_schema_version": PMX_RIGID_BODY_INSERTION_PREVIEW_SCHEMA_VERSION,
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
                "changed_kinds": ["rigid_body"],
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
                    "changed_kinds": ["rigid_body"],
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
                "rigid_body_insertion": {
                    **self.shift.to_dict(),
                    "payloads": [
                        {
                            "request_index": request_index,
                            "new_index": self.shift.new_index_for_insertion(
                                request_index
                            ),
                            "payload_sha256": _payload_sha256(insertion),
                            "shape": _SHAPE_NAMES[insertion.shape],
                            "physics_mode": _PHYSICS_MODE_NAMES[
                                insertion.physics_mode
                            ],
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


def preview_pmx_rigid_body_insertions(
    document: PmxDocument,
    insertions: tuple[PmxRigidBodyInsertionPayload, ...],
) -> PmxRigidBodyInsertionPreview:
    """Return one certified in-memory CP14 rigid-body insertion preview."""

    return PmxRigidBodyInsertionPreview(
        source_document=document,
        insertions=insertions,
    )


__all__ = (
    "PmxStructuralRigidBodyInsertionError",
    "PmxRigidBodyInsertionPayload",
    "PmxRigidBodyInsertionPreview",
    "preview_pmx_rigid_body_insertions",
)
