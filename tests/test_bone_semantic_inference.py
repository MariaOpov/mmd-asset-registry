"""Tests for hierarchy-aware PMX bone semantic inference."""

from __future__ import annotations

import unittest

from mmd_registry.bone_semantic_inference import infer_bone_semantics
from mmd_registry.model_scanning import PmxBone


def make_bone(
    *,
    local_name: str = "",
    universal_name: str = "",
    parent_index: int = -1,
) -> PmxBone:
    """Build one small scanner record for hierarchy inference tests."""

    return PmxBone(
        local_name=local_name,
        universal_name=universal_name,
        position=(0.0, 0.0, 0.0),
        parent_bone_index=parent_index,
        transform_layer=0,
        flags=0,
        flag_names=(),
        tail_mode="offset",
        tail_bone_index=None,
        tail_offset=(0.0, 1.0, 0.0),
        inherit_parent_bone_index=None,
        inherit_weight=None,
        fixed_axis=None,
        local_axis_x=None,
        local_axis_z=None,
        external_parent_key=None,
        ik=None,
    )


class BoneSemanticInferenceTests(unittest.TestCase):
    """Tests for conservative, non-recursive hierarchy refinement."""

    def test_empty_input_is_safe(self) -> None:
        self.assertEqual(
            infer_bone_semantics(()),
            (),
        )

    def test_parent_and_child_roles_infer_one_missing_knee(self) -> None:
        results = infer_bone_semantics(
            (
                make_bone(universal_name="Left Thigh"),
                make_bone(parent_index=0),
                make_bone(
                    universal_name="Left Ankle",
                    parent_index=1,
                ),
            )
        )
        inferred = results[1]

        self.assertEqual(inferred.role, "knee")
        self.assertEqual(inferred.side, "left")
        self.assertEqual(inferred.category, "deform")
        self.assertEqual(inferred.confidence, "medium")
        self.assertEqual(
            inferred.evidence,
            (
                "parent_role",
                "child_role",
                "hierarchy_side",
            ),
        )

    def test_name_convention_is_preserved_during_role_inference(self) -> None:
        results = infer_bone_semantics(
            (
                make_bone(universal_name="Left Thigh"),
                make_bone(
                    universal_name="MysteryD",
                    parent_index=0,
                ),
                make_bone(
                    universal_name="Left Ankle",
                    parent_index=1,
                ),
            )
        )
        inferred = results[1]

        self.assertEqual(inferred.role, "knee_deform")
        self.assertEqual(inferred.side, "left")
        self.assertEqual(inferred.category, "deform")
        self.assertEqual(inferred.confidence, "medium")
        self.assertIn("universal_name_convention", inferred.evidence)
        self.assertIn("parent_role", inferred.evidence)
        self.assertIn("child_role", inferred.evidence)

    def test_one_sided_parent_inference_remains_low_confidence(self) -> None:
        results = infer_bone_semantics(
            (
                make_bone(universal_name="Left Arm"),
                make_bone(parent_index=0),
            )
        )
        inferred = results[1]

        self.assertEqual(inferred.role, "elbow")
        self.assertEqual(inferred.side, "left")
        self.assertEqual(inferred.confidence, "low")
        self.assertIn("parent_role", inferred.evidence)
        self.assertNotIn("child_role", inferred.evidence)

    def test_helper_is_not_inferred_from_one_sided_context(self) -> None:
        results = infer_bone_semantics(
            (
                make_bone(universal_name="Left Arm"),
                make_bone(
                    universal_name="MysteryHelper",
                    parent_index=0,
                ),
            )
        )
        helper = results[1]

        self.assertEqual(helper.role, "unknown")
        self.assertEqual(helper.category, "helper")
        self.assertEqual(helper.confidence, "low")
        self.assertNotIn("parent_role", helper.evidence)

    def test_hierarchy_support_strengthens_a_named_role(self) -> None:
        results = infer_bone_semantics(
            (
                make_bone(universal_name="Left Thigh"),
                make_bone(
                    universal_name="Left Knee",
                    parent_index=0,
                ),
                make_bone(
                    universal_name="Left Ankle",
                    parent_index=1,
                ),
            )
        )
        knee = results[1]

        self.assertEqual(knee.role, "knee")
        self.assertEqual(knee.confidence, "high")
        self.assertIn("universal_name_alias", knee.evidence)
        self.assertIn("parent_role", knee.evidence)
        self.assertIn("child_role", knee.evidence)
        self.assertIn("hierarchy_side", knee.evidence)

    def test_hierarchy_does_not_overwrite_exact_conflicting_name(self) -> None:
        results = infer_bone_semantics(
            (
                make_bone(universal_name="Left Thigh"),
                make_bone(
                    local_name="センター",
                    parent_index=0,
                ),
                make_bone(
                    universal_name="Left Ankle",
                    parent_index=1,
                ),
            )
        )
        center = results[1]

        self.assertEqual(center.role, "center")
        self.assertEqual(center.side, "center")
        self.assertEqual(center.confidence, "high")
        self.assertNotIn("parent_role", center.evidence)
        self.assertNotIn("child_role", center.evidence)

    def test_fixed_point_inference_handles_multiple_missing_chain_roles(self) -> None:
        results = infer_bone_semantics(
            (
                make_bone(universal_name="Left Shoulder"),
                make_bone(parent_index=0),
                make_bone(parent_index=1),
                make_bone(
                    universal_name="Left Wrist",
                    parent_index=2,
                ),
            )
        )

        self.assertEqual(results[1].role, "arm")
        self.assertEqual(results[2].role, "elbow")
        self.assertEqual(results[1].side, "left")
        self.assertEqual(results[2].side, "left")
        self.assertEqual(results[1].confidence, "medium")
        self.assertEqual(results[2].confidence, "medium")
        self.assertIn("parent_role", results[1].evidence)
        self.assertIn("child_role", results[1].evidence)
        self.assertIn("parent_role", results[2].evidence)
        self.assertIn("child_role", results[2].evidence)

    def test_invalid_parent_is_safe_and_does_not_create_evidence(self) -> None:
        result = infer_bone_semantics(
            (
                make_bone(
                    universal_name="Mystery",
                    parent_index=99,
                ),
            )
        )[0]

        self.assertEqual(result.role, "unknown")
        self.assertEqual(result.evidence, ())

    def test_cycle_is_safe_and_does_not_require_recursion(self) -> None:
        results = infer_bone_semantics(
            (
                make_bone(
                    universal_name="Left Arm",
                    parent_index=1,
                ),
                make_bone(
                    universal_name="Left Wrist",
                    parent_index=0,
                ),
            )
        )

        self.assertEqual(
            tuple(result.role for result in results),
            ("arm", "wrist"),
        )
        self.assertNotIn("parent_role", results[0].evidence)
        self.assertNotIn("parent_role", results[1].evidence)

    def test_deep_hierarchy_is_non_recursive_and_preserves_input(self) -> None:
        bones = tuple(
            make_bone(
                universal_name=f"Unknown {index}",
                parent_index=(-1 if index == 0 else index - 1),
            )
            for index in range(1500)
        )
        original_names = tuple(bone.universal_name for bone in bones)

        results = infer_bone_semantics(bones)

        self.assertEqual(len(results), 1500)
        self.assertTrue(all(result.role == "unknown" for result in results))
        self.assertEqual(
            tuple(bone.universal_name for bone in bones),
            original_names,
        )


if __name__ == "__main__":
    unittest.main()
