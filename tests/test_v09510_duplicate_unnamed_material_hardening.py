from __future__ import annotations

import unittest

import mmd_registry.smart_part_detection as detection
import mmd_registry.smart_part_explainability as explainability
from mmd_registry.services import _smart_inspection
from mmd_registry.services._smart_inspection import SmartInspectionResult
from mmd_registry.services import _smart_material_draft
from mmd_registry.services._smart_material_draft import (
    SmartMaterialCapabilityStatus,
)
from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringMaterialCatalogEntry,
)
from mmd_registry.smart_parts import (
    SmartPart,
    SmartPartEvidence,
    SmartPartEvidenceKind,
    SmartPartKind,
)


class V09510DuplicateUnnamedMaterialHardeningTests(unittest.TestCase):
    def material(
        self,
        *,
        source_index: int,
        local_name: str = "",
        universal_name: str = "",
        texture_index: int = -1,
        sphere_texture_index: int = -1,
        surface_index_count: int = 0,
    ) -> PmxStructuralAuthoringMaterialCatalogEntry:
        return PmxStructuralAuthoringMaterialCatalogEntry(
            source_index=source_index,
            local_name=local_name,
            universal_name=universal_name,
            texture_index=texture_index,
            sphere_texture_index=sphere_texture_index,
            surface_index_count=surface_index_count,
        )

    def test_duplicate_material_names_preserve_distinct_source_indices(self) -> None:
        entries = (
            self.material(
                source_index=7,
                local_name="Face",
                universal_name="顔",
                texture_index=3,
                surface_index_count=9,
            ),
            self.material(
                source_index=2,
                local_name="Face",
                universal_name="顔",
                texture_index=8,
                surface_index_count=12,
            ),
        )

        forward = _smart_inspection._analyze_entries(entries)
        reverse = _smart_inspection._analyze_entries(tuple(reversed(entries)))

        self.assertEqual(forward.parts, reverse.parts)
        self.assertEqual(forward.explanations, reverse.explanations)

        group = _smart_material_draft.group_smart_materials(
            forward,
            SmartPartKind.FACE,
        )
        self.assertEqual(group.material_indices, (2, 7))
        self.assertEqual(
            tuple(sorted({item.source_index for item in group.evidence})),
            (2, 7),
        )
        self.assertNotEqual(entries[0].texture_index, entries[1].texture_index)
        self.assertNotEqual(
            entries[0].surface_index_count,
            entries[1].surface_index_count,
        )

    def test_duplicate_equivalent_evidence_does_not_multiply_edits(self) -> None:
        entries = (
            self.material(source_index=40, local_name="Face"),
            self.material(source_index=40, local_name="FACE"),
            self.material(source_index=40, local_name="  Ｆａｃｅ　"),
        )

        result = _smart_inspection._analyze_entries(entries)
        group = _smart_material_draft.group_smart_materials(
            result,
            SmartPartKind.FACE,
        )
        capability = _smart_material_draft.discover_smart_material_capability(
            result,
            SmartPartKind.FACE,
        )

        self.assertEqual(group.material_indices, (40,))
        self.assertEqual(len(group.evidence), 1)
        self.assertEqual(
            tuple(item.source_index for item in group.evidence),
            (40,),
        )
        self.assertIs(
            capability.status,
            SmartMaterialCapabilityStatus.SUPPORTED,
        )
        self.assertEqual(capability.material_indices, (40,))

    def test_unnamed_material_without_exact_evidence_gains_no_authority(self) -> None:
        entries = (
            self.material(
                source_index=50,
                local_name="",
                universal_name="",
            ),
            self.material(
                source_index=51,
                local_name="   ",
                universal_name="　",
            ),
        )

        result = _smart_inspection._analyze_entries(entries)

        self.assertEqual(detection.detect_smart_parts(entries), ())
        self.assertEqual(explainability.explain_smart_parts(entries), ())
        self.assertEqual(result.parts, ())

        capability = _smart_material_draft.discover_smart_material_capability(
            result,
            SmartPartKind.FACE,
        )
        self.assertIs(
            capability.status,
            SmartMaterialCapabilityStatus.UNSUPPORTED,
        )
        self.assertEqual(capability.reason, "no_exact_material_evidence")
        self.assertEqual(capability.material_indices, ())
        self.assertEqual(capability.evidence, ())

    def test_unnamed_exact_identity_can_remain_targetable_when_certified_evidence_is_present(
        self,
    ) -> None:
        entry = self.material(
            source_index=60,
            local_name="",
            universal_name="",
        )
        evidence = SmartPartEvidence(
            source_kind=SmartPartEvidenceKind.MATERIAL,
            source_index=60,
            reason="certified_exact_material_identity",
        )
        result = SmartInspectionResult(
            entries=(entry,),
            parts=(
                SmartPart(
                    kind=SmartPartKind.FACE,
                    evidence=(evidence,),
                ),
            ),
            explanations=(),
            assessments=(),
        )

        expected_group = _smart_material_draft.group_smart_materials(
            result,
            SmartPartKind.FACE,
        )
        expected_capability = (
            _smart_material_draft.discover_smart_material_capability(
                result,
                SmartPartKind.FACE,
            )
        )

        self.assertEqual(expected_group.material_indices, (60,))
        self.assertEqual(expected_group.evidence, (evidence,))
        self.assertIs(
            expected_capability.status,
            SmartMaterialCapabilityStatus.SUPPORTED,
        )
        self.assertEqual(
            expected_capability.reason,
            "exact_material_evidence",
        )
        self.assertEqual(expected_capability.material_indices, (60,))
        self.assertEqual(expected_capability.evidence, (evidence,))

        for _ in range(20):
            self.assertEqual(
                _smart_material_draft.group_smart_materials(
                    result,
                    SmartPartKind.FACE,
                ),
                expected_group,
            )
            self.assertEqual(
                _smart_material_draft.discover_smart_material_capability(
                    result,
                    SmartPartKind.FACE,
                ),
                expected_capability,
            )


if __name__ == "__main__":
    unittest.main()
