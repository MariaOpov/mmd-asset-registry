"""Tests for typed PMX geometry reading and document records."""

from __future__ import annotations

import io
import unittest
from dataclasses import FrozenInstanceError

from mmd_registry.binary_reader import BinaryParseError, BinaryReader
from mmd_registry.pmx import (
    PmxBdef1,
    PmxBdef2,
    PmxBdef4,
    PmxGeometry,
    PmxQdef,
    PmxSdef,
    PmxVertex,
)
from mmd_registry.pmx.sections.geometry import (
    PmxGeometryReadState,
    read_pmx_geometry,
)
from mmd_registry.pmx.sections.header import read_pmx_header
from tests.mmd_fixtures import build_pmx_structure


def read_geometry(data: bytes) -> tuple[PmxGeometry, int]:
    """Read generated PMX header and geometry sections."""

    stream = io.BytesIO(data)
    reader = BinaryReader(
        stream,
        format_name="PMX",
    )
    header_result = read_pmx_header(reader)
    geometry = read_pmx_geometry(
        reader,
        header=header_result.header,
    )
    return geometry, reader.offset


class PmxGeometryReaderTests(unittest.TestCase):
    """Validate byte-complete geometry records independently from scanning."""

    def test_reads_all_deforms_additional_uvs_and_surface_order(self) -> None:
        data = build_pmx_structure(
            version=2.1,
            deform_types=(0, 1, 2, 3, 4),
            surface_indices=(0, 1, 2, 2, 3, 4),
            additional_uv_count=2,
            bone_index_size=2,
            vertex_index_size=2,
        )

        geometry, _ = read_geometry(data)

        self.assertEqual(len(geometry.vertices), 5)
        self.assertIsInstance(geometry.vertices[0].deform, PmxBdef1)
        self.assertIsInstance(geometry.vertices[1].deform, PmxBdef2)
        self.assertIsInstance(geometry.vertices[2].deform, PmxBdef4)
        self.assertIsInstance(geometry.vertices[3].deform, PmxSdef)
        self.assertIsInstance(geometry.vertices[4].deform, PmxQdef)
        self.assertEqual(len(geometry.vertices[0].additional_uvs), 2)
        self.assertEqual(
            geometry.vertices[0].additional_uvs,
            ((0.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0)),
        )
        self.assertEqual(geometry.vertices[0].position, (0.0, 0.0, 0.0))
        self.assertEqual(geometry.vertices[0].normal, (0.0, 1.0, 0.0))
        self.assertEqual(geometry.vertices[0].uv, (0.0, 0.0))
        self.assertEqual(geometry.vertices[0].edge_scale, 1.0)
        self.assertEqual(geometry.surface_indices, (0, 1, 2, 2, 3, 4))
        self.assertEqual(geometry.triangle_count, 2)

    def test_preserves_deform_weights_and_sdef_vectors(self) -> None:
        geometry, _ = read_geometry(
            build_pmx_structure(
                version=2.1,
                deform_types=(1, 2, 3, 4),
                surface_indices=(),
            )
        )

        bdef2 = geometry.vertices[0].deform
        bdef4 = geometry.vertices[1].deform
        sdef = geometry.vertices[2].deform
        qdef = geometry.vertices[3].deform

        self.assertIsInstance(bdef2, PmxBdef2)
        self.assertEqual(bdef2.bone_indices, (0, 0))
        self.assertEqual(bdef2.bone_1_weight, 0.5)
        self.assertIsInstance(bdef4, PmxBdef4)
        self.assertEqual(bdef4.weights, (0.25, 0.25, 0.25, 0.25))
        self.assertIsInstance(sdef, PmxSdef)
        self.assertEqual(sdef.c, (0.0, 0.0, 0.0))
        self.assertEqual(sdef.r0, (0.0, 0.0, 0.0))
        self.assertEqual(sdef.r1, (0.0, 0.0, 0.0))
        self.assertIsInstance(qdef, PmxQdef)
        self.assertEqual(qdef.weights, (0.25, 0.25, 0.25, 0.25))

    def test_supports_all_declared_vertex_and_bone_index_sizes(self) -> None:
        for index_size in (1, 2, 4):
            with self.subTest(index_size=index_size):
                geometry, _ = read_geometry(
                    build_pmx_structure(
                        deform_types=(0,),
                        surface_indices=(0, 0, 0),
                        vertex_index_size=index_size,
                        bone_index_size=index_size,
                    )
                )

                self.assertEqual(geometry.surface_indices, (0, 0, 0))
                self.assertEqual(geometry.vertices[0].deform.bone_index, 0)

    def test_reads_empty_geometry(self) -> None:
        geometry, _ = read_geometry(
            build_pmx_structure(
                deform_types=(),
                surface_indices=(),
            )
        )

        self.assertEqual(geometry.vertices, ())
        self.assertEqual(geometry.surface_indices, ())
        self.assertEqual(geometry.triangle_count, 0)

    def test_rejects_qdef_for_pmx_2_0(self) -> None:
        with self.assertRaisesRegex(
            BinaryParseError,
            "QDEF deform type requires PMX 2.1",
        ):
            read_geometry(
                build_pmx_structure(
                    version=2.0,
                    deform_types=(4,),
                    surface_indices=(),
                )
            )

    def test_read_state_preserves_partial_counts_after_an_error(self) -> None:
        stream = io.BytesIO(
            build_pmx_structure(
                deform_types=(9,),
                surface_indices=(),
            )
        )
        reader = BinaryReader(
            stream,
            format_name="PMX",
        )
        header_result = read_pmx_header(reader)
        state = PmxGeometryReadState()

        with self.assertRaises(BinaryParseError):
            read_pmx_geometry(
                reader,
                header=header_result.header,
                state=state,
            )

        self.assertEqual(state.vertex_count, 1)
        self.assertIsNone(state.surface_index_count)
        self.assertIsNone(state.triangle_count)

    def test_geometry_records_are_immutable_and_validate_structure(self) -> None:
        geometry, _ = read_geometry(build_pmx_structure())

        with self.assertRaises(FrozenInstanceError):
            geometry.vertices = ()  # type: ignore[misc]

        with self.assertRaises(FrozenInstanceError):
            geometry.vertices[0].edge_scale = 2.0  # type: ignore[misc]

        with self.assertRaisesRegex(ValueError, "divisible by 3"):
            PmxGeometry(
                vertices=(),
                surface_indices=(0,),
            )

        with self.assertRaisesRegex(ValueError, "cannot be negative"):
            PmxGeometry(
                vertices=(),
                surface_indices=(-1, -1, -1),
            )

        with self.assertRaisesRegex(ValueError, "exactly 3 values"):
            PmxVertex(
                position=(0.0, 0.0),  # type: ignore[arg-type]
                normal=(0.0, 1.0, 0.0),
                uv=(0.0, 0.0),
                additional_uvs=(),
                deform=PmxBdef1(bone_index=0),
                edge_scale=1.0,
            )


if __name__ == "__main__":
    unittest.main()
