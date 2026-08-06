"""Tests for safe PMX texture-section scanning."""

from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path

from mmd_registry.model_scanning import (
    MAX_PMX_TEXTURE_COUNT,
    scan_pmx_structure,
)
from tests.mmd_fixtures import (
    build_pmx_structure,
)


class PmxTextureScanningTests(unittest.TestCase):
    """Tests for bounded extraction of raw PMX texture paths."""

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
        """Write and return one generated PMX fixture."""

        fixture_path = self.project_root / file_name
        fixture_path.write_bytes(data)
        return fixture_path

    def test_scans_zero_texture_section(self) -> None:
        fixture_data = build_pmx_structure(
            texture_paths=(),
        )
        fixture = self.write_fixture(
            "no_textures.pmx",
            fixture_data,
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.texture_count, 0)
        self.assertEqual(result.texture_paths, [])
        self.assertEqual(
            result.bytes_consumed,
            len(fixture_data),
        )

    def test_preserves_raw_utf8_texture_paths(self) -> None:
        texture_paths = (
            "textures/body.png",
            r"toon\face.bmp",
            "",
            "../shared/sphere.spa",
        )
        fixture_data = build_pmx_structure(
            texture_paths=texture_paths,
        )
        fixture = self.write_fixture(
            "utf8_textures.pmx",
            fixture_data,
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.texture_count, 4)
        self.assertEqual(
            result.texture_paths,
            list(texture_paths),
        )
        self.assertEqual(
            result.bytes_consumed,
            len(fixture_data),
        )

    def test_scans_utf16_texture_paths(self) -> None:
        texture_paths = (
            "テクスチャ/体.png",
            "toon/顔.bmp",
        )
        fixture = self.write_fixture(
            "utf16_textures.pmx",
            build_pmx_structure(
                encoding_flag=0,
                texture_paths=texture_paths,
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(
            result.encoding,
            "utf-16-le",
        )
        self.assertEqual(
            result.texture_paths,
            list(texture_paths),
        )

    def test_preserves_duplicate_texture_references(self) -> None:
        fixture = self.write_fixture(
            "duplicate_textures.pmx",
            build_pmx_structure(
                texture_paths=(
                    "body.png",
                    "body.png",
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.texture_count, 2)
        self.assertEqual(
            result.texture_paths,
            ["body.png", "body.png"],
        )

    def test_rejects_negative_texture_count(self) -> None:
        fixture_data = build_pmx_structure(
            deform_types=(),
            surface_indices=(),
            texture_paths=(),
            texture_count_override=-1,
            materials=(),
        )
        fixture = self.write_fixture(
            "negative_texture_count.pmx",
            fixture_data,
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "texture count" in error and "cannot be negative" in error
                for error in result.errors
            )
        )

    def test_rejects_texture_count_over_safety_limit(
        self,
    ) -> None:
        fixture = self.write_fixture(
            "oversized_texture_count.pmx",
            build_pmx_structure(
                texture_paths=(),
                texture_count_override=(MAX_PMX_TEXTURE_COUNT + 1),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "texture count" in error and "exceeds the safety limit" in error
                for error in result.errors
            )
        )

    def test_rejects_impossible_texture_count(self) -> None:
        fixture = self.write_fixture(
            "impossible_texture_count.pmx",
            build_pmx_structure(
                texture_paths=(),
                texture_count_override=100,
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "texture count" in error and "requires at least" in error
                for error in result.errors
            )
        )

    def test_rejects_truncated_texture_path(self) -> None:
        fixture_data = build_pmx_structure(
            deform_types=(),
            surface_indices=(),
            texture_paths=("textures/body.png",),
            materials=(),
        )
        fixture = self.write_fixture(
            "truncated_texture.pmx",
            fixture_data[:-21],
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "textures[0]" in error
                and "texture path" in error
                and "bytes remain" in error
                for error in result.errors
            )
        )

    def test_rejects_invalid_utf8_texture_path(self) -> None:
        fixture_data = build_pmx_structure(
            deform_types=(),
            surface_indices=(),
            texture_paths=(),
            materials=(),
        )
        fixture_data = b"".join(
            [
                fixture_data[:-24],
                struct.pack("<i", 1),
                struct.pack("<i", 1),
                b"\xff",
                struct.pack("<i", 0),
                struct.pack("<i", 0),
                struct.pack("<i", 0),
                struct.pack("<i", 0),
                struct.pack("<i", 0),
            ]
        )
        fixture = self.write_fixture(
            "invalid_utf8_texture.pmx",
            fixture_data,
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "textures[0]" in error and "invalid utf-8 data" in error
                for error in result.errors
            )
        )

    def test_texture_result_is_json_serializable(self) -> None:
        fixture = self.write_fixture(
            "texture_json.pmx",
            build_pmx_structure(
                texture_paths=(
                    "body.png",
                    "toon.bmp",
                ),
            ),
        )

        result = scan_pmx_structure(fixture)
        payload = result.to_dict()
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
        )

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(
            payload["texture_count"],
            2,
        )
        self.assertEqual(
            payload["texture_paths"],
            ["body.png", "toon.bmp"],
        )
        self.assertIn(
            '"texture_count": 2',
            serialized,
        )


if __name__ == "__main__":
    unittest.main()
