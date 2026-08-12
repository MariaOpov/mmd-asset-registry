"""Authoring failure and regression matrix for PMX edit-plan UX."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from mmd_registry.cli import run
from mmd_registry.pmx.editing.catalog import get_pmx_edit_operation_catalog


class PmxEditPlanAuthoringFailureMatrixTests(unittest.TestCase):
    """Lock strict failures, diagnostic context, and authoring-only safety."""

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_directory.name)
        self.plan_path = self.project_root / "編集計画.json"

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def capture_run(
        self,
        arguments: list[str],
    ) -> tuple[int, str, str]:
        output = io.StringIO()
        error_output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(error_output):
            exit_code = run(arguments)
        return exit_code, output.getvalue(), error_output.getvalue()

    def write_text(self, text: str) -> None:
        self.plan_path.write_text(text, encoding="utf-8")

    def write_json(self, payload: object) -> None:
        self.write_text(json.dumps(payload, ensure_ascii=False))

    def explain_json(self) -> tuple[int, str, str, dict[str, object]]:
        exit_code, output, error_output = self.capture_run(
            ["edit-plan", "explain", str(self.plan_path), "--json"]
        )
        return exit_code, output, error_output, json.loads(output)

    def assert_failure(
        self,
        result: tuple[int, str, str, dict[str, object]],
        *,
        expected_exit: int,
        phase: str,
        code: str,
        path: str | None = None,
        operation_index: int | None = None,
        operation_type: str | None = None,
    ) -> dict[str, object]:
        exit_code, output, error_output, payload = result
        self.assertEqual(exit_code, expected_exit)
        self.assertEqual(error_output, "")
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["command"], "edit-plan")
        self.assertEqual(payload["action"], "explain")
        self.assertNotIn("Traceback", output)
        self.assertNotIn(str(self.plan_path), output)

        error = payload["error"]
        self.assertIsInstance(error, dict)
        assert isinstance(error, dict)
        self.assertEqual(error["phase"], phase)
        self.assertEqual(error["code"], code)

        if path is None:
            self.assertNotIn("path", error)
        else:
            self.assertEqual(error["path"], path)

        if operation_index is None:
            self.assertNotIn("operation_index", error)
        else:
            self.assertEqual(error["operation_index"], operation_index)

        if operation_type is None:
            self.assertNotIn("operation_type", error)
        else:
            self.assertEqual(error["operation_type"], operation_type)

        return error

    def test_decode_failure_matrix(self) -> None:
        cases = (
            ("empty", b"", "document is empty"),
            ("whitespace", b" \r\n\t ", "document is empty"),
            (
                "malformed_json",
                b'{"schema_version":1,"operations":[',
                "invalid JSON",
            ),
            (
                "duplicate_key",
                (
                    b'{"schema_version":1,"schema_version":1,'
                    b'"operations":[{"op":"set_model_info",'
                    b'"local_name":"A"}]}'
                ),
                "duplicate JSON member",
            ),
            (
                "nan",
                (
                    b'{"schema_version":1,"operations":['
                    b'{"op":"update_material","material_index":0,'
                    b'"edge_scale":NaN}]}'
                ),
                "not valid JSON",
            ),
            (
                "infinity",
                (
                    b'{"schema_version":1,"operations":['
                    b'{"op":"update_material","material_index":0,'
                    b'"edge_scale":Infinity}]}'
                ),
                "not valid JSON",
            ),
            ("malformed_utf8", b"\xff\xfe\xfa", "valid UTF-8"),
        )

        for name, raw_bytes, message_fragment in cases:
            with self.subTest(name=name):
                self.plan_path.write_bytes(raw_bytes)
                error = self.assert_failure(
                    self.explain_json(),
                    expected_exit=1,
                    phase="plan_decode",
                    code="edit_plan_decode_failed",
                )
                self.assertIn(message_fragment, error["message"])

    def test_top_level_validation_failure_matrix(self) -> None:
        cases = (
            (
                "wrong_top_level_type",
                [],
                None,
                "top-level JSON value must be an object",
            ),
            (
                "unknown_top_level_field",
                {
                    "schema_version": 1,
                    "operations": [
                        {"op": "set_model_info", "local_name": "A"}
                    ],
                    "surprise": True,
                },
                "$.surprise",
                "unknown field",
            ),
            (
                "invalid_sha256",
                {
                    "schema_version": 1,
                    "expected_source_sha256": "ABC",
                    "operations": [
                        {"op": "set_model_info", "local_name": "A"}
                    ],
                },
                "$.expected_source_sha256",
                "64 lowercase hexadecimal",
            ),
            (
                "empty_operations",
                {"schema_version": 1, "operations": []},
                "$.operations",
                "at least one operation",
            ),
        )

        for name, candidate, expected_path, message_fragment in cases:
            with self.subTest(name=name):
                self.write_json(candidate)
                error = self.assert_failure(
                    self.explain_json(),
                    expected_exit=1,
                    phase="plan_validate",
                    code="edit_plan_invalid",
                    path=expected_path,
                )
                self.assertIn(message_fragment, error["message"])

    def test_supported_operation_failures_include_index_type_and_path(self) -> None:
        cases = (
            (
                "unknown_field",
                {
                    "schema_version": 1,
                    "operations": [
                        {
                            "op": "set_model_info",
                            "local_name": "A",
                            "unknown": "B",
                        }
                    ],
                },
                0,
                "set_model_info",
                "$.operations[0].unknown",
            ),
            (
                "wrong_exact_integer_type",
                {
                    "schema_version": 1,
                    "operations": [
                        {"op": "set_model_info", "local_name": "A"},
                        {
                            "op": "set_texture_path",
                            "texture_index": True,
                            "path": "textures/a.png",
                        },
                    ],
                },
                1,
                "set_texture_path",
                "$.operations[1].texture_index",
            ),
            (
                "missing_required_field",
                {
                    "schema_version": 1,
                    "operations": [
                        {"op": "set_texture_path", "texture_index": 0}
                    ],
                },
                0,
                "set_texture_path",
                "$.operations[0].path",
            ),
            (
                "wrong_exact_float_type",
                {
                    "schema_version": 1,
                    "operations": [
                        {
                            "op": "update_material",
                            "material_index": 0,
                            "edge_scale": 1,
                        }
                    ],
                },
                0,
                "update_material",
                "$.operations[0].edge_scale",
            ),
        )

        for name, candidate, index, op_type, expected_path in cases:
            with self.subTest(name=name):
                self.write_json(candidate)
                self.assert_failure(
                    self.explain_json(),
                    expected_exit=1,
                    phase="plan_validate",
                    code="edit_plan_invalid",
                    path=expected_path,
                    operation_index=index,
                    operation_type=op_type,
                )

    def test_duplicate_target_includes_second_operation_context(self) -> None:
        self.write_json(
            {
                "schema_version": 1,
                "operations": [
                    {"op": "set_model_info", "local_name": "A"},
                    {"op": "set_model_info", "local_name": "B"},
                ],
            }
        )
        error = self.assert_failure(
            self.explain_json(),
            expected_exit=1,
            phase="plan_validate",
            code="edit_plan_invalid",
            path="$.operations[1].local_name",
            operation_index=1,
            operation_type="set_model_info",
        )
        self.assertIn("duplicate write", error["message"])

    def test_invalid_operation_does_not_invent_canonical_type(self) -> None:
        self.write_json(
            {
                "schema_version": 1,
                "operations": [
                    {"op": "rename_model", "local_name": "invalid"}
                ],
            }
        )
        error = self.assert_failure(
            self.explain_json(),
            expected_exit=1,
            phase="plan_validate",
            code="edit_plan_invalid",
            path="$.operations[0].op",
            operation_index=0,
        )
        self.assertIn("unsupported operation", error["message"])

    def test_template_marker_is_rejected_by_explain(self) -> None:
        code, template_text, template_error = self.capture_run(
            ["edit-plan", "template", "set_texture_path"]
        )
        self.assertEqual(code, 0)
        self.assertEqual(template_error, "")
        self.plan_path.write_text(template_text, encoding="utf-8")

        error = self.assert_failure(
            self.explain_json(),
            expected_exit=1,
            phase="plan_validate",
            code="edit_plan_invalid",
            path="$._template",
        )
        self.assertIn("unknown field", error["message"])

    def test_removing_template_marker_still_leaves_invalid_placeholders(self) -> None:
        code, template_text, template_error = self.capture_run(
            ["edit-plan", "template", "set_texture_path"]
        )
        self.assertEqual(code, 0)
        self.assertEqual(template_error, "")

        candidate = json.loads(template_text)
        del candidate["_template"]
        self.write_json(candidate)

        error = self.assert_failure(
            self.explain_json(),
            expected_exit=1,
            phase="plan_validate",
            code="edit_plan_invalid",
            path="$.operations[0].texture_index",
            operation_index=0,
            operation_type="set_texture_path",
        )
        self.assertIn("JSON integer", error["message"])

    def test_failure_json_and_text_are_deterministic(self) -> None:
        self.write_json(
            {
                "schema_version": 1,
                "operations": [
                    {
                        "op": "set_texture_path",
                        "texture_index": True,
                        "path": "textures/a.png",
                    }
                ],
            }
        )
        json_args = [
            "edit-plan",
            "explain",
            str(self.plan_path),
            "--json",
        ]
        first_json = self.capture_run(json_args)
        second_json = self.capture_run(json_args)
        self.assertEqual(first_json, second_json)
        self.assertEqual(first_json[0], 1)
        self.assertEqual(first_json[2], "")

        self.write_text('{"schema_version":1,"operations":[')
        text_args = ["edit-plan", "explain", str(self.plan_path)]
        first_text = self.capture_run(text_args)
        second_text = self.capture_run(text_args)
        self.assertEqual(first_text, second_text)
        self.assertEqual(first_text[0], 1)
        self.assertEqual(first_text[1], "")
        self.assertIn(
            "plan_decode/edit_plan_decode_failed:",
            first_text[2],
        )
        self.assertNotIn("Traceback", first_text[2])
        self.assertNotIn(str(self.plan_path), first_text[2])

    def test_cli_catalog_and_templates_follow_authoritative_catalog(self) -> None:
        catalog = get_pmx_edit_operation_catalog()
        operation_types = tuple(
            entry.operation_type for entry in catalog.operations
        )

        code, output, error_output = self.capture_run(
            ["edit-plan", "catalog", "--json"]
        )
        payload = json.loads(output)
        self.assertEqual(code, 0)
        self.assertEqual(error_output, "")
        self.assertEqual(
            tuple(entry["type"] for entry in payload["operations"]),
            operation_types,
        )

        for operation_type in operation_types:
            with self.subTest(operation=operation_type):
                code, template_text, template_error = self.capture_run(
                    ["edit-plan", "template", operation_type]
                )
                template_payload = json.loads(template_text)
                self.assertEqual(code, 0)
                self.assertEqual(template_error, "")
                self.assertFalse(
                    template_payload["_template"]["executable"]
                )
                self.assertEqual(
                    template_payload["_template"]["operation_type"],
                    operation_type,
                )
                self.assertEqual(
                    template_payload["operations"][0]["op"],
                    operation_type,
                )

    def test_authoring_only_commands_never_touch_pmx_io_or_create_files(self) -> None:
        self.write_json(
            {
                "schema_version": 1,
                "operations": [
                    {"op": "set_model_info", "local_name": "モデル"}
                ],
            }
        )
        sentinel_path = self.project_root / "private-model.pmx"
        sentinel_bytes = b"private PMX sentinel bytes"
        sentinel_path.write_bytes(sentinel_bytes)
        before_names = sorted(
            path.name for path in self.project_root.iterdir()
        )

        with (
            patch(
                "mmd_registry.cli.dry_run_pmx_edit",
                side_effect=AssertionError("dry-run PMX path must not run"),
            ),
            patch(
                "mmd_registry.cli.write_pmx_edit",
                side_effect=AssertionError("PMX write path must not run"),
            ),
            patch(
                "mmd_registry.cli.scan_pmx_structure",
                side_effect=AssertionError("PMX scan path must not run"),
            ),
            patch(
                "mmd_registry.pmx.editing.engine.apply_pmx_edit_plan",
                side_effect=AssertionError("PMX apply path must not run"),
            ),
        ):
            commands = (
                ["edit-plan", "catalog"],
                ["edit-plan", "catalog", "--json"],
                ["edit-plan", "template"],
                ["edit-plan", "template", "set_model_info"],
                ["edit-plan", "explain", str(self.plan_path)],
                ["edit-plan", "explain", str(self.plan_path), "--json"],
            )
            for command in commands:
                with self.subTest(command=command):
                    code, _, error_output = self.capture_run(list(command))
                    self.assertEqual(code, 0)
                    self.assertEqual(error_output, "")

        after_names = sorted(
            path.name for path in self.project_root.iterdir()
        )
        self.assertEqual(before_names, after_names)
        self.assertEqual(sentinel_path.read_bytes(), sentinel_bytes)

    def test_missing_plan_is_plan_read_without_path_leak(self) -> None:
        missing_path = self.project_root / "秘密-missing-plan.json"
        exit_code, output, error_output = self.capture_run(
            [
                "edit-plan",
                "explain",
                str(missing_path),
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
        self.assertNotIn(str(missing_path), output)
        self.assertNotIn("Traceback", output)

    def test_legacy_edit_invalid_operation_diagnostic_shape_is_unchanged(self) -> None:
        source_path = self.project_root / "source.pmx"
        source_path.write_bytes(b"not reached for invalid plan")
        self.write_json(
            {
                "schema_version": 1,
                "operations": [
                    {"op": "rename_model", "local_name": "invalid"}
                ],
            }
        )

        exit_code, output, error_output = self.capture_run(
            [
                "edit",
                str(source_path),
                "--plan",
                str(self.plan_path),
                "--dry-run",
                "--json",
            ]
        )
        payload = json.loads(output)

        self.assertEqual(exit_code, 1)
        self.assertEqual(error_output, "")
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


if __name__ == "__main__":
    unittest.main()
