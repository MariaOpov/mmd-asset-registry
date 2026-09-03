"""Tests for CP16 structural transaction-plan CLI adapters."""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
import hashlib
import importlib
import inspect
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import mmd_registry.cli as cli
import mmd_registry.services.structural_transaction_plan as service
import mmd_registry.services.structural_transaction_plan_apply as apply_service
import mmd_registry.services.structural_transaction_plan_preview as preview_service
import mmd_registry.transaction_plan_cli as transaction_plan_cli
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.writer import serialize_pmx
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


EXPECTED_LEGACY_COMMANDS = (
    "validate",
    "hash",
    "inspect",
    "scan",
    "roundtrip",
    "edit",
    "edit-plan",
    "texture-portability",
    "doctor",
    "bones",
    "rig",
)
EXPECTED_TRANSACTION_PLAN_ACTIONS = (
    "template",
    "inspect",
    "build",
    "validate",
    "explain",
    "preview",
    "apply",
)
EXPECTED_HASH = "a" * 64


def _subparser_choices(
    parser: argparse.ArgumentParser,
) -> dict[str, argparse.ArgumentParser]:
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


def _valid_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "expected_source_sha256": EXPECTED_HASH,
        "operations": [
            {
                "op": "insert_texture",
                "path": "textures/安全.png",
            }
        ],
    }


def _clean_source_bytes() -> bytes:
    fixture = build_pmx_roundtrip_fixture(version=2.1, index_size=1)
    document = replace(
        load_pmx(io.BytesIO(fixture)),
        trailing_data=b"",
    )
    return serialize_pmx(document)


class V094TransactionPlanCliTests(unittest.TestCase):
    """Keep transaction-plan CLI additive, deterministic, and service-routed."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.plan_path = self.root / "plan.json"
        self.plan_path.write_text(
            json.dumps(
                _valid_payload(),
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_legacy_parser_namespace_and_normalization_remain_frozen(self) -> None:
        parser = cli.build_argument_parser()
        self.assertEqual(
            tuple(_subparser_choices(parser)),
            EXPECTED_LEGACY_COMMANDS,
        )
        self.assertEqual(
            cli.COMMAND_NAMES,
            frozenset(EXPECTED_LEGACY_COMMANDS),
        )
        self.assertEqual(
            cli.normalize_arguments(["transaction-plan", "template"]),
            ["validate", "transaction-plan", "template"],
        )

    def test_runtime_parser_adds_only_transaction_plan_with_exact_actions(
        self,
    ) -> None:
        parser = cli._build_runtime_argument_parser()
        commands = _subparser_choices(parser)

        self.assertEqual(
            tuple(commands),
            (*EXPECTED_LEGACY_COMMANDS, "transaction-plan"),
        )
        self.assertEqual(
            tuple(_subparser_choices(commands["transaction-plan"])),
            EXPECTED_TRANSACTION_PLAN_ACTIONS,
        )

        fresh_legacy = cli.build_argument_parser()
        self.assertEqual(
            tuple(_subparser_choices(fresh_legacy)),
            EXPECTED_LEGACY_COMMANDS,
        )

    def test_template_is_exact_safe_empty_canonical_json(self) -> None:
        exit_code, output, error_output = _capture_run(
            ["transaction-plan", "template"]
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(error_output, "")
        self.assertEqual(
            output,
            '{"schema_version":1,"operations":[]}\n',
        )

    def test_validate_text_and_json_use_cp15_service_result(self) -> None:
        text_code, text_output, text_error = _capture_run(
            ["transaction-plan", "validate", str(self.plan_path)]
        )
        json_code, json_output, json_error = _capture_run(
            [
                "transaction-plan",
                "validate",
                str(self.plan_path),
                "--json",
            ]
        )

        self.assertEqual(text_code, 0)
        self.assertEqual(text_error, "")
        self.assertEqual(
            text_output,
            "\n".join(
                (
                    "STRUCTURAL TRANSACTION PLAN VALID",
                    "Schema version: 1",
                    "Operations: 1",
                    "Expected source SHA-256 declared: yes",
                    "",
                )
            ),
        )

        self.assertEqual(json_code, 0)
        self.assertEqual(json_error, "")
        self.assertEqual(
            json.loads(json_output),
            {
                "status": "valid",
                "schema_version": 1,
                "operation_count": 1,
                "expected_source_sha256_declared": True,
            },
        )
        self.assertNotIn(EXPECTED_HASH, json_output)

    def test_explain_text_and_json_are_value_free_and_ordered(self) -> None:
        text_code, text_output, text_error = _capture_run(
            ["transaction-plan", "explain", str(self.plan_path)]
        )
        json_code, json_output, json_error = _capture_run(
            [
                "transaction-plan",
                "explain",
                str(self.plan_path),
                "--json",
            ]
        )

        self.assertEqual(text_code, 0)
        self.assertEqual(text_error, "")
        self.assertIn("STRUCTURAL TRANSACTION PLAN EXPLANATION", text_output)
        self.assertIn("[0] insert_texture", text_output)
        self.assertIn("Expected source SHA-256 declared: yes", text_output)
        self.assertNotIn(EXPECTED_HASH, text_output)
        self.assertNotIn("textures/安全.png", text_output)

        self.assertEqual(json_code, 0)
        self.assertEqual(json_error, "")
        payload = json.loads(json_output)
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["operation_count"], 1)
        self.assertTrue(payload["expected_source_sha256_declared"])
        self.assertEqual(payload["operations"][0]["operation_index"], 0)
        self.assertEqual(payload["operations"][0]["op"], "insert_texture")
        self.assertNotIn(EXPECTED_HASH, json_output)
        self.assertNotIn("textures/安全.png", json_output)

    def test_preview_text_and_json_use_cp17_source_bound_service(self) -> None:
        source_path = self.root / "source.pmx"
        source_bytes = _clean_source_bytes()
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()
        source_path.write_bytes(source_bytes)
        self.plan_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "expected_source_sha256": source_sha256,
                    "operations": [],
                },
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )

        with (
            patch.object(
                transaction_plan_cli,
                "load_structural_transaction_plan",
                wraps=service.load_structural_transaction_plan,
            ) as load_plan,
            patch.object(
                transaction_plan_cli,
                "preview_structural_transaction_plan",
                wraps=preview_service.preview_structural_transaction_plan,
            ) as preview_plan,
        ):
            text_code, text_output, text_error = _capture_run(
                [
                    "transaction-plan",
                    "preview",
                    str(source_path),
                    str(self.plan_path),
                ]
            )

        self.assertEqual(text_code, 0)
        self.assertEqual(text_error, "")
        self.assertEqual(
            text_output,
            "\n".join(
                (
                    "STRUCTURAL TRANSACTION PLAN PREVIEW",
                    "Status: no_changes",
                    "Source identity: matched",
                    "Changed targets: (none)",
                    "Inserted: 0",
                    "Deleted: 0",
                    "Reordered targets: 0",
                    "Output written: no",
                    "",
                )
            ),
        )
        load_plan.assert_called_once_with(str(self.plan_path))
        preview_plan.assert_called_once()
        self.assertEqual(
            preview_plan.call_args.args[0],
            str(source_path),
        )

        json_code, json_output, json_error = _capture_run(
            [
                "transaction-plan",
                "preview",
                str(source_path),
                str(self.plan_path),
                "--json",
            ]
        )
        self.assertEqual(json_code, 0)
        self.assertEqual(json_error, "")
        payload = json.loads(json_output)
        self.assertEqual(
            payload["source_identity"],
            {
                "algorithm": "sha256",
                "expected_source_sha256_declared": True,
                "status": "matched",
            },
        )
        self.assertEqual(payload["status"], "no_changes")
        self.assertTrue(payload["dry_run"])
        self.assertFalse(payload["output"]["written"])
        self.assertFalse(payload["output"]["source_touched"])
        self.assertFalse(payload["output"]["destination_touched"])

    def test_preview_identity_mismatch_is_exit_one_and_disclosure_safe(
        self,
    ) -> None:
        source_path = self.root / "秘密-source.pmx"
        source_bytes = _clean_source_bytes()
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()
        source_path.write_bytes(source_bytes)
        self.plan_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "expected_source_sha256": "0" * 64,
                    "operations": [],
                },
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )

        exit_code, output, error_output = _capture_run(
            [
                "transaction-plan",
                "preview",
                str(source_path),
                str(self.plan_path),
                "--json",
            ]
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(error_output, "")
        payload = json.loads(output)
        self.assertEqual(payload["action"], "preview")
        self.assertEqual(payload["error_type"], "source_identity_mismatch")
        self.assertEqual(
            payload["error"]["code"],
            "source_identity_mismatch",
        )
        self.assertNotIn("0" * 64, output)
        self.assertNotIn(source_sha256, output)
        self.assertNotIn(str(source_path), output)
        self.assertNotIn(str(self.plan_path), output)

    def test_preview_missing_source_maps_to_exit_two_without_path_leakage(
        self,
    ) -> None:
        source_path = self.root / "秘密-missing.pmx"
        self.plan_path.write_text(
            '{"schema_version":1,"operations":[]}',
            encoding="utf-8",
        )

        text_code, text_output, text_error = _capture_run(
            [
                "transaction-plan",
                "preview",
                str(source_path),
                str(self.plan_path),
            ]
        )
        json_code, json_output, json_error = _capture_run(
            [
                "transaction-plan",
                "preview",
                str(source_path),
                str(self.plan_path),
                "--json",
            ]
        )

        self.assertEqual(text_code, 2)
        self.assertEqual(text_output, "")
        self.assertIn("[ERROR] transaction-plan preview:", text_error)
        self.assertNotIn(str(source_path), text_error)

        self.assertEqual(json_code, 2)
        self.assertEqual(json_error, "")
        payload = json.loads(json_output)
        self.assertEqual(payload["error_type"], "io")
        self.assertEqual(payload["error"]["code"], "service_io_failed")
        self.assertNotIn(str(source_path), json_output)

    def test_preview_rejects_invalid_plan_before_source_preview_service(
        self,
    ) -> None:
        source_path = self.root / "must-not-be-read.pmx"
        self.plan_path.write_text(
            '{"schema_version":1,"operations":[],"unknown":true}',
            encoding="utf-8",
        )

        with patch.object(
            transaction_plan_cli,
            "preview_structural_transaction_plan",
        ) as preview_plan:
            exit_code, output, error_output = _capture_run(
                [
                    "transaction-plan",
                    "preview",
                    str(source_path),
                    str(self.plan_path),
                    "--json",
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(error_output, "")
        preview_plan.assert_not_called()
        payload = json.loads(output)
        self.assertEqual(payload["error_type"], "invalid_plan")
        self.assertEqual(
            payload["error"]["code"],
            "transaction_plan_invalid",
        )
        self.assertNotIn(str(source_path), output)

    def test_apply_text_and_json_use_cp18_source_bound_service(self) -> None:
        source_path = self.root / "apply-source.pmx"
        text_output_path = self.root / "apply-text-output.pmx"
        json_output_path = self.root / "apply-json-output.pmx"
        source_bytes = _clean_source_bytes()
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()
        source_path.write_bytes(source_bytes)
        self.plan_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "expected_source_sha256": source_sha256,
                    "operations": [],
                },
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )

        with (
            patch.object(
                transaction_plan_cli,
                "load_structural_transaction_plan",
                wraps=service.load_structural_transaction_plan,
            ) as load_plan,
            patch.object(
                transaction_plan_cli,
                "apply_structural_transaction_plan",
                wraps=apply_service.apply_structural_transaction_plan,
            ) as apply_plan,
        ):
            text_code, text_output, text_error = _capture_run(
                [
                    "transaction-plan",
                    "apply",
                    str(source_path),
                    str(self.plan_path),
                    str(text_output_path),
                ]
            )

        self.assertEqual(text_code, 0)
        self.assertEqual(text_error, "")
        self.assertIn("STRUCTURAL TRANSACTION PLAN APPLY", text_output)
        self.assertIn("Status: no_changes", text_output)
        self.assertIn("Source identity: matched", text_output)
        self.assertIn("Output written: yes", text_output)
        self.assertIn("Input unchanged: yes", text_output)
        self.assertNotIn(source_sha256, text_output)
        self.assertNotIn(str(source_path), text_output)
        self.assertNotIn(str(text_output_path), text_output)
        self.assertTrue(text_output_path.exists())
        load_plan.assert_called_once_with(str(self.plan_path))
        apply_plan.assert_called_once()
        self.assertEqual(
            apply_plan.call_args.args[:2],
            (str(source_path), str(text_output_path)),
        )
        self.assertIs(apply_plan.call_args.kwargs["overwrite"], False)

        json_code, json_output, json_error = _capture_run(
            [
                "transaction-plan",
                "apply",
                str(source_path),
                str(self.plan_path),
                str(json_output_path),
                "--json",
            ]
        )
        self.assertEqual(json_code, 0)
        self.assertEqual(json_error, "")
        payload = json.loads(json_output)
        self.assertEqual(
            payload["source_identity"],
            {
                "algorithm": "sha256",
                "expected_source_sha256_declared": True,
                "status": "matched",
            },
        )
        self.assertFalse(payload["dry_run"])
        self.assertTrue(payload["output"]["written"])
        self.assertNotIn("path", payload["output"])
        self.assertNotIn("sha256", payload["output"])
        self.assertNotIn("source", payload)
        self.assertNotIn("semantic_sha256", payload["plan"]["source"])
        self.assertNotIn(source_sha256, json_output)
        self.assertNotIn(str(source_path), json_output)
        self.assertNotIn(str(json_output_path), json_output)
        self.assertTrue(json_output_path.exists())

    def test_apply_identity_mismatch_is_exit_one_and_never_publishes(self) -> None:
        source_path = self.root / "秘密-apply-source.pmx"
        output_path = self.root / "秘密-apply-output.pmx"
        source_bytes = _clean_source_bytes()
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()
        source_path.write_bytes(source_bytes)
        self.plan_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "expected_source_sha256": "0" * 64,
                    "operations": [],
                },
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )

        text_code, text_output, text_error = _capture_run(
            [
                "transaction-plan",
                "apply",
                str(source_path),
                str(self.plan_path),
                str(output_path),
            ]
        )
        json_code, json_output, json_error = _capture_run(
            [
                "transaction-plan",
                "apply",
                str(source_path),
                str(self.plan_path),
                str(output_path),
                "--json",
            ]
        )

        self.assertEqual(text_code, 1)
        self.assertEqual(text_output, "")
        self.assertIn("[ERROR] transaction-plan apply:", text_error)
        self.assertFalse(output_path.exists())
        self.assertNotIn("0" * 64, text_error)
        self.assertNotIn(source_sha256, text_error)
        self.assertNotIn(str(source_path), text_error)
        self.assertNotIn(str(output_path), text_error)

        self.assertEqual(json_code, 1)
        self.assertEqual(json_error, "")
        payload = json.loads(json_output)
        self.assertEqual(payload["error_type"], "source_identity_mismatch")
        self.assertEqual(
            payload["error"]["code"],
            "source_identity_mismatch",
        )
        self.assertFalse(output_path.exists())
        self.assertNotIn("0" * 64, json_output)
        self.assertNotIn(source_sha256, json_output)
        self.assertNotIn(str(source_path), json_output)
        self.assertNotIn(str(output_path), json_output)

    def test_apply_existing_output_maps_to_exit_one_without_path_leakage(
        self,
    ) -> None:
        source_path = self.root / "apply-source.pmx"
        output_path = self.root / "秘密-existing-output.pmx"
        source_path.write_bytes(_clean_source_bytes())
        output_path.write_bytes(b"existing")
        self.plan_path.write_text(
            '{"schema_version":1,"operations":[]}',
            encoding="utf-8",
        )

        code, output, error_output = _capture_run(
            [
                "transaction-plan",
                "apply",
                str(source_path),
                str(self.plan_path),
                str(output_path),
                "--json",
            ]
        )

        self.assertEqual(code, 1)
        self.assertEqual(error_output, "")
        payload = json.loads(output)
        self.assertEqual(payload["error_type"], "output_path_unsafe")
        self.assertEqual(payload["error"]["code"], "output_path_unsafe")
        self.assertNotIn(str(output_path), output)
        self.assertEqual(output_path.read_bytes(), b"existing")

    def test_apply_rejects_invalid_plan_before_execution_service(self) -> None:
        source_path = self.root / "must-not-be-read-apply.pmx"
        output_path = self.root / "must-not-be-created.pmx"
        self.plan_path.write_text(
            '{"schema_version":1,"operations":[],"unknown":true}',
            encoding="utf-8",
        )

        with patch.object(
            transaction_plan_cli,
            "apply_structural_transaction_plan",
        ) as apply_plan:
            exit_code, output, error_output = _capture_run(
                [
                    "transaction-plan",
                    "apply",
                    str(source_path),
                    str(self.plan_path),
                    str(output_path),
                    "--json",
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(error_output, "")
        apply_plan.assert_not_called()
        self.assertFalse(output_path.exists())
        payload = json.loads(output)
        self.assertEqual(payload["error_type"], "invalid_plan")
        self.assertNotIn(str(source_path), output)
        self.assertNotIn(str(output_path), output)

    def test_invalid_plan_maps_to_exit_one_without_value_or_path_leakage(
        self,
    ) -> None:
        payload = _valid_payload()
        operation = payload["operations"][0]
        assert isinstance(operation, dict)
        operation["private_payload"] = r"C:\private\秘密-model.pmx"
        self.plan_path.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )

        exit_code, output, error_output = _capture_run(
            [
                "transaction-plan",
                "validate",
                str(self.plan_path),
                "--json",
            ]
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(error_output, "")
        diagnostic = json.loads(output)
        self.assertEqual(diagnostic["status"], "error")
        self.assertEqual(diagnostic["command"], "transaction-plan")
        self.assertEqual(diagnostic["action"], "validate")
        self.assertEqual(diagnostic["error_type"], "invalid_plan")
        self.assertEqual(
            diagnostic["error"]["code"],
            "transaction_plan_invalid",
        )
        self.assertNotIn("秘密-model", output)
        self.assertNotIn("C:\\\\private", output)
        self.assertNotIn(str(self.plan_path), output)

    def test_missing_file_maps_to_exit_two_without_path_leakage(self) -> None:
        missing = self.root / "秘密-plan.json"

        text_code, text_output, text_error = _capture_run(
            ["transaction-plan", "explain", str(missing)]
        )
        json_code, json_output, json_error = _capture_run(
            ["transaction-plan", "explain", str(missing), "--json"]
        )

        self.assertEqual(text_code, 2)
        self.assertEqual(text_output, "")
        self.assertIn("[ERROR] transaction-plan explain:", text_error)
        self.assertNotIn(str(missing), text_error)

        self.assertEqual(json_code, 2)
        self.assertEqual(json_error, "")
        payload = json.loads(json_output)
        self.assertEqual(payload["error_type"], "io")
        self.assertEqual(payload["error"]["code"], "service_io_failed")
        self.assertNotIn(str(missing), json_output)

    def test_validate_and_explain_delegate_through_cp15_service(self) -> None:
        with patch.object(
            transaction_plan_cli,
            "load_structural_transaction_plan",
            wraps=service.load_structural_transaction_plan,
        ) as load:
            exit_code, _, _ = _capture_run(
                ["transaction-plan", "validate", str(self.plan_path)]
            )
        self.assertEqual(exit_code, 0)
        load.assert_called_once_with(str(self.plan_path))

        with (
            patch.object(
                transaction_plan_cli,
                "load_structural_transaction_plan",
                wraps=service.load_structural_transaction_plan,
            ) as load,
            patch.object(
                transaction_plan_cli,
                "explain_structural_transaction_plan",
                wraps=service.explain_structural_transaction_plan,
            ) as explain,
        ):
            exit_code, _, _ = _capture_run(
                ["transaction-plan", "explain", str(self.plan_path)]
            )
        self.assertEqual(exit_code, 0)
        load.assert_called_once_with(str(self.plan_path))
        explain.assert_called_once()

    def test_top_level_runtime_help_surfaces_transaction_plan(self) -> None:
        output = io.StringIO()
        error_output = io.StringIO()
        with (
            redirect_stdout(output),
            redirect_stderr(error_output),
            self.assertRaises(SystemExit) as raised,
        ):
            cli.run(["--help"])

        self.assertEqual(raised.exception.code, 0)
        self.assertEqual(error_output.getvalue(), "")
        self.assertIn("transaction-plan", output.getvalue())
        for command in EXPECTED_LEGACY_COMMANDS:
            self.assertIn(command, output.getvalue())

    def test_main_internal_error_boundary_redacts_exception_text(self) -> None:
        secret = "C:/private/秘密-internal.txt"
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch.object(cli, "run", side_effect=RuntimeError(secret)),
            patch.object(
                sys,
                "argv",
                [
                    "mmd-asset-registry",
                    "transaction-plan",
                    "validate",
                    "plan.json",
                    "--json",
                ],
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
            self.assertRaises(SystemExit) as raised,
        ):
            cli.main()

        self.assertEqual(raised.exception.code, 3)
        self.assertEqual(stderr.getvalue(), "")
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["command"], "transaction-plan")
        self.assertEqual(payload["action"], "validate")
        self.assertEqual(payload["error_type"], "internal")
        self.assertNotIn(secret, stdout.getvalue())

    def test_transaction_plan_cli_routes_execution_only_through_plan_services(
        self,
    ) -> None:
        source = inspect.getsource(transaction_plan_cli)
        for forbidden in (
            "preview_structural_transaction(",
            "_write_structural_transaction",
            "structural_output",
            "_commit_verified_bytes",
            "write_pmx",
            "read_pmx",
            "load_pmx",
            "PmxIndexRemap",
            "final_index =",
            "hashlib",
            ".open(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)
        self.assertIn(
            "preview_structural_transaction_plan",
            source,
        )
        self.assertIn(
            "apply_structural_transaction_plan",
            source,
        )

    def test_transaction_plan_cli_import_does_not_load_writer_or_cli_cycle(
        self,
    ) -> None:
        script = "\n".join(
            (
                "import sys",
                "import mmd_registry.transaction_plan_cli as module",
                "assert module.__all__",
                "assert 'mmd_registry.pmx.structural_output' not in sys.modules",
                "assert 'mmd_registry.cli' not in sys.modules",
                "assert 'argparse' in sys.modules",
            )
        )
        subprocess.check_call(
            (sys.executable, "-c", script),
            cwd=Path(__file__).resolve().parents[1],
        )

    def test_module_surface_is_explicit_and_not_root_promoted(self) -> None:
        module = importlib.import_module("mmd_registry.transaction_plan_cli")
        self.assertEqual(
            module.__all__,
            (
                "TRANSACTION_PLAN_COMMAND_NAME",
                "add_transaction_plan_parser",
                "run_transaction_plan_command",
                "print_unexpected_transaction_plan_error",
            ),
        )
        self.assertEqual(
            module.TRANSACTION_PLAN_COMMAND_NAME,
            "transaction-plan",
        )


if __name__ == "__main__":
    unittest.main()
