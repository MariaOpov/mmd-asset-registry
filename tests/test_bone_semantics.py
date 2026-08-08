"""Tests for the typed PMX bone semantic vocabulary."""

from __future__ import annotations

import json
import unittest
from dataclasses import FrozenInstanceError

from mmd_registry.bone_semantics import (
    DEFAULT_BONE_SEMANTIC_PROFILE,
    BoneSemanticAlias,
    BoneSemanticProfile,
    BoneSemanticResult,
    base_bone_semantic_role,
    build_unknown_bone_semantic,
    default_bone_category_for_role,
    order_bone_evidence,
    specialize_bone_semantic_role,
)
from mmd_registry.model_scanning import PmxBone


def make_bone(
    *,
    local_name: str = "Bone",
    universal_name: str = "",
) -> PmxBone:
    """Build one small scanner record for semantic tests."""

    return PmxBone(
        local_name=local_name,
        universal_name=universal_name,
        position=(0.0, 0.0, 0.0),
        parent_bone_index=-1,
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


class BoneSemanticVocabularyTests(unittest.TestCase):
    """Tests for immutable semantic records and alias profiles."""

    def test_unknown_result_preserves_original_names(self) -> None:
        bone = make_bone(
            local_name=" 左ひざＤ ",
            universal_name="Bip001 L CalfD",
        )

        result = build_unknown_bone_semantic(339, bone)

        self.assertEqual(result.index, 339)
        self.assertEqual(result.local_name, " 左ひざＤ ")
        self.assertEqual(result.universal_name, "Bip001 L CalfD")
        self.assertEqual(result.role, "unknown")
        self.assertEqual(result.side, "none")
        self.assertEqual(result.category, "unknown")
        self.assertEqual(result.confidence, "unknown")
        self.assertEqual(result.evidence, ())
        self.assertEqual(result.matched_aliases, ())

    def test_unnamed_bone_is_safe(self) -> None:
        result = build_unknown_bone_semantic(
            0,
            make_bone(
                local_name="",
                universal_name="",
            ),
        )

        self.assertEqual(result.local_name, "")
        self.assertEqual(result.universal_name, "")
        self.assertEqual(result.role, "unknown")

    def test_result_is_json_serializable(self) -> None:
        result = BoneSemanticResult(
            index=12,
            local_name="左ひざD",
            universal_name="Left Knee Deform",
            role="knee_deform",
            side="left",
            category="deform",
            confidence="high",
            evidence=(
                "universal_name_alias",
                "local_name_alias",
            ),
            matched_aliases=(
                "knee",
                "ひざ",
            ),
        )

        report = result.to_dict()
        encoded = json.dumps(
            report,
            ensure_ascii=False,
        )

        self.assertEqual(
            report["evidence"],
            [
                "universal_name_alias",
                "local_name_alias",
            ],
        )
        self.assertEqual(
            report["matched_aliases"],
            [
                "knee",
                "ひざ",
            ],
        )
        self.assertIn("左ひざD", encoded)

    def test_result_is_immutable(self) -> None:
        result = build_unknown_bone_semantic(
            0,
            make_bone(),
        )

        with self.assertRaises(FrozenInstanceError):
            result.role = "root"  # type: ignore[misc]

    def test_default_profile_has_bounded_cross_language_vocabulary(self) -> None:
        aliases = {
            alias.alias: alias for alias in DEFAULT_BONE_SEMANTIC_PROFILE.aliases
        }

        self.assertEqual(
            DEFAULT_BONE_SEMANTIC_PROFILE.name,
            "mmd-standard-v1",
        )
        self.assertEqual(aliases["全ての親"].role, "root")
        self.assertEqual(aliases["root"].role, "root")
        self.assertEqual(aliases["センター"].role, "center")
        self.assertEqual(aliases["center"].role, "center")
        self.assertEqual(aliases["ひざ"].role, "knee")
        self.assertEqual(aliases["knee"].role, "knee")
        self.assertEqual(aliases["足首"].role, "ankle")
        self.assertEqual(aliases["leg ik"].role, "leg_ik")
        self.assertLessEqual(
            len(DEFAULT_BONE_SEMANTIC_PROFILE.aliases),
            80,
        )

    def test_profile_can_be_replaced_without_mutating_default(self) -> None:
        original_aliases = DEFAULT_BONE_SEMANTIC_PROFILE.aliases
        custom_profile = BoneSemanticProfile(
            name="custom",
            aliases=(
                BoneSemanticAlias(
                    alias="custom root",
                    role="root",
                    category="control",
                    side="center",
                ),
            ),
        )

        self.assertEqual(
            custom_profile.aliases[0].alias,
            "custom root",
        )
        self.assertEqual(
            DEFAULT_BONE_SEMANTIC_PROFILE.aliases,
            original_aliases,
        )
        self.assertNotIn(
            custom_profile.aliases[0],
            DEFAULT_BONE_SEMANTIC_PROFILE.aliases,
        )

    def test_profile_is_json_serializable(self) -> None:
        report = DEFAULT_BONE_SEMANTIC_PROFILE.to_dict()

        json.dumps(
            report,
            ensure_ascii=False,
        )

        self.assertEqual(report["name"], "mmd-standard-v1")
        self.assertEqual(report["aliases"][0]["alias"], "全ての親")
        self.assertEqual(report["aliases"][0]["side"], "center")

    def test_role_variant_helpers_are_deterministic(self) -> None:
        self.assertEqual(
            specialize_bone_semantic_role(
                "knee",
                "deform",
            ),
            "knee_deform",
        )
        self.assertEqual(
            specialize_bone_semantic_role(
                "arm_deform",
                "helper",
            ),
            "arm_helper",
        )
        self.assertEqual(
            base_bone_semantic_role("wrist_helper"),
            "wrist",
        )
        self.assertEqual(
            default_bone_category_for_role("leg_ik"),
            "ik",
        )
        self.assertEqual(
            default_bone_category_for_role("head"),
            "deform",
        )

    def test_evidence_ordering_is_shared_and_stable(self) -> None:
        self.assertEqual(
            order_bone_evidence(
                (
                    "child_role",
                    "local_name_alias",
                    "hierarchy_side",
                    "child_role",
                    "parent_role",
                )
            ),
            (
                "local_name_alias",
                "parent_role",
                "child_role",
                "hierarchy_side",
            ),
        )


if __name__ == "__main__":
    unittest.main()
