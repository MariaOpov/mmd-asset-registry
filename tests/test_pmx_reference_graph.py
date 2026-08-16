"""End-to-end tests for deterministic PMX reference graph extraction."""

from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from pathlib import Path
import unittest

import mmd_registry.pmx as pmx
import mmd_registry.services as services
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.reference_graph import (
    PmxReferenceGraph,
    PmxReferenceTargetCounts,
    PmxReferenceUnsupportedStateKind,
    extract_pmx_reference_graph,
)
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from tests.mmd_fixtures import (
    build_pmx_bone,
    build_pmx_bone_morph_offset,
    build_pmx_display_frame,
    build_pmx_display_frame_element,
    build_pmx_flip_morph_offset,
    build_pmx_group_morph_offset,
    build_pmx_ik_link,
    build_pmx_impulse_morph_offset,
    build_pmx_joint,
    build_pmx_material,
    build_pmx_material_morph_offset,
    build_pmx_morph,
    build_pmx_rigid_body,
    build_pmx_soft_body,
    build_pmx_soft_body_anchor,
    build_pmx_structure,
    build_pmx_uv_morph_offset,
    build_pmx_vertex_morph_offset,
)


EXPECTED_RELATIONSHIP_IDS = frozenset(
    (
        "surface.vertex",
        "vertex.deform.bdef1.bone",
        "vertex.deform.multi.bone",
        "material.texture",
        "material.sphere_texture",
        "material.toon_texture",
        "bone.parent",
        "bone.tail",
        "bone.inherit_parent",
        "bone.ik_target",
        "bone.ik_link",
        "morph.group.morph",
        "morph.vertex.vertex",
        "morph.bone.bone",
        "morph.uv.vertex",
        "morph.material.material",
        "morph.flip.morph",
        "morph.impulse.rigid_body",
        "display_frame.bone",
        "display_frame.morph",
        "rigid_body.bone",
        "joint.rigid_body_a",
        "joint.rigid_body_b",
        "soft_body.material",
        "soft_body.anchor.rigid_body",
        "soft_body.anchor.vertex",
        "soft_body.pin.vertex",
    )
)


def _complete_reference_document():
    """Build and parse one PMX 2.1 fixture exercising all reference families."""

    ik_link = build_pmx_ik_link(bone_index=0)
    bone = build_pmx_bone(
        parent_bone_index=0,
        tail_bone_index=0,
        inherit_rotation=True,
        inherit_parent_bone_index=0,
        inherit_weight=0.5,
        ik_target_bone_index=0,
        ik_links=(ik_link,),
    )

    morph_offsets = (
        build_pmx_group_morph_offset(morph_index=0),
        build_pmx_vertex_morph_offset(vertex_index=0),
        build_pmx_bone_morph_offset(bone_index=0),
        build_pmx_uv_morph_offset(vertex_index=0),
        build_pmx_uv_morph_offset(vertex_index=1),
        build_pmx_uv_morph_offset(vertex_index=2),
        build_pmx_uv_morph_offset(vertex_index=3),
        build_pmx_uv_morph_offset(vertex_index=4),
        build_pmx_material_morph_offset(material_index=0),
        build_pmx_flip_morph_offset(morph_index=0),
        build_pmx_impulse_morph_offset(rigid_body_index=0),
    )
    morphs = tuple(
        build_pmx_morph(
            local_name=f"Morph {morph_type}",
            morph_type=morph_type,
            offsets=(morph_offsets[morph_type],),
        )
        for morph_type in range(11)
    )

    display_frame = build_pmx_display_frame(
        elements=(
            build_pmx_display_frame_element(target_type=0, target_index=0),
            build_pmx_display_frame_element(target_type=1, target_index=0),
        )
    )

    rigid_body = build_pmx_rigid_body(bone_index=0)
    joint = build_pmx_joint(
        rigid_body_a_index=0,
        rigid_body_b_index=0,
    )
    anchor = build_pmx_soft_body_anchor(
        rigid_body_index=0,
        vertex_index=0,
    )
    soft_body = build_pmx_soft_body(
        material_index=0,
        anchors=(anchor,),
        pinned_vertex_indices=(0,),
    )

    payload = build_pmx_structure(
        version=2.1,
        additional_uv_count=4,
        deform_types=(0, 1, 2, 3, 4),
        surface_indices=(0, 1, 2),
        texture_paths=("texture.png",),
        materials=(
            build_pmx_material(
                texture_index=0,
                sphere_texture_index=0,
                toon_reference_mode=0,
                toon_reference_index=0,
                surface_index_count=3,
            ),
        ),
        bones=(bone,),
        morphs=morphs,
        display_frames=(display_frame,),
        rigid_bodies=(rigid_body,),
        joints=(joint,),
        soft_bodies=(soft_body,),
    )
    return load_pmx(BytesIO(payload))


class PmxReferenceGraphExtractionTests(unittest.TestCase):
    """Exercise all CP03 relationships through the real PMX reader."""

    def test_complete_fixture_extracts_all_27_relationship_families(self) -> None:
        document = _complete_reference_document()
        graph = extract_pmx_reference_graph(document)

        self.assertEqual(len(graph.edges), 44)
        self.assertEqual(
            frozenset(edge.relationship_id for edge in graph.edges),
            EXPECTED_RELATIONSHIP_IDS,
        )
        self.assertEqual(graph.invalid_targets, ())
        self.assertEqual(graph.unsupported_states, ())
        self.assertEqual(
            graph.target_counts,
            PmxReferenceTargetCounts(
                vertex=5,
                texture=1,
                material=1,
                bone=1,
                morph=11,
                rigid_body=1,
            ),
        )

    def test_extraction_is_deterministic_immutable_and_read_only(self) -> None:
        document = _complete_reference_document()
        before = document

        first = extract_pmx_reference_graph(document)
        second = extract_pmx_reference_graph(document)

        self.assertEqual(first, second)
        self.assertEqual(hash(first), hash(second))
        self.assertEqual(document, before)
        self.assertEqual(
            tuple(edge.source.path for edge in first.edges[:4]),
            (
                "surface_indices[0]",
                "surface_indices[1]",
                "surface_indices[2]",
                "vertices[0].deform.bone_index",
            ),
        )

    def test_optional_sentinels_and_shared_toon_are_no_edge_states(self) -> None:
        document = _complete_reference_document()
        material = replace(
            document.materials[0],
            texture_index=-1,
            sphere_texture_index=-1,
            toon_reference_mode="shared",
            toon_reference_index=7,
        )
        document = replace(document, materials=(material,))

        graph = extract_pmx_reference_graph(document)
        material_ids = {
            edge.relationship_id
            for edge in graph.edges
            if edge.source.section.value == "materials"
        }

        self.assertEqual(material_ids, set())
        self.assertFalse(
            any(
                item.source.section.value == "materials"
                for item in graph.invalid_targets
            )
        )

    def test_invalid_positive_and_required_negative_targets_are_preserved(self) -> None:
        document = _complete_reference_document()
        geometry = replace(
            document.geometry,
            surface_indices=(999, 1, 2),
        )
        frame = document.display_frames[0]
        invalid_element = replace(frame.elements[0], target_index=-1)
        frame = replace(
            frame,
            elements=(invalid_element, frame.elements[1]),
        )
        document = replace(
            document,
            geometry=geometry,
            display_frames=(frame,),
        )

        graph = extract_pmx_reference_graph(document)
        evidence = {
            (
                item.relationship_id,
                item.source.path,
                item.raw_index,
                item.target_kind,
                item.target_count,
            )
            for item in graph.invalid_targets
        }

        self.assertIn(
            (
                "surface.vertex",
                "surface_indices[0]",
                999,
                PmxReferenceTargetKind.VERTEX,
                5,
            ),
            evidence,
        )
        self.assertIn(
            (
                "display_frame.bone",
                "display_frames[0].elements[0].target_index",
                -1,
                PmxReferenceTargetKind.BONE,
                1,
            ),
            evidence,
        )
        emitted_paths = {edge.source.path for edge in graph.edges}
        self.assertNotIn("surface_indices[0]", emitted_paths)
        self.assertNotIn(
            "display_frames[0].elements[0].target_index",
            emitted_paths,
        )

    def test_morph_variant_mismatch_is_evidence_not_a_crash(self) -> None:
        document = _complete_reference_document()
        group_morph = document.morphs[0]
        vertex_offset = document.morphs[1].offsets[0]
        group_morph = replace(group_morph, offsets=(vertex_offset,))
        document = replace(
            document,
            morphs=(group_morph, *document.morphs[1:]),
        )

        graph = extract_pmx_reference_graph(document)

        self.assertTrue(
            any(
                state.kind
                is PmxReferenceUnsupportedStateKind.MORPH_OFFSET_TYPE_MISMATCH
                and state.relationship_id == "morph.group.morph"
                and state.source.path == "morphs[0].offsets[0]"
                for state in graph.unsupported_states
            )
        )

    def test_version_and_uv_layer_conditions_are_evidence_not_edges(self) -> None:
        document = _complete_reference_document()
        header = replace(
            document.header,
            version=2.0,
            additional_uv_count=0,
        )
        document = replace(document, header=header)

        graph = extract_pmx_reference_graph(document)
        unsupported_relationships = {
            state.relationship_id for state in graph.unsupported_states
        }

        self.assertIn("vertex.deform.multi.bone", unsupported_relationships)
        self.assertIn("morph.uv.vertex", unsupported_relationships)
        self.assertIn("morph.flip.morph", unsupported_relationships)
        self.assertIn("morph.impulse.rigid_body", unsupported_relationships)
        self.assertIn("soft_body.material", unsupported_relationships)
        self.assertIn("soft_body.anchor.rigid_body", unsupported_relationships)
        self.assertIn("soft_body.anchor.vertex", unsupported_relationships)
        self.assertIn("soft_body.pin.vertex", unsupported_relationships)

    def test_nonzero_joint_type_on_pmx20_preserves_version_evidence_and_edges(
        self,
    ) -> None:
        document = _complete_reference_document()
        header = replace(document.header, version=2.0)
        joint = replace(document.joints[0], joint_type=1)
        document = replace(
            document,
            header=header,
            joints=(joint,),
            soft_bodies=(),
        )

        graph = extract_pmx_reference_graph(document)
        joint_states = {
            (
                state.kind,
                state.relationship_id,
                state.source.path,
                state.observed,
            )
            for state in graph.unsupported_states
            if state.source.section.value == "joints"
        }

        self.assertEqual(
            joint_states,
            {
                (
                    PmxReferenceUnsupportedStateKind.VERSION_CONDITION_MISMATCH,
                    "joint.rigid_body_a",
                    "joints[0].rigid_body_a_index",
                    "pmx_version=2.0;joint_type=1",
                ),
                (
                    PmxReferenceUnsupportedStateKind.VERSION_CONDITION_MISMATCH,
                    "joint.rigid_body_b",
                    "joints[0].rigid_body_b_index",
                    "pmx_version=2.0;joint_type=1",
                ),
            },
        )
        emitted = {
            edge.relationship_id
            for edge in graph.edges
            if edge.source.section.value == "joints"
        }
        self.assertEqual(
            emitted,
            {"joint.rigid_body_a", "joint.rigid_body_b"},
        )

    def test_inconsistent_bone_flag_payloads_are_preserved_as_raw_evidence(self) -> None:
        document = _complete_reference_document()
        bone = document.bones[0]
        bone = replace(
            bone,
            flags=0,
            tail_bone_index=0,
            inherit_parent_bone_index=0,
            ik=bone.ik,
        )
        document = replace(document, bones=(bone,))

        graph = extract_pmx_reference_graph(document)

        observed = {
            (state.kind, state.relationship_id)
            for state in graph.unsupported_states
        }
        self.assertIn(
            (
                PmxReferenceUnsupportedStateKind.INACTIVE_PAYLOAD_PRESENT,
                "bone.tail",
            ),
            observed,
        )
        self.assertIn(
            (
                PmxReferenceUnsupportedStateKind.INACTIVE_PAYLOAD_PRESENT,
                "bone.inherit_parent",
            ),
            observed,
        )
        self.assertIn(
            (
                PmxReferenceUnsupportedStateKind.INACTIVE_PAYLOAD_PRESENT,
                "bone.ik_target",
            ),
            observed,
        )

    def test_missing_active_bone_payload_is_preserved_as_raw_evidence(self) -> None:
        document = _complete_reference_document()
        bone = replace(
            document.bones[0],
            tail_bone_index=None,
            inherit_parent_bone_index=None,
            ik=None,
        )
        document = replace(document, bones=(bone,))

        graph = extract_pmx_reference_graph(document)

        observed = {
            (state.kind, state.relationship_id)
            for state in graph.unsupported_states
        }
        self.assertIn(
            (
                PmxReferenceUnsupportedStateKind.ACTIVE_PAYLOAD_MISSING,
                "bone.tail",
            ),
            observed,
        )
        self.assertIn(
            (
                PmxReferenceUnsupportedStateKind.ACTIVE_PAYLOAD_MISSING,
                "bone.inherit_parent",
            ),
            observed,
        )
        self.assertIn(
            (
                PmxReferenceUnsupportedStateKind.ACTIVE_PAYLOAD_MISSING,
                "bone.ik_target",
            ),
            observed,
        )

    def test_trailing_data_is_opaque_and_does_not_create_guessed_edges(self) -> None:
        document = _complete_reference_document()
        baseline = extract_pmx_reference_graph(document)
        with_trailing = replace(document, trailing_data=b"\xff\x00opaque")

        self.assertEqual(
            extract_pmx_reference_graph(with_trailing),
            baseline,
        )

    def test_empty_document_has_zero_counts_and_no_evidence(self) -> None:
        document = load_pmx(
            BytesIO(
                build_pmx_structure(
                    version=2.1,
                    deform_types=(),
                    surface_indices=(),
                    materials=(),
                )
            )
        )

        graph = extract_pmx_reference_graph(document)

        self.assertEqual(
            graph,
            PmxReferenceGraph(
                target_counts=PmxReferenceTargetCounts(
                    vertex=0,
                    texture=0,
                    material=0,
                    bone=0,
                    morph=0,
                    rigid_body=0,
                ),
                edges=(),
                invalid_targets=(),
                unsupported_states=(),
            ),
        )

    def test_target_count_lookup_is_typed(self) -> None:
        counts = PmxReferenceTargetCounts(1, 2, 3, 4, 5, 6)

        self.assertEqual(counts.count_for(PmxReferenceTargetKind.MORPH), 5)
        with self.assertRaises(TypeError):
            counts.count_for("morph")  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            PmxReferenceTargetCounts(True, 0, 0, 0, 0, 0)
        with self.assertRaises(ValueError):
            PmxReferenceTargetCounts(-1, 0, 0, 0, 0, 0)

    def test_graph_rejects_untyped_inputs_and_package_exports_remain_frozen(
        self,
    ) -> None:
        with self.assertRaises(TypeError):
            extract_pmx_reference_graph(object())  # type: ignore[arg-type]

        self.assertNotIn("extract_pmx_reference_graph", pmx.__all__)
        self.assertNotIn("extract_pmx_reference_graph", services.__all__)

    def test_extractor_does_not_prevalidate_or_access_filesystem(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "mmd_registry"
            / "pmx"
            / "reference_graph.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("validate_pmx_document", source)
        self.assertNotIn("Path(", source)
        self.assertNotIn(".open(", source)
        self.assertNotIn("sys.exit", source)
        self.assertNotIn("print(", source)


if __name__ == "__main__":
    unittest.main()
