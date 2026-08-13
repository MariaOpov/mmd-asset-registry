"""Writer/roundtrip compatibility matrix for generated PMX profiles."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
import struct
import tempfile
import unittest

from mmd_registry.pmx import load_pmx, serialize_pmx
from mmd_registry.pmx.roundtrip import roundtrip_pmx
from tests.mmd_fixtures import (
    build_pmx_bone,
    build_pmx_material,
    build_pmx_structure,
)
from tests.pmx_compatibility_profiles import (
    PMX_COMPATIBILITY_PROFILES,
    build_compatibility_fixture,
)


def _sha256_bytes(data: bytes) -> str:
    """Return the SHA-256 digest for immutable bytes."""

    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    """Return the SHA-256 digest for one generated test file."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _replace_pmx_version(data: bytes, raw_version: float) -> bytes:
    """Replace only the on-disk PMX float version field."""

    if not data.startswith(b"PMX "):
        raise ValueError("fixture must begin with the PMX signature.")
    return data[:4] + struct.pack("<f", raw_version) + data[8:]


class PmxCompatibilityWriterRoundTripMatrixTests(unittest.TestCase):
    """Require semantic and deterministic writer stability across profiles."""

    def test_every_profile_has_stable_parse_serialize_parse_semantics(self) -> None:
        for profile in PMX_COMPATIBILITY_PROFILES:
            with self.subTest(profile=profile.profile_id):
                source = build_compatibility_fixture(profile)
                first_document = load_pmx(io.BytesIO(source))
                first_output = serialize_pmx(first_document)
                second_document = load_pmx(io.BytesIO(first_output))
                second_output = serialize_pmx(second_document)

                self.assertEqual(second_document, first_document)
                self.assertEqual(second_output, first_output)
                self.assertEqual(
                    second_document.header.version,
                    profile.version,
                )
                self.assertEqual(
                    second_document.header.encoding,
                    profile.encoding,
                )
                self.assertEqual(
                    tuple(second_document.header.index_sizes.to_dict().values()),
                    profile.index_sizes,
                )

    def test_filesystem_roundtrip_keeps_source_unchanged_for_every_profile(self) -> None:
        for profile in PMX_COMPATIBILITY_PROFILES:
            with self.subTest(profile=profile.profile_id):
                source_bytes = build_compatibility_fixture(profile)
                source_document = load_pmx(io.BytesIO(source_bytes))
                expected_output = serialize_pmx(source_document)

                with tempfile.TemporaryDirectory() as temp_directory:
                    root = Path(temp_directory)
                    source_path = root / f"{profile.profile_id}-source.pmx"
                    output_path = root / f"{profile.profile_id}-output.pmx"
                    source_path.write_bytes(source_bytes)
                    source_sha256_before = _sha256_file(source_path)

                    result = roundtrip_pmx(source_path, output_path)

                    self.assertTrue(source_path.exists())
                    self.assertTrue(output_path.exists())
                    self.assertNotEqual(
                        source_path.resolve(),
                        output_path.resolve(),
                    )
                    self.assertEqual(
                        _sha256_file(source_path),
                        source_sha256_before,
                    )
                    self.assertEqual(source_path.read_bytes(), source_bytes)
                    self.assertEqual(output_path.read_bytes(), expected_output)
                    self.assertEqual(
                        load_pmx(output_path),
                        source_document,
                    )
                    self.assertEqual(
                        result.input_sha256,
                        source_sha256_before,
                    )
                    self.assertEqual(
                        result.output_sha256,
                        _sha256_bytes(expected_output),
                    )
                    self.assertTrue(result.to_dict()["semantic_equal"])
                    self.assertEqual(
                        dict(result.section_counts)["trailing_bytes"],
                        len(source_document.trailing_data),
                    )

    def test_writer_preserves_trailing_opaque_bytes_semantically(self) -> None:
        trailing_data = b"\x00compatibility-extension\xff"
        source = build_pmx_structure(
            version=2.1,
            deform_types=(),
            surface_indices=(),
            materials=(),
            trailing_bytes=trailing_data,
        )

        first_document = load_pmx(io.BytesIO(source))
        first_output = serialize_pmx(first_document)
        second_document = load_pmx(io.BytesIO(first_output))
        second_output = serialize_pmx(second_document)

        self.assertEqual(first_document.trailing_data, trailing_data)
        self.assertEqual(second_document, first_document)
        self.assertEqual(second_document.trailing_data, trailing_data)
        self.assertEqual(second_output, first_output)

    def test_writer_preserves_opaque_bone_and_material_flag_values(self) -> None:
        bone_flags = 0x0040
        material_flags = 0xA5
        bone = build_pmx_bone(
            local_name="OpaqueFlagBone",
            universal_name="OpaqueFlagBone",
            flags_override=bone_flags,
        )
        material = build_pmx_material(
            local_name="OpaqueMaterialFlags",
            universal_name="OpaqueMaterialFlags",
            drawing_flags=material_flags,
            surface_index_count=0,
        )
        source = build_pmx_structure(
            deform_types=(),
            surface_indices=(),
            materials=(material,),
            bones=(bone,),
        )

        first_document = load_pmx(io.BytesIO(source))
        output = serialize_pmx(first_document)
        second_document = load_pmx(io.BytesIO(output))

        self.assertEqual(second_document, first_document)
        self.assertEqual(second_document.bones[0].flags, bone_flags)
        self.assertEqual(second_document.bones[0].flag_names, ())
        self.assertEqual(
            second_document.materials[0].drawing_flags,
            material_flags,
        )

    def test_tolerated_raw_version_roundtrips_semantically_not_byte_identically(self) -> None:
        canonical_source = build_pmx_structure(
            version=2.0,
            deform_types=(),
            surface_indices=(),
            materials=(),
        )
        source_bytes = _replace_pmx_version(canonical_source, 2.00005)

        source_document = load_pmx(io.BytesIO(source_bytes))
        serialized = serialize_pmx(source_document)
        verified_document = load_pmx(io.BytesIO(serialized))

        self.assertEqual(source_document.header.version, 2.0)
        self.assertEqual(verified_document, source_document)
        self.assertNotEqual(serialized, source_bytes)
        self.assertEqual(serialize_pmx(verified_document), serialized)

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            source_path = root / "tolerated-version-source.pmx"
            output_path = root / "tolerated-version-output.pmx"
            source_path.write_bytes(source_bytes)
            source_sha256_before = _sha256_file(source_path)

            result = roundtrip_pmx(source_path, output_path)

            self.assertEqual(
                _sha256_file(source_path),
                source_sha256_before,
            )
            self.assertFalse(result.byte_identical)
            self.assertTrue(result.to_dict()["semantic_equal"])
            self.assertEqual(output_path.read_bytes(), serialized)
            self.assertEqual(load_pmx(output_path), source_document)


if __name__ == "__main__":
    unittest.main()
