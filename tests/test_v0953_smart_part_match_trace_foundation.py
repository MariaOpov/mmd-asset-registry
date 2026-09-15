from __future__ import annotations

import dataclasses
import unittest

import mmd_registry
import mmd_registry.smart_part_detection as detection
from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringBoneCatalogEntry,
    PmxStructuralAuthoringMaterialCatalogEntry,
    PmxStructuralAuthoringRigidBodyCatalogEntry,
    PmxStructuralAuthoringTextureCatalogEntry,
    PmxStructuralAuthoringVertexCatalogEntry,
)
from mmd_registry.smart_parts import (
    SmartPart,
    SmartPartEvidence,
    SmartPartEvidenceKind,
    SmartPartKind,
)


class SmartPartMatchTraceFoundationTests(unittest.TestCase):
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

    def test_private_trace_is_frozen_slotted_hashable_and_fields_are_exact(self) -> None:
        evidence = SmartPartEvidence(
            SmartPartEvidenceKind.MATERIAL,
            7,
            "material.local_name:exact_alias:face",
        )
        trace = detection._SmartPartMatchTrace(
            kind=SmartPartKind.FACE,
            evidence=evidence,
            source_field="local_name",
            source_value="顔",
            comparison_value="顔",
            normalized_value="顔",
            matched_alias="顔",
            match_rule="exact_alias",
            derivation=(),
        )
        self.assertEqual(
            tuple(field.name for field in dataclasses.fields(trace)),
            (
                "kind",
                "evidence",
                "source_field",
                "source_value",
                "comparison_value",
                "normalized_value",
                "matched_alias",
                "match_rule",
                "derivation",
            ),
        )
        self.assertIn(trace, {trace})
        with self.assertRaises(dataclasses.FrozenInstanceError):
            trace.source_field = "changed"  # type: ignore[misc]

    def test_exact_alias_match_returns_kind_normalized_value_and_actual_alias(self) -> None:
        match = detection._exact_alias_match_from_index(
            "  Ｆａｃｅ　 ",
            detection._MATERIAL_ALIAS_INDEX,
        )
        self.assertEqual(match, (SmartPartKind.FACE, "face", "face"))
        self.assertIs(
            detection._exact_alias_kind_from_index(
                "  Ｆａｃｅ　 ",
                detection._MATERIAL_ALIAS_INDEX,
            ),
            SmartPartKind.FACE,
        )

    def test_named_trace_preserves_raw_and_derived_match_values(self) -> None:
        entry = self.material(
            source_index=7,
            local_name="  Ｆａｃｅ　 ",
            universal_name="unknown",
        )
        before = repr(entry)
        traces = detection._match_smart_part_traces((entry,))
        self.assertEqual(len(traces), 1)
        trace = traces[0]
        self.assertIs(trace.kind, SmartPartKind.FACE)
        self.assertEqual(
            trace.evidence,
            SmartPartEvidence(
                SmartPartEvidenceKind.MATERIAL,
                7,
                "material.local_name:exact_alias:face",
            ),
        )
        self.assertEqual(trace.source_field, "local_name")
        self.assertEqual(trace.source_value, "  Ｆａｃｅ　 ")
        self.assertEqual(trace.comparison_value, "  Ｆａｃｅ　 ")
        self.assertEqual(trace.normalized_value, "face")
        self.assertEqual(trace.matched_alias, "face")
        self.assertEqual(trace.match_rule, "exact_alias")
        self.assertEqual(trace.derivation, ())
        self.assertEqual(repr(entry), before)

    def test_same_kind_local_and_universal_names_remain_separate_traces(self) -> None:
        entry = self.material(
            source_index=12,
            local_name="顔",
            universal_name="Face",
        )
        traces = detection._match_smart_part_traces((entry,))
        self.assertEqual(len(traces), 2)
        self.assertEqual(
            tuple(trace.source_field for trace in traces),
            ("local_name", "universal_name"),
        )
        self.assertEqual(
            tuple(trace.evidence.reason for trace in traces),
            (
                "material.local_name:exact_alias:face",
                "material.universal_name:exact_alias:face",
            ),
        )
        self.assertTrue(all(trace.kind is SmartPartKind.FACE for trace in traces))

    def test_named_conflict_emits_zero_trace_and_zero_detector_evidence(self) -> None:
        entry = self.material(
            source_index=2,
            local_name="Face",
            universal_name="Hair",
        )
        self.assertEqual(detection._match_smart_part_traces((entry,)), ())
        self.assertEqual(detection.detect_smart_parts((entry,)), ())

    def test_texture_trace_preserves_path_and_derivation(self) -> None:
        entry = PmxStructuralAuthoringTextureCatalogEntry(
            source_index=5,
            path=r"textures\Face.png",
        )
        before = repr(entry)
        traces = detection._match_smart_part_traces((entry,))
        self.assertEqual(len(traces), 1)
        trace = traces[0]
        self.assertIs(trace.kind, SmartPartKind.FACE)
        self.assertEqual(
            trace.evidence,
            SmartPartEvidence(
                SmartPartEvidenceKind.TEXTURE,
                5,
                "texture.path:exact_alias:face",
            ),
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

    def test_texture_parent_directory_has_no_semantic_authority(self) -> None:
        entry = PmxStructuralAuthoringTextureCatalogEntry(
            source_index=6,
            path=r"face\unknown.png",
        )
        self.assertEqual(detection._match_smart_part_traces((entry,)), ())
        self.assertEqual(detection.detect_smart_parts((entry,)), ())

    def test_vertex_and_rigid_body_remain_no_lexical_authority(self) -> None:
        vertex = PmxStructuralAuthoringVertexCatalogEntry(
            source_index=0,
            position=(0.0, 0.0, 0.0),
            deform_type=0,
        )
        rigid = PmxStructuralAuthoringRigidBodyCatalogEntry(
            source_index=1,
            local_name="Face",
            universal_name="Face",
            bone_index=-1,
            shape_name="SPHERE",
            physics_mode_name="BONE_FOLLOW",
        )
        self.assertEqual(
            detection._match_smart_part_traces((vertex, rigid)),
            (),
        )

    def test_trace_order_is_input_permutation_independent(self) -> None:
        entries = (
            self.material(source_index=3, universal_name="Face"),
            self.bone(source_index=4, universal_name="Right Arm"),
            PmxStructuralAuthoringTextureCatalogEntry(
                source_index=1,
                path="eye.png",
            ),
        )
        self.assertEqual(
            detection._match_smart_part_traces(entries),
            detection._match_smart_part_traces(tuple(reversed(entries))),
        )

    def test_detector_is_projection_of_shared_trace_authority(self) -> None:
        entries = (
            self.material(
                source_index=2,
                local_name="顔",
                universal_name="Face",
            ),
            self.bone(source_index=4, universal_name="Right Arm"),
            PmxStructuralAuthoringTextureCatalogEntry(
                source_index=1,
                path=r"textures\eye.png",
            ),
        )
        traces = detection._match_smart_part_traces(entries)
        projected = detection._aggregate_parts(
            tuple(
                SmartPart(
                    kind=trace.kind,
                    evidence=(trace.evidence,),
                )
                for trace in traces
            )
        )
        self.assertEqual(projected, detection.detect_smart_parts(entries))

    def test_public_surfaces_and_version_remain_v0952_compatible(self) -> None:
        self.assertEqual(mmd_registry.__all__, ("__version__",))
        self.assertEqual(mmd_registry.__version__, "0.9.5.9")
        self.assertEqual(detection.__all__, ("detect_smart_parts",))
        self.assertFalse(hasattr(mmd_registry, "_SmartPartMatchTrace"))
        self.assertFalse(hasattr(mmd_registry, "_match_smart_part_traces"))


if __name__ == "__main__":
    unittest.main()
