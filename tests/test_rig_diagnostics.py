"""Tests for structured hierarchy-aware PMX rig diagnostics."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
import unittest

from mmd_registry.bone_semantic_resolver import BoneSemanticResolver
from mmd_registry.bone_semantics import (
    BoneSemanticAlias,
    BoneSemanticProfile,
)
from mmd_registry.model_scanning import PmxBone, PmxIk, PmxIkLink
from mmd_registry.rig_diagnostics import (
    RigDiagnosticProfile,
    RigDiagnosticReport,
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
    """Build one small scanner record for rig diagnostic tests."""

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


def codes_for(report: RigDiagnosticReport) -> tuple[str, ...]:
    """Return diagnostic codes from one report-like object."""

    return tuple(issue.code for issue in report.issues)


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


class RigDiagnosticTests(unittest.TestCase):
    """Tests for deterministic, non-fatal rig diagnostics."""

    def test_empty_input_reports_only_bounded_required_roles(self) -> None:
        report = diagnose_rig(())

        self.assertEqual(report.bone_count, 0)
        self.assertEqual(report.status, "warning")
        self.assertEqual(
            codes_for(report),
            ("missing_expected_role",) * 5,
        )
        self.assertEqual(
            report.severity_counts,
            {
                "info": 0,
                "warning": 5,
                "error": 0,
            },
        )
        json.dumps(report.to_dict(), ensure_ascii=False)

    def test_report_and_issues_are_immutable(self) -> None:
        report = diagnose_rig(())

        with self.assertRaises(FrozenInstanceError):
            report.bone_count = 1

        with self.assertRaises(FrozenInstanceError):
            report.issues[0].severity = "error"

    def test_custom_profile_replaces_default_expectations(self) -> None:
        profile = RigDiagnosticProfile(
            name="empty-policy",
            required_roles=(),
            paired_roles=(),
            duplicate_exempt_roles=(),
        )

        report = diagnose_rig(
            (make_bone(universal_name="Mystery"),),
            profile=profile,
        )

        self.assertEqual(report.profile_name, "empty-policy")
        self.assertEqual(codes_for(report), ("unclassified_bones",))
        self.assertEqual(report.status, "ok")

    def test_minimal_required_roles_produce_clean_report(self) -> None:
        report = diagnose_rig(minimal_standard_rig())

        self.assertEqual(report.status, "ok")
        self.assertEqual(report.issues, ())
        self.assertEqual(
            report.to_dict()["severity_counts"],
            {
                "info": 0,
                "warning": 0,
                "error": 0,
            },
        )

    def test_unknown_bones_are_grouped_into_one_information_issue(self) -> None:
        profile = RigDiagnosticProfile(
            name="unknown-only",
            required_roles=(),
            paired_roles=(),
            duplicate_exempt_roles=(),
        )

        report = diagnose_rig(
            (
                make_bone(universal_name="Mystery A"),
                make_bone(universal_name="Mystery B"),
            ),
            profile=profile,
        )

        self.assertEqual(len(report.issues), 1)
        self.assertEqual(report.issues[0].code, "unclassified_bones")
        self.assertEqual(report.issues[0].severity, "info")
        self.assertEqual(report.issues[0].bone_indices, (0, 1))

    def test_duplicate_same_side_role_is_reported(self) -> None:
        report = diagnose_rig(
            (
                *minimal_standard_rig(),
                make_bone(universal_name="Left Arm"),
                make_bone(universal_name="Left Arm"),
            )
        )
        duplicates = tuple(
            issue for issue in report.issues if issue.code == "duplicate_semantic_role"
        )

        self.assertEqual(len(duplicates), 1)
        self.assertEqual(duplicates[0].bone_indices, (5, 6))

    def test_base_and_deform_variant_are_not_reported_as_duplicates(self) -> None:
        profile = RigDiagnosticProfile(
            name="variant-only",
            required_roles=(),
            paired_roles=(),
            duplicate_exempt_roles=(),
        )

        report = diagnose_rig(
            (
                make_bone(universal_name="Left Knee"),
                make_bone(universal_name="Left Knee D"),
            ),
            profile=profile,
        )

        self.assertNotIn("duplicate_semantic_role", codes_for(report))

    def test_helper_companions_do_not_create_duplicates_or_asymmetry(self) -> None:
        profile = RigDiagnosticProfile(
            name="eye-only",
            required_roles=(),
            paired_roles=("eye",),
            duplicate_exempt_roles=(),
        )

        report = diagnose_rig(
            (
                make_bone(local_name="左目"),
                make_bone(local_name="左目先"),
                make_bone(local_name="右目"),
            ),
            profile=profile,
        )

        self.assertNotIn("duplicate_semantic_role", codes_for(report))
        self.assertNotIn("left_right_asymmetry", codes_for(report))

    def test_one_sided_paired_role_reports_asymmetry(self) -> None:
        report = diagnose_rig(
            (
                *minimal_standard_rig(),
                make_bone(universal_name="Left Wrist"),
            )
        )
        asymmetry = tuple(
            issue for issue in report.issues if issue.code == "left_right_asymmetry"
        )

        self.assertEqual(len(asymmetry), 1)
        self.assertEqual(asymmetry[0].bone_indices, (5,))
        self.assertIn("right_count=0", asymmetry[0].evidence)

    def test_ambiguous_custom_alias_is_not_guessed(self) -> None:
        resolver = BoneSemanticResolver(
            BoneSemanticProfile(
                name="ambiguous",
                aliases=(
                    BoneSemanticAlias(
                        alias="Mystery Joint",
                        role="knee",
                        category="deform",
                        side="left",
                    ),
                    BoneSemanticAlias(
                        alias="Mystery Joint",
                        role="ankle",
                        category="deform",
                        side="left",
                    ),
                ),
            )
        )
        profile = RigDiagnosticProfile(
            name="ambiguity-only",
            required_roles=(),
            paired_roles=(),
            duplicate_exempt_roles=(),
        )

        report = diagnose_rig(
            (make_bone(universal_name="Mystery Joint"),),
            resolver=resolver,
            profile=profile,
        )

        self.assertEqual(
            codes_for(report),
            (
                "ambiguous_semantic_role",
                "unclassified_bones",
            ),
        )

    def test_conflicting_left_and_right_names_are_reported(self) -> None:
        profile = RigDiagnosticProfile(
            name="conflict-only",
            required_roles=(),
            paired_roles=(),
            duplicate_exempt_roles=(),
        )

        report = diagnose_rig(
            (
                make_bone(
                    local_name="Left Knee",
                    universal_name="Right Knee",
                ),
            ),
            profile=profile,
        )

        self.assertIn("side_conflict", codes_for(report))

    def test_unexpected_strict_parent_role_is_reported(self) -> None:
        profile = RigDiagnosticProfile(
            name="parent-only",
            required_roles=(),
            paired_roles=(),
            duplicate_exempt_roles=(),
        )

        report = diagnose_rig(
            (
                make_bone(universal_name="Left Arm"),
                make_bone(
                    universal_name="Left Ankle",
                    parent_index=0,
                ),
            ),
            profile=profile,
        )

        self.assertIn("suspicious_parent_role", codes_for(report))

    def test_invalid_parent_and_cycle_are_reported_without_failure(self) -> None:
        profile = RigDiagnosticProfile(
            name="hierarchy-only",
            required_roles=(),
            paired_roles=(),
            duplicate_exempt_roles=(),
        )

        report = diagnose_rig(
            (
                make_bone(
                    universal_name="Mystery Root",
                    parent_index=99,
                ),
                make_bone(
                    universal_name="Mystery A",
                    parent_index=2,
                ),
                make_bone(
                    universal_name="Mystery B",
                    parent_index=1,
                ),
            ),
            profile=profile,
        )

        self.assertIn("invalid_parent_reference", codes_for(report))
        self.assertIn("hierarchy_cycle", codes_for(report))
        self.assertEqual(report.status, "error")

    def test_named_leg_ik_without_definition_is_reported(self) -> None:
        profile = RigDiagnosticProfile(
            name="ik-only",
            required_roles=(),
            paired_roles=(),
            duplicate_exempt_roles=(),
        )

        report = diagnose_rig(
            (make_bone(universal_name="Left Leg IK"),),
            profile=profile,
        )

        self.assertIn("missing_ik_definition", codes_for(report))

    def test_invalid_ik_target_and_link_are_errors(self) -> None:
        profile = RigDiagnosticProfile(
            name="ik-only",
            required_roles=(),
            paired_roles=(),
            duplicate_exempt_roles=(),
        )

        report = diagnose_rig(
            (
                make_bone(
                    universal_name="Left Leg IK",
                    ik=make_ik(
                        target_index=99,
                        link_indices=(88,),
                    ),
                ),
            ),
            profile=profile,
        )

        self.assertIn("invalid_ik_target", codes_for(report))
        self.assertIn("invalid_ik_link", codes_for(report))
        self.assertEqual(report.severity_counts["error"], 2)
        self.assertEqual(report.status, "error")

    def test_empty_ik_chain_is_reported(self) -> None:
        profile = RigDiagnosticProfile(
            name="ik-only",
            required_roles=(),
            paired_roles=(),
            duplicate_exempt_roles=(),
        )

        report = diagnose_rig(
            (
                make_bone(universal_name="Left Ankle"),
                make_bone(
                    universal_name="Left Leg IK",
                    ik=make_ik(target_index=0),
                ),
            ),
            profile=profile,
        )

        self.assertIn("missing_ik_chain", codes_for(report))

    def test_suspicious_ik_target_and_chain_roles_are_reported(self) -> None:
        profile = RigDiagnosticProfile(
            name="ik-only",
            required_roles=(),
            paired_roles=(),
            duplicate_exempt_roles=(),
        )

        report = diagnose_rig(
            (
                make_bone(universal_name="Left Wrist"),
                make_bone(universal_name="Left Arm"),
                make_bone(
                    universal_name="Left Leg IK",
                    ik=make_ik(
                        target_index=0,
                        link_indices=(1,),
                    ),
                ),
            ),
            profile=profile,
        )

        self.assertIn("suspicious_ik_target_role", codes_for(report))
        self.assertIn("suspicious_ik_chain", codes_for(report))

    def test_non_ik_role_with_definition_is_reported(self) -> None:
        profile = RigDiagnosticProfile(
            name="ik-only",
            required_roles=(),
            paired_roles=(),
            duplicate_exempt_roles=(),
        )

        report = diagnose_rig(
            (
                make_bone(
                    universal_name="Center",
                    ik=make_ik(
                        target_index=0,
                        link_indices=(0,),
                    ),
                ),
            ),
            profile=profile,
        )

        self.assertIn("unexpected_ik_definition", codes_for(report))
        self.assertIn("semantic_evidence_conflict", codes_for(report))

    def test_deep_hierarchy_is_non_recursive_and_preserves_input(self) -> None:
        profile = RigDiagnosticProfile(
            name="deep-hierarchy",
            required_roles=(),
            paired_roles=(),
            duplicate_exempt_roles=(),
        )
        bones = tuple(
            make_bone(
                universal_name=f"Mystery {index}",
                parent_index=(-1 if index == 0 else index - 1),
            )
            for index in range(1500)
        )
        original_names = tuple(bone.universal_name for bone in bones)

        report = diagnose_rig(
            bones,
            profile=profile,
        )

        self.assertEqual(report.bone_count, 1500)
        self.assertEqual(codes_for(report), ("unclassified_bones",))
        self.assertEqual(
            tuple(bone.universal_name for bone in bones),
            original_names,
        )

    def test_output_order_and_json_serialization_are_deterministic(self) -> None:
        bones = (
            *minimal_standard_rig(),
            make_bone(universal_name="Left Arm"),
        )

        first = diagnose_rig(bones).to_dict()
        second = diagnose_rig(bones).to_dict()

        self.assertEqual(first, second)
        self.assertEqual(
            json.dumps(first, ensure_ascii=False, sort_keys=True),
            json.dumps(second, ensure_ascii=False, sort_keys=True),
        )


if __name__ == "__main__":
    unittest.main()
