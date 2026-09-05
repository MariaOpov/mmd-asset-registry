from __future__ import annotations

import unittest

import mmd_registry.smart_part_detection as detection
from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringBoneCatalogEntry,
    PmxStructuralAuthoringMaterialCatalogEntry,
    PmxStructuralAuthoringMorphCatalogEntry,
    PmxStructuralAuthoringRigidBodyCatalogEntry,
    PmxStructuralAuthoringTextureCatalogEntry,
    PmxStructuralAuthoringVertexCatalogEntry,
)
from mmd_registry.smart_parts import (
    SmartPartEvidenceKind,
    SmartPartKind,
)


class SmartPartDetectionSingleEntityTests(unittest.TestCase):
    def material(
        self,
        *,
        source_index: int = 0,
        local_name: str = "",
        universal_name: str = "",
    ) -> PmxStructuralAuthoringMaterialCatalogEntry:
        return PmxStructuralAuthoringMaterialCatalogEntry(
            source_index=source_index,
            local_name=local_name,
            universal_name=universal_name,
            texture_index=-1,
            sphere_texture_index=-1,
            surface_index_count=0,
        )

    def bone(
        self,
        *,
        source_index: int = 0,
        local_name: str = "",
        universal_name: str = "",
    ) -> PmxStructuralAuthoringBoneCatalogEntry:
        return PmxStructuralAuthoringBoneCatalogEntry(
            source_index=source_index,
            local_name=local_name,
            universal_name=universal_name,
            parent_bone_index=-1,
            position=(0.0, 0.0, 0.0),
            flag_names=(),
        )

    def morph(
        self,
        *,
        source_index: int = 0,
        local_name: str = "",
        universal_name: str = "",
    ) -> PmxStructuralAuthoringMorphCatalogEntry:
        return PmxStructuralAuthoringMorphCatalogEntry(
            source_index=source_index,
            local_name=local_name,
            universal_name=universal_name,
            panel_name="",
            morph_type_name="VERTEX",
            offset_count=0,
        )

    def test_material_local_and_universal_same_kind_are_additive(self) -> None:
        result = detection.detect_smart_parts(
            (self.material(source_index=7, local_name="顔", universal_name="Face"),)
        )
        self.assertEqual(len(result), 1)
        part = result[0]
        self.assertIs(part.kind, SmartPartKind.FACE)
        self.assertEqual(
            tuple(
                (item.source_kind, item.source_index, item.reason)
                for item in part.evidence
            ),
            (
                (
                    SmartPartEvidenceKind.MATERIAL,
                    7,
                    "material.local_name:exact_alias:face",
                ),
                (
                    SmartPartEvidenceKind.MATERIAL,
                    7,
                    "material.universal_name:exact_alias:face",
                ),
            ),
        )

    def test_material_unknown_name_does_not_block_known_name(self) -> None:
        result = detection.detect_smart_parts(
            (
                self.material(
                    source_index=2,
                    local_name="CustomSurface",
                    universal_name="Skin",
                ),
            )
        )
        self.assertEqual(len(result), 1)
        self.assertIs(result[0].kind, SmartPartKind.SKIN)
        self.assertEqual(len(result[0].evidence), 1)

    def test_material_conflicting_names_do_not_pick_winner(self) -> None:
        result = detection.detect_smart_parts(
            (self.material(local_name="Face", universal_name="Hair"),)
        )
        self.assertEqual(result, ())

    def test_material_empty_names_produce_no_evidence(self) -> None:
        result = detection.detect_smart_parts(
            (self.material(local_name="  ", universal_name="\t\r\n"),)
        )
        self.assertEqual(result, ())

    def test_material_near_miss_does_not_match(self) -> None:
        result = detection.detect_smart_parts(
            (
                self.material(
                    local_name="Face Helper",
                    universal_name="facial",
                ),
            )
        )
        self.assertEqual(result, ())

    def test_bone_japanese_and_english_right_arm_match_arms(self) -> None:
        result = detection.detect_smart_parts(
            (
                self.bone(
                    source_index=3,
                    local_name="右腕",
                    universal_name="Right Arm",
                ),
            )
        )
        self.assertEqual(len(result), 1)
        self.assertIs(result[0].kind, SmartPartKind.ARMS)
        self.assertTrue(
            all(
                item.source_kind is SmartPartEvidenceKind.BONE
                and item.source_index == 3
                for item in result[0].evidence
            )
        )

    def test_bone_near_miss_does_not_match(self) -> None:
        result = detection.detect_smart_parts(
            (
                self.bone(
                    local_name="BrightArmature",
                    universal_name="Right Arm Helper",
                ),
            )
        )
        self.assertEqual(result, ())

    def test_bone_conflict_does_not_pick_winner(self) -> None:
        result = detection.detect_smart_parts(
            (
                self.bone(
                    local_name="右腕",
                    universal_name="Left Foot",
                ),
            )
        )
        self.assertEqual(result, ())

    def test_morph_blink_maps_to_eyes(self) -> None:
        result = detection.detect_smart_parts(
            (
                self.morph(
                    source_index=4,
                    local_name="まばたき",
                    universal_name="Blink",
                ),
            )
        )
        self.assertEqual(len(result), 1)
        self.assertIs(result[0].kind, SmartPartKind.EYES)
        self.assertEqual(
            {item.reason for item in result[0].evidence},
            {
                "morph.local_name:exact_alias:eyes",
                "morph.universal_name:exact_alias:eyes",
            },
        )

    def test_morph_unknown_does_not_match(self) -> None:
        self.assertEqual(
            detection.detect_smart_parts(
                (self.morph(local_name="あ", universal_name="CustomMorph"),)
            ),
            (),
        )

    def test_texture_windows_path_uses_basename_stem_only(self) -> None:
        texture = PmxStructuralAuthoringTextureCatalogEntry(
            source_index=1,
            path=r"textures\Face.png",
        )
        result = detection.detect_smart_parts((texture,))
        self.assertEqual(len(result), 1)
        self.assertIs(result[0].kind, SmartPartKind.FACE)
        self.assertEqual(
            result[0].evidence[0].reason,
            "texture.path:exact_alias:face",
        )

    def test_texture_parent_directory_is_not_semantic_evidence(self) -> None:
        texture = PmxStructuralAuthoringTextureCatalogEntry(
            source_index=1,
            path="face/custom.png",
        )
        self.assertEqual(detection.detect_smart_parts((texture,)), ())

    def test_texture_multi_dot_near_miss_is_not_reduced_to_first_stem(self) -> None:
        texture = PmxStructuralAuthoringTextureCatalogEntry(
            source_index=1,
            path="textures/Face.diffuse.png",
        )
        self.assertEqual(detection.detect_smart_parts((texture,)), ())

    def test_texture_full_width_stem_uses_frozen_normalization(self) -> None:
        texture = PmxStructuralAuthoringTextureCatalogEntry(
            source_index=8,
            path="textures/Ｆａｃｅ.png",
        )
        result = detection.detect_smart_parts((texture,))
        self.assertEqual(len(result), 1)
        self.assertIs(result[0].kind, SmartPartKind.FACE)

    def test_vertex_has_no_lexical_authority(self) -> None:
        vertex = PmxStructuralAuthoringVertexCatalogEntry(
            source_index=0,
            position=(0.0, 0.0, 0.0),
            deform_type=0,
        )
        self.assertEqual(detection.detect_smart_parts((vertex,)), ())

    def test_rigid_body_has_no_lexical_authority(self) -> None:
        rigid = PmxStructuralAuthoringRigidBodyCatalogEntry(
            source_index=5,
            local_name="右腕",
            universal_name="Right Arm",
            bone_index=3,
            shape_name="CAPSULE",
            physics_mode_name="BONE_FOLLOW",
        )
        self.assertEqual(detection.detect_smart_parts((rigid,)), ())

    def test_source_dtos_are_not_mutated(self) -> None:
        material = self.material(
            source_index=9,
            local_name="  Ｆａｃｅ  ",
            universal_name="Face",
        )
        before = repr(material)
        detection.detect_smart_parts((material,))
        self.assertEqual(repr(material), before)

    def test_distinct_kinds_are_sorted_by_smart_part_declaration_order(self) -> None:
        face = self.material(source_index=5, local_name="Face")
        eyes = self.morph(source_index=2, universal_name="Blink")
        result = detection.detect_smart_parts((face, eyes))
        self.assertEqual(
            tuple(part.kind for part in result),
            (SmartPartKind.EYES, SmartPartKind.FACE),
        )

    def test_cp05_same_kind_entities_are_aggregated(self) -> None:
        first = self.material(source_index=8, local_name="Face")
        second = self.material(source_index=3, universal_name="Face")
        result = detection.detect_smart_parts((first, second))
        self.assertEqual(len(result), 1)
        self.assertIs(result[0].kind, SmartPartKind.FACE)
        self.assertEqual(
            tuple(item.source_index for item in result[0].evidence),
            (3, 8),
        )


if __name__ == "__main__":
    unittest.main()
