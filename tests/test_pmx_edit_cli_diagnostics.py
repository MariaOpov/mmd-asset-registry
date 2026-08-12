"""Tests for the structured failure contract of the PMX edit CLI."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from mmd_registry.cli import main, run
from tests.mmd_fixtures import build_pmx_bone, build_pmx_structure


class PmxEditCliDiagnosticTests(unittest.TestCase):
    """Validate phases, JSON paths, streams, and safe failure messages."""

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_directory.name)
        self.input_path = self.project_root / "入力モデル.pmx"
        self.input_path.write_bytes(
            build_pmx_structure(
                bones=(build_pmx_bone(),),
            )
        )
        self.plan_path = self.project_root / "編集計画.json"
        self.write_plan(
            {
                "schema_version": 1,
                "operations": [
                    {
                        "op": "set_model_info",
                        "local_name": "安全モデル 🌸",
                    }
                ],
            }
        )

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def write_plan(self, payload: object) -> None:
        """Write one UTF-8 JSON plan."""

        self.plan_path.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )

    def capture_run(self, arguments: list[str]) -> tuple[int, str, str]:
        """Run the CLI while capturing stdout and stderr independently."""

        output = io.StringIO()
        error_output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(error_output):
            exit_code = run(arguments)
        return exit_code, output.getvalue(), error_output.getvalue()

    def dry_run_arguments(self, *extra: str) -> list[str]:
        """Return common dry-run arguments."""

        return [
            "edit",
            str(self.input_path),
            "--plan",
            str(self.plan_path),
            "--dry-run",
            *extra,
        ]

    def test_text_decode_error_reports_phase_and_code_on_stderr(self) -> None:
        self.plan_path.write_text(
            '{"schema_version":1,"operations":[',
            encoding="utf-8",
        )

        exit_code, output, error_output = self.capture_run(
            self.dry_run_arguments()
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(output, "")
        self.assertIn(
            "[ERROR] edit: plan_decode/edit_plan_decode_failed:",
            error_output,
        )
        self.assertIn("invalid JSON", error_output)
        self.assertNotIn("Traceback", error_output)

    def test_json_validation_error_extends_legacy_shape_with_diagnostic(self) -> None:
        self.write_plan(
            {
                "schema_version": 1,
                "operations": [
                    {
                        "op": "rename_model",
                        "local_name": "invalid",
                    }
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
        self.assertEqual(
            payload["error"],
            {
                "code": "edit_plan_invalid",
                "phase": "plan_validate",
                "message": "unsupported operation name 'rename_model'.",
                "operation_index": 0,
                "path": "$.operations[0].op",
            },
        )

    def test_unicode_unknown_field_has_unicode_safe_json_path(self) -> None:
        self.write_plan(
            {
                "schema_version": 1,
                "operations": [
                    {
                        "op": "set_model_info",
                        "local_name": "モデル",
                        "未知": "値",
                    }
                ],
            }
        )

        exit_code, output, error_output = self.capture_run(
            self.dry_run_arguments("--json")
        )
        payload = json.loads(output)

        self.assertEqual(exit_code, 1)
        self.assertEqual(error_output, "")
        self.assertEqual(payload["error"]["phase"], "plan_validate")
        self.assertEqual(
            payload["error"]["path"],
            '$.operations[0]["未知"]',
        )
        self.assertIn("未知", output)
        self.assertNotIn("\\u672a", output)

    def test_source_hash_mismatch_is_a_preflight_diagnostic(self) -> None:
        self.write_plan(
            {
                "schema_version": 1,
                "expected_source_sha256": "0" * 64,
                "operations": [
                    {
                        "op": "set_model_info",
                        "local_name": "hash mismatch",
                    }
                ],
            }
        )

        exit_code, output, error_output = self.capture_run(
            self.dry_run_arguments("--json")
        )
        payload = json.loads(output)

        self.assertEqual(exit_code, 1)
        self.assertEqual(error_output, "")
        self.assertEqual(payload["error_type"], "invalid_plan")
        self.assertEqual(payload["error"]["code"], "edit_preflight_failed")
        self.assertEqual(payload["error"]["phase"], "preflight")
        self.assertEqual(
            payload["error"]["path"],
            "$.expected_source_sha256",
        )
        self.assertIn("source SHA-256 mismatch", payload["error"]["message"])

    def test_invalid_pmx_is_reported_as_source_parse_failure(self) -> None:
        self.input_path.write_bytes(b"not a PMX")
        output_path = self.project_root / "never-created.pmx"

        exit_code, output, error_output = self.capture_run(
            [
                "edit",
                str(self.input_path),
                str(output_path),
                "--plan",
                str(self.plan_path),
                "--dry-run",
                "--json",
            ]
        )
        payload = json.loads(output)

        self.assertEqual(exit_code, 1)
        self.assertEqual(error_output, "")
        self.assertEqual(payload["error_type"], "invalid_pmx")
        self.assertEqual(payload["error"]["code"], "source_invalid")
        self.assertEqual(payload["error"]["phase"], "source_parse")
        self.assertFalse(output_path.exists())

    def test_write_path_policy_failure_is_a_preflight_diagnostic(self) -> None:
        output_path = self.project_root / "output.bin"

        exit_code, output, error_output = self.capture_run(
            [
                "edit",
                str(self.input_path),
                str(output_path),
                "--plan",
                str(self.plan_path),
                "--json",
            ]
        )
        payload = json.loads(output)

        self.assertEqual(exit_code, 2)
        self.assertEqual(error_output, "")
        self.assertEqual(payload["error_type"], "path_policy")
        self.assertEqual(payload["error"]["code"], "edit_preflight_failed")
        self.assertEqual(payload["error"]["phase"], "preflight")
        self.assertFalse(output_path.exists())

    def test_source_read_error_does_not_leak_os_exception_text(self) -> None:
        with patch.object(
            Path,
            "read_bytes",
            side_effect=PermissionError(13, "秘密 OS detail"),
        ):
            exit_code, output, error_output = self.capture_run(
                self.dry_run_arguments("--json")
            )
        payload = json.loads(output)

        self.assertEqual(exit_code, 2)
        self.assertEqual(error_output, "")
        self.assertEqual(payload["error_type"], "io")
        self.assertEqual(payload["error"]["code"], "source_read_failed")
        self.assertEqual(payload["error"]["phase"], "source_read")
        self.assertEqual(
            payload["error"]["message"],
            "Unable to read source PMX file.",
        )
        self.assertEqual(payload["error"]["details"], {"errno": 13})
        self.assertNotIn("秘密 OS detail", output)

    def test_plan_read_error_does_not_leak_os_exception_text(self) -> None:
        with patch.object(
            Path,
            "read_text",
            side_effect=PermissionError(13, "秘密 plan detail"),
        ):
            exit_code, output, error_output = self.capture_run(
                self.dry_run_arguments("--json")
            )
        payload = json.loads(output)

        self.assertEqual(exit_code, 2)
        self.assertEqual(error_output, "")
        self.assertEqual(payload["error_type"], "io")
        self.assertEqual(payload["error"]["code"], "edit_plan_read_failed")
        self.assertEqual(payload["error"]["phase"], "plan_read")
        self.assertEqual(
            payload["error"]["message"],
            "Unable to read edit-plan file.",
        )
        self.assertEqual(payload["error"]["details"], {"errno": 13})
        self.assertNotIn("秘密 plan detail", output)

    def test_process_boundary_internal_json_is_stable_and_hides_details(self) -> None:
        output = io.StringIO()
        error_output = io.StringIO()
        with (
            patch.object(
                sys,
                "argv",
                [
                    "check_assets.py",
                    "edit",
                    "model.pmx",
                    "--plan",
                    "plan.json",
                    "--dry-run",
                    "--json",
                ],
            ),
            patch(
                "mmd_registry.cli.run",
                side_effect=RuntimeError("秘密 implementation detail"),
            ),
            redirect_stdout(output),
            redirect_stderr(error_output),
            self.assertRaises(SystemExit) as context,
        ):
            main()

        payload = json.loads(output.getvalue())
        self.assertEqual(context.exception.code, 3)
        self.assertEqual(error_output.getvalue(), "")
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error_type"], "internal")
        self.assertEqual(
            payload["error"],
            {
                "code": "edit_internal_error",
                "phase": "internal",
                "message": "Unexpected internal edit failure.",
            },
        )
        self.assertNotIn("秘密 implementation detail", output.getvalue())

    def test_process_boundary_internal_text_is_stable_and_hides_details(self) -> None:
        output = io.StringIO()
        error_output = io.StringIO()
        with (
            patch.object(
                sys,
                "argv",
                [
                    "check_assets.py",
                    "edit",
                    "model.pmx",
                    "--plan",
                    "plan.json",
                    "--dry-run",
                ],
            ),
            patch(
                "mmd_registry.cli.run",
                side_effect=RuntimeError("秘密 implementation detail"),
            ),
            redirect_stdout(output),
            redirect_stderr(error_output),
            self.assertRaises(SystemExit) as context,
        ):
            main()

        self.assertEqual(context.exception.code, 3)
        self.assertEqual(output.getvalue(), "")
        self.assertIn(
            "[ERROR] edit: internal/edit_internal_error: "
            "Unexpected internal edit failure.",
            error_output.getvalue(),
        )
        self.assertNotIn("秘密 implementation detail", error_output.getvalue())


if __name__ == "__main__":
    unittest.main()
