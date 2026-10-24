"""v0.9.5.12 private semantic morphology link acceptance tests (synthetic only)."""
from __future__ import annotations
import dataclasses
import hashlib
import unittest
from mmd_registry.services._smart_morph_inspection import inspect_smart_morphs
from mmd_registry._smart_morph_readonly import SmartMorphCapabilityStatus as Status
from mmd_registry.smart_parts import SmartPartKind
from tests.test_v09511_morph_core_inventory import synthetic_source, synthetic_morph
from tests.mmd_fixtures import build_pmx_vertex_morph_offset, build_pmx_bone_morph_offset

V = lambda: (build_pmx_vertex_morph_offset(),)
B = lambda: (build_pmx_bone_morph_offset(),)

def cap(name, *, universal='', morph_type=1, offsets=None):
    offsets = V() if offsets is None else offsets
    data = synthetic_source(synthetic_morph(name, universal=universal, morph_type=morph_type, offsets=offsets))
    return data, inspect_smart_morphs(data)

class V09512PrivateSemanticLinkCertification(unittest.TestCase):
    def test_ac1_smile_face_exact_source(self):
        data, result = cap('smile')
        slot = result.capabilities[0]
        self.assertEqual(slot.part_kind, SmartPartKind.FACE)
        self.assertEqual(slot.capability_kind, 'smile')
        self.assertEqual(slot.reason, 'exact_morph_evidence')
        self.assertEqual(slot.status, Status.SUPPORTED)
        self.assertEqual(slot.candidate_indices, (0,))
        self.assertEqual(result.source_sha256, hashlib.sha256(data).hexdigest())
    def test_ac1_blink_eyes_bone(self):
        data, result = cap('blink', morph_type=2, offsets=B())
        slot = result.capabilities[1]
        self.assertEqual((slot.part_kind, slot.status, slot.candidate_indices),
                         (SmartPartKind.EYES, Status.SUPPORTED, (0,)))
    def test_ac1_japanese_exact_aliases(self):
        for n, i, p in [('笑顔',0,SmartPartKind.FACE),('まばたき',1,SmartPartKind.EYES)]:
            with self.subTest(n=n):
                _, result = cap(n)
                self.assertEqual(result.capabilities[i].part_kind,p)
                self.assertEqual(result.capabilities[i].reason,'exact_morph_evidence')
    def test_ac2_unknown_stays_unsupported(self):
        _, result = cap('unrecognized_morph')
        self.assertEqual(tuple(c.reason for c in result.capabilities),
                         ('no_exact_morph_evidence','no_exact_morph_evidence'))
    def test_ac3_conflict_blocks_not_guesses(self):
        _, result = cap('smile',universal='blink')
        self.assertTrue(all(c.status is Status.BLOCKED for c in result.capabilities))
        self.assertTrue(all(c.reason=='same_source_exact_conflict' for c in result.capabilities))
    def test_ac3_ambiguous_two_candidates_block(self):
        data=synthetic_source(synthetic_morph('smile', offsets=V()),
                              synthetic_morph('smile', offsets=V()))
        result=inspect_smart_morphs(data)
        self.assertEqual(result.capabilities[0].reason,'multiple_exact_morph_candidates')
        self.assertEqual(result.capabilities[0].candidate_indices,(0,1))
    def test_ac4_group_type_not_supported(self):
        _, result=cap('smile',morph_type=0,offsets=())
        self.assertEqual(result.capabilities[0].reason,'morph_type_out_of_scope')
    def test_ac4_empty_offsets_not_supported(self):
        _, result=cap('smile',offsets=())
        self.assertEqual(result.capabilities[0].reason,'empty_morph_offsets')
    def test_ac5_immutable_evidence(self):
        _,result=cap('smile')
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.capabilities[0].part_kind=SmartPartKind.HAIR
    def test_ac6_no_mutating_interface_in_dto(self):
        _,result=cap('smile')
        self.assertFalse(hasattr(result,'apply'))
        self.assertFalse(hasattr(result,'write'))
        self.assertFalse(hasattr(result,'set_weight'))
    def test_ac7_invariant_two_slots_and_no_inferred_extra(self):
        _,result=cap('smile')
        self.assertEqual(tuple(c.capability_kind for c in result.capabilities),('smile','blink'))
        self.assertEqual(result.capabilities[0].part_kind,SmartPartKind.FACE)
        self.assertEqual(result.capabilities[1].part_kind,SmartPartKind.EYES)
    def test_ac8_replay_canonical_unchanged(self):
        data=synthetic_source(synthetic_morph('smile',offsets=V()),
                              synthetic_morph('blink',morph_type=2,offsets=B()))
        self.assertEqual(inspect_smart_morphs(data),inspect_smart_morphs(data))

if __name__ == '__main__': unittest.main()
