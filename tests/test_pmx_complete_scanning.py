"""Tests for finalized complete-file PMX structural scan results."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from mmd_registry.model_scanning import (
    scan_pmx_header,
    scan_pmx_structure,
)
from tests.mmd_fixtures import (
    build_pmx_bone,
    build_pmx_display_frame,
    build_pmx_display_frame_element,
    build_pmx_ik_link,
    build_pmx_joint,
    build_pmx_material,
    build_pmx_morph,
    build_pmx_rigid_body,
    build_pmx_soft_body,
    build_pmx_soft_body_anchor,
    build_pmx_structure,
    build_pmx_vertex_morph_offset,
)


class PmxCompleteScanningTests(unittest.TestCase):
    """Tests for complete byte accounting and aggregate summaries."""

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

    def build_populated_pmx21(self, *, trailing_bytes: bytes = b"") -> bytes:
        """Build one valid PMX 2.1 fixture with every main section used."""

        materials = (
            build_pmx_material(
                local_name="Primary",
                texture_index=0,
                sphere_texture_index=1,
                sphere_mode=1,
                toon_reference_mode=0,
                toon_reference_index=2,
                surface_index_count=3,
            ),
            build_pmx_material(
                local_name="Secondary",
                texture_index=0,
                sphere_texture_index=-1,
                toon_reference_mode=1,
                toon_reference_index=5,
                surface_index_count=0,
            ),
        )
        bones = (
            build_pmx_bone(local_name="Root"),
            build_pmx_bone(
                local_name="IK",
                ik_target_bone_index=0,
                ik_links=(build_pmx_ik_link(bone_index=0),),
            ),
        )
        morphs = (
            build_pmx_morph(
                morph_type=1,
                offsets=(
                    build_pmx_vertex_morph_offset(vertex_index=0),
                    build_pmx_vertex_morph_offset(vertex_index=1),
                ),
            ),
        )
        display_frames = (
            build_pmx_display_frame(
                elements=(
                    build_pmx_display_frame_element(
                        target_type=0,
                        target_index=0,
                    ),
                    build_pmx_display_frame_element(
                        target_type=1,
                        target_index=0,
                    ),
                ),
            ),
        )
        rigid_bodies = (build_pmx_rigid_body(bone_index=0),)
        joints = (
            build_pmx_joint(
                rigid_body_a_index=0,
                rigid_body_b_index=-1,
            ),
        )
        anchors = (
            build_pmx_soft_body_anchor(
                rigid_body_index=0,
                vertex_index=0,
                near_mode=1,
            ),
        )
        soft_bodies = (
            build_pmx_soft_body(
                material_index=0,
                anchors=anchors,
                pinned_vertex_indices=(0, 1),
            ),
        )

        return build_pmx_structure(
            version=2.1,
            deform_types=(0, 0),
            surface_indices=(0, 1, 0),
            texture_paths=(
                "textures/diffuse.png",
                "textures/sphere.spa",
                "textures/toon.bmp",
                "textures/unused.png",
            ),
            materials=materials,
            bones=bones,
            morphs=morphs,
            display_frames=display_frames,
            rigid_bodies=rigid_bodies,
            joints=joints,
            soft_bodies=soft_bodies,
            trailing_bytes=trailing_bytes,
        )

    def test_finalizes_complete_pmx_2_0_scan(self) -> None:
        fixture_data = build_pmx_structure(version=2.0)
        fixture = self.write_fixture("complete20.pmx", fixture_data)

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertTrue(result.scan_complete)
        self.assertEqual(result.file_size, len(fixture_data))
        self.assertEqual(result.bytes_consumed, len(fixture_data))
        self.assertEqual(result.bytes_remaining, 0)
        self.assertEqual(result.trailing_byte_count, 0)
        self.assertIsNotNone(result.section_summary)
        self.assertIsNotNone(result.dependency_summary)

    def test_finalizes_complete_pmx_2_1_scan(self) -> None:
        fixture_data = self.build_populated_pmx21()
        fixture = self.write_fixture("complete21.pmx", fixture_data)

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertTrue(result.scan_complete)
        self.assertEqual(result.bytes_consumed, len(fixture_data))
        self.assertEqual(result.bytes_remaining, 0)
        self.assertEqual(result.trailing_byte_count, 0)

    def test_reports_trailing_bytes_as_warning(self) -> None:
        trailer = b"EXTRA\x00DATA"
        fixture_data = self.build_populated_pmx21(trailing_bytes=trailer)
        fixture = self.write_fixture("trailing.pmx", fixture_data)

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "warning")
        self.assertTrue(result.scan_complete)
        self.assertEqual(result.trailing_byte_count, len(trailer))
        self.assertEqual(result.bytes_remaining, len(trailer))
        self.assertEqual(
            result.bytes_consumed,
            len(fixture_data) - len(trailer),
        )
        self.assertTrue(
            any(
                f"{len(trailer)} trailing byte(s)" in warning
                for warning in result.warnings
            )
        )

    def test_section_summary_aggregates_all_sections(self) -> None:
        fixture = self.write_fixture(
            "summary.pmx",
            self.build_populated_pmx21(),
        )

        result = scan_pmx_structure(fixture)
        summary = result.section_summary

        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertEqual(summary.vertex_count, 2)
        self.assertEqual(summary.surface_index_count, 3)
        self.assertEqual(summary.triangle_count, 1)
        self.assertEqual(summary.texture_count, 4)
        self.assertEqual(summary.material_count, 2)
        self.assertEqual(summary.bone_count, 2)
        self.assertEqual(summary.ik_count, 1)
        self.assertEqual(summary.ik_link_count, 1)
        self.assertEqual(summary.morph_count, 1)
        self.assertEqual(summary.morph_offset_count, 2)
        self.assertEqual(summary.display_frame_count, 1)
        self.assertEqual(summary.display_frame_element_count, 2)
        self.assertEqual(summary.rigid_body_count, 1)
        self.assertEqual(summary.joint_count, 1)
        self.assertEqual(summary.soft_body_count, 1)
        self.assertEqual(summary.soft_body_anchor_count, 1)
        self.assertEqual(summary.pinned_vertex_count, 2)

    def test_dependency_summary_collects_texture_references(self) -> None:
        fixture = self.write_fixture(
            "dependencies.pmx",
            self.build_populated_pmx21(),
        )

        result = scan_pmx_structure(fixture)
        summary = result.dependency_summary

        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertEqual(summary.declared_texture_path_count, 4)
        self.assertEqual(summary.material_texture_reference_count, 2)
        self.assertEqual(summary.sphere_texture_reference_count, 1)
        self.assertEqual(summary.toon_texture_reference_count, 1)
        self.assertEqual(summary.total_texture_reference_count, 4)
        self.assertEqual(summary.referenced_texture_indices, (0, 1, 2))
        self.assertEqual(
            summary.referenced_texture_paths,
            (
                "textures/diffuse.png",
                "textures/sphere.spa",
                "textures/toon.bmp",
            ),
        )
        self.assertEqual(summary.unreferenced_texture_indices, (3,))
        self.assertEqual(
            summary.unreferenced_texture_paths,
            ("textures/unused.png",),
        )

    def test_dependency_summary_handles_zero_textures(self) -> None:
        fixture = self.write_fixture(
            "no_textures.pmx",
            build_pmx_structure(version=2.1),
        )

        result = scan_pmx_structure(fixture)
        summary = result.dependency_summary

        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertEqual(summary.declared_texture_path_count, 0)
        self.assertEqual(summary.total_texture_reference_count, 0)
        self.assertEqual(summary.referenced_texture_indices, ())
        self.assertEqual(summary.unreferenced_texture_indices, ())

    def test_header_only_scan_is_not_complete(self) -> None:
        fixture_data = self.build_populated_pmx21()
        fixture = self.write_fixture("header_only.pmx", fixture_data)

        result = scan_pmx_header(fixture)

        self.assertEqual(result.status, "ok")
        self.assertFalse(result.scan_complete)
        self.assertIsNone(result.trailing_byte_count)
        self.assertIsNone(result.section_summary)
        self.assertIsNone(result.dependency_summary)
        self.assertGreater(result.bytes_remaining or 0, 0)

    def test_malformed_scan_does_not_claim_completion(self) -> None:
        fixture_data = build_pmx_structure(version=2.1)[:-1]
        fixture = self.write_fixture("truncated.pmx", fixture_data)

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertFalse(result.scan_complete)
        self.assertIsNone(result.trailing_byte_count)
        self.assertIsNone(result.section_summary)
        self.assertIsNone(result.dependency_summary)

    def test_missing_file_has_unknown_remaining_bytes(self) -> None:
        result = scan_pmx_structure(self.project_root / "missing.pmx")

        self.assertEqual(result.status, "error")
        self.assertIsNone(result.file_size)
        self.assertIsNone(result.bytes_remaining)
        self.assertFalse(result.scan_complete)

    def test_complete_result_is_json_serializable(self) -> None:
        fixture = self.write_fixture(
            "serializable.pmx",
            self.build_populated_pmx21(),
        )

        payload = scan_pmx_structure(fixture).to_dict()
        encoded = json.dumps(payload, ensure_ascii=False)

        self.assertIn('"scan_complete": true', encoded)
        self.assertEqual(payload["bytes_remaining"], 0)
        self.assertEqual(payload["trailing_byte_count"], 0)
        self.assertEqual(payload["section_summary"]["vertex_count"], 2)
        self.assertEqual(
            payload["dependency_summary"]["referenced_texture_indices"],
            [0, 1, 2],
        )

    def test_trailing_warning_preserves_complete_summaries(self) -> None:
        fixture = self.write_fixture(
            "warning_summary.pmx",
            self.build_populated_pmx21(trailing_bytes=b"\xaa"),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "warning")
        self.assertIsNotNone(result.section_summary)
        self.assertIsNotNone(result.dependency_summary)
        self.assertEqual(result.section_summary.soft_body_count, 1)

    def test_duplicate_texture_slots_count_each_reference(self) -> None:
        fixture = self.write_fixture(
            "duplicate_references.pmx",
            build_pmx_structure(
                texture_paths=("same.png",),
                materials=(
                    build_pmx_material(
                        texture_index=0,
                        sphere_texture_index=0,
                        toon_reference_mode=0,
                        toon_reference_index=0,
                        surface_index_count=3,
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)
        summary = result.dependency_summary

        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertEqual(summary.total_texture_reference_count, 3)
        self.assertEqual(summary.referenced_texture_indices, (0,))
        self.assertEqual(summary.referenced_texture_paths, ("same.png",))


if __name__ == "__main__":
    unittest.main()
