"""Tests for safe PMX rigid-body structural scanning."""

from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

from mmd_registry.model_scanning import (
    MAX_PMX_RIGID_BODY_COUNT,
    scan_pmx_structure,
)
from tests.mmd_fixtures import (
    build_pmx_bone,
    build_pmx_impulse_morph_offset,
    build_pmx_morph,
    build_pmx_rigid_body,
    build_pmx_structure,
)


class PmxRigidBodyScanningTests(unittest.TestCase):
    """Tests for bounded PMX rigid-body metadata extraction."""

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

    def test_scans_zero_rigid_body_section(self) -> None:
        fixture_data = build_pmx_structure(rigid_bodies=())
        fixture = self.write_fixture("zero_rigid_bodies.pmx", fixture_data)

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.rigid_body_count, 0)
        self.assertEqual(result.rigid_bodies, [])
        self.assertEqual(result.bytes_consumed, len(fixture_data))

    def test_scans_all_shapes_and_physics_modes(self) -> None:
        rigid_bodies = tuple(
            build_pmx_rigid_body(
                local_name=f"Rigid {value}",
                shape=value,
                physics_mode=value,
                collision_group=value,
                collision_mask=0xFFFF ^ (1 << value),
            )
            for value in range(3)
        )
        fixture = self.write_fixture(
            "shape_modes.pmx",
            build_pmx_structure(rigid_bodies=rigid_bodies),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.rigid_body_count, 3)
        self.assertEqual(
            [record.shape_name for record in result.rigid_bodies],
            ["sphere", "box", "capsule"],
        )
        self.assertEqual(
            [record.physics_mode_name for record in result.rigid_bodies],
            [
                "bone_follow",
                "physics",
                "physics_with_bone_alignment",
            ],
        )
        self.assertEqual(result.rigid_bodies[2].collision_group, 2)
        self.assertEqual(result.rigid_bodies[2].collision_mask, 0xFFFB)

    def test_scans_physical_metadata_and_bone_reference(self) -> None:
        fixture = self.write_fixture(
            "physical_metadata.pmx",
            build_pmx_structure(
                bones=(build_pmx_bone(local_name="Root"),),
                rigid_bodies=(
                    build_pmx_rigid_body(
                        local_name="Body",
                        universal_name="Body EN",
                        bone_index=0,
                        size=(1.0, 2.0, 3.0),
                        position=(-1.0, 2.0, -3.0),
                        rotation=(0.1, 0.2, 0.3),
                        mass=4.0,
                        linear_damping=0.1,
                        angular_damping=0.2,
                        restitution=0.3,
                        friction=0.4,
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)
        rigid_body = result.rigid_bodies[0]

        self.assertEqual(result.status, "ok")
        self.assertEqual(rigid_body.local_name, "Body")
        self.assertEqual(rigid_body.universal_name, "Body EN")
        self.assertEqual(rigid_body.bone_index, 0)
        self.assertEqual(rigid_body.size, (1.0, 2.0, 3.0))
        for actual, expected in zip(
            rigid_body.position,
            (-1.0, 2.0, -3.0),
        ):
            self.assertAlmostEqual(actual, expected)
        self.assertAlmostEqual(rigid_body.mass, 4.0)
        self.assertAlmostEqual(rigid_body.friction, 0.4)

    def test_accepts_minus_one_bone_sentinel(self) -> None:
        fixture = self.write_fixture(
            "bone_sentinel.pmx",
            build_pmx_structure(
                rigid_bodies=(build_pmx_rigid_body(bone_index=-1),),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.rigid_bodies[0].bone_index, -1)

    def test_scans_utf16_rigid_body_names(self) -> None:
        fixture = self.write_fixture(
            "utf16_rigid_body.pmx",
            build_pmx_structure(
                encoding_flag=0,
                rigid_bodies=(
                    build_pmx_rigid_body(
                        local_name="剛体",
                        universal_name="Rigid Body",
                        encoding_flag=0,
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.rigid_bodies[0].local_name, "剛体")

    def test_supports_all_declared_bone_index_sizes(self) -> None:
        for index_size in (1, 2, 4):
            with self.subTest(index_size=index_size):
                fixture = self.write_fixture(
                    f"bone_index_{index_size}.pmx",
                    build_pmx_structure(
                        bone_index_size=index_size,
                        bones=(
                            build_pmx_bone(
                                bone_index_size=index_size,
                            ),
                        ),
                        rigid_bodies=(
                            build_pmx_rigid_body(
                                bone_index=0,
                                bone_index_size=index_size,
                            ),
                        ),
                    ),
                )

                result = scan_pmx_structure(fixture)
                self.assertEqual(result.status, "ok")
                self.assertEqual(result.rigid_bodies[0].bone_index, 0)

    def test_rejects_invalid_rigid_body_counts(self) -> None:
        cases = (
            (-1, "cannot be negative"),
            (MAX_PMX_RIGID_BODY_COUNT + 1, "exceeds the safety limit"),
            (100, "requires at least"),
        )

        for rigid_body_count, expected in cases:
            with self.subTest(rigid_body_count=rigid_body_count):
                fixture = self.write_fixture(
                    f"count_{rigid_body_count}.pmx",
                    build_pmx_structure(
                        rigid_bodies=(),
                        rigid_body_count_override=rigid_body_count,
                    ),
                )

                result = scan_pmx_structure(fixture)
                self.assertEqual(result.status, "error")
                self.assertTrue(
                    any(
                        "rigid-body count" in error and expected in error
                        for error in result.errors
                    )
                )

    def test_rejects_out_of_range_bone_index(self) -> None:
        fixture = self.write_fixture(
            "bad_bone_index.pmx",
            build_pmx_structure(
                bones=(build_pmx_bone(),),
                rigid_bodies=(build_pmx_rigid_body(bone_index=1),),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "rigid_bodies[0]" in error and "rigid-body bone index" in error
                for error in result.errors
            )
        )

    def test_rejects_invalid_collision_group(self) -> None:
        fixture = self.write_fixture(
            "bad_collision_group.pmx",
            build_pmx_structure(
                rigid_bodies=(build_pmx_rigid_body(collision_group=16),),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(any("collision group 16" in error for error in result.errors))

    def test_rejects_invalid_shape(self) -> None:
        fixture = self.write_fixture(
            "bad_shape.pmx",
            build_pmx_structure(
                rigid_bodies=(build_pmx_rigid_body(shape=3),),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any("invalid rigid-body shape 3" in error for error in result.errors)
        )

    def test_rejects_invalid_physics_mode(self) -> None:
        fixture = self.write_fixture(
            "bad_physics_mode.pmx",
            build_pmx_structure(
                rigid_bodies=(build_pmx_rigid_body(physics_mode=3),),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any("invalid physics mode 3" in error for error in result.errors)
        )

    def test_rejects_non_finite_vector_fields(self) -> None:
        cases = (
            ({"size": (math.nan, 1.0, 1.0)}, "rigid-body size x"),
            ({"position": (0.0, math.inf, 0.0)}, "rigid-body position y"),
            ({"rotation": (0.0, 0.0, -math.inf)}, "rigid-body rotation z"),
        )

        for kwargs, expected in cases:
            with self.subTest(expected=expected):
                fixture = self.write_fixture(
                    f"nonfinite_{expected.replace(' ', '_')}.pmx",
                    build_pmx_structure(
                        rigid_bodies=(build_pmx_rigid_body(**kwargs),),
                    ),
                )
                result = scan_pmx_structure(fixture)
                self.assertEqual(result.status, "error")
                self.assertTrue(
                    any(
                        expected in error and "must be finite" in error
                        for error in result.errors
                    )
                )

    def test_rejects_negative_size_components(self) -> None:
        fixture = self.write_fixture(
            "negative_size.pmx",
            build_pmx_structure(
                rigid_bodies=(build_pmx_rigid_body(size=(1.0, -2.0, 3.0)),),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "rigid-body size y cannot be negative" in error
                for error in result.errors
            )
        )

    def test_rejects_invalid_physical_scalars(self) -> None:
        cases = (
            ({"mass": -1.0}, "rigid-body mass cannot be negative"),
            ({"linear_damping": math.nan}, "rigid-body linear damping must be finite"),
            (
                {"angular_damping": math.inf},
                "rigid-body angular damping must be finite",
            ),
            ({"restitution": -0.1}, "rigid-body restitution cannot be negative"),
            ({"friction": -0.1}, "rigid-body friction cannot be negative"),
        )

        for kwargs, expected in cases:
            with self.subTest(expected=expected):
                fixture = self.write_fixture(
                    "invalid_scalar.pmx",
                    build_pmx_structure(
                        rigid_bodies=(build_pmx_rigid_body(**kwargs),),
                    ),
                )
                result = scan_pmx_structure(fixture)
                self.assertEqual(result.status, "error")
                self.assertTrue(any(expected in error for error in result.errors))

    def test_rejects_truncated_rigid_body_record(self) -> None:
        fixture_data = build_pmx_structure(
            rigid_bodies=(build_pmx_rigid_body(),),
        )
        fixture = self.write_fixture(
            "truncated_rigid_body.pmx",
            fixture_data[:-1],
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "rigid_bodies[0]" in error and "rigid-body physics mode" in error
                for error in result.errors
            )
        )

    def test_validates_impulse_morph_rigid_body_reference(self) -> None:
        fixture = self.write_fixture(
            "valid_impulse_reference.pmx",
            build_pmx_structure(
                version=2.1,
                morphs=(
                    build_pmx_morph(
                        morph_type=10,
                        offsets=(
                            build_pmx_impulse_morph_offset(
                                rigid_body_index=0,
                            ),
                        ),
                    ),
                ),
                rigid_bodies=(build_pmx_rigid_body(),),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        impulse = result.morphs[0].offsets[0]
        self.assertEqual(impulse.rigid_body_index, 0)

    def test_rejects_out_of_range_impulse_morph_reference(self) -> None:
        fixture = self.write_fixture(
            "bad_impulse_reference.pmx",
            build_pmx_structure(
                version=2.1,
                morphs=(
                    build_pmx_morph(
                        morph_type=10,
                        offsets=(
                            build_pmx_impulse_morph_offset(
                                rigid_body_index=1,
                            ),
                        ),
                    ),
                ),
                rigid_bodies=(build_pmx_rigid_body(),),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "morphs[0].offsets[0]" in error
                and "impulse morph rigid-body index" in error
                for error in result.errors
            )
        )

    def test_rigid_body_result_is_json_serializable(self) -> None:
        fixture = self.write_fixture(
            "rigid_body_json.pmx",
            build_pmx_structure(
                rigid_bodies=(
                    build_pmx_rigid_body(
                        local_name="Physics",
                        shape=1,
                        physics_mode=2,
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)
        payload = result.to_dict()
        serialized = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["rigid_body_count"], 1)
        self.assertEqual(payload["rigid_bodies"][0]["shape_name"], "box")
        self.assertIn('"rigid_body_count": 1', serialized)


if __name__ == "__main__":
    unittest.main()
