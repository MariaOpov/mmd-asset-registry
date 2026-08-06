"""Tests for safe PMX 2.1 soft-body structural scanning."""

from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mmd_registry import model_scanning
from mmd_registry.model_scanning import (
    MAX_PMX_SOFT_BODY_ANCHOR_COUNT,
    MAX_PMX_SOFT_BODY_COUNT,
    MAX_PMX_SOFT_BODY_PARAMETER_COUNT,
    MAX_PMX_SOFT_BODY_PIN_COUNT,
    scan_pmx_structure,
)
from tests.mmd_fixtures import (
    build_pmx_rigid_body,
    build_pmx_soft_body,
    build_pmx_soft_body_anchor,
    build_pmx_structure,
)


class PmxSoftBodyScanningTests(unittest.TestCase):
    """Tests for bounded PMX 2.1 soft-body metadata extraction."""

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

    def test_scans_zero_soft_body_section(self) -> None:
        fixture_data = build_pmx_structure(version=2.1)
        fixture = self.write_fixture("zero_soft_bodies.pmx", fixture_data)

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.soft_body_count, 0)
        self.assertEqual(result.soft_bodies, [])
        self.assertEqual(result.bytes_consumed, len(fixture_data))

    def test_pmx_2_0_has_no_soft_body_section(self) -> None:
        fixture_data = build_pmx_structure(version=2.0)
        fixture = self.write_fixture("pmx20_no_soft_body.pmx", fixture_data)

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.soft_body_count, 0)
        self.assertEqual(result.soft_bodies, [])
        self.assertEqual(result.bytes_consumed, len(fixture_data))

    def test_scans_soft_body_metadata_configs_anchors_and_pins(self) -> None:
        anchor = build_pmx_soft_body_anchor(
            rigid_body_index=0,
            vertex_index=0,
            near_mode=1,
        )
        soft_body = build_pmx_soft_body(
            local_name="Cape",
            universal_name="Cape EN",
            shape=0,
            material_index=0,
            collision_group=3,
            collision_mask=0xFF00,
            flags=0x07,
            bending_link_distance=2,
            cluster_count=4,
            total_mass=5.0,
            collision_margin=0.25,
            aerodynamics_model=3,
            config=tuple(float(value) / 10.0 for value in range(1, 13)),
            cluster_config=(1.1, 1.2, 1.3, 1.4, 1.5, 1.6),
            iteration_config=(2, 3, 4, 5),
            material_config=(0.7, 0.8, 0.9),
            anchors=(anchor,),
            pinned_vertex_indices=(1,),
        )
        fixture = self.write_fixture(
            "soft_body_metadata.pmx",
            build_pmx_structure(
                version=2.1,
                deform_types=(0, 0),
                rigid_bodies=(build_pmx_rigid_body(),),
                soft_bodies=(soft_body,),
            ),
        )

        result = scan_pmx_structure(fixture)
        scanned = result.soft_bodies[0]

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.soft_body_count, 1)
        self.assertEqual(scanned.local_name, "Cape")
        self.assertEqual(scanned.universal_name, "Cape EN")
        self.assertEqual(scanned.shape_name, "tri_mesh")
        self.assertEqual(scanned.material_index, 0)
        self.assertEqual(scanned.collision_group, 3)
        self.assertEqual(scanned.collision_mask, 0xFF00)
        self.assertEqual(
            scanned.flag_names,
            (
                "generate_bending_links",
                "generate_clusters",
                "randomize_constraints",
            ),
        )
        self.assertEqual(scanned.bending_link_distance, 2)
        self.assertEqual(scanned.cluster_count, 4)
        self.assertAlmostEqual(scanned.total_mass, 5.0)
        self.assertEqual(scanned.config.aerodynamics_model_name, "face_two_sided")
        self.assertEqual(scanned.iteration_config.position, 3)
        self.assertAlmostEqual(scanned.material_config.volume_stiffness, 0.9)
        self.assertEqual(scanned.anchors[0].rigid_body_index, 0)
        self.assertEqual(scanned.anchors[0].vertex_index, 0)
        self.assertTrue(scanned.anchors[0].near_mode)
        self.assertEqual(scanned.pinned_vertex_indices, (1,))

    def test_scans_both_soft_body_shapes(self) -> None:
        fixture = self.write_fixture(
            "soft_body_shapes.pmx",
            build_pmx_structure(
                version=2.1,
                soft_bodies=(
                    build_pmx_soft_body(shape=0),
                    build_pmx_soft_body(shape=1),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(
            [soft_body.shape_name for soft_body in result.soft_bodies],
            ["tri_mesh", "rope"],
        )

    def test_scans_all_aerodynamics_models(self) -> None:
        fixture = self.write_fixture(
            "aerodynamics_models.pmx",
            build_pmx_structure(
                version=2.1,
                soft_bodies=tuple(
                    build_pmx_soft_body(aerodynamics_model=value) for value in range(5)
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(
            [body.config.aerodynamics_model_name for body in result.soft_bodies],
            [
                "vertex_point",
                "vertex_two_sided",
                "vertex_one_sided",
                "face_two_sided",
                "face_one_sided",
            ],
        )

    def test_scans_utf16_soft_body_names(self) -> None:
        fixture = self.write_fixture(
            "utf16_soft_body.pmx",
            build_pmx_structure(
                version=2.1,
                encoding_flag=0,
                soft_bodies=(
                    build_pmx_soft_body(
                        local_name="布",
                        universal_name="Cloth",
                        encoding_flag=0,
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.soft_bodies[0].local_name, "布")

    def test_supports_all_referenced_index_sizes(self) -> None:
        for index_size in (1, 2, 4):
            with self.subTest(index_size=index_size):
                anchor = build_pmx_soft_body_anchor(
                    rigid_body_index=0,
                    vertex_index=0,
                    rigid_body_index_size=index_size,
                    vertex_index_size=index_size,
                )
                fixture = self.write_fixture(
                    f"soft_body_index_{index_size}.pmx",
                    build_pmx_structure(
                        version=2.1,
                        vertex_index_size=index_size,
                        material_index_size=index_size,
                        rigid_body_index_size=index_size,
                        rigid_bodies=(build_pmx_rigid_body(),),
                        soft_bodies=(
                            build_pmx_soft_body(
                                anchors=(anchor,),
                                pinned_vertex_indices=(0,),
                                material_index_size=index_size,
                                vertex_index_size=index_size,
                            ),
                        ),
                    ),
                )

                result = scan_pmx_structure(fixture)
                self.assertEqual(result.status, "ok")
                self.assertEqual(result.soft_bodies[0].material_index, 0)
                self.assertEqual(result.soft_bodies[0].anchors[0].vertex_index, 0)

    def test_accepts_minus_one_material_sentinel(self) -> None:
        fixture = self.write_fixture(
            "soft_body_material_sentinel.pmx",
            build_pmx_structure(
                version=2.1,
                soft_bodies=(build_pmx_soft_body(material_index=-1),),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.soft_bodies[0].material_index, -1)

    def test_rejects_invalid_soft_body_counts(self) -> None:
        cases = (
            (-1, "cannot be negative"),
            (MAX_PMX_SOFT_BODY_COUNT + 1, "exceeds the safety limit"),
            (100, "requires at least"),
        )

        for count, expected in cases:
            with self.subTest(count=count):
                fixture = self.write_fixture(
                    f"soft_body_count_{count}.pmx",
                    build_pmx_structure(
                        version=2.1,
                        soft_body_count_override=count,
                    ),
                )

                result = scan_pmx_structure(fixture)
                self.assertEqual(result.status, "error")
                self.assertTrue(
                    any(
                        "soft-body count" in error and expected in error
                        for error in result.errors
                    )
                )

    def test_rejects_invalid_shape(self) -> None:
        fixture = self.write_fixture(
            "invalid_soft_body_shape.pmx",
            build_pmx_structure(
                version=2.1,
                soft_bodies=(build_pmx_soft_body(shape=2),),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any("invalid soft-body shape 2" in error for error in result.errors)
        )

    def test_rejects_out_of_range_material_index(self) -> None:
        fixture = self.write_fixture(
            "invalid_soft_body_material.pmx",
            build_pmx_structure(
                version=2.1,
                soft_bodies=(build_pmx_soft_body(material_index=1),),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any("soft-body material index" in error for error in result.errors)
        )

    def test_rejects_invalid_collision_group_and_flags(self) -> None:
        cases = (
            ({"collision_group": 16}, "collision group 16"),
            ({"flags": 0x08}, "unknown bits 0x08"),
        )

        for arguments, expected in cases:
            with self.subTest(expected=expected):
                fixture = self.write_fixture(
                    f"invalid_{expected.replace(' ', '_')}.pmx",
                    build_pmx_structure(
                        version=2.1,
                        soft_bodies=(build_pmx_soft_body(**arguments),),
                    ),
                )

                result = scan_pmx_structure(fixture)
                self.assertEqual(result.status, "error")
                self.assertTrue(any(expected in error for error in result.errors))

    def test_rejects_invalid_integer_parameters(self) -> None:
        cases = (
            ({"bending_link_distance": -1}, "bending-link distance"),
            ({"cluster_count": -1}, "cluster count"),
            (
                {"cluster_count": MAX_PMX_SOFT_BODY_PARAMETER_COUNT + 1},
                "exceeds the safety limit",
            ),
            ({"iteration_config": (0, -1, 0, 0)}, "position iteration count"),
        )

        for arguments, expected in cases:
            with self.subTest(expected=expected):
                fixture = self.write_fixture(
                    f"invalid_integer_{len(expected)}.pmx",
                    build_pmx_structure(
                        version=2.1,
                        soft_bodies=(build_pmx_soft_body(**arguments),),
                    ),
                )

                result = scan_pmx_structure(fixture)
                self.assertEqual(result.status, "error")
                self.assertTrue(any(expected in error for error in result.errors))

    def test_rejects_invalid_mass_and_margin(self) -> None:
        cases = (
            ({"total_mass": -1.0}, "total mass cannot be negative"),
            ({"collision_margin": -0.1}, "collision margin cannot be negative"),
            ({"total_mass": math.nan}, "total mass must be finite"),
            ({"collision_margin": math.inf}, "collision margin must be finite"),
        )

        for arguments, expected in cases:
            with self.subTest(expected=expected):
                fixture = self.write_fixture(
                    f"invalid_physical_{len(expected)}.pmx",
                    build_pmx_structure(
                        version=2.1,
                        soft_bodies=(build_pmx_soft_body(**arguments),),
                    ),
                )

                result = scan_pmx_structure(fixture)
                self.assertEqual(result.status, "error")
                self.assertTrue(any(expected in error for error in result.errors))

    def test_rejects_non_finite_configuration_values(self) -> None:
        config = [
            1.0,
            0.0,
            0.0,
            0.0,
            math.nan,
            0.0,
            0.0,
            0.0,
            1.0,
            0.1,
            1.0,
            0.7,
        ]
        cluster = [1.0, 0.1, math.inf, 0.5, 0.5, 0.5]

        cases = (
            ({"config": tuple(config)}, "pressure coefficient"),
            ({"cluster_config": tuple(cluster)}, "soft-soft cluster hardness"),
            (
                {"material_config": (1.0, -math.inf, 1.0)},
                "area-angular stiffness",
            ),
        )

        for arguments, expected in cases:
            with self.subTest(expected=expected):
                fixture = self.write_fixture(
                    f"non_finite_config_{len(expected)}.pmx",
                    build_pmx_structure(
                        version=2.1,
                        soft_bodies=(build_pmx_soft_body(**arguments),),
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

    def test_rejects_invalid_aerodynamics_model(self) -> None:
        fixture = self.write_fixture(
            "invalid_aero_model.pmx",
            build_pmx_structure(
                version=2.1,
                soft_bodies=(build_pmx_soft_body(aerodynamics_model=5),),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(any("aerodynamics model 5" in error for error in result.errors))

    def test_rejects_invalid_anchor_counts(self) -> None:
        cases = (
            (-1, "cannot be negative"),
            (MAX_PMX_SOFT_BODY_ANCHOR_COUNT + 1, "exceeds the safety limit"),
            (100, "requires at least"),
        )

        for count, expected in cases:
            with self.subTest(count=count):
                fixture = self.write_fixture(
                    f"anchor_count_{count}.pmx",
                    build_pmx_structure(
                        version=2.1,
                        soft_bodies=(build_pmx_soft_body(anchor_count_override=count),),
                    ),
                )

                result = scan_pmx_structure(fixture)
                self.assertEqual(result.status, "error")
                self.assertTrue(
                    any(
                        "soft-body anchor count" in error and expected in error
                        for error in result.errors
                    )
                )

    def test_rejects_invalid_pinned_vertex_counts(self) -> None:
        cases = (
            (-1, "cannot be negative"),
            (MAX_PMX_SOFT_BODY_PIN_COUNT + 1, "exceeds the safety limit"),
            (100, "requires at least"),
        )

        for count, expected in cases:
            with self.subTest(count=count):
                fixture = self.write_fixture(
                    f"pin_count_{count}.pmx",
                    build_pmx_structure(
                        version=2.1,
                        soft_bodies=(
                            build_pmx_soft_body(
                                pinned_vertex_count_override=count,
                            ),
                        ),
                    ),
                )

                result = scan_pmx_structure(fixture)
                self.assertEqual(result.status, "error")
                self.assertTrue(
                    any(
                        "pinned-vertex count" in error and expected in error
                        for error in result.errors
                    )
                )

    def test_rejects_invalid_anchor_references_and_near_mode(self) -> None:
        cases = (
            (
                build_pmx_soft_body_anchor(rigid_body_index=-1),
                "index -1 is invalid",
            ),
            (
                build_pmx_soft_body_anchor(rigid_body_index=1),
                "index 1 is invalid",
            ),
            (
                build_pmx_soft_body_anchor(vertex_index=1),
                "index 1 is invalid",
            ),
            (
                build_pmx_soft_body_anchor(near_mode=2),
                "near-mode flag 2",
            ),
        )

        for anchor, expected in cases:
            with self.subTest(expected=expected):
                fixture = self.write_fixture(
                    f"invalid_anchor_{len(expected)}.pmx",
                    build_pmx_structure(
                        version=2.1,
                        rigid_bodies=(build_pmx_rigid_body(),),
                        soft_bodies=(build_pmx_soft_body(anchors=(anchor,)),),
                    ),
                )

                result = scan_pmx_structure(fixture)
                self.assertEqual(result.status, "error")
                self.assertTrue(
                    any(
                        "soft_bodies[0].anchors[0]" in error and expected in error
                        for error in result.errors
                    )
                )

    def test_rejects_out_of_range_pinned_vertex(self) -> None:
        fixture = self.write_fixture(
            "invalid_pinned_vertex.pmx",
            build_pmx_structure(
                version=2.1,
                soft_bodies=(build_pmx_soft_body(pinned_vertex_indices=(1,)),),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "soft_bodies[0].pinned_vertices[0]" in error
                and "index 1 is invalid" in error
                for error in result.errors
            )
        )

    def test_preserves_duplicate_anchors_and_pins(self) -> None:
        anchor = build_pmx_soft_body_anchor()
        fixture = self.write_fixture(
            "duplicate_soft_body_references.pmx",
            build_pmx_structure(
                version=2.1,
                rigid_bodies=(build_pmx_rigid_body(),),
                soft_bodies=(
                    build_pmx_soft_body(
                        anchors=(anchor, anchor),
                        pinned_vertex_indices=(0, 0),
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(len(result.soft_bodies[0].anchors), 2)
        self.assertEqual(result.soft_bodies[0].pinned_vertex_indices, (0, 0))

    def test_rejects_total_anchor_and_pin_budget_overflow(self) -> None:
        anchor = build_pmx_soft_body_anchor()
        fixture = self.write_fixture(
            "soft_body_total_budgets.pmx",
            build_pmx_structure(
                version=2.1,
                rigid_bodies=(build_pmx_rigid_body(),),
                soft_bodies=(
                    build_pmx_soft_body(
                        anchors=(anchor,),
                        pinned_vertex_indices=(0,),
                    ),
                    build_pmx_soft_body(
                        anchors=(anchor,),
                        pinned_vertex_indices=(0,),
                    ),
                ),
            ),
        )

        with patch.object(
            model_scanning,
            "MAX_PMX_TOTAL_SOFT_BODY_ANCHOR_COUNT",
            1,
        ):
            anchor_result = scan_pmx_structure(fixture)
        self.assertEqual(anchor_result.status, "error")
        self.assertTrue(
            any("2 total anchors" in error for error in anchor_result.errors)
        )

        with patch.object(
            model_scanning,
            "MAX_PMX_TOTAL_SOFT_BODY_PIN_COUNT",
            1,
        ):
            pin_result = scan_pmx_structure(fixture)
        self.assertEqual(pin_result.status, "error")
        self.assertTrue(
            any("2 total pinned vertices" in error for error in pin_result.errors)
        )

    def test_rejects_truncated_soft_body_record(self) -> None:
        fixture_data = build_pmx_structure(
            version=2.1,
            soft_bodies=(build_pmx_soft_body(pinned_vertex_indices=(0,)),),
        )
        fixture = self.write_fixture(
            "truncated_soft_body.pmx",
            fixture_data[:-1],
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "soft_bodies[0]" in error
                and "pinned-vertex count" in error
                and "requires at least" in error
                for error in result.errors
            )
        )

    def test_soft_body_result_is_json_serializable(self) -> None:
        fixture = self.write_fixture(
            "soft_body_json.pmx",
            build_pmx_structure(
                version=2.1,
                soft_bodies=(build_pmx_soft_body(shape=1),),
            ),
        )

        result = scan_pmx_structure(fixture)
        encoded = json.dumps(result.to_dict(), ensure_ascii=False)
        decoded = json.loads(encoded)

        self.assertEqual(decoded["soft_body_count"], 1)
        self.assertEqual(decoded["soft_bodies"][0]["shape_name"], "rope")
        self.assertEqual(decoded["soft_bodies"][0]["anchor_count"], 0)
        self.assertEqual(decoded["soft_bodies"][0]["pinned_vertex_count"], 0)


if __name__ == "__main__":
    unittest.main()
