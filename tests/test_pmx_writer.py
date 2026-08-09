"""Tests for complete PMX document loading, validation, and writing."""

from __future__ import annotations

import io
import math
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from mmd_registry.pmx import (
    PmxDocument,
    PmxValidationError,
    load_pmx,
    serialize_pmx,
    validate_pmx_document,
    write_pmx,
)
from tests.mmd_fixtures import build_pmx_bone, build_pmx_structure
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


class PmxWriterTests(unittest.TestCase):
    """Validate deterministic and failure-safe complete PMX writing."""

    def test_loads_complete_document_and_preserves_trailing_data(self) -> None:
        document = load_pmx(io.BytesIO(build_pmx_roundtrip_fixture()))

        self.assertIsInstance(document, PmxDocument)
        self.assertEqual(len(document.vertices), 5)
        self.assertEqual(len(document.morphs), 11)
        self.assertEqual(len(document.soft_bodies), 1)
        self.assertEqual(document.trailing_data, b"roundtrip-extension")

    def test_serializes_representative_pmx21_deterministically(self) -> None:
        source = build_pmx_roundtrip_fixture()
        document = load_pmx(io.BytesIO(source))

        first = serialize_pmx(document)
        second = serialize_pmx(document)

        self.assertEqual(first, source)
        self.assertEqual(second, first)

    def test_serializes_minimal_pmx20(self) -> None:
        source = build_pmx_structure(bones=(build_pmx_bone(),))

        self.assertEqual(serialize_pmx(load_pmx(io.BytesIO(source))), source)

    def test_validation_rejects_cross_section_reference(self) -> None:
        document = load_pmx(io.BytesIO(build_pmx_roundtrip_fixture()))
        invalid_geometry = replace(
            document.geometry,
            surface_indices=(len(document.vertices), 1, 2),
        )

        with self.assertRaisesRegex(
            PmxValidationError,
            r"surface_indices\[0\].*index 5 is invalid",
        ):
            validate_pmx_document(replace(document, geometry=invalid_geometry))

    def test_invalid_document_does_not_create_destination(self) -> None:
        document = load_pmx(io.BytesIO(build_pmx_roundtrip_fixture()))
        invalid_geometry = replace(document.geometry, surface_indices=(9, 1, 2))
        invalid_document = replace(document, geometry=invalid_geometry)

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory, "invalid.pmx")

            with self.assertRaises(PmxValidationError):
                write_pmx(invalid_document, destination)

            self.assertFalse(destination.exists())

    def test_validation_rejects_negative_physics_value(self) -> None:
        document = load_pmx(io.BytesIO(build_pmx_roundtrip_fixture()))
        invalid_body = replace(document.rigid_bodies[0], mass=-1.0)

        with self.assertRaisesRegex(
            PmxValidationError,
            r"rigid_bodies\[0\]\.mass.*cannot be negative",
        ):
            serialize_pmx(replace(document, rigid_bodies=(invalid_body,)))

    def test_validation_rejects_nonfinite_float(self) -> None:
        document = load_pmx(io.BytesIO(build_pmx_roundtrip_fixture()))
        invalid_body = replace(document.rigid_bodies[0], mass=math.nan)

        with self.assertRaisesRegex(
            PmxValidationError,
            r"document\.rigid_bodies\[0\]\.mass.*must be finite",
        ):
            serialize_pmx(replace(document, rigid_bodies=(invalid_body,)))

    def test_validation_rejects_unencodable_text(self) -> None:
        document = load_pmx(io.BytesIO(build_pmx_roundtrip_fixture()))
        invalid_info = replace(document.model_info, local_name="\ud800")

        with self.assertRaisesRegex(
            PmxValidationError,
            r"model_info\.local_name.*cannot be encoded as utf-8",
        ):
            serialize_pmx(replace(document, model_info=invalid_info))

    def test_validation_rejects_index_width_overflow(self) -> None:
        source = build_pmx_structure(
            bones=tuple(build_pmx_bone() for _ in range(129)),
        )
        document = load_pmx(io.BytesIO(source))

        with self.assertRaisesRegex(
            PmxValidationError,
            r"index_sizes\.bone.*1-byte index cannot address 129",
        ):
            serialize_pmx(document)

    def test_validation_rejects_invalid_ik_link(self) -> None:
        document = load_pmx(io.BytesIO(build_pmx_roundtrip_fixture()))
        ik = document.bones[1].ik
        assert ik is not None
        invalid_link = replace(ik.links[0], bone_index=99)
        invalid_ik = replace(ik, links=(invalid_link,))
        invalid_bone = replace(document.bones[1], ik=invalid_ik)

        with self.assertRaisesRegex(
            PmxValidationError,
            r"bones\[1\]\.ik\.links\[0\]\.bone_index.*index 99",
        ):
            serialize_pmx(
                replace(document, bones=(document.bones[0], invalid_bone))
            )

    def test_validation_rejects_negative_ik_loop_count(self) -> None:
        document = load_pmx(io.BytesIO(build_pmx_roundtrip_fixture()))
        ik = document.bones[1].ik
        assert ik is not None
        invalid_bone = replace(document.bones[1], ik=replace(ik, loop_count=-1))

        with self.assertRaisesRegex(
            PmxValidationError,
            r"bones\[1\]\.ik\.loop_count.*cannot be negative",
        ):
            serialize_pmx(
                replace(document, bones=(document.bones[0], invalid_bone))
            )

    def test_validation_rejects_invalid_morph_reference(self) -> None:
        document = load_pmx(io.BytesIO(build_pmx_roundtrip_fixture()))
        invalid_offset = replace(document.morphs[0].offsets[0], morph_index=99)
        invalid_morph = replace(document.morphs[0], offsets=(invalid_offset,))

        with self.assertRaisesRegex(
            PmxValidationError,
            r"morphs\[0\]\.offsets\[0\].*index 99",
        ):
            serialize_pmx(
                replace(document, morphs=(invalid_morph, *document.morphs[1:]))
            )

    def test_validation_rejects_invalid_soft_body_reference(self) -> None:
        document = load_pmx(io.BytesIO(build_pmx_roundtrip_fixture()))
        body = document.soft_bodies[0]
        invalid_anchor = replace(body.anchors[0], rigid_body_index=99)
        invalid_body = replace(body, anchors=(invalid_anchor,))

        with self.assertRaisesRegex(
            PmxValidationError,
            r"soft_bodies\[0\]\.anchors\[0\]\.rigid_body_index.*index 99",
        ):
            serialize_pmx(replace(document, soft_bodies=(invalid_body,)))

    def test_write_refuses_to_overwrite_by_default(self) -> None:
        source = build_pmx_roundtrip_fixture()
        document = load_pmx(io.BytesIO(source))

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory, "model.pmx")
            destination.write_bytes(b"existing")

            with self.assertRaises(FileExistsError):
                write_pmx(document, destination)

            self.assertEqual(destination.read_bytes(), b"existing")

    def test_explicit_overwrite_replaces_file(self) -> None:
        source = build_pmx_roundtrip_fixture()
        document = load_pmx(io.BytesIO(source))

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory, "model.pmx")
            destination.write_bytes(b"existing")

            result = write_pmx(document, destination, overwrite=True)

            self.assertEqual(result, destination)
            self.assertEqual(destination.read_bytes(), source)
            self.assertEqual(load_pmx(destination), document)


if __name__ == "__main__":
    unittest.main()
