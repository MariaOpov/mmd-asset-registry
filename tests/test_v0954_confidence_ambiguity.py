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
)
from mmd_registry.smart_parts import SmartPartEvidenceKind, SmartPartKind


class SmartPartConfidenceAmbiguityTests(unittest.TestCase):
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

    def test_private_candidate_and_assessment_shape(self) -> None:
        self.assertEqual(
            tuple(field.name for field in fields(confidence._SmartPartAmbiguityCandidate)),
            ("kind", "traces"),
        )
        self.assertEqual(
            tuple(field.name for field in fields(confidence._SmartPartAmbiguityAssessment)),
            ("source_kind", "source_index", "candidates", "reason"),
        )

    def test_same_source_material_conflict_is_ambiguous(self) -> None:
        conflict = self.material(10, "Face", "Hair")
        result = confidence._collect_smart_part_ambiguity_assessments((conflict,))
        self.assertEqual(len(result), 1)
        item = result[0]
        self.assertIs(item.source_kind, SmartPartEvidenceKind.MATERIAL)
        self.assertEqual(item.source_index, 10)
        self.assertEqual(item.reason, "same_source_exact_conflict")
        self.assertEqual(
            tuple(candidate.kind for candidate in item.candidates),
            (SmartPartKind.HAIR, SmartPartKind.FACE),
        )

    def test_candidate_reporting_keeps_field_specific_evidence(self) -> None:
        item = confidence._collect_smart_part_ambiguity_assessments(
            (self.material(10, "Face", "Hair"),)
        )[0]
        by_kind = {candidate.kind: candidate for candidate in item.candidates}
        self.assertEqual(
            tuple(trace.source_field for trace in by_kind[SmartPartKind.FACE].traces),
            ("local_name",),
        )
        self.assertEqual(
            tuple(trace.source_value for trace in by_kind[SmartPartKind.FACE].traces),
            ("Face",),
        )
        self.assertEqual(
            tuple(trace.source_field for trace in by_kind[SmartPartKind.HAIR].traces),
            ("universal_name",),
        )
        self.assertEqual(
            tuple(trace.source_value for trace in by_kind[SmartPartKind.HAIR].traces),
            ("Hair",),
        )

    def test_duplicate_input_does_not_duplicate_candidate_evidence(self) -> None:
        conflict = self.material(10, "Face", "Hair")
        item = confidence._collect_smart_part_ambiguity_assessments(
            (conflict, conflict, conflict)
        )[0]
        self.assertEqual(
            tuple(len(candidate.traces) for candidate in item.candidates),
            (1, 1),
        )

    def test_same_kind_local_universal_is_not_ambiguous(self) -> None:
        self.assertEqual(
            confidence._collect_smart_part_ambiguity_assessments(
                (self.material(10, "Face", "FACE"),)
            ),
            (),
        )

    def test_unrelated_parts_are_not_ambiguous(self) -> None:
        self.assertEqual(
            confidence._collect_smart_part_ambiguity_assessments(
                (
                    self.material(1, "Face"),
                    self.bone(2, "Hair"),
                )
            ),
            (),
        )

    def test_valid_other_entity_does_not_resolve_local_conflict(self) -> None:
        conflict = self.material(10, "Face", "Hair")
        valid = self.material(11, "Face")
        ambiguous = confidence._collect_smart_part_ambiguity_assessments(
            (conflict, valid)
        )
        self.assertEqual(len(ambiguous), 1)
        self.assertEqual(ambiguous[0].source_index, 10)

        resolved = confidence._derive_smart_part_resolved_assessments(
            (conflict, valid)
        )
        face = next(item for item in resolved if item.support.kind is SmartPartKind.FACE)
        self.assertIs(
            face.confidence,
            confidence._SmartPartResolvedConfidence.MEDIUM,
        )
        self.assertEqual(len(face.support.direct_source_keys), 1)

    def test_released_detector_and_explainer_still_filter_conflict(self) -> None:
        conflict = self.material(10, "Face", "Hair")
        self.assertEqual(detection._match_smart_part_traces((conflict,)), ())
        self.assertEqual(detection.detect_smart_parts((conflict,)), ())
        self.assertEqual(explainability.explain_smart_parts((conflict,)), ())

    def test_multiple_ambiguities_use_source_kind_then_index_order(self) -> None:
        entries = (
            self.morph(8, "Blink", "Smile"),
            self.material(9, "Face", "Hair"),
            self.bone(7, "Arm", "Foot"),
            self.material(3, "Face", "Hair"),
        )
        result = confidence._collect_smart_part_ambiguity_assessments(entries)
        self.assertEqual(
            tuple((item.source_kind, item.source_index) for item in result),
            (
                (SmartPartEvidenceKind.MATERIAL, 3),
                (SmartPartEvidenceKind.MATERIAL, 9),
                (SmartPartEvidenceKind.BONE, 7),
                (SmartPartEvidenceKind.MORPH, 8),
            ),
        )

    def test_candidate_kind_order_is_smart_part_declaration_order(self) -> None:
        item = confidence._collect_smart_part_ambiguity_assessments(
            (self.bone(4, "Arm", "Foot"),)
        )[0]
        self.assertEqual(
            tuple(candidate.kind for candidate in item.candidates),
            (SmartPartKind.ARMS, SmartPartKind.FEET),
        )

    def test_input_permutation_is_deterministic(self) -> None:
        entries = (
            self.material(9, "Face", "Hair"),
            self.material(3, "Face", "Hair"),
            self.bone(7, "Arm", "Foot"),
        )
        first = confidence._collect_smart_part_ambiguity_assessments(entries)
        second = confidence._collect_smart_part_ambiguity_assessments(
            tuple(reversed(entries))
        )
        self.assertEqual(first, second)

    def test_unknown_signal_has_no_ambiguity(self) -> None:
        self.assertEqual(
            confidence._collect_smart_part_ambiguity_assessments(
                (self.material(12, "CustomSurface", "Unknown"),)
            ),
            (),
        )

    def test_private_ambiguity_values_are_immutable(self) -> None:
        item = confidence._collect_smart_part_ambiguity_assessments(
            (self.material(10, "Face", "Hair"),)
        )[0]
        with self.assertRaises(FrozenInstanceError):
            item.source_index = 2  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            item.candidates[0].kind = SmartPartKind.FACE  # type: ignore[misc]
        self.assertFalse(hasattr(item, "__dict__"))
        self.assertFalse(hasattr(item.candidates[0], "__dict__"))

    def test_no_public_confidence_api_yet(self) -> None:
        self.assertEqual(confidence.__all__, ())
        self.assertEqual(mmd_registry.__all__, ("__version__",))
        self.assertFalse(hasattr(confidence, "SmartPartConfidence"))
        self.assertFalse(hasattr(confidence, "SmartPartConfidenceCandidate"))
        self.assertFalse(hasattr(confidence, "SmartPartConfidenceAssessment"))
        self.assertFalse(hasattr(confidence, "assess_smart_parts"))


if __name__ == "__main__":
    unittest.main()
