from __future__ import annotations

import itertools
import json
import os
import subprocess
import sys
import unittest

import mmd_registry.smart_part_confidence as confidence
from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringBoneCatalogEntry,
    PmxStructuralAuthoringMaterialCatalogEntry,
    PmxStructuralAuthoringMorphCatalogEntry,
    PmxStructuralAuthoringTextureCatalogEntry,
)


class SmartPartConfidenceDeterminismTests(unittest.TestCase):
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

    def signature(self, entries) -> tuple[object, ...]:
        return tuple(
            (
                item.confidence.value,
                item.reason,
                tuple(
                    (
                        candidate.kind.value,
                        tuple(
                            (
                                evidence.evidence.source_kind.value,
                                evidence.evidence.source_index,
                                evidence.evidence.reason,
                                evidence.source_field,
                                evidence.source_value,
                                evidence.comparison_value,
                                evidence.normalized_value,
                                evidence.matched_alias,
                                evidence.match_rule,
                                evidence.derivation,
                            )
                            for evidence in candidate.evidence
                        ),
                    )
                    for candidate in item.candidates
                ),
            )
            for item in confidence.assess_smart_parts(entries)
        )

    def representative_entries(self):
        return (
            self.material(1, "Face", "FACE"),
            self.bone(2, "Face"),
            self.texture(3, "hair.png"),
            self.material(10, "Face", "Hair"),
        )

    def test_repeated_calls_are_value_identical(self) -> None:
        entries = self.representative_entries()
        expected = confidence.assess_smart_parts(entries)
        for _ in range(100):
            self.assertEqual(confidence.assess_smart_parts(entries), expected)

    def test_signature_repeated_calls_are_identical(self) -> None:
        entries = self.representative_entries()
        expected = self.signature(entries)
        for _ in range(100):
            self.assertEqual(self.signature(entries), expected)

    def test_reverse_input_order_is_identical(self) -> None:
        entries = self.representative_entries()
        self.assertEqual(
            confidence.assess_smart_parts(entries),
            confidence.assess_smart_parts(tuple(reversed(entries))),
        )

    def test_all_permutations_of_representative_input_are_identical(self) -> None:
        entries = self.representative_entries()
        expected = self.signature(entries)
        for permuted in itertools.permutations(entries):
            self.assertEqual(self.signature(permuted), expected)

    def test_duplicate_normalization_variants_choose_stable_public_evidence(self) -> None:
        entries = (
            self.material(40, "Face"),
            self.material(40, "FACE"),
            self.material(40, "  Ｆａｃｅ　 "),
        )
        expected = self.signature(entries)
        self.assertEqual(
            expected,
            self.signature(tuple(reversed(entries))),
        )
        result = confidence.assess_smart_parts(entries)
        self.assertEqual(len(result), 1)
        self.assertIs(
            result[0].confidence,
            confidence.SmartPartConfidence.MEDIUM,
        )
        evidence = result[0].candidates[0].evidence
        self.assertEqual(len(evidence), 3)
        self.assertEqual(len({item.evidence for item in evidence}), 1)
        self.assertEqual(
            tuple(item.normalized_value for item in evidence),
            ("face", "face", "face"),
        )

    def test_same_source_dual_same_kind_fields_remain_canonical(self) -> None:
        entries = (self.material(41, "顔", "Face"),)
        first = confidence.assess_smart_parts(entries)
        second = confidence.assess_smart_parts(entries)
        self.assertEqual(first, second)
        self.assertEqual(
            tuple(e.source_field for e in first[0].candidates[0].evidence),
            ("local_name", "universal_name"),
        )

    def test_multiple_ambiguities_keep_stable_order(self) -> None:
        entries = (
            self.morph(8, "Blink", "Smile"),
            self.material(9, "Face", "Hair"),
            self.bone(7, "Arm", "Foot"),
            self.material(3, "Face", "Hair"),
        )
        expected = self.signature(entries)
        for permuted in itertools.permutations(entries):
            self.assertEqual(self.signature(permuted), expected)

    def test_resolved_always_precedes_ambiguous(self) -> None:
        entries = (
            self.material(10, "Face", "Hair"),
            self.bone(20, "Arm"),
            self.texture(21, "hair.png"),
        )
        result = confidence.assess_smart_parts(entries)
        self.assertNotEqual(result, ())
        seen_ambiguous = False
        for item in result:
            if item.confidence is confidence.SmartPartConfidence.AMBIGUOUS:
                seen_ambiguous = True
            else:
                self.assertFalse(seen_ambiguous)

    def test_confidence_reasons_are_stable_across_permutations(self) -> None:
        entries = (
            self.material(1, "Face"),
            self.bone(2, "Face"),
            self.texture(3, "hair.png"),
            self.material(10, "Face", "Hair"),
        )
        expected = tuple(item.reason for item in confidence.assess_smart_parts(entries))
        for permuted in itertools.permutations(entries):
            self.assertEqual(
                tuple(item.reason for item in confidence.assess_smart_parts(permuted)),
                expected,
            )

    def test_input_objects_remain_immutable_by_observation(self) -> None:
        entries = self.representative_entries()
        before = repr(entries)
        for _ in range(20):
            confidence.assess_smart_parts(entries)
        self.assertEqual(repr(entries), before)

    def _subprocess_signature(self, seed: str, mode: str) -> str:
        script = r"""
import json, sys
import mmd_registry.smart_part_confidence as c
from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringMaterialCatalogEntry as M,
    PmxStructuralAuthoringBoneCatalogEntry as B,
    PmxStructuralAuthoringMorphCatalogEntry as O,
    PmxStructuralAuthoringTextureCatalogEntry as T,
)

def material(i,l="",u=""):
    return M(source_index=i,local_name=l,universal_name=u,texture_index=-1,sphere_texture_index=-1,surface_index_count=0)
def bone(i,l="",u=""):
    return B(source_index=i,local_name=l,universal_name=u,parent_bone_index=-1,position=(0.0,0.0,0.0),flag_names=())
def morph(i,l="",u=""):
    return O(source_index=i,local_name=l,universal_name=u,panel_name="OTHER",morph_type_name="VERTEX",offset_count=0)
def texture(i,p):
    return T(source_index=i,path=p)

mode=sys.argv[1]
if mode=="mixed":
    entries=(material(1,"Face","FACE"),bone(2,"Face"),texture(3,"hair.png"),material(10,"Face","Hair"))
elif mode=="ambiguity":
    entries=(morph(8,"Blink","Smile"),material(9,"Face","Hair"),bone(7,"Arm","Foot"),material(3,"Face","Hair"))
elif mode=="duplicate":
    entries=(material(40,"Face"),material(40,"FACE"),material(40,"  Ｆａｃｅ　 "))
else:
    raise SystemExit("bad mode")

value=[]
for item in c.assess_smart_parts(entries):
    candidates=[]
    for candidate in item.candidates:
        evidence=[]
        for e in candidate.evidence:
            evidence.append([
                e.evidence.source_kind.value,
                e.evidence.source_index,
                e.evidence.reason,
                e.source_field,
                e.source_value,
                e.comparison_value,
                e.normalized_value,
                e.matched_alias,
                e.match_rule,
                list(e.derivation),
            ])
        candidates.append([candidate.kind.value,evidence])
    value.append([item.confidence.value,item.reason,candidates])
print(json.dumps(value,ensure_ascii=False,separators=(",",":")))
"""
        env = dict(os.environ)
        env["PYTHONHASHSEED"] = seed
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        cp = subprocess.run(
            [sys.executable, "-c", script, mode],
            text=True,
            encoding="utf-8",
            errors="strict",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            check=False,
        )
        self.assertEqual(cp.returncode, 0, cp.stderr)
        return cp.stdout.strip()

    def test_pythonhashseed_mixed_signature_is_identical(self) -> None:
        values = tuple(
            self._subprocess_signature(seed, "mixed")
            for seed in ("0", "1", "2", "42", "31337")
        )
        self.assertEqual(len(set(values)), 1)

    def test_pythonhashseed_ambiguity_signature_is_identical(self) -> None:
        values = tuple(
            self._subprocess_signature(seed, "ambiguity")
            for seed in ("0", "1", "2", "42", "31337")
        )
        self.assertEqual(len(set(values)), 1)

    def test_pythonhashseed_duplicate_signature_is_identical(self) -> None:
        values = tuple(
            self._subprocess_signature(seed, "duplicate")
            for seed in ("0", "1", "2", "42", "31337")
        )
        self.assertEqual(len(set(values)), 1)


if __name__ == "__main__":
    unittest.main()
