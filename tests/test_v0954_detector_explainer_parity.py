from __future__ import annotations

import itertools
import unittest

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
from mmd_registry.smart_parts import SmartPart, SmartPartKind


class SmartPartV0954DetectorExplainerParityTests(unittest.TestCase):
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

    def detector_signature(self, entries):
        return tuple(
            (part.kind, part.evidence)
            for part in detection.detect_smart_parts(entries)
        )

    def explanation_signature(self, entries):
        return tuple(
            (
                part.kind,
                tuple(item.evidence for item in part.evidence),
            )
            for part in explainability.explain_smart_parts(entries)
        )

    def assert_parity(self, entries):
        self.assertEqual(
            self.explanation_signature(entries),
            self.detector_signature(entries),
        )

    def test_public_surfaces_remain_v0953_compatible(self) -> None:
        self.assertEqual(mmd_registry.__all__, ("__version__",))
        self.assertEqual(detection.__all__, ("detect_smart_parts",))
        self.assertEqual(
            explainability.__all__,
            (
                "SmartPartEvidenceExplanation",
                "SmartPartExplanation",
                "explain_smart_parts",
            ),
        )
        self.assertEqual(confidence.__all__, ())

    def test_detector_is_still_projection_of_released_match_trace(self) -> None:
        entries = (
            self.material(1, "Face", "FACE"),
            self.bone(2, universal_name="Right Arm"),
            self.morph(3, local_name="Blink"),
            self.texture(4, "hair.png"),
        )
        traces = detection._match_smart_part_traces(entries)
        projected = detection._aggregate_parts(
            tuple(
                SmartPart(kind=trace.kind, evidence=(trace.evidence,))
                for trace in traces
            )
        )
        self.assertEqual(projected, detection.detect_smart_parts(entries))

    def test_explainer_is_still_projection_of_released_match_trace(self) -> None:
        entries = (
            self.material(1, "Face", "FACE"),
            self.bone(2, universal_name="Right Arm"),
            self.morph(3, local_name="Blink"),
            self.texture(4, "hair.png"),
        )
        traces = detection._match_smart_part_traces(entries)
        explained = explainability.explain_smart_parts(entries)
        self.assertEqual(
            tuple(
                (
                    part.kind,
                    tuple(item.evidence for item in part.evidence),
                )
                for part in explained
            ),
            tuple(
                (part.kind, part.evidence)
                for part in detection._aggregate_parts(
                    tuple(
                        SmartPart(kind=trace.kind, evidence=(trace.evidence,))
                        for trace in traces
                    )
                )
            ),
        )

    def test_private_candidate_conflict_does_not_leak_into_detector(self) -> None:
        entries = (self.material(10, "Face", "Hair"),)
        self.assertEqual(len(detection._match_smart_part_candidate_traces(entries)), 2)
        self.assertEqual(detection._match_smart_part_traces(entries), ())
        self.assertEqual(detection.detect_smart_parts(entries), ())

    def test_private_candidate_conflict_does_not_leak_into_explainer(self) -> None:
        entries = (self.bone(11, "Arm", "Foot"),)
        self.assertEqual(len(detection._match_smart_part_candidate_traces(entries)), 2)
        self.assertEqual(explainability.explain_smart_parts(entries), ())

    def test_private_morph_ambiguity_does_not_leak_into_released_outputs(self) -> None:
        entries = (self.morph(12, "Blink", "Smile"),)
        ambiguity = confidence._collect_smart_part_ambiguity_assessments(entries)
        self.assertEqual(len(ambiguity), 1)
        self.assertEqual(detection.detect_smart_parts(entries), ())
        self.assertEqual(explainability.explain_smart_parts(entries), ())

    def test_high_confidence_support_does_not_change_detector_evidence(self) -> None:
        entries = (
            self.material(20, "Face"),
            self.bone(21, "Face"),
        )
        resolved = confidence._derive_smart_part_resolved_assessments(entries)
        face = next(item for item in resolved if item.support.kind is SmartPartKind.FACE)
        self.assertEqual(face.confidence.value, "high")
        self.assert_parity(entries)
        detected = detection.detect_smart_parts(entries)
        face_part = next(part for part in detected if part.kind is SmartPartKind.FACE)
        self.assertEqual(len(face_part.evidence), 2)

    def test_medium_with_texture_does_not_hide_or_promote_released_evidence(self) -> None:
        entries = (
            self.material(30, "Face"),
            self.texture(31, "face.png"),
        )
        resolved = confidence._derive_smart_part_resolved_assessments(entries)
        face = next(item for item in resolved if item.support.kind is SmartPartKind.FACE)
        self.assertEqual(face.confidence.value, "medium")
        self.assert_parity(entries)
        detected = detection.detect_smart_parts(entries)
        face_part = next(part for part in detected if part.kind is SmartPartKind.FACE)
        self.assertEqual(len(face_part.evidence), 2)

    def test_low_texture_only_still_has_original_detector_explainer_parity(self) -> None:
        entries = (self.texture(40, "face.png"),)
        resolved = confidence._derive_smart_part_resolved_assessments(entries)
        self.assertEqual(resolved[0].confidence.value, "low")
        self.assert_parity(entries)
        self.assertEqual(len(detection.detect_smart_parts(entries)[0].evidence), 1)

    def test_valid_entity_does_not_resolve_conflicting_entity_in_released_outputs(self) -> None:
        conflict = self.material(50, "Face", "Hair")
        valid = self.material(51, "Face")
        entries = (conflict, valid)
        ambiguity = confidence._collect_smart_part_ambiguity_assessments(entries)
        self.assertEqual(len(ambiguity), 1)
        self.assertEqual(ambiguity[0].source_index, 50)
        self.assert_parity(entries)
        detected = detection.detect_smart_parts(entries)
        self.assertEqual(len(detected), 1)
        self.assertIs(detected[0].kind, SmartPartKind.FACE)
        self.assertEqual(
            tuple(e.source_index for e in detected[0].evidence),
            (51,),
        )

    def test_duplicate_input_keeps_released_canonical_evidence_parity(self) -> None:
        entry = self.material(60, "Face", "FACE")
        entries = (entry, entry, entry)
        self.assert_parity(entries)
        detected = detection.detect_smart_parts(entries)
        self.assertEqual(len(detected), 1)
        self.assertEqual(len(detected[0].evidence), 2)

    def test_confidence_calls_do_not_mutate_future_released_results(self) -> None:
        entries = (
            self.material(70, "Face", "FACE"),
            self.bone(71, universal_name="Right Arm"),
            self.texture(72, "hair.png"),
        )
        before_detection = detection.detect_smart_parts(entries)
        before_explanation = explainability.explain_smart_parts(entries)

        for _ in range(10):
            confidence._collect_smart_part_candidate_associations(entries)
            confidence._collect_smart_part_independent_support(entries)
            confidence._derive_smart_part_resolved_assessments(entries)
            confidence._collect_smart_part_ambiguity_assessments(entries)

        self.assertEqual(detection.detect_smart_parts(entries), before_detection)
        self.assertEqual(explainability.explain_smart_parts(entries), before_explanation)

    def test_representative_permutations_preserve_all_three_projections(self) -> None:
        entries = (
            self.material(80, "Face", "FACE"),
            self.bone(81, universal_name="Right Arm"),
            self.morph(82, local_name="Blink"),
            self.texture(83, "hair.png"),
        )
        expected_detection = detection.detect_smart_parts(entries)
        expected_explanation = explainability.explain_smart_parts(entries)
        expected_resolved = confidence._derive_smart_part_resolved_assessments(entries)

        for permuted in itertools.permutations(entries):
            self.assertEqual(detection.detect_smart_parts(permuted), expected_detection)
            self.assertEqual(
                explainability.explain_smart_parts(permuted),
                expected_explanation,
            )
            self.assertEqual(
                confidence._derive_smart_part_resolved_assessments(permuted),
                expected_resolved,
            )

    def test_invalid_boundaries_remain_detector_explainer_consistent(self) -> None:
        for value in ([], {}, "Face", None):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(TypeError):
                    detection.detect_smart_parts(value)  # type: ignore[arg-type]
                with self.assertRaises(TypeError):
                    explainability.explain_smart_parts(value)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
