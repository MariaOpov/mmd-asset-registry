"""Tests for v0.9.5.5 Smart Inspect ambiguity and no-evidence UX."""

from __future__ import annotations

import unittest

import mmd_registry.smart_cli as smart_cli
from mmd_registry.services import _smart_inspection as smart_inspection
from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringMaterialCatalogEntry,
)
from mmd_registry.smart_part_confidence import SmartPartConfidence
from mmd_registry.smart_parts import SmartPartKind


class SmartCliAmbiguityNoEvidenceUxTests(unittest.TestCase):
    def material(
        self,
        source_index: int,
        local_name: str,
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

    def ambiguous_result(self):
        return smart_inspection._analyze_entries(
            (self.material(7, "Face", "Hair"),)
        )

    def test_ambiguous_result_remains_explicit_and_is_never_silently_resolved(
        self,
    ) -> None:
        result = self.ambiguous_result()

        self.assertEqual(result.parts, ())
        self.assertEqual(result.explanations, ())
        self.assertEqual(len(result.assessments), 1)

        assessment = result.assessments[0]
        self.assertIs(assessment.confidence, SmartPartConfidence.AMBIGUOUS)

        output = smart_cli._render_basic_text(result)
        self.assertIn("Hair / Face", output)
        self.assertIn("AMBIGUOUS", output)
        self.assertIn("  Candidates:\n", output)
        self.assertNotIn("Hair                    MEDIUM", output)
        self.assertNotIn("Face                    MEDIUM", output)

    def test_ambiguous_multiple_candidates_preserve_authority_order(
        self,
    ) -> None:
        result = self.ambiguous_result()
        assessment = result.assessments[0]

        self.assertEqual(
            tuple(candidate.kind for candidate in assessment.candidates),
            (SmartPartKind.HAIR, SmartPartKind.FACE),
        )

        output = smart_cli._render_basic_text(result)
        hair_position = output.index("    Hair\n")
        face_position = output.index("    Face\n")
        self.assertLess(hair_position, face_position)

    def test_same_source_conflict_renders_candidate_evidence_without_winner(
        self,
    ) -> None:
        result = self.ambiguous_result()
        assessment = result.assessments[0]

        self.assertTrue(
            all(
                item.evidence.source_kind.value == "material"
                and item.evidence.source_index == 7
                for candidate in assessment.candidates
                for item in candidate.evidence
            )
        )

        output = smart_cli._render_basic_text(result)

        expected_lines = tuple(
            f"    {smart_cli._render_evidence_item(item)}"
            for candidate in assessment.candidates
            for item in candidate.evidence
        )
        for line in expected_lines:
            self.assertIn(line + "\n", output)

        self.assertIn('universal_name="Hair"', output)
        self.assertIn('local_name="Face"', output)

    def test_no_semantic_detections_use_clean_no_result_output(self) -> None:
        result = smart_inspection._analyze_entries(
            (self.material(1, "Completely Unknown"),)
        )

        self.assertEqual(result.parts, ())
        self.assertEqual(result.explanations, ())
        self.assertEqual(result.assessments, ())
        self.assertEqual(
            smart_cli._render_basic_text(result),
            "SMART PART INSPECTION\nNo Smart Parts detected.\n",
        )

    def test_partial_detections_show_known_evidence_without_false_no_result(
        self,
    ) -> None:
        result = smart_inspection._analyze_entries(
            (
                self.material(2, "Face"),
                self.material(3, "Completely Unknown"),
            )
        )

        output = smart_cli._render_basic_text(result)

        self.assertIn("Face", output)
        self.assertIn("MEDIUM", output)
        self.assertIn("Evidence:", output)
        self.assertIn('material[2] local_name="Face"', output)
        self.assertNotIn("Completely Unknown", output)
        self.assertNotIn("No Smart Parts detected.", output)


if __name__ == "__main__":
    unittest.main()
