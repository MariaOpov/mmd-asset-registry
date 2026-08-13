"""Reader/scanner compatibility matrix for generated PMX profiles."""

from __future__ import annotations

import io
from pathlib import Path
import tempfile
import unittest

from mmd_registry.model_scanning import scan_pmx_structure
from mmd_registry.pmx import PmxBdef1, PmxQdef, load_pmx
from tests.pmx_compatibility_profiles import (
    PMX_COMPATIBILITY_PROFILES,
    build_compatibility_fixture,
)


class PmxCompatibilityReaderScannerMatrixTests(unittest.TestCase):
    """Assert semantic compatibility facts through reader and scanner paths."""

    def _scan_profile(self, profile_id: str):
        profile = next(
            profile
            for profile in PMX_COMPATIBILITY_PROFILES
            if profile.profile_id == profile_id
        )
        data = build_compatibility_fixture(profile)

        with tempfile.TemporaryDirectory() as temp_directory:
            path = Path(temp_directory) / f"{profile.profile_id}.pmx"
            path.write_bytes(data)
            scan_result = scan_pmx_structure(path)

        return profile, data, scan_result

    def test_every_profile_reader_and_scanner_agree_on_header_dimensions(self) -> None:
        for profile in PMX_COMPATIBILITY_PROFILES:
            with self.subTest(profile=profile.profile_id):
                data = build_compatibility_fixture(profile)
                document = load_pmx(io.BytesIO(data))

                with tempfile.TemporaryDirectory() as temp_directory:
                    path = Path(temp_directory) / f"{profile.profile_id}.pmx"
                    path.write_bytes(data)
                    scan_result = scan_pmx_structure(path)

                self.assertEqual(scan_result.status, "ok")
                self.assertTrue(scan_result.scan_complete)
                self.assertEqual(scan_result.errors, [])
                self.assertEqual(scan_result.warnings, [])
                self.assertEqual(scan_result.version, document.header.version)
                self.assertEqual(scan_result.encoding, document.header.encoding)
                self.assertEqual(
                    scan_result.additional_uv_count,
                    document.header.additional_uv_count,
                )
                self.assertEqual(scan_result.index_sizes, document.header.index_sizes)
                self.assertEqual(scan_result.bytes_consumed, len(data))
                self.assertEqual(scan_result.bytes_remaining, 0)
                self.assertEqual(scan_result.trailing_byte_count, 0)

    def test_every_profile_reader_and_scanner_agree_on_section_counts(self) -> None:
        for profile in PMX_COMPATIBILITY_PROFILES:
            with self.subTest(profile=profile.profile_id):
                data = build_compatibility_fixture(profile)
                document = load_pmx(io.BytesIO(data))

                with tempfile.TemporaryDirectory() as temp_directory:
                    path = Path(temp_directory) / f"{profile.profile_id}.pmx"
                    path.write_bytes(data)
                    scan_result = scan_pmx_structure(path)

                expected_counts = {
                    "vertex_count": len(document.vertices),
                    "surface_index_count": len(document.surface_indices),
                    "texture_count": len(document.texture_paths),
                    "material_count": len(document.materials),
                    "bone_count": len(document.bones),
                    "morph_count": len(document.morphs),
                    "display_frame_count": len(document.display_frames),
                    "rigid_body_count": len(document.rigid_bodies),
                    "joint_count": len(document.joints),
                    "soft_body_count": len(document.soft_bodies),
                }

                for attribute, expected_count in expected_counts.items():
                    with self.subTest(
                        profile=profile.profile_id,
                        attribute=attribute,
                    ):
                        self.assertEqual(
                            getattr(scan_result, attribute),
                            expected_count,
                        )

                self.assertIsNotNone(scan_result.section_summary)
                summary = scan_result.section_summary
                assert summary is not None
                self.assertEqual(summary.vertex_count, len(document.vertices))
                self.assertEqual(
                    summary.surface_index_count,
                    len(document.surface_indices),
                )
                self.assertEqual(summary.texture_count, len(document.texture_paths))
                self.assertEqual(summary.material_count, len(document.materials))
                self.assertEqual(summary.bone_count, len(document.bones))
                self.assertEqual(summary.morph_count, len(document.morphs))
                self.assertEqual(
                    summary.display_frame_count,
                    len(document.display_frames),
                )
                self.assertEqual(
                    summary.rigid_body_count,
                    len(document.rigid_bodies),
                )
                self.assertEqual(summary.joint_count, len(document.joints))
                self.assertEqual(summary.soft_body_count, len(document.soft_bodies))

    def test_additional_uv_profiles_cover_every_declared_count(self) -> None:
        observed_counts: set[int] = set()

        for profile in PMX_COMPATIBILITY_PROFILES:
            if profile.additional_uv_count == 0:
                continue

            with self.subTest(profile=profile.profile_id):
                document = load_pmx(
                    io.BytesIO(build_compatibility_fixture(profile))
                )
                self.assertEqual(len(document.vertices), 1)
                self.assertEqual(
                    len(document.vertices[0].additional_uvs),
                    profile.additional_uv_count,
                )
                observed_counts.add(profile.additional_uv_count)

        self.assertEqual(observed_counts, {1, 2, 3, 4})

    def test_manifest_covers_uniform_and_mixed_index_widths(self) -> None:
        declared = {profile.index_sizes for profile in PMX_COMPATIBILITY_PROFILES}

        self.assertIn((1, 1, 1, 1, 1, 1), declared)
        self.assertIn((2, 2, 2, 2, 2, 2), declared)
        self.assertIn((4, 4, 4, 4, 4, 4), declared)
        self.assertTrue(
            any(len(set(index_sizes)) > 1 for index_sizes in declared),
            "expected at least one representative mixed-width profile",
        )

    def test_weighted_vertex_profiles_preserve_deform_semantics(self) -> None:
        for profile in PMX_COMPATIBILITY_PROFILES:
            if profile.fixture_kind not in {
                "bdef1_additional_uv",
                "qdef_additional_uv",
            }:
                continue

            with self.subTest(profile=profile.profile_id):
                document = load_pmx(
                    io.BytesIO(build_compatibility_fixture(profile))
                )
                deform = document.vertices[0].deform

                if profile.fixture_kind == "bdef1_additional_uv":
                    self.assertIsInstance(deform, PmxBdef1)
                    self.assertEqual(deform.bone_index, 0)
                else:
                    self.assertIsInstance(deform, PmxQdef)
                    self.assertEqual(deform.bone_indices, (0, 0, 0, 0))

    def test_unicode_bone_semantics_match_reader_and_scanner(self) -> None:
        profile, data, scan_result = self._scan_profile(
            "unicode-bone-pmx21-utf16"
        )
        document = load_pmx(io.BytesIO(data))

        self.assertEqual(scan_result.status, "ok")
        self.assertEqual(len(scan_result.bones), 1)
        self.assertEqual(scan_result.bones, list(document.bones))
        self.assertEqual(scan_result.bones[0].local_name, "センター")
        self.assertEqual(scan_result.bones[0].universal_name, "Center")
        self.assertEqual(scan_result.bones[0].tail_mode, "offset")
        self.assertIn("unicode-text", profile.capabilities)


if __name__ == "__main__":
    unittest.main()
