"""Generated tests for ephemeral private-model edit validation."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from mmd_registry.pmx.editing.private_validation import (
    PmxPrivateValidationError,
    main,
    render_private_validation_json,
    render_private_validation_text,
    validate_private_pmx_edit,
)
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


class PmxPrivateEditValidationTests(unittest.TestCase):
    """Validate cleanup, privacy-safe reporting, and exact real-model checks."""

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_directory.name)
        self.source_path = self.project_root / "非公開モデル.pmx"
        self.source_bytes = build_pmx_roundtrip_fixture()
        self.source_path.write_bytes(self.source_bytes)

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def capture_main(self, arguments: list[str]) -> tuple[int, str, str]:
        """Run the private validator and capture both streams."""

        output = io.StringIO()
        error_output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(error_output):
            exit_code = main(arguments)
        return exit_code, output.getvalue(), error_output.getvalue()

    def assert_no_validation_temporary_files(self) -> None:
        """Require all plan/output directories to have been removed."""

        self.assertEqual(
            list(self.project_root.glob(".mmd-registry-private-edit-*")),
            [],
        )

    def test_generated_real_model_validation_is_ephemeral(self) -> None:
        result = validate_private_pmx_edit(self.source_path)

        self.assertEqual(self.source_path.read_bytes(), self.source_bytes)
        self.assertTrue(result.temporary_files_removed)
        self.assertEqual(result.source_name, "非公開モデル.pmx")
        self.assertEqual(result.version, 2.1)
        self.assertEqual(result.encoding, "utf-8")
        self.assertEqual(result.material_index, 0)
        self.assertEqual(result.changed_fields, 3)
        self.assert_no_validation_temporary_files()

    def test_private_validation_supports_pmx20_utf16_mixed_widths(self) -> None:
        self.source_bytes = build_pmx_roundtrip_fixture(
            version=2.0,
            encoding_flag=0,
            index_sizes=(4, 1, 2, 4, 1, 2),
        )
        self.source_path.write_bytes(self.source_bytes)

        result = validate_private_pmx_edit(
            self.source_path,
            material_index=1,
        )

        self.assertEqual(result.version, 2.0)
        self.assertEqual(result.encoding, "utf-16-le")
        self.assertEqual(result.material_index, 1)
        self.assertEqual(self.source_path.read_bytes(), self.source_bytes)
        self.assert_no_validation_temporary_files()

    def test_reports_do_not_contain_absolute_private_path(self) -> None:
        result = validate_private_pmx_edit(self.source_path)

        text = render_private_validation_text(result)
        json_text = render_private_validation_json(result)
        payload = json.loads(json_text)

        self.assertNotIn(str(self.project_root), text)
        self.assertNotIn(str(self.project_root), json_text)
        self.assertIn("Source unchanged: yes", text)
        self.assertIn("Private asset persisted: no", text)
        self.assertEqual(payload["status"], "ok")
        self.assertFalse(payload["invariants"]["private_asset_persisted"])
        self.assertTrue(payload["invariants"]["temporary_files_removed"])

    def test_private_texture_files_are_never_touched(self) -> None:
        texture_directory = self.project_root / "テクスチャ"
        texture_directory.mkdir()
        texture_path = texture_directory / "体.png"
        texture_bytes = b"private texture sentinel"
        texture_path.write_bytes(texture_bytes)

        validate_private_pmx_edit(self.source_path)

        self.assertEqual(texture_path.read_bytes(), texture_bytes)
        self.assertEqual(self.source_path.read_bytes(), self.source_bytes)
        self.assert_no_validation_temporary_files()

    def test_invalid_material_index_is_rejected_without_temporary_files(self) -> None:
        with self.assertRaisesRegex(
            PmxPrivateValidationError,
            "out of range",
        ):
            validate_private_pmx_edit(self.source_path, material_index=99)

        self.assertEqual(self.source_path.read_bytes(), self.source_bytes)
        self.assert_no_validation_temporary_files()

    def test_write_failure_cleans_temporary_plan_and_output(self) -> None:
        with patch(
            "mmd_registry.pmx.editing.private_validation.write_pmx_edit",
            side_effect=OSError("simulated private output failure"),
        ):
            with self.assertRaisesRegex(OSError, "output failure"):
                validate_private_pmx_edit(self.source_path)

        self.assertEqual(self.source_path.read_bytes(), self.source_bytes)
        self.assert_no_validation_temporary_files()

    def test_json_cli_report_is_privacy_safe(self) -> None:
        exit_code, output, error_output = self.capture_main(
            [str(self.source_path), "--json"]
        )
        payload = json.loads(output)

        self.assertEqual(exit_code, 0)
        self.assertEqual(error_output, "")
        self.assertEqual(payload["source"]["name"], "非公開モデル.pmx")
        self.assertNotIn(str(self.project_root), output)
        self.assertFalse(payload["invariants"]["private_asset_persisted"])
        self.assert_no_validation_temporary_files()

    def test_cli_data_error_has_no_traceback_or_private_path(self) -> None:
        exit_code, output, error_output = self.capture_main(
            [str(self.source_path), "--material-index", "99"]
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(output, "")
        self.assertIn("out of range", error_output)
        self.assertNotIn("Traceback", error_output)
        self.assertNotIn(str(self.project_root), error_output)


if __name__ == "__main__":
    unittest.main()
