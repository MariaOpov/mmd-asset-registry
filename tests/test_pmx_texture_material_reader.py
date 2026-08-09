"""Tests for typed PMX texture and material reading."""

from __future__ import annotations

import io
import unittest
from dataclasses import FrozenInstanceError, replace

from mmd_registry.binary_reader import BinaryParseError, BinaryReader
from mmd_registry.pmx import PmxMaterial
from mmd_registry.pmx.sections.geometry import read_pmx_geometry
from mmd_registry.pmx.sections.header import read_pmx_header
from mmd_registry.pmx.sections.materials import (
    PmxMaterialReadState,
    read_pmx_materials,
)
from mmd_registry.pmx.sections.textures import read_pmx_textures
from tests.mmd_fixtures import build_pmx_material, build_pmx_structure


def read_texture_material_sections(
    data: bytes,
) -> tuple[tuple[str, ...], tuple[PmxMaterial, ...], int]:
    """Read generated PMX data through the material section."""

    reader = BinaryReader(
        io.BytesIO(data),
        format_name="PMX",
    )
    header = read_pmx_header(reader).header
    geometry = read_pmx_geometry(
        reader,
        header=header,
    )
    texture_paths = read_pmx_textures(
        reader,
        header=header,
    )
    materials = read_pmx_materials(
        reader,
        header=header,
        texture_count=len(texture_paths),
        surface_index_count=len(geometry.surface_indices),
    )
    return texture_paths, materials, reader.offset


class PmxTextureMaterialReaderTests(unittest.TestCase):
    """Validate byte-complete texture paths and material records."""

    def test_reads_complete_material_values_and_texture_order(self) -> None:
        texture_paths = (
            "textures/body.png",
            "sphere.spa",
            "toon.bmp",
        )
        material_data = build_pmx_material(
            local_name="Body",
            universal_name="Body EN",
            diffuse=(0.25, 0.5, 0.75, 1.0),
            specular=(0.125, 0.25, 0.5),
            specular_strength=0.75,
            ambient=(0.5, 0.25, 0.125),
            drawing_flags=0x1F,
            edge_color=(0.0, 0.25, 0.5, 0.75),
            edge_scale=1.5,
            texture_index=0,
            sphere_texture_index=1,
            sphere_mode=2,
            toon_reference_mode=0,
            toon_reference_index=2,
            memo="Complete material",
            surface_index_count=3,
        )

        paths, materials, _ = read_texture_material_sections(
            build_pmx_structure(
                texture_paths=texture_paths,
                materials=(material_data,),
            )
        )

        self.assertEqual(paths, texture_paths)
        self.assertEqual(len(materials), 1)
        material = materials[0]
        self.assertEqual(material.local_name, "Body")
        self.assertEqual(material.universal_name, "Body EN")
        self.assertEqual(material.diffuse, (0.25, 0.5, 0.75, 1.0))
        self.assertEqual(material.specular, (0.125, 0.25, 0.5))
        self.assertEqual(material.specular_strength, 0.75)
        self.assertEqual(material.ambient, (0.5, 0.25, 0.125))
        self.assertEqual(material.drawing_flags, 0x1F)
        self.assertEqual(material.edge_color, (0.0, 0.25, 0.5, 0.75))
        self.assertEqual(material.edge_scale, 1.5)
        self.assertEqual(material.texture_index, 0)
        self.assertEqual(material.sphere_texture_index, 1)
        self.assertEqual(material.sphere_mode, 2)
        self.assertEqual(material.toon_reference_mode, "texture")
        self.assertEqual(material.toon_reference_index, 2)
        self.assertEqual(material.memo, "Complete material")
        self.assertEqual(material.surface_index_count, 3)

    def test_reads_shared_toon_reference_and_sentinel_indices(self) -> None:
        _, materials, _ = read_texture_material_sections(
            build_pmx_structure(
                materials=(
                    build_pmx_material(
                        texture_index=-1,
                        sphere_texture_index=-1,
                        toon_reference_mode=1,
                        toon_reference_index=7,
                        surface_index_count=3,
                    ),
                ),
            )
        )

        material = materials[0]
        self.assertEqual(material.texture_index, -1)
        self.assertEqual(material.sphere_texture_index, -1)
        self.assertEqual(material.toon_reference_mode, "shared")
        self.assertEqual(material.toon_reference_index, 7)

    def test_supports_utf16_and_all_texture_index_sizes(self) -> None:
        for texture_index_size in (1, 2, 4):
            with self.subTest(texture_index_size=texture_index_size):
                paths, materials, _ = read_texture_material_sections(
                    build_pmx_structure(
                        encoding_flag=0,
                        texture_index_size=texture_index_size,
                        texture_paths=("テクスチャ/体.png",),
                        materials=(
                            build_pmx_material(
                                local_name="材質",
                                texture_index=0,
                                memo="説明",
                                surface_index_count=3,
                                encoding_flag=0,
                                texture_index_size=texture_index_size,
                            ),
                        ),
                    )
                )

                self.assertEqual(paths, ("テクスチャ/体.png",))
                self.assertEqual(materials[0].local_name, "材質")
                self.assertEqual(materials[0].memo, "説明")
                self.assertEqual(materials[0].texture_index, 0)

    def test_reads_empty_texture_and_material_sections(self) -> None:
        paths, materials, _ = read_texture_material_sections(
            build_pmx_structure(
                deform_types=(),
                surface_indices=(),
                texture_paths=(),
                materials=(),
            )
        )

        self.assertEqual(paths, ())
        self.assertEqual(materials, ())

    def test_material_state_preserves_count_after_record_error(self) -> None:
        reader = BinaryReader(
            io.BytesIO(
                build_pmx_structure(
                    materials=(
                        build_pmx_material(
                            toon_reference_mode=2,
                            surface_index_count=3,
                        ),
                    ),
                )
            ),
            format_name="PMX",
        )
        header = read_pmx_header(reader).header
        geometry = read_pmx_geometry(reader, header=header)
        texture_paths = read_pmx_textures(reader, header=header)
        state = PmxMaterialReadState()

        with self.assertRaisesRegex(BinaryParseError, "invalid toon reference mode"):
            read_pmx_materials(
                reader,
                header=header,
                texture_count=len(texture_paths),
                surface_index_count=len(geometry.surface_indices),
                state=state,
            )

        self.assertEqual(state.material_count, 1)
        self.assertEqual(state.materials, ())

    def test_material_is_immutable_validated_and_legacy_serializable(self) -> None:
        _, materials, _ = read_texture_material_sections(build_pmx_structure())
        material = materials[0]

        with self.assertRaises(FrozenInstanceError):
            material.memo = "changed"  # type: ignore[misc]

        with self.assertRaisesRegex(ValueError, "unsigned byte"):
            replace(material, drawing_flags=256)

        with self.assertRaisesRegex(ValueError, "divisible by 3"):
            replace(material, surface_index_count=1)

        legacy_payload = material.to_dict()
        self.assertEqual(legacy_payload["local_name"], "Material")
        self.assertNotIn("diffuse", legacy_payload)
        self.assertNotIn("drawing_flags", legacy_payload)

        legacy_constructed = PmxMaterial(
            local_name="Legacy",
            universal_name="Legacy EN",
            texture_index=-1,
            sphere_texture_index=-1,
            sphere_mode=0,
            toon_reference_mode="shared",
            toon_reference_index=0,
            memo="",
            surface_index_count=0,
        )
        self.assertEqual(legacy_constructed.diffuse, (1.0, 1.0, 1.0, 1.0))
        self.assertEqual(legacy_constructed.to_dict()["local_name"], "Legacy")


if __name__ == "__main__":
    unittest.main()
