from __future__ import annotations

import unittest

import mmd_registry
import mmd_registry.smart_part_detection as detection
import mmd_registry.smart_part_explainability as explainability
from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringMaterialCatalogEntry,
)
from mmd_registry.smart_parts import SmartPartKind


class V09510UnicodeNameHardeningTests(unittest.TestCase):
    def material(
        self,
        *,
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

    def test_nfkc_unicode_whitespace_casefold_exact_alias_semantics_remain_deterministic(
        self,
    ) -> None:
        entries = (
            self.material(source_index=7, local_name="  Ｆａｃｅ　"),
            self.material(source_index=8, local_name="Face"),
            self.material(
                source_index=9,
                local_name="顔",
                universal_name="FACE",
            ),
            self.material(source_index=10, local_name="顔"),
        )

        detected = detection.detect_smart_parts(entries)
        explained = explainability.explain_smart_parts(entries)

        self.assertEqual(
            detected,
            detection.detect_smart_parts(tuple(reversed(entries))),
        )
        self.assertEqual(
            explained,
            explainability.explain_smart_parts(tuple(reversed(entries))),
        )
        self.assertEqual(len(detected), 1)
        self.assertIs(detected[0].kind, SmartPartKind.FACE)
        self.assertEqual(
            tuple(item.source_index for item in detected[0].evidence),
            (7, 8, 9, 9, 10),
        )

        raw_values = tuple(item.source_value for item in explained[0].evidence)
        self.assertIn("  Ｆａｃｅ　", raw_values)
        self.assertIn("Face", raw_values)
        self.assertIn("顔", raw_values)
        self.assertIn("FACE", raw_values)
        self.assertEqual(
            {item.normalized_value for item in explained[0].evidence},
            {"face", "顔"},
        )

    def test_japanese_raw_source_strings_remain_exact_in_provenance(self) -> None:
        local_name = "　顔　"
        universal_name = " FACE "
        entry = self.material(
            source_index=20,
            local_name=local_name,
            universal_name=universal_name,
        )

        before = repr(entry)
        explanation = explainability.explain_smart_parts((entry,))

        self.assertEqual(len(explanation), 1)
        self.assertIs(explanation[0].kind, SmartPartKind.FACE)
        self.assertEqual(
            tuple(item.source_field for item in explanation[0].evidence),
            ("local_name", "universal_name"),
        )
        self.assertEqual(
            tuple(item.source_value for item in explanation[0].evidence),
            (local_name, universal_name),
        )
        self.assertEqual(
            tuple(item.normalized_value for item in explanation[0].evidence),
            ("顔", "face"),
        )
        self.assertEqual(repr(entry), before)
        self.assertEqual(mmd_registry.__all__, ("__version__",))

    def test_localized_universal_disagreement_uses_frozen_conflict_policy(
        self,
    ) -> None:
        conflict = self.material(
            source_index=30,
            local_name="顔",
            universal_name="Hair",
        )
        local_only = self.material(
            source_index=31,
            local_name="顔",
            universal_name="",
        )
        universal_only = self.material(
            source_index=32,
            local_name="",
            universal_name="Face",
        )

        for _ in range(10):
            self.assertEqual(detection.detect_smart_parts((conflict,)), ())
            self.assertEqual(
                explainability.explain_smart_parts((conflict,)),
                (),
            )

        local_detected = detection.detect_smart_parts((local_only,))
        universal_detected = detection.detect_smart_parts((universal_only,))
        self.assertEqual(len(local_detected), 1)
        self.assertEqual(len(universal_detected), 1)
        self.assertIs(local_detected[0].kind, SmartPartKind.FACE)
        self.assertIs(universal_detected[0].kind, SmartPartKind.FACE)

    def test_visually_similar_unicode_does_not_gain_authority_outside_frozen_normalization(
        self,
    ) -> None:
        cyrillic_a = "F\u0430ce"  # Cyrillic small a, not Latin a.
        unicode_punctuation = "Face\u2014"
        entries = (
            self.material(source_index=40, local_name=cyrillic_a),
            self.material(source_index=41, local_name=unicode_punctuation),
        )

        self.assertNotEqual(
            detection._normalize_semantic_text(cyrillic_a),
            "face",
        )
        self.assertNotEqual(
            detection._normalize_semantic_text(unicode_punctuation),
            "face",
        )
        self.assertEqual(detection.detect_smart_parts(entries), ())
        self.assertEqual(explainability.explain_smart_parts(entries), ())
        self.assertEqual(entries[0].local_name, cyrillic_a)
        self.assertEqual(entries[1].local_name, unicode_punctuation)


if __name__ == "__main__":
    unittest.main()
