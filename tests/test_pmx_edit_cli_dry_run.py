"""Tests for the safe PMX edit dry-run CLI command."""

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
from mmd_registry.pmx.editing import PmxEditVerificationError
from tests.mmd_fixtures import build_pmx_bone, build_pmx_structure


class PmxEditDryRunCliTests(unittest.TestCase):
    """Validate command wiring, reports, errors, and no-output behavior."""

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_directory.name)
        self.input_path = self.project_root / "入力モデル.pmx"
        self.input_bytes = build_pmx_structure(
            bones=(build_pmx_bone(),),
        )
        self.input_path.write_bytes(self.input_bytes)
        self.plan_path = self.project_root / "編集計画.json"
        self.write_plan(
            {
                "schema_version": 1,
                "operations": [
                    {
                        "op": "set_model_info",
                        "local_name": "モデル 🌸",
                    }
                ],
            }
        )

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def write_plan(self, payload: object) -> None:
        """Write one Unicode JSON plan to the test plan path."""

        self.plan_path.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )

    def capture_run(
        self,
        arguments: list[str],
    ) -> tuple[int, str, str]:
        """Run the CLI and capture both output streams."""

        output = io.StringIO()
        error_output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(error_output):
            exit_code = run(arguments)
        return exit_code, output.getvalue(), error_output.getvalue()

    def dry_run_arguments(self, *extra: str) -> list[str]:
        """Return the common successful edit dry-run arguments."""

        return [
            "edit",
            str(self.input_path),
            "--plan",
            str(self.plan_path),
            "--dry-run",
            *extra,
        ]

    def test_edit_command_is_preserved_by_legacy_normalization(self) -> None:
        arguments = self.dry_run_arguments()

        self.assertEqual(normalize_arguments(arguments), arguments)

    def test_text_dry_run_is_compact_and_creates_no_output(self) -> None:
        output_path = self.project_root / "should-not-exist.pmx"
        source_snapshot = self.input_path.read_bytes()
        plan_snapshot = self.plan_path.read_bytes()

        exit_code, output, error_output = self.capture_run(
            [
                "edit",
                str(self.input_path),
                str(output_path),
                "--plan",
                str(self.plan_path),
                "--dry-run",
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(error_output, "")
        self.assertTrue(output.startswith("PMX EDIT PREVIEW\n"))
        self.assertIn("Status: 1 field changed", output)
        self.assertIn("Model: 1 field changed", output)
        self.assertIn("Output written: no (dry-run)", output)
        self.assertNotIn("Changes:", output)
        self.assertFalse(output_path.exists())
        self.assertEqual(self.input_path.read_bytes(), source_snapshot)
        self.assertEqual(self.plan_path.read_bytes(), plan_snapshot)

    def test_json_dry_run_is_machine_readable_and_unicode_safe(self) -> None:
        exit_code, output, error_output = self.capture_run(
            self.dry_run_arguments("--json")
        )
        payload = json.loads(output)

        self.assertEqual(exit_code, 0)
        self.assertEqual(error_output, "")
        self.assertEqual(payload["status"], "changes_pending")
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["output"], {"written": False, "sha256": None})
        self.assertEqual(payload["verification"]["semantic"], "passed")
        self.assertEqual(
            payload["audit"]["changes"][0]["after"],
            "モデル 🌸",
        )
        self.assertIn("モデル 🌸", output)

    def test_noop_preview_succeeds_with_explicit_status(self) -> None:
        self.write_plan(
            {
                "schema_version": 1,
                "operations": [
                    {
                        "op": "set_model_info",
                        "local_name": "Test PMX Model",
                    }
                ],
            }
        )

        exit_code, output, error_output = self.capture_run(
            self.dry_run_arguments()
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(error_output, "")
        self.assertIn("Status: no changes", output)
        self.assertIn("Model: 0 fields changed", output)

    def test_existing_requested_output_is_never_touched_in_dry_run(self) -> None:
        output_path = self.project_root / "existing-output.pmx"
        output_path.write_bytes(b"existing output")

        exit_code, _, error_output = self.capture_run(
            [
                "edit",
                str(self.input_path),
                str(output_path),
                "--plan",
                str(self.plan_path),
                "--dry-run",
                "--overwrite",
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(error_output, "")
        self.assertEqual(output_path.read_bytes(), b"existing output")

    def test_expected_source_hash_match_and_mismatch(self) -> None:
        actual_hash = hashlib.sha256(self.input_bytes).hexdigest()
        operation = {
            "op": "set_model_info",
            "local_name": "Hash verified",
        }
        for expected_hash, expected_code in (
            (actual_hash, 0),
            ("0" * 64, 1),
        ):
            with self.subTest(expected_hash=expected_hash):
                self.write_plan(
                    {
                        "schema_version": 1,
                        "expected_source_sha256": expected_hash,
                        "operations": [operation],
                    }
                )
                exit_code, _, error_output = self.capture_run(
                    self.dry_run_arguments()
                )

                self.assertEqual(exit_code, expected_code)
                if expected_code:
                    self.assertIn("source SHA-256 mismatch", error_output)
                else:
                    self.assertEqual(error_output, "")

    def test_invalid_plan_is_a_data_error_without_traceback(self) -> None:
        self.plan_path.write_text(
            '{"schema_version":1,"operations":[',
            encoding="utf-8",
        )

        exit_code, output, error_output = self.capture_run(
            self.dry_run_arguments()
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(output, "")
        self.assertIn("[ERROR] edit:", error_output)
        self.assertIn("invalid JSON", error_output)
        self.assertNotIn("Traceback", error_output)

    def test_invalid_plan_json_error_is_machine_readable(self) -> None:
        self.write_plan(
            {
                "schema_version": 1,
                "operations": [
                    {"op": "rename_model", "local_name": "invalid"}
                ],
            }
        )

        exit_code, output, error_output = self.capture_run(
            self.dry_run_arguments("--json")
        )
        payload = json.loads(output)

        self.assertEqual(exit_code, 1)
        self.assertEqual(error_output, "")
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error_type"], "invalid_plan")
        self.assertTrue(payload["dry_run"])
        self.assertIn("unsupported operation", payload["errors"][0])

    def test_invalid_pmx_is_a_data_error_and_creates_no_output(self) -> None:
        self.input_path.write_bytes(b"not a PMX")
        output_path = self.project_root / "output.pmx"

        exit_code, output, error_output = self.capture_run(
            [
                "edit",
                str(self.input_path),
                str(output_path),
                "--plan",
                str(self.plan_path),
                "--dry-run",
            ]
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(output, "")
        self.assertIn("[ERROR] edit:", error_output)
        self.assertFalse(output_path.exists())

    def test_missing_or_directory_inputs_are_path_errors(self) -> None:
        missing = self.project_root / "missing.pmx"
        cases = (
            (missing, self.plan_path, "Input file does not exist"),
            (self.project_root, self.plan_path, "Input path is not a file"),
            (
                self.input_path,
                self.project_root / "missing.json",
                "Plan file does not exist",
            ),
            (
                self.input_path,
                self.project_root,
                "Plan path is not a file",
            ),
        )
        for input_path, plan_path, reason in cases:
            with self.subTest(reason=reason):
                exit_code, output, error_output = self.capture_run(
                    [
                        "edit",
                        str(input_path),
                        "--plan",
                        str(plan_path),
                        "--dry-run",
                    ]
                )

                self.assertEqual(exit_code, 2)
                self.assertEqual(output, "")
                self.assertIn(reason, error_output)

    def test_overwrite_without_output_is_usage_error(self) -> None:
        exit_code, output, error_output = self.capture_run(
            self.dry_run_arguments("--overwrite")
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(output, "")
        self.assertIn("--overwrite requires an output path", error_output)

    def test_write_mode_is_not_enabled_by_dry_run_checkpoint(self) -> None:
        output_path = self.project_root / "output.pmx"
        cases = (
            (
                [
                    "edit",
                    str(self.input_path),
                    "--plan",
                    str(self.plan_path),
                ],
                "Output path is required unless --dry-run",
            ),
            (
                [
                    "edit",
                    str(self.input_path),
                    str(output_path),
                    "--plan",
                    str(self.plan_path),
                ],
                "write mode is not available",
            ),
        )
        for arguments, reason in cases:
            with self.subTest(reason=reason):
                exit_code, output, error_output = self.capture_run(arguments)

                self.assertEqual(exit_code, 2)
                self.assertEqual(output, "")
                self.assertIn(reason, error_output)
                self.assertFalse(output_path.exists())

    def test_verification_failure_returns_one_without_output(self) -> None:
        output_path = self.project_root / "output.pmx"
        with patch(
            "mmd_registry.cli.dry_run_pmx_edit",
            side_effect=PmxEditVerificationError("simulated mismatch"),
        ):
            exit_code, output, error_output = self.capture_run(
                [
                    "edit",
                    str(self.input_path),
                    str(output_path),
                    "--plan",
                    str(self.plan_path),
                    "--dry-run",
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(output, "")
        self.assertIn("simulated mismatch", error_output)
        self.assertFalse(output_path.exists())

    def test_unexpected_failure_returns_three_without_traceback(self) -> None:
        with patch(
            "mmd_registry.cli.dry_run_pmx_edit",
            side_effect=RuntimeError("simulated internal failure"),
        ):
            exit_code, output, error_output = self.capture_run(
                self.dry_run_arguments()
            )

        self.assertEqual(exit_code, 3)
        self.assertEqual(output, "")
        self.assertIn("Internal edit failure", error_output)
        self.assertIn("simulated internal failure", error_output)
        self.assertNotIn("Traceback", error_output)

    def test_internal_loader_failure_returns_three_without_traceback(self) -> None:
        with patch(
            "mmd_registry.cli.load_pmx_edit_plan",
            side_effect=RuntimeError("simulated loader failure"),
        ):
            exit_code, output, error_output = self.capture_run(
                self.dry_run_arguments()
            )

        self.assertEqual(exit_code, 3)
        self.assertEqual(output, "")
        self.assertIn("Internal plan-load failure", error_output)
        self.assertNotIn("Traceback", error_output)

    def test_internal_renderer_failure_returns_three(self) -> None:
        with patch(
            "mmd_registry.cli.render_pmx_edit_preview_text",
            side_effect=RuntimeError("simulated renderer failure"),
        ):
            exit_code, output, error_output = self.capture_run(
                self.dry_run_arguments()
            )

        self.assertEqual(exit_code, 3)
        self.assertEqual(output, "")
        self.assertIn("Internal preview-render failure", error_output)

    def test_internal_json_failure_is_machine_readable(self) -> None:
        with patch(
            "mmd_registry.cli.dry_run_pmx_edit",
            side_effect=RuntimeError("simulated internal failure"),
        ):
            exit_code, output, error_output = self.capture_run(
                self.dry_run_arguments("--json")
            )
        payload = json.loads(output)

        self.assertEqual(exit_code, 3)
        self.assertEqual(error_output, "")
        self.assertEqual(payload["error_type"], "internal")
        self.assertIn("simulated internal failure", payload["errors"][0])

    def test_plan_argument_is_required_by_parser(self) -> None:
        output = io.StringIO()
        error_output = io.StringIO()
        with (
            redirect_stdout(output),
            redirect_stderr(error_output),
            self.assertRaises(SystemExit) as context,
        ):
            run(["edit", str(self.input_path), "--dry-run"])

        self.assertEqual(context.exception.code, 2)
        self.assertIn("--plan", error_output.getvalue())


if __name__ == "__main__":
    unittest.main()
