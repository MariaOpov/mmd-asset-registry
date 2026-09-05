from __future__ import annotations

import unittest

import mmd_registry.smart_part_detection as detection
from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringTextureCatalogEntry,
)
from mmd_registry.smart_parts import SmartPartEvidenceKind, SmartPartKind


class SmartPartTextureProvenanceTests(unittest.TestCase):
    def texture(
        self,
        *,
        source_index: int = 0,
        path: str = "",
    ) -> PmxStructuralAuthoringTextureCatalogEntry:
        return PmxStructuralAuthoringTextureCatalogEntry(
            source_index=source_index,
            path=path,
        )

    def test_windows_path_preserves_original_path_and_exact_derivation(self) -> None:
        entry = self.texture(
            source_index=5,
            path=r"textures\Face.png",
        )
        before = repr(entry)

        traces = detection._match_smart_part_traces((entry,))

        self.assertEqual(len(traces), 1)
        trace = traces[0]
        self.assertIs(trace.kind, SmartPartKind.FACE)
        self.assertIs(trace.evidence.source_kind, SmartPartEvidenceKind.TEXTURE)
        self.assertEqual(trace.evidence.source_index, 5)
        self.assertEqual(
            trace.evidence.reason,
            "texture.path:exact_alias:face",
        )
        self.assertEqual(trace.source_field, "path")
        self.assertEqual(trace.source_value, r"textures\Face.png")
        self.assertEqual(trace.comparison_value, "Face")
        self.assertEqual(trace.normalized_value, "face")
        self.assertEqual(trace.matched_alias, "face")
        self.assertEqual(trace.match_rule, "exact_alias")
        self.assertEqual(
            trace.derivation,
            (("basename", "Face.png"), ("basename_stem", "Face")),
        )
        self.assertEqual(repr(entry), before)

    def test_forward_slash_path_uses_final_basename_only(self) -> None:
        entry = self.texture(
            source_index=6,
            path="assets/materials/hair.png",
        )
        traces = detection._match_smart_part_traces((entry,))

        self.assertEqual(len(traces), 1)
        trace = traces[0]
        self.assertIs(trace.kind, SmartPartKind.HAIR)
        self.assertEqual(trace.source_value, "assets/materials/hair.png")
        self.assertEqual(trace.comparison_value, "hair")
        self.assertEqual(
            trace.derivation,
            (("basename", "hair.png"), ("basename_stem", "hair")),
        )

    def test_parent_directory_has_no_semantic_authority(self) -> None:
        entry = self.texture(
            source_index=7,
            path="face/unknown.png",
        )

        self.assertEqual(detection._match_smart_part_traces((entry,)), ())
        self.assertEqual(detection.detect_smart_parts((entry,)), ())

    def test_final_extension_only_is_removed(self) -> None:
        entry = self.texture(
            source_index=8,
            path="textures/Face.diffuse.png",
        )

        self.assertEqual(
            detection._texture_basename_and_stem(entry.path),
            ("Face.diffuse.png", "Face.diffuse"),
        )
        self.assertEqual(detection._match_smart_part_traces((entry,)), ())
        self.assertEqual(detection.detect_smart_parts((entry,)), ())

    def test_extensionless_texture_name_is_valid_comparison_value(self) -> None:
        entry = self.texture(
            source_index=9,
            path="textures/hair",
        )
        traces = detection._match_smart_part_traces((entry,))

        self.assertEqual(len(traces), 1)
        trace = traces[0]
        self.assertIs(trace.kind, SmartPartKind.HAIR)
        self.assertEqual(trace.comparison_value, "hair")
        self.assertEqual(
            trace.derivation,
            (("basename", "hair"), ("basename_stem", "hair")),
        )

    def test_nfkc_casefold_and_whitespace_apply_to_stem_not_original_path(self) -> None:
        raw = "textures/  Ｆａｃｅ　.PNG"
        entry = self.texture(source_index=10, path=raw)
        before = repr(entry)

        traces = detection._match_smart_part_traces((entry,))

        self.assertEqual(len(traces), 1)
        trace = traces[0]
        self.assertIs(trace.kind, SmartPartKind.FACE)
        self.assertEqual(trace.source_value, raw)
        self.assertEqual(trace.comparison_value, "  Ｆａｃｅ　")
        self.assertEqual(trace.normalized_value, "face")
        self.assertEqual(trace.matched_alias, "face")
        self.assertEqual(
            trace.derivation,
            (
                ("basename", "  Ｆａｃｅ　.PNG"),
                ("basename_stem", "  Ｆａｃｅ　"),
            ),
        )
        self.assertEqual(entry.path, raw)
        self.assertEqual(repr(entry), before)

    def test_texture_unknown_name_emits_no_trace_or_evidence(self) -> None:
        entry = self.texture(
            source_index=11,
            path="textures/not-a-smart-part.png",
        )

        self.assertEqual(detection._match_smart_part_traces((entry,)), ())
        self.assertEqual(detection.detect_smart_parts((entry,)), ())

    def test_texture_empty_basename_semantics_emit_no_trace(self) -> None:
        entries = (
            self.texture(source_index=12, path=""),
            self.texture(source_index=13, path="folder/"),
            self.texture(source_index=14, path="folder\\"),
        )

        self.assertEqual(detection._match_smart_part_traces(entries), ())
        self.assertEqual(detection.detect_smart_parts(entries), ())

    def test_texture_source_index_is_preserved_in_evidence(self) -> None:
        entry = self.texture(source_index=42, path="eye.png")

        trace = detection._match_smart_part_traces((entry,))[0]

        self.assertIs(trace.kind, SmartPartKind.EYES)
        self.assertEqual(trace.evidence.source_index, 42)
        self.assertEqual(
            trace.evidence.reason,
            "texture.path:exact_alias:eyes",
        )

    def test_texture_trace_order_is_input_order_independent(self) -> None:
        entries = (
            self.texture(source_index=3, path="hair.png"),
            self.texture(source_index=1, path="eye.png"),
            self.texture(source_index=2, path="face.png"),
        )

        self.assertEqual(
            detection._match_smart_part_traces(entries),
            detection._match_smart_part_traces(tuple(reversed(entries))),
        )

    def test_detector_projection_matches_texture_trace_evidence_exactly(self) -> None:
        entries = (
            self.texture(source_index=1, path="face.png"),
            self.texture(source_index=2, path="hair.png"),
            self.texture(source_index=3, path="eye.png"),
        )
        traces = detection._match_smart_part_traces(entries)
        detected = detection.detect_smart_parts(entries)

        detected_evidence = tuple(
            evidence
            for part in detected
            for evidence in part.evidence
        )
        trace_evidence = tuple(trace.evidence for trace in traces)

        self.assertEqual(set(detected_evidence), set(trace_evidence))
        self.assertEqual(len(detected_evidence), len(trace_evidence))


if __name__ == "__main__":
    unittest.main()
