"""v0.9.5 CLI integration for human-friendly material plan building."""

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
    materials = list(document.materials)
    materials[0] = replace(
        materials[0],
        local_name="AnchorLocal",
        universal_name="AnchorUniversal",
    )
    document = replace(
        document,
        texture_paths=(
            "anchor.png",
            *document.texture_paths[1:],
        ),
        materials=tuple(materials),
        trailing_data=b"",
    )
    return serialize_pmx(document)


def _runtime_parser() -> argparse.ArgumentParser:
    return cli._build_runtime_argument_parser()


class TransactionPlanBuildMaterialCliTests(unittest.TestCase):
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
                "material",
                str(self.source_path),
                "--local-name",
                "新しい材質",
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

    def test_parser_adds_material_as_second_build_kind(self) -> None:
        parser = _runtime_parser()
        arguments = parser.parse_args(
            [
                "transaction-plan",
                "build",
                "material",
                "source.pmx",
                "--local-name",
                "Material",
            ]
        )
        self.assertEqual(arguments.transaction_plan_action, "build")
        self.assertEqual(arguments.transaction_plan_build_kind, "material")
        self.assertEqual(arguments.local_name, "Material")
        self.assertEqual(arguments.universal_name, "")
        self.assertEqual(arguments.memo, "")
        self.assertIsNone(arguments.texture_index)
        self.assertIsNone(arguments.texture_path)

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
        build = actions.choices["build"]
        kinds = [
            action
            for action in build._actions
            if isinstance(action, argparse._SubParsersAction)
        ][0]
        self.assertEqual(tuple(kinds.choices), ("texture", "material", "morph", "bone", "rigid-body", "vertex"))

    def test_minimal_material_outputs_existing_canonical_schema_one_plan(self) -> None:
        with patch.object(
            transaction_plan_cli,
            "resolve_structural_authoring_selector",
            side_effect=AssertionError("minimal append must not resolve"),
        ) as resolve_selector:
            exit_code, stdout, stderr = self._run("--new-id", "mat_added")

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        resolve_selector.assert_not_called()

        plan = parse_pmx_structural_transaction_plan_json(stdout)
        self.assertEqual(len(plan.operations), 1)
        operation = plan.operations[0]
        self.assertEqual(operation.local_name, "新しい材質")
        self.assertEqual(operation.universal_name, "")
        self.assertEqual(operation.memo, "")
        self.assertEqual(operation.texture_index, -1)
        self.assertEqual(operation.position, "append")
        self.assertIsNone(operation.source_index)
        self.assertEqual(operation.new_id, "mat_added")
        self.assertEqual(stdout, builder.render_structural_authoring_plan(plan))

    def test_texture_index_is_resolved_as_exact_source_texture_selector(self) -> None:
        with patch.object(
            transaction_plan_cli,
            "resolve_structural_authoring_selector",
            wraps=selector.resolve_structural_authoring_selector,
        ) as resolve_selector:
            exit_code, stdout, stderr = self._run("--texture-index", "0")

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        resolve_selector.assert_called_once()
        selection = resolve_selector.call_args.args[1]
        self.assertEqual(selection.target_kind.value, "texture")
        self.assertEqual(selection.field.value, "source_index")
        self.assertEqual(selection.value, 0)

        plan = parse_pmx_structural_transaction_plan_json(stdout)
        self.assertEqual(plan.operations[0].texture_index, 0)

    def test_texture_path_is_exact_and_material_local_name_anchor_compiles(self) -> None:
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
                "--texture-path",
                "anchor.png",
                "--before-local-name",
                "AnchorLocal",
                "--universal-name",
                "NewUniversal",
                "--memo",
                "memo",
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(resolve_selector.call_count, 2)
        texture_selection = resolve_selector.call_args_list[0].args[1]
        material_selection = resolve_selector.call_args_list[1].args[1]
        self.assertEqual(texture_selection.target_kind.value, "texture")
        self.assertEqual(texture_selection.field.value, "path")
        self.assertEqual(texture_selection.value, "anchor.png")
        self.assertEqual(material_selection.target_kind.value, "material")
        self.assertEqual(material_selection.field.value, "local_name")
        self.assertEqual(material_selection.value, "AnchorLocal")
        compile_before.assert_called_once()

        plan = parse_pmx_structural_transaction_plan_json(stdout)
        operation = plan.operations[0]
        self.assertEqual(operation.texture_index, 0)
        self.assertEqual(operation.position, "insert_before")
        self.assertEqual(operation.source_index, 0)
        self.assertEqual(operation.universal_name, "NewUniversal")
        self.assertEqual(operation.memo, "memo")

    def test_material_universal_name_anchor_is_exact(self) -> None:
        with patch.object(
            transaction_plan_cli,
            "resolve_structural_authoring_selector",
            wraps=selector.resolve_structural_authoring_selector,
        ) as resolve_selector:
            exit_code, stdout, stderr = self._run(
                "--before-universal-name",
                "AnchorUniversal",
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        selection = resolve_selector.call_args.args[1]
        self.assertEqual(selection.target_kind.value, "material")
        self.assertEqual(selection.field.value, "universal_name")
        self.assertEqual(selection.value, "AnchorUniversal")

        plan = parse_pmx_structural_transaction_plan_json(stdout)
        self.assertEqual(plan.operations[0].source_index, 0)

    def test_texture_reference_options_are_mutually_exclusive(self) -> None:
        parser = _runtime_parser()
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(
                [
                    "transaction-plan",
                    "build",
                    "material",
                    "source.pmx",
                    "--local-name",
                    "Material",
                    "--texture-index",
                    "0",
                    "--texture-path",
                    "anchor.png",
                ]
            )

    def test_material_placement_options_are_mutually_exclusive(self) -> None:
        parser = _runtime_parser()
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(
                [
                    "transaction-plan",
                    "build",
                    "material",
                    "source.pmx",
                    "--local-name",
                    "Material",
                    "--before-index",
                    "0",
                    "--before-local-name",
                    "AnchorLocal",
                ]
            )

    def test_expected_source_sha256_is_passed_through_not_computed(self) -> None:
        digest = "b" * 64
        exit_code, stdout, stderr = self._run(
            "--expected-source-sha256",
            digest,
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        plan = parse_pmx_structural_transaction_plan_json(stdout)
        self.assertEqual(plan.expected_source_sha256, digest)

        source = inspect.getsource(transaction_plan_cli)
        start = source.index('    if action == "build":')
        end = source.index('    if action == "format":', start)
        build_block = source[start:end]
        self.assertNotIn("hashlib", build_block)
        self.assertNotIn("sha256(", build_block)

    def test_material_build_has_no_execution_or_generic_payload_authority(self) -> None:
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
        end = source.index('    if action == "format":', start)
        block = source[start:end]
        for forbidden in (
            "preview_structural_transaction_plan",
            "apply_structural_transaction_plan",
            "PmxIndexRemap",
            "structural_output",
            "write_pmx",
            "serialize_pmx",
            "final_index =",
            "--operation-json",
            "--operation-file",
            "--fields-json",
            "--payload",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, block)


if __name__ == "__main__":
    unittest.main()
