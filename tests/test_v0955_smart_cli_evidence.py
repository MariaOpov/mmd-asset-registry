"""Tests for v0.9.5.5 Smart Inspect explainability/evidence presentation."""

from __future__ import annotations

import unittest

import mmd_registry.smart_cli as smart_cli
from mmd_registry.services import _smart_inspection as smart_inspection
from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringBoneCatalogEntry,
    PmxStructuralAuthoringMaterialCatalogEntry,
)


class SmartCliExplainabilityEvidenceTests(unittest.TestCase):
    def material(
        self,
        source_index: int,
        local_name: str,
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
        local_name: str,
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

    def test_resolved_output_renders_concise_authoritative_evidence(self) -> None:
        result = smart_inspection._analyze_entries(
            (
                self.material(2, "瞳"),
                self.bone(4, "左目"),
            )
        )

        output = smart_cli._render_basic_text(result)

        self.assertIn("Eyes", output)
        self.assertIn("HIGH", output)
        self.assertIn("  Evidence:\n", output)

        explanation = next(
            item for item in result.explanations if item.kind.value == "eyes"
        )
        self.assertGreaterEqual(len(explanation.evidence), 2)

        positions: list[int] = []
        for item in explanation.evidence:
            expected = smart_cli._render_evidence_item(item)
            self.assertIn(expected + "\n", output)
            positions.append(output.index(expected))

            self.assertIn(
                f"{item.evidence.source_kind.value}[{item.evidence.source_index}]",
                expected,
            )
            self.assertIn(item.source_field, expected)
            self.assertIn(item.source_value, expected)
            self.assertIn(item.matched_alias, expected)

        self.assertEqual(positions, sorted(positions))

    def test_rendered_resolved_provenance_is_exactly_from_explainability_authority(
        self,
    ) -> None:
        result = smart_inspection._analyze_entries(
            (
                self.material(10, "Eyes"),
                self.bone(11, "right eye"),
            )
        )

        explanation = next(
            item for item in result.explanations if item.kind.value == "eyes"
        )
        rendered = tuple(
            smart_cli._render_evidence_item(item)
            for item in explanation.evidence
        )
        output = smart_cli._render_basic_text(result)

        evidence_lines = tuple(
            line
            for line in output.splitlines()
            if line.startswith("    ")
        )
        self.assertEqual(evidence_lines, rendered)

        for source, line in zip(explanation.evidence, evidence_lines, strict=True):
            self.assertIn(source.evidence.reason.split(":")[0].split(".")[0], line)
            self.assertIn(source.source_field, line)
            self.assertIn(source.source_value, line)
            self.assertIn(source.matched_alias, line)

    def test_cp07_resolved_explanations_remain_separate_from_ambiguity(
        self,
    ) -> None:
        result = smart_inspection._analyze_entries(
            (self.material(7, "Face", "Hair"),)
        )

        self.assertEqual(result.explanations, ())
        output = smart_cli._render_basic_text(result)

        self.assertIn("Hair / Face", output)
        self.assertIn("AMBIGUOUS", output)


if __name__ == "__main__":
    unittest.main()
