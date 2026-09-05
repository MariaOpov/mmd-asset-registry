from __future__ import annotations

import unittest

import mmd_registry.smart_part_detection as detection
from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringBoneCatalogEntry,
    PmxStructuralAuthoringMaterialCatalogEntry,
    PmxStructuralAuthoringMorphCatalogEntry,
)
from mmd_registry.smart_parts import SmartPartKind


class SmartPartDetectionConflictSafetyTests(unittest.TestCase):
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

    def test_resolver_empty_matches_is_unclassified(self) -> None:
        self.assertIsNone(detection._resolve_named_field_matches(()))

    def test_resolver_one_kind_is_classified(self) -> None:
        self.assertIs(
            detection._resolve_named_field_matches(
                (("local_name", SmartPartKind.FACE),)
            ),
            SmartPartKind.FACE,
        )

    def test_resolver_same_kind_multiple_fields_is_classified(self) -> None:
        self.assertIs(
            detection._resolve_named_field_matches(
                (
                    ("local_name", SmartPartKind.FACE),
                    ("universal_name", SmartPartKind.FACE),
                )
            ),
            SmartPartKind.FACE,
        )

    def test_resolver_conflicting_kinds_is_unclassified(self) -> None:
        self.assertIsNone(
            detection._resolve_named_field_matches(
                (
                    ("local_name", SmartPartKind.FACE),
                    ("universal_name", SmartPartKind.HAIR),
                )
            )
        )

    def test_resolver_conflict_is_order_independent(self) -> None:
        first = (
            ("local_name", SmartPartKind.FACE),
            ("universal_name", SmartPartKind.HAIR),
        )
        second = tuple(reversed(first))
        self.assertIsNone(detection._resolve_named_field_matches(first))
        self.assertIsNone(detection._resolve_named_field_matches(second))

    def test_resolver_rejects_non_tuple_container(self) -> None:
        with self.assertRaises(TypeError):
            detection._resolve_named_field_matches([])  # type: ignore[arg-type]

    def test_resolver_rejects_malformed_item(self) -> None:
        with self.assertRaises(TypeError):
            detection._resolve_named_field_matches(
                (("local_name", SmartPartKind.FACE, "extra"),)  # type: ignore[arg-type]
            )

    def test_resolver_rejects_empty_field_name(self) -> None:
        with self.assertRaises(ValueError):
            detection._resolve_named_field_matches(
                (("", SmartPartKind.FACE),)
            )

    def test_resolver_rejects_non_kind(self) -> None:
        with self.assertRaises(TypeError):
            detection._resolve_named_field_matches(
                (("local_name", "face"),)  # type: ignore[arg-type]
            )

    def test_material_conflict_contributes_zero_evidence(self) -> None:
        entry = self.material(
            source_index=10,
            local_name="Face",
            universal_name="Hair",
        )
        self.assertEqual(detection.detect_smart_parts((entry,)), ())

    def test_material_conflict_has_no_local_name_priority(self) -> None:
        first = self.material(
            source_index=10,
            local_name="Face",
            universal_name="Hair",
        )
        second = self.material(
            source_index=11,
            local_name="Hair",
            universal_name="Face",
        )
        self.assertEqual(detection.detect_smart_parts((first,)), ())
        self.assertEqual(detection.detect_smart_parts((second,)), ())

    def test_bone_conflict_contributes_zero_evidence(self) -> None:
        entry = self.bone(
            source_index=3,
            local_name="右腕",
            universal_name="Left Foot",
        )
        self.assertEqual(detection.detect_smart_parts((entry,)), ())

    def test_morph_conflict_contributes_zero_evidence(self) -> None:
        entry = self.morph(
            source_index=4,
            local_name="まばたき",
            universal_name="Smile",
        )
        self.assertEqual(detection.detect_smart_parts((entry,)), ())

    def test_unknown_local_does_not_block_known_universal(self) -> None:
        entry = self.material(
            source_index=2,
            local_name="CustomSurface",
            universal_name="Face",
        )
        result = detection.detect_smart_parts((entry,))
        self.assertEqual(len(result), 1)
        self.assertIs(result[0].kind, SmartPartKind.FACE)
        self.assertEqual(len(result[0].evidence), 1)

    def test_known_local_does_not_require_universal_match(self) -> None:
        entry = self.material(
            source_index=2,
            local_name="Face",
            universal_name="CustomSurface",
        )
        result = detection.detect_smart_parts((entry,))
        self.assertEqual(len(result), 1)
        self.assertIs(result[0].kind, SmartPartKind.FACE)
        self.assertEqual(len(result[0].evidence), 1)

    def test_conflicted_entity_does_not_suppress_valid_other_entity(self) -> None:
        conflict = self.material(
            source_index=20,
            local_name="Face",
            universal_name="Hair",
        )
        valid = self.material(
            source_index=21,
            local_name="Skin",
            universal_name="Skin",
        )
        result = detection.detect_smart_parts((conflict, valid))
        self.assertEqual(tuple(part.kind for part in result), (SmartPartKind.SKIN,))
        self.assertEqual(
            {item.source_index for item in result[0].evidence},
            {21},
        )

    def test_conflicted_entity_does_not_contaminate_same_kind_aggregation(self) -> None:
        conflict = self.material(
            source_index=30,
            local_name="Face",
            universal_name="Hair",
        )
        valid_face = self.material(
            source_index=31,
            local_name="Face",
            universal_name="Face",
        )
        result = detection.detect_smart_parts((conflict, valid_face))
        self.assertEqual(len(result), 1)
        self.assertIs(result[0].kind, SmartPartKind.FACE)
        self.assertEqual(
            {item.source_index for item in result[0].evidence},
            {31},
        )

    def test_multiple_conflicted_entities_produce_no_output(self) -> None:
        entries = (
            self.material(
                source_index=1,
                local_name="Face",
                universal_name="Hair",
            ),
            self.bone(
                source_index=2,
                local_name="右腕",
                universal_name="Left Foot",
            ),
            self.morph(
                source_index=3,
                local_name="Blink",
                universal_name="Smile",
            ),
        )
        self.assertEqual(detection.detect_smart_parts(entries), ())

    def test_normalized_same_kind_names_are_not_false_conflict(self) -> None:
        entry = self.material(
            source_index=7,
            local_name="  Ｆａｃｅ  ",
            universal_name="FACE",
        )
        result = detection.detect_smart_parts((entry,))
        self.assertEqual(len(result), 1)
        self.assertIs(result[0].kind, SmartPartKind.FACE)
        self.assertEqual(len(result[0].evidence), 2)

    def test_each_family_alias_index_has_unique_normalized_aliases(self) -> None:
        for name in (
            "_MATERIAL_ALIAS_INDEX",
            "_BONE_ALIAS_INDEX",
            "_MORPH_ALIAS_INDEX",
            "_TEXTURE_ALIAS_INDEX",
        ):
            with self.subTest(index=name):
                index = getattr(detection, name)
                aliases = tuple(alias for alias, _kind in index)
                self.assertEqual(len(aliases), len(set(aliases)))

    def test_synthetic_cross_kind_alias_collision_fails_closed(self) -> None:
        table = (
            (SmartPartKind.FACE, ("same",)),
            (SmartPartKind.HAIR, (" SAME ",)),
        )
        with self.assertRaises(ValueError):
            detection._build_normalized_alias_index(table)


if __name__ == "__main__":
    unittest.main()
