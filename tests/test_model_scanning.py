"""Tests for safe PMX structural metadata scanning."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from mmd_registry.model_scanning import scan_pmx_header
from tests.mmd_fixtures import build_pmx_model_info


class PmxHeaderScanningTests(unittest.TestCase):
    """Tests for PMX globals, index sizes, and model information."""

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

    def test_scans_valid_utf8_model_information(self) -> None:
        fixture_data = build_pmx_model_info(
            local_name="Local Name",
            universal_name="Universal Name",
            local_comments="Local comments",
            universal_comments="Universal comments",
            version=2.1,
            additional_uv_count=2,
            vertex_index_size=1,
            texture_index_size=2,
            material_index_size=4,
            bone_index_size=1,
            morph_index_size=2,
            rigid_body_index_size=4,
        )
        fixture = self.write_fixture(
            "model.pmx",
            fixture_data,
        )

        result = scan_pmx_header(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.detected_format, "pmx")
        self.assertEqual(result.magic, "PMX ")
        self.assertEqual(result.version, 2.1)
        self.assertEqual(result.encoding, "utf-8")
        self.assertEqual(result.global_count, 8)
        self.assertEqual(result.additional_uv_count, 2)
        self.assertEqual(result.file_size, len(fixture_data))
        self.assertEqual(
            result.bytes_consumed,
            len(fixture_data),
        )

        self.assertIsNotNone(result.index_sizes)
        self.assertEqual(result.index_sizes.vertex, 1)
        self.assertEqual(result.index_sizes.texture, 2)
        self.assertEqual(result.index_sizes.material, 4)
        self.assertEqual(result.index_sizes.bone, 1)
        self.assertEqual(result.index_sizes.morph, 2)
        self.assertEqual(result.index_sizes.rigid_body, 4)

        self.assertIsNotNone(result.model_info)
        self.assertEqual(
            result.model_info.local_name,
            "Local Name",
        )
        self.assertEqual(
            result.model_info.universal_name,
            "Universal Name",
        )
        self.assertEqual(
            result.model_info.local_comments,
            "Local comments",
        )
        self.assertEqual(
            result.model_info.universal_comments,
            "Universal comments",
        )

    def test_scans_valid_utf16_model_information(self) -> None:
        fixture_data = build_pmx_model_info(
            local_name="ローカル",
            universal_name="Universal",
            local_comments="コメント",
            universal_comments="Comments",
            encoding_flag=0,
        )
        fixture = self.write_fixture(
            "utf16.pmx",
            fixture_data,
        )

        result = scan_pmx_header(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.encoding, "utf-16-le")
        self.assertIsNotNone(result.model_info)
        self.assertEqual(
            result.model_info.local_name,
            "ローカル",
        )
        self.assertEqual(
            result.model_info.local_comments,
            "コメント",
        )

    def test_accepts_all_supported_index_sizes(self) -> None:
        for index_size in (1, 2, 4):
            with self.subTest(index_size=index_size):
                fixture = self.write_fixture(
                    f"index_{index_size}.pmx",
                    build_pmx_model_info(
                        vertex_index_size=index_size,
                        texture_index_size=index_size,
                        material_index_size=index_size,
                        bone_index_size=index_size,
                        morph_index_size=index_size,
                        rigid_body_index_size=index_size,
                    ),
                )

                result = scan_pmx_header(fixture)

                self.assertEqual(result.status, "ok")
                self.assertIsNotNone(result.index_sizes)
                self.assertEqual(
                    result.index_sizes.vertex,
                    index_size,
                )
                self.assertEqual(
                    result.index_sizes.rigid_body,
                    index_size,
                )

    def test_extra_global_bytes_are_preserved_as_warning(
        self,
    ) -> None:
        fixture = self.write_fixture(
            "extra_globals.pmx",
            build_pmx_model_info(
                extra_globals=b"\xaa\xbb",
            ),
        )

        result = scan_pmx_header(fixture)

        self.assertEqual(result.status, "warning")
        self.assertEqual(result.global_count, 10)
        self.assertIn(
            ("PMX header contains 2 unrecognized extra global-setting bytes."),
            result.warnings,
        )

    def test_rejects_too_small_global_count(self) -> None:
        fixture = self.write_fixture(
            "small_globals.pmx",
            build_pmx_model_info(
                globals_override=bytes([1, 0, 1, 1, 1, 1, 1]),
            ),
        )

        result = scan_pmx_header(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any("smaller than the required minimum" in error for error in result.errors)
        )

    def test_rejects_invalid_encoding_flag(self) -> None:
        fixture = self.write_fixture(
            "encoding.pmx",
            build_pmx_model_info(
                encoding_flag=9,
            ),
        )

        result = scan_pmx_header(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any("invalid PMX text-encoding flag: 9" in error for error in result.errors)
        )

    def test_rejects_invalid_additional_uv_count(
        self,
    ) -> None:
        fixture = self.write_fixture(
            "additional_uv.pmx",
            build_pmx_model_info(
                additional_uv_count=5,
            ),
        )

        result = scan_pmx_header(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any("expected a value from 0 through 4" in error for error in result.errors)
        )

    def test_rejects_invalid_index_size(self) -> None:
        fixture = self.write_fixture(
            "index_size.pmx",
            build_pmx_model_info(
                vertex_index_size=3,
            ),
        )

        result = scan_pmx_header(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(any("invalid index size 3" in error for error in result.errors))

    def test_rejects_truncated_model_information(
        self,
    ) -> None:
        fixture_data = build_pmx_model_info(
            universal_comments="Final field",
        )
        fixture = self.write_fixture(
            "truncated.pmx",
            fixture_data[:-1],
        )

        result = scan_pmx_header(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any("universal model comments" in error for error in result.errors)
        )
        self.assertTrue(any("bytes remain" in error for error in result.errors))

    def test_rejects_unsupported_version(self) -> None:
        fixture = self.write_fixture(
            "version.pmx",
            build_pmx_model_info(
                version=3.0,
            ),
        )

        result = scan_pmx_header(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any("unsupported PMX version: 3" in error for error in result.errors)
        )

    def test_result_is_json_serializable(self) -> None:
        fixture = self.write_fixture(
            "json.pmx",
            build_pmx_model_info(),
        )

        result = scan_pmx_header(fixture)
        payload = result.to_dict()
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
        )

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(
            payload["index_sizes"]["vertex"],
            1,
        )
        self.assertEqual(
            payload["model_info"]["local_name"],
            "Test PMX Model",
        )
        self.assertIn(
            '"detected_format": "pmx"',
            serialized,
        )


if __name__ == "__main__":
    unittest.main()
