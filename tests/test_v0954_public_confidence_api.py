from __future__ import annotations

import inspect
import unittest
from dataclasses import FrozenInstanceError, fields

import mmd_registry
import mmd_registry.smart_part_confidence as confidence
import mmd_registry.smart_part_detection as detection
import mmd_registry.smart_part_explainability as explainability
from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringBoneCatalogEntry,
    PmxStructuralAuthoringMaterialCatalogEntry,
    PmxStructuralAuthoringMorphCatalogEntry,
    PmxStructuralAuthoringTextureCatalogEntry,
)
from mmd_registry.smart_part_explainability import SmartPartEvidenceExplanation
from mmd_registry.smart_parts import SmartPartKind


class SmartPartPublicConfidenceApiTests(unittest.TestCase):
    def material(self, source_index: int, local_name: str = "", universal_name: str = ""):
        return PmxStructuralAuthoringMaterialCatalogEntry(
            source_index=source_index,
            local_name=local_name,
            universal_name=universal_name,
            texture_index=-1,
            sphere_texture_index=-1,
            surface_index_count=0,
        )

    def bone(self, source_index: int, local_name: str = "", universal_name: str = ""):
        return PmxStructuralAuthoringBoneCatalogEntry(
            source_index=source_index,
            local_name=local_name,
            universal_name=universal_name,
            parent_bone_index=-1,
            position=(0.0, 0.0, 0.0),
            flag_names=(),
        )

    def morph(self, source_index: int, local_name: str = "", universal_name: str = ""):
        return PmxStructuralAuthoringMorphCatalogEntry(
            source_index=source_index,
            local_name=local_name,
            universal_name=universal_name,
            panel_name="OTHER",
            morph_type_name="VERTEX",
            offset_count=0,
        )

    def texture(self, source_index: int, path: str):
        return PmxStructuralAuthoringTextureCatalogEntry(
            source_index=source_index,
            path=path,
        )

    def test_public_all_is_exact_and_root_is_not_promoted(self) -> None:
        self.assertEqual(
            confidence.__all__,
            (
                "SmartPartConfidence",
                "SmartPartConfidenceCandidate",
                "SmartPartConfidenceAssessment",
                "assess_smart_parts",
            ),
        )
        self.assertEqual(mmd_registry.__all__, ("__version__",))
        self.assertFalse(hasattr(mmd_registry, "SmartPartConfidence"))
        self.assertFalse(hasattr(mmd_registry, "assess_smart_parts"))

    def test_enum_values_are_exact(self) -> None:
        self.assertEqual(
            tuple((item.name, item.value) for item in confidence.SmartPartConfidence),
            (
                ("HIGH", "high"),
                ("MEDIUM", "medium"),
                ("LOW", "low"),
                ("AMBIGUOUS", "ambiguous"),
            ),
        )

    def test_public_dto_fields_are_exact_frozen_and_slotted(self) -> None:
        self.assertEqual(
            tuple(field.name for field in fields(confidence.SmartPartConfidenceCandidate)),
            ("kind", "evidence"),
        )
        self.assertEqual(
            tuple(field.name for field in fields(confidence.SmartPartConfidenceAssessment)),
            ("confidence", "candidates", "reason"),
        )
        item = confidence.assess_smart_parts((self.material(1, "Face"),))[0]
        with self.assertRaises(FrozenInstanceError):
            item.reason = "changed"  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            item.candidates[0].kind = SmartPartKind.HAIR  # type: ignore[misc]
        self.assertFalse(hasattr(item, "__dict__"))
        self.assertFalse(hasattr(item.candidates[0], "__dict__"))

    def test_function_signature_keeps_single_entries_parameter(self) -> None:
        signature = inspect.signature(confidence.assess_smart_parts)
        self.assertEqual(tuple(signature.parameters), ("entries",))

    def test_high_public_assessment(self) -> None:
        result = confidence.assess_smart_parts(
            (
                self.material(1, "Face"),
                self.bone(2, "Face"),
            )
        )
        face = next(item for item in result if item.candidates[0].kind is SmartPartKind.FACE)
        self.assertIs(face.confidence, confidence.SmartPartConfidence.HIGH)
        self.assertEqual(face.reason, "multiple_independent_direct_exact_sources")
        self.assertEqual(len(face.candidates), 1)
        self.assertEqual(len(face.candidates[0].evidence), 2)

    def test_medium_material_plus_texture_remains_medium(self) -> None:
        result = confidence.assess_smart_parts(
            (
                self.material(1, "Face"),
                self.texture(2, "face.png"),
            )
        )
        face = next(item for item in result if item.candidates[0].kind is SmartPartKind.FACE)
        self.assertIs(face.confidence, confidence.SmartPartConfidence.MEDIUM)
        self.assertEqual(face.reason, "single_direct_exact_source")
        self.assertEqual(len(face.candidates[0].evidence), 2)

    def test_low_texture_only(self) -> None:
        result = confidence.assess_smart_parts((self.texture(2, "face.png"),))
        self.assertEqual(len(result), 1)
        self.assertIs(result[0].confidence, confidence.SmartPartConfidence.LOW)
        self.assertEqual(result[0].reason, "derived_texture_only")
        self.assertIs(result[0].candidates[0].kind, SmartPartKind.FACE)

    def test_zero_evidence_returns_no_assessment(self) -> None:
        self.assertEqual(
            confidence.assess_smart_parts(
                (self.material(9, "CustomSurface", "Unknown"),)
            ),
            (),
        )

    def test_same_source_conflict_is_public_ambiguous(self) -> None:
        result = confidence.assess_smart_parts(
            (self.material(10, "Face", "Hair"),)
        )
        self.assertEqual(len(result), 1)
        item = result[0]
        self.assertIs(item.confidence, confidence.SmartPartConfidence.AMBIGUOUS)
        self.assertEqual(item.reason, "same_source_exact_conflict")
        self.assertEqual(
            tuple(candidate.kind for candidate in item.candidates),
            (SmartPartKind.HAIR, SmartPartKind.FACE),
        )
        self.assertEqual(
            tuple(len(candidate.evidence) for candidate in item.candidates),
            (1, 1),
        )

    def test_public_candidate_evidence_uses_explanation_dto_only(self) -> None:
        item = confidence.assess_smart_parts(
            (self.material(10, "Face", "Hair"),)
        )[0]
        self.assertTrue(
            all(
                isinstance(evidence, SmartPartEvidenceExplanation)
                for candidate in item.candidates
                for evidence in candidate.evidence
            )
        )
        self.assertTrue(
            all(
                not type(evidence).__name__.endswith("Trace")
                for candidate in item.candidates
                for evidence in candidate.evidence
            )
        )

    def test_ambiguous_evidence_preserves_source_fields(self) -> None:
        item = confidence.assess_smart_parts(
            (self.material(10, "Face", "Hair"),)
        )[0]
        by_kind = {candidate.kind: candidate for candidate in item.candidates}
        self.assertEqual(
            tuple(e.source_field for e in by_kind[SmartPartKind.FACE].evidence),
            ("local_name",),
        )
        self.assertEqual(
            tuple(e.source_field for e in by_kind[SmartPartKind.HAIR].evidence),
            ("universal_name",),
        )

    def test_valid_other_entity_does_not_resolve_ambiguity(self) -> None:
        result = confidence.assess_smart_parts(
            (
                self.material(10, "Face", "Hair"),
                self.material(11, "Face"),
            )
        )
        self.assertEqual(len(result), 2)
        self.assertIs(result[0].confidence, confidence.SmartPartConfidence.MEDIUM)
        self.assertIs(result[0].candidates[0].kind, SmartPartKind.FACE)
        self.assertIs(result[1].confidence, confidence.SmartPartConfidence.AMBIGUOUS)

    def test_resolved_assessments_precede_ambiguity(self) -> None:
        result = confidence.assess_smart_parts(
            (
                self.material(10, "Face", "Hair"),
                self.bone(20, "Arm"),
            )
        )
        self.assertEqual(
            tuple(item.confidence for item in result),
            (
                confidence.SmartPartConfidence.MEDIUM,
                confidence.SmartPartConfidence.AMBIGUOUS,
            ),
        )
        self.assertIs(result[0].candidates[0].kind, SmartPartKind.ARMS)

    def test_multiple_ambiguities_use_evidence_kind_then_source_index_order(self) -> None:
        result = confidence.assess_smart_parts(
            (
                self.morph(8, "Blink", "Smile"),
                self.material(9, "Face", "Hair"),
                self.bone(7, "Arm", "Foot"),
                self.material(3, "Face", "Hair"),
            )
        )
        ambiguous = tuple(
            item
            for item in result
            if item.confidence is confidence.SmartPartConfidence.AMBIGUOUS
        )
        source_keys = tuple(
            (
                item.candidates[0].evidence[0].evidence.source_kind,
                item.candidates[0].evidence[0].evidence.source_index,
            )
            for item in ambiguous
        )
        from mmd_registry.smart_parts import SmartPartEvidenceKind
        self.assertEqual(
            source_keys,
            (
                (SmartPartEvidenceKind.MATERIAL, 3),
                (SmartPartEvidenceKind.MATERIAL, 9),
                (SmartPartEvidenceKind.BONE, 7),
                (SmartPartEvidenceKind.MORPH, 8),
            ),
        )

    def test_duplicate_input_does_not_duplicate_public_evidence(self) -> None:
        entry = self.material(5, "Face", "FACE")
        result = confidence.assess_smart_parts((entry, entry, entry))
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0].candidates[0].evidence), 2)

    def test_input_permutation_is_deterministic(self) -> None:
        entries = (
            self.material(1, "Face"),
            self.bone(2, "Face"),
            self.texture(3, "hair.png"),
            self.material(10, "Face", "Hair"),
        )
        self.assertEqual(
            confidence.assess_smart_parts(entries),
            confidence.assess_smart_parts(tuple(reversed(entries))),
        )

    def test_detector_and_explainer_remain_unchanged_by_public_assessment(self) -> None:
        entries = (
            self.material(1, "Face", "FACE"),
            self.bone(2, "Right Arm"),
            self.texture(3, "hair.png"),
        )
        before_detection = detection.detect_smart_parts(entries)
        before_explanation = explainability.explain_smart_parts(entries)
        for _ in range(10):
            confidence.assess_smart_parts(entries)
        self.assertEqual(detection.detect_smart_parts(entries), before_detection)
        self.assertEqual(explainability.explain_smart_parts(entries), before_explanation)

    def test_invalid_container_boundary_fails_closed(self) -> None:
        for value in ([], {}, "Face", None):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(TypeError):
                    confidence.assess_smart_parts(value)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
