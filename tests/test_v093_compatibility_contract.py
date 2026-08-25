"""Freeze representative v0.8-v0.9.2 contracts for the v0.9.3 campaign."""

from __future__ import annotations

import importlib
import inspect
import subprocess
import sys
import tomllib
from dataclasses import fields
from pathlib import Path
import unittest

import mmd_registry
import mmd_registry.pmx as pmx_public
import mmd_registry.services as services
from mmd_registry import capabilities, constants, diagnostics
from mmd_registry.pmx.editing.catalog import get_pmx_edit_operation_catalog
from mmd_registry.pmx.editing.plan import PMX_EDIT_PLAN_SCHEMA_VERSION


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

LEGACY_SERVICE_EXPORTS = (
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

LEGACY_CAPABILITY_FIELDS = (
    "pmx_versions",
    "text_encodings",
    "index_sizes",
    "deform_types",
    "morph_types",
    "soft_body_support",
    "roundtrip_contract",
    "edit_operation_types",
    "texture_portability",
    "private_runtime_required",
    "structural_preview",
    "structural_write",
    "structural_target_kinds",
    "structural_contract",
    "structural_insert",
)

STRUCTURAL_TARGET_KINDS = (
    "vertex",
    "texture",
    "material",
    "bone",
    "morph",
    "rigid_body",
)

STRUCTURAL_DTO_EXPORTS = {
    "mmd_registry.services.structural_reference": (
        "PmxStructuralNewReference",
    ),
    "mmd_registry.services.structural_texture": (
        "PmxStructuralTextureInsertion",
    ),
    "mmd_registry.services.structural_material": (
        "PmxStructuralMaterialInsertion",
    ),
    "mmd_registry.services.structural_bone": (
        "PmxStructuralBoneIkLink",
        "PmxStructuralBoneIk",
        "PmxStructuralBoneInsertion",
    ),
    "mmd_registry.services.structural_morph": (
        "PmxStructuralMorphGroupOffset",
        "PmxStructuralMorphVertexOffset",
        "PmxStructuralMorphBoneOffset",
        "PmxStructuralMorphUvOffset",
        "PmxStructuralMorphMaterialOffset",
        "PmxStructuralMorphFlipOffset",
        "PmxStructuralMorphImpulseOffset",
        "PmxStructuralMorphInsertion",
    ),
    "mmd_registry.services.structural_rigid_body": (
        "PmxStructuralRigidBodyInsertion",
    ),
    "mmd_registry.services.structural_vertex": (
        "PmxStructuralVertexBdef1",
        "PmxStructuralVertexBdef2",
        "PmxStructuralVertexBdef4",
        "PmxStructuralVertexSdef",
        "PmxStructuralVertexQdef",
        "PmxStructuralVertexInsertion",
    ),
}


def _signature_shape(value: object) -> tuple[tuple[str, str, object], ...]:
    signature = inspect.signature(value)
    return tuple(
        (
            parameter.name,
            parameter.kind.name,
            "<required>"
            if parameter.default is inspect.Parameter.empty
            else parameter.default,
        )
        for parameter in signature.parameters.values()
    )


def _assert_legacy_values_in_order(
    case: unittest.TestCase,
    enum_type: type,
    legacy_values: tuple[str, ...],
) -> None:
    actual = tuple(member.value for member in enum_type)
    positions = tuple(actual.index(value) for value in legacy_values)
    case.assertEqual(positions, tuple(sorted(positions)))


class V093CompatibilityContractTests(unittest.TestCase):
    """Keep transaction work additive to every released public boundary."""

    def test_package_entrypoint_and_cli_identity_remain_compatible(self) -> None:
        self.assertEqual(mmd_registry.__all__, ("__version__",))
        self.assertIsInstance(mmd_registry.__version__, str)
        self.assertTrue(mmd_registry.__version__)

        pyproject = tomllib.loads(
            (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )
        self.assertEqual(pyproject["project"]["name"], "mmd-asset-registry")
        self.assertEqual(pyproject["project"]["dynamic"], ["version"])
        self.assertEqual(
            pyproject["project"]["scripts"]["mmd-asset-registry"],
            "mmd_registry.cli:main",
        )

        version_result = subprocess.run(
            [sys.executable, "check_assets.py", "--version"],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(version_result.returncode, 0, version_result.stderr)
        self.assertEqual(version_result.stderr, "")
        self.assertEqual(
            version_result.stdout.strip(),
            f"mmd-asset-registry {mmd_registry.__version__}",
        )

        help_result = subprocess.run(
            [sys.executable, "check_assets.py", "--help"],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        for command in (
            "validate",
            "hash",
            "inspect",
            "scan",
            "roundtrip",
            "edit",
            "edit-plan",
            "texture-portability",
            "doctor",
            "bones",
            "rig",
        ):
            self.assertIn(command, help_result.stdout)

    def test_released_service_exports_remain_present_and_ordered(self) -> None:
        self.assertEqual(len(services.__all__), len(set(services.__all__)))
        positions = tuple(services.__all__.index(name) for name in LEGACY_SERVICE_EXPORTS)
        self.assertEqual(positions, tuple(sorted(positions)))
        for name in LEGACY_SERVICE_EXPORTS:
            self.assertTrue(hasattr(services, name), name)

        self.assertIs(
            services.PmxStructuralEditRequest,
            services.PmxStructuralPreviewRequest,
        )
        for forbidden in (
            "PmxStructuralNewReference",
            "apply_structural_insert",
            "write_pmx",
            "write_pmx_structural_output",
            "remap_pmx_references",
        ):
            self.assertNotIn(forbidden, services.__all__)
            self.assertFalse(hasattr(services, forbidden))

    def test_released_service_call_shapes_remain_stable(self) -> None:
        expected = {
            "get_capabilities": (),
            "load_document": (("source", "POSITIONAL_OR_KEYWORD", "<required>"),),
            "inspect_document": (
                ("document", "POSITIONAL_OR_KEYWORD", "<required>"),
            ),
            "validate_document": (
                ("document", "POSITIONAL_OR_KEYWORD", "<required>"),
            ),
            "analyze_references": (
                ("document", "POSITIONAL_OR_KEYWORD", "<required>"),
            ),
            "analyze_reference_node": (
                ("analysis", "POSITIONAL_OR_KEYWORD", "<required>"),
                ("node", "POSITIONAL_OR_KEYWORD", "<required>"),
            ),
            "preview_edit": (
                ("source_bytes", "POSITIONAL_OR_KEYWORD", "<required>"),
                ("plan", "POSITIONAL_OR_KEYWORD", "<required>"),
            ),
            "apply_edit": (
                ("input_path", "POSITIONAL_OR_KEYWORD", "<required>"),
                ("output_path", "POSITIONAL_OR_KEYWORD", "<required>"),
                ("plan", "POSITIONAL_OR_KEYWORD", "<required>"),
                ("overwrite", "KEYWORD_ONLY", False),
            ),
            "preview_structural_edit": (
                ("document", "POSITIONAL_OR_KEYWORD", "<required>"),
                ("request", "POSITIONAL_OR_KEYWORD", "<required>"),
            ),
            "apply_structural_edit": (
                ("input_path", "POSITIONAL_OR_KEYWORD", "<required>"),
                ("output_path", "POSITIONAL_OR_KEYWORD", "<required>"),
                ("request", "POSITIONAL_OR_KEYWORD", "<required>"),
                ("overwrite", "KEYWORD_ONLY", False),
            ),
        }
        for name, shape in expected.items():
            with self.subTest(name=name):
                self.assertEqual(_signature_shape(getattr(services, name)), shape)

    def test_capability_prefix_defaults_and_canonical_values_are_frozen(self) -> None:
        manifest_fields = fields(capabilities.PmxCapabilityManifest)
        self.assertGreaterEqual(len(manifest_fields), len(LEGACY_CAPABILITY_FIELDS))
        self.assertEqual(
            tuple(field.name for field in manifest_fields[:15]),
            LEGACY_CAPABILITY_FIELDS,
        )
        defaults = {field.name: field.default for field in manifest_fields}
        self.assertIs(defaults["structural_preview"], True)
        self.assertIs(defaults["structural_write"], False)
        self.assertEqual(defaults["structural_target_kinds"], STRUCTURAL_TARGET_KINDS)
        self.assertEqual(defaults["structural_contract"], "reference_safe_preview")
        self.assertIs(defaults["structural_insert"], False)

        legacy = capabilities.PmxCapabilityManifest(
            pmx_versions=(2.0,),
            text_encodings=("utf-8",),
            index_sizes=(1,),
            deform_types=(0,),
            morph_types=(0,),
            soft_body_support=False,
            roundtrip_contract="validated_semantic_roundtrip",
            edit_operation_types=(),
            texture_portability=False,
            private_runtime_required=True,
        )
        self.assertTrue(legacy.structural_preview)
        self.assertFalse(legacy.structural_write)
        self.assertEqual(legacy.structural_target_kinds, STRUCTURAL_TARGET_KINDS)
        self.assertEqual(legacy.structural_contract, "reference_safe_preview")
        self.assertFalse(legacy.structural_insert)

        canonical = services.get_capabilities()
        self.assertTrue(canonical.structural_preview)
        self.assertTrue(canonical.structural_write)
        self.assertTrue(canonical.structural_insert)
        self.assertEqual(canonical.structural_target_kinds, STRUCTURAL_TARGET_KINDS)
        self.assertEqual(canonical.structural_contract, "reference_safe_execution")
        payload = canonical.to_dict()
        self.assertEqual(tuple(payload)[:15], LEGACY_CAPABILITY_FIELDS)
        self.assertEqual(payload["structural_target_kinds"], list(STRUCTURAL_TARGET_KINDS))

    def test_v08_edit_vocabulary_and_schemas_remain_independent(self) -> None:
        self.assertEqual(PMX_EDIT_PLAN_SCHEMA_VERSION, 1)
        self.assertEqual(constants.LATEST_SCHEMA_VERSION, "0.3")
        self.assertEqual(
            constants.SUPPORTED_SCHEMA_VERSIONS,
            frozenset(("0.2", "0.3")),
        )
        self.assertEqual(constants.SCHEMA_VERSION, constants.LATEST_SCHEMA_VERSION)
        self.assertEqual(
            tuple(
                operation.operation_type
                for operation in get_pmx_edit_operation_catalog().operations
            ),
            ("set_model_info", "set_texture_path", "update_material"),
        )

    def test_diagnostic_vocabularies_remain_additive_and_bounded(self) -> None:
        self.assertEqual(
            diagnostics.__all__,
            (
                "PmxServiceDiagnostic",
                "PmxServiceDiagnosticCode",
                "PmxServiceError",
                "PmxServiceOperation",
                "diagnostic_from_service_error",
            ),
        )
        _assert_legacy_values_in_order(
            self,
            diagnostics.PmxServiceOperation,
            (
                "load_document",
                "inspect_document",
                "validate_document",
                "analyze_references",
                "analyze_reference_node",
                "preview_edit",
                "apply_edit",
                "preview_structural_edit",
                "apply_structural_edit",
            ),
        )
        _assert_legacy_values_in_order(
            self,
            diagnostics.PmxServiceDiagnosticCode,
            (
                "invalid_argument",
                "service_io_failed",
                "source_invalid",
                "document_invalid",
                "edit_plan_invalid",
                "edit_path_unsafe",
                "edit_verification_failed",
                "structural_preview_failed",
                "structural_path_unsafe",
                "structural_verification_failed",
                "service_internal_error",
            ),
        )

    def test_structural_request_alias_and_default_shape_remain_consumable(self) -> None:
        self.assertIs(
            services.PmxStructuralEditRequest,
            services.PmxStructuralPreviewRequest,
        )
        request_fields = fields(services.PmxStructuralPreviewRequest)
        expected_fields = (
            "collection_edits",
            "texture_insertions",
            "material_insertions",
            "bone_insertions",
            "morph_insertions",
            "rigid_body_insertions",
            "vertex_insertions",
        )
        self.assertGreaterEqual(len(request_fields), len(expected_fields))
        self.assertEqual(
            tuple(field.name for field in request_fields[:7]),
            expected_fields,
        )

        request = services.PmxStructuralPreviewRequest()
        positional_request = services.PmxStructuralPreviewRequest(())
        for field_name in expected_fields:
            self.assertEqual(getattr(request, field_name), ())
            self.assertEqual(getattr(positional_request, field_name), ())

    def test_structural_dto_namespaces_remain_explicit_and_non_root(self) -> None:
        for module_name, expected_exports in STRUCTURAL_DTO_EXPORTS.items():
            with self.subTest(module=module_name):
                module = importlib.import_module(module_name)
                self.assertEqual(module.__all__, expected_exports)
                for export_name in expected_exports:
                    self.assertTrue(hasattr(module, export_name), export_name)

        reference_module = importlib.import_module(
            "mmd_registry.services.structural_reference"
        )
        reference = reference_module.PmxStructuralNewReference("bone", "compat_bone")
        self.assertIsInstance(reference, reference_module.PmxStructuralNewReference)
        self.assertFalse(hasattr(services, "PmxStructuralNewReference"))
        self.assertFalse(hasattr(pmx_public, "PmxStructuralNewReference"))

    def test_ci_keeps_released_compatibility_and_safety_gates_active(self) -> None:
        workflow = (
            REPOSITORY_ROOT / ".github" / "workflows" / "validate.yml"
        ).read_text(encoding="utf-8")
        for marker in (
            "python -m ruff check",
            "python -m compileall",
            "tests.test_v08_contract_freeze",
            "tests.test_v08_backward_compatibility",
            "tests.test_v091_compatibility_contract",
            "tests.test_v091_structural_execution_contract",
            "tests.test_v091_destination_safety",
            "tests.test_v091_atomic_structural_transaction",
            "tests.test_v092_capability_promotion",
            "tests.test_v092_backward_compatibility",
            "python -m coverage run -m unittest discover -s tests -q",
            "python -m build --sdist --wheel",
            "python tools/verify_clean_install.py dist",
        ):
            self.assertIn(marker, workflow)

        for relative_path in (
            "tests/test_v092_structural_insertion_atomicity.py",
            "tests/test_v092_structural_insertion_failure_provenance.py",
            "tests/test_pmx_edit_safe_output.py",
        ):
            self.assertTrue((REPOSITORY_ROOT / relative_path).is_file(), relative_path)


if __name__ == "__main__":
    unittest.main()
