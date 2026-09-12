"""Tests for v0.9.5.5 basic deterministic Smart Inspect output."""

from __future__ import annotations

import unittest

import mmd_registry.smart_cli as smart_cli
from mmd_registry.services import _smart_inspection as smart_inspection
from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringBoneCatalogEntry,
    PmxStructuralAuthoringMaterialCatalogEntry,
)


class SmartCliBasicOutputTests(unittest.TestCase):
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

    def test_resolved_output_shows_semantic_label_and_confidence_only(self) -> None:
        result = smart_inspection._analyze_entries(
            (
                self.material(2, "瞳"),
                self.bone(4, "左目"),
            )
        )

        output = smart_cli._render_basic_text(result)

        self.assertTrue(output.startswith("SMART PART INSPECTION\n"))
        self.assertIn("Eyes", output)
        self.assertIn("HIGH", output)
        self.assertIn("Evidence:", output)
        self.assertNotIn("safe to edit", output.casefold())
        self.assertNotIn("permission", output.casefold())

    def test_no_detection_is_successful_human_readable_state(self) -> None:
        result = smart_inspection._analyze_entries(())

        self.assertEqual(
            smart_cli._render_basic_text(result),
            "SMART PART INSPECTION\nNo Smart Parts detected.\n",
        )

    def test_basic_ambiguous_output_exposes_all_candidates_without_winner(self) -> None:
        result = smart_inspection._analyze_entries(
            (self.material(7, "Face", "Hair"),)
        )

        output = smart_cli._render_basic_text(result)

        self.assertIn("Hair", output)
        self.assertIn("Face", output)
        self.assertIn("AMBIGUOUS", output)
        self.assertIn("Hair / Face", output)
        self.assertNotRegex(output, r"(?m)^Hair\s+(HIGH|MEDIUM|LOW)$")
        self.assertNotRegex(output, r"(?m)^Face\s+(HIGH|MEDIUM|LOW)$")

    def test_display_vocabulary_uses_human_semantic_clothing_label(self) -> None:
        result = smart_inspection._analyze_entries(
            (self.material(9, "服"),)
        )
        output = smart_cli._render_basic_text(result)

        self.assertIn("Clothes", output)
        self.assertIn("MEDIUM", output)


if __name__ == "__main__":
    unittest.main()
