"""v0.9.5.12 Angry English-only opt-in private synthetic acceptance (A9-A14)."""
from __future__ import annotations
import dataclasses
import hashlib
import unittest
from unittest.mock import patch
from mmd_registry.services import _smart_morph_inspection as inspection
from mmd_registry._smart_morph_readonly import SmartMorphCapabilityStatus
from mmd_registry.smart_parts import SmartPartKind
from tests.test_v09511_morph_core_inventory import synthetic_morph, synthetic_source
from tests.mmd_fixtures import (build_pmx_vertex_morph_offset, build_pmx_bone_morph_offset,
    build_pmx_group_morph_offset, build_pmx_material_morph_offset)

def vertex(): return (build_pmx_vertex_morph_offset(),)
def bone(): return (build_pmx_bone_morph_offset(),)
def get(*morphs): return inspection.inspect_smart_morphs(synthetic_source(*morphs), include_angry=True)
def slot(result, name): return next(c for c in result.capabilities if c.capability_kind == name)

class AngryPrivateTDDTests(unittest.TestCase):
    def test_angry_direct_vertex_supported(self):
        result = get(synthetic_morph('angry', offsets=vertex()))
        c = slot(result, 'angry')
        self.assertEqual(tuple(x.capability_kind for x in result.capabilities), ('smile','blink','angry'))
        self.assertEqual((c.part_kind, c.status, c.reason, c.candidate_indices),
            (SmartPartKind.FACE, SmartMorphCapabilityStatus.SUPPORTED, 'exact_morph_evidence', (0,)))
        self.assertEqual(result.source_sha256, hashlib.sha256(synthetic_source(synthetic_morph('angry', offsets=vertex()))).hexdigest())
    def test_angry_direct_bone_supported(self):
        c = slot(get(synthetic_morph('angry', morph_type=2, offsets=bone())), 'angry')
        self.assertTrue(c.supported)
    def test_angry_nfkc_whitespace_casefold(self):
        for name in ('angry','ＡＮＧＲＹ','  ANGRY  '):
            with self.subTest(name=name):
                self.assertTrue(slot(get(synthetic_morph(name, offsets=vertex())), 'angry').supported)
    def test_no_unapproved_translations_or_mouth(self):
        for name in ('anger', '怒り', '怒', 'mouth', '口', 'angry face'):
            with self.subTest(name=name):
                self.assertEqual(slot(get(synthetic_morph(name, offsets=vertex())), 'angry').status, SmartMorphCapabilityStatus.UNSUPPORTED)
    def test_universal_name_exact_english(self):
        self.assertTrue(slot(get(synthetic_morph('unknown', universal='angry', offsets=vertex())), 'angry').supported)
    def test_same_source_smile_angry_blocks_both(self):
        result = get(synthetic_morph('smile', universal='angry', offsets=vertex()))
        for name in ('smile','angry'):
            c = slot(result, name)
            self.assertEqual((c.status, c.reason, c.candidate_indices),
                (SmartMorphCapabilityStatus.BLOCKED, 'same_source_exact_conflict', (0,)))
            self.assertGreaterEqual(len(c.evidence), 2)
    def test_different_sources_smile_angry_both_supported(self):
        result = get(synthetic_morph('smile', offsets=vertex()), synthetic_morph('angry', offsets=vertex()))
        self.assertTrue(slot(result,'smile').supported)
        self.assertTrue(slot(result,'angry').supported)
    def test_face_eyes_same_source_blocks_angry_and_blink(self):
        result = get(synthetic_morph('angry', universal='blink', offsets=vertex()))
        for name in ('angry','blink'):
            self.assertEqual(slot(result,name).reason,'same_source_exact_conflict')
    def test_multiple_angry_candidates_block(self):
        c = slot(get(synthetic_morph('angry', offsets=vertex()), synthetic_morph('angry', offsets=vertex())), 'angry')
        self.assertEqual((c.reason,c.status,c.candidate_indices),
           ('multiple_exact_morph_candidates',SmartMorphCapabilityStatus.BLOCKED,(0,1)))
    def test_unsupported_group_flip_and_material(self):
        for morph_type, offsets in ((0,(build_pmx_group_morph_offset(),)),(8,(build_pmx_material_morph_offset(),))):
            with self.subTest(morph_type=morph_type):
                c = slot(get(synthetic_morph('angry', morph_type=morph_type, offsets=offsets)), 'angry')
                self.assertEqual(c.reason,'morph_type_out_of_scope')

    def test_public_smart_part_detector_does_not_expose_angry(self):
        from mmd_registry.services.structural_authoring_catalog import PmxStructuralAuthoringMorphCatalogEntry
        from mmd_registry.smart_part_detection import detect_smart_parts, _match_smart_part_candidate_traces
        e = PmxStructuralAuthoringMorphCatalogEntry(0, 'angry', '', 'other', 'vertex', 1)
        self.assertEqual(detect_smart_parts((e,)), ())
        self.assertEqual(_match_smart_part_candidate_traces((e,)), ())
        private = inspection.inspect_smart_morphs(
            synthetic_source(synthetic_morph('angry', offsets=vertex())),
            include_angry=True,
        )
        angry = slot(private, 'angry')
        self.assertEqual((angry.status, angry.reason, angry.candidate_indices),
            (SmartMorphCapabilityStatus.SUPPORTED, 'exact_morph_evidence', (0,)))
        self.assertEqual(tuple(t.matched_alias for t in angry.evidence), ('angry',))

    def test_flip_morph_is_unsupported(self):
        from tests.mmd_fixtures import build_pmx_flip_morph_offset
        source = synthetic_source(synthetic_morph('angry', morph_type=9,
            offsets=(build_pmx_flip_morph_offset(),)), version=2.1)
        result = inspection.inspect_smart_morphs(source, include_angry=True)
        c = slot(result, 'angry')
        self.assertEqual((c.status, c.reason),
            (SmartMorphCapabilityStatus.UNSUPPORTED, 'morph_type_out_of_scope'))
    def test_empty_offsets_unsupported(self):
        self.assertEqual(slot(get(synthetic_morph('angry')),'angry').reason,'empty_morph_offsets')
    def test_catalog_mismatch_blocks(self):
        with patch.object(inspection,'_collect_morph_catalog', return_value=()):
            c = slot(get(synthetic_morph('angry', offsets=vertex())),'angry')
        self.assertEqual((c.status,c.reason),(SmartMorphCapabilityStatus.BLOCKED,'source_evidence_mismatch'))
    def test_legacy_default_keeps_two_slots(self):
        result = inspection.inspect_smart_morphs(synthetic_source(synthetic_morph('smile', offsets=vertex())))
        self.assertEqual(tuple(c.capability_kind for c in result.capabilities),('smile','blink'))
        self.assertTrue(slot(result,'smile').supported)
    def test_readonly_immutable_results(self):
        result = get(synthetic_morph('angry', offsets=vertex()))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            slot(result,'angry').reason = 'arbitrary'
    def test_invalid_optin_argument_rejected(self):
        with self.assertRaises(TypeError):
            inspection.inspect_smart_morphs(synthetic_source(), include_angry='yes')
    def test_stable_repeat_and_source_sha(self):
        src = synthetic_source(synthetic_morph('angry', offsets=vertex()))
        first = inspection.inspect_smart_morphs(src, include_angry=True)
        self.assertEqual(first, inspection.inspect_smart_morphs(src, include_angry=True))
        self.assertEqual(first.source_sha256, hashlib.sha256(src).hexdigest())
