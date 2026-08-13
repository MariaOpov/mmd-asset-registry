"""Tests for the v0.8.4 generated PMX compatibility profile foundation."""

from __future__ import annotations

import io
import unittest
from dataclasses import FrozenInstanceError, replace

from mmd_registry.pmx import PmxQdef, load_pmx
from tests.pmx_compatibility_profiles import (
    PMX_COMPATIBILITY_PROFILES,
    PmxCompatibilityProfile,
    build_compatibility_fixture,
)


class PmxCompatibilityProfileFoundationTests(unittest.TestCase):
    """Validate immutable profile metadata and deterministic fixture building."""

    def test_manifest_has_stable_unique_profile_ids_and_dimensions(self) -> None:
        profile_ids = tuple(
            profile.profile_id for profile in PMX_COMPATIBILITY_PROFILES
        )
        dimension_keys = tuple(
            profile.dimension_key for profile in PMX_COMPATIBILITY_PROFILES
        )

        self.assertEqual(
            profile_ids,
            (
                "minimal-pmx20-utf16",
                "minimal-pmx20-utf8",
                "mixed-index-pmx21",
                "wide-index-pmx21-utf8",
                "additional-uv1-bdef1-pmx20-utf8",
                "additional-uv2-bdef1-pmx21-utf16",
                "additional-uv3-bdef1-pmx20-utf16",
                "unicode-bone-pmx21-utf16",
                "additional-uv4-qdef-pmx21",
            ),
        )
        self.assertEqual(len(profile_ids), len(set(profile_ids)))
        self.assertEqual(len(dimension_keys), len(set(dimension_keys)))

    def test_profile_metadata_is_immutable(self) -> None:
        profile = PMX_COMPATIBILITY_PROFILES[0]

        with self.assertRaises(FrozenInstanceError):
            profile.profile_id = "changed"  # type: ignore[misc]

    def test_invalid_profile_metadata_is_rejected(self) -> None:
        base_arguments: dict[str, object] = {
            "profile_id": "invalid-case",
            "version": 2.0,
            "encoding_flag": 1,
            "additional_uv_count": 0,
            "index_sizes": (1, 1, 1, 1, 1, 1),
            "fixture_kind": "empty",
            "capabilities": ("test",),
        }
        invalid_cases = (
            ("version", 2.2),
            ("encoding_flag", 2),
            ("additional_uv_count", 5),
            ("index_sizes", (1, 2)),
            ("index_sizes", (1, 1, 1, 1, 1, 3)),
            ("fixture_kind", "unknown"),
            ("capabilities", ()),
            ("capabilities", ("same", "same")),
        )

        for field_name, invalid_value in invalid_cases:
            with self.subTest(field_name=field_name, invalid_value=invalid_value):
                arguments = dict(base_arguments)
                arguments[field_name] = invalid_value
                with self.assertRaises((TypeError, ValueError)):
                    PmxCompatibilityProfile(**arguments)  # type: ignore[arg-type]

    def test_generated_bytes_are_deterministic_for_every_profile(self) -> None:
        for profile in PMX_COMPATIBILITY_PROFILES:
            with self.subTest(profile=profile.profile_id):
                first = build_compatibility_fixture(profile)
                second = build_compatibility_fixture(profile)

                self.assertEqual(second, first)
                self.assertTrue(first.startswith(b"PMX "))

    def test_generated_header_matches_declared_profile_dimensions(self) -> None:
        for profile in PMX_COMPATIBILITY_PROFILES:
            with self.subTest(profile=profile.profile_id):
                document = load_pmx(
                    io.BytesIO(build_compatibility_fixture(profile))
                )

                self.assertEqual(document.header.version, profile.version)
                self.assertEqual(document.header.encoding, profile.encoding)
                self.assertEqual(
                    document.header.additional_uv_count,
                    profile.additional_uv_count,
                )
                self.assertEqual(
                    tuple(document.header.index_sizes.to_dict().values()),
                    profile.index_sizes,
                )

    def test_empty_profiles_have_zero_count_sections(self) -> None:
        for profile in PMX_COMPATIBILITY_PROFILES:
            if profile.fixture_kind != "empty":
                continue

            with self.subTest(profile=profile.profile_id):
                document = load_pmx(
                    io.BytesIO(build_compatibility_fixture(profile))
                )

                self.assertEqual(document.vertices, ())
                self.assertEqual(document.surface_indices, ())
                self.assertEqual(document.texture_paths, ())
                self.assertEqual(document.materials, ())
                self.assertEqual(document.bones, ())
                self.assertEqual(document.morphs, ())
                self.assertEqual(document.display_frames, ())
                self.assertEqual(document.rigid_bodies, ())
                self.assertEqual(document.joints, ())
                self.assertEqual(document.soft_bodies, ())

    def test_vertex_profiles_preserve_declared_additional_uv_count(self) -> None:
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

                self.assertEqual(len(document.vertices), 1)
                self.assertEqual(
                    len(document.vertices[0].additional_uvs),
                    profile.additional_uv_count,
                )

    def test_unicode_bone_profile_preserves_text_and_offset_tail(self) -> None:
        profile = next(
            profile
            for profile in PMX_COMPATIBILITY_PROFILES
            if profile.profile_id == "unicode-bone-pmx21-utf16"
        )
        document = load_pmx(io.BytesIO(build_compatibility_fixture(profile)))

        self.assertEqual(len(document.bones), 1)
        self.assertEqual(document.bones[0].local_name, "センター")
        self.assertEqual(document.bones[0].universal_name, "Center")
        self.assertEqual(document.bones[0].tail_mode, "offset")
        self.assertEqual(document.bones[0].tail_offset, (0.0, 1.0, 0.0))

    def test_qdef_profile_preserves_additional_uv_shape(self) -> None:
        profile = next(
            profile
            for profile in PMX_COMPATIBILITY_PROFILES
            if profile.profile_id == "additional-uv4-qdef-pmx21"
        )
        document = load_pmx(io.BytesIO(build_compatibility_fixture(profile)))

        self.assertEqual(len(document.vertices), 1)
        self.assertIsInstance(document.vertices[0].deform, PmxQdef)
        self.assertEqual(len(document.vertices[0].additional_uvs), 4)
        self.assertEqual(len(document.bones), 1)

    def test_profile_replacement_still_runs_validation(self) -> None:
        profile = PMX_COMPATIBILITY_PROFILES[0]

        with self.assertRaisesRegex(ValueError, "version must be 2.0 or 2.1"):
            replace(profile, version=2.2)


if __name__ == "__main__":
    unittest.main()
