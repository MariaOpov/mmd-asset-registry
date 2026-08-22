"""CP24 v0.9.2 capability-promotion contract tests."""

from __future__ import annotations

import importlib
import unittest
from dataclasses import fields

import mmd_registry
import mmd_registry.capabilities as capabilities
import mmd_registry.services as services
from mmd_registry.constants import LATEST_SCHEMA_VERSION, SUPPORTED_SCHEMA_VERSIONS
from mmd_registry.pmx.editing.plan import PMX_EDIT_PLAN_SCHEMA_VERSION


ROOT_SERVICE_EXPORTS = (
    "PmxDocumentMetadata",
    "PmxDocumentValidationResult",
    "apply_edit",
    "get_capabilities",
    "inspect_document",
    "load_document",
    "preview_edit",
    "validate_document",
    "PmxReferenceAnalysisResult",
    "PmxReferenceDiagnostic",
    "PmxReferenceDiagnosticCode",
    "PmxReferenceImpact",
    "PmxReferenceNode",
    "PmxReferenceTargetKind",
    "analyze_reference_node",
    "analyze_references",
    "PmxStructuralCollectionEdit",
    "PmxStructuralPreviewRequest",
    "PmxStructuralPreviewResult",
    "preview_structural_edit",
    "PmxStructuralEditRequest",
    "PmxStructuralExecutionResult",
    "apply_structural_edit",
)

PUBLIC_VOCABULARY = {
    "structural_reference": ("PmxStructuralNewReference",),
    "structural_texture": ("PmxStructuralTextureInsertion",),
    "structural_material": ("PmxStructuralMaterialInsertion",),
    "structural_bone": (
        "PmxStructuralBoneIkLink",
        "PmxStructuralBoneIk",
        "PmxStructuralBoneInsertion",
    ),
    "structural_morph": (
        "PmxStructuralMorphGroupOffset",
        "PmxStructuralMorphVertexOffset",
        "PmxStructuralMorphBoneOffset",
        "PmxStructuralMorphUvOffset",
        "PmxStructuralMorphMaterialOffset",
        "PmxStructuralMorphFlipOffset",
        "PmxStructuralMorphImpulseOffset",
        "PmxStructuralMorphInsertion",
    ),
    "structural_rigid_body": ("PmxStructuralRigidBodyInsertion",),
    "structural_vertex": (
        "PmxStructuralVertexBdef1",
        "PmxStructuralVertexBdef2",
        "PmxStructuralVertexBdef4",
        "PmxStructuralVertexSdef",
        "PmxStructuralVertexQdef",
        "PmxStructuralVertexInsertion",
    ),
}


class V092CapabilityPromotionTests(unittest.TestCase):
    def test_version_and_schema_promotion_are_independent(self) -> None:
        self.assertEqual(mmd_registry.__version__, "0.9.2")
        self.assertEqual(PMX_EDIT_PLAN_SCHEMA_VERSION, 1)
        self.assertEqual(LATEST_SCHEMA_VERSION, "0.3")
        self.assertEqual(SUPPORTED_SCHEMA_VERSIONS, frozenset(("0.2", "0.3")))

    def test_canonical_manifest_promotes_only_structural_insert_dimension(self) -> None:
        manifest = capabilities.get_capabilities()
        payload = manifest.to_dict()

        self.assertTrue(manifest.structural_preview)
        self.assertTrue(manifest.structural_write)
        self.assertTrue(manifest.structural_insert)
        self.assertEqual(manifest.structural_contract, "reference_safe_execution")
        self.assertEqual(
            manifest.structural_target_kinds,
            ("vertex", "texture", "material", "bone", "morph", "rigid_body"),
        )
        self.assertIs(payload["structural_insert"], True)
        self.assertEqual(list(payload)[-1], "structural_insert")
        self.assertEqual(
            capabilities.get_pmx_capability_manifest().to_dict(),
            payload,
        )

    def test_legacy_manifest_constructor_defaults_structural_insert_false(self) -> None:
        legacy = capabilities.PmxCapabilityManifest(
            pmx_versions=(2.0, 2.1),
            text_encodings=("utf-16-le", "utf-8"),
            index_sizes=(1, 2, 4),
            deform_types=(0, 1, 2, 3, 4),
            morph_types=tuple(range(11)),
            soft_body_support=True,
            roundtrip_contract="validated_semantic_roundtrip",
            edit_operation_types=(
                "set_model_info",
                "set_texture_path",
                "update_material",
            ),
            texture_portability=True,
            private_runtime_required=False,
        )

        self.assertFalse(legacy.structural_insert)
        self.assertTrue(legacy.structural_preview)
        self.assertFalse(legacy.structural_write)
        self.assertEqual(legacy.structural_contract, "reference_safe_preview")
        self.assertEqual(fields(capabilities.PmxCapabilityManifest)[-1].name, "structural_insert")

    def test_root_service_authority_and_request_alias_remain_exact(self) -> None:
        self.assertEqual(services.__all__, ROOT_SERVICE_EXPORTS)
        self.assertIs(
            services.PmxStructuralEditRequest,
            services.PmxStructuralPreviewRequest,
        )
        for forbidden in (
            "insert_structural_edit",
            "apply_structural_insert",
            "write_pmx_structural_transform",
            "PmxStructuralWriteResult",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, services.__all__)
                self.assertFalse(hasattr(services, forbidden))

    def test_existing_structural_submodules_are_the_public_insertion_vocabulary(self) -> None:
        for module_name, expected_exports in PUBLIC_VOCABULARY.items():
            with self.subTest(module=module_name):
                module = importlib.import_module(
                    f"mmd_registry.services.{module_name}"
                )
                self.assertEqual(tuple(module.__all__), expected_exports)
                for export in expected_exports:
                    self.assertTrue(hasattr(module, export))

    def test_capability_promotion_does_not_reexport_dto_vocabulary_at_root(self) -> None:
        dto_names = {
            name
            for exports in PUBLIC_VOCABULARY.values()
            for name in exports
        }
        self.assertTrue(dto_names.isdisjoint(services.__all__))
        self.assertNotIn("structural_insert", services.__all__)


if __name__ == "__main__":
    unittest.main()
