"""Preview-only zero-surface material insertion for v0.9.2.

This internal target-specific layer materializes typed material insertions from
source-domain positions, reuses the CP06 reference-shift planner, rewrites the
existing morph->material and soft-body->material relationships through their
authoritative CP13/CP14 owners, and returns a completely certified in-memory
preview.

Inserted materials deliberately own zero surface indices in CP09. Coordinated
surface/geometry insertion remains out of scope. This module does not construct
or weaken ``PmxCollectionTransform``, serialize bytes, write files, resize PMX
index widths, expose a public mutation authority, or enable material insertion
execution.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
from dataclasses import dataclass, field, replace
from typing import Final, Literal

from mmd_registry.pmx.document import PmxDocument, PmxMaterial
from mmd_registry.pmx.morph_display_remap import (
    remap_material_morph_references_for_insertion,
)
from mmd_registry.pmx.physics_reference_remap import (
    remap_soft_body_material_references_for_insertion,
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
from mmd_registry.pmx.sections.materials import (
    MAX_PMX_MATERIAL_COUNT,
    MAX_PMX_MATERIAL_MEMO_BYTES,
)
from mmd_registry.pmx.structural_insert_intent import (
    PmxCollectionInsertionIntent,
    PmxStructuralInsertPosition,
)
from mmd_registry.pmx.structural_invariants import (
    PmxStructuralInvariantCertificate,
)
from mmd_registry.pmx.structural_preview import PmxStructuralReferenceImpactAudit
from mmd_registry.pmx.structural_reference_shift import (
    PmxCollectionReferenceShiftPlan,
    plan_collection_reference_shift,
)


PMX_MATERIAL_INSERTION_PREVIEW_SCHEMA_VERSION: Final[int] = 1


class PmxStructuralMaterialInsertionError(ValueError):
    """Raised when one material insertion preview cannot be safely materialized."""


def _is_plain_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


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


def _canonical_pmx_float32(value: float, field_name: str) -> float:
    """Return the exact finite binary32 value PMX will serialize and reparse."""

    _require_finite_float(value, field_name)
    try:
        encoded = struct.pack("<f", value)
    except (OverflowError, struct.error):
        raise PmxStructuralMaterialInsertionError(
            f"{field_name} must be representable as a finite PMX float32 value."
        ) from None
    canonical = struct.unpack("<f", encoded)[0]
    if not math.isfinite(canonical):
        raise PmxStructuralMaterialInsertionError(
            f"{field_name} must be representable as a finite PMX float32 value."
        )
    return canonical


def _canonical_pmx_float_tuple(
    values: tuple[float, ...],
    *,
    field_name: str,
) -> tuple[float, ...]:
    return tuple(
        _canonical_pmx_float32(value, f"{field_name} value") for value in values
    )


@dataclass(frozen=True, slots=True)
class PmxMaterialInsertionPayload:
    """One internal zero-surface material paired with a source-domain position."""

    local_name: str
    universal_name: str
    memo: str
    texture_index: int
    sphere_texture_index: int
    sphere_mode: int
    toon_reference_mode: Literal["texture", "shared"]
    toon_reference_index: int
    diffuse: tuple[float, float, float, float]
    specular: tuple[float, float, float]
    specular_strength: float
    ambient: tuple[float, float, float]
    drawing_flags: int
    edge_color: tuple[float, float, float, float]
    edge_scale: float
    position: PmxStructuralInsertPosition

    def __post_init__(self) -> None:
        for field_name in ("local_name", "universal_name", "memo"):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"{field_name} must be a string.")

        for field_name in (
            "texture_index",
            "sphere_texture_index",
            "toon_reference_index",
        ):
            value = getattr(self, field_name)
            if not _is_plain_int(value):
                raise TypeError(f"{field_name} must be an integer.")
            if value < -1:
                raise ValueError(f"{field_name} cannot be smaller than -1.")

        if not _is_plain_int(self.sphere_mode):
            raise TypeError("sphere_mode must be an integer.")
        if self.sphere_mode not in (0, 1, 2, 3):
            raise ValueError("sphere_mode must be a value from 0 through 3.")
        if self.toon_reference_mode not in ("texture", "shared"):
            raise ValueError(
                "toon_reference_mode must be either 'texture' or 'shared'."
            )
        if (
            self.toon_reference_mode == "shared"
            and not 0 <= self.toon_reference_index <= 9
        ):
            raise ValueError(
                "shared toon_reference_index must be a value from 0 through 9."
            )

        _require_float_tuple(self.diffuse, field_name="diffuse", length=4)
        _require_float_tuple(self.specular, field_name="specular", length=3)
        _require_finite_float(self.specular_strength, "specular_strength")
        _require_float_tuple(self.ambient, field_name="ambient", length=3)
        _require_float_tuple(self.edge_color, field_name="edge_color", length=4)
        _require_finite_float(self.edge_scale, "edge_scale")

        if not _is_plain_int(self.drawing_flags):
            raise TypeError("drawing_flags must be an integer.")
        if not 0 <= self.drawing_flags <= 0xFF:
            raise ValueError("drawing_flags must fit in one unsigned byte.")
        if not isinstance(self.position, PmxStructuralInsertPosition):
            raise TypeError("position must be a PmxStructuralInsertPosition value.")

    def to_material(self) -> PmxMaterial:
        """Construct the exact PMX-representable immutable zero-surface material."""

        return PmxMaterial(
            local_name=self.local_name,
            universal_name=self.universal_name,
            texture_index=self.texture_index,
            sphere_texture_index=self.sphere_texture_index,
            sphere_mode=self.sphere_mode,
            toon_reference_mode=self.toon_reference_mode,
            toon_reference_index=self.toon_reference_index,
            memo=self.memo,
            surface_index_count=0,
            diffuse=_canonical_pmx_float_tuple(
                self.diffuse,
                field_name="material diffuse",
            ),
            specular=_canonical_pmx_float_tuple(
                self.specular,
                field_name="material specular",
            ),
            specular_strength=_canonical_pmx_float32(
                self.specular_strength,
                "material specular_strength",
            ),
            ambient=_canonical_pmx_float_tuple(
                self.ambient,
                field_name="material ambient",
            ),
            drawing_flags=self.drawing_flags,
            edge_color=_canonical_pmx_float_tuple(
                self.edge_color,
                field_name="material edge_color",
            ),
            edge_scale=_canonical_pmx_float32(
                self.edge_scale,
                "material edge_scale",
            ),
        )

    def to_dict(self) -> dict[str, object]:
        """Return canonical internal request evidence for deterministic hashing."""

        return {
            "local_name": self.local_name,
            "universal_name": self.universal_name,
            "memo": self.memo,
            "texture_index": self.texture_index,
            "sphere_texture_index": self.sphere_texture_index,
            "sphere_mode": self.sphere_mode,
            "toon_reference_mode": self.toon_reference_mode,
            "toon_reference_index": self.toon_reference_index,
            "diffuse": list(self.diffuse),
            "specular": list(self.specular),
            "specular_strength": self.specular_strength,
            "ambient": list(self.ambient),
            "drawing_flags": self.drawing_flags,
            "edge_color": list(self.edge_color),
            "edge_scale": self.edge_scale,
            "surface_index_count": 0,
            "position": self.position.to_dict(),
        }


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
    max_bytes: int,
    label: str,
) -> None:
    try:
        encoded = text.encode(encoding, errors="strict")
    except UnicodeEncodeError:
        raise PmxStructuralMaterialInsertionError(
            f"{label} cannot be encoded using the source PMX text encoding."
        ) from None
    if len(encoded) > max_bytes:
        raise PmxStructuralMaterialInsertionError(
            f"encoded {label} exceeds the PMX material parser safety limit."
        )


def _validate_texture_reference(
    value: int,
    *,
    texture_count: int,
    label: str,
) -> None:
    if value == -1:
        return
    if value < -1 or value >= texture_count:
        raise PmxStructuralMaterialInsertionError(
            f"{label} must reference an existing source texture or use -1."
        )


def _validate_payload_for_source(
    document: PmxDocument,
    insertion: PmxMaterialInsertionPayload,
) -> None:
    _validate_text_for_source(
        insertion.local_name,
        encoding=document.header.encoding,
        max_bytes=MAX_PMX_NAME_BYTES,
        label="material local name",
    )
    _validate_text_for_source(
        insertion.universal_name,
        encoding=document.header.encoding,
        max_bytes=MAX_PMX_NAME_BYTES,
        label="material universal name",
    )
    _validate_text_for_source(
        insertion.memo,
        encoding=document.header.encoding,
        max_bytes=MAX_PMX_MATERIAL_MEMO_BYTES,
        label="material memo",
    )

    texture_count = len(document.texture_paths)
    _validate_texture_reference(
        insertion.texture_index,
        texture_count=texture_count,
        label="material texture_index",
    )
    _validate_texture_reference(
        insertion.sphere_texture_index,
        texture_count=texture_count,
        label="material sphere_texture_index",
    )
    if insertion.toon_reference_mode == "texture":
        _validate_texture_reference(
            insertion.toon_reference_index,
            texture_count=texture_count,
            label="material toon_reference_index",
        )

    _canonical_pmx_float_tuple(
        insertion.diffuse,
        field_name="material diffuse",
    )
    _canonical_pmx_float_tuple(
        insertion.specular,
        field_name="material specular",
    )
    _canonical_pmx_float32(
        insertion.specular_strength,
        "material specular_strength",
    )
    _canonical_pmx_float_tuple(
        insertion.ambient,
        field_name="material ambient",
    )
    _canonical_pmx_float_tuple(
        insertion.edge_color,
        field_name="material edge_color",
    )
    _canonical_pmx_float32(
        insertion.edge_scale,
        "material edge_scale",
    )


def _require_reader_safe_result_count(
    current_count: int,
    insert_count: int,
) -> int:
    result_count = current_count + insert_count
    if result_count > MAX_PMX_MATERIAL_COUNT:
        raise PmxStructuralMaterialInsertionError(
            "resulting material count exceeds the PMX material parser safety limit."
        )
    return result_count


def _build_material_shift_plan(
    document: PmxDocument,
    insertions: tuple[PmxMaterialInsertionPayload, ...],
) -> PmxCollectionReferenceShiftPlan:
    current_count = len(document.materials)
    expected_result_count = _require_reader_safe_result_count(
        current_count,
        len(insertions),
    )

    for insertion in insertions:
        _validate_payload_for_source(document, insertion)

    position_intent = PmxCollectionInsertionIntent(
        target_kind=PmxReferenceTargetKind.MATERIAL,
        positions=tuple(insertion.position for insertion in insertions),
    )
    shift = plan_collection_reference_shift(
        position_intent,
        current_count=current_count,
        index_width=document.header.index_sizes.material,
    )
    if shift.result_count != expected_result_count:
        raise AssertionError(
            "material reference-shift result count disagrees with the reader-safe "
            "result count."
        )
    return shift


def _materialize_materials(
    source_materials: tuple[PmxMaterial, ...],
    insertions: tuple[PmxMaterialInsertionPayload, ...],
    shift: PmxCollectionReferenceShiftPlan,
) -> tuple[PmxMaterial, ...]:
    if shift.current_count != len(source_materials):
        raise ValueError(
            "material shift current_count does not match source material collection."
        )
    if shift.insert_count != len(insertions):
        raise ValueError(
            "material shift insert_count does not match material insertion payload count."
        )

    slots: list[PmxMaterial | None] = [None] * shift.result_count
    for old_index, new_index in enumerate(shift.remap.targets):
        if new_index is None:
            raise AssertionError("material insertion shift cannot remove old materials.")
        if slots[new_index] is not None:
            raise AssertionError(
                "material insertion shift assigned a duplicate new slot."
            )
        slots[new_index] = source_materials[old_index]

    for request_index, insertion in enumerate(insertions):
        new_index = shift.new_index_for_insertion(request_index)
        if slots[new_index] is not None:
            raise AssertionError(
                "material insertion payload overlaps an old material slot."
            )
        slots[new_index] = insertion.to_material()

    if any(value is None for value in slots):
        raise AssertionError("material insertion materialization left an unfilled slot.")

    return tuple(value for value in slots if value is not None)


def _calculate_intent_sha256(
    insertions: tuple[PmxMaterialInsertionPayload, ...],
    shift: PmxCollectionReferenceShiftPlan,
) -> str:
    canonical = {
        "material_insertions": [insertion.to_dict() for insertion in insertions],
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


def _payload_sha256(insertion: PmxMaterialInsertionPayload) -> str:
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
                kind=PmxReferenceTargetKind.MATERIAL,
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
class PmxMaterialInsertionPreview:
    """One deterministic certified preview for zero-surface material insertion."""

    source_document: PmxDocument
    insertions: tuple[PmxMaterialInsertionPayload, ...]
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
                "material insertion preview requires at least one insertion."
            )
        if not all(
            isinstance(insertion, PmxMaterialInsertionPayload)
            for insertion in self.insertions
        ):
            raise TypeError(
                "insertions must contain only PmxMaterialInsertionPayload values."
            )

        shift = _build_material_shift_plan(self.source_document, self.insertions)
        materials = _materialize_materials(
            self.source_document.materials,
            self.insertions,
            shift,
        )
        morphs = remap_material_morph_references_for_insertion(
            self.source_document.morphs,
            shift,
            pmx_version=self.source_document.header.version,
            additional_uv_count=self.source_document.header.additional_uv_count,
        )
        soft_bodies = remap_soft_body_material_references_for_insertion(
            self.source_document.soft_bodies,
            shift,
            pmx_version=self.source_document.header.version,
        )
        intended_document = replace(
            self.source_document,
            materials=materials,
            morphs=morphs,
            soft_bodies=soft_bodies,
        )

        if intended_document.surface_indices != self.source_document.surface_indices:
            raise AssertionError(
                "material insertion preview must not modify the surface index stream."
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
            "preview_schema_version": PMX_MATERIAL_INSERTION_PREVIEW_SCHEMA_VERSION,
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
                "changed_kinds": ["material"],
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
                    "changed_kinds": ["material"],
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
                "material_insertion": {
                    **self.shift.to_dict(),
                    "surface_stream_changed": False,
                    "inserted_surface_index_count": 0,
                    "payloads": [
                        {
                            "request_index": request_index,
                            "new_index": self.shift.new_index_for_insertion(
                                request_index
                            ),
                            "payload_sha256": _payload_sha256(insertion),
                            "surface_index_count": 0,
                        }
                        for request_index, insertion in enumerate(self.insertions)
                    ],
                },
                "reference_impacts": [
                    item.to_dict() for item in self.reference_impacts
                ],
                "source_reference_diagnostics": [
                    item.to_dict()
                    for item in self.source_reference_diagnostics
                ],
            },
        }


def preview_pmx_material_insertions(
    document: PmxDocument,
    insertions: tuple[PmxMaterialInsertionPayload, ...],
) -> PmxMaterialInsertionPreview:
    """Return one certified in-memory material insertion preview without I/O."""

    return PmxMaterialInsertionPreview(
        source_document=document,
        insertions=insertions,
    )


__all__ = (
    "PmxStructuralMaterialInsertionError",
    "PmxMaterialInsertionPayload",
    "PmxMaterialInsertionPreview",
    "preview_pmx_material_insertions",
)
