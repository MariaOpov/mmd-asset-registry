"""CP17 deterministic structural preview and audit evidence.

This internal layer turns one CP10 structural intent into deterministic,
GUI-friendly in-memory evidence without serialization or filesystem I/O.

The preview reuses the established v0.8 preview vocabulary:

* immutable preview and audit records;
* ``status`` plus ``dry_run``;
* nested ``source`` / ``intent`` / ``output`` / ``verification`` / ``audit``;
* canonical SHA-256 over JSON-ready intent evidence;
* stable ordered ``to_dict()`` output.

Unlike the legacy field-edit preview, CP17 starts from an already-typed
``PmxDocument`` and intentionally does not serialize/reparse it. Therefore it
must not reuse the legacy ``verification.semantic = passed`` claim, whose
existing meaning follows serialize/reparse equality. CP15 owns structural
transformation, CP16 owns complete invariant certification, and CP18 owns
verified serialization/output.

Reference-impact evidence is computed from the *source* CP05 graph. This is
explicitly conservative *direct-node* evidence, not a complete global edge
delta: CP06 does not attribute non-addressable source sections such as surface
indices, display frames, joints, or soft bodies to target nodes. Source/output
valid-edge counts are therefore reported separately. CP06 completeness
semantics are preserved, and source diagnostics are retained rather than
silently normalized.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Final

from mmd_registry.pmx.collection_transform import (
    PmxCollectionTransform,
    PmxStructuralTransformIntent,
)
from mmd_registry.pmx.document import PmxDocument
from mmd_registry.pmx.reference_diagnostics import (
    PmxReferenceDiagnostic,
    diagnose_reference_graph,
)
from mmd_registry.pmx.reference_graph import (
    PmxReferenceGraph,
    PmxReferenceTargetCounts,
    extract_pmx_reference_graph,
)
from mmd_registry.pmx.reference_model import (
    PmxReferenceEdge,
    PmxReferenceNode,
    PmxReferenceTargetKind,
)
from mmd_registry.pmx.reference_queries import (
    PmxReferenceImpact,
    analyze_reference_impact,
)
from mmd_registry.pmx.structural_invariants import (
    PmxStructuralInvariantCertificate,
    transform_and_certify_pmx_document,
)


PMX_STRUCTURAL_PREVIEW_SCHEMA_VERSION: Final[int] = 1

_TARGET_KIND_ORDER: Final[dict[PmxReferenceTargetKind, int]] = {
    kind: position for position, kind in enumerate(PmxReferenceTargetKind)
}


def _target_collection_size(
    document: PmxDocument,
    kind: PmxReferenceTargetKind,
) -> int:
    if kind is PmxReferenceTargetKind.VERTEX:
        return len(document.vertices)
    if kind is PmxReferenceTargetKind.TEXTURE:
        return len(document.texture_paths)
    if kind is PmxReferenceTargetKind.MATERIAL:
        return len(document.materials)
    if kind is PmxReferenceTargetKind.BONE:
        return len(document.bones)
    if kind is PmxReferenceTargetKind.MORPH:
        return len(document.morphs)
    if kind is PmxReferenceTargetKind.RIGID_BODY:
        return len(document.rigid_bodies)
    raise AssertionError(f"unhandled target kind {kind!r}")


def _target_counts_to_dict(
    counts: PmxReferenceTargetCounts,
) -> dict[str, int]:
    return {
        "vertex": counts.vertex,
        "texture": counts.texture,
        "material": counts.material,
        "bone": counts.bone,
        "morph": counts.morph,
        "rigid_body": counts.rigid_body,
    }


def _edge_key(edge: PmxReferenceEdge) -> tuple[str, str, int, str, str, int]:
    return (
        edge.relationship_id,
        edge.source.section.value,
        edge.source.record_index,
        edge.source.path,
        edge.target.kind.value,
        edge.target.index,
    )


@dataclass(frozen=True, slots=True)
class PmxStructuralCollectionAudit:
    """Deterministic evidence for one fully resolved target collection transform."""

    transform: PmxCollectionTransform

    def __post_init__(self) -> None:
        if not isinstance(self.transform, PmxCollectionTransform):
            raise TypeError("transform must be a PmxCollectionTransform value.")

    @property
    def kind(self) -> PmxReferenceTargetKind:
        return self.transform.kind

    @property
    def changed_old_indices(self) -> tuple[int, ...]:
        return tuple(
            old_index
            for old_index, new_index in enumerate(self.transform.remap.targets)
            if new_index != old_index
        )

    @property
    def reindexed_old_indices(self) -> tuple[int, ...]:
        return tuple(
            old_index
            for old_index, new_index in enumerate(self.transform.remap.targets)
            if new_index is not None and new_index != old_index
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "old_size": self.transform.old_size,
            "new_size": self.transform.new_size,
            "targets": list(self.transform.remap.targets),
            "removed_old_indices": list(self.transform.removed_old_indices),
            "old_indices_in_new_order": list(
                self.transform.old_indices_in_new_order
            ),
            "changed_old_indices": list(self.changed_old_indices),
            "reindexed_old_indices": list(self.reindexed_old_indices),
            "has_deletions": self.transform.has_deletions,
            "has_reorder": self.transform.has_reorder,
            "is_noop": self.transform.is_noop,
        }


@dataclass(frozen=True, slots=True)
class PmxStructuralReferenceImpactAudit:
    """CP06 direct source-graph impact for one removed or reindexed old node."""

    node: PmxReferenceNode
    new_index: int | None
    impact: PmxReferenceImpact

    def __post_init__(self) -> None:
        if not isinstance(self.node, PmxReferenceNode):
            raise TypeError("node must be a PmxReferenceNode value.")
        if self.new_index is not None:
            if type(self.new_index) is not int:
                raise TypeError("new_index must be an integer or None.")
            if self.new_index < 0:
                raise ValueError("new_index cannot be negative.")
            if self.new_index == self.node.index:
                raise ValueError(
                    "reference impact audit requires a removed or reindexed node."
                )
        if not isinstance(self.impact, PmxReferenceImpact):
            raise TypeError("impact must be a PmxReferenceImpact value.")
        if self.impact.node != self.node:
            raise ValueError("impact node must match the audited source node.")

    @property
    def state(self) -> str:
        return "removed" if self.new_index is None else "reindexed"

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.node.kind.value,
            "old_index": self.node.index,
            "new_index": self.new_index,
            "state": self.state,
            "inbound_reference_count": len(self.impact.inbound_edges),
            "outbound_reference_count": len(self.impact.outbound_edges),
            "source_invalid_target_count": len(
                self.impact.source_invalid_targets
            ),
            "source_unsupported_state_count": len(
                self.impact.source_unsupported_states
            ),
            "complete": self.impact.is_complete,
        }


@dataclass(frozen=True, slots=True)
class PmxStructuralAudit:
    """Ordered structural-transform and conservative direct-impact evidence."""

    collections: tuple[PmxStructuralCollectionAudit, ...]
    reference_impacts: tuple[PmxStructuralReferenceImpactAudit, ...]
    source_reference_diagnostics: tuple[PmxReferenceDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        if type(self.collections) is not tuple:
            raise TypeError("collections must be a tuple.")
        if not all(
            isinstance(item, PmxStructuralCollectionAudit)
            for item in self.collections
        ):
            raise TypeError(
                "collections must contain only PmxStructuralCollectionAudit values."
            )

        kinds = tuple(item.kind for item in self.collections)
        expected_kinds = tuple(PmxReferenceTargetKind)
        if kinds != expected_kinds:
            raise ValueError(
                "collections must cover all target kinds exactly once in canonical order."
            )

        if type(self.reference_impacts) is not tuple:
            raise TypeError("reference_impacts must be a tuple.")
        if not all(
            isinstance(item, PmxStructuralReferenceImpactAudit)
            for item in self.reference_impacts
        ):
            raise TypeError(
                "reference_impacts must contain only "
                "PmxStructuralReferenceImpactAudit values."
            )

        expected_impacts: list[
            tuple[PmxReferenceTargetKind, int, int | None]
        ] = []
        for collection in self.collections:
            for old_index in collection.changed_old_indices:
                expected_impacts.append(
                    (
                        collection.kind,
                        old_index,
                        collection.transform.remap.targets[old_index],
                    )
                )
        observed_impacts = [
            (item.node.kind, item.node.index, item.new_index)
            for item in self.reference_impacts
        ]
        if observed_impacts != expected_impacts:
            raise ValueError(
                "reference_impacts must exactly cover changed old nodes in "
                "canonical target-kind/old-index order."
            )

        if type(self.source_reference_diagnostics) is not tuple:
            raise TypeError("source_reference_diagnostics must be a tuple.")
        if not all(
            isinstance(item, PmxReferenceDiagnostic)
            for item in self.source_reference_diagnostics
        ):
            raise TypeError(
                "source_reference_diagnostics must contain only "
                "PmxReferenceDiagnostic values."
            )

    @property
    def changed_kinds(self) -> tuple[PmxReferenceTargetKind, ...]:
        return tuple(
            item.kind for item in self.collections if not item.transform.is_noop
        )

    @property
    def changed_node_count(self) -> int:
        return len(self.reference_impacts)

    @property
    def removed_record_count(self) -> int:
        return sum(
            len(item.transform.removed_old_indices)
            for item in self.collections
        )

    @property
    def reindexed_record_count(self) -> int:
        return sum(len(item.reindexed_old_indices) for item in self.collections)

    @property
    def direct_reference_edge_count(self) -> int:
        unique_edges: set[tuple[str, str, int, str, str, int]] = set()
        for item in self.reference_impacts:
            for edge in (*item.impact.inbound_edges, *item.impact.outbound_edges):
                unique_edges.add(_edge_key(edge))
        return len(unique_edges)

    @property
    def direct_reference_impact_complete(self) -> bool:
        return all(item.impact.is_complete for item in self.reference_impacts)

    def to_dict(self) -> dict[str, object]:
        return {
            "summary": {
                "changed_kinds": [kind.value for kind in self.changed_kinds],
                "changed_collection_count": len(self.changed_kinds),
                "changed_node_count": self.changed_node_count,
                "removed_record_count": self.removed_record_count,
                "reindexed_record_count": self.reindexed_record_count,
                "direct_reference_edge_count": self.direct_reference_edge_count,
                "direct_reference_impact_complete": self.direct_reference_impact_complete,
                "source_reference_diagnostic_count": len(
                    self.source_reference_diagnostics
                ),
            },
            "collections": [item.to_dict() for item in self.collections],
            "reference_impacts": [
                item.to_dict() for item in self.reference_impacts
            ],
            "source_reference_diagnostics": [
                item.to_dict() for item in self.source_reference_diagnostics
            ],
        }


def _resolved_collection_audits(
    document: PmxDocument,
    intent: PmxStructuralTransformIntent,
) -> tuple[PmxStructuralCollectionAudit, ...]:
    audits: list[PmxStructuralCollectionAudit] = []
    for kind in PmxReferenceTargetKind:
        old_size = _target_collection_size(document, kind)
        transform = intent.transform_for(kind)
        if transform is None:
            transform = PmxCollectionTransform.identity(kind, old_size)
        elif transform.old_size != old_size:
            raise AssertionError(
                "CP15 accepted a transform whose old_size does not match "
                f"the source {kind.value} collection."
            )
        audits.append(PmxStructuralCollectionAudit(transform=transform))
    return tuple(audits)


def _reference_impact_audits(
    source_graph: PmxReferenceGraph,
    collections: tuple[PmxStructuralCollectionAudit, ...],
) -> tuple[PmxStructuralReferenceImpactAudit, ...]:
    result: list[PmxStructuralReferenceImpactAudit] = []
    for collection in collections:
        for old_index in collection.changed_old_indices:
            node = PmxReferenceNode(kind=collection.kind, index=old_index)
            result.append(
                PmxStructuralReferenceImpactAudit(
                    node=node,
                    new_index=collection.transform.remap.targets[old_index],
                    impact=analyze_reference_impact(source_graph, node),
                )
            )
    return tuple(result)


def _calculate_resolved_intent_sha256(
    collections: tuple[PmxStructuralCollectionAudit, ...],
) -> str:
    canonical = {
        "collections": [item.to_dict() for item in collections],
    }
    payload = json.dumps(
        canonical,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PmxStructuralPreview:
    """One self-derived in-memory structural preview with certified result."""

    source_document: PmxDocument
    intent: PmxStructuralTransformIntent
    certificate: PmxStructuralInvariantCertificate = field(init=False)
    audit: PmxStructuralAudit = field(init=False)
    intent_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.source_document, PmxDocument):
            raise TypeError("source_document must be a PmxDocument instance.")
        if not isinstance(self.intent, PmxStructuralTransformIntent):
            raise TypeError("intent must be a PmxStructuralTransformIntent value.")

        # Execute CP15 + CP16 first.  No preview exists for uncertified output.
        certificate = transform_and_certify_pmx_document(
            self.source_document,
            self.intent,
        )

        # Source analysis is deliberately independent and may retain diagnostics
        # for state removed by the successful structural transform.
        source_graph = extract_pmx_reference_graph(self.source_document)
        source_diagnostics = diagnose_reference_graph(source_graph)

        collections = _resolved_collection_audits(
            self.source_document,
            self.intent,
        )
        audit = PmxStructuralAudit(
            collections=collections,
            reference_impacts=_reference_impact_audits(
                source_graph,
                collections,
            ),
            source_reference_diagnostics=source_diagnostics,
        )

        object.__setattr__(self, "certificate", certificate)
        object.__setattr__(self, "audit", audit)
        object.__setattr__(
            self,
            "intent_sha256",
            _calculate_resolved_intent_sha256(collections),
        )

    @property
    def status(self) -> str:
        return "no_changes" if not self.audit.changed_kinds else "changes_pending"

    def to_dict(self) -> dict[str, object]:
        source_graph = extract_pmx_reference_graph(self.source_document)
        return {
            "preview_schema_version": PMX_STRUCTURAL_PREVIEW_SCHEMA_VERSION,
            "status": self.status,
            "dry_run": True,
            "source": {
                "target_counts": _target_counts_to_dict(
                    source_graph.target_counts
                ),
                "reference_edge_count": len(source_graph.edges),
                "reference_diagnostic_count": len(
                    self.audit.source_reference_diagnostics
                ),
            },
            "intent": {
                "sha256": self.intent_sha256,
                "changed_kinds": [
                    kind.value for kind in self.audit.changed_kinds
                ],
                "collection_count": len(self.audit.collections),
            },
            "output": {
                "written": False,
                "target_counts": _target_counts_to_dict(
                    self.certificate.reference_graph.target_counts
                ),
                "reference_edge_count": self.certificate.edge_count,
                "reference_diagnostic_count": 0,
            },
            "verification": {
                "invariants": "passed",
                "reference_model": "passed",
                "serialization": "not_performed",
            },
            "audit": self.audit.to_dict(),
        }


def preview_pmx_structural_transform(
    document: PmxDocument,
    intent: PmxStructuralTransformIntent,
) -> PmxStructuralPreview:
    """Return deterministic certified structural evidence without serialization."""

    return PmxStructuralPreview(
        source_document=document,
        intent=intent,
    )
