"""v0.9.5 CLI integration for human-friendly morph plan building."""

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


MORPH_TYPES = (
    "group",
    "vertex",
    "bone",
    "uv",
    "additional_uv_1",
    "additional_uv_2",
    "additional_uv_3",
    "additional_uv_4",
    "material",
    "flip",
    "impulse",
)
MORPH_PANELS = ("system", "eyebrow", "eye", "mouth", "other")


def _source_bytes() -> bytes:
    fixture = build_pmx_roundtrip_fixture(version=2.1, index_size=1)
    document = load_pmx(io.BytesIO(fixture))
    morphs = list(document.morphs)
    morphs[0] = replace(
        morphs[0],
        local_name="AnchorMorphLocal",
        universal_name="AnchorMorphUniversal",
    )
    document = replace(
        document,
        morphs=tuple(morphs),
        trailing_data=b"",
    )
    return serialize_pmx(document)


def _runtime_parser() -> argparse.ArgumentParser:
    return cli._build_runtime_argument_parser()


class TransactionPlanBuildMorphCliTests(unittest.TestCase):
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
                "morph",
                str(self.source_path),
                "--local-name",
                "新しいモーフ",
                "--type",
                "group",
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

    def test_parser_adds_morph_as_third_build_kind(self) -> None:
        parser = _runtime_parser()
        arguments = parser.parse_args(
            [
                "transaction-plan",
                "build",
                "morph",
                "source.pmx",
                "--local-name",
                "Morph",
                "--type",
                "vertex",
            ]
        )
        self.assertEqual(arguments.transaction_plan_action, "build")
        self.assertEqual(arguments.transaction_plan_build_kind, "morph")
        self.assertEqual(arguments.local_name, "Morph")
        self.assertEqual(arguments.morph_type, "vertex")
        self.assertEqual(arguments.universal_name, "")
        self.assertEqual(arguments.panel, "other")

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
            ("texture", "material", "morph"),
        )

    def test_minimal_morph_outputs_existing_canonical_schema_one_plan(self) -> None:
        with patch.object(
            transaction_plan_cli,
            "resolve_structural_authoring_selector",
            side_effect=AssertionError("minimal append must not resolve"),
        ) as resolve_selector:
            exit_code, stdout, stderr = self._run("--new-id", "morph_added")

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        resolve_selector.assert_not_called()

        plan = parse_pmx_structural_transaction_plan_json(stdout)
        self.assertEqual(len(plan.operations), 1)
        operation = plan.operations[0]
        self.assertEqual(operation.local_name, "新しいモーフ")
        self.assertEqual(operation.morph_type, "group")
        self.assertEqual(operation.universal_name, "")
        self.assertEqual(operation.panel, "other")
        self.assertEqual(operation.offsets, ())
        self.assertEqual(operation.position, "append")
        self.assertIsNone(operation.source_index)
        self.assertEqual(operation.new_id, "morph_added")
        self.assertEqual(stdout, builder.render_structural_authoring_plan(plan))

    def test_panel_and_type_are_passed_to_released_morph_dto(self) -> None:
        arguments = _runtime_parser().parse_args(
            [
                "transaction-plan",
                "build",
                "morph",
                str(self.source_path),
                "--local-name",
                "Morph",
                "--type",
                "material",
                "--panel",
                "mouth",
                "--universal-name",
                "UniversalMorph",
            ]
        )
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = transaction_plan_cli.run_transaction_plan_command(
                arguments
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        plan = parse_pmx_structural_transaction_plan_json(stdout.getvalue())
        operation = plan.operations[0]
        self.assertEqual(operation.morph_type, "material")
        self.assertEqual(operation.panel, "mouth")
        self.assertEqual(operation.universal_name, "UniversalMorph")
        self.assertEqual(operation.offsets, ())

    def test_before_index_uses_exact_morph_selector(self) -> None:
        with patch.object(
            transaction_plan_cli,
            "resolve_structural_authoring_selector",
            wraps=selector.resolve_structural_authoring_selector,
        ) as resolve_selector:
            exit_code, stdout, stderr = self._run("--before-index", "0")

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        resolve_selector.assert_called_once()
        selection = resolve_selector.call_args.args[1]
        self.assertEqual(selection.target_kind.value, "morph")
        self.assertEqual(selection.field.value, "source_index")
        self.assertEqual(selection.value, 0)

        plan = parse_pmx_structural_transaction_plan_json(stdout)
        self.assertEqual(plan.operations[0].position, "insert_before")
        self.assertEqual(plan.operations[0].source_index, 0)

    def test_before_local_name_routes_through_exact_selector_and_builder(self) -> None:
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
                "--before-local-name",
                "AnchorMorphLocal",
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        selection = resolve_selector.call_args.args[1]
        self.assertEqual(selection.target_kind.value, "morph")
        self.assertEqual(selection.field.value, "local_name")
        self.assertEqual(selection.value, "AnchorMorphLocal")
        compile_before.assert_called_once()

        plan = parse_pmx_structural_transaction_plan_json(stdout)
        self.assertEqual(plan.operations[0].source_index, 0)

    def test_before_universal_name_is_exact(self) -> None:
        with patch.object(
            transaction_plan_cli,
            "resolve_structural_authoring_selector",
            wraps=selector.resolve_structural_authoring_selector,
        ) as resolve_selector:
            exit_code, stdout, stderr = self._run(
                "--before-universal-name",
                "AnchorMorphUniversal",
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        selection = resolve_selector.call_args.args[1]
        self.assertEqual(selection.target_kind.value, "morph")
        self.assertEqual(selection.field.value, "universal_name")
        self.assertEqual(selection.value, "AnchorMorphUniversal")

        plan = parse_pmx_structural_transaction_plan_json(stdout)
        self.assertEqual(plan.operations[0].source_index, 0)

    def test_parser_rejects_invalid_type_panel_and_conflicting_placement(self) -> None:
        parser = _runtime_parser()
        invalid_cases = (
            [
                "transaction-plan",
                "build",
                "morph",
                "source.pmx",
                "--local-name",
                "Morph",
                "--type",
                "not-a-type",
            ],
            [
                "transaction-plan",
                "build",
                "morph",
                "source.pmx",
                "--local-name",
                "Morph",
                "--type",
                "group",
                "--panel",
                "not-a-panel",
            ],
            [
                "transaction-plan",
                "build",
                "morph",
                "source.pmx",
                "--local-name",
                "Morph",
                "--type",
                "group",
                "--before-index",
                "0",
                "--before-local-name",
                "AnchorMorphLocal",
            ],
        )
        for arguments in invalid_cases:
            with self.subTest(arguments=arguments):
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    parser.parse_args(arguments)

    def test_expected_source_sha256_is_passed_through_not_computed(self) -> None:
        digest = "c" * 64
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

    def test_morph_build_has_no_execution_or_generic_payload_authority(self) -> None:
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
            "--offsets-json",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, block)


if __name__ == "__main__":
    unittest.main()
