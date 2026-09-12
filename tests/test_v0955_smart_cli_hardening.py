"""CP09 input, error, path, and UTF-8 hardening for Smart Inspect."""

from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import mmd_registry.cli as cli
import mmd_registry.smart_cli as smart_cli
from tests.mmd_fixtures import build_pmx_material, build_pmx_structure


class SmartCliInputErrorEncodingHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_directory.name)
        self.valid_bytes = build_pmx_structure(
            deform_types=(),
            surface_indices=(),
            materials=(
                build_pmx_material(
                    local_name="瞳",
                    universal_name="Eyes",
                    surface_index_count=0,
                ),
            ),
        )

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def capture_run(self, source: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = cli.run(["smart", "inspect", source])
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def write_valid(self, relative: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.valid_bytes)
        return path

    def run_main_with_legacy_streams(
        self,
        arguments: list[str],
        *,
        inspect_side_effect: Exception | None = None,
    ) -> tuple[int, bytes, bytes]:
        stdout_bytes = io.BytesIO()
        stderr_bytes = io.BytesIO()
        stdout = io.TextIOWrapper(stdout_bytes, encoding="cp1252")
        stderr = io.TextIOWrapper(stderr_bytes, encoding="cp1252")

        try:
            patches = [
                patch.object(sys, "argv", ["check_assets.py", *arguments]),
                patch.object(sys, "stdout", stdout),
                patch.object(sys, "stderr", stderr),
            ]
            if inspect_side_effect is not None:
                patches.append(
                    patch.object(
                        smart_cli,
                        "inspect_smart_parts",
                        side_effect=inspect_side_effect,
                    )
                )

            with patches[0], patches[1], patches[2]:
                if len(patches) == 4:
                    with patches[3]:
                        with self.assertRaises(SystemExit) as raised:
                            cli.main()
                else:
                    with self.assertRaises(SystemExit) as raised:
                        cli.main()

            stdout.flush()
            stderr.flush()
            return (
                int(raised.exception.code),
                stdout_bytes.getvalue(),
                stderr_bytes.getvalue(),
            )
        finally:
            stdout.detach()
            stderr.detach()

    def assert_expected_error(
        self,
        source: str,
        *,
        exit_code: int,
        message: str,
    ) -> None:
        actual_exit, stdout, stderr = self.capture_run(source)
        self.assertEqual(actual_exit, exit_code)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, f"[ERROR] smart inspect: {message}\n")
        self.assertNotIn("Traceback", stderr)
        self.assertNotIn(source, stderr)

    def test_missing_file_is_safe_io_error(self) -> None:
        missing = self.root / "missing 日本語 model.pmx"
        self.assert_expected_error(
            str(missing),
            exit_code=2,
            message="Service file operation failed.",
        )

    def test_directory_input_is_safe_io_error(self) -> None:
        directory = self.root / "directory input"
        directory.mkdir()
        self.assert_expected_error(
            str(directory),
            exit_code=2,
            message="Service file operation failed.",
        )

    def test_non_pmx_input_is_source_invalid_without_traceback(self) -> None:
        path = self.root / "not a model.txt"
        path.write_bytes(b"This is not PMX data.")
        self.assert_expected_error(
            str(path),
            exit_code=1,
            message="Source PMX data is invalid.",
        )

    def test_corrupt_truncated_pmx_is_source_invalid_without_traceback(self) -> None:
        path = self.root / "truncated model.pmx"
        path.write_bytes(self.valid_bytes[:24])
        self.assert_expected_error(
            str(path),
            exit_code=1,
            message="Source PMX data is invalid.",
        )

    def test_unicode_path_and_japanese_names_are_preserved(self) -> None:
        path = self.write_valid("日本語 フォルダ/モデル 瞳.pmx")

        exit_code, stdout, stderr = self.capture_run(str(path))

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("SMART PART INSPECTION", stdout)
        self.assertIn("Eyes", stdout)
        self.assertIn("瞳", stdout)
        self.assertNotIn(str(path), stdout)

    def test_paths_with_spaces_are_accepted(self) -> None:
        path = self.write_valid("folder with spaces/model with spaces.pmx")

        exit_code, stdout, stderr = self.capture_run(str(path))

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("Eyes", stdout)

    def test_redirected_smart_output_is_utf8(self) -> None:
        path = self.write_valid("UTF8 日本語/瞳 model.pmx")

        exit_code, stdout, stderr = self.run_main_with_legacy_streams(
            ["smart", "inspect", str(path)]
        )

        decoded = stdout.decode("utf-8")
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, b"")
        self.assertIn("SMART PART INSPECTION", decoded)
        self.assertIn("瞳", decoded)

    def test_slash_and_backslash_behavior_is_platform_explicit(self) -> None:
        path = self.write_valid("separator folder/separator model.pmx")
        slash_form = str(path).replace("\\", "/")
        slash_exit, slash_stdout, slash_stderr = self.capture_run(slash_form)

        self.assertEqual(slash_exit, 0)
        self.assertEqual(slash_stderr, "")
        self.assertIn("Eyes", slash_stdout)

        backslash_form = str(path).replace("/", "\\")
        backslash_exit, backslash_stdout, backslash_stderr = self.capture_run(
            backslash_form
        )

        if os.name == "nt":
            self.assertEqual(backslash_exit, 0)
            self.assertEqual(backslash_stderr, "")
            self.assertEqual(backslash_stdout, slash_stdout)
        else:
            self.assertEqual(backslash_exit, 2)
            self.assertEqual(backslash_stdout, "")
            self.assertEqual(
                backslash_stderr,
                "[ERROR] smart inspect: Service file operation failed.\n",
            )

    def test_unexpected_internal_failure_is_redacted(self) -> None:
        private_detail = r"private 日本語 detail C:\秘密\model.pmx"

        exit_code, stdout, stderr = self.run_main_with_legacy_streams(
            ["smart", "inspect", "input.pmx"],
            inspect_side_effect=RuntimeError(private_detail),
        )

        decoded = stderr.decode("utf-8")
        self.assertEqual(exit_code, 3)
        self.assertEqual(stdout, b"")
        self.assertEqual(
            decoded.splitlines(),
            ["[ERROR] smart inspect: Unexpected internal Smart Inspect failure."],
        )
        self.assertNotIn(private_detail, decoded)
        self.assertNotIn("RuntimeError", decoded)
        self.assertNotIn("Traceback", decoded)


if __name__ == "__main__":
    unittest.main()
