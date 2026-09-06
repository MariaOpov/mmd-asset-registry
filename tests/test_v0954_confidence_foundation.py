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
    PmxStructuralAuthoringTextureCatalogEntry,
)
from mmd_registry.smart_parts import SmartPartEvidenceKind, SmartPartKind


class SmartPartConfidenceFoundationTests(unittest.TestCase):
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

    def test_private_module_has_no_public_surface(self) -> None:
        self.assertEqual(confidence.__all__, ())
        self.assertEqual(mmd_registry.__all__, ("__version__",))

    def test_private_association_contract_is_frozen_and_slot_based(self) -> None:
        cls = confidence._SmartPartCandidateAssociation
        self.assertEqual(
            tuple(field.name for field in fields(cls)),
            ("source_kind", "source_index", "candidates", "traces"),
        )
        association = confidence._collect_smart_part_candidate_associations(
            (self.material(1, "Face", "Face"),)
        )[0]
        with self.assertRaises(FrozenInstanceError):
            association.source_index = 2  # type: ignore[misc]
        self.assertFalse(hasattr(association, "__dict__"))

    def test_same_source_conflict_is_preserved_privately(self) -> None:
        entry = self.material(10, "Face", "Hair")
        candidates = detection._match_smart_part_candidate_traces((entry,))
        self.assertEqual(
            tuple(trace.kind for trace in candidates),
            (SmartPartKind.HAIR, SmartPartKind.FACE),
        )
        associations = confidence._collect_smart_part_candidate_associations((entry,))
        self.assertEqual(len(associations), 1)
        self.assertEqual(
            associations[0].candidates,
            (SmartPartKind.HAIR, SmartPartKind.FACE),
        )
        self.assertEqual(len(associations[0].traces), 2)

    def test_released_conflict_projection_remains_filtered(self) -> None:
        entry = self.material(10, "Face", "Hair")
        self.assertEqual(detection._match_smart_part_traces((entry,)), ())
        self.assertEqual(detection.detect_smart_parts((entry,)), ())
        self.assertEqual(explainability.explain_smart_parts((entry,)), ())

    def test_same_entity_same_kind_keeps_two_rows_but_one_candidate(self) -> None:
        entry = self.material(11, "Face", "FACE")
        associations = confidence._collect_smart_part_candidate_associations((entry,))
        self.assertEqual(len(associations), 1)
        self.assertEqual(associations[0].candidates, (SmartPartKind.FACE,))
        self.assertEqual(len(associations[0].traces), 2)
        released = detection.detect_smart_parts((entry,))
        self.assertEqual(len(released), 1)
        self.assertIs(released[0].kind, SmartPartKind.FACE)
        self.assertEqual(len(released[0].evidence), 2)

    def test_texture_candidate_preserves_released_derivation(self) -> None:
        entry = PmxStructuralAuthoringTextureCatalogEntry(
            source_index=2,
            path=r"tex\face.png",
        )
        association = confidence._collect_smart_part_candidate_associations((entry,))[0]
        self.assertIs(association.source_kind, SmartPartEvidenceKind.TEXTURE)
        self.assertEqual(association.candidates, (SmartPartKind.FACE,))
        self.assertEqual(
            association.traces[0].derivation,
            (("basename", "face.png"), ("basename_stem", "face")),
        )

    def test_unrelated_parts_remain_separate_associations(self) -> None:
        entries = (
            self.material(3, "Face", ""),
            self.bone(4, "Hair", ""),
        )
        associations = confidence._collect_smart_part_candidate_associations(entries)
        self.assertEqual(len(associations), 2)
        self.assertEqual(
            tuple(association.candidates for association in associations),
            ((SmartPartKind.FACE,), (SmartPartKind.HAIR,)),
        )

    def test_association_order_uses_evidence_kind_then_source_index(self) -> None:
        entries = (
            self.material(5, "Face", ""),
            PmxStructuralAuthoringTextureCatalogEntry(
                source_index=7,
                path="hair.png",
            ),
            self.material(2, "Skin", ""),
        )
        associations = confidence._collect_smart_part_candidate_associations(entries)
        self.assertEqual(
            tuple(
                (association.source_kind, association.source_index)
                for association in associations
            ),
            (
                (SmartPartEvidenceKind.TEXTURE, 7),
                (SmartPartEvidenceKind.MATERIAL, 2),
                (SmartPartEvidenceKind.MATERIAL, 5),
            ),
        )

    def test_unknown_signal_creates_no_private_assessment_foundation(self) -> None:
        entry = self.material(8, "CustomSurface", "Unknown")
        self.assertEqual(
            confidence._collect_smart_part_candidate_associations((entry,)),
            (),
        )

    def test_private_foundation_contains_no_final_confidence_api(self) -> None:
        self.assertFalse(hasattr(confidence, "SmartPartConfidence"))
        self.assertFalse(hasattr(confidence, "SmartPartConfidenceAssessment"))
        self.assertFalse(hasattr(confidence, "assess_smart_parts"))


if __name__ == "__main__":
    unittest.main()
