"""v0.9.5.6 material capability discovery contract tests."""

from __future__ import annotations

import dataclasses
import unittest

import mmd_registry.services._smart_inspection as smart_inspection
from mmd_registry.services._smart_material_draft import (
    SmartMaterialCapabilityStatus,
    discover_smart_material_capability,
)
from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringBoneCatalogEntry,
    PmxStructuralAuthoringMaterialCatalogEntry,
    PmxStructuralAuthoringMorphCatalogEntry,
    PmxStructuralAuthoringTextureCatalogEntry,
)
from mmd_registry.smart_part_confidence import SmartPartConfidence
from mmd_registry.smart_parts import SmartPartEvidenceKind, SmartPartKind


def material(
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


def bone(
    source_index: int,
    local_name: str,
) -> PmxStructuralAuthoringBoneCatalogEntry:
    return PmxStructuralAuthoringBoneCatalogEntry(
        source_index=source_index,
        local_name=local_name,
        universal_name="",
        parent_bone_index=-1,
        position=(0.0, 0.0, 0.0),
        flag_names=(),
    )


def morph(
    source_index: int,
    local_name: str,
) -> PmxStructuralAuthoringMorphCatalogEntry:
    return PmxStructuralAuthoringMorphCatalogEntry(
        source_index=source_index,
        local_name=local_name,
        universal_name="",
        panel_name="eye",
        morph_type_name="vertex",
        offset_count=0,
    )


class SmartMaterialCapabilityTests(unittest.TestCase):
    def test_exact_material_evidence_supports_material_color(self) -> None:
        result = smart_inspection._analyze_entries((material(2, "Eyes"),))

        capability = discover_smart_material_capability(
            result,
            SmartPartKind.EYES,
        )

        self.assertIs(capability.status, SmartMaterialCapabilityStatus.SUPPORTED)
        self.assertTrue(capability.supported)
        self.assertFalse(capability.blocked)
        self.assertEqual(capability.reason, "exact_material_evidence")
        self.assertEqual(capability.material_indices, (2,))

    def test_texture_only_low_confidence_is_unsupported(self) -> None:
        result = smart_inspection._analyze_entries(
            (
                PmxStructuralAuthoringTextureCatalogEntry(
                    source_index=0,
                    path="eyes.png",
                ),
            )
        )
        self.assertIs(result.assessments[0].confidence, SmartPartConfidence.LOW)

        capability = discover_smart_material_capability(
            result,
            SmartPartKind.EYES,
        )

        self.assertIs(capability.status, SmartMaterialCapabilityStatus.UNSUPPORTED)
        self.assertFalse(capability.supported)
        self.assertEqual(capability.reason, "no_exact_material_evidence")

    def test_high_confidence_without_material_evidence_is_still_unsupported(self) -> None:
        result = smart_inspection._analyze_entries(
            (
                bone(0, "左目"),
                morph(1, "blink"),
            )
        )
        self.assertIs(result.assessments[0].confidence, SmartPartConfidence.HIGH)

        capability = discover_smart_material_capability(
            result,
            SmartPartKind.EYES,
        )

        self.assertIs(capability.status, SmartMaterialCapabilityStatus.UNSUPPORTED)
        self.assertEqual(capability.reason, "no_exact_material_evidence")

    def test_ambiguity_blocks_even_when_another_exact_material_target_exists(self) -> None:
        result = smart_inspection._analyze_entries(
            (
                material(0, "Eyes"),
                material(1, "Eyes", "Hair"),
            )
        )

        capability = discover_smart_material_capability(
            result,
            SmartPartKind.EYES,
        )

        self.assertIs(capability.status, SmartMaterialCapabilityStatus.BLOCKED)
        self.assertTrue(capability.blocked)
        self.assertFalse(capability.supported)
        self.assertEqual(capability.reason, "ambiguous_semantic_selection")
        self.assertEqual(capability.material_indices, (0,))

    def test_capability_is_frozen(self) -> None:
        result = smart_inspection._analyze_entries((material(0, "Eyes"),))
        capability = discover_smart_material_capability(
            result,
            SmartPartKind.EYES,
        )

        with self.assertRaises(dataclasses.FrozenInstanceError):
            capability.reason = "changed"  # type: ignore[misc]


class SmartMaterialCapabilityEvidenceTests(unittest.TestCase):
    def test_supported_capability_retains_exact_material_provenance(self) -> None:
        result = smart_inspection._analyze_entries(
            (
                material(2, "瞳"),
                material(5, "Eyes"),
            )
        )

        capability = discover_smart_material_capability(
            result,
            SmartPartKind.EYES,
        )

        self.assertIs(capability.status, SmartMaterialCapabilityStatus.SUPPORTED)
        self.assertEqual(capability.reason, "exact_material_evidence")
        self.assertEqual(capability.material_indices, (2, 5))
        self.assertTrue(capability.evidence)
        self.assertTrue(
            all(
                item.source_kind is SmartPartEvidenceKind.MATERIAL
                for item in capability.evidence
            )
        )
        self.assertEqual(
            tuple(item.source_index for item in capability.evidence),
            (2, 5),
        )

        explanation = next(
            item
            for item in result.explanations
            if item.kind is SmartPartKind.EYES
        )
        explanation_evidence = tuple(
            item.evidence for item in explanation.evidence
        )
        self.assertEqual(len(explanation_evidence), len(capability.evidence))
        for evidence in capability.evidence:
            self.assertIn(evidence, explanation_evidence)

    def test_ambiguity_blocks_without_silent_candidate_resolution(self) -> None:
        result = smart_inspection._analyze_entries(
            (
                material(0, "Eyes", "Hair"),
                material(1, "Eyes"),
            )
        )

        ambiguous = tuple(
            assessment
            for assessment in result.assessments
            if assessment.confidence is SmartPartConfidence.AMBIGUOUS
        )
        self.assertEqual(len(ambiguous), 1)
        self.assertEqual(
            tuple(candidate.kind for candidate in ambiguous[0].candidates),
            (SmartPartKind.EYES, SmartPartKind.HAIR),
        )

        capability = discover_smart_material_capability(
            result,
            SmartPartKind.EYES,
        )

        self.assertIs(capability.status, SmartMaterialCapabilityStatus.BLOCKED)
        self.assertEqual(capability.reason, "ambiguous_semantic_selection")
        self.assertEqual(capability.material_indices, (1,))
        self.assertTrue(
            all(item.source_index != 0 for item in capability.evidence)
        )

    def test_medium_confidence_is_not_permission_but_exact_evidence_is(self) -> None:
        result = smart_inspection._analyze_entries((material(4, "Eyes"),))

        assessment = next(
            item
            for item in result.assessments
            if item.candidates[0].kind is SmartPartKind.EYES
        )
        self.assertIs(assessment.confidence, SmartPartConfidence.MEDIUM)

        capability = discover_smart_material_capability(
            result,
            SmartPartKind.EYES,
        )
        self.assertIs(capability.status, SmartMaterialCapabilityStatus.SUPPORTED)
        self.assertEqual(capability.reason, "exact_material_evidence")

    def test_capability_reasons_are_stable_and_explainable(self) -> None:
        supported = discover_smart_material_capability(
            smart_inspection._analyze_entries((material(0, "Eyes"),)),
            SmartPartKind.EYES,
        )
        unsupported = discover_smart_material_capability(
            smart_inspection._analyze_entries(
                (
                    PmxStructuralAuthoringTextureCatalogEntry(
                        source_index=0,
                        path="eyes.png",
                    ),
                )
            ),
            SmartPartKind.EYES,
        )
        blocked = discover_smart_material_capability(
            smart_inspection._analyze_entries(
                (material(0, "Eyes", "Hair"),)
            ),
            SmartPartKind.EYES,
        )

        self.assertEqual(
            (supported.reason, unsupported.reason, blocked.reason),
            (
                "exact_material_evidence",
                "no_exact_material_evidence",
                "ambiguous_semantic_selection",
            ),
        )


if __name__ == "__main__":
    unittest.main()
