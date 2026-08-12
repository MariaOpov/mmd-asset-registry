"""Tests for privacy-safe real-model edit failure validation."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from mmd_registry.pmx.editing.private_failure_validation import (
    main,
    render_private_failure_validation_json,
    render_private_failure_validation_text,
    validate_private_pmx_edit_failures,
)
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


class PmxPrivateFailureValidationTests(unittest.TestCase):
    """Validate private negative paths without retaining edited private output."""

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_directory.name)
        self.source_path = self.project_root / "非公開モデル.pmx"
        self.source_bytes = build_pmx_roundtrip_fixture()
        self.source_path.write_bytes(self.source_bytes)

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def capture_main(self, arguments: list[str]) -> tuple[int, str, str]:
        output = io.StringIO()
        error_output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(error_output):
            exit_code = main(arguments)
        return exit_code, output.getvalue(), error_output.getvalue()

    def assert_no_private_failure_residue(self) -> None:
        self.assertEqual(
            list(self.project_root.glob(".mmd-registry-private-edit-*")),
            [],
        )
        self.assertEqual(list(self.project_root.glob(".*.tmp")), [])

    def test_failure_matrix_preserves_source_and_creates_no_output(self) -> None:
        result = validate_private_pmx_edit_failures(self.source_path)

        self.assertEqual(self.source_path.read_bytes(), self.source_bytes)
        self.assertEqual(result.source_sha256_before, result.source_sha256_after)
        self.assertFalse(result.temporary_residue_created)
        self.assertEqual(
            [scenario.name for scenario in result.scenarios],
            [
                "valid_dry_run",
                "plan_validation_failure",
                "source_hash_mismatch",
                "input_output_alias_refusal",
                "temporary_residue",
            ],
        )
        self.assert_no_private_failure_residue()

    def test_failure_diagnostics_have_expected_phases(self) -> None:
        result = validate_private_pmx_edit_failures(self.source_path)
        scenarios = {scenario.name: scenario for scenario in result.scenarios}

        self.assertEqual(
            scenarios["plan_validation_failure"].code,
            "edit_plan_invalid",
        )
        self.assertEqual(
            scenarios["plan_validation_failure"].phase,
            "plan_validate",
        )
        self.assertEqual(
            scenarios["source_hash_mismatch"].code,
            "edit_preflight_failed",
        )
        self.assertEqual(
            scenarios["source_hash_mismatch"].phase,
            "preflight",
        )
        self.assertEqual(
            scenarios["input_output_alias_refusal"].phase,
            "preflight",
        )

    def test_supports_pmx20_utf16_without_persisting_output(self) -> None:
        self.source_bytes = build_pmx_roundtrip_fixture(
            version=2.0,
            encoding_flag=0,
            index_sizes=(4, 1, 2, 4, 1, 2),
        )
        self.source_path.write_bytes(self.source_bytes)

        result = validate_private_pmx_edit_failures(self.source_path)

        self.assertEqual(result.version, 2.0)
        self.assertEqual(result.encoding, "utf-16-le")
        self.assertEqual(self.source_path.read_bytes(), self.source_bytes)
        self.assert_no_private_failure_residue()

    def test_reports_do_not_expose_absolute_private_path(self) -> None:
        result = validate_private_pmx_edit_failures(self.source_path)

        text = render_private_failure_validation_text(result)
        json_text = render_private_failure_validation_json(result)
        payload = json.loads(json_text)

        self.assertNotIn(str(self.project_root), text)
        self.assertNotIn(str(self.project_root), json_text)
        self.assertEqual(payload["source"]["name"], "非公開モデル.pmx")
        self.assertTrue(payload["invariants"]["source_unchanged"])
        self.assertFalse(payload["invariants"]["temporary_residue_created"])
        self.assertFalse(payload["invariants"]["private_asset_persisted"])

    def test_json_cli_is_privacy_safe(self) -> None:
        exit_code, output, error_output = self.capture_main(
            [str(self.source_path), "--json"]
        )
        payload = json.loads(output)

        self.assertEqual(exit_code, 0)
        self.assertEqual(error_output, "")
        self.assertEqual(payload["status"], "ok")
        self.assertNotIn(str(self.project_root), output)
        self.assertFalse(payload["invariants"]["private_asset_persisted"])
        self.assert_no_private_failure_residue()


if __name__ == "__main__":
    unittest.main()
