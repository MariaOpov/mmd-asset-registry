"""Compatibility-boundary evidence for generated PMX reader/scanner cases."""

from __future__ import annotations

import io
from pathlib import Path
import struct
import tempfile
import unittest

from mmd_registry.binary_reader import BinaryParseError
from mmd_registry.model_scanning import scan_pmx_structure
from mmd_registry.pmx import load_pmx
from tests.mmd_fixtures import (
    build_pmx_bone,
    build_pmx_material,
    build_pmx_structure,
)


def _replace_pmx_version(data: bytes, raw_version: float) -> bytes:
    """Replace only the on-disk PMX float version field."""

    if not data.startswith(b"PMX "):
        raise ValueError("fixture must begin with the PMX signature.")
    return data[:4] + struct.pack("<f", raw_version) + data[8:]


def _scan_bytes(data: bytes):
    """Scan generated PMX bytes through the filesystem-facing scanner API."""

    with tempfile.TemporaryDirectory() as temp_directory:
        path = Path(temp_directory) / "compatibility-boundary.pmx"
        path.write_bytes(data)
        return scan_pmx_structure(path)


class PmxCompatibilityBoundaryTests(unittest.TestCase):
    """Lock explicit compatibility behavior without changing parser policy."""

    def test_version_values_inside_current_tolerance_are_canonicalized(self) -> None:
        cases = (
            (2.0, 2.00005),
            (2.1, 2.10005),
        )

        for canonical_version, raw_version in cases:
            with self.subTest(
                canonical_version=canonical_version,
                raw_version=raw_version,
            ):
                base = build_pmx_structure(
                    version=canonical_version,
                    deform_types=(),
                    surface_indices=(),
                    materials=(),
                )
                data = _replace_pmx_version(base, raw_version)

                document = load_pmx(io.BytesIO(data))
                scan_result = _scan_bytes(data)

                self.assertEqual(document.header.version, canonical_version)
                self.assertEqual(scan_result.status, "ok")
                self.assertTrue(scan_result.scan_complete)
                self.assertEqual(scan_result.version, canonical_version)
                self.assertEqual(scan_result.errors, [])
                self.assertEqual(scan_result.warnings, [])

    def test_version_values_outside_current_tolerance_are_rejected(self) -> None:
        cases = (
            (2.0, 2.0002),
            (2.1, 2.1002),
        )

        for canonical_version, raw_version in cases:
            with self.subTest(
                canonical_version=canonical_version,
                raw_version=raw_version,
            ):
                base = build_pmx_structure(
                    version=canonical_version,
                    deform_types=(),
                    surface_indices=(),
                    materials=(),
                )
                data = _replace_pmx_version(base, raw_version)

                with self.assertRaisesRegex(
                    BinaryParseError,
                    "unsupported PMX version",
                ):
                    load_pmx(io.BytesIO(data))

                scan_result = _scan_bytes(data)
                self.assertEqual(scan_result.status, "error")
                self.assertFalse(scan_result.scan_complete)
                self.assertTrue(
                    any(
                        "unsupported PMX version" in message
                        for message in scan_result.errors
                    )
                )

    def test_unrecognized_bone_flag_bit_is_preserved_but_not_named(self) -> None:
        unknown_flag = 0x0040
        bone = build_pmx_bone(
            local_name="OpaqueFlagBone",
            universal_name="OpaqueFlagBone",
            flags_override=unknown_flag,
        )
        data = build_pmx_structure(
            deform_types=(),
            surface_indices=(),
            materials=(),
            bones=(bone,),
        )

        document = load_pmx(io.BytesIO(data))
        scan_result = _scan_bytes(data)

        self.assertEqual(len(document.bones), 1)
        self.assertEqual(document.bones[0].flags, unknown_flag)
        self.assertEqual(document.bones[0].flag_names, ())
        self.assertEqual(scan_result.status, "ok")
        self.assertEqual(scan_result.bones, list(document.bones))

    def test_material_drawing_flag_byte_is_preserved_opaquely(self) -> None:
        raw_drawing_flags = 0xA5
        material = build_pmx_material(
            local_name="OpaqueMaterialFlags",
            universal_name="OpaqueMaterialFlags",
            drawing_flags=raw_drawing_flags,
            surface_index_count=0,
        )
        data = build_pmx_structure(
            deform_types=(),
            surface_indices=(),
            materials=(material,),
        )

        document = load_pmx(io.BytesIO(data))
        scan_result = _scan_bytes(data)

        self.assertEqual(len(document.materials), 1)
        self.assertEqual(
            document.materials[0].drawing_flags,
            raw_drawing_flags,
        )
        self.assertEqual(scan_result.status, "ok")
        self.assertEqual(scan_result.materials, list(document.materials))

    def test_trailing_bytes_are_preserved_but_scanner_marks_warning(self) -> None:
        trailing_data = b"\xde\xad\xbe\xef"
        data = build_pmx_structure(
            version=2.1,
            deform_types=(),
            surface_indices=(),
            materials=(),
            trailing_bytes=trailing_data,
        )

        document = load_pmx(io.BytesIO(data))
        scan_result = _scan_bytes(data)

        self.assertEqual(document.trailing_data, trailing_data)
        self.assertEqual(scan_result.status, "warning")
        self.assertTrue(scan_result.scan_complete)
        self.assertEqual(scan_result.errors, [])
        self.assertEqual(scan_result.trailing_byte_count, len(trailing_data))
        self.assertEqual(scan_result.bytes_remaining, len(trailing_data))
        self.assertTrue(
            any(
                "trailing byte" in warning.lower()
                for warning in scan_result.warnings
            )
        )

    def test_clean_fixture_is_not_confused_with_trailing_byte_preservation(self) -> None:
        data = build_pmx_structure(
            version=2.1,
            deform_types=(),
            surface_indices=(),
            materials=(),
        )

        document = load_pmx(io.BytesIO(data))
        scan_result = _scan_bytes(data)

        self.assertEqual(document.trailing_data, b"")
        self.assertEqual(scan_result.status, "ok")
        self.assertTrue(scan_result.scan_complete)
        self.assertEqual(scan_result.trailing_byte_count, 0)
        self.assertEqual(scan_result.bytes_remaining, 0)
        self.assertEqual(scan_result.warnings, [])


if __name__ == "__main__":
    unittest.main()
