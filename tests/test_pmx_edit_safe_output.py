"""Tests for verified atomic PMX edit output and CLI write mode."""

from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import mmd_registry.pmx.editing.output as edit_output
from mmd_registry.cli import run
from mmd_registry.pmx import load_pmx
from mmd_registry.pmx.editing import (
    PmxEditPathError,
    PmxEditVerificationError,
    dry_run_pmx_edit,
    parse_pmx_edit_plan_json,
    render_pmx_edit_write_json,
    render_pmx_edit_write_text,
    write_pmx_edit,
)
from tests.mmd_fixtures import build_pmx_bone, build_pmx_structure


class PmxEditSafeOutputTests(unittest.TestCase):
    """Validate distinct paths, verification, and atomic commit behavior."""

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_directory.name)
        self.input_path = self.project_root / "入力モデル.pmx"
        self.source_bytes = build_pmx_structure(
            bones=(build_pmx_bone(),),
        )
        self.input_path.write_bytes(self.source_bytes)
        self.plan = parse_pmx_edit_plan_json(
            json.dumps(
                {
                    "schema_version": 1,
                    "operations": [
                        {
                            "op": "set_model_info",
                            "local_name": "編集済みモデル 🌸",
                        }
                    ],
                },
                ensure_ascii=False,
            )
        )

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def temporary_outputs(self, output_path: Path) -> list[Path]:
        """Return unfinished atomic-output files for one destination."""

        return list(output_path.parent.glob(f".{output_path.name}.*.tmp"))

    def test_api_writes_verified_distinct_output_and_preserves_source(self) -> None:
        output_path = self.project_root / "出力モデル.pmx"
        intended = dry_run_pmx_edit(self.source_bytes, self.plan).document

        result = write_pmx_edit(self.input_path, output_path, self.plan)

        self.assertEqual(self.input_path.read_bytes(), self.source_bytes)
        self.assertEqual(load_pmx(output_path), intended)
        self.assertEqual(result.status, "written")
        self.assertEqual(result.output_path, output_path.resolve())
        self.assertEqual(
            result.output_sha256,
            hashlib.sha256(output_path.read_bytes()).hexdigest(),
        )
        self.assertEqual(result.output_size_bytes, output_path.stat().st_size)
        self.assertEqual(self.temporary_outputs(output_path), [])

    def test_api_noop_still_writes_copy_with_clear_status(self) -> None:
        source = load_pmx(io.BytesIO(self.source_bytes))
        plan = parse_pmx_edit_plan_json(
            json.dumps(
                {
                    "schema_version": 1,
                    "operations": [
                        {
                            "op": "set_model_info",
                            "local_name": source.model_info.local_name,
                        }
                    ],
                }
            )
        )
        output_path = self.project_root / "noop.pmx"

        result = write_pmx_edit(self.input_path, output_path, plan)

        self.assertEqual(result.status, "no_changes")
        self.assertEqual(result.preview.audit.changed_fields, 0)
        self.assertEqual(load_pmx(output_path), source)

    def test_default_overwrite_refusal_preserves_existing_output(self) -> None:
        output_path = self.project_root / "existing.pmx"
        output_path.write_bytes(b"existing output")

        with self.assertRaisesRegex(PmxEditPathError, "already exists"):
            write_pmx_edit(self.input_path, output_path, self.plan)

        self.assertEqual(output_path.read_bytes(), b"existing output")

    def test_explicit_overwrite_atomically_replaces_separate_output(self) -> None:
        output_path = self.project_root / "existing.pmx"
        output_path.write_bytes(b"existing output")

        result = write_pmx_edit(
            self.input_path,
            output_path,
            self.plan,
            overwrite=True,
        )

        self.assertEqual(result.status, "written")
        self.assertEqual(
            load_pmx(output_path).model_info.local_name,
            "編集済みモデル 🌸",
        )
        self.assertEqual(self.input_path.read_bytes(), self.source_bytes)
        self.assertEqual(self.temporary_outputs(output_path), [])

    def test_input_path_is_always_refused_as_output(self) -> None:
        for overwrite in (False, True):
            with self.subTest(overwrite=overwrite):
                with self.assertRaisesRegex(
                    PmxEditPathError,
                    "Input and output must be different",
                ):
                    write_pmx_edit(
                        self.input_path,
                        self.input_path,
                        self.plan,
                        overwrite=overwrite,
                    )
        self.assertEqual(self.input_path.read_bytes(), self.source_bytes)

    def test_hardlink_alias_of_input_is_refused(self) -> None:
        output_path = self.project_root / "hardlink.pmx"
        try:
            os.link(self.input_path, output_path)
        except OSError as error:
            self.skipTest(f"hardlinks unavailable: {error}")

        with self.assertRaisesRegex(PmxEditPathError, "same file"):
            write_pmx_edit(
                self.input_path,
                output_path,
                self.plan,
                overwrite=True,
            )

        self.assertEqual(self.input_path.read_bytes(), self.source_bytes)

    def test_symlink_alias_of_input_is_refused(self) -> None:
        output_path = self.project_root / "symlink.pmx"
        try:
            output_path.symlink_to(self.input_path)
        except (NotImplementedError, OSError) as error:
            self.skipTest(f"symlinks unavailable: {error}")

        with self.assertRaisesRegex(PmxEditPathError, "symbolic link"):
            write_pmx_edit(
                self.input_path,
                output_path,
                self.plan,
                overwrite=True,
            )

        self.assertEqual(self.input_path.read_bytes(), self.source_bytes)

    def test_invalid_output_paths_are_refused_before_writing(self) -> None:
        directory_output = self.project_root / "directory.pmx"
        directory_output.mkdir()
        output_parent_file = self.project_root / "parent-file"
        output_parent_file.write_bytes(b"not a directory")
        cases = (
            (self.project_root / "output.bin", ".pmx extension"),
            (self.project_root / "missing" / "output.pmx", "does not exist"),
            (directory_output, "not a file"),
            (output_parent_file / "output.pmx", "not a directory"),
        )
        for output_path, reason in cases:
            with self.subTest(output_path=output_path):
                with self.assertRaisesRegex(PmxEditPathError, reason):
                    write_pmx_edit(self.input_path, output_path, self.plan)

    def test_semantic_mismatch_creates_no_output(self) -> None:
        output_path = self.project_root / "mismatch.pmx"
        source_document = load_pmx(io.BytesIO(self.source_bytes))

        with patch(
            "mmd_registry.pmx.editing.output.load_pmx",
            return_value=source_document,
        ):
            with self.assertRaisesRegex(
                PmxEditVerificationError,
                "intended edited document",
            ):
                write_pmx_edit(self.input_path, output_path, self.plan)

        self.assertFalse(output_path.exists())
        self.assertEqual(self.temporary_outputs(output_path), [])

    def test_external_source_change_before_commit_creates_no_output(self) -> None:
        output_path = self.project_root / "source-changed.pmx"
        serialize_pmx = edit_output.serialize_pmx

        def serialize_then_change_source(document: object) -> bytes:
            data = serialize_pmx(document)  # type: ignore[arg-type]
            self.input_path.write_bytes(b"externally modified")
            return data

        with patch(
            "mmd_registry.pmx.editing.output.serialize_pmx",
            side_effect=serialize_then_change_source,
        ):
            with self.assertRaisesRegex(
                PmxEditVerificationError,
                "source SHA-256 changed before output commit",
            ):
                write_pmx_edit(self.input_path, output_path, self.plan)

        self.assertEqual(self.input_path.read_bytes(), b"externally modified")
        self.assertFalse(output_path.exists())
        self.assertEqual(self.temporary_outputs(output_path), [])

    def test_atomic_replace_failure_preserves_existing_output(self) -> None:
        output_path = self.project_root / "replace-failure.pmx"
        output_path.write_bytes(b"existing output")

        with patch(
            "mmd_registry.pmx.editing.output.os.replace",
            side_effect=OSError("simulated replace failure"),
        ):
            with self.assertRaisesRegex(OSError, "replace failure"):
                write_pmx_edit(
                    self.input_path,
                    output_path,
                    self.plan,
                    overwrite=True,
                )

        self.assertEqual(output_path.read_bytes(), b"existing output")
        self.assertEqual(self.temporary_outputs(output_path), [])

    def test_atomic_create_failure_leaves_no_partial_output(self) -> None:
        output_path = self.project_root / "link-failure.pmx"

        with patch(
            "mmd_registry.pmx.editing.output.os.link",
            side_effect=OSError("simulated link failure"),
        ):
            with self.assertRaisesRegex(OSError, "link failure"):
                write_pmx_edit(self.input_path, output_path, self.plan)

        self.assertFalse(output_path.exists())
        self.assertEqual(self.temporary_outputs(output_path), [])

    def test_atomic_no_clobber_race_is_reported_as_path_error(self) -> None:
        output_path = self.project_root / "race.pmx"

        with patch(
            "mmd_registry.pmx.editing.output.os.link",
            side_effect=FileExistsError("simulated race"),
        ):
            with self.assertRaisesRegex(PmxEditPathError, "already exists"):
                write_pmx_edit(self.input_path, output_path, self.plan)

        self.assertFalse(output_path.exists())
        self.assertEqual(self.temporary_outputs(output_path), [])

    def test_same_source_and_plan_produce_identical_output_bytes(self) -> None:
        first_output = self.project_root / "first.pmx"
        second_output = self.project_root / "second.pmx"

        write_pmx_edit(self.input_path, first_output, self.plan)
        write_pmx_edit(self.input_path, second_output, self.plan)

        self.assertEqual(first_output.read_bytes(), second_output.read_bytes())

    def test_write_report_text_and_json_are_stable(self) -> None:
        output_path = self.project_root / "report.pmx"
        result = write_pmx_edit(self.input_path, output_path, self.plan)

        text = render_pmx_edit_write_text(result)
        payload = json.loads(render_pmx_edit_write_json(result))

        self.assertTrue(text.startswith("PMX EDIT RESULT\n"))
        self.assertIn("Status: 1 field changed", text)
        self.assertIn("Output written: yes", text)
        self.assertEqual(payload["status"], "written")
        self.assertFalse(payload["dry_run"])
        self.assertEqual(payload["output"]["written"], True)
        self.assertEqual(payload["verification"]["semantic"], "passed")
        self.assertEqual(
            payload["audit"]["changes"][0]["after"],
            "編集済みモデル 🌸",
        )

    def test_api_rejects_invalid_argument_types(self) -> None:
        output_path = self.project_root / "output.pmx"
        with self.assertRaisesRegex(TypeError, "plan"):
            write_pmx_edit(  # type: ignore[arg-type]
                self.input_path,
                output_path,
                object(),
            )
        with self.assertRaisesRegex(TypeError, "overwrite"):
            write_pmx_edit(
                self.input_path,
                output_path,
                self.plan,
                overwrite=1,  # type: ignore[arg-type]
            )


class PmxEditWriteCliTests(unittest.TestCase):
    """Validate write-mode CLI reports, safety errors, and exit codes."""

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_directory.name)
        self.input_path = self.project_root / "入力モデル.pmx"
        self.source_bytes = build_pmx_structure(
            bones=(build_pmx_bone(),),
        )
        self.input_path.write_bytes(self.source_bytes)
        self.plan_path = self.project_root / "編集計画.json"
        self.plan_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "operations": [
                        {
                            "op": "set_model_info",
                            "local_name": "CLI 編集 🌸",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def capture_run(
        self,
        arguments: list[str],
    ) -> tuple[int, str, str]:
        """Run the CLI and capture both output streams."""

        output = io.StringIO()
        error_output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(error_output):
            exit_code = run(arguments)
        return exit_code, output.getvalue(), error_output.getvalue()

    def write_arguments(self, output_path: Path, *extra: str) -> list[str]:
        """Return common edit write-mode arguments."""

        return [
            "edit",
            str(self.input_path),
            str(output_path),
            "--plan",
            str(self.plan_path),
            *extra,
        ]

    def test_text_write_succeeds_and_reloads_output(self) -> None:
        output_path = self.project_root / "出力モデル.pmx"

        exit_code, output, error_output = self.capture_run(
            self.write_arguments(output_path)
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(error_output, "")
        self.assertTrue(output.startswith("PMX EDIT RESULT\n"))
        self.assertIn("Output written: yes", output)
        self.assertEqual(
            load_pmx(output_path).model_info.local_name,
            "CLI 編集 🌸",
        )
        self.assertEqual(self.input_path.read_bytes(), self.source_bytes)

    def test_json_write_is_machine_readable_and_unicode_safe(self) -> None:
        output_path = self.project_root / "出力モデル.pmx"

        exit_code, output, error_output = self.capture_run(
            self.write_arguments(output_path, "--json")
        )
        payload = json.loads(output)

        self.assertEqual(exit_code, 0)
        self.assertEqual(error_output, "")
        self.assertEqual(payload["status"], "written")
        self.assertFalse(payload["dry_run"])
        self.assertTrue(payload["output"]["written"])
        self.assertTrue(payload["output"]["path"].endswith("出力モデル.pmx"))
        self.assertEqual(
            payload["audit"]["changes"][0]["after"],
            "CLI 編集 🌸",
        )

    def test_existing_output_requires_explicit_overwrite(self) -> None:
        output_path = self.project_root / "existing.pmx"
        output_path.write_bytes(b"existing output")

        exit_code, output, error_output = self.capture_run(
            self.write_arguments(output_path)
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(output, "")
        self.assertIn("already exists", error_output)
        self.assertEqual(output_path.read_bytes(), b"existing output")

    def test_explicit_overwrite_of_separate_output_succeeds(self) -> None:
        output_path = self.project_root / "existing.pmx"
        output_path.write_bytes(b"existing output")

        exit_code, output, error_output = self.capture_run(
            self.write_arguments(output_path, "--overwrite")
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(error_output, "")
        self.assertIn("Output written: yes", output)
        self.assertEqual(
            load_pmx(output_path).model_info.local_name,
            "CLI 編集 🌸",
        )

    def test_input_output_alias_is_path_error_even_with_overwrite(self) -> None:
        exit_code, output, error_output = self.capture_run(
            self.write_arguments(self.input_path, "--overwrite")
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(output, "")
        self.assertIn("different files", error_output)
        self.assertNotIn("Traceback", error_output)
        self.assertEqual(self.input_path.read_bytes(), self.source_bytes)

    def test_json_path_error_has_stable_exit_code_and_mode(self) -> None:
        output_path = self.project_root / "output.bin"

        exit_code, output, error_output = self.capture_run(
            self.write_arguments(output_path, "--json")
        )
        payload = json.loads(output)

        self.assertEqual(exit_code, 2)
        self.assertEqual(error_output, "")
        self.assertEqual(payload["error_type"], "path_policy")
        self.assertFalse(payload["dry_run"])
        self.assertFalse(output_path.exists())

    def test_invalid_pmx_returns_one_without_output(self) -> None:
        self.input_path.write_bytes(b"not a PMX")
        output_path = self.project_root / "output.pmx"

        exit_code, output, error_output = self.capture_run(
            self.write_arguments(output_path)
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(output, "")
        self.assertIn("[ERROR] edit:", error_output)
        self.assertFalse(output_path.exists())

    def test_verification_failure_returns_one_without_output(self) -> None:
        output_path = self.project_root / "output.pmx"
        with patch(
            "mmd_registry.cli.write_pmx_edit",
            side_effect=PmxEditVerificationError("simulated mismatch"),
        ):
            exit_code, output, error_output = self.capture_run(
                self.write_arguments(output_path)
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(output, "")
        self.assertIn("simulated mismatch", error_output)
        self.assertFalse(output_path.exists())

    def test_io_failure_returns_two_without_traceback(self) -> None:
        output_path = self.project_root / "output.pmx"
        with patch(
            "mmd_registry.cli.write_pmx_edit",
            side_effect=OSError("simulated write failure"),
        ):
            exit_code, output, error_output = self.capture_run(
                self.write_arguments(output_path)
            )

        self.assertEqual(exit_code, 2)
        self.assertEqual(output, "")
        self.assertIn("File operation failed", error_output)
        self.assertNotIn("Traceback", error_output)

    def test_unexpected_failure_returns_three_without_traceback(self) -> None:
        output_path = self.project_root / "output.pmx"
        with patch(
            "mmd_registry.cli.write_pmx_edit",
            side_effect=RuntimeError("simulated internal failure"),
        ):
            exit_code, output, error_output = self.capture_run(
                self.write_arguments(output_path)
            )

        self.assertEqual(exit_code, 3)
        self.assertEqual(output, "")
        self.assertIn("Internal edit failure", error_output)
        self.assertNotIn("Traceback", error_output)


if __name__ == "__main__":
    unittest.main()
