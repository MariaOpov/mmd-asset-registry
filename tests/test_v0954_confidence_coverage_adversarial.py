from __future__ import annotations

import unittest
from dataclasses import replace

import mmd_registry._smart_part_confidence as private
import mmd_registry.smart_part_confidence as public
import mmd_registry.smart_part_detection as detection
from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringBoneCatalogEntry,
    PmxStructuralAuthoringMaterialCatalogEntry,
    PmxStructuralAuthoringTextureCatalogEntry,
)
from mmd_registry.smart_parts import SmartPartEvidenceKind, SmartPartKind


class SmartPartV0954CoverageAdversarialTests(unittest.TestCase):
    def material(
        self,
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

    def texture(
        self,
        source_index: int,
        path: str,
    ) -> PmxStructuralAuthoringTextureCatalogEntry:
        return PmxStructuralAuthoringTextureCatalogEntry(
            source_index=source_index,
            path=path,
        )

    def assert_contract_rejects(self, factory) -> None:
        with self.assertRaises((TypeError, ValueError)):
            factory()

    def test_public_candidate_rejects_empty_evidence(self) -> None:
        assessment = public.assess_smart_parts((self.material(1, "Face"),))[0]
        candidate = assessment.candidates[0]
        self.assert_contract_rejects(
            lambda: type(candidate)(kind=candidate.kind, evidence=())
        )

    def test_public_assessment_rejects_empty_candidates(self) -> None:
        self.assert_contract_rejects(
            lambda: public.SmartPartConfidenceAssessment(
                confidence=public.SmartPartConfidence.MEDIUM,
                candidates=(),
                reason="single_direct_exact_source",
            )
        )

    def test_public_ambiguous_requires_multiple_candidates(self) -> None:
        resolved = public.assess_smart_parts((self.material(2, "Face"),))[0]
        self.assert_contract_rejects(
            lambda: public.SmartPartConfidenceAssessment(
                confidence=public.SmartPartConfidence.AMBIGUOUS,
                candidates=resolved.candidates,
                reason="same_source_exact_conflict",
            )
        )

    def test_public_resolved_requires_single_candidate(self) -> None:
        ambiguous = public.assess_smart_parts(
            (self.material(3, "Face", "Hair"),)
        )[0]
        self.assertGreaterEqual(len(ambiguous.candidates), 2)
        self.assert_contract_rejects(
            lambda: public.SmartPartConfidenceAssessment(
                confidence=public.SmartPartConfidence.HIGH,
                candidates=ambiguous.candidates,
                reason="multiple_independent_direct_exact_sources",
            )
        )

    def test_public_rejects_reason_confidence_mismatch(self) -> None:
        resolved = public.assess_smart_parts((self.material(4, "Face"),))[0]
        self.assert_contract_rejects(
            lambda: public.SmartPartConfidenceAssessment(
                confidence=public.SmartPartConfidence.HIGH,
                candidates=resolved.candidates,
                reason="single_direct_exact_source",
            )
        )

    def test_public_candidate_rejects_duplicate_evidence(self) -> None:
        assessment = public.assess_smart_parts(
            (self.material(5, "Face", "FACE"),)
        )[0]
        candidate = assessment.candidates[0]
        evidence = candidate.evidence
        self.assertGreaterEqual(len(evidence), 2)
        self.assert_contract_rejects(
            lambda: type(candidate)(
                kind=candidate.kind,
                evidence=(evidence[0], evidence[0]),
            )
        )

    def test_private_association_rejects_empty_candidates(self) -> None:
        association = private._collect_smart_part_candidate_associations(
            (self.material(6, "Face"),)
        )[0]
        self.assert_contract_rejects(
            lambda: replace(association, candidates=())
        )

    def test_private_association_rejects_empty_traces(self) -> None:
        association = private._collect_smart_part_candidate_associations(
            (self.material(7, "Face"),)
        )[0]
        self.assert_contract_rejects(
            lambda: replace(association, traces=())
        )

    def test_private_association_rejects_negative_source_index(self) -> None:
        association = private._collect_smart_part_candidate_associations(
            (self.material(8, "Face"),)
        )[0]
        self.assert_contract_rejects(
            lambda: replace(association, source_index=-1)
        )

    def test_private_association_rejects_mismatched_source_kind(self) -> None:
        association = private._collect_smart_part_candidate_associations(
            (self.material(9, "Face"),)
        )[0]
        self.assert_contract_rejects(
            lambda: replace(
                association,
                source_kind=SmartPartEvidenceKind.BONE,
            )
        )

    def test_private_support_rejects_no_sources(self) -> None:
        support = private._collect_smart_part_independent_support(
            (self.material(10, "Face"),)
        )[0]
        self.assert_contract_rejects(
            lambda: replace(
                support,
                direct_source_keys=(),
                derived_source_keys=(),
            )
        )

    def test_private_support_rejects_noncanonical_duplicate_keys(self) -> None:
        support = private._collect_smart_part_independent_support(
            (
                self.material(11, "Face"),
                self.bone(12, "Face"),
            )
        )[0]
        key = support.direct_source_keys[0]
        self.assert_contract_rejects(
            lambda: replace(
                support,
                direct_source_keys=(key, key),
            )
        )

    def test_private_resolved_assessment_rejects_reason_mismatch(self) -> None:
        resolved = private._derive_smart_part_resolved_assessments(
            (self.material(13, "Face"),)
        )[0]
        self.assert_contract_rejects(
            lambda: replace(
                resolved,
                reason="multiple_independent_direct_exact_sources",
            )
        )

    def test_private_ambiguity_candidate_rejects_empty_traces(self) -> None:
        ambiguity = private._collect_smart_part_ambiguity_assessments(
            (self.material(14, "Face", "Hair"),)
        )[0]
        candidate = ambiguity.candidates[0]
        self.assert_contract_rejects(
            lambda: replace(candidate, traces=())
        )

    def test_private_ambiguity_candidate_rejects_mixed_kind_trace(self) -> None:
        ambiguity = private._collect_smart_part_ambiguity_assessments(
            (self.material(15, "Face", "Hair"),)
        )[0]
        first, second = ambiguity.candidates[:2]
        self.assert_contract_rejects(
            lambda: replace(first, traces=second.traces)
        )

    def test_private_ambiguity_assessment_requires_two_candidates(self) -> None:
        ambiguity = private._collect_smart_part_ambiguity_assessments(
            (self.material(16, "Face", "Hair"),)
        )[0]
        self.assert_contract_rejects(
            lambda: replace(
                ambiguity,
                candidates=(ambiguity.candidates[0],),
            )
        )

    def test_private_ambiguity_assessment_rejects_wrong_reason(self) -> None:
        ambiguity = private._collect_smart_part_ambiguity_assessments(
            (self.material(17, "Face", "Hair"),)
        )[0]
        self.assert_contract_rejects(
            lambda: replace(ambiguity, reason="single_direct_exact_source")
        )

    def test_duplicate_input_same_identity_does_not_upgrade_medium(self) -> None:
        entry = self.material(18, "Face")
        assessments = public.assess_smart_parts((entry, entry, entry))
        self.assertEqual(len(assessments), 1)
        self.assertIs(
            assessments[0].confidence,
            public.SmartPartConfidence.MEDIUM,
        )
        self.assertEqual(
            assessments[0].reason,
            "single_direct_exact_source",
        )

    def test_multiple_derived_textures_remain_low(self) -> None:
        assessments = public.assess_smart_parts(
            (
                self.texture(19, "face.png"),
                self.texture(20, r"nested\face.PNG"),
            )
        )
        self.assertEqual(len(assessments), 1)
        self.assertIs(
            assessments[0].confidence,
            public.SmartPartConfidence.LOW,
        )
        self.assertEqual(assessments[0].reason, "derived_texture_only")

    def test_two_distinct_direct_sources_upgrade_high(self) -> None:
        assessments = public.assess_smart_parts(
            (
                self.material(21, "Face"),
                self.bone(22, "Face"),
            )
        )
        self.assertEqual(len(assessments), 1)
        self.assertIs(
            assessments[0].confidence,
            public.SmartPartConfidence.HIGH,
        )
        self.assertEqual(
            assessments[0].reason,
            "multiple_independent_direct_exact_sources",
        )

    def test_same_source_conflict_remains_ambiguous_with_unrelated_support(self) -> None:
        assessments = public.assess_smart_parts(
            (
                self.material(23, "Face", "Hair"),
                self.bone(24, "Face"),
            )
        )
        ambiguous = [
            item
            for item in assessments
            if item.confidence is public.SmartPartConfidence.AMBIGUOUS
        ]
        self.assertEqual(len(ambiguous), 1)
        self.assertEqual(
            tuple(candidate.kind for candidate in ambiguous[0].candidates),
            (SmartPartKind.HAIR, SmartPartKind.FACE),
        )

    def test_same_kind_local_universal_is_not_ambiguous(self) -> None:
        assessments = public.assess_smart_parts(
            (self.material(25, "Face", "FACE"),)
        )
        self.assertEqual(len(assessments), 1)
        self.assertIs(
            assessments[0].confidence,
            public.SmartPartConfidence.MEDIUM,
        )

    def test_texture_parent_directory_is_not_semantic_authority(self) -> None:
        entry = self.texture(26, "face/unknown.png")
        self.assertEqual(public.assess_smart_parts((entry,)), ())
        self.assertEqual(detection.detect_smart_parts((entry,)), ())

    def test_empty_entries_are_empty_everywhere(self) -> None:
        self.assertEqual(private._collect_smart_part_candidate_associations(()), ())
        self.assertEqual(private._collect_smart_part_independent_support(()), ())
        self.assertEqual(private._derive_smart_part_resolved_assessments(()), ())
        self.assertEqual(private._collect_smart_part_ambiguity_assessments(()), ())
        self.assertEqual(public.assess_smart_parts(()), ())


class SmartPartV0954CoverageGuardBranchTests(unittest.TestCase):
    def material(
        self,
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

    def texture(
        self,
        source_index: int,
        path: str,
    ) -> PmxStructuralAuthoringTextureCatalogEntry:
        return PmxStructuralAuthoringTextureCatalogEntry(
            source_index=source_index,
            path=path,
        )

    def association(self, source_index: int = 100):
        return private._collect_smart_part_candidate_associations(
            (self.material(source_index, "Face"),)
        )[0]

    def medium_support(self, source_index: int = 200):
        return private._collect_smart_part_independent_support(
            (self.material(source_index, "Face"),)
        )[0]

    def high_support(self):
        return private._collect_smart_part_independent_support(
            (
                self.material(201, "Face"),
                self.bone(202, "Face"),
            )
        )[0]

    def low_support(self):
        return private._collect_smart_part_independent_support(
            (self.texture(203, "face.png"),)
        )[0]

    def ambiguity(self, source_index: int = 300):
        return private._collect_smart_part_ambiguity_assessments(
            (self.material(source_index, "Face", "Hair"),)
        )[0]

    def test_public_candidate_rejects_non_kind(self) -> None:
        candidate = public.assess_smart_parts(
            (self.material(1, "Face"),)
        )[0].candidates[0]
        with self.assertRaises(TypeError):
            public.SmartPartConfidenceCandidate(
                kind="face",  # type: ignore[arg-type]
                evidence=candidate.evidence,
            )

    def test_public_candidate_rejects_non_tuple_evidence(self) -> None:
        candidate = public.assess_smart_parts(
            (self.material(2, "Face"),)
        )[0].candidates[0]
        with self.assertRaises(TypeError):
            public.SmartPartConfidenceCandidate(
                kind=candidate.kind,
                evidence=list(candidate.evidence),  # type: ignore[arg-type]
            )

    def test_public_candidate_rejects_non_explanation_item(self) -> None:
        with self.assertRaises(TypeError):
            public.SmartPartConfidenceCandidate(
                kind=SmartPartKind.FACE,
                evidence=(object(),),  # type: ignore[arg-type]
            )

    def test_public_candidate_rejects_noncanonical_evidence_order(self) -> None:
        candidate = public.assess_smart_parts(
            (self.material(3, "Face", "FACE"),)
        )[0].candidates[0]
        self.assertGreaterEqual(len(candidate.evidence), 2)
        with self.assertRaises(ValueError):
            public.SmartPartConfidenceCandidate(
                kind=candidate.kind,
                evidence=tuple(reversed(candidate.evidence)),
            )

    def test_public_candidate_rejects_foreign_kind_evidence(self) -> None:
        candidate = public.assess_smart_parts(
            (self.material(4, "Face"),)
        )[0].candidates[0]
        with self.assertRaises(ValueError):
            public.SmartPartConfidenceCandidate(
                kind=SmartPartKind.HAIR,
                evidence=candidate.evidence,
            )

    def test_public_assessment_rejects_non_confidence_value(self) -> None:
        candidate = public.assess_smart_parts(
            (self.material(5, "Face"),)
        )[0].candidates[0]
        with self.assertRaises(TypeError):
            public.SmartPartConfidenceAssessment(
                confidence="medium",  # type: ignore[arg-type]
                candidates=(candidate,),
                reason="single_direct_exact_source",
            )

    def test_public_assessment_rejects_non_candidate_item(self) -> None:
        with self.assertRaises(TypeError):
            public.SmartPartConfidenceAssessment(
                confidence=public.SmartPartConfidence.MEDIUM,
                candidates=(object(),),  # type: ignore[arg-type]
                reason="single_direct_exact_source",
            )

    def test_public_assessment_rejects_noncanonical_candidate_order(self) -> None:
        ambiguous = public.assess_smart_parts(
            (self.material(6, "Face", "Hair"),)
        )[0]
        self.assertGreaterEqual(len(ambiguous.candidates), 2)
        with self.assertRaises(ValueError):
            public.SmartPartConfidenceAssessment(
                confidence=public.SmartPartConfidence.AMBIGUOUS,
                candidates=tuple(reversed(ambiguous.candidates)),
                reason="same_source_exact_conflict",
            )

    def test_public_assessment_rejects_non_string_reason(self) -> None:
        candidate = public.assess_smart_parts(
            (self.material(7, "Face"),)
        )[0].candidates[0]
        with self.assertRaises(TypeError):
            public.SmartPartConfidenceAssessment(
                confidence=public.SmartPartConfidence.MEDIUM,
                candidates=(candidate,),
                reason=1,  # type: ignore[arg-type]
            )

    def test_public_ambiguous_rejects_wrong_machine_reason(self) -> None:
        ambiguous = public.assess_smart_parts(
            (self.material(8, "Face", "Hair"),)
        )[0]
        with self.assertRaises(ValueError):
            public.SmartPartConfidenceAssessment(
                confidence=public.SmartPartConfidence.AMBIGUOUS,
                candidates=ambiguous.candidates,
                reason="single_direct_exact_source",
            )

    def test_private_association_rejects_non_integer_source_index(self) -> None:
        association = self.association(101)
        with self.assertRaises(TypeError):
            replace(association, source_index="101")

    def test_private_association_rejects_negative_source_index_directly(self) -> None:
        association = self.association(102)
        with self.assertRaises(ValueError):
            replace(association, source_index=-1)

    def test_private_association_rejects_non_kind_candidate(self) -> None:
        association = self.association(103)
        with self.assertRaises(TypeError):
            replace(
                association,
                candidates=(object(),),  # type: ignore[arg-type]
            )

    def test_private_association_rejects_noncanonical_candidates(self) -> None:
        association = self.association(104)
        with self.assertRaises(ValueError):
            replace(
                association,
                candidates=(SmartPartKind.FACE, SmartPartKind.FACE),
            )

    def test_private_association_rejects_non_trace_item(self) -> None:
        association = self.association(105)
        with self.assertRaises(TypeError):
            replace(
                association,
                traces=(object(),),  # type: ignore[arg-type]
            )

    def test_private_association_rejects_trace_source_kind_mismatch(self) -> None:
        association = self.association(106)
        trace = association.traces[0]
        mismatched_evidence = replace(
            trace.evidence,
            source_kind=SmartPartEvidenceKind.BONE,
        )
        mismatched_trace = replace(trace, evidence=mismatched_evidence)
        with self.assertRaises(ValueError):
            replace(association, traces=(mismatched_trace,))

    def test_private_association_rejects_trace_source_index_mismatch(self) -> None:
        association = self.association(107)
        trace = association.traces[0]
        mismatched_evidence = replace(
            trace.evidence,
            source_index=999,
        )
        mismatched_trace = replace(trace, evidence=mismatched_evidence)
        with self.assertRaises(ValueError):
            replace(association, traces=(mismatched_trace,))

    def test_private_association_rejects_trace_kind_not_in_candidates(self) -> None:
        association = self.association(108)
        mismatched_trace = replace(
            association.traces[0],
            kind=SmartPartKind.HAIR,
        )
        with self.assertRaises(ValueError):
            replace(association, traces=(mismatched_trace,))

    def test_private_candidate_trace_identity_rejects_non_trace(self) -> None:
        with self.assertRaises(TypeError):
            private._candidate_trace_identity_key(object())

    def test_private_deduplicate_rejects_non_tuple(self) -> None:
        with self.assertRaises(TypeError):
            private._deduplicate_candidate_traces([])  # type: ignore[arg-type]

    def test_private_deduplicate_rejects_non_trace_item(self) -> None:
        with self.assertRaises(TypeError):
            private._deduplicate_candidate_traces(
                (object(),)  # type: ignore[arg-type]
            )

    def test_private_support_rejects_non_kind(self) -> None:
        support = self.medium_support(204)
        with self.assertRaises(TypeError):
            replace(support, kind="face")

    def test_private_support_rejects_non_tuple_source_keys(self) -> None:
        support = self.medium_support(205)
        with self.assertRaises(TypeError):
            replace(
                support,
                direct_source_keys=list(support.direct_source_keys),
            )

    def test_private_support_rejects_malformed_source_identity(self) -> None:
        support = self.medium_support(206)
        with self.assertRaises(TypeError):
            replace(
                support,
                direct_source_keys=((SmartPartEvidenceKind.MATERIAL,),),
            )

    def test_private_support_rejects_non_evidence_kind_identity(self) -> None:
        support = self.medium_support(207)
        with self.assertRaises(TypeError):
            replace(
                support,
                direct_source_keys=(("material", 207),),
            )

    def test_private_support_rejects_negative_identity_index(self) -> None:
        support = self.medium_support(208)
        with self.assertRaises(ValueError):
            replace(
                support,
                direct_source_keys=((SmartPartEvidenceKind.MATERIAL, -1),),
            )

    def test_private_support_rejects_texture_as_direct_source(self) -> None:
        with self.assertRaises(ValueError):
            private._SmartPartIndependentSupport(
                kind=SmartPartKind.FACE,
                direct_source_keys=((SmartPartEvidenceKind.TEXTURE, 209),),
                derived_source_keys=(),
            )

    def test_private_support_rejects_material_as_derived_source(self) -> None:
        with self.assertRaises(ValueError):
            private._SmartPartIndependentSupport(
                kind=SmartPartKind.FACE,
                direct_source_keys=(),
                derived_source_keys=((SmartPartEvidenceKind.MATERIAL, 210),),
            )

    def test_private_resolved_rejects_non_confidence_value(self) -> None:
        support = self.medium_support(211)
        with self.assertRaises(TypeError):
            private._SmartPartResolvedAssessment(
                confidence="medium",  # type: ignore[arg-type]
                support=support,
                reason="single_direct_exact_source",
            )

    def test_private_resolved_rejects_non_support_value(self) -> None:
        with self.assertRaises(TypeError):
            private._SmartPartResolvedAssessment(
                confidence=private._SmartPartResolvedConfidence.MEDIUM,
                support=object(),  # type: ignore[arg-type]
                reason="single_direct_exact_source",
            )

    def test_private_resolved_rejects_non_string_reason(self) -> None:
        support = self.medium_support(212)
        with self.assertRaises(TypeError):
            private._SmartPartResolvedAssessment(
                confidence=private._SmartPartResolvedConfidence.MEDIUM,
                support=support,
                reason=1,  # type: ignore[arg-type]
            )

    def test_private_high_rejects_wrong_reason(self) -> None:
        support = self.high_support()
        with self.assertRaises(ValueError):
            private._SmartPartResolvedAssessment(
                confidence=private._SmartPartResolvedConfidence.HIGH,
                support=support,
                reason="single_direct_exact_source",
            )

    def test_private_high_requires_two_direct_sources(self) -> None:
        support = self.medium_support(213)
        with self.assertRaises(ValueError):
            private._SmartPartResolvedAssessment(
                confidence=private._SmartPartResolvedConfidence.HIGH,
                support=support,
                reason="multiple_independent_direct_exact_sources",
            )

    def test_private_medium_rejects_two_direct_sources(self) -> None:
        support = self.high_support()
        with self.assertRaises(ValueError):
            private._SmartPartResolvedAssessment(
                confidence=private._SmartPartResolvedConfidence.MEDIUM,
                support=support,
                reason="single_direct_exact_source",
            )

    def test_private_low_rejects_wrong_reason(self) -> None:
        support = self.low_support()
        with self.assertRaises(ValueError):
            private._SmartPartResolvedAssessment(
                confidence=private._SmartPartResolvedConfidence.LOW,
                support=support,
                reason="single_direct_exact_source",
            )

    def test_private_low_rejects_direct_support(self) -> None:
        support = self.medium_support(214)
        with self.assertRaises(ValueError):
            private._SmartPartResolvedAssessment(
                confidence=private._SmartPartResolvedConfidence.LOW,
                support=support,
                reason="derived_texture_only",
            )

    def test_private_derive_rejects_non_support(self) -> None:
        with self.assertRaises(TypeError):
            private._derive_resolved_confidence(object())

    def test_private_ambiguity_candidate_rejects_non_kind(self) -> None:
        candidate = self.ambiguity(301).candidates[0]
        with self.assertRaises(TypeError):
            replace(candidate, kind="hair")

    def test_private_ambiguity_candidate_rejects_non_trace_item(self) -> None:
        candidate = self.ambiguity(302).candidates[0]
        with self.assertRaises(TypeError):
            replace(
                candidate,
                traces=(object(),),  # type: ignore[arg-type]
            )

    def test_private_ambiguity_candidate_rejects_duplicate_trace(self) -> None:
        candidate = self.ambiguity(303).candidates[0]
        trace = candidate.traces[0]
        with self.assertRaises(ValueError):
            replace(candidate, traces=(trace, trace))

    def test_private_ambiguity_candidate_requires_one_source_identity(self) -> None:
        first = private._collect_smart_part_candidate_associations(
            (self.material(304, "Face"),)
        )[0].traces[0]
        second = private._collect_smart_part_candidate_associations(
            (self.material(305, "Face"),)
        )[0].traces[0]
        with self.assertRaises(ValueError):
            private._SmartPartAmbiguityCandidate(
                kind=SmartPartKind.FACE,
                traces=(first, second),
            )

    def test_private_ambiguity_assessment_rejects_non_source_kind(self) -> None:
        ambiguity = self.ambiguity(306)
        with self.assertRaises(TypeError):
            replace(ambiguity, source_kind="material")

    def test_private_ambiguity_assessment_rejects_negative_source_index(self) -> None:
        ambiguity = self.ambiguity(307)
        with self.assertRaises(ValueError):
            replace(ambiguity, source_index=-1)

    def test_private_ambiguity_assessment_rejects_non_candidate_item(self) -> None:
        ambiguity = self.ambiguity(308)
        with self.assertRaises(TypeError):
            replace(
                ambiguity,
                candidates=(object(), object()),  # type: ignore[arg-type]
            )

    def test_private_ambiguity_assessment_rejects_noncanonical_order(self) -> None:
        ambiguity = self.ambiguity(309)
        with self.assertRaises(ValueError):
            replace(
                ambiguity,
                candidates=tuple(reversed(ambiguity.candidates)),
            )

    def test_private_ambiguity_assessment_rejects_source_kind_mismatch(self) -> None:
        ambiguity = self.ambiguity(310)
        with self.assertRaises(ValueError):
            replace(
                ambiguity,
                source_kind=SmartPartEvidenceKind.BONE,
            )

    def test_private_ambiguity_assessment_rejects_source_index_mismatch(self) -> None:
        ambiguity = self.ambiguity(311)
        with self.assertRaises(ValueError):
            replace(ambiguity, source_index=999)

    def test_private_ambiguity_assessment_rejects_wrong_reason(self) -> None:
        ambiguity = self.ambiguity(312)
        with self.assertRaises(ValueError):
            replace(ambiguity, reason="single_direct_exact_source")

    def test_detector_normalization_rejects_non_string(self) -> None:
        with self.assertRaises(TypeError):
            detection._normalize_semantic_text(1)  # type: ignore[arg-type]

    def test_detector_alias_table_rejects_non_tuple(self) -> None:
        with self.assertRaises(TypeError):
            detection._build_normalized_alias_index([])  # type: ignore[arg-type]

    def test_detector_alias_table_rejects_malformed_item(self) -> None:
        with self.assertRaises(TypeError):
            detection._build_normalized_alias_index(
                ((SmartPartKind.FACE,),)  # type: ignore[arg-type]
            )

    def test_detector_alias_table_rejects_non_kind(self) -> None:
        with self.assertRaises(TypeError):
            detection._build_normalized_alias_index(
                (("face", ("face",)),)  # type: ignore[arg-type]
            )

    def test_detector_alias_table_rejects_non_tuple_aliases(self) -> None:
        with self.assertRaises(TypeError):
            detection._build_normalized_alias_index(
                ((SmartPartKind.FACE, ["face"]),)  # type: ignore[list-item]
            )

    def test_detector_alias_table_rejects_empty_normalized_alias(self) -> None:
        with self.assertRaises(ValueError):
            detection._build_normalized_alias_index(
                ((SmartPartKind.FACE, ("   ",)),)
            )

    def test_detector_alias_table_rejects_cross_kind_normalized_collision(self) -> None:
        with self.assertRaises(ValueError):
            detection._build_normalized_alias_index(
                (
                    (SmartPartKind.FACE, ("face",)),
                    (SmartPartKind.HAIR, ("FACE",)),
                )
            )

    def test_detector_texture_path_rejects_non_string(self) -> None:
        with self.assertRaises(TypeError):
            detection._texture_basename_and_stem(1)  # type: ignore[arg-type]

    def test_detector_named_match_resolution_rejects_non_tuple(self) -> None:
        with self.assertRaises(TypeError):
            detection._resolve_named_field_matches([])  # type: ignore[arg-type]

    def test_detector_named_match_resolution_rejects_malformed_item(self) -> None:
        with self.assertRaises(TypeError):
            detection._resolve_named_field_matches(
                (("local_name",),)  # type: ignore[arg-type]
            )

    def test_detector_named_match_resolution_rejects_empty_field_name(self) -> None:
        with self.assertRaises(ValueError):
            detection._resolve_named_field_matches(
                (("", SmartPartKind.FACE),)
            )

    def test_detector_named_match_resolution_rejects_non_kind(self) -> None:
        with self.assertRaises(TypeError):
            detection._resolve_named_field_matches(
                (("local_name", "face"),)  # type: ignore[arg-type]
            )

    def test_detector_candidate_dispatch_rejects_unknown_entry(self) -> None:
        with self.assertRaises(TypeError):
            detection._match_single_entry_candidates(object())

    def test_detector_candidate_collection_rejects_non_tuple_entries(self) -> None:
        with self.assertRaises(TypeError):
            detection._match_smart_part_candidate_traces(
                []  # type: ignore[arg-type]
            )

    def test_detector_candidate_collection_rejects_unknown_entry(self) -> None:
        with self.assertRaises(TypeError):
            detection._match_smart_part_candidate_traces(
                (object(),)  # type: ignore[arg-type]
            )

    def test_detector_sort_key_rejects_non_smart_part(self) -> None:
        with self.assertRaises(TypeError):
            detection._smart_part_sort_key(object())

    def test_detector_validated_entries_rejects_non_tuple(self) -> None:
        with self.assertRaises(TypeError):
            detection._validated_entries([])  # type: ignore[arg-type]

    def test_detector_validated_entries_rejects_unknown_entry(self) -> None:
        with self.assertRaises(TypeError):
            detection._validated_entries(
                (object(),)  # type: ignore[arg-type]
            )

    def test_detector_aggregate_rejects_non_tuple(self) -> None:
        with self.assertRaises(TypeError):
            detection._aggregate_parts([])  # type: ignore[arg-type]

    def test_detector_aggregate_rejects_non_smart_part_item(self) -> None:
        with self.assertRaises(TypeError):
            detection._aggregate_parts(
                (object(),)  # type: ignore[arg-type]
            )


if __name__ == "__main__":
    unittest.main()
