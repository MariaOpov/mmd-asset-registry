"""Tests for deterministic inbound/outbound PMX reference queries."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
import unittest

import mmd_registry.pmx as pmx
import mmd_registry.services as services
from mmd_registry.pmx.reference_graph import (
    PmxReferenceGraph,
    PmxReferenceInvalidTarget,
    PmxReferenceTargetCounts,
    PmxReferenceUnsupportedState,
    PmxReferenceUnsupportedStateKind,
)
from mmd_registry.pmx.reference_model import (
    PmxReferenceEdge,
    PmxReferenceNode,
    PmxReferenceSourceLocation,
    PmxReferenceSourceSection,
    PmxReferenceTargetKind,
)
from mmd_registry.pmx.reference_queries import (
    PmxReferenceImpact,
    analyze_reference_impact,
    inbound_references,
    outbound_references,
)


def _source(
    section: PmxReferenceSourceSection,
    record_index: int,
    suffix: str,
) -> PmxReferenceSourceLocation:
    prefix = f"{section.value}[{record_index}]"
    return PmxReferenceSourceLocation(
        section,
        record_index,
        f"{prefix}.{suffix}" if suffix else prefix,
    )


def _edge(
    relationship_id: str,
    section: PmxReferenceSourceSection,
    source_index: int,
    source_suffix: str,
    target_kind: PmxReferenceTargetKind,
    target_index: int,
) -> PmxReferenceEdge:
    return PmxReferenceEdge(
        relationship_id,
        _source(section, source_index, source_suffix),
        PmxReferenceNode(target_kind, target_index),
    )


def _graph(
    *,
    edges: tuple[PmxReferenceEdge, ...] = (),
    invalid_targets: tuple[PmxReferenceInvalidTarget, ...] = (),
    unsupported_states: tuple[PmxReferenceUnsupportedState, ...] = (),
) -> PmxReferenceGraph:
    return PmxReferenceGraph(
        target_counts=PmxReferenceTargetCounts(
            vertex=2,
            texture=2,
            material=2,
            bone=3,
            morph=2,
            rigid_body=2,
        ),
        edges=edges,
        invalid_targets=invalid_targets,
        unsupported_states=unsupported_states,
    )


class PmxReferenceQueryTests(unittest.TestCase):
    """Freeze CP06 as a graph-only deterministic query layer."""

    def test_inbound_references_preserve_graph_order_and_cycles(self) -> None:
        target = PmxReferenceNode(PmxReferenceTargetKind.BONE, 1)
        edges = (
            _edge(
                "bone.parent",
                PmxReferenceSourceSection.BONES,
                1,
                "parent_bone_index",
                PmxReferenceTargetKind.BONE,
                1,
            ),
            _edge(
                "vertex.deform.bdef1.bone",
                PmxReferenceSourceSection.VERTICES,
                0,
                "deform.bone_index",
                PmxReferenceTargetKind.BONE,
                1,
            ),
            _edge(
                "bone.parent",
                PmxReferenceSourceSection.BONES,
                2,
                "parent_bone_index",
                PmxReferenceTargetKind.BONE,
                0,
            ),
            _edge(
                "bone.ik_link",
                PmxReferenceSourceSection.BONES,
                0,
                "ik.links[0].bone_index",
                PmxReferenceTargetKind.BONE,
                1,
            ),
        )

        result = inbound_references(_graph(edges=edges), target)

        self.assertEqual(result, (edges[0], edges[1], edges[3]))

    def test_outbound_references_are_owned_only_by_addressable_source_records(
        self,
    ) -> None:
        bone = PmxReferenceNode(PmxReferenceTargetKind.BONE, 1)
        edges = (
            _edge(
                "bone.parent",
                PmxReferenceSourceSection.BONES,
                1,
                "parent_bone_index",
                PmxReferenceTargetKind.BONE,
                0,
            ),
            _edge(
                "bone.tail",
                PmxReferenceSourceSection.BONES,
                1,
                "tail_bone_index",
                PmxReferenceTargetKind.BONE,
                2,
            ),
            _edge(
                "display_frame.bone",
                PmxReferenceSourceSection.DISPLAY_FRAMES,
                1,
                "elements[0].target_index",
                PmxReferenceTargetKind.BONE,
                1,
            ),
            _edge(
                "joint.rigid_body_a",
                PmxReferenceSourceSection.JOINTS,
                1,
                "rigid_body_a_index",
                PmxReferenceTargetKind.RIGID_BODY,
                0,
            ),
        )

        result = outbound_references(_graph(edges=edges), bone)

        self.assertEqual(result, (edges[0], edges[1]))

    def test_each_reference_owning_target_collection_maps_to_its_source_section(
        self,
    ) -> None:
        cases = (
            (
                PmxReferenceTargetKind.VERTEX,
                PmxReferenceSourceSection.VERTICES,
                "vertex.deform.bdef1.bone",
                "deform.bone_index",
                PmxReferenceTargetKind.BONE,
            ),
            (
                PmxReferenceTargetKind.MATERIAL,
                PmxReferenceSourceSection.MATERIALS,
                "material.texture",
                "texture_index",
                PmxReferenceTargetKind.TEXTURE,
            ),
            (
                PmxReferenceTargetKind.BONE,
                PmxReferenceSourceSection.BONES,
                "bone.parent",
                "parent_bone_index",
                PmxReferenceTargetKind.BONE,
            ),
            (
                PmxReferenceTargetKind.MORPH,
                PmxReferenceSourceSection.MORPHS,
                "morph.vertex.vertex",
                "offsets[0].vertex_index",
                PmxReferenceTargetKind.VERTEX,
            ),
            (
                PmxReferenceTargetKind.RIGID_BODY,
                PmxReferenceSourceSection.RIGID_BODIES,
                "rigid_body.bone",
                "bone_index",
                PmxReferenceTargetKind.BONE,
            ),
        )

        for (
            source_kind,
            source_section,
            relationship_id,
            suffix,
            target_kind,
        ) in cases:
            with self.subTest(source_kind=source_kind):
                edge = _edge(
                    relationship_id,
                    source_section,
                    0,
                    suffix,
                    target_kind,
                    0,
                )
                graph = _graph(edges=(edge,))

                self.assertEqual(
                    outbound_references(
                        graph,
                        PmxReferenceNode(source_kind, 0),
                    ),
                    (edge,),
                )

    def test_texture_node_has_no_outbound_ownership(self) -> None:
        edge = _edge(
            "material.texture",
            PmxReferenceSourceSection.MATERIALS,
            0,
            "texture_index",
            PmxReferenceTargetKind.TEXTURE,
            0,
        )
        graph = _graph(edges=(edge,))

        self.assertEqual(
            outbound_references(
                graph,
                PmxReferenceNode(PmxReferenceTargetKind.TEXTURE, 0),
            ),
            (),
        )

    def test_query_rejects_missing_node_instead_of_returning_false_empty_impact(
        self,
    ) -> None:
        graph = _graph()
        missing = PmxReferenceNode(PmxReferenceTargetKind.BONE, 3)

        for query in (
            inbound_references,
            outbound_references,
            analyze_reference_impact,
        ):
            with self.subTest(query=query.__name__):
                with self.assertRaises(ValueError):
                    query(graph, missing)

        with self.assertRaises(TypeError):
            inbound_references(object(), PmxReferenceNode(PmxReferenceTargetKind.BONE, 0))  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            inbound_references(graph, object())  # type: ignore[arg-type]

    def test_impact_collects_direct_edges_and_source_owned_invalid_evidence(
        self,
    ) -> None:
        node = PmxReferenceNode(PmxReferenceTargetKind.BONE, 1)
        inbound = _edge(
            "vertex.deform.bdef1.bone",
            PmxReferenceSourceSection.VERTICES,
            0,
            "deform.bone_index",
            PmxReferenceTargetKind.BONE,
            1,
        )
        outbound = _edge(
            "bone.parent",
            PmxReferenceSourceSection.BONES,
            1,
            "parent_bone_index",
            PmxReferenceTargetKind.BONE,
            0,
        )
        invalid = PmxReferenceInvalidTarget(
            "bone.ik_link",
            _source(
                PmxReferenceSourceSection.BONES,
                1,
                "ik.links[0].bone_index",
            ),
            PmxReferenceTargetKind.BONE,
            99,
            3,
        )
        unrelated_invalid = PmxReferenceInvalidTarget(
            "surface.vertex",
            _source(PmxReferenceSourceSection.SURFACE_INDICES, 0, ""),
            PmxReferenceTargetKind.VERTEX,
            99,
            2,
        )
        graph = _graph(
            edges=(inbound, outbound),
            invalid_targets=(invalid, unrelated_invalid),
        )

        impact = analyze_reference_impact(graph, node)

        self.assertEqual(impact.inbound_edges, (inbound,))
        self.assertEqual(impact.outbound_edges, (outbound,))
        self.assertEqual(impact.source_invalid_targets, (invalid,))
        self.assertEqual(impact.source_unsupported_states, ())
        self.assertEqual(impact.unresolved_states, ())
        self.assertTrue(impact.is_complete)

    def test_any_unsupported_state_marks_impact_incomplete_conservatively(
        self,
    ) -> None:
        node = PmxReferenceNode(PmxReferenceTargetKind.BONE, 1)
        owned = PmxReferenceUnsupportedState(
            PmxReferenceUnsupportedStateKind.ACTIVE_PAYLOAD_MISSING,
            "bone.ik_target",
            _source(PmxReferenceSourceSection.BONES, 1, "ik"),
            "ik_flag_enabled;ik=None",
        )
        elsewhere = PmxReferenceUnsupportedState(
            PmxReferenceUnsupportedStateKind.MORPH_OFFSET_TYPE_MISMATCH,
            "morph.vertex.vertex",
            _source(PmxReferenceSourceSection.MORPHS, 0, "offsets[0]"),
            "PmxBoneMorphOffset",
        )
        graph = _graph(unsupported_states=(owned, elsewhere))

        impact = analyze_reference_impact(graph, node)

        self.assertEqual(impact.source_unsupported_states, (owned,))
        self.assertEqual(impact.unresolved_states, (owned, elsewhere))
        self.assertFalse(impact.is_complete)

    def test_impact_is_immutable_hashable_and_deterministic(self) -> None:
        node = PmxReferenceNode(PmxReferenceTargetKind.MATERIAL, 0)
        graph = _graph()

        first = analyze_reference_impact(graph, node)
        second = analyze_reference_impact(graph, node)

        self.assertEqual(first, second)
        self.assertEqual(hash(first), hash(second))
        with self.assertRaises(FrozenInstanceError):
            first.node = PmxReferenceNode(  # type: ignore[misc]
                PmxReferenceTargetKind.MATERIAL,
                1,
            )

    def test_impact_constructor_rejects_untyped_collections(self) -> None:
        node = PmxReferenceNode(PmxReferenceTargetKind.BONE, 0)

        with self.assertRaises(TypeError):
            PmxReferenceImpact(  # type: ignore[arg-type]
                node=node,
                inbound_edges=[],
                outbound_edges=(),
                source_invalid_targets=(),
                source_unsupported_states=(),
                unresolved_states=(),
            )

    def test_query_layer_does_not_expand_public_exports_or_retraverse_document(
        self,
    ) -> None:
        self.assertNotIn("inbound_references", pmx.__all__)
        self.assertNotIn("analyze_reference_impact", pmx.__all__)
        self.assertNotIn("inbound_references", services.__all__)
        self.assertNotIn("analyze_reference_impact", services.__all__)

        source = (
            Path(__file__).resolve().parents[1]
            / "mmd_registry"
            / "pmx"
            / "reference_queries.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("PmxDocument", source)
        self.assertNotIn("extract_pmx_reference_graph", source)
        self.assertNotIn("validate_pmx_document", source)
        self.assertNotIn("Path(", source)
        self.assertNotIn(".open(", source)


if __name__ == "__main__":
    unittest.main()
