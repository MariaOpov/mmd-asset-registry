"""Tests for the PMX Bone Explorer command-line workflow."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from mmd_registry.cli import normalize_arguments, run
from tests.mmd_fixtures import (
    build_pmx_bone,
    build_pmx_structure,
)


_ROTATE_VISIBLE_ENABLED = 0x001A
_MOVE_ROTATE_VISIBLE_ENABLED = 0x001E


class BoneCliTests(unittest.TestCase):
    """Tests for human-readable and JSON Bone Explorer modes."""

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_directory.name)

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

    def build_model(self) -> Path:
        """Create a complete PMX fixture with a small bone hierarchy."""

        bones = (
            build_pmx_bone(
                local_name="全ての親",
                universal_name="Root",
                parent_bone_index=-1,
                tail_bone_index=1,
                extra_flags=_ROTATE_VISIBLE_ENABLED,
            ),
            build_pmx_bone(
                local_name="左ひざD",
                universal_name="Bip001 L CalfD",
                parent_bone_index=0,
                position=(1.0, 2.0, 3.0),
                extra_flags=_ROTATE_VISIBLE_ENABLED,
            ),
            build_pmx_bone(
                local_name="左足ＩＫ",
                universal_name="Left Leg IK",
                parent_bone_index=0,
                ik_target_bone_index=1,
                extra_flags=_MOVE_ROTATE_VISIBLE_ENABLED,
            ),
        )
        model_path = self.project_root / "芙拉薇娅.pmx"
        model_path.write_bytes(build_pmx_structure(bones=bones))

        return model_path

    def test_bones_command_is_preserved(self) -> None:
        self.assertEqual(
            normalize_arguments(["bones", "model.pmx"]),
            ["bones", "model.pmx"],
        )

    def test_default_mode_renders_compact_table(self) -> None:
        model_path = self.build_model()

        exit_code, output, error_output = self.capture_run(["bones", str(model_path)])

        self.assertEqual(exit_code, 0)
        self.assertEqual(error_output, "")
        self.assertIn("Status: ok", output)
        self.assertIn("Bones: 3", output)
        self.assertIn("Showing: 3", output)
        self.assertIn("Idx", output)
        self.assertIn("Bip001 L CalfD", output)
        self.assertIn("Left Leg IK", output)

    def test_search_filters_table(self) -> None:
        model_path = self.build_model()

        exit_code, output, _ = self.capture_run(
            [
                "bones",
                str(model_path),
                "--search",
                "calfd",
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("Showing: 1", output)
        self.assertIn("Search: calfd", output)
        self.assertIn("Bip001 L CalfD", output)
        self.assertNotIn("Left Leg IK", output)

    def test_search_accepts_exact_index(self) -> None:
        model_path = self.build_model()

        exit_code, output, _ = self.capture_run(
            [
                "bones",
                str(model_path),
                "--search",
                "#1",
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("Showing: 1", output)
        self.assertIn("Bip001 L CalfD", output)
        self.assertNotIn("Left Leg IK", output)

    def test_ik_only_filters_table(self) -> None:
        model_path = self.build_model()

        exit_code, output, _ = self.capture_run(["bones", str(model_path), "--ik-only"])

        self.assertEqual(exit_code, 0)
        self.assertIn("Showing: 1", output)
        self.assertIn("IK only: yes", output)
        self.assertIn("Left Leg IK", output)
        self.assertNotIn("Bip001 L CalfD", output)

    def test_search_and_ik_only_compose(self) -> None:
        model_path = self.build_model()

        exit_code, output, _ = self.capture_run(
            [
                "bones",
                str(model_path),
                "--search",
                "足",
                "--ik-only",
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("Showing: 1", output)
        self.assertIn("Left Leg IK", output)

    def test_search_without_matches_is_successful(self) -> None:
        model_path = self.build_model()

        exit_code, output, error_output = self.capture_run(
            [
                "bones",
                str(model_path),
                "--search",
                "missing",
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(error_output, "")
        self.assertIn("Showing: 0", output)

    def test_tree_mode_renders_hierarchy(self) -> None:
        model_path = self.build_model()

        exit_code, output, error_output = self.capture_run(
            ["bones", str(model_path), "--tree"]
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(error_output, "")
        self.assertIn("Roots: 1", output)
        self.assertIn("Hierarchy issues: 0", output)
        self.assertIn("[0] Root", output)
        self.assertIn("[1] Bip001 L CalfD", output)
        self.assertIn("[2] Left Leg IK", output)

    def test_details_mode_renders_one_bone(self) -> None:
        model_path = self.build_model()

        exit_code, output, error_output = self.capture_run(
            [
                "bones",
                str(model_path),
                "--details",
                "1",
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(error_output, "")
        self.assertIn("Bone #1", output)
        self.assertIn("Display name:   Bip001 L CalfD", output)
        self.assertIn("Original name:  左ひざD", output)
        self.assertIn("Parent:          [0] Root", output)

    def test_default_json_output_is_machine_readable(self) -> None:
        model_path = self.build_model()

        exit_code, output, error_output = self.capture_run(
            ["bones", str(model_path), "--json"]
        )
        report = json.loads(output)

        self.assertEqual(exit_code, 0)
        self.assertEqual(error_output, "")
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["mode"], "table")
        self.assertEqual(report["bone_count"], 3)
        self.assertEqual(report["match_count"], 3)
        self.assertEqual(len(report["bones"]), 3)
        self.assertIsNone(report["hierarchy"])
        self.assertIsNone(report["detail"])

    def test_filtered_json_records_filters_and_matches(self) -> None:
        model_path = self.build_model()

        exit_code, output, _ = self.capture_run(
            [
                "bones",
                str(model_path),
                "--search",
                "leg",
                "--ik-only",
                "--json",
            ]
        )
        report = json.loads(output)

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["match_count"], 1)
        self.assertEqual(report["filters"]["search"], "leg")
        self.assertTrue(report["filters"]["ik_only"])
        self.assertEqual(
            report["bones"][0]["display_name"],
            "Left Leg IK",
        )

    def test_tree_json_contains_serializable_hierarchy(self) -> None:
        model_path = self.build_model()

        exit_code, output, _ = self.capture_run(
            [
                "bones",
                str(model_path),
                "--tree",
                "--json",
            ]
        )
        report = json.loads(output)

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["mode"], "tree")
        self.assertEqual(report["match_count"], 3)
        self.assertEqual(report["hierarchy"]["root_indices"], [0])
        self.assertEqual(report["hierarchy"]["node_count"], 3)
        self.assertIsNone(report["bones"])

    def test_details_json_contains_serializable_detail(self) -> None:
        model_path = self.build_model()

        exit_code, output, _ = self.capture_run(
            [
                "bones",
                str(model_path),
                "--details",
                "1",
                "--json",
            ]
        )
        report = json.loads(output)

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["mode"], "details")
        self.assertEqual(report["match_count"], 1)
        self.assertEqual(report["detail"]["bone"]["index"], 1)
        self.assertEqual(
            report["detail"]["bone"]["display_name"],
            "Bip001 L CalfD",
        )

    def test_invalid_detail_index_returns_two(self) -> None:
        model_path = self.build_model()

        exit_code, output, error_output = self.capture_run(
            [
                "bones",
                str(model_path),
                "--details",
                "99",
                "--json",
            ]
        )
        report = json.loads(output)

        self.assertEqual(exit_code, 2)
        self.assertEqual(error_output, "")
        self.assertEqual(report["status"], "error")
        self.assertFalse(report["internal_error"])
        self.assertIn("Bone index 99 does not exist", report["errors"][0])

    def test_details_rejects_other_modes_and_filters(self) -> None:
        model_path = self.build_model()

        exit_code, output, error_output = self.capture_run(
            [
                "bones",
                str(model_path),
                "--details",
                "1",
                "--search",
                "Calf",
            ]
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(output, "")
        self.assertIn(
            "--details cannot be combined",
            error_output,
        )

    def test_tree_rejects_filters(self) -> None:
        model_path = self.build_model()

        exit_code, output, error_output = self.capture_run(
            [
                "bones",
                str(model_path),
                "--tree",
                "--ik-only",
            ]
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(output, "")
        self.assertIn(
            "--tree cannot be combined",
            error_output,
        )

    def test_missing_file_returns_two(self) -> None:
        missing_path = self.project_root / "missing.pmx"

        exit_code, output, error_output = self.capture_run(["bones", str(missing_path)])

        self.assertEqual(exit_code, 2)
        self.assertEqual(output, "")
        self.assertIn(
            "[ERROR] bones: File does not exist",
            error_output,
        )

    def test_malformed_model_returns_one(self) -> None:
        model_path = self.project_root / "malformed.pmx"
        model_path.write_bytes(b"")

        exit_code, output, error_output = self.capture_run(["bones", str(model_path)])

        self.assertEqual(exit_code, 1)
        self.assertEqual(output, "")
        self.assertIn("[ERROR] bones:", error_output)

    def test_internal_scan_failure_returns_three_as_json(self) -> None:
        model_path = self.project_root / "internal.pmx"
        model_path.write_bytes(b"fixture")

        with patch(
            "mmd_registry.bone_cli.scan_pmx_structure",
            side_effect=RuntimeError("boom"),
        ):
            exit_code, output, error_output = self.capture_run(
                [
                    "bones",
                    str(model_path),
                    "--json",
                ]
            )

        report = json.loads(output)
        self.assertEqual(exit_code, 3)
        self.assertEqual(error_output, "")
        self.assertEqual(report["status"], "error")
        self.assertTrue(report["internal_error"])
        self.assertIn("Internal scan failure: boom", report["errors"][0])


if __name__ == "__main__":
    unittest.main()
