"""Preview-only texture-path structural insertion for v0.9.2.

This internal target-specific layer materializes typed texture-path insertions from
source-domain positions, reuses the CP06 reference-shift planner, rewrites the
existing material->texture relationships through their authoritative CP11 owner,
and returns a completely certified in-memory preview.

It does not construct or weaken ``PmxCollectionTransform``, serialize bytes, write
files, resize index widths, expose a public mutation authority, or enable insertion
execution.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from typing import Final

from mmd_registry.pmx.document import PmxDocument
from mmd_registry.pmx.editing.path_policy import validate_portable_texture_path
from mmd_registry.pmx.geometry_material_remap import (
    remap_material_texture_references_for_insertion,
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
from mmd_registry.pmx.sections.textures import (
    MAX_PMX_TEXTURE_COUNT,
    MAX_PMX_TEXTURE_PATH_BYTES,
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


PMX_TEXTURE_INSERTION_PREVIEW_SCHEMA_VERSION: Final[int] = 2


class PmxStructuralTextureInsertionError(ValueError):
    """Raised when one texture insertion preview cannot be safely materialized."""


@dataclass(frozen=True, slots=True)
class PmxTextureInsertionPayload:
    """One internal texture path paired with one source-domain insertion position."""

    path: str
    position: PmxStructuralInsertPosition

    def __post_init__(self) -> None:
        if not isinstance(self.path, str):
            raise TypeError("path must be a string.")
        if not isinstance(self.position, PmxStructuralInsertPosition):
            raise TypeError("position must be a PmxStructuralInsertPosition value.")

    def to_dict(self) -> dict[str, object]:
        """Return canonical internal request evidence for deterministic hashing."""

        return {
            "path": self.path,
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


def _validate_texture_path_for_source(
    path: str,
    *,
    encoding: str,
) -> None:
    """Validate only the explicitly inserted path without rewriting it."""

    validate_portable_texture_path(path)
    try:
        encoded = path.encode(encoding, errors="strict")
    except UnicodeEncodeError:
        raise PmxStructuralTextureInsertionError(
            "texture insertion path cannot be encoded using the source PMX "
            "text encoding."
        ) from None

    if len(encoded) > MAX_PMX_TEXTURE_PATH_BYTES:
        raise PmxStructuralTextureInsertionError(
            "encoded texture insertion path exceeds the PMX texture parser "
            "safety limit."
        )


def _require_reader_safe_result_count(
    current_count: int,
    insert_count: int,
) -> int:
    """Enforce the existing bounded texture reader limit before remap allocation."""

    result_count = current_count + insert_count
    if result_count > MAX_PMX_TEXTURE_COUNT:
        raise PmxStructuralTextureInsertionError(
            "resulting texture count exceeds the PMX texture parser safety limit."
        )
    return result_count


def _build_texture_shift_plan(
    document: PmxDocument,
    insertions: tuple[PmxTextureInsertionPayload, ...],
) -> PmxCollectionReferenceShiftPlan:
    current_count = len(document.texture_paths)
    expected_result_count = _require_reader_safe_result_count(
        current_count,
        len(insertions),
    )

    for insertion in insertions:
        _validate_texture_path_for_source(
            insertion.path,
            encoding=document.header.encoding,
        )

    position_intent = PmxCollectionInsertionIntent(
        target_kind=PmxReferenceTargetKind.TEXTURE,
        positions=tuple(insertion.position for insertion in insertions),
    )
    shift = plan_collection_reference_shift(
        position_intent,
        current_count=current_count,
        index_width=document.header.index_sizes.texture,
    )
    if shift.result_count != expected_result_count:
        raise AssertionError(
            "texture reference-shift result count disagrees with the reader-safe "
            "result count."
        )
    return shift


def _materialize_texture_paths(
    source_paths: tuple[str, ...],
    insertions: tuple[PmxTextureInsertionPayload, ...],
    shift: PmxCollectionReferenceShiftPlan,
) -> tuple[str, ...]:
    """Materialize one dense texture-path result from certified shift evidence."""

    if shift.current_count != len(source_paths):
        raise ValueError(
            "texture shift current_count does not match source texture collection."
        )
    if shift.insert_count != len(insertions):
        raise ValueError(
            "texture shift insert_count does not match texture insertion payload count."
        )

    slots: list[str | None] = [None] * shift.result_count

    for old_index, new_index in enumerate(shift.remap.targets):
        if new_index is None:
            raise AssertionError("texture insertion shift cannot remove old textures.")
        if slots[new_index] is not None:
            raise AssertionError(
                "texture insertion shift assigned a duplicate new slot."
            )
        slots[new_index] = source_paths[old_index]

    for request_index, insertion in enumerate(insertions):
        new_index = shift.new_index_for_insertion(request_index)
        if slots[new_index] is not None:
            raise AssertionError(
                "texture insertion payload overlaps an old texture slot."
            )
        slots[new_index] = insertion.path

    if any(value is None for value in slots):
        raise AssertionError("texture insertion materialization left an unfilled slot.")

    return tuple(value for value in slots if value is not None)


def _calculate_intent_sha256(
    insertions: tuple[PmxTextureInsertionPayload, ...],
    shift: PmxCollectionReferenceShiftPlan,
) -> str:
    canonical = {
        "texture_insertions": [insertion.to_dict() for insertion in insertions],
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


def _path_sha256(path: str) -> str:
    return hashlib.sha256(path.encode("utf-8")).hexdigest()


def _reference_impact_audits(
    source_graph: PmxReferenceGraph,
    shift: PmxCollectionReferenceShiftPlan,
) -> tuple[PmxStructuralReferenceImpactAudit, ...]:
    specs = tuple(
        (
            PmxReferenceNode(
                kind=PmxReferenceTargetKind.TEXTURE,
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
class PmxTextureInsertionPreview:
    """One deterministic certified preview for texture-path insertion only."""

    source_document: PmxDocument
    insertions: tuple[PmxTextureInsertionPayload, ...]
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
                "texture insertion preview requires at least one insertion."
            )
        if not all(
            isinstance(insertion, PmxTextureInsertionPayload)
            for insertion in self.insertions
        ):
            raise TypeError(
                "insertions must contain only PmxTextureInsertionPayload values."
            )

        shift = _build_texture_shift_plan(self.source_document, self.insertions)
        texture_paths = _materialize_texture_paths(
            self.source_document.texture_paths,
            self.insertions,
            shift,
        )
        materials = remap_material_texture_references_for_insertion(
            self.source_document.materials,
            shift,
        )
        intended_document = replace(
            self.source_document,
            texture_paths=texture_paths,
            materials=materials,
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
            "preview_schema_version": PMX_TEXTURE_INSERTION_PREVIEW_SCHEMA_VERSION,
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
                "changed_kinds": ["texture"],
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
                    "changed_kinds": ["texture"],
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
                "texture_insertion": {
                    **self.shift.to_dict(),
                    "payloads": [
                        {
                            "request_index": request_index,
                            "new_index": self.shift.new_index_for_insertion(
                                request_index
                            ),
                            "path_sha256": _path_sha256(insertion.path),
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


def preview_pmx_texture_insertions(
    document: PmxDocument,
    insertions: tuple[PmxTextureInsertionPayload, ...],
) -> PmxTextureInsertionPreview:
    """Return one certified in-memory texture insertion preview without I/O."""

    return PmxTextureInsertionPreview(
        source_document=document,
        insertions=insertions,
    )


__all__ = (
    "PmxStructuralTextureInsertionError",
    "PmxTextureInsertionPayload",
    "PmxTextureInsertionPreview",
    "preview_pmx_texture_insertions",
)
