"""Tests for the multi-command command-line interface."""

from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from mmd_registry.cli import normalize_arguments, run
from tests.mmd_fixtures import (
    build_minimal_pmd_header,
    build_minimal_pmx_header,
    build_pmx_material,
    build_pmx_structure,
)


class CliTests(unittest.TestCase):
    """Tests for validate, hash, inspect, and scan CLI commands."""

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_directory.name)

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def capture_run(
        self,
        arguments: list[str],
    ) -> tuple[int, str]:
        """Run the CLI while capturing standard output."""

        exit_code, output, _ = self.capture_run_with_stderr(arguments)
        return exit_code, output

    def capture_run_with_stderr(
        self,
        arguments: list[str],
    ) -> tuple[int, str, str]:
        """Run the CLI while capturing both output streams."""

        output = io.StringIO()
        error_output = io.StringIO()

        with redirect_stdout(output), redirect_stderr(error_output):
            exit_code = run(arguments)

        return exit_code, output.getvalue(), error_output.getvalue()

    def test_legacy_arguments_are_normalized_to_validate(self) -> None:
        self.assertEqual(
            normalize_arguments(
                [
                    "--mode",
                    "private",
                    "--no-report",
                ]
            ),
            [
                "validate",
                "--mode",
                "private",
                "--no-report",
            ],
        )

    def test_explicit_command_is_preserved(self) -> None:
        self.assertEqual(
            normalize_arguments(["hash", "model.pmx"]),
            ["hash", "model.pmx"],
        )

    def test_scan_command_is_preserved(self) -> None:
        self.assertEqual(
            normalize_arguments(["scan", "model.pmx"]),
            ["scan", "model.pmx"],
        )

    def test_empty_arguments_default_to_validate(self) -> None:
        self.assertEqual(normalize_arguments([]), ["validate"])

    def test_legacy_validate_invocation_reaches_validate_handler(self) -> None:
        with patch(
            "mmd_registry.cli._run_validate",
            return_value=0,
        ) as validate_handler:
            exit_code = run(
                [
                    "--mode",
                    "private",
                    "--no-report",
                ]
            )

        self.assertEqual(exit_code, 0)
        parsed_arguments = validate_handler.call_args.args[0]
        self.assertEqual(parsed_arguments.command, "validate")
        self.assertEqual(parsed_arguments.mode, "private")
        self.assertTrue(parsed_arguments.no_report)

    def test_hash_command_prints_digest_and_size(self) -> None:
        payload = b"CLI hashing fixture"
        fixture = self.project_root / "fixture.bin"
        fixture.write_bytes(payload)

        exit_code, output = self.capture_run(
            [
                "hash",
                str(fixture),
            ]
        )

        expected_digest = hashlib.sha256(payload).hexdigest()

        self.assertEqual(exit_code, 0)
        self.assertIn(f"SHA-256: {expected_digest}", output)
        self.assertIn(f"Size bytes: {len(payload)}", output)
        self.assertIn("Status: not_recorded", output)

    def test_hash_expected_match_returns_zero(self) -> None:
        payload = b"matching hash fixture"
        fixture = self.project_root / "fixture.bin"
        fixture.write_bytes(payload)
        expected_digest = hashlib.sha256(payload).hexdigest()

        exit_code, output = self.capture_run(
            [
                "hash",
                str(fixture),
                "--expected",
                expected_digest,
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("Status: matched", output)

    def test_hash_mismatch_returns_one(self) -> None:
        fixture = self.project_root / "fixture.bin"
        fixture.write_bytes(b"mismatch fixture")

        exit_code, output = self.capture_run(
            [
                "hash",
                str(fixture),
                "--expected",
                "0" * 64,
            ]
        )

        self.assertEqual(exit_code, 1)
        self.assertIn("Status: mismatched", output)

    def test_hash_json_output_is_machine_readable(self) -> None:
        payload = b"JSON hash fixture"
        fixture = self.project_root / "fixture.bin"
        fixture.write_bytes(payload)

        exit_code, output = self.capture_run(
            [
                "hash",
                str(fixture),
                "--json",
            ]
        )

        report = json.loads(output)

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["algorithm"], "sha256")
        self.assertEqual(report["size_bytes"], len(payload))
        self.assertEqual(
            report["actual"],
            hashlib.sha256(payload).hexdigest(),
        )

    def test_inspect_valid_pmx_returns_zero(self) -> None:
        fixture = self.project_root / "fixture.pmx"
        fixture.write_bytes(build_minimal_pmx_header("CLI PMX"))

        exit_code, output = self.capture_run(
            [
                "inspect",
                str(fixture),
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("Status: ok", output)
        self.assertIn("Format: PMX", output)
        self.assertIn("Model name: CLI PMX", output)

    def test_inspect_invalid_model_returns_one(self) -> None:
        fixture = self.project_root / "invalid.pmx"
        fixture.write_bytes(b"")

        exit_code, output = self.capture_run(
            [
                "inspect",
                str(fixture),
            ]
        )

        self.assertEqual(exit_code, 1)
        self.assertIn("Status: error", output)
        self.assertIn(
            "File is too short to contain an MMD model signature.",
            output,
        )

    def test_inspect_json_output_is_machine_readable(self) -> None:
        fixture = self.project_root / "fixture.pmx"
        fixture.write_bytes(build_minimal_pmx_header("JSON PMX"))

        exit_code, output = self.capture_run(
            [
                "inspect",
                str(fixture),
                "--json",
            ]
        )

        report = json.loads(output)

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["detected_format"], "pmx")
        self.assertEqual(report["version"], 2.0)
        self.assertEqual(report["model_name"], "JSON PMX")

    def test_scan_valid_pmx_prints_structural_summary(self) -> None:
        fixture = self.project_root / "complete.pmx"
        fixture.write_bytes(build_pmx_structure())

        exit_code, output = self.capture_run(
            [
                "scan",
                str(fixture),
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("Status: ok", output)
        self.assertIn("Format: PMX", output)
        self.assertIn("Model name: Test PMX Model", output)
        self.assertIn("Scan complete: yes", output)
        self.assertIn("Sections:", output)
        self.assertIn("  Vertices: 1", output)
        self.assertIn("  Triangles: 1", output)
        self.assertIn("  Materials: 1", output)
        self.assertIn("Trailing bytes: 0", output)

    def test_scan_text_lists_texture_dependencies(self) -> None:
        fixture = self.project_root / "dependencies.pmx"
        material = build_pmx_material(
            texture_index=0,
            surface_index_count=3,
        )
        fixture.write_bytes(
            build_pmx_structure(
                texture_paths=(
                    "textures/body.png",
                    "textures/unused.png",
                ),
                materials=(material,),
            )
        )

        exit_code, output = self.capture_run(
            [
                "scan",
                str(fixture),
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("Texture dependencies:", output)
        self.assertIn("  Declared paths: 2", output)
        self.assertIn("  Total references: 1", output)
        self.assertIn("    [0] textures/body.png", output)
        self.assertIn("    [1] textures/unused.png", output)

    def test_scan_json_output_is_machine_readable(self) -> None:
        fixture = self.project_root / "complete-json.pmx"
        fixture.write_bytes(build_pmx_structure(version=2.1))

        exit_code, output = self.capture_run(
            [
                "scan",
                str(fixture),
                "--json",
            ]
        )

        report = json.loads(output)

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["detected_format"], "pmx")
        self.assertEqual(report["version"], 2.1)
        self.assertTrue(report["scan_complete"])
        self.assertEqual(report["trailing_byte_count"], 0)
        self.assertEqual(
            report["section_summary"]["vertex_count"],
            1,
        )
        self.assertEqual(
            report["section_summary"]["soft_body_count"],
            0,
        )
        self.assertIn("dependency_summary", report)

    def test_scan_warning_returns_zero(self) -> None:
        fixture = self.project_root / "trailing.pmx"
        fixture.write_bytes(build_pmx_structure(trailing_bytes=b"XYZ"))

        exit_code, output = self.capture_run(
            [
                "scan",
                str(fixture),
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("Status: warning", output)
        self.assertIn("Scan complete: yes", output)
        self.assertIn("Trailing bytes: 3", output)
        self.assertIn("[WARNING]", output)

    def test_scan_malformed_model_returns_one(self) -> None:
        fixture = self.project_root / "malformed.pmx"
        fixture.write_bytes(b"")

        exit_code, output = self.capture_run(
            [
                "scan",
                str(fixture),
            ]
        )

        self.assertEqual(exit_code, 1)
        self.assertIn("Status: error", output)
        self.assertIn("Scan complete: no", output)
        self.assertIn("[ERROR]", output)

    def test_scan_pmd_is_reported_as_unsupported(self) -> None:
        fixture = self.project_root / "model.pmd"
        fixture.write_bytes(build_minimal_pmd_header("CLI PMD"))

        exit_code, output = self.capture_run(
            [
                "scan",
                str(fixture),
            ]
        )

        self.assertEqual(exit_code, 1)
        self.assertIn("Status: error", output)
        self.assertIn("Format: unknown", output)
        self.assertIn("invalid PMX magic/signature", output)

    def test_scan_missing_file_returns_two(self) -> None:
        missing = self.project_root / "missing.pmx"

        exit_code, output = self.capture_run(
            [
                "scan",
                str(missing),
            ]
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("[ERROR] scan: File does not exist:", output)

    def test_scan_directory_path_returns_two(self) -> None:
        exit_code, output = self.capture_run(
            [
                "scan",
                str(self.project_root),
            ]
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("[ERROR] scan: Path is not a file:", output)

    def test_scan_internal_failure_returns_three(self) -> None:
        fixture = self.project_root / "internal.pmx"
        fixture.write_bytes(build_pmx_structure())

        with patch(
            "mmd_registry.cli.scan_pmx_structure",
            side_effect=RuntimeError("simulated scanner failure"),
        ):
            exit_code, output, error_output = self.capture_run_with_stderr(
                [
                    "scan",
                    str(fixture),
                ]
            )

        self.assertEqual(exit_code, 3)
        self.assertEqual(output, "")
        self.assertIn(
            "[ERROR] scan: Internal scan failure: simulated scanner failure",
            error_output,
        )

    def test_scan_internal_json_failure_is_machine_readable(self) -> None:
        fixture = self.project_root / "internal-json.pmx"
        fixture.write_bytes(build_pmx_structure())

        with patch(
            "mmd_registry.cli.scan_pmx_structure",
            side_effect=RuntimeError("simulated scanner failure"),
        ):
            exit_code, output = self.capture_run(
                [
                    "scan",
                    str(fixture),
                    "--json",
                ]
            )

        report = json.loads(output)

        self.assertEqual(exit_code, 3)
        self.assertEqual(report["status"], "error")
        self.assertTrue(report["internal_error"])
        self.assertIn(
            "simulated scanner failure",
            report["errors"][0],
        )


if __name__ == "__main__":
    unittest.main()
