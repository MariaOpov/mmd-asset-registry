"""Tests for complete PMX rig reports and semantic bone maps."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
import unittest

from mmd_registry.bone_semantic_inference import infer_bone_semantics
from mmd_registry.bone_semantic_resolver import BoneSemanticResolver
from mmd_registry.bone_semantics import (
    BoneSemanticAlias,
    BoneSemanticProfile,
)
from mmd_registry.model_scanning import PmxBone, PmxIk, PmxIkLink
from mmd_registry.rig_analysis import (
    BONE_MAP_SCHEMA_VERSION,
    RIG_ANALYSIS_SCHEMA_VERSION,
    analyze_rig,
    canonical_bone_map_key,
)
from mmd_registry.rig_diagnostics import (
    RigDiagnosticProfile,
    diagnose_resolved_rig,
    diagnose_rig,
)


def make_link(bone_index: int) -> PmxIkLink:
    """Build one small IK link scanner record."""

    return PmxIkLink(
        bone_index=bone_index,
        angle_limits_enabled=False,
        lower_limit=None,
        upper_limit=None,
    )


def make_ik(
    *,
    target_index: int,
    link_indices: tuple[int, ...] = (),
) -> PmxIk:
    """Build one small IK scanner record."""

    return PmxIk(
        target_bone_index=target_index,
        loop_count=40,
        angle_limit=1.0,
        links=tuple(make_link(index) for index in link_indices),
    )


def make_bone(
    *,
    local_name: str = "",
    universal_name: str = "",
    parent_index: int = -1,
    ik: PmxIk | None = None,
) -> PmxBone:
    """Build one small scanner record for rig analysis tests."""

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
        ik=ik,
    )


def empty_diagnostic_profile(
    name: str = "empty-policy",
) -> RigDiagnosticProfile:
    """Return a diagnostic policy without expected or paired roles."""

    return RigDiagnosticProfile(
        name=name,
        required_roles=(),
        paired_roles=(),
        duplicate_exempt_roles=(),
    )


def minimal_standard_rig() -> tuple[PmxBone, ...]:
    """Return the bounded set of roles required by the default profile."""

    return (
        make_bone(universal_name="Center"),
        make_bone(
            universal_name="Lower Body",
            parent_index=0,
        ),
        make_bone(
            universal_name="Upper Body",
            parent_index=0,
        ),
        make_bone(
            universal_name="Neck",
            parent_index=2,
        ),
        make_bone(
            universal_name="Head",
            parent_index=3,
        ),
    )


class RigAnalysisTests(unittest.TestCase):
    """Tests for stable complete reports and duplicate-safe maps."""

    def test_empty_input_has_stable_complete_schema(self) -> None:
        report = analyze_rig(())
        payload = report.to_dict()

        self.assertEqual(report.schema_version, RIG_ANALYSIS_SCHEMA_VERSION)
        self.assertEqual(report.bone_map.schema_version, BONE_MAP_SCHEMA_VERSION)
        self.assertEqual(report.status, "warning")
        self.assertEqual(report.summary.bone_count, 0)
        self.assertEqual(report.summary.resolved_bone_count, 0)
        self.assertEqual(report.summary.unresolved_bone_count, 0)
        self.assertEqual(report.summary.warning_count, 5)
        self.assertEqual(report.bone_map.role_index, {})
        self.assertEqual(
            tuple(payload),
            (
                "schema_version",
                "status",
                "semantic_profile_name",
                "diagnostic_profile_name",
                "summary",
                "bones",
                "diagnostics",
                "bone_map",
            ),
        )
        json.dumps(payload, ensure_ascii=False)

    def test_minimal_standard_rig_produces_clean_report(self) -> None:
        report = analyze_rig(minimal_standard_rig())

        self.assertEqual(report.status, "ok")
        self.assertEqual(report.diagnostics.issues, ())
        self.assertEqual(report.summary.bone_count, 5)
        self.assertEqual(report.summary.resolved_bone_count, 5)
        self.assertEqual(report.summary.unresolved_bone_count, 0)
        self.assertEqual(report.summary.mapped_role_count, 5)
        self.assertEqual(
            report.bone_map.role_index,
            {
                "center": [0],
                "head": [4],
                "lower_body": [1],
                "neck": [3],
                "upper_body": [2],
            },
        )

    def test_canonical_keys_use_side_and_collapse_role_variants(self) -> None:
        self.assertEqual(
            canonical_bone_map_key("knee_deform", "left"),
            "left_knee",
        )
        self.assertEqual(
            canonical_bone_map_key("arm_helper", "right"),
            "right_arm",
        )
        self.assertEqual(
            canonical_bone_map_key("head", "center"),
            "head",
        )
        self.assertIsNone(canonical_bone_map_key("unknown", "none"))

    def test_mixed_results_have_complete_stable_counts(self) -> None:
        report = analyze_rig(
            (
                make_bone(universal_name="Left Knee D"),
                make_bone(universal_name="Mystery Joint"),
                make_bone(universal_name="Center"),
            ),
            diagnostic_profile=empty_diagnostic_profile(),
        )
        summary = report.summary.to_dict()

        self.assertEqual(report.summary.resolved_bone_count, 2)
        self.assertEqual(report.summary.unresolved_bone_count, 1)
        self.assertEqual(
            report.bone_map.role_index,
            {
                "center": [2],
                "left_knee": [0],
            },
        )
        self.assertEqual(report.bone_map.unmapped_indices, (1,))
        self.assertEqual(
            summary["category_counts"],
            {
                "control": 1,
                "deform": 1,
                "helper": 0,
                "ik": 0,
                "physics": 0,
                "unknown": 1,
            },
        )
        self.assertEqual(
            summary["side_counts"],
            {
                "left": 1,
                "right": 0,
                "center": 1,
                "none": 1,
            },
        )

    def test_duplicate_role_map_preserves_every_matching_index(self) -> None:
        report = analyze_rig(
            (
                make_bone(universal_name="Left Knee D"),
                make_bone(universal_name="Left Knee"),
            ),
            diagnostic_profile=empty_diagnostic_profile(),
        )

        self.assertEqual(
            report.bone_map.role_index,
            {"left_knee": [0, 1]},
        )
        self.assertEqual(report.bone_map.mapped_count, 2)
        self.assertEqual(len(report.bone_map.entries), 2)
        self.assertIn(
            "duplicate_semantic_role",
            tuple(issue.code for issue in report.diagnostics.issues),
        )

    def test_bone_map_preserves_names_roles_and_source_order(self) -> None:
        bones = (
            make_bone(
                local_name="左ひざ",
                universal_name="Left Knee",
            ),
            make_bone(
                local_name="右ひざ",
                universal_name="Right Knee",
            ),
        )

        report = analyze_rig(
            bones,
            diagnostic_profile=empty_diagnostic_profile(),
        )
        entries = report.bone_map.entries

        self.assertEqual(
            tuple(entry.index for entry in entries),
            (0, 1),
        )
        self.assertEqual(entries[0].local_name, "左ひざ")
        self.assertEqual(entries[1].universal_name, "Right Knee")
        self.assertEqual(entries[0].role, "knee")
        self.assertEqual(entries[0].base_role, "knee")

    def test_custom_semantic_and_diagnostic_profiles_are_recorded(self) -> None:
        resolver = BoneSemanticResolver(
            BoneSemanticProfile(
                name="custom-semantic-profile",
                aliases=(
                    BoneSemanticAlias(
                        alias="Custom Joint",
                        role="arm",
                        category="deform",
                        side="right",
                    ),
                ),
            )
        )
        diagnostic_profile = empty_diagnostic_profile("custom-diagnostic-profile")

        report = analyze_rig(
            (make_bone(universal_name="Custom Joint"),),
            resolver=resolver,
            diagnostic_profile=diagnostic_profile,
        )

        self.assertEqual(
            report.semantic_profile_name,
            "custom-semantic-profile",
        )
        self.assertEqual(
            report.diagnostic_profile_name,
            "custom-diagnostic-profile",
        )
        self.assertEqual(
            report.bone_map.profile_name,
            "custom-semantic-profile",
        )
        self.assertEqual(
            report.bone_map.role_index,
            {"right_arm": [0]},
        )

    def test_precomputed_diagnostics_match_direct_diagnostics(self) -> None:
        bones = (
            make_bone(universal_name="Center"),
            make_bone(universal_name="Mystery Joint"),
        )
        profile = empty_diagnostic_profile()
        semantics = infer_bone_semantics(bones)

        precomputed = diagnose_resolved_rig(
            bones,
            semantics,
            profile=profile,
        )
        direct = diagnose_rig(
            bones,
            profile=profile,
        )

        self.assertEqual(precomputed, direct)

    def test_mismatched_precomputed_semantics_are_rejected(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "exactly one result",
        ):
            diagnose_resolved_rig(
                (make_bone(universal_name="Center"),),
                (),
                profile=empty_diagnostic_profile(),
            )

    def test_report_models_are_immutable(self) -> None:
        report = analyze_rig(minimal_standard_rig())

        with self.assertRaises(FrozenInstanceError):
            report.schema_version = "changed"

        with self.assertRaises(FrozenInstanceError):
            report.summary.bone_count = 0

        with self.assertRaises(FrozenInstanceError):
            report.bone_map.entries[0].key = "changed"

        first_index = report.bone_map.role_index
        first_index["center"].append(99)
        self.assertEqual(report.bone_map.role_index["center"], [0])

    def test_embedded_diagnostics_and_summary_counts_agree(self) -> None:
        report = analyze_rig(
            (make_bone(universal_name="Mystery Joint"),),
            diagnostic_profile=empty_diagnostic_profile(),
        )

        self.assertEqual(
            report.summary.diagnostic_count,
            len(report.diagnostics.issues),
        )
        self.assertEqual(
            report.summary.to_dict()["severity_counts"],
            report.diagnostics.severity_counts,
        )

    def test_invalid_ik_references_produce_error_status(self) -> None:
        report = analyze_rig(
            (
                make_bone(
                    universal_name="Left Leg IK",
                    ik=make_ik(
                        target_index=99,
                        link_indices=(88,),
                    ),
                ),
            ),
            diagnostic_profile=empty_diagnostic_profile(),
        )

        self.assertEqual(report.status, "error")
        self.assertEqual(report.summary.error_count, 2)
        self.assertEqual(
            report.to_dict()["diagnostics"]["status"],
            "error",
        )

    def test_deep_hierarchy_is_non_recursive_and_does_not_mutate_input(
        self,
    ) -> None:
        bones = tuple(
            make_bone(
                universal_name=f"Mystery {index}",
                parent_index=(-1 if index == 0 else index - 1),
            )
            for index in range(1500)
        )
        original_names = tuple(bone.universal_name for bone in bones)

        report = analyze_rig(
            bones,
            diagnostic_profile=empty_diagnostic_profile(),
        )

        self.assertEqual(report.summary.bone_count, 1500)
        self.assertEqual(report.summary.resolved_bone_count, 0)
        self.assertEqual(report.bone_map.unmapped_count, 1500)
        self.assertEqual(
            tuple(bone.universal_name for bone in bones),
            original_names,
        )

    def test_complete_report_json_is_deterministic(self) -> None:
        bones = (
            *minimal_standard_rig(),
            make_bone(universal_name="Left Arm"),
        )

        first = analyze_rig(bones).to_dict()
        second = analyze_rig(bones).to_dict()
        first_json = json.dumps(
            first,
            ensure_ascii=False,
            sort_keys=True,
        )
        second_json = json.dumps(
            second,
            ensure_ascii=False,
            sort_keys=True,
        )

        self.assertEqual(first, second)
        self.assertEqual(first_json, second_json)
        self.assertIn("Left Arm", first_json)


if __name__ == "__main__":
    unittest.main()
