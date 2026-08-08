"""Tests for deterministic PMX bone semantic resolution."""

from __future__ import annotations

import unittest

from mmd_registry.bone_semantic_resolver import (
    BoneSemanticResolver,
    resolve_bone_semantic,
    resolve_bone_semantics,
)
from mmd_registry.bone_semantics import (
    BoneSemanticAlias,
    BoneSemanticProfile,
)
from mmd_registry.model_scanning import (
    PmxBone,
    PmxIk,
)


def make_ik() -> PmxIk:
    """Build one small IK definition for semantic tests."""

    return PmxIk(
        target_bone_index=0,
        loop_count=1,
        angle_limit=0.5,
        links=(),
    )


def make_bone(
    *,
    local_name: str = "",
    universal_name: str = "",
    flag_names: tuple[str, ...] = (),
    ik: PmxIk | None = None,
) -> PmxBone:
    """Build one small scanner record for semantic resolver tests."""

    return PmxBone(
        local_name=local_name,
        universal_name=universal_name,
        position=(0.0, 0.0, 0.0),
        parent_bone_index=-1,
        transform_layer=0,
        flags=0,
        flag_names=flag_names,
        tail_mode="offset",
        tail_bone_index=None,
        tail_offset=(0.0, 1.0, 0.0),
        inherit_parent_bone_index=None,
        inherit_weight=None,
        fixed_axis=None,
        local_axis_x=None,
        local_axis_z=None,
        external_parent_key=None,
        ik=ik,
    )


class BoneSemanticResolverTests(unittest.TestCase):
    """Tests for conservative name and convention inference."""

    def test_empty_input_is_safe(self) -> None:
        self.assertEqual(
            resolve_bone_semantics(()),
            (),
        )

    def test_unnamed_bone_remains_unknown(self) -> None:
        result = resolve_bone_semantic(
            0,
            make_bone(),
        )

        self.assertEqual(result.role, "unknown")
        self.assertEqual(result.side, "none")
        self.assertEqual(result.category, "unknown")
        self.assertEqual(result.confidence, "unknown")
        self.assertEqual(result.evidence, ())

    def test_exact_standard_alias_can_be_high_confidence(self) -> None:
        result = resolve_bone_semantic(
            0,
            make_bone(local_name=" センター "),
        )

        self.assertEqual(result.role, "center")
        self.assertEqual(result.side, "center")
        self.assertEqual(result.category, "control")
        self.assertEqual(result.confidence, "high")
        self.assertEqual(result.evidence, ("local_name_alias",))

    def test_japanese_and_english_names_confirm_deform_role(self) -> None:
        result = resolve_bone_semantic(
            339,
            make_bone(
                local_name="左ひざＤ",
                universal_name="Bip001 L CalfD",
            ),
        )

        self.assertEqual(result.role, "knee_deform")
        self.assertEqual(result.side, "left")
        self.assertEqual(result.category, "deform")
        self.assertEqual(result.confidence, "high")
        self.assertEqual(
            result.evidence,
            (
                "local_name_alias",
                "universal_name_alias",
                "local_name_convention",
                "universal_name_convention",
                "side_marker",
            ),
        )
        self.assertEqual(
            result.matched_aliases,
            (
                "ひざ",
                "calf",
            ),
        )

    def test_full_width_japanese_ik_name_and_structure_agree(self) -> None:
        result = resolve_bone_semantic(
            6,
            make_bone(
                local_name="右つま先ＩＫ",
                flag_names=("ik",),
                ik=make_ik(),
            ),
        )

        self.assertEqual(result.role, "toe_ik")
        self.assertEqual(result.side, "right")
        self.assertEqual(result.category, "ik")
        self.assertEqual(result.confidence, "high")
        self.assertIn("local_name_alias", result.evidence)
        self.assertIn("side_marker", result.evidence)
        self.assertIn("bone_flags", result.evidence)
        self.assertIn("ik_definition", result.evidence)

    def test_english_camel_case_deform_suffix_is_supported(self) -> None:
        result = resolve_bone_semantic(
            10,
            make_bone(universal_name="Bip001 R FootD"),
        )

        self.assertEqual(result.role, "ankle_deform")
        self.assertEqual(result.side, "right")
        self.assertEqual(result.category, "deform")
        self.assertEqual(result.confidence, "medium")
        self.assertEqual(
            result.evidence,
            (
                "universal_name_alias",
                "universal_name_convention",
                "side_marker",
            ),
        )

    def test_helper_suffix_is_supported(self) -> None:
        result = resolve_bone_semantic(
            4,
            make_bone(universal_name="LeftArmHelper"),
        )

        self.assertEqual(result.role, "arm_helper")
        self.assertEqual(result.side, "left")
        self.assertEqual(result.category, "helper")
        self.assertEqual(result.confidence, "medium")

    def test_leg_ik_alias_outranks_generic_leg_alias(self) -> None:
        result = resolve_bone_semantic(
            7,
            make_bone(universal_name="Left_Leg-IK"),
        )

        self.assertEqual(result.role, "leg_ik")
        self.assertEqual(result.side, "left")
        self.assertEqual(result.category, "ik")
        self.assertEqual(result.confidence, "medium")
        self.assertEqual(result.matched_aliases, ("leg ik",))

    def test_local_and_universal_role_conflict_is_not_guessed(self) -> None:
        result = resolve_bone_semantic(
            12,
            make_bone(
                local_name="左ひざ",
                universal_name="Right Ankle",
            ),
        )

        self.assertEqual(result.role, "unknown")
        self.assertEqual(result.side, "none")
        self.assertEqual(result.category, "unknown")
        self.assertEqual(result.confidence, "low")
        self.assertIn("alias_conflict", result.evidence)
        self.assertIn("side_conflict", result.evidence)

    def test_ambiguous_custom_alias_is_not_guessed(self) -> None:
        profile = BoneSemanticProfile(
            name="ambiguous",
            aliases=(
                BoneSemanticAlias(
                    alias="joint",
                    role="knee",
                    category="deform",
                ),
                BoneSemanticAlias(
                    alias="joint",
                    role="ankle",
                    category="deform",
                ),
            ),
        )
        resolver = BoneSemanticResolver(profile=profile)

        result = resolver.resolve(
            0,
            make_bone(local_name="joint"),
        )

        self.assertEqual(result.role, "unknown")
        self.assertEqual(result.confidence, "low")
        self.assertEqual(result.evidence, ("local_name_alias", "alias_conflict"))

    def test_custom_profile_replaces_default_aliases(self) -> None:
        profile = BoneSemanticProfile(
            name="custom",
            aliases=(
                BoneSemanticAlias(
                    alias="custom joint",
                    role="wrist",
                    category="deform",
                    side="left",
                ),
            ),
        )
        resolver = BoneSemanticResolver(profile=profile)

        custom = resolver.resolve(
            0,
            make_bone(local_name="custom joint"),
        )
        standard = resolver.resolve(
            1,
            make_bone(local_name="センター"),
        )

        self.assertEqual(custom.role, "wrist")
        self.assertEqual(custom.side, "left")
        self.assertEqual(custom.confidence, "high")
        self.assertEqual(standard.role, "unknown")

    def test_ik_structure_without_name_evidence_stays_low_confidence(self) -> None:
        result = resolve_bone_semantic(
            20,
            make_bone(
                local_name="UnknownDriver",
                flag_names=("ik",),
                ik=make_ik(),
            ),
        )

        self.assertEqual(result.role, "unknown")
        self.assertEqual(result.category, "ik")
        self.assertEqual(result.confidence, "low")
        self.assertEqual(
            result.evidence,
            (
                "bone_flags",
                "ik_definition",
            ),
        )

    def test_weak_substrings_do_not_create_role_or_side_matches(self) -> None:
        result = resolve_bone_semantic(
            30,
            make_bone(universal_name="BrightArmature"),
        )

        self.assertEqual(result.role, "unknown")
        self.assertEqual(result.side, "none")
        self.assertEqual(result.confidence, "unknown")

    def test_conflicting_helper_and_deform_conventions_are_reported(self) -> None:
        result = resolve_bone_semantic(
            31,
            make_bone(universal_name="LeftArmHelperD"),
        )

        self.assertEqual(result.role, "arm")
        self.assertEqual(result.side, "left")
        self.assertEqual(result.category, "unknown")
        self.assertEqual(result.confidence, "low")
        self.assertIn("naming_conflict", result.evidence)

    def test_category_conflict_across_names_is_reported(self) -> None:
        profile = BoneSemanticProfile(
            name="category-conflict",
            aliases=(
                BoneSemanticAlias(
                    alias="local wrist",
                    role="wrist",
                    category="deform",
                ),
                BoneSemanticAlias(
                    alias="global wrist",
                    role="wrist",
                    category="helper",
                ),
            ),
        )
        resolver = BoneSemanticResolver(profile=profile)

        result = resolver.resolve(
            32,
            make_bone(
                local_name="local wrist",
                universal_name="global wrist",
            ),
        )

        self.assertEqual(result.role, "wrist")
        self.assertEqual(result.category, "unknown")
        self.assertEqual(result.confidence, "low")
        self.assertIn("category_conflict", result.evidence)

    def test_sequence_resolution_preserves_order_and_source_records(self) -> None:
        bones = (
            make_bone(local_name="センター"),
            make_bone(local_name="左ひざ"),
        )
        original_names = tuple(bone.local_name for bone in bones)

        results = resolve_bone_semantics(bones)

        self.assertEqual(
            tuple(result.index for result in results),
            (0, 1),
        )
        self.assertEqual(
            tuple(result.role for result in results),
            ("center", "knee"),
        )
        self.assertEqual(
            tuple(bone.local_name for bone in bones),
            original_names,
        )


if __name__ == "__main__":
    unittest.main()
