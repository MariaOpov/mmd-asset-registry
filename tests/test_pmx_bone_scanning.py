"""Tests for safe PMX bone-section structural scanning."""

from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

from mmd_registry.model_scanning import (
    MAX_PMX_BONE_COUNT,
    MAX_PMX_IK_LINK_COUNT,
    MAX_PMX_IK_LOOP_COUNT,
    PMX_BONE_FLAG_AFTER_PHYSICS,
    PMX_BONE_FLAG_ENABLED,
    PMX_BONE_FLAG_LOCAL_APPEND,
    PMX_BONE_FLAG_ROTATABLE,
    PMX_BONE_FLAG_TRANSLATABLE,
    PMX_BONE_FLAG_VISIBLE,
    scan_pmx_structure,
)
from tests.mmd_fixtures import (
    build_pmx_bone,
    build_pmx_ik_link,
    build_pmx_structure,
)


class PmxBoneScanningTests(unittest.TestCase):
    """Tests for bounded PMX bone and IK parsing."""

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

    def test_scans_zero_bone_section(self) -> None:
        fixture_data = build_pmx_structure(
            bones=(),
        )
        fixture = self.write_fixture(
            "no_bones.pmx",
            fixture_data,
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.bone_count, 0)
        self.assertEqual(result.bones, [])
        self.assertEqual(
            result.bytes_consumed,
            len(fixture_data),
        )

    def test_scans_basic_offset_tail_bone(self) -> None:
        flags = (
            PMX_BONE_FLAG_ROTATABLE
            | PMX_BONE_FLAG_TRANSLATABLE
            | PMX_BONE_FLAG_VISIBLE
            | PMX_BONE_FLAG_ENABLED
            | PMX_BONE_FLAG_LOCAL_APPEND
            | PMX_BONE_FLAG_AFTER_PHYSICS
        )
        fixture = self.write_fixture(
            "basic_bone.pmx",
            build_pmx_structure(
                bones=(
                    build_pmx_bone(
                        local_name="Center",
                        universal_name="Center",
                        position=(1.0, 2.0, 3.0),
                        transform_layer=2,
                        tail_offset=(0.0, 1.5, 0.0),
                        extra_flags=flags,
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)
        bone = result.bones[0]

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.bone_count, 1)
        self.assertEqual(bone.local_name, "Center")
        self.assertEqual(bone.position, (1.0, 2.0, 3.0))
        self.assertEqual(bone.parent_bone_index, -1)
        self.assertEqual(bone.transform_layer, 2)
        self.assertEqual(bone.tail_mode, "offset")
        self.assertEqual(bone.tail_offset, (0.0, 1.5, 0.0))
        self.assertIn("rotatable", bone.flag_names)
        self.assertIn("local_append", bone.flag_names)
        self.assertIn("after_physics", bone.flag_names)

    def test_scans_indexed_tail_and_parent_references(self) -> None:
        fixture = self.write_fixture(
            "indexed_tail.pmx",
            build_pmx_structure(
                bones=(
                    build_pmx_bone(
                        local_name="Root",
                        tail_bone_index=1,
                    ),
                    build_pmx_bone(
                        local_name="Child",
                        parent_bone_index=0,
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.bone_count, 2)
        self.assertEqual(result.bones[0].tail_mode, "bone")
        self.assertEqual(result.bones[0].tail_bone_index, 1)
        self.assertEqual(result.bones[1].parent_bone_index, 0)

    def test_scans_all_optional_non_ik_fields(self) -> None:
        fixture = self.write_fixture(
            "optional_fields.pmx",
            build_pmx_structure(
                bones=(
                    build_pmx_bone(
                        local_name="Root",
                    ),
                    build_pmx_bone(
                        local_name="Controlled",
                        parent_bone_index=0,
                        inherit_rotation=True,
                        inherit_translation=True,
                        inherit_parent_bone_index=0,
                        inherit_weight=0.75,
                        fixed_axis=(1.0, 0.0, 0.0),
                        local_axes=(
                            (1.0, 0.0, 0.0),
                            (0.0, 0.0, 1.0),
                        ),
                        external_parent_key=42,
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)
        bone = result.bones[1]

        self.assertEqual(result.status, "ok")
        self.assertEqual(bone.inherit_parent_bone_index, 0)
        self.assertAlmostEqual(bone.inherit_weight or 0.0, 0.75)
        self.assertEqual(bone.fixed_axis, (1.0, 0.0, 0.0))
        self.assertEqual(bone.local_axis_x, (1.0, 0.0, 0.0))
        self.assertEqual(bone.local_axis_z, (0.0, 0.0, 1.0))
        self.assertEqual(bone.external_parent_key, 42)
        self.assertIn("inherit_rotation", bone.flag_names)
        self.assertIn("inherit_translation", bone.flag_names)
        self.assertIn("fixed_axis", bone.flag_names)
        self.assertIn("local_axes", bone.flag_names)
        self.assertIn("external_parent", bone.flag_names)

    def test_scans_ik_links_with_and_without_limits(self) -> None:
        fixture = self.write_fixture(
            "ik_bone.pmx",
            build_pmx_structure(
                bones=(
                    build_pmx_bone(local_name="Target"),
                    build_pmx_bone(local_name="Link A"),
                    build_pmx_bone(local_name="Link B"),
                    build_pmx_bone(
                        local_name="IK",
                        ik_target_bone_index=0,
                        ik_loop_count=40,
                        ik_angle_limit=0.75,
                        ik_links=(
                            build_pmx_ik_link(
                                bone_index=1,
                            ),
                            build_pmx_ik_link(
                                bone_index=2,
                                angle_limit_flag=1,
                                lower_limit=(-1.0, -0.5, -0.25),
                                upper_limit=(1.0, 0.5, 0.25),
                            ),
                        ),
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)
        ik = result.bones[3].ik

        self.assertEqual(result.status, "ok")
        self.assertIsNotNone(ik)
        assert ik is not None
        self.assertEqual(ik.target_bone_index, 0)
        self.assertEqual(ik.loop_count, 40)
        self.assertAlmostEqual(ik.angle_limit, 0.75)
        self.assertEqual(len(ik.links), 2)
        self.assertFalse(ik.links[0].angle_limits_enabled)
        self.assertTrue(ik.links[1].angle_limits_enabled)
        self.assertEqual(
            ik.links[1].lower_limit,
            (-1.0, -0.5, -0.25),
        )
        self.assertEqual(
            ik.links[1].upper_limit,
            (1.0, 0.5, 0.25),
        )

    def test_scans_utf16_bone_names(self) -> None:
        fixture = self.write_fixture(
            "utf16_bone.pmx",
            build_pmx_structure(
                encoding_flag=0,
                bones=(
                    build_pmx_bone(
                        local_name="センター",
                        universal_name="Center",
                        encoding_flag=0,
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.encoding, "utf-16-le")
        self.assertEqual(result.bones[0].local_name, "センター")

    def test_accepts_minus_one_reference_sentinels(self) -> None:
        fixture = self.write_fixture(
            "sentinels.pmx",
            build_pmx_structure(
                bones=(
                    build_pmx_bone(
                        parent_bone_index=-1,
                        tail_bone_index=-1,
                        inherit_rotation=True,
                        inherit_parent_bone_index=-1,
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.bones[0].parent_bone_index, -1)
        self.assertEqual(result.bones[0].tail_bone_index, -1)
        self.assertEqual(
            result.bones[0].inherit_parent_bone_index,
            -1,
        )

    def test_rejects_out_of_range_parent_index(self) -> None:
        fixture = self.write_fixture(
            "parent_index.pmx",
            build_pmx_structure(
                bones=(
                    build_pmx_bone(
                        parent_bone_index=1,
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "bones[0]" in error
                and "parent bone index" in error
                and "index 1 is invalid" in error
                for error in result.errors
            )
        )

    def test_rejects_out_of_range_tail_index(self) -> None:
        fixture = self.write_fixture(
            "tail_index.pmx",
            build_pmx_structure(
                bones=(
                    build_pmx_bone(
                        tail_bone_index=2,
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "tail bone index" in error and "index 2 is invalid" in error
                for error in result.errors
            )
        )

    def test_rejects_out_of_range_inherit_index(self) -> None:
        fixture = self.write_fixture(
            "inherit_index.pmx",
            build_pmx_structure(
                bones=(
                    build_pmx_bone(
                        inherit_rotation=True,
                        inherit_parent_bone_index=3,
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "inherit parent bone index" in error and "index 3 is invalid" in error
                for error in result.errors
            )
        )

    def test_rejects_out_of_range_ik_target(self) -> None:
        fixture = self.write_fixture(
            "ik_target.pmx",
            build_pmx_structure(
                bones=(
                    build_pmx_bone(
                        ik_target_bone_index=4,
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "IK target bone index" in error and "index 4 is invalid" in error
                for error in result.errors
            )
        )

    def test_rejects_out_of_range_ik_link_index(self) -> None:
        fixture = self.write_fixture(
            "ik_link_index.pmx",
            build_pmx_structure(
                bones=(
                    build_pmx_bone(local_name="Target"),
                    build_pmx_bone(
                        local_name="IK",
                        ik_target_bone_index=0,
                        ik_links=(
                            build_pmx_ik_link(
                                bone_index=5,
                            ),
                        ),
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "bones[1].ik_links[0]" in error and "IK link bone index" in error
                for error in result.errors
            )
        )

    def test_rejects_invalid_ik_angle_limit_flag(self) -> None:
        fixture = self.write_fixture(
            "ik_limit_flag.pmx",
            build_pmx_structure(
                bones=(
                    build_pmx_bone(local_name="Target"),
                    build_pmx_bone(
                        local_name="IK",
                        ik_target_bone_index=0,
                        ik_links=(
                            build_pmx_ik_link(
                                bone_index=0,
                                angle_limit_flag=2,
                            ),
                        ),
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "angle-limit flag" in error and "expected 0 or 1" in error
                for error in result.errors
            )
        )

    def test_rejects_invalid_ik_loop_counts(self) -> None:
        for label, loop_count, expected in (
            ("negative", -1, "cannot be negative"),
            (
                "oversized",
                MAX_PMX_IK_LOOP_COUNT + 1,
                "exceeds the safety limit",
            ),
        ):
            with self.subTest(label=label):
                fixture = self.write_fixture(
                    f"{label}_ik_loop.pmx",
                    build_pmx_structure(
                        bones=(
                            build_pmx_bone(local_name="Target"),
                            build_pmx_bone(
                                local_name="IK",
                                ik_target_bone_index=0,
                                ik_loop_count=loop_count,
                            ),
                        ),
                    ),
                )

                result = scan_pmx_structure(fixture)

                self.assertEqual(result.status, "error")
                self.assertTrue(
                    any(
                        "IK loop count" in error and expected in error
                        for error in result.errors
                    )
                )

    def test_rejects_non_finite_ik_angle_limit(self) -> None:
        fixture = self.write_fixture(
            "ik_angle_nan.pmx",
            build_pmx_structure(
                bones=(
                    build_pmx_bone(local_name="Target"),
                    build_pmx_bone(
                        local_name="IK",
                        ik_target_bone_index=0,
                        ik_angle_limit=math.nan,
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "IK angle limit" in error and "finite" in error
                for error in result.errors
            )
        )

    def test_rejects_invalid_ik_link_counts(self) -> None:
        for label, link_count, expected in (
            ("negative", -1, "cannot be negative"),
            (
                "oversized",
                MAX_PMX_IK_LINK_COUNT + 1,
                "exceeds the safety limit",
            ),
            ("impossible", 10, "requires at least"),
        ):
            with self.subTest(label=label):
                fixture = self.write_fixture(
                    f"{label}_ik_links.pmx",
                    build_pmx_structure(
                        bones=(
                            build_pmx_bone(local_name="Target"),
                            build_pmx_bone(
                                local_name="IK",
                                ik_target_bone_index=0,
                                ik_link_count_override=link_count,
                            ),
                        ),
                    ),
                )

                result = scan_pmx_structure(fixture)

                self.assertEqual(result.status, "error")
                self.assertTrue(
                    any(
                        "IK link count" in error and expected in error
                        for error in result.errors
                    )
                )

    def test_rejects_invalid_bone_counts(self) -> None:
        for label, bone_count, expected in (
            ("negative", -1, "cannot be negative"),
            (
                "oversized",
                MAX_PMX_BONE_COUNT + 1,
                "exceeds the safety limit",
            ),
            ("impossible", 100, "requires at least"),
        ):
            with self.subTest(label=label):
                fixture = self.write_fixture(
                    f"{label}_bone_count.pmx",
                    build_pmx_structure(
                        bones=(),
                        bone_count_override=bone_count,
                    ),
                )

                result = scan_pmx_structure(fixture)

                self.assertEqual(result.status, "error")
                self.assertTrue(
                    any(
                        "bone count" in error and expected in error
                        for error in result.errors
                    )
                )

    def test_rejects_truncated_bone_record(self) -> None:
        fixture_data = build_pmx_structure(
            bones=(
                build_pmx_bone(
                    local_name="Truncated",
                ),
            ),
        )
        fixture = self.write_fixture(
            "truncated_bone.pmx",
            fixture_data[:-5],
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "bones[0]" in error and "bone tail offset" in error
                for error in result.errors
            )
        )

    def test_bone_result_is_json_serializable(self) -> None:
        fixture = self.write_fixture(
            "bone_json.pmx",
            build_pmx_structure(
                bones=(
                    build_pmx_bone(
                        local_name="Center",
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
        self.assertEqual(payload["bone_count"], 1)
        self.assertEqual(
            payload["bones"][0]["local_name"],
            "Center",
        )
        self.assertEqual(
            payload["bones"][0]["tail_mode"],
            "offset",
        )
        self.assertIn('"bone_count": 1', serialized)


if __name__ == "__main__":
    unittest.main()
