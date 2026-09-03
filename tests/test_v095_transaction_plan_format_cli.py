"""v0.9.5 CLI integration for canonical transaction-plan formatting."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import argparse
import inspect
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import mmd_registry.cli as cli
import mmd_registry.transaction_plan_cli as transaction_plan_cli
from mmd_registry.services import structural_authoring_formatter as formatter


def _runtime_parser() -> argparse.ArgumentParser:
    return cli._build_runtime_argument_parser()


class TransactionPlanFormatCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _run(self, path: Path) -> tuple[int, str, str]:
        arguments = _runtime_parser().parse_args(
            ["transaction-plan", "format", str(path)]
        )
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = transaction_plan_cli.run_transaction_plan_command(
                arguments
            )
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_parser_adds_format_as_one_additive_action(self) -> None:
        parser = _runtime_parser()
        arguments = parser.parse_args(
            ["transaction-plan", "format", "plan.json"]
        )
        self.assertEqual(arguments.transaction_plan_action, "format")
        self.assertEqual(arguments.plan, "plan.json")

        top = [
            action
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        ][0]
        transaction = top.choices["transaction-plan"]
        actions = [
            action
            for action in transaction._actions
            if isinstance(action, argparse._SubParsersAction)
        ][0]
        self.assertEqual(
            tuple(actions.choices),
            (
                "template",
                "inspect",
                "build",
                "format",
                "validate",
                "explain",
                "preview",
                "apply",
            ),
        )

    def test_format_outputs_exact_cp11_canonical_normalization(self) -> None:
        source = (
            '{ "operations" : [ '
            '{"path":"テクスチャ/追加.png","op":"insert_texture"},'
            '{"path":"second.png","op":"insert_texture"}'
            ' ], "schema_version" : 1 }'
        )
        path = self.root / "plan.json"
        path.write_text(source, encoding="utf-8")

        with patch.object(
            transaction_plan_cli,
            "normalize_structural_authoring_plan_json",
            wraps=formatter.normalize_structural_authoring_plan_json,
        ) as normalize:
            exit_code, stdout, stderr = self._run(path)

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        normalize.assert_called_once_with(source)
        self.assertEqual(
            stdout,
            formatter.normalize_structural_authoring_plan_json(source),
        )
        self.assertLess(
            stdout.index("テクスチャ/追加.png"),
            stdout.index("second.png"),
        )

    def test_format_is_idempotent(self) -> None:
        source = (
            '{"schema_version":1,"operations":'
            '[{"op":"insert_texture","path":"a.png"}]}'
        )
        first_path = self.root / "first.json"
        first_path.write_text(source, encoding="utf-8")
        first_code, first, first_error = self._run(first_path)
        self.assertEqual(first_code, 0)
        self.assertEqual(first_error, "")

        second_path = self.root / "second.json"
        second_path.write_text(first, encoding="utf-8")
        second_code, second, second_error = self._run(second_path)
        self.assertEqual(second_code, 0)
        self.assertEqual(second_error, "")
        self.assertEqual(second, first)

    def test_invalid_plan_returns_one_without_path_or_plan_output(self) -> None:
        path = self.root / "secret-plan-name.json"
        path.write_text(
            '{"schema_version":1,"operations":[],"unknown":true}',
            encoding="utf-8",
        )
        exit_code, stdout, stderr = self._run(path)
        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("[ERROR] transaction-plan format:", stderr)
        self.assertNotIn(str(path), stderr)
        self.assertNotIn("secret-plan-name", stderr)

    def test_missing_file_returns_two_and_redacts_path(self) -> None:
        path = self.root / "private-missing-plan.json"
        exit_code, stdout, stderr = self._run(path)
        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("[ERROR] transaction-plan format:", stderr)
        self.assertNotIn(str(path), stderr)
        self.assertNotIn("private-missing-plan", stderr)

    def test_formatter_internal_failure_returns_three(self) -> None:
        path = self.root / "plan.json"
        path.write_text(
            '{"schema_version":1,"operations":[]}',
            encoding="utf-8",
        )
        failure = formatter.PmxStructuralAuthoringFormatterServiceError(
            formatter.PmxStructuralAuthoringFormatterServiceDiagnostic(
                code=(
                    formatter
                    .PmxStructuralAuthoringFormatterServiceDiagnosticCode
                    .INTERNAL_ERROR
                ),
                operation=(
                    formatter
                    .PmxStructuralAuthoringFormatterServiceOperation
                    .NORMALIZE_JSON
                ),
                message="internal detail must not escape",
            )
        )
        with patch.object(
            transaction_plan_cli,
            "normalize_structural_authoring_plan_json",
            side_effect=failure,
        ):
            exit_code, stdout, stderr = self._run(path)
        self.assertEqual(exit_code, 3)
        self.assertEqual(stdout, "")
        self.assertIn("[ERROR] transaction-plan format:", stderr)
        self.assertNotIn("internal detail must not escape", stderr)

    def test_format_route_has_no_pmx_or_execution_authority(self) -> None:
        path = self.root / "plan.json"
        path.write_text(
            '{"schema_version":1,"operations":[]}',
            encoding="utf-8",
        )
        with (
            patch.object(
                transaction_plan_cli,
                "load_document",
                side_effect=AssertionError("format must not load PMX"),
            ),
            patch.object(
                transaction_plan_cli,
                "preview_structural_transaction_plan",
                side_effect=AssertionError("format must not preview"),
            ),
            patch.object(
                transaction_plan_cli,
                "apply_structural_transaction_plan",
                side_effect=AssertionError("format must not apply"),
            ),
        ):
            exit_code, stdout, stderr = self._run(path)

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertTrue(stdout)

        source = inspect.getsource(transaction_plan_cli)
        start = source.index('    if action == "format":')
        end = source.index('    if action not in {"validate"', start)
        block = source[start:end]
        for forbidden in (
            "load_document(",
            "preview_structural_transaction_plan",
            "apply_structural_transaction_plan",
            "PmxIndexRemap",
            "write_pmx",
            "serialize_pmx",
            "hashlib",
            "sha256(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, block)


if __name__ == "__main__":
    unittest.main()
