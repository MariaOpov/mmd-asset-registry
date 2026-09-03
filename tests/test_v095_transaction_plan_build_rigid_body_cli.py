"""v0.9.5 CLI integration for human-friendly rigid-body plan building."""

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

    bones = list(document.bones)
    bones[0] = replace(
        bones[0],
        local_name="AnchorBoneLocal",
        universal_name="AnchorBoneUniversal",
    )

    rigid_bodies = list(document.rigid_bodies)
    rigid_bodies[0] = replace(
        rigid_bodies[0],
        local_name="AnchorRigidLocal",
        universal_name="AnchorRigidUniversal",
    )

    document = replace(
        document,
        bones=tuple(bones),
        rigid_bodies=tuple(rigid_bodies),
        trailing_data=b"",
    )
    return serialize_pmx(document)


def _runtime_parser() -> argparse.ArgumentParser:
    return cli._build_runtime_argument_parser()


class TransactionPlanBuildRigidBodyCliTests(unittest.TestCase):
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
                "rigid-body",
                str(self.source_path),
                "--local-name",
                "新しい剛体",
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

    def test_parser_adds_rigid_body_as_fifth_build_kind(self) -> None:
        parser = _runtime_parser()
        arguments = parser.parse_args(
            [
                "transaction-plan",
                "build",
                "rigid-body",
                "source.pmx",
                "--local-name",
                "Rigid",
            ]
        )
        self.assertEqual(arguments.transaction_plan_action, "build")
        self.assertEqual(
            arguments.transaction_plan_build_kind,
            "rigid-body",
        )
        self.assertEqual(arguments.local_name, "Rigid")
        self.assertEqual(arguments.universal_name, "")
        self.assertIsNone(arguments.bone_index)
        self.assertIsNone(arguments.body_size)
        self.assertIsNone(arguments.body_position)
        self.assertIsNone(arguments.rotation)
        self.assertEqual(arguments.shape, "sphere")
        self.assertEqual(arguments.physics_mode, "bone_follow")

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
            ("texture", "material", "morph", "bone", "rigid-body", "vertex"),
        )

    def test_minimal_rigid_body_outputs_existing_canonical_schema_one_plan(self) -> None:
        with patch.object(
            transaction_plan_cli,
            "resolve_structural_authoring_selector",
            side_effect=AssertionError("minimal append must not resolve"),
        ) as resolve_selector:
            exit_code, stdout, stderr = self._run("--new-id", "rigid_added")

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        resolve_selector.assert_not_called()

        plan = parse_pmx_structural_transaction_plan_json(stdout)
        self.assertEqual(len(plan.operations), 1)
        operation = plan.operations[0]
        self.assertEqual(operation.local_name, "新しい剛体")
        self.assertEqual(operation.universal_name, "")
        self.assertEqual(operation.bone_index, -1)
        self.assertEqual(operation.shape, "sphere")
        self.assertEqual(operation.size, (1.0, 1.0, 1.0))
        self.assertEqual(operation.body_position, (0.0, 0.0, 0.0))
        self.assertEqual(operation.rotation, (0.0, 0.0, 0.0))
        self.assertEqual(operation.physics_mode, "bone_follow")
        self.assertEqual(operation.position, "append")
        self.assertIsNone(operation.source_index)
        self.assertEqual(operation.new_id, "rigid_added")
        self.assertEqual(stdout, builder.render_structural_authoring_plan(plan))

    def test_shape_vectors_and_physics_mode_use_released_fields(self) -> None:
        exit_code, stdout, stderr = self._run(
            "--shape",
            "capsule",
            "--size",
            "1.25",
            "2.5",
            "3.75",
            "--position",
            "-1.0",
            "2.0",
            "-3.0",
            "--rotation",
            "0.1",
            "0.2",
            "0.3",
            "--physics-mode",
            "physics_with_bone_alignment",
            "--universal-name",
            "RigidUniversal",
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        plan = parse_pmx_structural_transaction_plan_json(stdout)
        operation = plan.operations[0]
        self.assertEqual(operation.shape, "capsule")
        self.assertEqual(operation.size, (1.25, 2.5, 3.75))
        self.assertEqual(operation.body_position, (-1.0, 2.0, -3.0))
        self.assertEqual(operation.rotation, (0.1, 0.2, 0.3))
        self.assertEqual(
            operation.physics_mode,
            "physics_with_bone_alignment",
        )
        self.assertEqual(operation.universal_name, "RigidUniversal")

    def test_bone_index_uses_exact_bone_selector(self) -> None:
        with patch.object(
            transaction_plan_cli,
            "resolve_structural_authoring_selector",
            wraps=selector.resolve_structural_authoring_selector,
        ) as resolve_selector:
            exit_code, stdout, stderr = self._run("--bone-index", "0")

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        resolve_selector.assert_called_once()
        selection = resolve_selector.call_args.args[1]
        self.assertEqual(selection.target_kind.value, "bone")
        self.assertEqual(selection.field.value, "source_index")
        self.assertEqual(selection.value, 0)

        plan = parse_pmx_structural_transaction_plan_json(stdout)
        self.assertEqual(plan.operations[0].bone_index, 0)

    def test_bone_local_name_uses_exact_bone_selector(self) -> None:
        with patch.object(
            transaction_plan_cli,
            "resolve_structural_authoring_selector",
            wraps=selector.resolve_structural_authoring_selector,
        ) as resolve_selector:
            exit_code, stdout, stderr = self._run(
                "--bone-local-name",
                "AnchorBoneLocal",
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        selection = resolve_selector.call_args.args[1]
        self.assertEqual(selection.target_kind.value, "bone")
        self.assertEqual(selection.field.value, "local_name")
        self.assertEqual(selection.value, "AnchorBoneLocal")

        plan = parse_pmx_structural_transaction_plan_json(stdout)
        self.assertEqual(plan.operations[0].bone_index, 0)

    def test_bone_universal_name_and_before_local_name_use_two_exact_selectors(self) -> None:
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
                "--bone-universal-name",
                "AnchorBoneUniversal",
                "--before-local-name",
                "AnchorRigidLocal",
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(resolve_selector.call_count, 2)

        bone_selection = resolve_selector.call_args_list[0].args[1]
        before_selection = resolve_selector.call_args_list[1].args[1]
        self.assertEqual(bone_selection.target_kind.value, "bone")
        self.assertEqual(bone_selection.field.value, "universal_name")
        self.assertEqual(bone_selection.value, "AnchorBoneUniversal")
        self.assertEqual(before_selection.target_kind.value, "rigid_body")
        self.assertEqual(before_selection.field.value, "local_name")
        self.assertEqual(before_selection.value, "AnchorRigidLocal")
        compile_before.assert_called_once()

        plan = parse_pmx_structural_transaction_plan_json(stdout)
        operation = plan.operations[0]
        self.assertEqual(operation.bone_index, 0)
        self.assertEqual(operation.position, "insert_before")
        self.assertEqual(operation.source_index, 0)

    def test_before_index_and_universal_name_are_exact_rigid_body_selectors(self) -> None:
        cases = (
            ("--before-index", "0", "source_index", 0),
            (
                "--before-universal-name",
                "AnchorRigidUniversal",
                "universal_name",
                "AnchorRigidUniversal",
            ),
        )
        for option, value, expected_field, expected_value in cases:
            with self.subTest(option=option):
                with patch.object(
                    transaction_plan_cli,
                    "resolve_structural_authoring_selector",
                    wraps=selector.resolve_structural_authoring_selector,
                ) as resolve_selector:
                    exit_code, stdout, stderr = self._run(option, value)

                self.assertEqual(exit_code, 0)
                self.assertEqual(stderr, "")
                selection = resolve_selector.call_args.args[1]
                self.assertEqual(selection.target_kind.value, "rigid_body")
                self.assertEqual(selection.field.value, expected_field)
                self.assertEqual(selection.value, expected_value)
                plan = parse_pmx_structural_transaction_plan_json(stdout)
                self.assertEqual(plan.operations[0].source_index, 0)

    def test_parser_rejects_invalid_choices_and_conflicting_selectors(self) -> None:
        parser = _runtime_parser()
        invalid_cases = (
            [
                "transaction-plan",
                "build",
                "rigid-body",
                "source.pmx",
                "--local-name",
                "Rigid",
                "--shape",
                "cylinder",
            ],
            [
                "transaction-plan",
                "build",
                "rigid-body",
                "source.pmx",
                "--local-name",
                "Rigid",
                "--physics-mode",
                "invalid",
            ],
            [
                "transaction-plan",
                "build",
                "rigid-body",
                "source.pmx",
                "--local-name",
                "Rigid",
                "--bone-index",
                "0",
                "--bone-local-name",
                "AnchorBoneLocal",
            ],
            [
                "transaction-plan",
                "build",
                "rigid-body",
                "source.pmx",
                "--local-name",
                "Rigid",
                "--before-index",
                "0",
                "--before-local-name",
                "AnchorRigidLocal",
            ],
        )
        for arguments in invalid_cases:
            with self.subTest(arguments=arguments):
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    parser.parse_args(arguments)

    def test_expected_source_sha256_is_passed_through_not_computed(self) -> None:
        digest = "e" * 64
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

    def test_rigid_body_build_has_no_deferred_or_execution_authority(self) -> None:
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
            "--collision-group",
            "--collision-mask",
            "--mass",
            "--linear-damping",
            "--angular-damping",
            "--restitution",
            "--friction",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, block)


if __name__ == "__main__":
    unittest.main()
