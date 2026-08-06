"""Tests for UTF-8 CLI output when Windows redirects streams."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mmd_registry.cli import main


class _FakeScanResult:
    """Minimal successful scan result used by CLI encoding tests."""

    errors: list[str] = []
    warnings: list[str] = []
    scan_complete = True
    texture_paths: list[str] = []
    dependency_summary = SimpleNamespace(
        referenced_texture_indices=[],
    )

    def to_dict(self) -> dict[str, object]:
        """Return a Unicode payload representative of a real PMX scan."""

        return {
            "status": "ok",
            "scan_complete": True,
            "model_info": {
                "local_name": "芙拉薇娅",
            },
            "texture_paths": [],
        }


class _FakeDiagnostics:
    """Minimal successful texture diagnostics result."""

    error_count = 0
    warning_count = 0

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable diagnostic payload."""

        return {
            "status": "ok",
            "dependencies": [],
        }


class CliUtf8OutputTests(unittest.TestCase):
    """Verify redirected stdout and stderr are explicitly UTF-8."""

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_directory.name)
        self.model_path = self.project_root / "芙拉薇娅.pmx"
        self.model_path.write_bytes(b"fixture")

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def run_main_with_legacy_streams(
        self,
        arguments: list[str],
    ) -> tuple[int, bytes, bytes]:
        """Run main with streams initially configured as Windows cp1252."""

        stdout_bytes = io.BytesIO()
        stderr_bytes = io.BytesIO()
        stdout = io.TextIOWrapper(stdout_bytes, encoding="cp1252")
        stderr = io.TextIOWrapper(stderr_bytes, encoding="cp1252")

        try:
            with (
                patch.object(
                    sys,
                    "argv",
                    ["check_assets.py", *arguments],
                ),
                patch.object(sys, "stdout", stdout),
                patch.object(sys, "stderr", stderr),
            ):
                with self.assertRaises(SystemExit) as exit_context:
                    main()

            stdout.flush()
            stderr.flush()
            return (
                int(exit_context.exception.code),
                stdout_bytes.getvalue(),
                stderr_bytes.getvalue(),
            )
        finally:
            stdout.detach()
            stderr.detach()

    def test_scan_json_redirection_writes_utf8(self) -> None:
        """Unicode model paths and names survive stdout redirection."""

        with patch(
            "mmd_registry.cli.scan_pmx_structure",
            return_value=_FakeScanResult(),
        ):
            exit_code, stdout, stderr = self.run_main_with_legacy_streams(
                ["scan", str(self.model_path), "--json"]
            )

        payload = json.loads(stdout.decode("utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, b"")
        self.assertEqual(payload["model_info"]["local_name"], "芙拉薇娅")
        self.assertTrue(payload["path"].endswith("芙拉薇娅.pmx"))

    def test_doctor_json_redirection_writes_utf8(self) -> None:
        """Combined doctor JSON is written as UTF-8 when redirected."""

        with (
            patch(
                "mmd_registry.cli.scan_pmx_structure",
                return_value=_FakeScanResult(),
            ),
            patch(
                "mmd_registry.cli.diagnose_texture_dependencies",
                return_value=_FakeDiagnostics(),
            ),
        ):
            exit_code, stdout, stderr = self.run_main_with_legacy_streams(
                ["doctor", str(self.model_path), "--json"]
            )

        payload = json.loads(stdout.decode("utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, b"")
        self.assertEqual(
            payload["scan"]["model_info"]["local_name"],
            "芙拉薇娅",
        )
        self.assertEqual(payload["texture_diagnostics"]["status"], "ok")

    def test_internal_error_redirection_writes_utf8_stderr(self) -> None:
        """Unexpected Unicode errors also survive stderr redirection."""

        with patch(
            "mmd_registry.cli.run",
            side_effect=RuntimeError("芙拉薇娅 failure"),
        ):
            exit_code, stdout, stderr = self.run_main_with_legacy_streams([])

        self.assertEqual(exit_code, 3)
        self.assertEqual(stdout, b"")
        self.assertIn("芙拉薇娅 failure", stderr.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
