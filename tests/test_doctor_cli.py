"""Tests for the PMX doctor command-line workflow."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from mmd_registry.cli import normalize_arguments, run
from mmd_registry.model_scanning import PmxHeaderScanResult
from tests.mmd_fixtures import (
    build_minimal_pmd_header,
    build_pmx_material,
    build_pmx_structure,
)


class DoctorCliTests(unittest.TestCase):
    """Tests for structural scan plus texture dependency diagnostics."""

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_directory.name)

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def capture_run(
        self,
        arguments: list[str],
    ) -> tuple[int, str, str]:
        """Run the CLI while capturing both output streams."""

        output = io.StringIO()
        error_output = io.StringIO()

        with redirect_stdout(output), redirect_stderr(error_output):
            exit_code = run(arguments)

        return exit_code, output.getvalue(), error_output.getvalue()

    def build_model(
        self,
        *,
        texture_paths: tuple[str, ...] = (),
        referenced_texture_index: int | None = None,
        trailing_bytes: bytes = b"",
    ) -> Path:
        """Create one complete PMX model fixture."""

        if referenced_texture_index is None:
            materials: tuple[bytes, ...] = ()
            surface_indices: tuple[int, ...] = ()
        else:
            materials = (
                build_pmx_material(
                    texture_index=referenced_texture_index,
                    surface_index_count=3,
                ),
            )
            surface_indices = (0, 0, 0)

        model_path = self.project_root / "model.pmx"
        model_path.write_bytes(
            build_pmx_structure(
                surface_indices=surface_indices,
                texture_paths=texture_paths,
                materials=materials,
                trailing_bytes=trailing_bytes,
            )
        )
        return model_path

    def test_doctor_command_is_preserved(self) -> None:
        self.assertEqual(
            normalize_arguments(["doctor", "model.pmx"]),
            ["doctor", "model.pmx"],
        )

    def test_doctor_valid_model_without_textures_returns_zero(self) -> None:
        model_path = self.build_model()

        exit_code, output, error_output = self.capture_run(["doctor", str(model_path)])

        self.assertEqual(exit_code, 0)
        self.assertEqual(error_output, "")
        self.assertIn("Status: ok", output)
        self.assertIn("Structural scan:", output)
        self.assertIn("  Complete: yes", output)
        self.assertIn("Texture filesystem diagnostics:", output)
        self.assertIn("  Declared: 0", output)

    def test_doctor_existing_referenced_texture_returns_zero(self) -> None:
        texture_path = self.project_root / "textures" / "body.png"
        texture_path.parent.mkdir()
        texture_path.write_bytes(b"texture")
        model_path = self.build_model(
            texture_paths=("textures/body.png",),
            referenced_texture_index=0,
        )

        exit_code, output, _ = self.capture_run(["doctor", str(model_path)])

        self.assertEqual(exit_code, 0)
        self.assertIn("  Existing files: 1", output)
        self.assertIn("[0] ok | referenced | textures/body.png", output)

    def test_doctor_missing_referenced_texture_returns_one(self) -> None:
        model_path = self.build_model(
            texture_paths=("textures/missing.png",),
            referenced_texture_index=0,
        )

        exit_code, output, _ = self.capture_run(["doctor", str(model_path)])

        self.assertEqual(exit_code, 1)
        self.assertIn("Status: error", output)
        self.assertIn("[0] error | referenced", output)
        self.assertIn("missing_file", output)

    def test_doctor_missing_unreferenced_texture_is_warning(self) -> None:
        model_path = self.build_model(
            texture_paths=("textures/unused.png",),
        )

        exit_code, output, _ = self.capture_run(["doctor", str(model_path)])

        self.assertEqual(exit_code, 0)
        self.assertIn("Status: warning", output)
        self.assertIn("[0] warning | unreferenced", output)
        self.assertIn("missing_file", output)

    def test_doctor_scan_warning_returns_zero(self) -> None:
        model_path = self.build_model(trailing_bytes=b"XYZ")

        exit_code, output, _ = self.capture_run(["doctor", str(model_path)])

        self.assertEqual(exit_code, 0)
        self.assertIn("Status: warning", output)
        self.assertIn("  Trailing bytes: 3", output)
        self.assertIn("Texture filesystem diagnostics:", output)

    def test_doctor_json_output_combines_scan_and_diagnostics(self) -> None:
        texture_path = self.project_root / "body.png"
        texture_path.write_bytes(b"texture")
        model_path = self.build_model(
            texture_paths=("body.png",),
            referenced_texture_index=0,
        )

        exit_code, output, error_output = self.capture_run(
            ["doctor", str(model_path), "--json"]
        )
        report = json.loads(output)

        self.assertEqual(exit_code, 0)
        self.assertEqual(error_output, "")
        self.assertEqual(report["status"], "ok")
        self.assertTrue(report["scan"]["scan_complete"])
        self.assertEqual(
            report["texture_diagnostics"]["existing_file_count"],
            1,
        )
        self.assertEqual(
            report["texture_diagnostics"]["dependencies"][0]["status"],
            "ok",
        )

    def test_doctor_malformed_model_skips_diagnostics(self) -> None:
        model_path = self.project_root / "malformed.pmx"
        model_path.write_bytes(b"")

        exit_code, output, _ = self.capture_run(["doctor", str(model_path), "--json"])
        report = json.loads(output)

        self.assertEqual(exit_code, 1)
        self.assertEqual(report["status"], "error")
        self.assertFalse(report["scan"]["scan_complete"])
        self.assertIsNone(report["texture_diagnostics"])

    def test_doctor_pmd_is_reported_as_unsupported(self) -> None:
        model_path = self.project_root / "model.pmd"
        model_path.write_bytes(build_minimal_pmd_header("Doctor PMD"))

        exit_code, output, _ = self.capture_run(["doctor", str(model_path)])

        self.assertEqual(exit_code, 1)
        self.assertIn("Status: error", output)
        self.assertIn("Complete: no", output)
        self.assertNotIn("Texture filesystem diagnostics:", output)

    def test_doctor_missing_file_returns_two(self) -> None:
        missing_path = self.project_root / "missing.pmx"

        exit_code, output, error_output = self.capture_run(
            ["doctor", str(missing_path)]
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(output, "")
        self.assertIn("[ERROR] doctor: File does not exist", error_output)

    def test_doctor_missing_file_json_is_machine_readable(self) -> None:
        missing_path = self.project_root / "missing.pmx"

        exit_code, output, error_output = self.capture_run(
            ["doctor", str(missing_path), "--json"]
        )
        report = json.loads(output)

        self.assertEqual(exit_code, 2)
        self.assertEqual(error_output, "")
        self.assertEqual(report["status"], "error")
        self.assertFalse(report["internal_error"])
        self.assertIsNone(report["scan"])
        self.assertIsNone(report["texture_diagnostics"])

    def test_doctor_scan_internal_failure_returns_three(self) -> None:
        model_path = self.project_root / "model.pmx"
        model_path.write_bytes(b"fixture")

        with patch(
            "mmd_registry.cli.scan_pmx_structure",
            side_effect=RuntimeError("boom"),
        ):
            exit_code, output, error_output = self.capture_run(
                ["doctor", str(model_path)]
            )

        self.assertEqual(exit_code, 3)
        self.assertEqual(output, "")
        self.assertIn("Internal scan failure: boom", error_output)

    def test_doctor_dependency_failure_returns_three(self) -> None:
        model_path = self.build_model()

        with patch(
            "mmd_registry.cli.diagnose_texture_dependencies",
            side_effect=RuntimeError("boom"),
        ):
            exit_code, output, _ = self.capture_run(
                ["doctor", str(model_path), "--json"]
            )

        report = json.loads(output)
        self.assertEqual(exit_code, 3)
        self.assertTrue(report["internal_error"])
        self.assertIn(
            "Internal dependency diagnostic failure: boom",
            report["errors"][0],
        )

    def test_complete_scan_without_dependency_summary_returns_three(self) -> None:
        model_path = self.project_root / "model.pmx"
        model_path.write_bytes(b"fixture")
        result = PmxHeaderScanResult(
            detected_format="pmx",
            scan_complete=True,
        )

        with patch(
            "mmd_registry.cli.scan_pmx_structure",
            return_value=result,
        ):
            exit_code, output, _ = self.capture_run(
                ["doctor", str(model_path), "--json"]
            )

        report = json.loads(output)
        self.assertEqual(exit_code, 3)
        self.assertTrue(report["internal_error"])
        self.assertIn("dependency summary", report["errors"][0])


if __name__ == "__main__":
    unittest.main()
