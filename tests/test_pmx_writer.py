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
from tests.mmd_fixtures import (
    build_pmx_bone,
    build_pmx_bone_morph_offset,
    build_pmx_display_frame,
    build_pmx_display_frame_element,
    build_pmx_flip_morph_offset,
    build_pmx_group_morph_offset,
    build_pmx_ik_link,
    build_pmx_impulse_morph_offset,
    build_pmx_joint,
    build_pmx_material_morph_offset,
    build_pmx_morph,
    build_pmx_rigid_body,
    build_pmx_soft_body,
    build_pmx_soft_body_anchor,
    build_pmx_structure,
    build_pmx_uv_morph_offset,
    build_pmx_vertex_morph_offset,
)


def build_representative_pmx21() -> bytes:
    """Build one PMX 2.1 fixture exercising every writable section."""

    bones = (
        build_pmx_bone(local_name="Root"),
        build_pmx_bone(
            local_name="IK",
            parent_bone_index=0,
            tail_bone_index=0,
            inherit_rotation=True,
            inherit_translation=True,
            inherit_parent_bone_index=0,
            inherit_weight=0.25,
            fixed_axis=(1.0, 0.0, 0.0),
            local_axes=((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
            external_parent_key=7,
            ik_target_bone_index=0,
            ik_links=(build_pmx_ik_link(angle_limit_flag=1),),
        ),
    )
    morphs = (
        build_pmx_morph(
            local_name="Group",
            morph_type=0,
            offsets=(build_pmx_group_morph_offset(morph_index=1),),
        ),
        build_pmx_morph(
            local_name="Vertex",
            morph_type=1,
            offsets=(build_pmx_vertex_morph_offset(),),
        ),
        build_pmx_morph(
            local_name="Bone",
            morph_type=2,
            offsets=(build_pmx_bone_morph_offset(),),
        ),
        build_pmx_morph(
            local_name="UV1",
            morph_type=4,
            offsets=(build_pmx_uv_morph_offset(),),
        ),
        build_pmx_morph(
            local_name="Material",
            morph_type=8,
            offsets=(build_pmx_material_morph_offset(),),
        ),
        build_pmx_morph(
            local_name="Flip",
            morph_type=9,
            offsets=(build_pmx_flip_morph_offset(morph_index=1),),
        ),
        build_pmx_morph(
            local_name="Impulse",
            morph_type=10,
            offsets=(build_pmx_impulse_morph_offset(),),
        ),
    )
    display_frames = (
        build_pmx_display_frame(
            special_flag=1,
            elements=(
                build_pmx_display_frame_element(target_type=0),
                build_pmx_display_frame_element(target_type=1, target_index=1),
            ),
        ),
    )
    rigid_bodies = (build_pmx_rigid_body(bone_index=0),)
    joints = (
        build_pmx_joint(
            joint_type=5,
            rigid_body_a_index=0,
            rigid_body_b_index=0,
        ),
    )
    soft_bodies = (
        build_pmx_soft_body(
            material_index=0,
            anchors=(build_pmx_soft_body_anchor(),),
            pinned_vertex_indices=(1,),
        ),
    )

    return build_pmx_structure(
        version=2.1,
        additional_uv_count=1,
        deform_types=(0, 1, 2, 3, 4),
        surface_indices=(0, 1, 2),
        texture_paths=("textures/body.png",),
        bones=bones,
        morphs=morphs,
        display_frames=display_frames,
        rigid_bodies=rigid_bodies,
        joints=joints,
        soft_bodies=soft_bodies,
        trailing_bytes=b"extension-data",
    )


class PmxWriterTests(unittest.TestCase):
    """Validate deterministic and failure-safe complete PMX writing."""

    def test_loads_complete_document_and_preserves_trailing_data(self) -> None:
        document = load_pmx(io.BytesIO(build_representative_pmx21()))

        self.assertIsInstance(document, PmxDocument)
        self.assertEqual(len(document.vertices), 5)
        self.assertEqual(len(document.morphs), 7)
        self.assertEqual(len(document.soft_bodies), 1)
        self.assertEqual(document.trailing_data, b"extension-data")

    def test_serializes_representative_pmx21_deterministically(self) -> None:
        source = build_representative_pmx21()
        document = load_pmx(io.BytesIO(source))

        first = serialize_pmx(document)
        second = serialize_pmx(document)

        self.assertEqual(first, source)
        self.assertEqual(second, first)

    def test_serializes_minimal_pmx20(self) -> None:
        source = build_pmx_structure(bones=(build_pmx_bone(),))

        self.assertEqual(serialize_pmx(load_pmx(io.BytesIO(source))), source)

    def test_validation_rejects_cross_section_reference(self) -> None:
        document = load_pmx(io.BytesIO(build_representative_pmx21()))
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
        document = load_pmx(io.BytesIO(build_representative_pmx21()))
        invalid_geometry = replace(document.geometry, surface_indices=(9, 1, 2))
        invalid_document = replace(document, geometry=invalid_geometry)

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory, "invalid.pmx")

            with self.assertRaises(PmxValidationError):
                write_pmx(invalid_document, destination)

            self.assertFalse(destination.exists())

    def test_validation_rejects_negative_physics_value(self) -> None:
        document = load_pmx(io.BytesIO(build_representative_pmx21()))
        invalid_body = replace(document.rigid_bodies[0], mass=-1.0)

        with self.assertRaisesRegex(
            PmxValidationError,
            r"rigid_bodies\[0\]\.mass.*cannot be negative",
        ):
            serialize_pmx(replace(document, rigid_bodies=(invalid_body,)))

    def test_validation_rejects_nonfinite_float(self) -> None:
        document = load_pmx(io.BytesIO(build_representative_pmx21()))
        invalid_body = replace(document.rigid_bodies[0], mass=math.nan)

        with self.assertRaisesRegex(
            PmxValidationError,
            r"document\.rigid_bodies\[0\]\.mass.*must be finite",
        ):
            serialize_pmx(replace(document, rigid_bodies=(invalid_body,)))

    def test_validation_rejects_unencodable_text(self) -> None:
        document = load_pmx(io.BytesIO(build_representative_pmx21()))
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
        document = load_pmx(io.BytesIO(build_representative_pmx21()))
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
        document = load_pmx(io.BytesIO(build_representative_pmx21()))
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
        document = load_pmx(io.BytesIO(build_representative_pmx21()))
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
        document = load_pmx(io.BytesIO(build_representative_pmx21()))
        body = document.soft_bodies[0]
        invalid_anchor = replace(body.anchors[0], rigid_body_index=99)
        invalid_body = replace(body, anchors=(invalid_anchor,))

        with self.assertRaisesRegex(
            PmxValidationError,
            r"soft_bodies\[0\]\.anchors\[0\]\.rigid_body_index.*index 99",
        ):
            serialize_pmx(replace(document, soft_bodies=(invalid_body,)))

    def test_write_refuses_to_overwrite_by_default(self) -> None:
        source = build_representative_pmx21()
        document = load_pmx(io.BytesIO(source))

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory, "model.pmx")
            destination.write_bytes(b"existing")

            with self.assertRaises(FileExistsError):
                write_pmx(document, destination)

            self.assertEqual(destination.read_bytes(), b"existing")

    def test_explicit_overwrite_replaces_file(self) -> None:
        source = build_representative_pmx21()
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
