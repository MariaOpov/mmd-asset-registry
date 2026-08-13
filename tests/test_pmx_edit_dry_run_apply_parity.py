"""Explicit dry-run/apply semantic-parity contracts for PMX editing."""

from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from mmd_registry.cli import run
from mmd_registry.pmx import load_pmx, serialize_pmx
from mmd_registry.pmx.editing.json_loader import parse_pmx_edit_plan_json
from mmd_registry.pmx.editing.output import write_pmx_edit
from mmd_registry.pmx.editing.preview import dry_run_pmx_edit
from tests.mmd_fixtures import build_pmx_bone, build_pmx_structure


class PmxEditDryRunApplyParityTests(unittest.TestCase):
    """Freeze dry-run as the semantic source of truth for verified apply."""

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_directory.name)
        self.input_path = self.root / "input.pmx"
        self.source_bytes = build_pmx_structure(
            bones=(build_pmx_bone(),),
        )
        self.input_path.write_bytes(self.source_bytes)
        self.changed_plan = parse_pmx_edit_plan_json(
            json.dumps(
                {
                    "schema_version": 1,
                    "operations": [
                        {
                            "op": "set_model_info",
                            "local_name": "Parity モデル 🌸",
                        }
                    ],
                },
                ensure_ascii=False,
            )
        )

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    @staticmethod
    def _common_report_contract(payload: dict[str, object]) -> dict[str, object]:
        source = payload["source"]
        if not isinstance(source, dict):
            raise AssertionError("source report must be an object")
        return {
            "preview_schema_version": payload["preview_schema_version"],
            "source": {
                "sha256": source["sha256"],
                "size_bytes": source["size_bytes"],
            },
            "plan": payload["plan"],
            "verification": payload["verification"],
            "audit": payload["audit"],
        }

    def _noop_plan(self):
        source = load_pmx(io.BytesIO(self.source_bytes))
        return parse_pmx_edit_plan_json(
            json.dumps(
                {
                    "schema_version": 1,
                    "operations": [
                        {
                            "op": "set_model_info",
                            "local_name": source.model_info.local_name,
                        }
                    ],
                },
                ensure_ascii=False,
            )
        )

    def _write_plan_file(self, plan_payload: dict[str, object], name: str) -> Path:
        path = self.root / name
        path.write_text(
            json.dumps(plan_payload, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    @staticmethod
    def _capture_cli(arguments: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = run(arguments)
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_api_apply_commits_exact_verified_preview_document(self) -> None:
        preview = dry_run_pmx_edit(self.source_bytes, self.changed_plan)
        expected_bytes = serialize_pmx(preview.document)
        output_path = self.root / "output.pmx"

        result = write_pmx_edit(
            self.input_path,
            output_path,
            self.changed_plan,
        )

        self.assertEqual(result.preview, preview)
        self.assertEqual(output_path.read_bytes(), expected_bytes)
        self.assertEqual(load_pmx(output_path), preview.document)
        self.assertEqual(
            result.output_sha256,
            hashlib.sha256(expected_bytes).hexdigest(),
        )
        self.assertEqual(result.output_size_bytes, len(expected_bytes))
        self.assertEqual(self.input_path.read_bytes(), self.source_bytes)

    def test_api_dry_run_and_apply_reports_share_semantic_contract(self) -> None:
        preview = dry_run_pmx_edit(self.source_bytes, self.changed_plan)
        output_path = self.root / "report-output.pmx"
        result = write_pmx_edit(
            self.input_path,
            output_path,
            self.changed_plan,
        )

        preview_payload = preview.to_dict()
        write_payload = result.to_dict()

        self.assertEqual(result.preview, preview)
        self.assertEqual(
            self._common_report_contract(write_payload),
            self._common_report_contract(preview_payload),
        )
        self.assertEqual(preview_payload["status"], "changes_pending")
        self.assertEqual(write_payload["status"], "written")
        self.assertTrue(preview_payload["dry_run"])
        self.assertFalse(write_payload["dry_run"])
        self.assertEqual(
            preview_payload["output"],
            {"written": False, "sha256": None},
        )
        self.assertTrue(write_payload["output"]["written"])  # type: ignore[index]

    def test_noop_dry_run_and_apply_keep_identical_audit_and_semantics(self) -> None:
        plan = self._noop_plan()
        preview = dry_run_pmx_edit(self.source_bytes, plan)
        output_path = self.root / "noop-output.pmx"

        result = write_pmx_edit(self.input_path, output_path, plan)

        self.assertEqual(result.preview, preview)
        self.assertEqual(preview.status, "no_changes")
        self.assertEqual(result.status, "no_changes")
        self.assertEqual(preview.audit, result.preview.audit)
        self.assertEqual(preview.audit.changed_fields, 0)
        self.assertEqual(load_pmx(output_path), preview.document)
        self.assertEqual(
            output_path.read_bytes(),
            serialize_pmx(preview.document),
        )
        self.assertEqual(self.input_path.read_bytes(), self.source_bytes)

    def test_cli_json_dry_run_and_write_share_common_semantic_report(self) -> None:
        plan_payload = {
            "schema_version": 1,
            "operations": [
                {
                    "op": "set_model_info",
                    "local_name": "CLI parity 🌸",
                }
            ],
        }
        plan_path = self._write_plan_file(plan_payload, "plan.json")
        output_path = self.root / "cli-output.pmx"

        dry_code, dry_stdout, dry_stderr = self._capture_cli(
            [
                "edit",
                str(self.input_path),
                str(output_path),
                "--plan",
                str(plan_path),
                "--dry-run",
                "--json",
            ]
        )

        self.assertEqual(dry_code, 0)
        self.assertEqual(dry_stderr, "")
        self.assertFalse(output_path.exists())
        dry_payload = json.loads(dry_stdout)

        write_code, write_stdout, write_stderr = self._capture_cli(
            [
                "edit",
                str(self.input_path),
                str(output_path),
                "--plan",
                str(plan_path),
                "--json",
            ]
        )

        self.assertEqual(write_code, 0)
        self.assertEqual(write_stderr, "")
        write_payload = json.loads(write_stdout)

        self.assertEqual(
            self._common_report_contract(write_payload),
            self._common_report_contract(dry_payload),
        )
        self.assertEqual(dry_payload["status"], "changes_pending")
        self.assertEqual(write_payload["status"], "written")
        self.assertTrue(dry_payload["dry_run"])
        self.assertFalse(write_payload["dry_run"])
        self.assertFalse(dry_payload["output"]["written"])
        self.assertTrue(write_payload["output"]["written"])
        self.assertEqual(
            write_payload["output"]["sha256"],
            hashlib.sha256(output_path.read_bytes()).hexdigest(),
        )
        self.assertEqual(self.input_path.read_bytes(), self.source_bytes)

    def test_cli_json_noop_status_and_audit_match_between_modes(self) -> None:
        source = load_pmx(io.BytesIO(self.source_bytes))
        plan_payload = {
            "schema_version": 1,
            "operations": [
                {
                    "op": "set_model_info",
                    "local_name": source.model_info.local_name,
                }
            ],
        }
        plan_path = self._write_plan_file(plan_payload, "noop-plan.json")
        output_path = self.root / "cli-noop-output.pmx"

        dry_code, dry_stdout, dry_stderr = self._capture_cli(
            [
                "edit",
                str(self.input_path),
                str(output_path),
                "--plan",
                str(plan_path),
                "--dry-run",
                "--json",
            ]
        )
        self.assertEqual(dry_code, 0)
        self.assertEqual(dry_stderr, "")
        self.assertFalse(output_path.exists())

        write_code, write_stdout, write_stderr = self._capture_cli(
            [
                "edit",
                str(self.input_path),
                str(output_path),
                "--plan",
                str(plan_path),
                "--json",
            ]
        )
        self.assertEqual(write_code, 0)
        self.assertEqual(write_stderr, "")

        dry_payload = json.loads(dry_stdout)
        write_payload = json.loads(write_stdout)

        self.assertEqual(dry_payload["status"], "no_changes")
        self.assertEqual(write_payload["status"], "no_changes")
        self.assertEqual(dry_payload["audit"], write_payload["audit"])
        self.assertEqual(
            self._common_report_contract(write_payload),
            self._common_report_contract(dry_payload),
        )
        self.assertEqual(load_pmx(output_path), source)
        self.assertEqual(self.input_path.read_bytes(), self.source_bytes)


if __name__ == "__main__":
    unittest.main()
