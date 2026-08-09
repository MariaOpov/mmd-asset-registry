"""Generated semantic and byte-stability round-trip tests for complete PMX."""

from __future__ import annotations

import io
import itertools
import unittest

from mmd_registry.pmx import PmxDocument, load_pmx, serialize_pmx
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


class PmxGeneratedRoundTripTests(unittest.TestCase):
    """Exercise complete PMX payloads across the supported header matrix."""

    def assert_stable_roundtrip(self, source: bytes) -> PmxDocument:
        """Require parse/serialize/parse semantic and deterministic stability."""

        first_document = load_pmx(io.BytesIO(source))
        first_output = serialize_pmx(first_document)
        second_document = load_pmx(io.BytesIO(first_output))
        second_output = serialize_pmx(second_document)

        self.assertEqual(second_document, first_document)
        self.assertEqual(second_output, first_output)
        self.assertEqual(first_output, source)
        return second_document

    def test_round_trips_version_encoding_and_index_matrix(self) -> None:
        encodings = {0: "utf-16-le", 1: "utf-8"}

        for version, encoding_flag, index_size in itertools.product(
            (2.0, 2.1),
            (0, 1),
            (1, 2, 4),
        ):
            with self.subTest(
                version=version,
                encoding=encodings[encoding_flag],
                index_size=index_size,
            ):
                document = self.assert_stable_roundtrip(
                    build_pmx_roundtrip_fixture(
                        version=version,
                        encoding_flag=encoding_flag,
                        index_size=index_size,
                    )
                )
                self.assertEqual(document.header.version, version)
                self.assertEqual(document.header.encoding, encodings[encoding_flag])
                self.assertEqual(
                    tuple(document.header.index_sizes.to_dict().values()),
                    (index_size,) * 6,
                )

    def test_pmx20_fixture_covers_all_20_payload_types(self) -> None:
        document = self.assert_stable_roundtrip(
            build_pmx_roundtrip_fixture(version=2.0)
        )

        self.assertEqual(
            [vertex.deform.deform_type for vertex in document.vertices],
            [0, 1, 2, 3],
        )
        self.assertEqual(
            [morph.morph_type for morph in document.morphs],
            list(range(9)),
        )
        self.assertEqual([joint.joint_type for joint in document.joints], [0])
        self.assertEqual(document.soft_bodies, ())

    def test_round_trips_mixed_index_widths(self) -> None:
        mixed_sizes = (1, 2, 4, 1, 2, 4)
        document = self.assert_stable_roundtrip(
            build_pmx_roundtrip_fixture(index_sizes=mixed_sizes)
        )

        self.assertEqual(
            tuple(document.header.index_sizes.to_dict().values()),
            mixed_sizes,
        )

    def test_pmx21_fixture_covers_all_21_payload_types(self) -> None:
        document = self.assert_stable_roundtrip(
            build_pmx_roundtrip_fixture(version=2.1)
        )

        self.assertEqual(
            [vertex.deform.deform_type for vertex in document.vertices],
            [0, 1, 2, 3, 4],
        )
        self.assertEqual(
            [morph.morph_type for morph in document.morphs],
            list(range(11)),
        )
        self.assertEqual(
            [joint.joint_type for joint in document.joints],
            list(range(6)),
        )
        self.assertEqual(len(document.soft_bodies), 1)

    def test_roundtrip_preserves_ordered_cross_section_data(self) -> None:
        document = self.assert_stable_roundtrip(
            build_pmx_roundtrip_fixture(encoding_flag=0)
        )

        self.assertEqual(document.header.encoding, "utf-16-le")
        self.assertEqual(
            document.texture_paths,
            (
                "テクスチャ/体.png",
                "textures/sphere.spa",
                "textures/toon.bmp",
            ),
        )
        self.assertEqual(
            [material.local_name for material in document.materials],
            ["材質", "補助材質"],
        )
        self.assertEqual(
            [bone.local_name for bone in document.bones],
            ["全ての親", "ＩＫ"],
        )
        self.assertEqual(
            [element.target_type for element in document.display_frames[0].elements],
            ["bone", "morph"],
        )
        self.assertEqual(
            [body.local_name for body in document.rigid_bodies],
            ["剛体A", "剛体B"],
        )
        self.assertEqual(document.trailing_data, b"roundtrip-extension")

    def test_fixture_builder_rejects_unsupported_header_values(self) -> None:
        invalid_arguments = (
            {"version": 2.2},
            {"encoding_flag": 2},
            {"index_size": 3},
            {"index_sizes": (1, 2)},
            {"index_sizes": (1, 2, 4, 1, 2, 3)},
        )

        for arguments in invalid_arguments:
            with self.subTest(arguments=arguments):
                with self.assertRaises(ValueError):
                    build_pmx_roundtrip_fixture(**arguments)


if __name__ == "__main__":
    unittest.main()
