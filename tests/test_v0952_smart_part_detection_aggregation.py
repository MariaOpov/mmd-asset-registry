from __future__ import annotations

import itertools
import unittest

import mmd_registry.smart_part_detection as detection
from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringBoneCatalogEntry,
    PmxStructuralAuthoringMaterialCatalogEntry,
    PmxStructuralAuthoringMorphCatalogEntry,
    PmxStructuralAuthoringTextureCatalogEntry,
)
from mmd_registry.smart_parts import (
    SmartPart,
    SmartPartEvidence,
    SmartPartEvidenceKind,
    SmartPartKind,
)


class SmartPartDetectionAggregationTests(unittest.TestCase):
    def material(
        self,
        *,
        source_index: int,
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

    def morph(
        self,
        *,
        source_index: int,
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

    def bone(
        self,
        *,
        source_index: int,
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

    def test_same_kind_cross_family_evidence_is_aggregated(self) -> None:
        entries = (
            self.material(
                source_index=7,
                local_name="顔",
                universal_name="Face",
            ),
            PmxStructuralAuthoringTextureCatalogEntry(
                source_index=1,
                path=r"textures\Face.png",
            ),
            self.morph(
                source_index=4,
                local_name="笑顔",
                universal_name="Smile",
            ),
        )
        result = detection.detect_smart_parts(entries)
        self.assertEqual(len(result), 1)
        part = result[0]
        self.assertIs(part.kind, SmartPartKind.FACE)
        self.assertEqual(len(part.evidence), 5)
        self.assertEqual(
            tuple(
                (
                    item.source_kind,
                    item.source_index,
                    item.reason,
                )
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
                (
                    SmartPartEvidenceKind.MORPH,
                    4,
                    "morph.local_name:exact_alias:face",
                ),
                (
                    SmartPartEvidenceKind.MORPH,
                    4,
                    "morph.universal_name:exact_alias:face",
                ),
                (
                    SmartPartEvidenceKind.TEXTURE,
                    1,
                    "texture.path:exact_alias:face",
                ),
            ),
        )

    def test_exact_duplicate_source_entity_evidence_is_deduplicated(self) -> None:
        material = self.material(
            source_index=3,
            local_name="Face",
            universal_name="Face",
        )
        result = detection.detect_smart_parts((material, material))
        self.assertEqual(len(result), 1)
        self.assertIs(result[0].kind, SmartPartKind.FACE)
        self.assertEqual(len(result[0].evidence), 2)
        self.assertEqual(len(set(result[0].evidence)), 2)

    def test_same_kind_different_source_indices_are_additive(self) -> None:
        first = self.material(source_index=9, local_name="Skin")
        second = self.material(source_index=2, universal_name="Skin")
        result = detection.detect_smart_parts((first, second))
        self.assertEqual(len(result), 1)
        self.assertIs(result[0].kind, SmartPartKind.SKIN)
        self.assertEqual(
            tuple(item.source_index for item in result[0].evidence),
            (2, 9),
        )

    def test_different_kinds_remain_separate(self) -> None:
        face = self.material(source_index=5, local_name="Face")
        arm = self.bone(
            source_index=2,
            local_name="右腕",
            universal_name="Right Arm",
        )
        result = detection.detect_smart_parts((face, arm))
        self.assertEqual(
            tuple(part.kind for part in result),
            (SmartPartKind.FACE, SmartPartKind.ARMS),
        )

    def test_aggregation_output_follows_smart_part_declaration_order(self) -> None:
        entries = (
            self.material(source_index=1, local_name="Shoes"),
            self.bone(source_index=2, universal_name="Right Arm"),
            self.morph(source_index=3, universal_name="Blink"),
            self.material(source_index=4, local_name="Hair"),
        )
        result = detection.detect_smart_parts(entries)
        self.assertEqual(
            tuple(part.kind for part in result),
            (
                SmartPartKind.EYES,
                SmartPartKind.HAIR,
                SmartPartKind.ARMS,
                SmartPartKind.SHOES,
            ),
        )

    def test_input_order_does_not_change_aggregated_result(self) -> None:
        entries = (
            self.material(
                source_index=7,
                local_name="顔",
                universal_name="Face",
            ),
            PmxStructuralAuthoringTextureCatalogEntry(
                source_index=1,
                path="textures/Face.png",
            ),
            self.morph(
                source_index=4,
                local_name="笑顔",
                universal_name="Smile",
            ),
        )
        expected = detection.detect_smart_parts(entries)
        for permutation in itertools.permutations(entries):
            with self.subTest(order=tuple(item.source_index for item in permutation)):
                self.assertEqual(
                    detection.detect_smart_parts(tuple(permutation)),
                    expected,
                )

    def test_repeated_detection_is_identical_and_hashable(self) -> None:
        entries = (
            self.material(source_index=1, local_name="Face"),
            PmxStructuralAuthoringTextureCatalogEntry(
                source_index=2,
                path="Face.png",
            ),
        )
        first = detection.detect_smart_parts(entries)
        second = detection.detect_smart_parts(entries)
        self.assertEqual(first, second)
        self.assertEqual(tuple(map(hash, first)), tuple(map(hash, second)))

    def test_internal_aggregate_rejects_non_tuple(self) -> None:
        with self.assertRaises(TypeError):
            detection._aggregate_parts([])  # type: ignore[arg-type]

    def test_internal_aggregate_rejects_non_smart_part_item(self) -> None:
        with self.assertRaises(TypeError):
            detection._aggregate_parts((object(),))  # type: ignore[arg-type]

    def test_internal_aggregate_deduplicates_exact_evidence(self) -> None:
        evidence = SmartPartEvidence(
            SmartPartEvidenceKind.MATERIAL,
            1,
            "material.local_name:exact_alias:face",
        )
        first = SmartPart(SmartPartKind.FACE, (evidence,))
        second = SmartPart(SmartPartKind.FACE, (evidence,))
        result = detection._aggregate_parts((first, second))
        self.assertEqual(
            result,
            (SmartPart(SmartPartKind.FACE, (evidence,)),),
        )

    def test_cross_kind_evidence_is_never_merged(self) -> None:
        face_evidence = SmartPartEvidence(
            SmartPartEvidenceKind.MATERIAL,
            1,
            "material.local_name:exact_alias:face",
        )
        hair_evidence = SmartPartEvidence(
            SmartPartEvidenceKind.MATERIAL,
            2,
            "material.local_name:exact_alias:hair",
        )
        result = detection._aggregate_parts(
            (
                SmartPart(SmartPartKind.HAIR, (hair_evidence,)),
                SmartPart(SmartPartKind.FACE, (face_evidence,)),
            )
        )
        self.assertEqual(
            tuple(part.kind for part in result),
            (SmartPartKind.HAIR, SmartPartKind.FACE),
        )

    def test_source_entries_remain_unchanged_after_aggregation(self) -> None:
        material = self.material(
            source_index=8,
            local_name="  Ｆａｃｅ  ",
            universal_name="Face",
        )
        texture = PmxStructuralAuthoringTextureCatalogEntry(
            source_index=9,
            path=r"textures\Face.png",
        )
        before = (repr(material), repr(texture))
        detection.detect_smart_parts((material, texture))
        self.assertEqual((repr(material), repr(texture)), before)


if __name__ == "__main__":
    unittest.main()
