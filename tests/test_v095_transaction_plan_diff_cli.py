"""v0.9.5 CLI integration tests for certified rich preview diff."""

from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import replace
import argparse
import inspect
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import mmd_registry.cli as cli
import mmd_registry.transaction_plan_cli as transaction_plan_cli
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.writer import serialize_pmx
from mmd_registry.services import structural_authoring_diff as diff_service
from mmd_registry.services import structural_transaction_plan_preview as preview_service
from mmd_registry.services.structural_transaction_plan_preview import (
    PmxStructuralTransactionPlanPreviewResult,
)
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


def _clean_source_bytes() -> bytes:
    fixture = build_pmx_roundtrip_fixture(version=2.1, index_size=1)
    document = replace(
        load_pmx(io.BytesIO(fixture)),
        trailing_data=b"",
    )
    return serialize_pmx(document)


def _runtime_parser() -> argparse.ArgumentParser:
    return cli._build_runtime_argument_parser()


class TransactionPlanRichDiffCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.source_path = self.root / "source.pmx"
        self.plan_path = self.root / "plan.json"
        self.source_path.write_bytes(_clean_source_bytes())
        self.plan_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "operations": [
                        {
                            "op": "insert_texture",
                            "path": "テクスチャ/追加.png",
                        }
                    ],
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _arguments(
        self,
        *,
        rich_diff: bool,
        json_output: bool = False,
    ) -> argparse.Namespace:
        argv = [
            "transaction-plan",
            "preview",
            str(self.source_path),
            str(self.plan_path),
        ]
        if rich_diff:
            argv.append("--diff")
        if json_output:
            argv.append("--json")
        return _runtime_parser().parse_args(argv)

    def test_preview_parser_adds_only_optional_diff_flag(self) -> None:
        parser = _runtime_parser()
        arguments = parser.parse_args(
            [
                "transaction-plan",
                "preview",
                "source.pmx",
                "plan.json",
                "--diff",
            ]
        )
        self.assertTrue(arguments.diff)
        self.assertFalse(arguments.json)

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
            ("template", "inspect", "validate", "explain", "preview", "apply"),
        )

    def test_default_preview_output_and_service_route_remain_unchanged(self) -> None:
        arguments = self._arguments(rich_diff=False)
        output = io.StringIO()

        with (
            patch.object(
                transaction_plan_cli,
                "build_structural_authoring_diff",
                side_effect=AssertionError("diff must be opt-in"),
            ) as build_diff,
            redirect_stdout(output),
        ):
            exit_code = transaction_plan_cli.run_transaction_plan_command(
                arguments
            )

        self.assertEqual(exit_code, 0)
        build_diff.assert_not_called()
        rendered = output.getvalue()
        self.assertIn("STRUCTURAL TRANSACTION PLAN PREVIEW", rendered)
        self.assertNotIn("STRUCTURAL TRANSACTION PLAN DIFF", rendered)
        self.assertIn("Inserted: 1", rendered)

    def test_diff_text_reuses_exactly_one_certified_preview(self) -> None:
        arguments = self._arguments(rich_diff=True)
        output = io.StringIO()

        with (
            patch.object(
                transaction_plan_cli,
                "preview_structural_transaction_plan",
                wraps=preview_service.preview_structural_transaction_plan,
            ) as preview,
            patch.object(
                transaction_plan_cli,
                "build_structural_authoring_diff",
                wraps=diff_service.build_structural_authoring_diff,
            ) as build_diff,
            redirect_stdout(output),
        ):
            exit_code = transaction_plan_cli.run_transaction_plan_command(
                arguments
            )

        self.assertEqual(exit_code, 0)
        preview.assert_called_once()
        build_diff.assert_called_once()
        self.assertIsInstance(
            build_diff.call_args.args[0],
            PmxStructuralTransactionPlanPreviewResult,
        )

        rendered = output.getvalue()
        self.assertIn("STRUCTURAL TRANSACTION PLAN DIFF", rendered)
        self.assertIn("Changed targets: texture", rendered)
        self.assertIn("Inserted: 1", rendered)
        self.assertIn("texture:", rendered)
        self.assertIn("Output written: no", rendered)

    def test_diff_json_is_the_cp10_projection_not_raw_preview_evidence(self) -> None:
        arguments = self._arguments(rich_diff=True, json_output=True)
        output = io.StringIO()

        with redirect_stdout(output):
            exit_code = transaction_plan_cli.run_transaction_plan_command(
                arguments
            )

        self.assertEqual(exit_code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["status"], "changes_pending")
        self.assertEqual(payload["changed_targets"], ["texture"])
        self.assertEqual(payload["totals"]["inserted"], 1)
        self.assertEqual(len(payload["collections"]), 6)
        self.assertNotIn("effects", payload)
        self.assertNotIn("operations", payload)
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn(str(self.source_path), serialized)
        self.assertNotIn('"source_sha256"', serialized)
        self.assertNotIn('"semantic_sha256"', serialized)

    def test_cli_does_not_reimplement_or_repeat_preview_authority(self) -> None:
        source = inspect.getsource(transaction_plan_cli)
        self.assertEqual(
            source.count("preview_structural_transaction_plan("),
            1,
        )
        self.assertEqual(
            source.count("build_structural_authoring_diff(result)"),
            1,
        )
        for forbidden in (
            "preview_structural_transaction(result",
            "PmxIndexRemap",
            "final_index =",
            "serialize_pmx",
            "write_pmx",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_diff_projection_failure_is_translated_as_internal_cli_failure(
        self,
    ) -> None:
        arguments = self._arguments(rich_diff=True, json_output=True)
        output = io.StringIO()
        failure = diff_service.PmxStructuralAuthoringDiffServiceError(
            diff_service.PmxStructuralAuthoringDiffServiceDiagnostic(
                code=(
                    diff_service
                    .PmxStructuralAuthoringDiffServiceDiagnosticCode
                    .EVIDENCE_INVALID
                ),
                operation=(
                    diff_service
                    .PmxStructuralAuthoringDiffServiceOperation
                    .BUILD_DIFF
                ),
                message="Certified structural preview evidence is invalid.",
            )
        )

        with (
            patch.object(
                transaction_plan_cli,
                "build_structural_authoring_diff",
                side_effect=failure,
            ),
            redirect_stdout(output),
        ):
            exit_code = transaction_plan_cli.run_transaction_plan_command(
                arguments
            )

        self.assertEqual(exit_code, 3)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["action"], "preview")
        self.assertEqual(payload["error_type"], "diff_projection_failed")
        self.assertEqual(
            payload["error"]["code"],
            "certified_preview_evidence_invalid",
        )


if __name__ == "__main__":
    unittest.main()
