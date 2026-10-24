"""v0.9.5.11 deterministic exact-alias capability/precedence tests."""

from __future__ import annotations

import dataclasses
import unittest
from unittest.mock import patch

from mmd_registry._smart_morph_readonly import (
    SmartMorphCapabilityStatus,
    _canonical_candidate_traces,
)
from mmd_registry.services import _smart_morph_inspection as inspection
from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringMorphCatalogEntry,
)
from mmd_registry.smart_part_detection import (
    _candidate_trace_sort_key,
    _match_smart_part_candidate_traces,
)
from mmd_registry.smart_parts import SmartPartEvidenceKind, SmartPartKind
from tests.mmd_fixtures import (
    build_pmx_bone_morph_offset,
    build_pmx_material_morph_offset,
    build_pmx_vertex_morph_offset,
)
from tests.test_v09511_morph_core_inventory import synthetic_morph, synthetic_source


V = lambda: (build_pmx_vertex_morph_offset(),)
B = lambda: (build_pmx_bone_morph_offset(),)
M = lambda: (build_pmx_material_morph_offset(),)


def result_of(*morphs: bytes, version: float = 2.0):
    return inspection.inspect_smart_morphs(synthetic_source(*morphs, version=version))


def capability(slot: str, *morphs: bytes, version: float = 2.0):
    result = result_of(*morphs, version=version)
    return next(c for c in result.capabilities if c.capability_kind == slot)


class SmartMorphCapabilityTests(unittest.TestCase):
    def test_supported_smile_vertex_and_blink_bone(self) -> None:
        result = result_of(synthetic_morph("smile", offsets=V()),
                           synthetic_morph("blink", morph_type=2, offsets=B()))
        self.assertEqual(tuple(c.reason for c in result.capabilities),
                         ("exact_morph_evidence", "exact_morph_evidence"))
        self.assertEqual(result.capabilities[0].candidate_indices, (0,))
        self.assertEqual(result.capabilities[1].candidate_indices, (1,))
        self.assertTrue(all(c.supported for c in result.capabilities))

    def test_japanese_aliases_and_nfkc_casefold(self) -> None:
        for value in ("smile", "ＳＭＩＬＥ", "笑顔", "笑い", "  SMILE  "):
            with self.subTest(value=value):
                c = capability("smile", synthetic_morph(value, offsets=V()))
                self.assertEqual(c.reason, "exact_morph_evidence")
                self.assertEqual(c.evidence[0].evidence.source_kind, SmartPartEvidenceKind.MORPH)
        for value in ("blink", "ＢＬＩＮＫ", "まばたき"):
            with self.subTest(value=value):
                self.assertEqual(capability("blink", synthetic_morph(value, offsets=V())).reason,
                                 "exact_morph_evidence")

    def test_generic_face_eyes_and_wink_not_slot_aliases(self) -> None:
        for value in ("face", "顔", "eyes", "eye", "wink", "ウィンク", "almostsmile"):
            with self.subTest(value=value):
                result = result_of(synthetic_morph(value, offsets=V()))
                self.assertEqual(tuple(c.reason for c in result.capabilities),
                                 ("no_exact_morph_evidence", "no_exact_morph_evidence"))

    def test_source_conflict_blocks_both_slots_and_retains_both_field_traces(self) -> None:
        result = result_of(synthetic_morph("smile", universal="blink", offsets=V()))
        for c in result.capabilities:
            self.assertEqual(c.reason, "same_source_exact_conflict")
            self.assertEqual(c.candidate_indices, (0,))
            self.assertEqual({e.source_field for e in c.evidence}, {"local_name", "universal_name"})
            self.assertEqual({e.kind for e in c.evidence}, {SmartPartKind.FACE, SmartPartKind.EYES})
            self.assertEqual({e.evidence.source_kind for e in c.evidence}, {SmartPartEvidenceKind.MORPH})

    def test_same_source_conflict_precedes_other_valid_candidate(self) -> None:
        c = capability("smile", synthetic_morph("smile", universal="blink", offsets=V()),
                       synthetic_morph("smile", offsets=V()))
        self.assertEqual(c.reason, "same_source_exact_conflict")
        self.assertEqual(c.candidate_indices, (0, 1))
        self.assertTrue(any(e.kind is SmartPartKind.EYES for e in c.evidence))

    def test_unrelated_source_conflict_does_not_poison_slot(self) -> None:
        c = capability("smile", synthetic_morph("eyes", universal="face", offsets=V()),
                       synthetic_morph("smile", offsets=V()))
        self.assertEqual(c.reason, "exact_morph_evidence")
        self.assertEqual(c.candidate_indices, (1,))

    def test_same_part_kind_other_field_not_conflict(self) -> None:
        c = capability("smile", synthetic_morph("smile", universal="face", offsets=V()))
        self.assertEqual(c.reason, "exact_morph_evidence")
        self.assertEqual(c.candidate_indices, (0,))

    def test_valid_vertex_plus_material_morph_blocks_multiple(self) -> None:
        c = capability("smile", synthetic_morph("smile", offsets=V()),
                       synthetic_morph("smile", morph_type=8, offsets=M()))
        self.assertEqual(c.reason, "multiple_exact_morph_candidates")
        self.assertEqual(c.candidate_indices, (0, 1))

    def test_valid_bone_plus_empty_bone_blocks_multiple(self) -> None:
        c = capability("blink", synthetic_morph("blink", morph_type=2, offsets=B()),
                       synthetic_morph("blink", morph_type=2, offsets=()))
        self.assertEqual(c.reason, "multiple_exact_morph_candidates")

    def test_two_ineligible_types_still_block_multiple(self) -> None:
        c = capability("smile", synthetic_morph("smile", morph_type=8),
                       synthetic_morph("smile", morph_type=8))
        self.assertEqual(c.reason, "multiple_exact_morph_candidates")

    def test_out_of_scope_type_precedes_empty_offsets(self) -> None:
        c = capability("smile", synthetic_morph("smile", morph_type=8, offsets=()))
        self.assertEqual(c.reason, "morph_type_out_of_scope")
        self.assertEqual(c.candidate_indices, (0,))
        self.assertEqual(len(c.evidence), 1)

    def test_type_one_empty_offsets_unsupported(self) -> None:
        c = capability("smile", synthetic_morph("smile", morph_type=1, offsets=()))
        self.assertEqual(c.reason, "empty_morph_offsets")
        self.assertFalse(c.supported)

    def test_direct_type_two_only_but_group_morph_unsupported(self) -> None:
        self.assertEqual(capability("blink", synthetic_morph("blink", morph_type=0)).reason,
                         "morph_type_out_of_scope")

    def test_no_alias_no_candidate_indices_or_evidence(self) -> None:
        c = capability("blink", synthetic_morph("unknown", offsets=V()))
        self.assertEqual(c.reason, "no_exact_morph_evidence")
        self.assertEqual(c.candidate_indices, ())
        self.assertEqual(c.evidence, ())

    def test_local_universal_duplicate_kind_distinct_trace_provenance(self) -> None:
        c = capability("smile", synthetic_morph("smile", universal="smile", offsets=V()))
        self.assertEqual(c.reason, "exact_morph_evidence")
        self.assertEqual({e.source_field for e in c.evidence}, {"local_name", "universal_name"})
        self.assertEqual(len(c.evidence), 2)

    def test_explanations_are_immutable(self) -> None:
        c = capability("smile", synthetic_morph("smile", offsets=V()))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            c.evidence[0].source_value = "changed"  # type: ignore[misc]

    def test_catalog_name_mismatch_blocks_both_before_support(self) -> None:
        original = inspection._collect_morph_catalog
        def altered(doc):
            entries = list(original(doc))
            entries[0] = dataclasses.replace(entries[0], universal_name="foreign")
            return tuple(entries)
        with patch.object(inspection, "_collect_morph_catalog", side_effect=altered):
            result = result_of(synthetic_morph("smile", offsets=V()))
        self.assertEqual(tuple(c.reason for c in result.capabilities),
                         ("source_evidence_mismatch", "source_evidence_mismatch"))

    def test_duplicate_catalog_index_blocks_both(self) -> None:
        original = inspection._collect_morph_catalog
        def duplicate(doc):
            entries = list(original(doc))
            entries[1] = dataclasses.replace(entries[1], source_index=0)
            return tuple(entries)
        with patch.object(inspection, "_collect_morph_catalog", side_effect=duplicate):
            result = result_of(synthetic_morph("smile", offsets=V()), synthetic_morph("blink", offsets=V()))
        self.assertTrue(all(c.reason == "source_evidence_mismatch" for c in result.capabilities))

    def test_missing_catalog_index_blocks_both(self) -> None:
        original = inspection._collect_morph_catalog
        with patch.object(inspection, "_collect_morph_catalog", side_effect=lambda doc: original(doc)[:-1]):
            result = result_of(synthetic_morph("smile", offsets=V()))
        self.assertTrue(all(c.blocked for c in result.capabilities))

    def test_sorted_catalog_presentation_is_placement_invariant(self) -> None:
        source = synthetic_source(synthetic_morph("smile", offsets=V()),
                                  synthetic_morph("blink", offsets=V()))
        expected = inspection.inspect_smart_morphs(source)
        original = inspection._collect_morph_catalog
        with patch.object(inspection, "_collect_morph_catalog", side_effect=lambda doc: tuple(reversed(original(doc)))):
            actual = inspection.inspect_smart_morphs(source)
        self.assertEqual(actual, expected)

    def test_pre_filter_trace_dedup_sort_uses_existing_detector_key(self) -> None:
        entries = (
            PmxStructuralAuthoringMorphCatalogEntry(0, "smile", "blink", "other", "vertex", 1),
            PmxStructuralAuthoringMorphCatalogEntry(1, "smile", "smile", "other", "vertex", 1),
        )
        traces = _match_smart_part_candidate_traces(entries)
        reversed_duplicated = tuple(reversed(traces + traces))
        actual = _canonical_candidate_traces(reversed_duplicated)
        self.assertEqual(actual, tuple(sorted(traces, key=_candidate_trace_sort_key)))
        self.assertEqual({t.kind for t in actual if t.evidence.source_index == 0},
                         {SmartPartKind.FACE, SmartPartKind.EYES})

    def test_explanations_never_contain_non_morph_sources(self) -> None:
        result = result_of(synthetic_morph("smile", offsets=V()),
                           synthetic_morph("blink", offsets=V()))
        self.assertTrue(all(e.evidence.source_kind is SmartPartEvidenceKind.MORPH
                            for c in result.capabilities for e in c.evidence))

    def test_legacy_version_exports_not_modified(self) -> None:
        import mmd_registry
        self.assertEqual(mmd_registry.__version__, "0.9.5.11")
        self.assertEqual(mmd_registry.__all__, ("__version__",))


if __name__ == "__main__":
    unittest.main()
