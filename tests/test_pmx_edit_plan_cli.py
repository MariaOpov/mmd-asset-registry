"""CLI tests for v0.8.2 edit-plan authoring and explain UX."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from mmd_registry.cli import main, normalize_arguments, run
from mmd_registry.pmx.editing.errors import PmxEditPlanError
from mmd_registry.pmx.editing.json_loader import parse_pmx_edit_plan_json


class PmxEditPlanCliTests(unittest.TestCase):
    """Lock authoring command names, streams, diagnostics, and UTF-8."""

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_directory.name)
        self.plan_path = self.project_root / "編集計画.json"
        self.write_plan(
            {
                "schema_version": 1,
                "expected_source_sha256": "a" * 64,
                "operations": [
                    {
                        "op": "set_model_info",
                        "local_name": "/home/alice/private/モデル名",
                    },
                    {
                        "op": "set_texture_path",
                        "texture_index": 2,
                        "path": r"C:\Users\Alice\private\texture.png",
                    },
                    {
                        "op": "update_material",
                        "material_index": 4,
                        "memo": "秘密 material value",
                    },
                ],
            }
        )

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def write_plan(self, payload: object) -> None:
        """Write one Unicode strict-plan candidate."""

        self.plan_path.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )

    def capture_run(
        self,
        arguments: list[str],
    ) -> tuple[int, str, str]:
        """Run the CLI with independent stdout/stderr capture."""

        output = io.StringIO()
        error_output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(error_output):
            exit_code = run(arguments)
        return exit_code, output.getvalue(), error_output.getvalue()

    def test_edit_plan_namespace_is_preserved_by_legacy_normalization(self) -> None:
        arguments = ["edit-plan", "catalog"]

        self.assertEqual(normalize_arguments(arguments), arguments)

    def test_legacy_edit_namespace_is_still_preserved(self) -> None:
        arguments = [
            "edit",
            "model.pmx",
            "--plan",
            "plan.json",
            "--dry-run",
        ]

        self.assertEqual(normalize_arguments(arguments), arguments)

    def test_catalog_text_is_deterministic_and_complete(self) -> None:
        exit_code, output, error_output = self.capture_run(
            ["edit-plan", "catalog"]
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(error_output, "")
        self.assertTrue(output.startswith("PMX EDIT OPERATION CATALOG\n"))
        self.assertIn("[0] set_model_info", output)
        self.assertIn("[1] set_texture_path", output)
        self.assertIn("[2] update_material", output)
        self.assertIn("texture_index: integer; required; selector", output)
        self.assertIn("drawing_flags: integer; optional; value", output)

        second_code, second_output, second_error = self.capture_run(
            ["edit-plan", "catalog"]
        )
        self.assertEqual(second_code, 0)
        self.assertEqual(second_error, "")
        self.assertEqual(output, second_output)

    def test_catalog_json_is_machine_readable_in_authoritative_order(self) -> None:
        exit_code, output, error_output = self.capture_run(
            ["edit-plan", "catalog", "--json"]
        )
        payload = json.loads(output)

        self.assertEqual(exit_code, 0)
        self.assertEqual(error_output, "")
        self.assertEqual(
            tuple(operation["type"] for operation in payload["operations"]),
            (
                "set_model_info",
                "set_texture_path",
                "update_material",
            ),
        )
        self.assertNotIn("object at", output)

    def test_template_without_operation_prints_non_executable_skeleton(self) -> None:
        exit_code, output, error_output = self.capture_run(
            ["edit-plan", "template"]
        )
        payload = json.loads(output)

        self.assertEqual(exit_code, 0)
        self.assertEqual(error_output, "")
        self.assertFalse(payload["_template"]["executable"])
        self.assertIsNone(payload["_template"]["operation_type"])
        self.assertEqual(payload["operations"], [])

        with self.assertRaises(PmxEditPlanError):
            parse_pmx_edit_plan_json(output)

    def test_template_operation_is_derived_from_catalog_choices(self) -> None:
        for operation_type in (
            "set_model_info",
            "set_texture_path",
            "update_material",
        ):
            with self.subTest(operation=operation_type):
                exit_code, output, error_output = self.capture_run(
                    ["edit-plan", "template", operation_type]
                )
                payload = json.loads(output)

                self.assertEqual(exit_code, 0)
                self.assertEqual(error_output, "")
                self.assertEqual(
                    payload["_template"]["operation_type"],
                    operation_type,
                )
                self.assertEqual(
                    payload["operations"][0]["op"],
                    operation_type,
                )
                self.assertFalse(payload["_template"]["executable"])

                with self.assertRaises(PmxEditPlanError):
                    parse_pmx_edit_plan_json(output)

    def test_unsupported_template_operation_is_parser_usage_error(self) -> None:
        output = io.StringIO()
        error_output = io.StringIO()

        with (
            redirect_stdout(output),
            redirect_stderr(error_output),
            self.assertRaises(SystemExit) as context,
        ):
            run(["edit-plan", "template", "rename_model"])

        self.assertEqual(context.exception.code, 2)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("invalid choice", error_output.getvalue())
        self.assertIn("set_model_info", error_output.getvalue())

    def test_explain_text_reports_intent_without_values_or_pmx_results(self) -> None:
        exit_code, output, error_output = self.capture_run(
            ["edit-plan", "explain", str(self.plan_path)]
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(error_output, "")
        self.assertTrue(output.startswith("PMX EDIT PLAN EXPLANATION\n"))
        self.assertIn("[0] set_model_info", output)
        self.assertIn("Target: model", output)
        self.assertIn("[1] set_texture_path", output)
        self.assertIn("Target: texture[2]", output)
        self.assertIn("[2] update_material", output)
        self.assertIn("Target: material[4]", output)
        self.assertIn("local_name", output)
        self.assertIn("path", output)
        self.assertIn("memo", output)
        self.assertIn("Expected source SHA-256: present", output)
        self.assertIn("Execution: not performed", output)

        for secret in (
            "/home/alice/private/モデル名",
            r"C:\Users\Alice\private\texture.png",
            "秘密 material value",
            "a" * 64,
            str(self.plan_path),
        ):
            self.assertNotIn(secret, output)

        self.assertNotIn("before", output.lower())
        self.assertNotIn("after", output.lower())

    def test_explain_json_has_stable_shape_and_hides_values(self) -> None:
        exit_code, output, error_output = self.capture_run(
            ["edit-plan", "explain", str(self.plan_path), "--json"]
        )
        payload = json.loads(output)

        self.assertEqual(exit_code, 0)
        self.assertEqual(error_output, "")
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["expected_source_sha256"])
        self.assertEqual(payload["operation_count"], 3)
        self.assertEqual(
            tuple(operation["target"] for operation in payload["operations"]),
            ("model", "texture[2]", "material[4]"),
        )

        for secret in (
            "/home/alice/private/モデル名",
            r"C:\Users\Alice\private\texture.png",
            "秘密 material value",
            "a" * 64,
            str(self.plan_path),
        ):
            self.assertNotIn(secret, output)

    def test_explain_decode_error_uses_plan_decode_and_stderr(self) -> None:
        self.plan_path.write_text(
            '{"schema_version":1,"operations":[',
            encoding="utf-8",
        )

        exit_code, output, error_output = self.capture_run(
            ["edit-plan", "explain", str(self.plan_path)]
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(output, "")
        self.assertIn(
            "[ERROR] edit-plan explain: "
            "plan_decode/edit_plan_decode_failed:",
            error_output,
        )
        self.assertNotIn("Traceback", error_output)
        self.assertNotIn(str(self.plan_path), error_output)

    def test_explain_validation_error_uses_plan_validate_json(self) -> None:
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
            [
                "edit-plan",
                "explain",
                str(self.plan_path),
                "--json",
            ]
        )
        payload = json.loads(output)

        self.assertEqual(exit_code, 1)
        self.assertEqual(error_output, "")
        self.assertEqual(payload["command"], "edit-plan")
        self.assertEqual(payload["action"], "explain")
        self.assertEqual(payload["error_type"], "invalid_plan")
        self.assertEqual(payload["error"]["phase"], "plan_validate")
        self.assertEqual(payload["error"]["code"], "edit_plan_invalid")
        self.assertEqual(
            payload["error"]["path"],
            '$.operations[0]["未知"]',
        )
        self.assertIn("未知", output)
        self.assertNotIn(str(self.plan_path), output)

    def test_explain_read_error_uses_plan_read_and_hides_os_details(self) -> None:
        with patch(
            "mmd_registry.cli.load_pmx_edit_plan",
            side_effect=PermissionError(13, "秘密 OS detail"),
        ):
            exit_code, output, error_output = self.capture_run(
                [
                    "edit-plan",
                    "explain",
                    str(self.plan_path),
                    "--json",
                ]
            )
        payload = json.loads(output)

        self.assertEqual(exit_code, 2)
        self.assertEqual(error_output, "")
        self.assertEqual(payload["error_type"], "io")
        self.assertEqual(payload["error"]["phase"], "plan_read")
        self.assertEqual(
            payload["error"]["code"],
            "edit_plan_read_failed",
        )
        self.assertEqual(
            payload["error"]["message"],
            "Unable to read edit-plan file.",
        )
        self.assertEqual(payload["error"]["details"], {"errno": 13})
        self.assertNotIn("秘密 OS detail", output)
        self.assertNotIn(str(self.plan_path), output)

    def test_unexpected_explain_failure_propagates_from_run(self) -> None:
        with patch(
            "mmd_registry.cli.explain_pmx_edit_plan",
            side_effect=RuntimeError("秘密 internal detail"),
        ):
            output = io.StringIO()
            error_output = io.StringIO()
            with (
                redirect_stdout(output),
                redirect_stderr(error_output),
                self.assertRaisesRegex(
                    RuntimeError,
                    "秘密 internal detail",
                ),
            ):
                run(
                    [
                        "edit-plan",
                        "explain",
                        str(self.plan_path),
                    ]
                )

        self.assertEqual(output.getvalue(), "")
        self.assertEqual(error_output.getvalue(), "")

    def test_process_boundary_internal_json_is_stable_and_hides_details(self) -> None:
        output = io.StringIO()
        error_output = io.StringIO()
        with (
            patch.object(
                sys,
                "argv",
                [
                    "check_assets.py",
                    "edit-plan",
                    "explain",
                    "秘密-plan.json",
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
        self.assertEqual(payload["command"], "edit-plan")
        self.assertEqual(payload["action"], "explain")
        self.assertEqual(payload["error_type"], "internal")
        self.assertEqual(payload["error"]["phase"], "internal")
        self.assertEqual(payload["error"]["code"], "edit_internal_error")
        self.assertNotIn("秘密 implementation detail", output.getvalue())
        self.assertNotIn("秘密-plan.json", output.getvalue())

    def test_process_boundary_internal_text_is_stable_and_hides_details(self) -> None:
        output = io.StringIO()
        error_output = io.StringIO()
        with (
            patch.object(
                sys,
                "argv",
                ["check_assets.py", "edit-plan", "catalog"],
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
            "[ERROR] edit-plan catalog: "
            "internal/edit_internal_error: "
            "Unexpected internal edit-plan failure.",
            error_output.getvalue(),
        )
        self.assertNotIn(
            "秘密 implementation detail",
            error_output.getvalue(),
        )

    def test_redirected_template_output_is_utf8_decodable(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [
                sys.executable,
                "check_assets.py",
                "edit-plan",
                "template",
                "set_model_info",
            ],
            cwd=repository_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        output = result.stdout.decode("utf-8")
        error_output = result.stderr.decode("utf-8")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(error_output, "")
        self.assertIn("モデル名", output)
        self.assertFalse(json.loads(output)["_template"]["executable"])

    def test_redirected_unicode_validation_error_is_utf8_json(self) -> None:
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
        repository_root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [
                sys.executable,
                "check_assets.py",
                "edit-plan",
                "explain",
                str(self.plan_path),
                "--json",
            ],
            cwd=repository_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        output = result.stdout.decode("utf-8")
        error_output = result.stderr.decode("utf-8")
        payload = json.loads(output)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(error_output, "")
        self.assertIn("未知", output)
        self.assertEqual(
            payload["error"]["path"],
            '$.operations[0]["未知"]',
        )


if __name__ == "__main__":
    unittest.main()
