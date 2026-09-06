from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError, fields

import mmd_registry._smart_part_confidence as confidence
from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringBoneCatalogEntry,
    PmxStructuralAuthoringMaterialCatalogEntry,
    PmxStructuralAuthoringTextureCatalogEntry,
)
from mmd_registry.smart_parts import SmartPartEvidenceKind, SmartPartKind


class SmartPartConfidenceIndependenceTests(unittest.TestCase):
    def material(
        self,
        source_index: int,
        local_name: str,
        universal_name: str,
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
        source_index: int,
        local_name: str,
        universal_name: str,
    ) -> PmxStructuralAuthoringBoneCatalogEntry:
        return PmxStructuralAuthoringBoneCatalogEntry(
            source_index=source_index,
            local_name=local_name,
            universal_name=universal_name,
            parent_bone_index=-1,
            position=(0.0, 0.0, 0.0),
            flag_names=(),
        )

    def texture(
        self,
        source_index: int,
        path: str,
    ) -> PmxStructuralAuthoringTextureCatalogEntry:
        return PmxStructuralAuthoringTextureCatalogEntry(
            source_index=source_index,
            path=path,
        )

    def support_for(self, entries, kind):
        return next(
            item
            for item in confidence._collect_smart_part_independent_support(entries)
            if item.kind is kind
        )

    def test_support_dto_is_frozen_slot_based_and_field_ordered(self) -> None:
        cls = confidence._SmartPartIndependentSupport
        self.assertEqual(
            tuple(field.name for field in fields(cls)),
            ("kind", "direct_source_keys", "derived_source_keys"),
        )
        support = self.support_for((self.material(1, "Face", ""),), SmartPartKind.FACE)
        with self.assertRaises(FrozenInstanceError):
            support.kind = SmartPartKind.HAIR  # type: ignore[misc]
        self.assertFalse(hasattr(support, "__dict__"))

    def test_local_and_universal_names_on_same_entity_are_one_source(self) -> None:
        entry = self.material(7, "Face", "FACE")
        association = confidence._collect_smart_part_candidate_associations((entry,))[0]
        self.assertEqual(len(association.traces), 2)
        support = self.support_for((entry,), SmartPartKind.FACE)
        self.assertEqual(
            support.direct_source_keys,
            ((SmartPartEvidenceKind.MATERIAL, 7),),
        )

    def test_duplicate_input_same_identity_does_not_increase_support(self) -> None:
        entry = self.material(7, "Face", "FACE")
        support = self.support_for((entry, entry, entry), SmartPartKind.FACE)
        self.assertEqual(
            support.direct_source_keys,
            ((SmartPartEvidenceKind.MATERIAL, 7),),
        )

    def test_duplicate_exact_candidate_rows_are_removed_in_association(self) -> None:
        entry = self.material(7, "Face", "FACE")
        associations = confidence._collect_smart_part_candidate_associations(
            (entry, entry)
        )
        self.assertEqual(len(associations), 1)
        self.assertEqual(len(associations[0].traces), 2)
        identities = tuple(
            confidence._candidate_trace_identity_key(trace)
            for trace in associations[0].traces
        )
        self.assertEqual(len(identities), len(set(identities)))

    def test_two_distinct_direct_entities_produce_two_independent_sources(self) -> None:
        entries = (
            self.material(3, "Face", ""),
            self.bone(9, "Face", ""),
        )
        support = self.support_for(entries, SmartPartKind.FACE)
        self.assertEqual(
            support.direct_source_keys,
            (
                (SmartPartEvidenceKind.MATERIAL, 3),
                (SmartPartEvidenceKind.BONE, 9),
            ),
        )
        self.assertEqual(support.derived_source_keys, ())

    def test_texture_only_is_derived_not_direct(self) -> None:
        support = self.support_for((self.texture(4, "face.png"),), SmartPartKind.FACE)
        self.assertEqual(support.direct_source_keys, ())
        self.assertEqual(
            support.derived_source_keys,
            ((SmartPartEvidenceKind.TEXTURE, 4),),
        )

    def test_material_plus_texture_keeps_direct_and_derived_separate(self) -> None:
        entries = (
            self.material(3, "Face", ""),
            self.texture(4, "face.png"),
        )
        support = self.support_for(entries, SmartPartKind.FACE)
        self.assertEqual(
            support.direct_source_keys,
            ((SmartPartEvidenceKind.MATERIAL, 3),),
        )
        self.assertEqual(
            support.derived_source_keys,
            ((SmartPartEvidenceKind.TEXTURE, 4),),
        )

    def test_same_source_conflict_does_not_become_resolved_support(self) -> None:
        conflict = self.material(10, "Face", "Hair")
        self.assertEqual(
            confidence._collect_smart_part_independent_support((conflict,)),
            (),
        )

    def test_conflict_does_not_suppress_unrelated_valid_support(self) -> None:
        entries = (
            self.material(10, "Face", "Hair"),
            self.material(11, "Skin", ""),
        )
        result = confidence._collect_smart_part_independent_support(entries)
        self.assertEqual(tuple(item.kind for item in result), (SmartPartKind.SKIN,))

    def test_input_permutation_is_deterministic(self) -> None:
        entries = (
            self.texture(4, "face.png"),
            self.bone(9, "Face", ""),
            self.material(3, "Face", "FACE"),
        )
        first = confidence._collect_smart_part_independent_support(entries)
        second = confidence._collect_smart_part_independent_support(tuple(reversed(entries)))
        self.assertEqual(first, second)

    def test_private_surface_stays_private(self) -> None:
        self.assertEqual(confidence.__all__, ())
        self.assertFalse(hasattr(confidence, "SmartPartConfidence"))
        self.assertFalse(hasattr(confidence, "assess_smart_parts"))


if __name__ == "__main__":
    unittest.main()
