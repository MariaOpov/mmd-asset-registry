"""v0.9.5 CLI integration for human-friendly texture plan building."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
import argparse
import inspect
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import mmd_registry.cli as cli
import mmd_registry.transaction_plan_cli as transaction_plan_cli
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.transaction_plan import (
    parse_pmx_structural_transaction_plan_json,
)
from mmd_registry.pmx.writer import serialize_pmx
from mmd_registry.services import structural_authoring_builder as builder
from mmd_registry.services import structural_authoring_selector as selector
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


def _source_bytes() -> bytes:
    fixture = build_pmx_roundtrip_fixture(version=2.1, index_size=1)
    document = load_pmx(io.BytesIO(fixture))
    document = replace(
        document,
        texture_paths=(
            "anchor.png",
            "other.png",
            *document.texture_paths[2:],
        ),
        trailing_data=b"",
    )
    return serialize_pmx(document)


def _runtime_parser() -> argparse.ArgumentParser:
    return cli._build_runtime_argument_parser()


class TransactionPlanBuildTextureCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.source_path = self.root / "source.pmx"
        self.source_path.write_bytes(_source_bytes())

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _run(self, *extra: str) -> tuple[int, str, str]:
        arguments = _runtime_parser().parse_args(
            [
                "transaction-plan",
                "build",
                "texture",
                str(self.source_path),
                "--path",
                "テクスチャ/追加.png",
                *extra,
            ]
        )
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = transaction_plan_cli.run_transaction_plan_command(
                arguments
            )
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_parser_adds_build_texture_as_one_additive_action(self) -> None:
        parser = _runtime_parser()
        arguments = parser.parse_args(
            [
                "transaction-plan",
                "build",
                "texture",
                "source.pmx",
                "--path",
                "new.png",
            ]
        )
        self.assertEqual(arguments.transaction_plan_action, "build")
        self.assertEqual(arguments.transaction_plan_build_kind, "texture")
        self.assertEqual(arguments.path, "new.png")
        self.assertIsNone(arguments.before_index)
        self.assertIsNone(arguments.before_path)

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
            ("template", "inspect", "build", "format", "validate", "explain", "preview", "apply"),
        )

    def test_append_build_outputs_existing_canonical_schema_one_plan(self) -> None:
        with (
            patch.object(
                transaction_plan_cli,
                "resolve_structural_authoring_selector",
                side_effect=AssertionError("append must not resolve a selector"),
            ) as resolve_selector,
            patch.object(
                transaction_plan_cli,
                "compile_structural_authoring_insert_before",
                side_effect=AssertionError("append must not compile an anchor"),
            ) as compile_before,
        ):
            exit_code, stdout, stderr = self._run("--new-id", "tex_added")

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        resolve_selector.assert_not_called()
        compile_before.assert_not_called()

        plan = parse_pmx_structural_transaction_plan_json(stdout)
        self.assertEqual(len(plan.operations), 1)
        operation = plan.operations[0]
        self.assertEqual(operation.path, "テクスチャ/追加.png")
        self.assertEqual(operation.position, "append")
        self.assertIsNone(operation.source_index)
        self.assertEqual(operation.new_id, "tex_added")
        self.assertEqual(
            stdout,
            builder.render_structural_authoring_plan(plan),
        )

    def test_before_index_compiles_exact_selector_to_source_index(self) -> None:
        exit_code, stdout, stderr = self._run("--before-index", "1")

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        plan = parse_pmx_structural_transaction_plan_json(stdout)
        operation = plan.operations[0]
        self.assertEqual(operation.position, "insert_before")
        self.assertEqual(operation.source_index, 1)

    def test_before_path_routes_through_exact_selector_and_builder(self) -> None:
        with (
            patch.object(
                transaction_plan_cli,
                "resolve_structural_authoring_selector",
                wraps=selector.resolve_structural_authoring_selector,
            ) as resolve_selector,
            patch.object(
                transaction_plan_cli,
                "compile_structural_authoring_insert_before",
                wraps=builder.compile_structural_authoring_insert_before,
            ) as compile_before,
        ):
            exit_code, stdout, stderr = self._run(
                "--before-path",
                "anchor.png",
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        resolve_selector.assert_called_once()
        compile_before.assert_called_once()
        selection = resolve_selector.call_args.args[1]
        self.assertEqual(selection.target_kind.value, "texture")
        self.assertEqual(selection.field.value, "path")
        self.assertEqual(selection.value, "anchor.png")

        plan = parse_pmx_structural_transaction_plan_json(stdout)
        self.assertEqual(plan.operations[0].source_index, 0)

    def test_expected_source_sha256_is_passed_through_not_computed(self) -> None:
        digest = "a" * 64
        exit_code, stdout, stderr = self._run(
            "--expected-source-sha256",
            digest,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        plan = parse_pmx_structural_transaction_plan_json(stdout)
        self.assertEqual(plan.expected_source_sha256, digest)

        source = inspect.getsource(transaction_plan_cli)
        self.assertNotIn("hashlib", source)
        self.assertNotIn("sha256(", source)

    def test_anchor_options_are_mutually_exclusive_at_parser_boundary(self) -> None:
        parser = _runtime_parser()
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(
                [
                    "transaction-plan",
                    "build",
                    "texture",
                    "source.pmx",
                    "--path",
                    "new.png",
                    "--before-index",
                    "0",
                    "--before-path",
                    "anchor.png",
                ]
            )

    def test_build_never_calls_preview_apply_writer_or_remap_authority(self) -> None:
        with (
            patch.object(
                transaction_plan_cli,
                "preview_structural_transaction_plan",
                side_effect=AssertionError("build must not preview"),
            ),
            patch.object(
                transaction_plan_cli,
                "apply_structural_transaction_plan",
                side_effect=AssertionError("build must not apply"),
            ),
        ):
            exit_code, stdout, stderr = self._run()

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertTrue(stdout)

        source = inspect.getsource(transaction_plan_cli)
        start = source.index('    if action == "build":')
        end = source.index(
            '    if action not in {"validate"',
            start,
        )
        build_block = source[start:end]
        for forbidden in (
            "preview_structural_transaction_plan",
            "apply_structural_transaction_plan",
            "PmxIndexRemap",
            "structural_output",
            "write_pmx",
            "serialize_pmx",
            "final_index =",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, build_block)

    def test_missing_source_fails_without_plan_output(self) -> None:
        missing = self.root / "missing.pmx"
        arguments = _runtime_parser().parse_args(
            [
                "transaction-plan",
                "build",
                "texture",
                str(missing),
                "--path",
                "new.png",
            ]
        )
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = transaction_plan_cli.run_transaction_plan_command(
                arguments
            )

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("[ERROR] transaction-plan build:", stderr.getvalue())
        self.assertNotIn(str(missing), stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
