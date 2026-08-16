from __future__ import annotations

import importlib
import io
import unittest
from dataclasses import replace
from unittest.mock import patch

import mmd_registry.pmx as pmx_public
import mmd_registry.services as services_public
from mmd_registry.pmx import load_pmx
from mmd_registry.pmx.collection_transform import (
    PmxCollectionTransform,
    PmxStructuralTransformIntent,
)
from mmd_registry.pmx.index_remap import PmxIndexRemap
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
    _analyze_reference_impacts,
)
from mmd_registry.pmx.structural_preview import preview_pmx_structural_transform
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


reference_queries_module = importlib.import_module(
    "mmd_registry.pmx.reference_queries"
)
structural_preview_module = importlib.import_module(
    "mmd_registry.pmx.structural_preview"
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


def _synthetic_bone_graph(size: int = 128) -> PmxReferenceGraph:
    edges = tuple(
        PmxReferenceEdge(
            "bone.parent",
            _source(
                PmxReferenceSourceSection.BONES,
                index,
                "parent_bone_index",
            ),
            PmxReferenceNode(
                PmxReferenceTargetKind.BONE,
                (index - 1) % size,
            ),
        )
        for index in range(size)
    )
    invalid_targets = tuple(
        PmxReferenceInvalidTarget(
            "bone.ik_link",
            _source(
                PmxReferenceSourceSection.BONES,
                index,
                "ik.links[0].bone_index",
            ),
            PmxReferenceTargetKind.BONE,
            size + index,
            size,
        )
        for index in range(size)
    )
    unsupported_states = tuple(
        PmxReferenceUnsupportedState(
            PmxReferenceUnsupportedStateKind.ACTIVE_PAYLOAD_MISSING,
            "bone.ik_target",
            _source(PmxReferenceSourceSection.BONES, index, "ik"),
            "ik_flag_enabled;ik=None",
        )
        for index in range(size)
    )
    return PmxReferenceGraph(
        target_counts=PmxReferenceTargetCounts(
            vertex=0,
            texture=0,
            material=0,
            bone=size,
            morph=0,
            rigid_body=0,
        ),
        edges=edges,
        invalid_targets=invalid_targets,
        unsupported_states=unsupported_states,
    )


def _document(*, version: float = 2.1):
    return replace(
        load_pmx(io.BytesIO(build_pmx_roundtrip_fixture(version=version))),
        trailing_data=b"",
    )


def _target_size(document, kind: PmxReferenceTargetKind) -> int:
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


def _full_reverse_intent(document) -> PmxStructuralTransformIntent:
    transforms = []
    for kind in PmxReferenceTargetKind:
        size = _target_size(document, kind)
        transforms.append(
            PmxCollectionTransform(
                kind=kind,
                remap=PmxIndexRemap(
                    targets=tuple(reversed(range(size))),
                    new_size=size,
                ),
            )
        )
    return PmxStructuralTransformIntent(transforms=tuple(transforms))


class StructuralResourceStateIsolationTests(unittest.TestCase):
    def test_batch_impact_analysis_is_linear_in_graph_evidence_not_changed_nodes(
        self,
    ) -> None:
        graph = _synthetic_bone_graph()
        nodes = tuple(
            PmxReferenceNode(PmxReferenceTargetKind.BONE, index)
            for index in range(graph.target_counts.bone)
        )
        original_owner = reference_queries_module._source_target_owner

        with patch.object(
            reference_queries_module,
            "_source_target_owner",
            wraps=original_owner,
        ) as owner_lookup:
            with patch.object(
                PmxReferenceImpact,
                "__post_init__",
                side_effect=AssertionError(
                    "batch graph evidence must not revalidate each impact"
                ),
            ):
                impacts = _analyze_reference_impacts(graph, nodes)

        self.assertEqual(len(impacts), len(nodes))
        self.assertEqual(
            owner_lookup.call_count,
            len(graph.edges)
            + len(graph.invalid_targets)
            + len(graph.unsupported_states),
        )
        self.assertTrue(
            all(
                impact.unresolved_states is graph.unsupported_states
                for impact in impacts
            )
        )
        self.assertTrue(all(not impact.is_complete for impact in impacts))

        first = impacts[0]
        self.assertEqual(first.node, nodes[0])
        self.assertEqual(len(first.inbound_edges), 1)
        self.assertEqual(len(first.outbound_edges), 1)
        self.assertEqual(len(first.source_invalid_targets), 1)
        self.assertEqual(len(first.source_unsupported_states), 1)

    def test_structural_preview_batches_all_changed_nodes_once(self) -> None:
        source = _document()
        intent = _full_reverse_intent(source)
        original_batch = reference_queries_module._analyze_reference_impacts

        with patch.object(
            structural_preview_module,
            "_analyze_reference_impacts",
            wraps=original_batch,
        ) as batch:
            preview = preview_pmx_structural_transform(source, intent)
            report = preview.to_dict()

        self.assertEqual(batch.call_count, 1)
        batch_nodes = batch.call_args.args[1]
        self.assertEqual(len(batch_nodes), preview.audit.changed_node_count)
        self.assertEqual(
            report["audit"]["summary"]["changed_node_count"],
            preview.audit.changed_node_count,
        )

    def test_repeated_preview_isolated_across_unrelated_calls(self) -> None:
        source_a = _document(version=2.1)
        source_b = _document(version=2.0)
        intent_a = _full_reverse_intent(source_a)

        first = preview_pmx_structural_transform(source_a, intent_a)
        preview_pmx_structural_transform(
            source_b,
            PmxStructuralTransformIntent(),
        ).to_dict()
        second = preview_pmx_structural_transform(source_a, intent_a)

        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(first.certificate.document, second.certificate.document)
        self.assertIs(first.source_document, source_a)
        self.assertIs(second.source_document, source_a)

    def test_structural_path_has_no_mutable_process_global_lookup_tables(self) -> None:
        self.assertFalse(
            hasattr(reference_queries_module, "_SOURCE_TARGET_OWNERS")
        )
        self.assertFalse(
            hasattr(structural_preview_module, "_TARGET_KIND_ORDER")
        )
        self.assertFalse(hasattr(services_public, "_STRUCTURAL_TARGET_RANK"))
        self.assertIsInstance(services_public._STRUCTURAL_TARGET_ORDER, tuple)

    def test_batch_helper_remains_internal(self) -> None:
        self.assertNotIn(
            "_analyze_reference_impacts",
            reference_queries_module.__all__,
        )
        self.assertFalse(hasattr(pmx_public, "_analyze_reference_impacts"))
        self.assertFalse(hasattr(services_public, "_analyze_reference_impacts"))


if __name__ == "__main__":
    unittest.main()
