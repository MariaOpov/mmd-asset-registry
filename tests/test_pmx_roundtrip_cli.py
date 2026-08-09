"""Tests for the explicit safe PMX round-trip API and CLI command."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from mmd_registry.cli import normalize_arguments, run
from mmd_registry.pmx import load_pmx, roundtrip_pmx
from mmd_registry.pmx.roundtrip import PmxRoundTripVerificationError
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


class PmxRoundTripCliTests(unittest.TestCase):
    """Validate PMX output, path policy, errors, and reporting."""

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_directory.name)
        self.input_path = self.project_root / "input.pmx"
        self.input_bytes = build_pmx_roundtrip_fixture()
        self.input_path.write_bytes(self.input_bytes)

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

    def test_roundtrip_command_is_preserved_by_legacy_normalization(self) -> None:
        arguments = ["roundtrip", "input.pmx", "output.pmx"]

        self.assertEqual(normalize_arguments(arguments), arguments)

    def test_roundtrip_api_writes_verified_distinct_copy(self) -> None:
        output_path = self.project_root / "output.pmx"

        result = roundtrip_pmx(self.input_path, output_path)

        self.assertTrue(output_path.is_file())
        self.assertEqual(self.input_path.read_bytes(), self.input_bytes)
        self.assertEqual(load_pmx(output_path), load_pmx(self.input_path))
        self.assertTrue(result.byte_identical)
        self.assertEqual(dict(result.section_counts)["bones"], 2)

    def test_roundtrip_cli_prints_successful_summary(self) -> None:
        output_path = self.project_root / "output.pmx"

        exit_code, output, error_output = self.capture_run(
            ["roundtrip", str(self.input_path), str(output_path)]
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(error_output, "")
        self.assertIn("Status: ok", output)
        self.assertIn("Semantic equality: yes", output)
        self.assertIn("Byte-identical: yes", output)
        self.assertEqual(output_path.read_bytes(), self.input_bytes)

    def test_roundtrip_json_output_is_machine_readable(self) -> None:
        output_path = self.project_root / "output.pmx"

        exit_code, output, error_output = self.capture_run(
            [
                "roundtrip",
                str(self.input_path),
                str(output_path),
                "--json",
            ]
        )
        payload = json.loads(output)

        self.assertEqual(exit_code, 0)
        self.assertEqual(error_output, "")
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["semantic_equal"])
        self.assertTrue(payload["byte_identical"])
        self.assertEqual(payload["section_counts"]["morphs"], 11)

    def test_roundtrip_always_refuses_input_as_output(self) -> None:
        for extra_arguments in ([], ["--overwrite"]):
            with self.subTest(extra_arguments=extra_arguments):
                exit_code, output, error_output = self.capture_run(
                    [
                        "roundtrip",
                        str(self.input_path),
                        str(self.input_path),
                        *extra_arguments,
                    ]
                )

                self.assertEqual(exit_code, 2)
                self.assertEqual(output, "")
                self.assertIn(
                    "Input and output must be different files",
                    error_output,
                )
                self.assertEqual(self.input_path.read_bytes(), self.input_bytes)

    def test_roundtrip_refuses_existing_output_by_default(self) -> None:
        output_path = self.project_root / "output.pmx"
        output_path.write_bytes(b"existing output")

        exit_code, output, error_output = self.capture_run(
            ["roundtrip", str(self.input_path), str(output_path)]
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(output, "")
        self.assertIn("Output file already exists", error_output)
        self.assertEqual(output_path.read_bytes(), b"existing output")

    def test_roundtrip_explicit_overwrite_replaces_distinct_output(self) -> None:
        output_path = self.project_root / "output.pmx"
        output_path.write_bytes(b"existing output")

        exit_code, _, error_output = self.capture_run(
            [
                "roundtrip",
                str(self.input_path),
                str(output_path),
                "--overwrite",
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(error_output, "")
        self.assertEqual(output_path.read_bytes(), self.input_bytes)
        self.assertEqual(self.input_path.read_bytes(), self.input_bytes)

    def test_roundtrip_refuses_hardlink_alias_of_input(self) -> None:
        output_path = self.project_root / "alias.pmx"
        try:
            os.link(self.input_path, output_path)
        except OSError as error:
            self.skipTest(f"hardlinks are unavailable: {error}")

        exit_code, _, error_output = self.capture_run(
            [
                "roundtrip",
                str(self.input_path),
                str(output_path),
                "--overwrite",
            ]
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("Input and output must be different files", error_output)
        self.assertEqual(self.input_path.read_bytes(), self.input_bytes)

    def test_invalid_pmx_does_not_create_output(self) -> None:
        self.input_path.write_bytes(b"not a PMX")
        output_path = self.project_root / "output.pmx"

        exit_code, output, error_output = self.capture_run(
            ["roundtrip", str(self.input_path), str(output_path)]
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(output, "")
        self.assertIn("[ERROR] roundtrip:", error_output)
        self.assertFalse(output_path.exists())

    def test_missing_input_and_output_directory_are_path_errors(self) -> None:
        cases = (
            (
                self.project_root / "missing.pmx",
                self.project_root / "output.pmx",
                "Input file does not exist",
            ),
            (
                self.input_path,
                self.project_root / "missing" / "output.pmx",
                "Output directory does not exist",
            ),
        )
        for input_path, output_path, expected_error in cases:
            with self.subTest(expected_error=expected_error):
                exit_code, output, error_output = self.capture_run(
                    ["roundtrip", str(input_path), str(output_path)]
                )

                self.assertEqual(exit_code, 2)
                self.assertEqual(output, "")
                self.assertIn(expected_error, error_output)
                self.assertFalse(output_path.exists())

    def test_semantic_verification_failure_prevents_output(self) -> None:
        source_document = load_pmx(self.input_path)
        changed_info = replace(
            source_document.model_info,
            local_name="changed",
        )
        changed_document = replace(
            source_document,
            model_info=changed_info,
        )
        output_path = self.project_root / "output.pmx"

        with patch(
            "mmd_registry.pmx.roundtrip.load_pmx",
            side_effect=(source_document, changed_document),
        ):
            with self.assertRaises(PmxRoundTripVerificationError):
                roundtrip_pmx(self.input_path, output_path)

        self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()
