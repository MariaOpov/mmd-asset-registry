"""Tests for safe PMX joint structural scanning."""

from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

from mmd_registry.model_scanning import (
    MAX_PMX_JOINT_COUNT,
    scan_pmx_structure,
)
from tests.mmd_fixtures import (
    build_pmx_joint,
    build_pmx_rigid_body,
    build_pmx_structure,
)


class PmxJointScanningTests(unittest.TestCase):
    """Tests for bounded PMX joint metadata extraction."""

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

    def test_scans_zero_joint_section(self) -> None:
        fixture_data = build_pmx_structure(joints=())
        fixture = self.write_fixture("zero_joints.pmx", fixture_data)

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.joint_count, 0)
        self.assertEqual(result.joints, [])
        self.assertEqual(result.bytes_consumed, len(fixture_data))

    def test_scans_joint_metadata_limits_and_springs(self) -> None:
        fixture = self.write_fixture(
            "joint_metadata.pmx",
            build_pmx_structure(
                rigid_bodies=(
                    build_pmx_rigid_body(local_name="A"),
                    build_pmx_rigid_body(local_name="B"),
                ),
                joints=(
                    build_pmx_joint(
                        local_name="Arm Joint",
                        universal_name="Arm Joint EN",
                        rigid_body_a_index=0,
                        rigid_body_b_index=1,
                        position=(1.0, 2.0, 3.0),
                        rotation=(0.1, 0.2, 0.3),
                        translation_limit_minimum=(-1.0, -2.0, -3.0),
                        translation_limit_maximum=(1.0, 2.0, 3.0),
                        rotation_limit_minimum=(-0.1, -0.2, -0.3),
                        rotation_limit_maximum=(0.1, 0.2, 0.3),
                        translation_spring=(4.0, 5.0, 6.0),
                        rotation_spring=(7.0, 8.0, 9.0),
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)
        joint = result.joints[0]

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.joint_count, 1)
        self.assertEqual(joint.local_name, "Arm Joint")
        self.assertEqual(joint.universal_name, "Arm Joint EN")
        self.assertEqual(joint.joint_type, 0)
        self.assertEqual(joint.joint_type_name, "spring_6dof")
        self.assertEqual(joint.rigid_body_a_index, 0)
        self.assertEqual(joint.rigid_body_b_index, 1)
        self.assertEqual(joint.position, (1.0, 2.0, 3.0))
        self.assertEqual(
            joint.translation_limit_minimum,
            (-1.0, -2.0, -3.0),
        )
        self.assertEqual(
            joint.translation_limit_maximum,
            (1.0, 2.0, 3.0),
        )
        self.assertEqual(joint.translation_spring, (4.0, 5.0, 6.0))
        self.assertEqual(joint.rotation_spring, (7.0, 8.0, 9.0))

    def test_scans_all_pmx_2_1_joint_types(self) -> None:
        joints = tuple(
            build_pmx_joint(
                local_name=f"Joint {joint_type}",
                joint_type=joint_type,
            )
            for joint_type in range(6)
        )
        fixture = self.write_fixture(
            "joint_types.pmx",
            build_pmx_structure(version=2.1, joints=joints),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(
            [joint.joint_type_name for joint in result.joints],
            [
                "spring_6dof",
                "6dof",
                "point_to_point",
                "cone_twist",
                "slider",
                "hinge",
            ],
        )

    def test_rejects_pmx_2_1_joint_types_in_pmx_2_0(self) -> None:
        for joint_type in range(1, 6):
            with self.subTest(joint_type=joint_type):
                fixture = self.write_fixture(
                    f"pmx20_type_{joint_type}.pmx",
                    build_pmx_structure(
                        version=2.0,
                        joints=(build_pmx_joint(joint_type=joint_type),),
                    ),
                )

                result = scan_pmx_structure(fixture)
                self.assertEqual(result.status, "error")
                self.assertTrue(
                    any("requires PMX 2.1" in error for error in result.errors)
                )

    def test_scans_utf16_joint_names(self) -> None:
        fixture = self.write_fixture(
            "utf16_joint.pmx",
            build_pmx_structure(
                encoding_flag=0,
                joints=(
                    build_pmx_joint(
                        local_name="接続",
                        universal_name="Joint",
                        encoding_flag=0,
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.joints[0].local_name, "接続")

    def test_supports_all_declared_rigid_body_index_sizes(self) -> None:
        for index_size in (1, 2, 4):
            with self.subTest(index_size=index_size):
                fixture = self.write_fixture(
                    f"rigid_body_index_{index_size}.pmx",
                    build_pmx_structure(
                        rigid_body_index_size=index_size,
                        rigid_bodies=(
                            build_pmx_rigid_body(),
                            build_pmx_rigid_body(),
                        ),
                        joints=(
                            build_pmx_joint(
                                rigid_body_a_index=0,
                                rigid_body_b_index=1,
                                rigid_body_index_size=index_size,
                            ),
                        ),
                    ),
                )

                result = scan_pmx_structure(fixture)
                self.assertEqual(result.status, "ok")
                self.assertEqual(result.joints[0].rigid_body_a_index, 0)
                self.assertEqual(result.joints[0].rigid_body_b_index, 1)

    def test_accepts_minus_one_rigid_body_sentinels(self) -> None:
        fixture = self.write_fixture(
            "joint_sentinels.pmx",
            build_pmx_structure(
                joints=(
                    build_pmx_joint(
                        rigid_body_a_index=-1,
                        rigid_body_b_index=-1,
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.joints[0].rigid_body_a_index, -1)
        self.assertEqual(result.joints[0].rigid_body_b_index, -1)

    def test_rejects_invalid_joint_counts(self) -> None:
        cases = (
            (-1, "cannot be negative"),
            (MAX_PMX_JOINT_COUNT + 1, "exceeds the safety limit"),
            (100, "requires at least"),
        )

        for joint_count, expected in cases:
            with self.subTest(joint_count=joint_count):
                fixture = self.write_fixture(
                    f"count_{joint_count}.pmx",
                    build_pmx_structure(
                        joints=(),
                        joint_count_override=joint_count,
                    ),
                )

                result = scan_pmx_structure(fixture)
                self.assertEqual(result.status, "error")
                self.assertTrue(
                    any(
                        "joint count" in error and expected in error
                        for error in result.errors
                    )
                )

    def test_rejects_invalid_joint_type(self) -> None:
        fixture = self.write_fixture(
            "bad_joint_type.pmx",
            build_pmx_structure(
                version=2.1,
                joints=(build_pmx_joint(joint_type=6),),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(any("invalid joint type 6" in error for error in result.errors))

    def test_rejects_out_of_range_rigid_body_a_index(self) -> None:
        fixture = self.write_fixture(
            "bad_rigid_body_a.pmx",
            build_pmx_structure(
                rigid_bodies=(build_pmx_rigid_body(),),
                joints=(build_pmx_joint(rigid_body_a_index=1),),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "joints[0]" in error and "joint rigid-body A index" in error
                for error in result.errors
            )
        )

    def test_rejects_out_of_range_rigid_body_b_index(self) -> None:
        fixture = self.write_fixture(
            "bad_rigid_body_b.pmx",
            build_pmx_structure(
                rigid_bodies=(build_pmx_rigid_body(),),
                joints=(build_pmx_joint(rigid_body_b_index=1),),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "joints[0]" in error and "joint rigid-body B index" in error
                for error in result.errors
            )
        )

    def test_rejects_non_finite_vector_fields(self) -> None:
        cases = (
            ("position", {"position": (math.nan, 0.0, 0.0)}),
            ("rotation", {"rotation": (0.0, math.inf, 0.0)}),
            (
                "translation limit minimum",
                {
                    "translation_limit_minimum": (
                        0.0,
                        0.0,
                        -math.inf,
                    )
                },
            ),
            (
                "translation limit maximum",
                {
                    "translation_limit_maximum": (
                        math.nan,
                        1.0,
                        1.0,
                    )
                },
            ),
            (
                "rotation limit minimum",
                {
                    "rotation_limit_minimum": (
                        -1.0,
                        math.nan,
                        -1.0,
                    )
                },
            ),
            (
                "rotation limit maximum",
                {
                    "rotation_limit_maximum": (
                        1.0,
                        1.0,
                        math.inf,
                    )
                },
            ),
            (
                "translation spring",
                {"translation_spring": (math.nan, 0.0, 0.0)},
            ),
            (
                "rotation spring",
                {"rotation_spring": (0.0, -math.inf, 0.0)},
            ),
        )

        for expected_label, joint_arguments in cases:
            with self.subTest(expected_label=expected_label):
                fixture = self.write_fixture(
                    f"non_finite_{expected_label.replace(' ', '_')}.pmx",
                    build_pmx_structure(
                        joints=(build_pmx_joint(**joint_arguments),),
                    ),
                )

                result = scan_pmx_structure(fixture)
                self.assertEqual(result.status, "error")
                self.assertTrue(
                    any(
                        expected_label in error and "must be finite" in error
                        for error in result.errors
                    )
                )

    def test_rejects_reversed_translation_limits(self) -> None:
        fixture = self.write_fixture(
            "reversed_translation_limits.pmx",
            build_pmx_structure(
                joints=(
                    build_pmx_joint(
                        translation_limit_minimum=(2.0, -1.0, -1.0),
                        translation_limit_maximum=(1.0, 1.0, 1.0),
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "joint translation limit minimum x value" in error
                and "exceeds maximum" in error
                for error in result.errors
            )
        )

    def test_rejects_reversed_rotation_limits(self) -> None:
        fixture = self.write_fixture(
            "reversed_rotation_limits.pmx",
            build_pmx_structure(
                joints=(
                    build_pmx_joint(
                        rotation_limit_minimum=(-1.0, 2.0, -1.0),
                        rotation_limit_maximum=(1.0, 1.0, 1.0),
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "joint rotation limit minimum y value" in error
                and "exceeds maximum" in error
                for error in result.errors
            )
        )

    def test_accepts_equal_limit_boundaries(self) -> None:
        fixture = self.write_fixture(
            "equal_limits.pmx",
            build_pmx_structure(
                joints=(
                    build_pmx_joint(
                        translation_limit_minimum=(1.0, 1.0, 1.0),
                        translation_limit_maximum=(1.0, 1.0, 1.0),
                        rotation_limit_minimum=(0.0, 0.0, 0.0),
                        rotation_limit_maximum=(0.0, 0.0, 0.0),
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")

    def test_rejects_truncated_joint_record(self) -> None:
        fixture_data = build_pmx_structure(
            joints=(build_pmx_joint(),),
        )
        fixture = self.write_fixture(
            "truncated_joint.pmx",
            fixture_data[:-1],
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "joints[0]" in error and "joint rotation spring z" in error
                for error in result.errors
            )
        )

    def test_joint_result_is_json_serializable(self) -> None:
        fixture = self.write_fixture(
            "joint_json.pmx",
            build_pmx_structure(
                joints=(build_pmx_joint(),),
            ),
        )

        result = scan_pmx_structure(fixture)
        encoded = json.dumps(result.to_dict(), ensure_ascii=False)
        decoded = json.loads(encoded)

        self.assertEqual(decoded["joint_count"], 1)
        self.assertEqual(decoded["joints"][0]["joint_type_name"], "spring_6dof")
        self.assertEqual(decoded["joints"][0]["position"], [0.0, 0.0, 0.0])

    def test_error_context_identifies_later_joint_record(self) -> None:
        fixture = self.write_fixture(
            "second_joint_error.pmx",
            build_pmx_structure(
                version=2.1,
                joints=(
                    build_pmx_joint(local_name="Valid"),
                    build_pmx_joint(local_name="Invalid", joint_type=9),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "joints[1]" in error and "invalid joint type 9" in error
                for error in result.errors
            )
        )


if __name__ == "__main__":
    unittest.main()
