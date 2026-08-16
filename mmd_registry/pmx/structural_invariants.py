"""CP16 complete post-transform invariant certification.

This internal layer composes the CP15 structural orchestrator with the existing
whole-document PMX validator and the CP05/CP07 reference-analysis model.  It
does not define a competing PMX validity model, serialize bytes, write files,
resize index widths, expose a public mutation API, or repair invalid state.

The existing ``validate_pmx_document`` function remains authoritative for PMX
semantic validity and serialization capacity.  Reference extraction is a
second, read-only consistency check over the frozen 27-relationship taxonomy.
A validator PASS followed by non-empty reference diagnostics is treated as an
internal invariant-model disagreement and fails closed.

The certificate is self-validating: callers provide only a ``PmxDocument``.
Construction performs the complete CP16 certification sequence and derives the
reference graph internally, so a stale or unrelated graph cannot be attached
to a document and presented as certified evidence.

Structural certification rejects non-empty ``trailing_data`` even for a no-op
transform. Read-only round-trip may preserve opaque trailing bytes, but a
document carrying unknown trailing reference semantics is not eligible for the
v0.9.0 structural-edit certification path.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mmd_registry.pmx.collection_transform import PmxStructuralTransformIntent
from mmd_registry.pmx.document import PmxDocument
from mmd_registry.pmx.reference_diagnostics import diagnose_reference_graph
from mmd_registry.pmx.reference_graph import (
    PmxReferenceGraph,
    extract_pmx_reference_graph,
)
from mmd_registry.pmx.structural_orchestrator import transform_pmx_document
from mmd_registry.pmx.validation import validate_pmx_document


class PmxStructuralInvariantError(ValueError):
    """Raised when structural output cannot receive a complete certificate."""


@dataclass(frozen=True, slots=True)
class PmxStructuralInvariantCertificate:
    """Immutable evidence that one document passed the complete CP16 gate."""

    document: PmxDocument
    reference_graph: PmxReferenceGraph = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.document, PmxDocument):
            raise TypeError("document must be a PmxDocument instance.")

        if self.document.trailing_data:
            raise PmxStructuralInvariantError(
                "structural certification requires empty trailing_data because "
                "opaque trailing reference semantics are unknown."
            )

        # Single PMX validity authority.  Preserve PmxValidationError unchanged.
        # This proves declared index-width capacity, version constraints,
        # text/float encodability, section coverage, and cross-section bounds.
        validate_pmx_document(self.document)

        # Derive the graph *after* validator PASS.  Because callers cannot
        # provide this field, the certificate cannot carry a stale graph from
        # another same-sized document.
        graph = extract_pmx_reference_graph(self.document)
        diagnostics = diagnose_reference_graph(graph)
        if diagnostics:
            first = diagnostics[0]
            raise PmxStructuralInvariantError(
                "validated structural output disagrees with the reference model: "
                f"{len(diagnostics)} diagnostic(s); first={first.code.value}; "
                f"relationship={first.relationship_id}; source={first.source.path}."
            )

        object.__setattr__(self, "reference_graph", graph)

    @property
    def edge_count(self) -> int:
        """Return the number of valid active reference edges."""

        return len(self.reference_graph.edges)

    @property
    def relationship_counts(self) -> tuple[tuple[str, int], ...]:
        """Return deterministic valid-edge counts by relationship identifier."""

        counts: dict[str, int] = {}
        for edge in self.reference_graph.edges:
            counts[edge.relationship_id] = counts.get(edge.relationship_id, 0) + 1
        return tuple(sorted(counts.items()))

    def to_dict(self) -> dict[str, object]:
        """Return deterministic JSON-ready certification evidence."""

        counts = self.reference_graph.target_counts
        return {
            "target_counts": {
                "vertex": counts.vertex,
                "texture": counts.texture,
                "material": counts.material,
                "bone": counts.bone,
                "morph": counts.morph,
                "rigid_body": counts.rigid_body,
            },
            "edge_count": self.edge_count,
            "relationship_counts": dict(self.relationship_counts),
            "reference_diagnostic_count": 0,
        }


def transform_and_certify_pmx_document(
    document: PmxDocument,
    intent: PmxStructuralTransformIntent,
) -> PmxStructuralInvariantCertificate:
    """Transform one document and return evidence only after complete CP16 PASS."""

    transformed = transform_pmx_document(document, intent)
    return PmxStructuralInvariantCertificate(document=transformed)
