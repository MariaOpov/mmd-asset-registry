"""Tests for typed PMX bone and IK reading."""

from __future__ import annotations

import io
import unittest
from dataclasses import FrozenInstanceError, replace

from mmd_registry.binary_reader import BinaryParseError, BinaryReader
from mmd_registry.model_scanning import (
    PmxBone as LegacyPmxBone,
    PmxIk as LegacyPmxIk,
    PmxIkLink as LegacyPmxIkLink,
)
from mmd_registry.pmx import (
    PMX_BONE_FLAG_IK,
    PMX_BONE_FLAG_INHERIT_ROTATION,
    PMX_BONE_FLAG_LOCAL_AXES,
    PMX_BONE_FLAG_TAIL_INDEX,
    PmxBone,
    PmxHeader,
    PmxIk,
    PmxIkLink,
)
from mmd_registry.pmx.sections.bones import PmxBoneReadState, read_pmx_bones
from mmd_registry.pmx.sections.geometry import read_pmx_geometry
from mmd_registry.pmx.sections.header import read_pmx_header
from mmd_registry.pmx.sections.materials import read_pmx_materials
from mmd_registry.pmx.sections.textures import read_pmx_textures
from tests.mmd_fixtures import (
    build_pmx_bone,
    build_pmx_ik_link,
    build_pmx_structure,
)


def reader_at_bone_section(data: bytes) -> tuple[BinaryReader, PmxHeader]:
    """Return a reader and typed header positioned at the bone section."""

    reader = BinaryReader(
        io.BytesIO(data),
        format_name="PMX",
    )
    header = read_pmx_header(reader).header
    geometry = read_pmx_geometry(reader, header=header)
    texture_paths = read_pmx_textures(reader, header=header)
    read_pmx_materials(
        reader,
        header=header,
        texture_count=len(texture_paths),
        surface_index_count=len(geometry.surface_indices),
    )
    return reader, header


def read_bones(data: bytes) -> tuple[tuple[PmxBone, ...], int]:
    """Read generated PMX data through the bone section."""

    reader, header = reader_at_bone_section(data)
    bones = read_pmx_bones(
        reader,
        header=header,
    )
    return bones, reader.offset


class PmxBoneReaderTests(unittest.TestCase):
    """Validate complete immutable bone and IK records."""

    def test_reads_all_flag_controlled_fields_and_ik_limits(self) -> None:
        bones, _ = read_bones(
            build_pmx_structure(
                bones=(
                    build_pmx_bone(local_name="Target"),
                    build_pmx_bone(local_name="Link", parent_bone_index=0),
                    build_pmx_bone(
                        local_name="IK",
                        universal_name="IK EN",
                        position=(1.0, 2.0, 3.0),
                        parent_bone_index=0,
                        transform_layer=2,
                        tail_bone_index=1,
                        inherit_rotation=True,
                        inherit_parent_bone_index=0,
                        inherit_weight=0.75,
                        fixed_axis=(1.0, 0.0, 0.0),
                        local_axes=((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
                        external_parent_key=42,
                        ik_target_bone_index=0,
                        ik_loop_count=40,
                        ik_angle_limit=0.5,
                        ik_links=(
                            build_pmx_ik_link(
                                bone_index=1,
                                angle_limit_flag=1,
                                lower_limit=(-1.0, -0.5, -0.25),
                                upper_limit=(1.0, 0.5, 0.25),
                            ),
                        ),
                    ),
                ),
            )
        )

        bone = bones[2]
        self.assertEqual(bone.local_name, "IK")
        self.assertEqual(bone.universal_name, "IK EN")
        self.assertEqual(bone.position, (1.0, 2.0, 3.0))
        self.assertEqual(bone.parent_bone_index, 0)
        self.assertEqual(bone.transform_layer, 2)
        self.assertTrue(bone.flags & PMX_BONE_FLAG_TAIL_INDEX)
        self.assertTrue(bone.flags & PMX_BONE_FLAG_INHERIT_ROTATION)
        self.assertTrue(bone.flags & PMX_BONE_FLAG_LOCAL_AXES)
        self.assertTrue(bone.flags & PMX_BONE_FLAG_IK)
        self.assertEqual(bone.tail_mode, "bone")
        self.assertEqual(bone.tail_bone_index, 1)
        self.assertEqual(bone.inherit_parent_bone_index, 0)
        self.assertEqual(bone.inherit_weight, 0.75)
        self.assertEqual(bone.fixed_axis, (1.0, 0.0, 0.0))
        self.assertEqual(bone.local_axis_x, (1.0, 0.0, 0.0))
        self.assertEqual(bone.local_axis_z, (0.0, 0.0, 1.0))
        self.assertEqual(bone.external_parent_key, 42)
        self.assertIsNotNone(bone.ik)
        assert bone.ik is not None
        self.assertEqual(bone.ik.target_bone_index, 0)
        self.assertEqual(bone.ik.loop_count, 40)
        self.assertEqual(bone.ik.angle_limit, 0.5)
        self.assertEqual(len(bone.ik.links), 1)
        self.assertTrue(bone.ik.links[0].angle_limits_enabled)
        self.assertEqual(bone.ik.links[0].lower_limit, (-1.0, -0.5, -0.25))
        self.assertEqual(bone.ik.links[0].upper_limit, (1.0, 0.5, 0.25))

    def test_supports_utf16_and_all_bone_index_sizes(self) -> None:
        for bone_index_size in (1, 2, 4):
            with self.subTest(bone_index_size=bone_index_size):
                bones, _ = read_bones(
                    build_pmx_structure(
                        encoding_flag=0,
                        bone_index_size=bone_index_size,
                        bones=(
                            build_pmx_bone(
                                local_name="センター",
                                universal_name="Center",
                                encoding_flag=0,
                                bone_index_size=bone_index_size,
                            ),
                        ),
                    )
                )

                self.assertEqual(bones[0].local_name, "センター")
                self.assertEqual(bones[0].universal_name, "Center")
                self.assertEqual(bones[0].parent_bone_index, -1)

    def test_reads_empty_bone_section(self) -> None:
        bones, _ = read_bones(build_pmx_structure(bones=()))
        self.assertEqual(bones, ())

    def test_read_state_preserves_count_after_record_error(self) -> None:
        reader, header = reader_at_bone_section(
            build_pmx_structure(
                bones=(
                    build_pmx_bone(parent_bone_index=2),
                ),
            )
        )
        state = PmxBoneReadState()

        with self.assertRaisesRegex(BinaryParseError, "parent bone index"):
            read_pmx_bones(
                reader,
                header=header,
                state=state,
            )

        self.assertEqual(state.bone_count, 1)
        self.assertEqual(state.bones, ())

    def test_records_are_immutable_and_validate_structural_types(self) -> None:
        bones, _ = read_bones(build_pmx_structure(bones=(build_pmx_bone(),)))
        bone = bones[0]

        with self.assertRaises(FrozenInstanceError):
            bone.local_name = "changed"  # type: ignore[misc]

        with self.assertRaisesRegex(ValueError, "exactly 3 values"):
            replace(bone, position=(0.0, 0.0))  # type: ignore[arg-type]

        with self.assertRaisesRegex(ValueError, "require lower and upper"):
            PmxIkLink(
                bone_index=0,
                angle_limits_enabled=True,
                lower_limit=None,
                upper_limit=None,
            )

    def test_preserves_legacy_type_and_diagnostic_inconsistent_states(self) -> None:
        self.assertIs(PmxBone, LegacyPmxBone)
        self.assertIs(PmxIk, LegacyPmxIk)
        self.assertIs(PmxIkLink, LegacyPmxIkLink)

        ik = PmxIk(
            target_bone_index=99,
            loop_count=1,
            angle_limit=0.5,
            links=(),
        )
        diagnostic_bone = PmxBone(
            local_name="Diagnostic",
            universal_name="",
            position=(0.0, 0.0, 0.0),
            parent_bone_index=-1,
            transform_layer=0,
            flags=0,
            flag_names=("ik",),
            tail_mode="offset",
            tail_bone_index=None,
            tail_offset=(0.0, 1.0, 0.0),
            inherit_parent_bone_index=None,
            inherit_weight=None,
            fixed_axis=None,
            local_axis_x=None,
            local_axis_z=None,
            external_parent_key=None,
            ik=ik,
        )

        self.assertIs(diagnostic_bone.ik, ik)
        self.assertEqual(diagnostic_bone.flags, 0)
        self.assertEqual(diagnostic_bone.flag_names, ("ik",))
        self.assertEqual(diagnostic_bone.to_dict()["ik"]["target_bone_index"], 99)


if __name__ == "__main__":
    unittest.main()
