"""Negative-path safety regression tests for verified PMX edit output."""

from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import mmd_registry.pmx.editing.output as edit_output
from mmd_registry.binary_reader import BinaryParseError
from mmd_registry.pmx import load_pmx
from mmd_registry.pmx.editing import (
    PmxEditPlanError,
    PmxEditVerificationError,
    parse_pmx_edit_plan_json,
    write_pmx_edit,
)
from tests.mmd_fixtures import build_pmx_bone, build_pmx_structure


class PmxEditNegativeSafetyTests(unittest.TestCase):
    """Prove expected failures never expose partial or destructive output."""

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_directory.name)
        self.input_path = self.project_root / "source.pmx"
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
                            "local_name": "negative safety edit",
                        }
                    ],
                }
            )
        )

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def temporary_outputs(self, output_path: Path) -> list[Path]:
        return list(output_path.parent.glob(f".{output_path.name}.*.tmp"))

    def assert_source_unchanged(self) -> None:
        self.assertEqual(self.input_path.read_bytes(), self.source_bytes)

    def test_hash_mismatch_preserves_existing_overwrite_target(self) -> None:
        output_path = self.project_root / "existing.pmx"
        output_path.write_bytes(b"existing output")
        mismatch_plan = parse_pmx_edit_plan_json(
            json.dumps(
                {
                    "schema_version": 1,
                    "expected_source_sha256": "0" * 64,
                    "operations": [
                        {
                            "op": "set_model_info",
                            "local_name": "must not be written",
                        }
                    ],
                }
            )
        )

        with self.assertRaisesRegex(
            PmxEditPlanError,
            "source SHA-256 mismatch",
        ):
            write_pmx_edit(
                self.input_path,
                output_path,
                mismatch_plan,
                overwrite=True,
            )

        self.assert_source_unchanged()
        self.assertEqual(output_path.read_bytes(), b"existing output")
        self.assertEqual(self.temporary_outputs(output_path), [])

    def test_serialization_failure_creates_no_output_or_temp(self) -> None:
        output_path = self.project_root / "serialize-failure.pmx"

        with patch(
            "mmd_registry.pmx.editing.output.serialize_pmx",
            side_effect=RuntimeError("simulated serialization failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "serialization failure"):
                write_pmx_edit(self.input_path, output_path, self.plan)

        self.assert_source_unchanged()
        self.assertFalse(output_path.exists())
        self.assertEqual(self.temporary_outputs(output_path), [])

    def test_reparse_failure_creates_no_output_or_temp(self) -> None:
        output_path = self.project_root / "reparse-failure.pmx"
        parse_error = BinaryParseError(
            format_name="PMX",
            section="test",
            record_index=None,
            offset=0,
            operation="reparsing edited output",
            reason="simulated reparse failure",
        )

        with patch(
            "mmd_registry.pmx.editing.output.load_pmx",
            side_effect=parse_error,
        ):
            with self.assertRaisesRegex(BinaryParseError, "reparse failure"):
                write_pmx_edit(self.input_path, output_path, self.plan)

        self.assert_source_unchanged()
        self.assertFalse(output_path.exists())
        self.assertEqual(self.temporary_outputs(output_path), [])

    def test_semantic_failure_preserves_existing_overwrite_target(self) -> None:
        output_path = self.project_root / "semantic-existing.pmx"
        output_path.write_bytes(b"existing output")
        source_document = load_pmx(io.BytesIO(self.source_bytes))

        with patch(
            "mmd_registry.pmx.editing.output.load_pmx",
            return_value=source_document,
        ):
            with self.assertRaisesRegex(
                PmxEditVerificationError,
                "intended edited document",
            ):
                write_pmx_edit(
                    self.input_path,
                    output_path,
                    self.plan,
                    overwrite=True,
                )

        self.assert_source_unchanged()
        self.assertEqual(output_path.read_bytes(), b"existing output")
        self.assertEqual(self.temporary_outputs(output_path), [])

    def test_temporary_payload_hash_mismatch_is_cleaned(self) -> None:
        output_path = self.project_root / "temp-hash.pmx"
        original_hash_file = edit_output._hash_file

        def mismatching_temp_hash(path: Path) -> str:
            if path.name.startswith(f".{output_path.name}.") and path.suffix == ".tmp":
                return "0" * 64
            return original_hash_file(path)

        with patch(
            "mmd_registry.pmx.editing.output._hash_file",
            side_effect=mismatching_temp_hash,
        ):
            with self.assertRaisesRegex(
                PmxEditVerificationError,
                "temporary PMX",
            ):
                write_pmx_edit(self.input_path, output_path, self.plan)

        self.assert_source_unchanged()
        self.assertFalse(output_path.exists())
        self.assertEqual(self.temporary_outputs(output_path), [])

    def test_fsync_failure_is_cleaned_without_partial_output(self) -> None:
        output_path = self.project_root / "fsync-failure.pmx"

        with patch(
            "mmd_registry.pmx.editing.output.os.fsync",
            side_effect=OSError("simulated fsync failure"),
        ):
            with self.assertRaisesRegex(OSError, "fsync failure"):
                write_pmx_edit(self.input_path, output_path, self.plan)

        self.assert_source_unchanged()
        self.assertFalse(output_path.exists())
        self.assertEqual(self.temporary_outputs(output_path), [])

    def test_same_bytes_source_replacement_is_rejected_by_identity(self) -> None:
        output_path = self.project_root / "identity-replacement.pmx"
        original_serialize = edit_output.serialize_pmx
        original_copy = self.project_root / "original-source.pmx"

        def serialize_then_replace_source(document: object) -> bytes:
            data = original_serialize(document)  # type: ignore[arg-type]
            self.input_path.replace(original_copy)
            self.input_path.write_bytes(self.source_bytes)
            return data

        with patch(
            "mmd_registry.pmx.editing.output.serialize_pmx",
            side_effect=serialize_then_replace_source,
        ):
            with self.assertRaisesRegex(
                PmxEditVerificationError,
                "identity changed before output commit",
            ):
                write_pmx_edit(self.input_path, output_path, self.plan)

        self.assertEqual(
            hashlib.sha256(self.input_path.read_bytes()).hexdigest(),
            hashlib.sha256(self.source_bytes).hexdigest(),
        )
        self.assertFalse(output_path.exists())
        self.assertEqual(self.temporary_outputs(output_path), [])

    def test_source_read_failure_preserves_existing_output(self) -> None:
        output_path = self.project_root / "read-failure-existing.pmx"
        output_path.write_bytes(b"existing output")

        with patch.object(
            Path,
            "read_bytes",
            side_effect=PermissionError("simulated source read failure"),
        ):
            with self.assertRaisesRegex(PermissionError, "source read failure"):
                write_pmx_edit(
                    self.input_path,
                    output_path,
                    self.plan,
                    overwrite=True,
                )

        self.assertEqual(output_path.read_bytes(), b"existing output")
        self.assertEqual(self.input_path.read_bytes(), self.source_bytes)
        self.assertEqual(self.temporary_outputs(output_path), [])


if __name__ == "__main__":
    unittest.main()
