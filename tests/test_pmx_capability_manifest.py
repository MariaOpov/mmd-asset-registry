"""Contract tests for the internal PMX capability manifest."""

from __future__ import annotations

import os
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import patch

from mmd_registry.capabilities import (
    PmxCapabilityManifest,
    get_pmx_capability_manifest,
)
from mmd_registry.pmx.document import (
    SUPPORTED_PMX_VERSIONS,
    VALID_PMX_INDEX_SIZES,
    VALID_PMX_TEXT_ENCODINGS,
)
from mmd_registry.pmx.editing.catalog import get_pmx_edit_operation_catalog


class PmxCapabilityManifestTests(unittest.TestCase):
    def test_manifest_derives_authoritative_core_capabilities(self) -> None:
        manifest = get_pmx_capability_manifest()

        self.assertEqual(manifest.pmx_versions, tuple(SUPPORTED_PMX_VERSIONS))
        self.assertEqual(
            manifest.text_encodings,
            tuple(sorted(VALID_PMX_TEXT_ENCODINGS)),
        )
        self.assertEqual(manifest.index_sizes, tuple(sorted(VALID_PMX_INDEX_SIZES)))
        self.assertEqual(manifest.deform_types, (0, 1, 2, 3, 4))
        self.assertEqual(manifest.morph_types, tuple(range(11)))
        self.assertTrue(manifest.soft_body_support)
        self.assertEqual(
            manifest.roundtrip_contract,
            "validated_semantic_roundtrip",
        )
        self.assertTrue(manifest.texture_portability)
        self.assertFalse(manifest.private_runtime_required)
        self.assertTrue(manifest.structural_preview)
        self.assertTrue(manifest.structural_write)
        self.assertEqual(
            manifest.structural_target_kinds,
            ("vertex", "texture", "material", "bone", "morph", "rigid_body"),
        )
        self.assertEqual(manifest.structural_contract, "reference_safe_execution")

    def test_edit_operations_come_from_authoritative_catalog(self) -> None:
        manifest = get_pmx_capability_manifest()
        catalog = get_pmx_edit_operation_catalog()

        self.assertEqual(
            manifest.edit_operation_types,
            tuple(operation.operation_type for operation in catalog.operations),
        )
        self.assertEqual(
            manifest.edit_operation_types,
            ("set_model_info", "set_texture_path", "update_material"),
        )

    def test_manifest_is_immutable_and_repeatable(self) -> None:
        first = get_pmx_capability_manifest()
        second = get_pmx_capability_manifest()

        self.assertEqual(first, second)
        self.assertEqual(first.to_dict(), second.to_dict())
        with self.assertRaises(FrozenInstanceError):
            first.private_runtime_required = True  # type: ignore[misc]

    def test_manifest_is_independent_of_private_runtime_environment(self) -> None:
        baseline = get_pmx_capability_manifest()

        with patch.dict(
            os.environ,
            {"MMD_REGISTRY_PRIVATE_PMX": r"C:\private\fixture.pmx"},
            clear=False,
        ):
            enabled_environment = get_pmx_capability_manifest()

        self.assertEqual(enabled_environment, baseline)
        self.assertFalse(enabled_environment.private_runtime_required)

    def test_to_dict_has_stable_primitive_shape(self) -> None:
        manifest = get_pmx_capability_manifest()

        self.assertEqual(
            manifest.to_dict(),
            {
                "pmx_versions": [2.0, 2.1],
                "text_encodings": ["utf-16-le", "utf-8"],
                "index_sizes": [1, 2, 4],
                "deform_types": [0, 1, 2, 3, 4],
                "morph_types": list(range(11)),
                "soft_body_support": True,
                "roundtrip_contract": "validated_semantic_roundtrip",
                "edit_operation_types": [
                    "set_model_info",
                    "set_texture_path",
                    "update_material",
                ],
                "texture_portability": True,
                "private_runtime_required": False,
                "structural_preview": True,
                "structural_write": True,
                "structural_target_kinds": [
                    "vertex",
                    "texture",
                    "material",
                    "bone",
                    "morph",
                    "rigid_body",
                ],
                "structural_contract": "reference_safe_execution",
                "structural_insert": True,
            },
        )

    def test_constructor_remains_typed_and_explicit(self) -> None:
        manifest = get_pmx_capability_manifest()

        self.assertIsInstance(manifest, PmxCapabilityManifest)


if __name__ == "__main__":
    unittest.main()
