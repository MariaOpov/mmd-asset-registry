"""v0.9.5 CLI integration for human-friendly BDEF1 vertex plan building."""

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
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.transaction_plan import (
    parse_pmx_structural_transaction_plan_json,
)
from mmd_registry.services import structural_authoring_builder as builder
from mmd_registry.services import structural_authoring_selector as selector
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


def _source_bytes() -> bytes:
    return build_pmx_roundtrip_fixture(version=2.1, index_size=1)


def _runtime_parser() -> argparse.ArgumentParser:
    return cli._build_runtime_argument_parser()


class TransactionPlanBuildVertexCliTests(unittest.TestCase):
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
                "vertex",
                str(self.source_path),
                "--position",
                "1.0",
                "2.0",
                "3.0",
                "--normal",
                "0.0",
                "1.0",
                "0.0",
                "--uv",
                "0.25",
                "0.75",
                "--bone-index",
                "0",
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

    def test_parser_adds_vertex_as_sixth_build_kind(self) -> None:
        parser = _runtime_parser()
        arguments = parser.parse_args(
            [
                "transaction-plan",
                "build",
                "vertex",
                "source.pmx",
                "--position",
                "1",
                "2",
                "3",
                "--normal",
                "0",
                "1",
                "0",
                "--uv",
                "0.25",
                "0.75",
                "--bone-local-name",
                "Root",
            ]
        )
        self.assertEqual(arguments.transaction_plan_action, "build")
        self.assertEqual(arguments.transaction_plan_build_kind, "vertex")
        self.assertEqual(arguments.vertex_position, [1.0, 2.0, 3.0])
        self.assertEqual(arguments.normal, [0.0, 1.0, 0.0])
        self.assertEqual(arguments.uv, [0.25, 0.75])
        self.assertEqual(arguments.edge_scale, 1.0)
        self.assertEqual(arguments.bone_local_name, "Root")
        self.assertIsNone(arguments.before_index)

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
        self.assertEqual(
            tuple(kinds.choices),
            (
                "texture",
                "material",
                "morph",
                "bone",
                "rigid-body",
                "vertex",
            ),
        )

    def test_minimal_vertex_uses_source_header_additional_uv_count(self) -> None:
        exit_code, stdout, stderr = self._run("--new-id", "vertex_added")

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")

        source_document = load_pmx(io.BytesIO(_source_bytes()))
        self.assertEqual(source_document.header.additional_uv_count, 4)

        plan = parse_pmx_structural_transaction_plan_json(stdout)
        self.assertEqual(len(plan.operations), 1)
        operation = plan.operations[0]
        self.assertEqual(operation.vertex_position, (1.0, 2.0, 3.0))
        self.assertEqual(operation.normal, (0.0, 1.0, 0.0))
        self.assertEqual(operation.uv, (0.25, 0.75))
        self.assertEqual(
            operation.additional_uvs,
            (
                (0.0, 0.0, 0.0, 0.0),
                (0.0, 0.0, 0.0, 0.0),
                (0.0, 0.0, 0.0, 0.0),
                (0.0, 0.0, 0.0, 0.0),
            ),
        )
        self.assertEqual(operation.deform.bone_index, 0)
        self.assertEqual(operation.edge_scale, 1.0)
        self.assertEqual(operation.position, "append")
        self.assertIsNone(operation.source_index)
        self.assertEqual(operation.new_id, "vertex_added")
        self.assertEqual(stdout, builder.render_structural_authoring_plan(plan))

    def test_edge_scale_is_passed_to_released_vertex_dto(self) -> None:
        exit_code, stdout, stderr = self._run("--edge-scale", "0.625")
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        plan = parse_pmx_structural_transaction_plan_json(stdout)
        self.assertEqual(plan.operations[0].edge_scale, 0.625)

    def test_bone_index_uses_exact_bone_selector(self) -> None:
        with patch.object(
            transaction_plan_cli,
            "resolve_structural_authoring_selector",
            wraps=selector.resolve_structural_authoring_selector,
        ) as resolve_selector:
            exit_code, stdout, stderr = self._run()

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        resolve_selector.assert_called_once()
        selection = resolve_selector.call_args.args[1]
        self.assertEqual(selection.target_kind.value, "bone")
        self.assertEqual(selection.field.value, "source_index")
        self.assertEqual(selection.value, 0)
        plan = parse_pmx_structural_transaction_plan_json(stdout)
        self.assertEqual(plan.operations[0].deform.bone_index, 0)

    def test_bone_local_and_universal_name_are_exact_selectors(self) -> None:
        source = load_pmx(io.BytesIO(_source_bytes()))
        local_name = source.bones[0].local_name
        universal_name = source.bones[0].universal_name

        cases = (
            ("--bone-local-name", local_name, "local_name"),
            ("--bone-universal-name", universal_name, "universal_name"),
        )
        for option, value, field in cases:
            with self.subTest(option=option):
                arguments = _runtime_parser().parse_args(
                    [
                        "transaction-plan",
                        "build",
                        "vertex",
                        str(self.source_path),
                        "--position",
                        "1",
                        "2",
                        "3",
                        "--normal",
                        "0",
                        "1",
                        "0",
                        "--uv",
                        "0",
                        "0",
                        option,
                        value,
                    ]
                )
                stdout = io.StringIO()
                stderr = io.StringIO()
                with patch.object(
                    transaction_plan_cli,
                    "resolve_structural_authoring_selector",
                    wraps=selector.resolve_structural_authoring_selector,
                ) as resolve_selector:
                    with redirect_stdout(stdout), redirect_stderr(stderr):
                        exit_code = (
                            transaction_plan_cli.run_transaction_plan_command(
                                arguments
                            )
                        )

                self.assertEqual(exit_code, 0)
                self.assertEqual(stderr.getvalue(), "")
                selection = resolve_selector.call_args.args[1]
                self.assertEqual(selection.target_kind.value, "bone")
                self.assertEqual(selection.field.value, field)
                self.assertEqual(selection.value, value)

    def test_before_index_uses_exact_vertex_selector_and_builder(self) -> None:
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
            exit_code, stdout, stderr = self._run("--before-index", "0")

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(resolve_selector.call_count, 2)
        bone_selection = resolve_selector.call_args_list[0].args[1]
        vertex_selection = resolve_selector.call_args_list[1].args[1]
        self.assertEqual(bone_selection.target_kind.value, "bone")
        self.assertEqual(vertex_selection.target_kind.value, "vertex")
        self.assertEqual(vertex_selection.field.value, "source_index")
        self.assertEqual(vertex_selection.value, 0)
        compile_before.assert_called_once()

        plan = parse_pmx_structural_transaction_plan_json(stdout)
        self.assertEqual(plan.operations[0].position, "insert_before")
        self.assertEqual(plan.operations[0].source_index, 0)

    def test_bone_reference_group_is_required_and_mutually_exclusive(self) -> None:
        parser = _runtime_parser()
        missing_bone = [
            "transaction-plan",
            "build",
            "vertex",
            "source.pmx",
            "--position",
            "1",
            "2",
            "3",
            "--normal",
            "0",
            "1",
            "0",
            "--uv",
            "0",
            "0",
        ]
        conflicting = [
            *missing_bone,
            "--bone-index",
            "0",
            "--bone-local-name",
            "Root",
        ]
        for arguments in (missing_bone, conflicting):
            with self.subTest(arguments=arguments):
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    parser.parse_args(arguments)

    def test_expected_source_sha256_is_passed_through_not_computed(self) -> None:
        digest = "f" * 64
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
        block = source[start:end]
        self.assertNotIn("hashlib", block)
        self.assertNotIn("sha256(", block)

    def test_vertex_build_has_no_deferred_or_execution_authority(self) -> None:
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
            "write_pmx",
            "serialize_pmx",
            "final_index =",
            "--operation-json",
            "--operation-file",
            "--fields-json",
            "--payload",
            "PmxStructuralVertexBdef2",
            "PmxStructuralVertexBdef4",
            "PmxStructuralVertexSdef",
            "PmxStructuralVertexQdef",
            "PmxStructuralNewReference",
            "--additional-uv",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, block)


if __name__ == "__main__":
    unittest.main()
