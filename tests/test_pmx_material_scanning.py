"""Tests for safe PMX material-section scanning."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from mmd_registry.model_scanning import (
    MAX_PMX_MATERIAL_COUNT,
    scan_pmx_structure,
)
from tests.mmd_fixtures import (
    build_pmx_material,
    build_pmx_structure,
)


class PmxMaterialScanningTests(unittest.TestCase):
    """Tests for bounded PMX material metadata extraction."""

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

    def test_scans_zero_material_section(self) -> None:
        fixture_data = build_pmx_structure(
            deform_types=(),
            surface_indices=(),
            materials=(),
        )
        fixture = self.write_fixture(
            "no_materials.pmx",
            fixture_data,
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.material_count, 0)
        self.assertEqual(result.materials, [])
        self.assertEqual(
            result.bytes_consumed,
            len(fixture_data),
        )

    def test_scans_material_metadata_and_surface_coverage(
        self,
    ) -> None:
        texture_paths = (
            "body.png",
            "sphere.spa",
            "toon.bmp",
        )
        materials = (
            build_pmx_material(
                local_name="Body",
                universal_name="Body EN",
                texture_index=0,
                sphere_texture_index=1,
                sphere_mode=2,
                toon_reference_mode=0,
                toon_reference_index=2,
                memo="Primary body material",
                surface_index_count=3,
            ),
            build_pmx_material(
                local_name="Face",
                universal_name="Face EN",
                texture_index=-1,
                sphere_texture_index=-1,
                sphere_mode=0,
                toon_reference_mode=1,
                toon_reference_index=7,
                memo="Face material",
                surface_index_count=3,
            ),
        )
        fixture_data = build_pmx_structure(
            deform_types=(0, 0, 0, 0),
            surface_indices=(
                0,
                1,
                2,
                1,
                2,
                3,
            ),
            texture_paths=texture_paths,
            materials=materials,
        )
        fixture = self.write_fixture(
            "materials.pmx",
            fixture_data,
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.material_count, 2)
        self.assertEqual(len(result.materials), 2)

        body = result.materials[0]
        self.assertEqual(body.local_name, "Body")
        self.assertEqual(body.universal_name, "Body EN")
        self.assertEqual(body.texture_index, 0)
        self.assertEqual(body.sphere_texture_index, 1)
        self.assertEqual(body.sphere_mode, 2)
        self.assertEqual(
            body.toon_reference_mode,
            "texture",
        )
        self.assertEqual(body.toon_reference_index, 2)
        self.assertEqual(
            body.memo,
            "Primary body material",
        )
        self.assertEqual(body.surface_index_count, 3)

        face = result.materials[1]
        self.assertEqual(face.texture_index, -1)
        self.assertEqual(face.sphere_texture_index, -1)
        self.assertEqual(
            face.toon_reference_mode,
            "shared",
        )
        self.assertEqual(face.toon_reference_index, 7)
        self.assertEqual(face.surface_index_count, 3)
        self.assertEqual(
            result.bytes_consumed,
            len(fixture_data),
        )

    def test_scans_utf16_material_text(self) -> None:
        material = build_pmx_material(
            local_name="材質",
            universal_name="Material",
            memo="説明",
            surface_index_count=3,
            encoding_flag=0,
        )
        fixture = self.write_fixture(
            "utf16_material.pmx",
            build_pmx_structure(
                encoding_flag=0,
                materials=(material,),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(
            result.materials[0].local_name,
            "材質",
        )
        self.assertEqual(
            result.materials[0].memo,
            "説明",
        )

    def test_accepts_texture_index_sentinel(self) -> None:
        fixture = self.write_fixture(
            "sentinel_indices.pmx",
            build_pmx_structure(
                materials=(
                    build_pmx_material(
                        texture_index=-1,
                        sphere_texture_index=-1,
                        toon_reference_mode=0,
                        toon_reference_index=-1,
                        surface_index_count=3,
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(
            result.materials[0].toon_reference_index,
            -1,
        )

    def test_rejects_out_of_range_texture_index(self) -> None:
        fixture = self.write_fixture(
            "texture_index.pmx",
            build_pmx_structure(
                texture_paths=("body.png",),
                materials=(
                    build_pmx_material(
                        texture_index=1,
                        surface_index_count=3,
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "materials[0]" in error
                and "material texture index" in error
                and "texture count 1" in error
                for error in result.errors
            )
        )

    def test_rejects_out_of_range_sphere_texture_index(
        self,
    ) -> None:
        fixture = self.write_fixture(
            "sphere_texture_index.pmx",
            build_pmx_structure(
                texture_paths=("body.png",),
                materials=(
                    build_pmx_material(
                        sphere_texture_index=2,
                        surface_index_count=3,
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any("material sphere texture index" in error for error in result.errors)
        )

    def test_rejects_invalid_sphere_mode(self) -> None:
        fixture = self.write_fixture(
            "sphere_mode.pmx",
            build_pmx_structure(
                materials=(
                    build_pmx_material(
                        sphere_mode=4,
                        surface_index_count=3,
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any("invalid sphere mode 4" in error for error in result.errors)
        )

    def test_rejects_invalid_toon_reference_mode(self) -> None:
        fixture = self.write_fixture(
            "toon_mode.pmx",
            build_pmx_structure(
                materials=(
                    build_pmx_material(
                        toon_reference_mode=2,
                        surface_index_count=3,
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any("invalid toon reference mode 2" in error for error in result.errors)
        )

    def test_rejects_invalid_shared_toon_index(self) -> None:
        fixture = self.write_fixture(
            "shared_toon.pmx",
            build_pmx_structure(
                materials=(
                    build_pmx_material(
                        toon_reference_mode=1,
                        toon_reference_index=10,
                        surface_index_count=3,
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any("invalid shared toon index 10" in error for error in result.errors)
        )

    def test_rejects_out_of_range_toon_texture_index(
        self,
    ) -> None:
        fixture = self.write_fixture(
            "toon_texture.pmx",
            build_pmx_structure(
                texture_paths=("toon.bmp",),
                materials=(
                    build_pmx_material(
                        toon_reference_mode=0,
                        toon_reference_index=2,
                        surface_index_count=3,
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any("material toon texture index" in error for error in result.errors)
        )

    def test_rejects_non_triangle_material_surface_count(
        self,
    ) -> None:
        fixture = self.write_fixture(
            "material_surface_count.pmx",
            build_pmx_structure(
                surface_indices=(),
                materials=(
                    build_pmx_material(
                        surface_index_count=1,
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "materials[0]" in error and "must be divisible by 3" in error
                for error in result.errors
            )
        )

    def test_rejects_material_surface_total_mismatch(
        self,
    ) -> None:
        fixture = self.write_fixture(
            "material_surface_total.pmx",
            build_pmx_structure(
                materials=(
                    build_pmx_material(
                        surface_index_count=0,
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "materials cover 0 surface indices" in error
                and "model declares 3" in error
                for error in result.errors
            )
        )

    def test_rejects_material_surface_total_overflow(
        self,
    ) -> None:
        fixture = self.write_fixture(
            "material_surface_overflow.pmx",
            build_pmx_structure(
                materials=(
                    build_pmx_material(
                        surface_index_count=6,
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "cumulative material surface index count 6" in error
                for error in result.errors
            )
        )

    def test_rejects_material_count_over_safety_limit(
        self,
    ) -> None:
        fixture = self.write_fixture(
            "material_count.pmx",
            build_pmx_structure(
                deform_types=(),
                surface_indices=(),
                materials=(),
                material_count_override=(MAX_PMX_MATERIAL_COUNT + 1),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "material count" in error and "exceeds the safety limit" in error
                for error in result.errors
            )
        )

    def test_rejects_truncated_material_record(self) -> None:
        fixture_data = build_pmx_structure(
            materials=(
                build_pmx_material(
                    memo="material memo",
                    surface_index_count=3,
                ),
            ),
        )
        fixture = self.write_fixture(
            "truncated_material.pmx",
            fixture_data[:-21],
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "materials[0]" in error and "material surface index count" in error
                for error in result.errors
            )
        )

    def test_material_result_is_json_serializable(self) -> None:
        fixture = self.write_fixture(
            "material_json.pmx",
            build_pmx_structure(
                materials=(
                    build_pmx_material(
                        local_name="Body",
                        surface_index_count=3,
                    ),
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
        self.assertEqual(payload["material_count"], 1)
        self.assertEqual(
            payload["materials"][0]["local_name"],
            "Body",
        )
        self.assertEqual(
            payload["materials"][0]["toon_reference_mode"],
            "shared",
        )
        self.assertIn(
            '"material_count": 1',
            serialized,
        )


if __name__ == "__main__":
    unittest.main()
