"""Freeze v0.8/v0.9.0 compatibility contracts for the v0.9.1 release line."""

from __future__ import annotations

import importlib
import inspect
import unittest
from dataclasses import FrozenInstanceError

import check_assets
import mmd_registry.pmx as pmx
import mmd_registry.pmx.editing as editing
import mmd_registry.services as services
from mmd_registry import cli
from mmd_registry.capabilities import (
    PmxCapabilityManifest,
    get_capabilities,
    get_pmx_capability_manifest,
)
from mmd_registry.constants import LATEST_SCHEMA_VERSION, SUPPORTED_SCHEMA_VERSIONS
from mmd_registry.diagnostics import PmxServiceDiagnosticCode, PmxServiceOperation
from mmd_registry.pmx.editing.plan import PMX_EDIT_PLAN_SCHEMA_VERSION
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind


V090_PMX_EXPORTS = frozenset(
    (
        "PmxDocument",
        "PmxRoundTripResult",
        "PmxValidationError",
        "PmxValidationIssue",
        "load_pmx",
        "read_pmx_document",
        "roundtrip_pmx",
        "serialize_pmx",
        "validate_pmx_document",
        "write_pmx",
    )
)

V090_EDITING_EXPORTS = frozenset(
    (
        "PmxEditDiagnostic",
        "PmxEditPlan",
        "PmxEditPreview",
        "PmxEditResult",
        "PmxEditWriteResult",
        "SetModelInfo",
        "SetTexturePath",
        "UpdateMaterial",
        "apply_pmx_edit_plan",
        "dry_run_pmx_edit",
        "load_pmx_edit_plan",
        "parse_pmx_edit_plan_json",
        "validate_pmx_edit_plan",
        "write_pmx_edit",
    )
)

V090_SERVICE_EXPORTS = frozenset(
    (
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
    )
)

V090_SERVICE_OPERATIONS = frozenset(
    (
        "load_document",
        "inspect_document",
        "validate_document",
        "analyze_references",
        "analyze_reference_node",
        "preview_edit",
        "apply_edit",
        "preview_structural_edit",
    )
)

V090_SERVICE_DIAGNOSTIC_CODES = frozenset(
    (
        "invalid_argument",
        "service_io_failed",
        "source_invalid",
        "document_invalid",
        "edit_plan_invalid",
        "edit_path_unsafe",
        "edit_verification_failed",
        "structural_preview_failed",
        "service_internal_error",
    )
)

STRUCTURAL_TARGET_KINDS = (
    "vertex",
    "texture",
    "material",
    "bone",
    "morph",
    "rigid_body",
)

V08_EDIT_OPERATION_TYPES = (
    "set_model_info",
    "set_texture_path",
    "update_material",
)


class V091CompatibilityContractTests(unittest.TestCase):
    """Protect released callers while v0.9.1 adds bounded structural execution."""

    def test_released_public_namespaces_remain_additively_compatible(self) -> None:
        self.assertTrue(V090_PMX_EXPORTS.issubset(set(pmx.__all__)))
        self.assertTrue(V090_EDITING_EXPORTS.issubset(set(editing.__all__)))
        self.assertTrue(V090_SERVICE_EXPORTS.issubset(set(services.__all__)))

    def test_legacy_registry_and_launcher_entrypoints_remain_available(self) -> None:
        expected_members = {
            "mmd_registry.capabilities": (
                "PmxCapabilityManifest",
                "get_pmx_capability_manifest",
            ),
            "mmd_registry.reporting": (
                "build_json_report",
                "generate_credits_markdown",
                "write_credits_file",
                "write_json_report",
            ),
            "mmd_registry.validator": (
                "AssetValidationResult",
                "RegistryValidationResult",
                "validate_asset",
                "validate_registry",
            ),
        }

        for module_name, member_names in expected_members.items():
            module = importlib.import_module(module_name)
            for member_name in member_names:
                with self.subTest(module=module_name, member=member_name):
                    self.assertTrue(hasattr(module, member_name))

        self.assertIs(check_assets.main, cli.main)

    def test_registry_and_edit_plan_schema_versions_remain_stable(self) -> None:
        self.assertEqual(PMX_EDIT_PLAN_SCHEMA_VERSION, 1)
        self.assertEqual(LATEST_SCHEMA_VERSION, "0.3")
        self.assertEqual(SUPPORTED_SCHEMA_VERSIONS, frozenset(("0.2", "0.3")))

    def test_bounded_v08_edit_operation_surface_remains_exact(self) -> None:
        manifest = get_capabilities()
        self.assertEqual(manifest.edit_operation_types, V08_EDIT_OPERATION_TYPES)

    def test_reference_safe_preview_contract_remains_consumable(self) -> None:
        manifest = get_capabilities()

        self.assertTrue(manifest.structural_preview)
        self.assertEqual(manifest.structural_target_kinds, STRUCTURAL_TARGET_KINDS)
        self.assertEqual(
            tuple(kind.value for kind in PmxReferenceTargetKind),
            STRUCTURAL_TARGET_KINDS,
        )

        request = services.PmxStructuralPreviewRequest()
        self.assertEqual(request.collection_edits, ())
        with self.assertRaises(FrozenInstanceError):
            request.collection_edits = ()  # type: ignore[misc]

    def test_v090_capability_constructor_shape_remains_accepted(self) -> None:
        manifest = PmxCapabilityManifest(
            pmx_versions=(2.0, 2.1),
            text_encodings=("utf-16-le", "utf-8"),
            index_sizes=(1, 2, 4),
            deform_types=(0, 1, 2, 3, 4),
            morph_types=tuple(range(11)),
            soft_body_support=True,
            roundtrip_contract="validated_semantic_roundtrip",
            edit_operation_types=V08_EDIT_OPERATION_TYPES,
            texture_portability=True,
            private_runtime_required=False,
        )

        self.assertTrue(manifest.structural_preview)
        self.assertEqual(manifest.structural_target_kinds, STRUCTURAL_TARGET_KINDS)

    def test_legacy_capability_helper_matches_canonical_manifest(self) -> None:
        self.assertEqual(
            get_pmx_capability_manifest().to_dict(),
            get_capabilities().to_dict(),
        )

    def test_service_operation_and_diagnostic_vocabularies_are_additive(self) -> None:
        operation_values = {operation.value for operation in PmxServiceOperation}
        diagnostic_values = {code.value for code in PmxServiceDiagnosticCode}

        self.assertTrue(V090_SERVICE_OPERATIONS.issubset(operation_values))
        self.assertTrue(V090_SERVICE_DIAGNOSTIC_CODES.issubset(diagnostic_values))

    def test_released_edit_service_signature_keeps_source_destination_boundary(self) -> None:
        signature = inspect.signature(services.apply_edit)
        parameters = tuple(signature.parameters.values())

        self.assertGreaterEqual(len(parameters), 4)
        self.assertEqual(parameters[0].name, "input_path")
        self.assertEqual(parameters[1].name, "output_path")
        self.assertEqual(parameters[2].name, "plan")
        self.assertEqual(parameters[3].name, "overwrite")
        self.assertEqual(parameters[3].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertIs(parameters[3].default, False)

    def test_structural_preview_service_signature_remains_compatible(self) -> None:
        signature = inspect.signature(services.preview_structural_edit)
        parameters = tuple(signature.parameters.values())

        self.assertGreaterEqual(len(parameters), 2)
        self.assertEqual(parameters[0].name, "document")
        self.assertEqual(parameters[1].name, "request")


    def test_v091_structural_execution_service_is_additive_and_bounded(self) -> None:
        self.assertIs(
            services.PmxStructuralEditRequest,
            services.PmxStructuralPreviewRequest,
        )
        for name in (
            "PmxStructuralEditRequest",
            "PmxStructuralExecutionResult",
            "apply_structural_edit",
        ):
            self.assertIn(name, services.__all__)

        signature = inspect.signature(services.apply_structural_edit)
        parameters = tuple(signature.parameters.values())
        self.assertEqual(parameters[0].name, "input_path")
        self.assertEqual(parameters[1].name, "output_path")
        self.assertEqual(parameters[2].name, "request")
        self.assertEqual(parameters[3].name, "overwrite")
        self.assertEqual(parameters[3].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertIs(parameters[3].default, False)

        self.assertEqual(
            PmxServiceOperation.APPLY_STRUCTURAL_EDIT.value,
            "apply_structural_edit",
        )
        self.assertEqual(
            PmxServiceDiagnosticCode.STRUCTURAL_PATH_UNSAFE.value,
            "structural_path_unsafe",
        )
        self.assertEqual(
            PmxServiceDiagnosticCode.STRUCTURAL_VERIFICATION_FAILED.value,
            "structural_verification_failed",
        )

    def test_internal_structural_writer_is_not_retroactively_public(self) -> None:
        # v0.9.1 may add a reviewed execution service later, but the v0.9.0
        # internal kernel itself must not become public by incidental re-export.
        self.assertNotIn("write_pmx_structural_transform", services.__all__)
        self.assertNotIn("write_pmx_structural_transform", pmx.__all__)


if __name__ == "__main__":
    unittest.main()
