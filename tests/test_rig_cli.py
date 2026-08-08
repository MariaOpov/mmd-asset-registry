"""Tests for the PMX Rig Analyzer command-line workflow."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mmd_registry.cli import normalize_arguments, run
from mmd_registry.model_scanning import PmxBone, PmxIk, PmxIkLink


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
    """Build one small scanner record for Rig CLI tests."""

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


def build_scan_result(
    bones: tuple[PmxBone, ...],
    *,
    warnings: tuple[str, ...] = (),
    errors: tuple[str, ...] = (),
    scan_complete: bool = True,
    model_name: str = "Rig CLI Fixture",
) -> SimpleNamespace:
    """Build one scanner-shaped result for CLI workflow tests."""

    return SimpleNamespace(
        bones=bones,
        warnings=warnings,
        errors=errors,
        scan_complete=scan_complete,
        model_info=SimpleNamespace(local_name=model_name),
    )


class RigCliTests(unittest.TestCase):
    """Tests for text, JSON, filters, exports, and exit codes."""

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_directory.name)
        self.model_path = self.project_root / "モデル.pmx"
        self.model_path.write_bytes(b"PMX fixture placeholder")

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def capture_run(
        self,
        arguments: list[str],
    ) -> tuple[int, str, str]:
        """Run the CLI while capturing both output streams."""

        output = io.StringIO()
        error_output = io.StringIO()

        with redirect_stdout(output), redirect_stderr(error_output):
            exit_code = run(arguments)

        return exit_code, output.getvalue(), error_output.getvalue()

    def run_with_scan(
        self,
        arguments: list[str],
        scan_result: SimpleNamespace,
    ) -> tuple[int, str, str]:
        """Run the CLI with one deterministic scanner result."""

        with patch(
            "mmd_registry.rig_cli.scan_pmx_structure",
            return_value=scan_result,
        ):
            return self.capture_run(arguments)

    def test_rig_command_is_preserved(self) -> None:
        self.assertEqual(
            normalize_arguments(["rig", "model.pmx"]),
            ["rig", "model.pmx"],
        )

    def test_parser_dispatches_all_rig_options(self) -> None:
        with patch(
            "mmd_registry.cli.run_rig_command",
            return_value=0,
        ) as handler:
            exit_code = run(
                [
                    "rig",
                    "model.pmx",
                    "--role",
                    "left_knee",
                    "--export-map",
                    "bone-map.json",
                    "--json",
                ]
            )

        self.assertEqual(exit_code, 0)
        handler.assert_called_once_with(
            path="model.pmx",
            unmapped=False,
            role="left_knee",
            export_map="bone-map.json",
            json_output=True,
        )

    def test_default_text_output_renders_clean_summary_and_map(self) -> None:
        scan_result = build_scan_result(minimal_standard_rig())

        exit_code, output, error_output = self.run_with_scan(
            ["rig", str(self.model_path)],
            scan_result,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(error_output, "")
        self.assertIn("Status: ok", output)
        self.assertIn("Model: Rig CLI Fixture", output)
        self.assertIn("Bones: 5", output)
        self.assertIn("Resolved: 5", output)
        self.assertIn("Canonical roles:", output)
        self.assertIn("center: 0", output)
        self.assertIn("Rig diagnostics:\n  [none]", output)

    def test_actionable_diagnostics_return_one(self) -> None:
        scan_result = build_scan_result((make_bone(universal_name="Mystery Joint"),))

        exit_code, output, error_output = self.run_with_scan(
            ["rig", str(self.model_path)],
            scan_result,
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(error_output, "")
        self.assertIn("Status: warning", output)
        self.assertIn("missing_expected_role", output)
        self.assertIn("unclassified_bones", output)

    def test_json_output_contains_complete_analysis(self) -> None:
        scan_result = build_scan_result(
            minimal_standard_rig(),
            model_name="日本語モデル",
        )

        exit_code, output, error_output = self.run_with_scan(
            [
                "rig",
                str(self.model_path),
                "--json",
            ],
            scan_result,
        )
        payload = json.loads(output)

        self.assertEqual(exit_code, 0)
        self.assertEqual(error_output, "")
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["model_name"], "日本語モデル")
        self.assertEqual(payload["analysis"]["schema_version"], "1.0")
        self.assertEqual(payload["analysis"]["summary"]["bone_count"], 5)
        self.assertEqual(
            payload["analysis"]["bone_map"]["roles"]["head"],
            [4],
        )
        self.assertIsNone(payload["selection"])
        self.assertIn("日本語モデル", output)

    def test_unmapped_filter_selects_only_unknown_bones(self) -> None:
        scan_result = build_scan_result(
            (
                *minimal_standard_rig(),
                make_bone(universal_name="Mystery Joint"),
            )
        )

        exit_code, output, _ = self.run_with_scan(
            [
                "rig",
                str(self.model_path),
                "--unmapped",
            ],
            scan_result,
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("Selection: unmapped", output)
        self.assertIn("Matches: 1", output)
        self.assertIn("[5] Mystery Joint", output)
        self.assertNotIn("Canonical roles:", output)

    def test_role_filter_is_normalized_and_selects_matching_side(self) -> None:
        scan_result = build_scan_result(
            (
                *minimal_standard_rig(),
                make_bone(universal_name="Left Knee"),
                make_bone(universal_name="Right Knee"),
            )
        )

        exit_code, output, _ = self.run_with_scan(
            [
                "rig",
                str(self.model_path),
                "--role",
                "Left-Knee",
            ],
            scan_result,
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("Selection: role left_knee", output)
        self.assertIn("Matches: 1", output)
        self.assertIn("[5] Left Knee", output)
        self.assertNotIn("Right Knee", output)

    def test_role_filter_without_matches_is_successful(self) -> None:
        scan_result = build_scan_result(minimal_standard_rig())

        exit_code, output, _ = self.run_with_scan(
            [
                "rig",
                str(self.model_path),
                "--role",
                "left_knee",
            ],
            scan_result,
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("Matches: 0", output)

    def test_role_filter_json_contains_stable_selection(self) -> None:
        scan_result = build_scan_result(
            (
                *minimal_standard_rig(),
                make_bone(universal_name="Left Knee"),
                make_bone(universal_name="Right Knee"),
            )
        )

        exit_code, output, error_output = self.run_with_scan(
            [
                "rig",
                str(self.model_path),
                "--role",
                "LEFT KNEE",
                "--json",
            ],
            scan_result,
        )
        payload = json.loads(output)

        self.assertEqual(exit_code, 0)
        self.assertEqual(error_output, "")
        self.assertEqual(payload["filters"]["role"], "left_knee")
        self.assertEqual(payload["selection"]["mode"], "role")
        self.assertEqual(payload["selection"]["query"], "left_knee")
        self.assertEqual(payload["selection"]["count"], 1)
        self.assertEqual(payload["selection"]["bones"][0]["index"], 5)

    def test_role_and_unmapped_filters_conflict(self) -> None:
        exit_code, output, error_output = self.capture_run(
            [
                "rig",
                str(self.model_path),
                "--unmapped",
                "--role",
                "left_knee",
            ]
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(output, "")
        self.assertIn("--unmapped cannot be combined", error_output)

    def test_empty_role_is_a_machine_readable_usage_error(self) -> None:
        exit_code, output, error_output = self.capture_run(
            [
                "rig",
                str(self.model_path),
                "--role",
                "   ",
                "--json",
            ]
        )
        payload = json.loads(output)

        self.assertEqual(exit_code, 2)
        self.assertEqual(error_output, "")
        self.assertFalse(payload["internal_error"])
        self.assertIn("non-empty canonical role", payload["errors"][0])

    def test_missing_file_returns_two(self) -> None:
        missing_path = self.project_root / "missing.pmx"

        exit_code, output, error_output = self.capture_run(["rig", str(missing_path)])

        self.assertEqual(exit_code, 2)
        self.assertEqual(output, "")
        self.assertIn("[ERROR] rig: File does not exist", error_output)

    def test_scan_error_returns_one_as_json(self) -> None:
        scan_result = build_scan_result(
            (),
            errors=("Malformed PMX fixture.",),
            scan_complete=False,
        )

        exit_code, output, error_output = self.run_with_scan(
            [
                "rig",
                str(self.model_path),
                "--json",
            ],
            scan_result,
        )
        payload = json.loads(output)

        self.assertEqual(exit_code, 1)
        self.assertEqual(error_output, "")
        self.assertFalse(payload["internal_error"])
        self.assertIn("Malformed PMX fixture.", payload["errors"])
        self.assertIsNone(payload["analysis"])

    def test_incomplete_scan_without_error_returns_one(self) -> None:
        scan_result = build_scan_result(
            (),
            scan_complete=False,
        )

        exit_code, output, error_output = self.run_with_scan(
            ["rig", str(self.model_path)],
            scan_result,
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(output, "")
        self.assertIn("scan did not complete", error_output)

    def test_internal_scan_failure_returns_three_as_json(self) -> None:
        with patch(
            "mmd_registry.rig_cli.scan_pmx_structure",
            side_effect=RuntimeError("boom"),
        ):
            exit_code, output, error_output = self.capture_run(
                [
                    "rig",
                    str(self.model_path),
                    "--json",
                ]
            )
        payload = json.loads(output)

        self.assertEqual(exit_code, 3)
        self.assertEqual(error_output, "")
        self.assertTrue(payload["internal_error"])
        self.assertIn("Internal scan failure: boom", payload["errors"][0])

    def test_internal_analysis_failure_returns_three(self) -> None:
        scan_result = build_scan_result(minimal_standard_rig())

        with (
            patch(
                "mmd_registry.rig_cli.scan_pmx_structure",
                return_value=scan_result,
            ),
            patch(
                "mmd_registry.rig_cli.analyze_rig",
                side_effect=RuntimeError("analysis boom"),
            ),
        ):
            exit_code, output, error_output = self.capture_run(
                ["rig", str(self.model_path)]
            )

        self.assertEqual(exit_code, 3)
        self.assertEqual(output, "")
        self.assertIn("Internal Rig Analyzer failure", error_output)

    def test_export_map_writes_standalone_utf8_json(self) -> None:
        scan_result = build_scan_result(minimal_standard_rig())
        export_path = self.project_root / "reports" / "bone-map.json"

        exit_code, output, error_output = self.run_with_scan(
            [
                "rig",
                str(self.model_path),
                "--export-map",
                str(export_path),
            ],
            scan_result,
        )
        exported = json.loads(export_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(error_output, "")
        self.assertIn(f"Exported map: {export_path.as_posix()}", output)
        self.assertEqual(exported["schema_version"], "1.0")
        self.assertEqual(exported["roles"]["center"], [0])
        self.assertTrue(export_path.read_text(encoding="utf-8").endswith("\n"))

    def test_export_map_requires_json_path(self) -> None:
        export_path = self.project_root / "bone-map.txt"

        exit_code, output, error_output = self.capture_run(
            [
                "rig",
                str(self.model_path),
                "--export-map",
                str(export_path),
            ]
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(output, "")
        self.assertIn("must use a .json", error_output)
        self.assertFalse(export_path.exists())

    def test_export_map_cannot_overwrite_input(self) -> None:
        json_named_model = self.project_root / "model.json"
        json_named_model.write_bytes(b"PMX fixture placeholder")

        exit_code, output, error_output = self.capture_run(
            [
                "rig",
                str(json_named_model),
                "--export-map",
                str(json_named_model),
            ]
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(output, "")
        self.assertIn("cannot overwrite the input", error_output)

    def test_export_failure_returns_three_without_internal_flag(self) -> None:
        scan_result = build_scan_result(minimal_standard_rig())
        export_path = self.project_root / "bone-map.json"

        with (
            patch(
                "mmd_registry.rig_cli.scan_pmx_structure",
                return_value=scan_result,
            ),
            patch(
                "mmd_registry.rig_cli.write_json_report",
                side_effect=OSError("disk unavailable"),
            ),
        ):
            exit_code, output, error_output = self.capture_run(
                [
                    "rig",
                    str(self.model_path),
                    "--export-map",
                    str(export_path),
                    "--json",
                ]
            )
        payload = json.loads(output)

        self.assertEqual(exit_code, 3)
        self.assertEqual(error_output, "")
        self.assertFalse(payload["internal_error"])
        self.assertIn("Unable to export bone map", payload["errors"][0])

    def test_scan_warning_is_visible_but_does_not_fail_clean_rig(self) -> None:
        scan_result = build_scan_result(
            minimal_standard_rig(),
            warnings=("Trailing bytes were ignored.",),
        )

        exit_code, output, _ = self.run_with_scan(
            ["rig", str(self.model_path)],
            scan_result,
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("Status: warning", output)
        self.assertIn("[WARNING] scan: Trailing bytes were ignored.", output)


if __name__ == "__main__":
    unittest.main()
