from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError, fields

import mmd_registry
import mmd_registry._smart_part_confidence as confidence
import mmd_registry.smart_part_detection as detection
import mmd_registry.smart_part_explainability as explainability
from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringBoneCatalogEntry,
    PmxStructuralAuthoringMaterialCatalogEntry,
    PmxStructuralAuthoringMorphCatalogEntry,
    PmxStructuralAuthoringTextureCatalogEntry,
)
from mmd_registry.smart_parts import SmartPartKind


class SmartPartResolvedConfidenceDerivationTests(unittest.TestCase):
    def material(self, source_index: int, local_name: str, universal_name: str = ""):
        return PmxStructuralAuthoringMaterialCatalogEntry(
            source_index=source_index,
            local_name=local_name,
            universal_name=universal_name,
            texture_index=-1,
            sphere_texture_index=-1,
            surface_index_count=0,
        )

    def bone(self, source_index: int, local_name: str, universal_name: str = ""):
        return PmxStructuralAuthoringBoneCatalogEntry(
            source_index=source_index,
            local_name=local_name,
            universal_name=universal_name,
            parent_bone_index=-1,
            position=(0.0, 0.0, 0.0),
            flag_names=(),
        )

    def morph(self, source_index: int, local_name: str, universal_name: str = ""):
        return PmxStructuralAuthoringMorphCatalogEntry(
            source_index=source_index,
            local_name=local_name,
            universal_name=universal_name,
            panel_name="",
            morph_type_name="VERTEX",
            offset_count=0,
        )

    def texture(self, source_index: int, path: str):
        return PmxStructuralAuthoringTextureCatalogEntry(
            source_index=source_index,
            path=path,
        )

    def assessment_for(self, entries, kind):
        return next(
            item
            for item in confidence._derive_smart_part_resolved_assessments(entries)
            if item.support.kind is kind
        )

    def test_private_resolved_enum_exact_values(self) -> None:
        self.assertEqual(
            tuple(item.value for item in confidence._SmartPartResolvedConfidence),
            ("high", "medium", "low"),
        )

    def test_private_assessment_is_frozen_slot_based_and_field_ordered(self) -> None:
        cls = confidence._SmartPartResolvedAssessment
        self.assertEqual(
            tuple(field.name for field in fields(cls)),
            ("confidence", "support", "reason"),
        )
        item = self.assessment_for((self.material(1, "Face"),), SmartPartKind.FACE)
        with self.assertRaises(FrozenInstanceError):
            item.reason = "changed"  # type: ignore[misc]
        self.assertFalse(hasattr(item, "__dict__"))

    def test_two_distinct_direct_sources_are_high(self) -> None:
        item = self.assessment_for(
            (self.material(3, "Face"), self.bone(9, "Face")),
            SmartPartKind.FACE,
        )
        self.assertIs(item.confidence, confidence._SmartPartResolvedConfidence.HIGH)
        self.assertEqual(item.reason, "multiple_independent_direct_exact_sources")

    def test_three_direct_source_families_remain_high(self) -> None:
        item = self.assessment_for(
            (
                self.material(3, "Face"),
                self.bone(9, "Face"),
                self.morph(11, "Smile"),
            ),
            SmartPartKind.FACE,
        )
        self.assertIs(item.confidence, confidence._SmartPartResolvedConfidence.HIGH)

    def test_single_direct_source_is_medium(self) -> None:
        item = self.assessment_for((self.material(3, "Face"),), SmartPartKind.FACE)
        self.assertIs(item.confidence, confidence._SmartPartResolvedConfidence.MEDIUM)
        self.assertEqual(item.reason, "single_direct_exact_source")

    def test_local_and_universal_same_entity_remain_medium(self) -> None:
        item = self.assessment_for(
            (self.material(3, "Face", "FACE"),),
            SmartPartKind.FACE,
        )
        self.assertIs(item.confidence, confidence._SmartPartResolvedConfidence.MEDIUM)
        self.assertEqual(len(item.support.direct_source_keys), 1)

    def test_duplicate_input_same_identity_remains_medium(self) -> None:
        entry = self.material(3, "Face", "FACE")
        item = self.assessment_for((entry, entry, entry), SmartPartKind.FACE)
        self.assertIs(item.confidence, confidence._SmartPartResolvedConfidence.MEDIUM)
        self.assertEqual(len(item.support.direct_source_keys), 1)

    def test_material_plus_texture_remains_medium(self) -> None:
        item = self.assessment_for(
            (self.material(3, "Face"), self.texture(4, "face.png")),
            SmartPartKind.FACE,
        )
        self.assertIs(item.confidence, confidence._SmartPartResolvedConfidence.MEDIUM)
        self.assertEqual(item.reason, "single_direct_exact_source")
        self.assertEqual(len(item.support.direct_source_keys), 1)
        self.assertEqual(len(item.support.derived_source_keys), 1)

    def test_texture_only_is_low(self) -> None:
        item = self.assessment_for(
            (self.texture(4, "face.png"),),
            SmartPartKind.FACE,
        )
        self.assertIs(item.confidence, confidence._SmartPartResolvedConfidence.LOW)
        self.assertEqual(item.reason, "derived_texture_only")

    def test_multiple_textures_same_kind_remain_low(self) -> None:
        item = self.assessment_for(
            (self.texture(4, "face.png"), self.texture(8, "face.jpg")),
            SmartPartKind.FACE,
        )
        self.assertIs(item.confidence, confidence._SmartPartResolvedConfidence.LOW)
        self.assertEqual(len(item.support.derived_source_keys), 2)

    def test_zero_evidence_produces_no_assessment(self) -> None:
        self.assertEqual(
            confidence._derive_smart_part_resolved_assessments(
                (self.material(7, "CustomSurface", "Unknown"),)
            ),
            (),
        )

    def test_conflict_only_produces_no_resolved_assessment(self) -> None:
        conflict = self.material(10, "Face", "Hair")
        self.assertEqual(
            confidence._derive_smart_part_resolved_assessments((conflict,)),
            (),
        )
        self.assertEqual(detection.detect_smart_parts((conflict,)), ())
        self.assertEqual(explainability.explain_smart_parts((conflict,)), ())

    def test_different_kinds_are_not_combined_for_high(self) -> None:
        result = confidence._derive_smart_part_resolved_assessments(
            (self.material(1, "Face"), self.bone(2, "Hair"))
        )
        self.assertEqual(
            tuple((item.support.kind, item.confidence) for item in result),
            (
                (SmartPartKind.HAIR, confidence._SmartPartResolvedConfidence.MEDIUM),
                (SmartPartKind.FACE, confidence._SmartPartResolvedConfidence.MEDIUM),
            ),
        )

    def test_input_permutation_is_deterministic(self) -> None:
        entries = (
            self.texture(4, "face.png"),
            self.bone(9, "Face"),
            self.material(3, "Face", "FACE"),
        )
        self.assertEqual(
            confidence._derive_smart_part_resolved_assessments(entries),
            confidence._derive_smart_part_resolved_assessments(tuple(reversed(entries))),
        )

    def test_machine_reasons_and_private_surface(self) -> None:
        self.assertEqual(
            (confidence._REASON_HIGH, confidence._REASON_MEDIUM, confidence._REASON_LOW),
            (
                "multiple_independent_direct_exact_sources",
                "single_direct_exact_source",
                "derived_texture_only",
            ),
        )
        self.assertEqual(confidence.__all__, ())
        self.assertEqual(mmd_registry.__all__, ("__version__",))
        self.assertFalse(hasattr(confidence, "SmartPartConfidence"))
        self.assertFalse(hasattr(confidence, "SmartPartConfidenceAssessment"))
        self.assertFalse(hasattr(confidence, "assess_smart_parts"))


if __name__ == "__main__":
    unittest.main()
