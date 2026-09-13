"""v0.9.5.6 semantic material grouping contract tests."""

from __future__ import annotations

import dataclasses
import unittest

import mmd_registry.services._smart_inspection as smart_inspection
from mmd_registry.services._smart_material_draft import (
    SmartMaterialGroup,
    group_smart_materials,
)
from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringMaterialCatalogEntry,
    PmxStructuralAuthoringTextureCatalogEntry,
)
from mmd_registry.smart_parts import SmartPartKind


def material(
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


class SmartMaterialGroupingTests(unittest.TestCase):
    def test_groups_only_exact_material_evidence_in_ascending_source_order(self) -> None:
        result = smart_inspection._analyze_entries(
            (
                material(4, "Hair"),
                material(3, "瞳"),
                material(1, "Eyes"),
            )
        )

        group = group_smart_materials(result, SmartPartKind.EYES)

        self.assertEqual(group.part_kind, SmartPartKind.EYES)
        self.assertEqual(group.material_indices, (1, 3))
        self.assertEqual(
            tuple(item.source_index for item in group.evidence),
            (1, 3),
        )

    def test_texture_only_semantics_do_not_become_material_targets(self) -> None:
        result = smart_inspection._analyze_entries(
            (
                PmxStructuralAuthoringTextureCatalogEntry(
                    source_index=0,
                    path="textures/eyes.png",
                ),
            )
        )

        group = group_smart_materials(result, SmartPartKind.EYES)

        self.assertEqual(group.material_indices, ())
        self.assertEqual(group.evidence, ())

    def test_duplicate_exact_evidence_collapses_to_one_material_identity(self) -> None:
        duplicate = material(2, "Eyes")
        result = smart_inspection._analyze_entries((duplicate, duplicate))

        group = group_smart_materials(result, SmartPartKind.EYES)

        self.assertEqual(group.material_indices, (2,))
        self.assertEqual(len(group.evidence), 1)

    def test_group_is_frozen(self) -> None:
        result = smart_inspection._analyze_entries((material(0, "Eyes"),))
        group = group_smart_materials(result, SmartPartKind.EYES)

        with self.assertRaises(dataclasses.FrozenInstanceError):
            group.material_indices = ()  # type: ignore[misc]
        self.assertIsInstance(group, SmartMaterialGroup)


if __name__ == "__main__":
    unittest.main()
