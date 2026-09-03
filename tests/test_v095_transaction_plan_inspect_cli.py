"""v0.9.5 CLI contracts for read-only structural authoring inspection."""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import mmd_registry.cli as cli
import mmd_registry.services as services
import mmd_registry.transaction_plan_cli as transaction_plan_cli
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.services import structural_authoring_catalog as catalog
from tests.mmd_fixtures import (
    build_pmx_bone,
    build_pmx_material,
    build_pmx_morph,
    build_pmx_rigid_body,
    build_pmx_structure,
)


EXPECTED_TRANSACTION_PLAN_ACTIONS = ("template", "inspect", "build", "format", "validate", "explain", "preview", "apply")


def _subparser_choices(parser: argparse.ArgumentParser):
    actions = [
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    ]
    if len(actions) != 1:
        raise AssertionError(
            f"expected one subparser action, found {len(actions)}"
        )
    return actions[0].choices


def _capture_run(arguments: list[str]) -> tuple[int, str, str]:
    output = io.StringIO()
    error_output = io.StringIO()
    with redirect_stdout(output), redirect_stderr(error_output):
        exit_code = cli.run(arguments)
    return exit_code, output.getvalue(), error_output.getvalue()


def _source_bytes() -> bytes:
    return build_pmx_structure(
        deform_types=(0, 1),
        surface_indices=(),
        texture_paths=(r"textures\Face.png", "テクスチャ/目.png"),
        materials=(
            build_pmx_material(
                local_name="顔",
                universal_name="Face",
                texture_index=0,
                surface_index_count=0,
            ),
        ),
        bones=(
            build_pmx_bone(
                local_name="右腕",
                universal_name="Right Arm",
                parent_bone_index=-1,
            ),
        ),
        morphs=(
            build_pmx_morph(
                local_name="まばたき",
                universal_name="Blink",
                panel=1,
                morph_type=1,
                offsets=(),
            ),
        ),
        rigid_bodies=(
            build_pmx_rigid_body(
                local_name="右腕剛体",
                universal_name="Right Arm Body",
                bone_index=0,
                shape=1,
                physics_mode=0,
            ),
        ),
    )


class V095TransactionPlanInspectCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.source_path = self.root / "source.pmx"
        self.source_bytes = _source_bytes()
        self.source_path.write_bytes(self.source_bytes)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_runtime_parser_adds_inspect_without_changing_legacy_parser(self) -> None:
        runtime = cli._build_runtime_argument_parser()
        commands = _subparser_choices(runtime)
        actions = _subparser_choices(commands["transaction-plan"])

        self.assertEqual(tuple(actions), EXPECTED_TRANSACTION_PLAN_ACTIONS)
        self.assertNotIn(
            "transaction-plan",
            _subparser_choices(cli.build_argument_parser()),
        )

    def test_summary_text_and_json_route_through_services(self) -> None:
        with (
            patch.object(
                transaction_plan_cli,
                "load_document",
                wraps=services.load_document,
            ) as load_document,
            patch.object(
                transaction_plan_cli,
                "summarize_structural_authoring_catalog",
                wraps=catalog.summarize_structural_authoring_catalog,
            ) as summarize,
        ):
            text_code, text_output, text_error = _capture_run(
                ["transaction-plan", "inspect", str(self.source_path)]
            )

        self.assertEqual(text_code, 0)
        self.assertEqual(text_error, "")
        self.assertEqual(
            text_output,
            "\n".join(
                (
                    "STRUCTURAL AUTHORING CATALOG",
                    "Vertices: 2",
                    "Textures: 2",
                    "Materials: 1",
                    "Bones: 1",
                    "Morphs: 1",
                    "Rigid bodies: 1",
                    "Detailed entries: no",
                    "",
                )
            ),
        )
        load_document.assert_called_once_with(str(self.source_path))
        summarize.assert_called_once()

        json_code, json_output, json_error = _capture_run(
            [
                "transaction-plan",
                "inspect",
                str(self.source_path),
                "--json",
            ]
        )
        self.assertEqual(json_code, 0)
        self.assertEqual(json_error, "")
        self.assertEqual(
            json.loads(json_output),
            {
                "counts": {
                    "vertex": 2,
                    "texture": 2,
                    "material": 1,
                    "bone": 1,
                    "morph": 1,
                    "rigid_body": 1,
                }
            },
        )
        self.assertNotIn(str(self.source_path), json_output)

    def test_kind_page_is_source_ordered_bounded_and_unicode_safe(self) -> None:
        code, output, error_output = _capture_run(
            [
                "transaction-plan",
                "inspect",
                str(self.source_path),
                "--kind",
                "texture",
                "--offset",
                "1",
                "--limit",
                "1",
                "--json",
            ]
        )
        self.assertEqual(code, 0)
        self.assertEqual(error_output, "")
        payload = json.loads(output)
        self.assertEqual(payload["target_kind"], "texture")
        self.assertEqual(payload["total_count"], 2)
        self.assertEqual(payload["returned_count"], 1)
        self.assertEqual(
            payload["entries"],
            [{"source_index": 1, "path": "テクスチャ/目.png"}],
        )

        text_code, text_output, text_error = _capture_run(
            [
                "transaction-plan",
                "inspect",
                str(self.source_path),
                "--kind",
                "bone",
            ]
        )
        self.assertEqual(text_code, 0)
        self.assertEqual(text_error, "")
        self.assertIn("Target kind: bone", text_output)
        self.assertIn(
            "[0] local_name='右腕' universal_name='Right Arm'",
            text_output,
        )

    def test_invalid_limit_maps_to_usage_without_path_leakage(self) -> None:
        code, output, error_output = _capture_run(
            [
                "transaction-plan",
                "inspect",
                str(self.source_path),
                "--kind",
                "bone",
                "--limit",
                "0",
                "--json",
            ]
        )
        self.assertEqual(code, 2)
        self.assertEqual(error_output, "")
        payload = json.loads(output)
        self.assertEqual(payload["action"], "inspect")
        self.assertEqual(payload["error_type"], "usage")
        self.assertEqual(payload["error"]["code"], "invalid_argument")
        self.assertNotIn(str(self.source_path), output)

    def test_missing_and_invalid_sources_use_existing_policy(self) -> None:
        missing = self.root / "秘密-missing.pmx"
        code, output, error_output = _capture_run(
            ["transaction-plan", "inspect", str(missing), "--json"]
        )
        self.assertEqual(code, 2)
        self.assertEqual(error_output, "")
        payload = json.loads(output)
        self.assertEqual(payload["error_type"], "io")
        self.assertEqual(payload["error"]["code"], "service_io_failed")
        self.assertNotIn(str(missing), output)

        invalid = self.root / "秘密-invalid.pmx"
        invalid.write_bytes(b"bad")
        code, output, error_output = _capture_run(
            ["transaction-plan", "inspect", str(invalid), "--json"]
        )
        self.assertEqual(code, 1)
        self.assertEqual(error_output, "")
        payload = json.loads(output)
        self.assertEqual(payload["error_type"], "source_invalid")
        self.assertEqual(payload["error"]["code"], "source_invalid")
        self.assertNotIn(str(invalid), output)

    def test_inspect_never_loads_plan_and_never_mutates_source(self) -> None:
        before = self.source_path.read_bytes()
        with patch.object(
            transaction_plan_cli,
            "load_structural_transaction_plan",
        ) as load_plan:
            code, output, error_output = _capture_run(
                [
                    "transaction-plan",
                    "inspect",
                    str(self.source_path),
                    "--kind",
                    PmxReferenceTargetKind.MATERIAL.value,
                ]
            )
        self.assertEqual(code, 0)
        self.assertEqual(error_output, "")
        self.assertIn("Target kind: material", output)
        load_plan.assert_not_called()
        self.assertEqual(self.source_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
