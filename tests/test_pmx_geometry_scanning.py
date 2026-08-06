"""Tests for safe PMX vertex and surface-index scanning."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from mmd_registry.model_scanning import (
    scan_pmx_structure,
)
from tests.mmd_fixtures import (
    build_pmx_structure,
)


class PmxGeometryScanningTests(unittest.TestCase):
    """Tests for bounded PMX geometry-section scanning."""

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

    def test_scans_zero_geometry_sections(self) -> None:
        fixture_data = build_pmx_structure(
            deform_types=(),
            surface_indices=(),
        )
        fixture = self.write_fixture(
            "empty_geometry.pmx",
            fixture_data,
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.vertex_count, 0)
        self.assertEqual(
            result.surface_index_count,
            0,
        )
        self.assertEqual(result.triangle_count, 0)
        self.assertEqual(
            result.bytes_consumed,
            len(fixture_data),
        )

    def test_scans_all_supported_deform_types(self) -> None:
        fixture_data = build_pmx_structure(
            version=2.1,
            deform_types=(0, 1, 2, 3, 4),
            surface_indices=(
                0,
                1,
                2,
                2,
                3,
                4,
            ),
            additional_uv_count=2,
            bone_index_size=2,
            vertex_index_size=2,
        )
        fixture = self.write_fixture(
            "deform_types.pmx",
            fixture_data,
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.vertex_count, 5)
        self.assertEqual(
            result.surface_index_count,
            6,
        )
        self.assertEqual(result.triangle_count, 2)
        self.assertEqual(
            result.bytes_consumed,
            len(fixture_data),
        )

    def test_rejects_invalid_vertex_deform_type(self) -> None:
        fixture = self.write_fixture(
            "invalid_deform.pmx",
            build_pmx_structure(
                deform_types=(9,),
                surface_indices=(),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any("invalid PMX vertex deform type: 9" in error for error in result.errors)
        )
        self.assertTrue(any("vertices[0]" in error for error in result.errors))

    def test_rejects_qdef_in_pmx_2_0(self) -> None:
        fixture = self.write_fixture(
            "qdef_20.pmx",
            build_pmx_structure(
                version=2.0,
                deform_types=(4,),
                surface_indices=(),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any("QDEF deform type requires PMX 2.1" in error for error in result.errors)
        )

    def test_rejects_impossible_vertex_count(self) -> None:
        fixture = self.write_fixture(
            "impossible_count.pmx",
            build_pmx_structure(
                deform_types=(),
                surface_indices=(),
                vertex_count_override=100,
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "vertex count" in error and "requires at least" in error
                for error in result.errors
            )
        )

    def test_rejects_non_triangle_surface_count(self) -> None:
        fixture = self.write_fixture(
            "surface_count.pmx",
            build_pmx_structure(
                deform_types=(0,),
                surface_indices=(0,),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any("must be divisible by 3" in error for error in result.errors)
        )

    def test_rejects_truncated_vertex_record(self) -> None:
        fixture_data = build_pmx_structure(
            deform_types=(2,),
            surface_indices=(),
        )

        # Remove bone, material, texture, and surface count fields,
        # plus one byte from the vertex edge-scale value.
        fixture = self.write_fixture(
            "truncated_vertex.pmx",
            fixture_data[:-17],
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(any("vertices[0]" in error for error in result.errors))
        self.assertTrue(any("vertex edge scale" in error for error in result.errors))

    def test_geometry_result_is_json_serializable(self) -> None:
        fixture = self.write_fixture(
            "geometry_json.pmx",
            build_pmx_structure(),
        )

        result = scan_pmx_structure(fixture)
        payload = result.to_dict()

        serialized = json.dumps(
            payload,
            ensure_ascii=False,
        )

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(
            payload["vertex_count"],
            1,
        )
        self.assertEqual(
            payload["surface_index_count"],
            3,
        )
        self.assertEqual(
            payload["triangle_count"],
            1,
        )
        self.assertIn(
            '"triangle_count": 1',
            serialized,
        )


if __name__ == "__main__":
    unittest.main()
