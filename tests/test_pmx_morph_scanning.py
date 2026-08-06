"""Tests for safe PMX morph-section structural scanning."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from mmd_registry.model_scanning import (
    MAX_PMX_MORPH_COUNT,
    MAX_PMX_MORPH_OFFSET_COUNT,
    scan_pmx_structure,
)
from tests.mmd_fixtures import (
    build_pmx_bone,
    build_pmx_bone_morph_offset,
    build_pmx_flip_morph_offset,
    build_pmx_group_morph_offset,
    build_pmx_impulse_morph_offset,
    build_pmx_material_morph_offset,
    build_pmx_morph,
    build_pmx_rigid_body,
    build_pmx_structure,
    build_pmx_uv_morph_offset,
    build_pmx_vertex_morph_offset,
)


class PmxMorphScanningTests(unittest.TestCase):
    """Tests for bounded PMX morph metadata extraction."""

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_directory.name)

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def write_fixture(self, file_name: str, data: bytes) -> Path:
        """Write and return one generated PMX fixture."""

        fixture_path = self.project_root / file_name
        fixture_path.write_bytes(data)
        return fixture_path

    def test_scans_zero_morph_section(self) -> None:
        fixture_data = build_pmx_structure(morphs=())
        fixture = self.write_fixture("no_morphs.pmx", fixture_data)

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.morph_count, 0)
        self.assertEqual(result.morphs, [])
        self.assertEqual(result.bytes_consumed, len(fixture_data))

    def test_scans_group_and_vertex_morphs(self) -> None:
        morphs = (
            build_pmx_morph(
                local_name="Group",
                universal_name="Group",
                panel=0,
                morph_type=0,
                offsets=(
                    build_pmx_group_morph_offset(
                        morph_index=1,
                        weight=0.5,
                    ),
                ),
            ),
            build_pmx_morph(
                local_name="Smile",
                universal_name="Smile",
                panel=3,
                morph_type=1,
                offsets=(
                    build_pmx_vertex_morph_offset(
                        vertex_index=0,
                        translation=(0.1, 0.2, 0.3),
                    ),
                ),
            ),
        )
        fixture_data = build_pmx_structure(morphs=morphs)
        fixture = self.write_fixture("group_vertex.pmx", fixture_data)

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.morph_count, 2)
        self.assertEqual(result.morphs[0].panel_name, "system")
        self.assertEqual(result.morphs[0].morph_type_name, "group")
        self.assertAlmostEqual(result.morphs[0].offsets[0].weight, 0.5)
        self.assertEqual(result.morphs[1].panel_name, "mouth")
        self.assertEqual(result.morphs[1].morph_type_name, "vertex")
        self.assertEqual(result.morphs[1].offsets[0].vertex_index, 0)
        self.assertEqual(result.bytes_consumed, len(fixture_data))

    def test_scans_bone_and_all_uv_morph_types(self) -> None:
        bones = (build_pmx_bone(local_name="Root"),)
        morphs = [
            build_pmx_morph(
                morph_type=2,
                offsets=(build_pmx_bone_morph_offset(bone_index=0),),
            )
        ]
        for morph_type in range(3, 8):
            morphs.append(
                build_pmx_morph(
                    morph_type=morph_type,
                    offsets=(build_pmx_uv_morph_offset(vertex_index=0),),
                )
            )

        fixture = self.write_fixture(
            "bone_uv.pmx",
            build_pmx_structure(
                additional_uv_count=4,
                bones=bones,
                morphs=tuple(morphs),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.morph_count, 6)
        self.assertEqual(result.morphs[0].morph_type_name, "bone")
        self.assertEqual(
            [morph.morph_type_name for morph in result.morphs[1:]],
            [
                "uv",
                "additional_uv_1",
                "additional_uv_2",
                "additional_uv_3",
                "additional_uv_4",
            ],
        )

    def test_scans_material_morph_and_all_material_sentinel(self) -> None:
        fixture = self.write_fixture(
            "material_morph.pmx",
            build_pmx_structure(
                morphs=(
                    build_pmx_morph(
                        morph_type=8,
                        offsets=(
                            build_pmx_material_morph_offset(
                                material_index=-1,
                                operation=0,
                                edge_scale=2.0,
                            ),
                        ),
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        offset = result.morphs[0].offsets[0]
        self.assertEqual(offset.material_index, -1)
        self.assertEqual(offset.operation, "multiply")
        self.assertAlmostEqual(offset.edge_scale, 2.0)

    def test_scans_pmx_2_1_flip_and_impulse_morphs(self) -> None:
        morphs = (
            build_pmx_morph(
                morph_type=9,
                offsets=(
                    build_pmx_flip_morph_offset(
                        morph_index=1,
                        weight=0.75,
                    ),
                ),
            ),
            build_pmx_morph(
                morph_type=10,
                offsets=(
                    build_pmx_impulse_morph_offset(
                        rigid_body_index=0,
                        local_flag=1,
                    ),
                ),
            ),
        )
        fixture = self.write_fixture(
            "pmx21_morphs.pmx",
            build_pmx_structure(
                version=2.1,
                morphs=morphs,
                rigid_bodies=(build_pmx_rigid_body(),),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.morphs[0].morph_type_name, "flip")
        impulse = result.morphs[1].offsets[0]
        self.assertTrue(impulse.local)
        self.assertEqual(impulse.rigid_body_index, 0)
        self.assertEqual(impulse.velocity, (1.0, 2.0, 3.0))

    def test_rejects_pmx_2_1_only_morphs_in_pmx_2_0(self) -> None:
        for morph_type in (9, 10):
            with self.subTest(morph_type=morph_type):
                fixture = self.write_fixture(
                    f"pmx20_type_{morph_type}.pmx",
                    build_pmx_structure(
                        version=2.0,
                        morphs=(build_pmx_morph(morph_type=morph_type),),
                    ),
                )
                result = scan_pmx_structure(fixture)
                self.assertEqual(result.status, "error")
                self.assertTrue(
                    any("requires PMX 2.1" in error for error in result.errors)
                )

    def test_rejects_invalid_panel(self) -> None:
        fixture = self.write_fixture(
            "invalid_panel.pmx",
            build_pmx_structure(
                morphs=(build_pmx_morph(panel=5),),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "morphs[0]" in error and "invalid panel 5" in error
                for error in result.errors
            )
        )

    def test_rejects_invalid_morph_type(self) -> None:
        fixture = self.write_fixture(
            "invalid_type.pmx",
            build_pmx_structure(
                morphs=(build_pmx_morph(morph_type=11),),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any("invalid morph type 11" in error for error in result.errors)
        )

    def test_rejects_unavailable_additional_uv_layer(self) -> None:
        fixture = self.write_fixture(
            "missing_additional_uv.pmx",
            build_pmx_structure(
                additional_uv_count=1,
                morphs=(build_pmx_morph(morph_type=5),),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any("requires additional UV layer 2" in error for error in result.errors)
        )

    def test_rejects_invalid_morph_counts(self) -> None:
        cases = (
            (
                "negative",
                build_pmx_structure(morph_count_override=-1),
                "cannot be negative",
            ),
            (
                "oversized",
                build_pmx_structure(
                    morph_count_override=MAX_PMX_MORPH_COUNT + 1,
                ),
                "exceeds the safety limit",
            ),
            (
                "impossible",
                build_pmx_structure(morph_count_override=1),
                "requires at least",
            ),
        )

        for label, fixture_data, expected in cases:
            with self.subTest(label=label):
                result = scan_pmx_structure(
                    self.write_fixture(f"{label}_count.pmx", fixture_data)
                )
                self.assertEqual(result.status, "error")
                self.assertTrue(
                    any(
                        "morph count" in error and expected in error
                        for error in result.errors
                    )
                )

    def test_rejects_invalid_offset_counts(self) -> None:
        cases = (
            (-1, "cannot be negative"),
            (
                MAX_PMX_MORPH_OFFSET_COUNT + 1,
                "exceeds the safety limit",
            ),
            (1, "requires at least"),
        )

        for count, expected in cases:
            with self.subTest(count=count):
                fixture = self.write_fixture(
                    f"offset_count_{count}.pmx",
                    build_pmx_structure(
                        morphs=(
                            build_pmx_morph(
                                morph_type=1,
                                offset_count_override=count,
                            ),
                        ),
                    ),
                )
                result = scan_pmx_structure(fixture)
                self.assertEqual(result.status, "error")
                self.assertTrue(
                    any(
                        "morph offset count" in error and expected in error
                        for error in result.errors
                    )
                )

    def test_rejects_out_of_range_vertex_index(self) -> None:
        fixture = self.write_fixture(
            "bad_vertex_index.pmx",
            build_pmx_structure(
                morphs=(
                    build_pmx_morph(
                        morph_type=1,
                        offsets=(build_pmx_vertex_morph_offset(vertex_index=1),),
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "morphs[0].offsets[0]" in error and "vertex morph vertex index" in error
                for error in result.errors
            )
        )

    def test_rejects_out_of_range_bone_index(self) -> None:
        fixture = self.write_fixture(
            "bad_bone_index.pmx",
            build_pmx_structure(
                bones=(build_pmx_bone(),),
                morphs=(
                    build_pmx_morph(
                        morph_type=2,
                        offsets=(build_pmx_bone_morph_offset(bone_index=1),),
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any("bone morph bone index" in error for error in result.errors)
        )

    def test_rejects_out_of_range_material_index(self) -> None:
        fixture = self.write_fixture(
            "bad_material_index.pmx",
            build_pmx_structure(
                morphs=(
                    build_pmx_morph(
                        morph_type=8,
                        offsets=(build_pmx_material_morph_offset(material_index=1),),
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any("material morph material index" in error for error in result.errors)
        )

    def test_rejects_out_of_range_group_and_flip_references(self) -> None:
        cases = (
            (
                0,
                build_pmx_group_morph_offset(morph_index=1),
                2.0,
            ),
            (
                9,
                build_pmx_flip_morph_offset(morph_index=1),
                2.1,
            ),
        )

        for morph_type, offset_data, version in cases:
            with self.subTest(morph_type=morph_type):
                fixture = self.write_fixture(
                    f"bad_morph_ref_{morph_type}.pmx",
                    build_pmx_structure(
                        version=version,
                        morphs=(
                            build_pmx_morph(
                                morph_type=morph_type,
                                offsets=(offset_data,),
                            ),
                        ),
                    ),
                )
                result = scan_pmx_structure(fixture)
                self.assertEqual(result.status, "error")
                self.assertTrue(any("morph index" in error for error in result.errors))

    def test_rejects_invalid_material_operation(self) -> None:
        fixture = self.write_fixture(
            "bad_material_operation.pmx",
            build_pmx_structure(
                morphs=(
                    build_pmx_morph(
                        morph_type=8,
                        offsets=(build_pmx_material_morph_offset(operation=2),),
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(any("invalid operation 2" in error for error in result.errors))

    def test_rejects_invalid_impulse_fields(self) -> None:
        cases = (
            (
                "negative_index",
                build_pmx_impulse_morph_offset(rigid_body_index=-1),
                "cannot be negative",
            ),
            (
                "local_flag",
                build_pmx_impulse_morph_offset(local_flag=2),
                "invalid flag 2",
            ),
        )

        for label, offset_data, expected in cases:
            with self.subTest(label=label):
                fixture = self.write_fixture(
                    f"impulse_{label}.pmx",
                    build_pmx_structure(
                        version=2.1,
                        morphs=(
                            build_pmx_morph(
                                morph_type=10,
                                offsets=(offset_data,),
                            ),
                        ),
                    ),
                )
                result = scan_pmx_structure(fixture)
                self.assertEqual(result.status, "error")
                self.assertTrue(any(expected in error for error in result.errors))

    def test_rejects_truncated_morph_offset(self) -> None:
        fixture_data = build_pmx_structure(
            morphs=(
                build_pmx_morph(
                    morph_type=1,
                    offsets=(build_pmx_vertex_morph_offset(),),
                ),
            ),
        )
        fixture = self.write_fixture(
            "truncated_morph.pmx",
            fixture_data[:-9],
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "morphs[0]" in error
                and "morph offset count" in error
                and "requires at least" in error
                for error in result.errors
            )
        )

    def test_scans_utf16_morph_names(self) -> None:
        fixture = self.write_fixture(
            "utf16_morph.pmx",
            build_pmx_structure(
                encoding_flag=0,
                morphs=(
                    build_pmx_morph(
                        local_name="笑顔",
                        universal_name="Smile",
                        encoding_flag=0,
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.morphs[0].local_name, "笑顔")
        self.assertEqual(result.morphs[0].universal_name, "Smile")

    def test_morph_result_is_json_serializable(self) -> None:
        fixture = self.write_fixture(
            "morph_json.pmx",
            build_pmx_structure(
                morphs=(
                    build_pmx_morph(
                        morph_type=1,
                        offsets=(build_pmx_vertex_morph_offset(),),
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)
        payload = result.to_dict()
        serialized = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["morph_count"], 1)
        self.assertEqual(payload["morphs"][0]["offset_count"], 1)
        self.assertEqual(payload["morphs"][0]["morph_type_name"], "vertex")
        self.assertIn('"morph_count": 1', serialized)


if __name__ == "__main__":
    unittest.main()
