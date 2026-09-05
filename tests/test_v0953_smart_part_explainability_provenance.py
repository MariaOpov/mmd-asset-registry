from __future__ import annotations

import unittest

import mmd_registry.smart_part_detection as detection
from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringBoneCatalogEntry,
    PmxStructuralAuthoringMaterialCatalogEntry,
    PmxStructuralAuthoringMorphCatalogEntry,
)
from mmd_registry.smart_parts import SmartPartEvidenceKind, SmartPartKind


class SmartPartNamedEntityProvenanceTests(unittest.TestCase):
    def material(
        self,
        *,
        source_index: int = 0,
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
        *,
        source_index: int = 0,
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

    def morph(
        self,
        *,
        source_index: int = 0,
        local_name: str = "",
        universal_name: str = "",
    ) -> PmxStructuralAuthoringMorphCatalogEntry:
        return PmxStructuralAuthoringMorphCatalogEntry(
            source_index=source_index,
            local_name=local_name,
            universal_name=universal_name,
            panel_name="OTHER",
            morph_type_name="VERTEX",
            offset_count=0,
        )

    def test_material_japanese_local_name_provenance_is_exact(self) -> None:
        entry = self.material(source_index=12, local_name="顔")
        before = repr(entry)
        traces = detection._match_smart_part_traces((entry,))
        self.assertEqual(len(traces), 1)
        trace = traces[0]
        self.assertIs(trace.kind, SmartPartKind.FACE)
        self.assertIs(trace.evidence.source_kind, SmartPartEvidenceKind.MATERIAL)
        self.assertEqual(trace.evidence.source_index, 12)
        self.assertEqual(trace.evidence.reason, "material.local_name:exact_alias:face")
        self.assertEqual(trace.source_field, "local_name")
        self.assertEqual(trace.source_value, "顔")
        self.assertEqual(trace.comparison_value, "顔")
        self.assertEqual(trace.normalized_value, "顔")
        self.assertEqual(trace.matched_alias, "顔")
        self.assertEqual(trace.match_rule, "exact_alias")
        self.assertEqual(trace.derivation, ())
        self.assertEqual(repr(entry), before)

    def test_material_english_universal_name_provenance_is_exact(self) -> None:
        entry = self.material(source_index=3, universal_name="Face")
        traces = detection._match_smart_part_traces((entry,))
        self.assertEqual(len(traces), 1)
        trace = traces[0]
        self.assertIs(trace.kind, SmartPartKind.FACE)
        self.assertEqual(trace.source_field, "universal_name")
        self.assertEqual(trace.source_value, "Face")
        self.assertEqual(trace.comparison_value, "Face")
        self.assertEqual(trace.normalized_value, "face")
        self.assertEqual(trace.matched_alias, "face")
        self.assertEqual(trace.evidence.reason, "material.universal_name:exact_alias:face")

    def test_bone_universal_name_retains_raw_whitespace_and_case(self) -> None:
        entry = self.bone(source_index=34, universal_name="  RIGHT\t ARM  ")
        traces = detection._match_smart_part_traces((entry,))
        self.assertEqual(len(traces), 1)
        trace = traces[0]
        self.assertIs(trace.kind, SmartPartKind.ARMS)
        self.assertIs(trace.evidence.source_kind, SmartPartEvidenceKind.BONE)
        self.assertEqual(trace.evidence.source_index, 34)
        self.assertEqual(trace.source_field, "universal_name")
        self.assertEqual(trace.source_value, "  RIGHT\t ARM  ")
        self.assertEqual(trace.comparison_value, "  RIGHT\t ARM  ")
        self.assertEqual(trace.normalized_value, "right arm")
        self.assertEqual(trace.matched_alias, "right arm")
        self.assertEqual(trace.evidence.reason, "bone.universal_name:exact_alias:arms")

    def test_bone_japanese_local_name_provenance_is_exact(self) -> None:
        entry = self.bone(source_index=8, local_name="右腕")
        traces = detection._match_smart_part_traces((entry,))
        self.assertEqual(len(traces), 1)
        trace = traces[0]
        self.assertIs(trace.kind, SmartPartKind.ARMS)
        self.assertEqual(trace.source_field, "local_name")
        self.assertEqual(trace.source_value, "右腕")
        self.assertEqual(trace.normalized_value, "右腕")
        self.assertEqual(trace.matched_alias, "右腕")

    def test_morph_japanese_local_name_provenance_is_exact(self) -> None:
        entry = self.morph(source_index=9, local_name="まばたき")
        traces = detection._match_smart_part_traces((entry,))
        self.assertEqual(len(traces), 1)
        trace = traces[0]
        self.assertIs(trace.kind, SmartPartKind.EYES)
        self.assertIs(trace.evidence.source_kind, SmartPartEvidenceKind.MORPH)
        self.assertEqual(trace.evidence.source_index, 9)
        self.assertEqual(trace.source_field, "local_name")
        self.assertEqual(trace.source_value, "まばたき")
        self.assertEqual(trace.normalized_value, "まばたき")
        self.assertEqual(trace.matched_alias, "まばたき")
        self.assertEqual(trace.evidence.reason, "morph.local_name:exact_alias:eyes")

    def test_morph_english_universal_name_provenance_is_exact(self) -> None:
        entry = self.morph(source_index=10, universal_name="Blink")
        traces = detection._match_smart_part_traces((entry,))
        self.assertEqual(len(traces), 1)
        trace = traces[0]
        self.assertIs(trace.kind, SmartPartKind.EYES)
        self.assertEqual(trace.source_field, "universal_name")
        self.assertEqual(trace.source_value, "Blink")
        self.assertEqual(trace.normalized_value, "blink")
        self.assertEqual(trace.matched_alias, "blink")

    def test_same_kind_local_and_universal_remain_separate_provenance(self) -> None:
        entry = self.material(source_index=21, local_name="顔", universal_name="Face")
        traces = detection._match_smart_part_traces((entry,))
        self.assertEqual(len(traces), 2)
        self.assertEqual(tuple(trace.source_field for trace in traces), ("local_name", "universal_name"))
        self.assertEqual(tuple(trace.source_value for trace in traces), ("顔", "Face"))
        self.assertEqual(
            tuple(trace.evidence.reason for trace in traces),
            (
                "material.local_name:exact_alias:face",
                "material.universal_name:exact_alias:face",
            ),
        )
        self.assertTrue(all(trace.kind is SmartPartKind.FACE for trace in traces))

    def test_unknown_local_does_not_fabricate_provenance_or_block_known_universal(self) -> None:
        entry = self.material(source_index=22, local_name="not-a-semantic-name", universal_name="Face")
        traces = detection._match_smart_part_traces((entry,))
        self.assertEqual(len(traces), 1)
        self.assertEqual(traces[0].source_field, "universal_name")
        self.assertEqual(traces[0].source_value, "Face")

    def test_unknown_universal_does_not_fabricate_provenance_or_block_known_local(self) -> None:
        entry = self.bone(source_index=23, local_name="右腕", universal_name="unknown")
        traces = detection._match_smart_part_traces((entry,))
        self.assertEqual(len(traces), 1)
        self.assertEqual(traces[0].source_field, "local_name")
        self.assertEqual(traces[0].source_value, "右腕")

    def test_conflicting_known_names_emit_no_provenance(self) -> None:
        entry = self.material(source_index=24, local_name="Face", universal_name="Hair")
        self.assertEqual(detection._match_smart_part_traces((entry,)), ())
        self.assertEqual(detection.detect_smart_parts((entry,)), ())

    def test_empty_named_fields_emit_no_provenance(self) -> None:
        entries = (
            self.material(source_index=1),
            self.bone(source_index=2),
            self.morph(source_index=3),
        )
        self.assertEqual(detection._match_smart_part_traces(entries), ())
        self.assertEqual(detection.detect_smart_parts(entries), ())

    def test_unicode_compatibility_and_whitespace_are_explanatory_only(self) -> None:
        raw = "  Ｆａｃｅ　 "
        entry = self.material(source_index=25, local_name=raw)
        before = repr(entry)
        trace = detection._match_smart_part_traces((entry,))[0]
        self.assertEqual(trace.source_value, raw)
        self.assertEqual(trace.comparison_value, raw)
        self.assertEqual(trace.normalized_value, "face")
        self.assertEqual(trace.matched_alias, "face")
        self.assertEqual(entry.local_name, raw)
        self.assertEqual(repr(entry), before)

    def test_named_provenance_is_input_order_independent(self) -> None:
        entries = (
            self.material(source_index=5, universal_name="Face"),
            self.bone(source_index=8, local_name="右腕"),
            self.morph(source_index=9, universal_name="Blink"),
        )
        self.assertEqual(
            detection._match_smart_part_traces(entries),
            detection._match_smart_part_traces(tuple(reversed(entries))),
        )


if __name__ == "__main__":
    unittest.main()
