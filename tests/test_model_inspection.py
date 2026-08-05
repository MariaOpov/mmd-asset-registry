"""Tests for safe PMX and PMD header inspection."""

from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from mmd_registry.model_inspection import (
    MAX_MODEL_NAME_BYTES,
    inspect_model_header,
)
from tests.mmd_fixtures import (
    build_minimal_pmd_header,
    build_minimal_pmx_header,
)


class ModelInspectionTests(unittest.TestCase):
    """Tests for bounded MMD model-header inspection."""

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_directory.name)

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def write_fixture(
        self,
        file_name: str,
        data: bytes,
    ) -> Path:
        """Write and return one generated binary fixture."""

        fixture_path = self.project_root / file_name
        fixture_path.write_bytes(data)
        return fixture_path

    def test_valid_minimal_pmx_utf8_header(self) -> None:
        fixture = self.write_fixture(
            "model.pmx",
            build_minimal_pmx_header("Fixture PMX"),
        )

        result = inspect_model_header(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.detected_format, "pmx")
        self.assertEqual(result.magic, "PMX ")
        self.assertEqual(result.version, 2.0)
        self.assertEqual(result.encoding, "utf-8")
        self.assertEqual(result.model_name, "Fixture PMX")

    def test_valid_minimal_pmx_utf16_header(self) -> None:
        fixture = self.write_fixture(
            "model.pmx",
            build_minimal_pmx_header(
                "PMX UTF16",
                encoding_flag=0,
                version=2.1,
            ),
        )

        result = inspect_model_header(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.version, 2.1)
        self.assertEqual(result.encoding, "utf-16-le")
        self.assertEqual(result.model_name, "PMX UTF16")

    def test_valid_minimal_pmd_header(self) -> None:
        fixture = self.write_fixture(
            "model.pmd",
            build_minimal_pmd_header("Fixture PMD"),
        )

        result = inspect_model_header(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.detected_format, "pmd")
        self.assertEqual(result.magic, "Pmd")
        self.assertEqual(result.version, 1.0)
        self.assertEqual(result.encoding, "cp932")
        self.assertEqual(result.model_name, "Fixture PMD")

    def test_too_short_file_is_error(self) -> None:
        fixture = self.write_fixture("short.pmx", b"PM")

        result = inspect_model_header(fixture)

        self.assertEqual(result.status, "error")
        self.assertIn(
            "File is too short to contain an MMD model signature.",
            result.errors,
        )

    def test_invalid_magic_is_error(self) -> None:
        fixture = self.write_fixture(
            "invalid.pmx",
            b"NOPE" + b"\x00" * 32,
        )

        result = inspect_model_header(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any("Invalid MMD model magic/signature" in error for error in result.errors)
        )

    def test_truncated_pmx_header_is_error(self) -> None:
        fixture = self.write_fixture(
            "truncated.pmx",
            b"PMX " + b"\x00\x00",
        )

        result = inspect_model_header(fixture)

        self.assertEqual(result.status, "error")
        self.assertEqual(result.detected_format, "pmx")
        self.assertTrue(any("Truncated file" in error for error in result.errors))

    def test_unsupported_pmx_version_is_error(self) -> None:
        fixture = self.write_fixture(
            "unsupported.pmx",
            build_minimal_pmx_header(version=3.0),
        )

        result = inspect_model_header(fixture)

        self.assertEqual(result.status, "error")
        self.assertIn(
            "Unsupported PMX version: 3.",
            result.errors,
        )

    def test_unsupported_pmd_version_is_error(self) -> None:
        fixture = self.write_fixture(
            "unsupported.pmd",
            build_minimal_pmd_header(version=2.0),
        )

        result = inspect_model_header(fixture)

        self.assertEqual(result.status, "error")
        self.assertIn(
            "Unsupported PMD version: 2.",
            result.errors,
        )

    def test_invalid_pmx_encoding_flag_is_error(self) -> None:
        fixture = self.write_fixture(
            "encoding.pmx",
            build_minimal_pmx_header(encoding_flag=9),
        )

        result = inspect_model_header(fixture)

        self.assertEqual(result.status, "error")
        self.assertIn(
            "Invalid PMX text-encoding flag: 9.",
            result.errors,
        )

    def test_oversized_pmx_model_name_is_rejected_before_read(self) -> None:
        globals_data = bytes([1, 0, 1, 1, 1, 1, 1, 1])
        fixture_data = b"".join(
            [
                b"PMX ",
                struct.pack("<f", 2.0),
                struct.pack("<B", len(globals_data)),
                globals_data,
                struct.pack("<i", MAX_MODEL_NAME_BYTES + 1),
            ]
        )
        fixture = self.write_fixture("oversized.pmx", fixture_data)

        result = inspect_model_header(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any("exceeds the safety limit" in error for error in result.errors)
        )

    def test_extension_content_mismatch_is_error(self) -> None:
        fixture = self.write_fixture(
            "wrong_extension.pmd",
            build_minimal_pmx_header(),
        )

        result = inspect_model_header(fixture)

        self.assertEqual(result.detected_format, "pmx")
        self.assertEqual(result.status, "error")
        self.assertIn(
            "File extension '.pmd' does not match detected PMX content.",
            result.errors,
        )


if __name__ == "__main__":
    unittest.main()
