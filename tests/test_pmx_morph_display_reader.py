"""Tests for typed PMX morph and display-frame reading."""

from __future__ import annotations

import io
import unittest
from dataclasses import FrozenInstanceError, replace

from mmd_registry.binary_reader import BinaryParseError, BinaryReader
from mmd_registry.model_scanning import (
    PmxDisplayFrame as LegacyPmxDisplayFrame,
    PmxDisplayFrameElement as LegacyPmxDisplayFrameElement,
    PmxMorph as LegacyPmxMorph,
)
from mmd_registry.pmx import (
    PmxBoneMorphOffset,
    PmxDisplayFrame,
    PmxDisplayFrameElement,
    PmxFlipMorphOffset,
    PmxGroupMorphOffset,
    PmxHeader,
    PmxImpulseMorphOffset,
    PmxMaterialMorphOffset,
    PmxMorph,
    PmxUvMorphOffset,
    PmxVertexMorphOffset,
)
from mmd_registry.pmx.sections.bones import read_pmx_bones
from mmd_registry.pmx.sections.display_frames import (
    PmxDisplayFrameReadState,
    read_pmx_display_frames,
)
from mmd_registry.pmx.sections.geometry import read_pmx_geometry
from mmd_registry.pmx.sections.header import read_pmx_header
from mmd_registry.pmx.sections.materials import read_pmx_materials
from mmd_registry.pmx.sections.morphs import (
    PmxMorphReadState,
    read_pmx_morphs,
)
from mmd_registry.pmx.sections.textures import read_pmx_textures
from tests.mmd_fixtures import (
    build_pmx_bone,
    build_pmx_bone_morph_offset,
    build_pmx_display_frame,
    build_pmx_display_frame_element,
    build_pmx_flip_morph_offset,
    build_pmx_group_morph_offset,
    build_pmx_impulse_morph_offset,
    build_pmx_material_morph_offset,
    build_pmx_morph,
    build_pmx_structure,
    build_pmx_uv_morph_offset,
    build_pmx_vertex_morph_offset,
)


def reader_at_morph_section(
    data: bytes,
) -> tuple[BinaryReader, PmxHeader, int, int, int]:
    """Return a reader and dependencies positioned at the morph section."""

    reader = BinaryReader(io.BytesIO(data), format_name="PMX")
    header = read_pmx_header(reader).header
    geometry = read_pmx_geometry(reader, header=header)
    texture_paths = read_pmx_textures(reader, header=header)
    materials = read_pmx_materials(
        reader,
        header=header,
        texture_count=len(texture_paths),
        surface_index_count=len(geometry.surface_indices),
    )
    bones = read_pmx_bones(reader, header=header)
    return reader, header, len(geometry.vertices), len(bones), len(materials)


def read_morphs(
    reader: BinaryReader,
    *,
    header: PmxHeader,
    vertex_count: int,
    bone_count: int,
    material_count: int,
) -> tuple[PmxMorph, ...]:
    """Read the morph section with its prior-section counts."""

    return read_pmx_morphs(
        reader,
        header=header,
        vertex_count=vertex_count,
        bone_count=bone_count,
        material_count=material_count,
    )


class PmxMorphDisplayReaderTests(unittest.TestCase):
    """Validate complete immutable morph and display-frame records."""

    def test_reads_every_morph_offset_type(self) -> None:
        morphs = (
            build_pmx_morph(
                morph_type=0,
                offsets=(build_pmx_group_morph_offset(morph_index=1, weight=0.5),),
            ),
            build_pmx_morph(
                morph_type=1,
                offsets=(
                    build_pmx_vertex_morph_offset(
                        translation=(1.0, 2.0, 3.0),
                    ),
                ),
            ),
            build_pmx_morph(
                morph_type=2,
                offsets=(
                    build_pmx_bone_morph_offset(
                        translation=(4.0, 5.0, 6.0),
                        rotation=(0.0, 0.0, 0.5, 1.0),
                    ),
                ),
            ),
            build_pmx_morph(
                morph_type=4,
                offsets=(
                    build_pmx_uv_morph_offset(
                        uv_offset=(0.1, 0.2, 0.3, 0.4),
                    ),
                ),
            ),
            build_pmx_morph(
                morph_type=8,
                offsets=(
                    build_pmx_material_morph_offset(
                        operation=1,
                        diffuse=(0.1, 0.2, 0.3, 0.4),
                        edge_scale=2.0,
                    ),
                ),
            ),
            build_pmx_morph(
                morph_type=9,
                offsets=(build_pmx_flip_morph_offset(morph_index=0, weight=0.75),),
            ),
            build_pmx_morph(
                morph_type=10,
                offsets=(
                    build_pmx_impulse_morph_offset(
                        local_flag=1,
                        velocity=(7.0, 8.0, 9.0),
                        angular_torque=(10.0, 11.0, 12.0),
                    ),
                ),
            ),
        )
        reader, header, vertex_count, bone_count, material_count = (
            reader_at_morph_section(
                build_pmx_structure(
                    version=2.1,
                    additional_uv_count=1,
                    bones=(build_pmx_bone(),),
                    morphs=morphs,
                )
            )
        )

        records = read_morphs(
            reader,
            header=header,
            vertex_count=vertex_count,
            bone_count=bone_count,
            material_count=material_count,
        )

        expected_types = (
            PmxGroupMorphOffset,
            PmxVertexMorphOffset,
            PmxBoneMorphOffset,
            PmxUvMorphOffset,
            PmxMaterialMorphOffset,
            PmxFlipMorphOffset,
            PmxImpulseMorphOffset,
        )
        self.assertEqual(len(records), len(expected_types))
        for morph, expected_type in zip(records, expected_types):
            self.assertIsInstance(morph.offsets[0], expected_type)

        self.assertEqual(records[1].offsets[0].translation, (1.0, 2.0, 3.0))
        self.assertEqual(records[2].offsets[0].rotation, (0.0, 0.0, 0.5, 1.0))
        self.assertEqual(records[4].offsets[0].operation, "add")
        impulse = records[6].offsets[0]
        self.assertTrue(impulse.local)
        self.assertEqual(impulse.velocity, (7.0, 8.0, 9.0))
        self.assertEqual(impulse.angular_torque, (10.0, 11.0, 12.0))

    def test_reads_utf16_names_and_all_morph_index_sizes(self) -> None:
        for morph_index_size in (1, 2, 4):
            with self.subTest(morph_index_size=morph_index_size):
                reader, header, vertex_count, bone_count, material_count = (
                    reader_at_morph_section(
                        build_pmx_structure(
                            encoding_flag=0,
                            morph_index_size=morph_index_size,
                            morphs=(
                                build_pmx_morph(
                                    local_name="笑顔",
                                    universal_name="Smile",
                                    encoding_flag=0,
                                ),
                            ),
                        )
                    )
                )
                records = read_morphs(
                    reader,
                    header=header,
                    vertex_count=vertex_count,
                    bone_count=bone_count,
                    material_count=material_count,
                )

                self.assertEqual(records[0].local_name, "笑顔")
                self.assertEqual(records[0].universal_name, "Smile")

    def test_morph_state_preserves_count_after_record_error(self) -> None:
        reader, header, vertex_count, bone_count, material_count = (
            reader_at_morph_section(
                build_pmx_structure(
                    morphs=(build_pmx_morph(panel=5),),
                )
            )
        )
        state = PmxMorphReadState()

        with self.assertRaisesRegex(BinaryParseError, "invalid panel 5"):
            read_pmx_morphs(
                reader,
                header=header,
                vertex_count=vertex_count,
                bone_count=bone_count,
                material_count=material_count,
                state=state,
            )

        self.assertEqual(state.morph_count, 1)
        self.assertEqual(state.morphs, ())

    def test_reads_ordered_display_frame_elements(self) -> None:
        frame = build_pmx_display_frame(
            local_name="Main",
            universal_name="Main EN",
            special_flag=1,
            elements=(
                build_pmx_display_frame_element(target_type=0, target_index=0),
                build_pmx_display_frame_element(target_type=1, target_index=0),
                build_pmx_display_frame_element(target_type=0, target_index=0),
            ),
        )
        reader, header, vertex_count, bone_count, material_count = (
            reader_at_morph_section(
                build_pmx_structure(
                    bones=(build_pmx_bone(),),
                    morphs=(build_pmx_morph(),),
                    display_frames=(frame,),
                )
            )
        )
        morphs = read_morphs(
            reader,
            header=header,
            vertex_count=vertex_count,
            bone_count=bone_count,
            material_count=material_count,
        )

        frames = read_pmx_display_frames(
            reader,
            header=header,
            bone_count=bone_count,
            morph_count=len(morphs),
        )

        self.assertEqual(frames[0].local_name, "Main")
        self.assertEqual(frames[0].universal_name, "Main EN")
        self.assertTrue(frames[0].special)
        self.assertEqual(
            [(item.target_type, item.target_index) for item in frames[0].elements],
            [("bone", 0), ("morph", 0), ("bone", 0)],
        )

    def test_display_state_preserves_count_after_record_error(self) -> None:
        reader, header, vertex_count, bone_count, material_count = (
            reader_at_morph_section(
                build_pmx_structure(
                    display_frames=(build_pmx_display_frame(special_flag=2),),
                )
            )
        )
        morphs = read_morphs(
            reader,
            header=header,
            vertex_count=vertex_count,
            bone_count=bone_count,
            material_count=material_count,
        )
        state = PmxDisplayFrameReadState()

        with self.assertRaisesRegex(BinaryParseError, "special flag 2"):
            read_pmx_display_frames(
                reader,
                header=header,
                bone_count=bone_count,
                morph_count=len(morphs),
                state=state,
            )

        self.assertEqual(state.display_frame_count, 1)
        self.assertEqual(state.display_frames, ())

    def test_records_are_immutable_validated_and_legacy_compatible(self) -> None:
        self.assertIs(PmxMorph, LegacyPmxMorph)
        self.assertIs(PmxDisplayFrame, LegacyPmxDisplayFrame)
        self.assertIs(PmxDisplayFrameElement, LegacyPmxDisplayFrameElement)

        morph = PmxMorph(
            local_name="Diagnostic",
            universal_name="",
            panel=4,
            panel_name="other",
            morph_type=1,
            morph_type_name="vertex",
            offsets=(),
        )

        with self.assertRaises(FrozenInstanceError):
            morph.local_name = "changed"  # type: ignore[misc]

        with self.assertRaisesRegex(TypeError, "offsets must be a tuple"):
            replace(morph, offsets=[])  # type: ignore[arg-type]

        with self.assertRaisesRegex(ValueError, "target_type"):
            PmxDisplayFrameElement(
                target_type="invalid",  # type: ignore[arg-type]
                target_index=0,
            )

        self.assertEqual(morph.to_dict()["offset_count"], 0)


if __name__ == "__main__":
    unittest.main()
