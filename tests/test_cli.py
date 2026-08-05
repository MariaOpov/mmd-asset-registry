"""Tests for the multi-command command-line interface."""

from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from mmd_registry.cli import normalize_arguments, run
from tests.mmd_fixtures import build_minimal_pmx_header


class CliTests(unittest.TestCase):
    """Tests for validate, hash, and inspect CLI commands."""

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

        output = io.StringIO()

        with redirect_stdout(output):
            exit_code = run(arguments)

        return exit_code, output.getvalue()

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


if __name__ == "__main__":
    unittest.main()
