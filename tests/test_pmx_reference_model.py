"""Tests for the immutable PMX reference identity foundation."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

import mmd_registry.pmx as pmx
from mmd_registry.pmx.reference_model import (
    PmxReferenceEdge,
    PmxReferenceNode,
    PmxReferenceSourceLocation,
    PmxReferenceSourceSection,
    PmxReferenceTargetKind,
)


class PmxReferenceModelTests(unittest.TestCase):
    """Keep CP04 small, typed, immutable, and free of graph behavior."""

    def test_target_kind_matches_the_six_cp03_global_targets(self) -> None:
        self.assertEqual(
            tuple(kind.value for kind in PmxReferenceTargetKind),
            (
                "vertex",
                "texture",
                "material",
                "bone",
                "morph",
                "rigid_body",
            ),
        )

    def test_source_section_matches_every_cp03_reference_owner_section(self) -> None:
        self.assertEqual(
            tuple(section.value for section in PmxReferenceSourceSection),
            (
                "surface_indices",
                "vertices",
                "materials",
                "bones",
                "morphs",
                "display_frames",
                "rigid_bodies",
                "joints",
                "soft_bodies",
            ),
        )

    def test_node_is_immutable_hashable_and_keeps_unbounded_positive_identity(
        self,
    ) -> None:
        node = PmxReferenceNode(PmxReferenceTargetKind.BONE, 999_999)

        self.assertEqual(
            node,
            PmxReferenceNode(PmxReferenceTargetKind.BONE, 999_999),
        )
        self.assertEqual(len({node, node}), 1)
        with self.assertRaises(FrozenInstanceError):
            node.index = 1  # type: ignore[misc]

    def test_node_rejects_untyped_boolean_and_negative_indices(self) -> None:
        with self.assertRaises(TypeError):
            PmxReferenceNode("bone", 0)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            PmxReferenceNode(PmxReferenceTargetKind.BONE, True)
        with self.assertRaises(ValueError):
            PmxReferenceNode(PmxReferenceTargetKind.BONE, -1)

    def test_source_location_is_concrete_immutable_and_hashable(self) -> None:
        source = PmxReferenceSourceLocation(
            section=PmxReferenceSourceSection.BONES,
            record_index=4,
            path="bones[4].ik.links[2].bone_index",
        )

        self.assertEqual(
            source,
            PmxReferenceSourceLocation(
                section=PmxReferenceSourceSection.BONES,
                record_index=4,
                path="bones[4].ik.links[2].bone_index",
            ),
        )
        self.assertEqual(len({source, source}), 1)
        with self.assertRaises(FrozenInstanceError):
            source.path = "bones[4].parent_bone_index"  # type: ignore[misc]

    def test_source_location_rejects_ambiguous_or_mismatched_paths(self) -> None:
        valid_section = PmxReferenceSourceSection.MORPHS
        invalid_cases = (
            {"section": "morphs", "record_index": 0, "path": "morphs[0]"},
            {"section": valid_section, "record_index": True, "path": "morphs[1]"},
            {"section": valid_section, "record_index": -1, "path": "morphs[0]"},
            {"section": valid_section, "record_index": 0, "path": ""},
            {"section": valid_section, "record_index": 0, "path": "morphs[*]"},
            {"section": valid_section, "record_index": 0, "path": "bones[0]"},
        )

        for arguments in invalid_cases:
            with self.subTest(arguments=arguments):
                with self.assertRaises((TypeError, ValueError)):
                    PmxReferenceSourceLocation(**arguments)  # type: ignore[arg-type]

    def test_edge_is_immutable_hashable_and_supports_self_reference(self) -> None:
        source = PmxReferenceSourceLocation(
            PmxReferenceSourceSection.BONES,
            3,
            "bones[3].parent_bone_index",
        )
        target = PmxReferenceNode(PmxReferenceTargetKind.BONE, 3)
        edge = PmxReferenceEdge("bone.parent", source, target)

        self.assertEqual(edge.target.index, edge.source.record_index)
        self.assertEqual(len({edge, edge}), 1)
        with self.assertRaises(FrozenInstanceError):
            edge.relationship_id = "bone.tail"  # type: ignore[misc]

    def test_edge_rejects_unstable_identifier_or_untyped_components(self) -> None:
        source = PmxReferenceSourceLocation(
            PmxReferenceSourceSection.MATERIALS,
            0,
            "materials[0].texture_index",
        )
        target = PmxReferenceNode(PmxReferenceTargetKind.TEXTURE, 0)

        for relationship_id in ("", "Material.Texture", "material texture", "material"):
            with self.subTest(relationship_id=relationship_id):
                with self.assertRaises(ValueError):
                    PmxReferenceEdge(relationship_id, source, target)

        with self.assertRaises(TypeError):
            PmxReferenceEdge("material.texture", object(), target)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            PmxReferenceEdge("material.texture", source, object())  # type: ignore[arg-type]

    def test_reference_foundation_does_not_expand_existing_pmx_public_exports(
        self,
    ) -> None:
        for name in (
            "PmxReferenceEdge",
            "PmxReferenceNode",
            "PmxReferenceSourceLocation",
            "PmxReferenceSourceSection",
            "PmxReferenceTargetKind",
        ):
            with self.subTest(name=name):
                self.assertNotIn(name, pmx.__all__)


if __name__ == "__main__":
    unittest.main()
