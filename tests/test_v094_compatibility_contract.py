"""Freeze released v0.8-v0.9.3 boundaries for the v0.9.4 campaign."""

from __future__ import annotations

from dataclasses import fields
import inspect
from pathlib import Path
import subprocess
import sys
import tomllib
import unittest

import mmd_registry
from mmd_registry import capabilities, constants, diagnostics
from mmd_registry.pmx.editing.catalog import get_pmx_edit_operation_catalog
from mmd_registry.pmx.editing.plan import PMX_EDIT_PLAN_SCHEMA_VERSION
import mmd_registry.services as services
import mmd_registry.services.structural_transaction as transactions


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

TRANSACTION_EXPORTS = (
    "PmxStructuralTransactionOperation",
    "PmxStructuralTransactionRequest",
    "PmxStructuralTransactionPreviewResult",
    "preview_structural_transaction",
    "apply_structural_transaction",
)

CAPABILITY_V093_PREFIX = (
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
    "structural_transaction",
)

RELEASED_SERVICE_OPERATIONS = (
    "load_document",
    "inspect_document",
    "validate_document",
    "analyze_references",
    "analyze_reference_node",
    "preview_edit",
    "apply_edit",
    "preview_structural_edit",
    "apply_structural_edit",
    "preview_structural_transaction",
    "apply_structural_transaction",
)

RELEASED_DIAGNOSTIC_CODES = (
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
)


def _shape(value: object) -> tuple[tuple[str, str, object], ...]:
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


def _assert_values_preserved_in_order(
    case: unittest.TestCase,
    enum_type: type,
    released_values: tuple[str, ...],
) -> None:
    actual = tuple(member.value for member in enum_type)
    for value in released_values:
        case.assertIn(value, actual)
    positions = tuple(actual.index(value) for value in released_values)
    case.assertEqual(positions, tuple(sorted(positions)))


class V094CompatibilityContractTests(unittest.TestCase):
    """Keep transaction-plan authoring additive to every released boundary."""

    def test_registry_and_v08_edit_schemas_remain_independent(self) -> None:
        self.assertEqual(constants.LATEST_SCHEMA_VERSION, "0.3")
        self.assertEqual(
            constants.SUPPORTED_SCHEMA_VERSIONS,
            frozenset(("0.2", "0.3")),
        )
        self.assertEqual(constants.SCHEMA_VERSION, constants.LATEST_SCHEMA_VERSION)
        self.assertEqual(PMX_EDIT_PLAN_SCHEMA_VERSION, 1)
        self.assertEqual(
            tuple(
                operation.operation_type
                for operation in get_pmx_edit_operation_catalog().operations
            ),
            ("set_model_info", "set_texture_path", "update_material"),
        )

    def test_package_and_installed_cli_identity_remain_compatible(self) -> None:
        self.assertEqual(mmd_registry.__all__, ("__version__",))
        self.assertIsInstance(mmd_registry.__version__, str)
        self.assertTrue(mmd_registry.__version__)

        pyproject = tomllib.loads(
            (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )
        self.assertEqual(pyproject["project"]["name"], "mmd-asset-registry")
        self.assertEqual(
            pyproject["project"]["scripts"]["mmd-asset-registry"],
            "mmd_registry.cli:main",
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
        self.assertEqual(help_result.stderr, "")
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

    def test_legacy_root_service_boundary_remains_frozen(self) -> None:
        self.assertEqual(services.__all__, LEGACY_SERVICE_EXPORTS)
        for name in LEGACY_SERVICE_EXPORTS:
            self.assertTrue(hasattr(services, name), name)

        for transaction_name in TRANSACTION_EXPORTS:
            self.assertNotIn(transaction_name, services.__all__)
            self.assertFalse(hasattr(services, transaction_name))

        self.assertEqual(
            _shape(services.apply_edit),
            (
                ("input_path", "POSITIONAL_OR_KEYWORD", "<required>"),
                ("output_path", "POSITIONAL_OR_KEYWORD", "<required>"),
                ("plan", "POSITIONAL_OR_KEYWORD", "<required>"),
                ("overwrite", "KEYWORD_ONLY", False),
            ),
        )
        self.assertEqual(
            _shape(services.apply_structural_edit),
            (
                ("input_path", "POSITIONAL_OR_KEYWORD", "<required>"),
                ("output_path", "POSITIONAL_OR_KEYWORD", "<required>"),
                ("request", "POSITIONAL_OR_KEYWORD", "<required>"),
                ("overwrite", "KEYWORD_ONLY", False),
            ),
        )

    def test_v093_transaction_namespace_and_call_shapes_remain_frozen(self) -> None:
        self.assertEqual(transactions.__all__, TRANSACTION_EXPORTS)
        self.assertEqual(
            tuple(field.name for field in fields(transactions.PmxStructuralTransactionRequest)),
            ("operations",),
        )
        self.assertEqual(
            _shape(transactions.preview_structural_transaction),
            (
                ("document", "POSITIONAL_OR_KEYWORD", "<required>"),
                ("request", "POSITIONAL_OR_KEYWORD", "<required>"),
            ),
        )
        self.assertEqual(
            _shape(transactions.apply_structural_transaction),
            (
                ("input_path", "POSITIONAL_OR_KEYWORD", "<required>"),
                ("output_path", "POSITIONAL_OR_KEYWORD", "<required>"),
                ("request", "POSITIONAL_OR_KEYWORD", "<required>"),
                ("overwrite", "KEYWORD_ONLY", False),
            ),
        )

    def test_v093_capability_prefix_and_legacy_defaults_remain_compatible(self) -> None:
        manifest_fields = fields(capabilities.PmxCapabilityManifest)
        self.assertGreaterEqual(len(manifest_fields), len(CAPABILITY_V093_PREFIX))
        self.assertEqual(
            tuple(field.name for field in manifest_fields[:16]),
            CAPABILITY_V093_PREFIX,
        )

        defaults = {field.name: field.default for field in manifest_fields}
        self.assertIs(defaults["structural_preview"], True)
        self.assertIs(defaults["structural_write"], False)
        self.assertIs(defaults["structural_insert"], False)
        self.assertIs(defaults["structural_transaction"], False)
        self.assertEqual(defaults["structural_contract"], "reference_safe_preview")

        canonical = capabilities.get_capabilities()
        self.assertIs(canonical.structural_preview, True)
        self.assertIs(canonical.structural_write, True)
        self.assertIs(canonical.structural_insert, True)
        self.assertIs(canonical.structural_transaction, True)
        self.assertEqual(canonical.structural_contract, "reference_safe_execution")
        self.assertEqual(
            tuple(canonical.to_dict())[:16],
            CAPABILITY_V093_PREFIX,
        )

    def test_released_diagnostic_values_remain_additive_and_ordered(self) -> None:
        _assert_values_preserved_in_order(
            self,
            diagnostics.PmxServiceOperation,
            RELEASED_SERVICE_OPERATIONS,
        )
        _assert_values_preserved_in_order(
            self,
            diagnostics.PmxServiceDiagnosticCode,
            RELEASED_DIAGNOSTIC_CODES,
        )

    def test_structural_dto_namespaces_remain_explicit_and_non_root(self) -> None:
        expected = {
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
        for module_name, exports in expected.items():
            with self.subTest(module=module_name):
                module = __import__(module_name, fromlist=["__all__"])
                self.assertEqual(module.__all__, exports)

        self.assertFalse(hasattr(services, "PmxStructuralNewReference"))

    def test_ci_still_runs_complete_unittest_discovery(self) -> None:
        workflow = (
            REPOSITORY_ROOT / ".github" / "workflows" / "validate.yml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "python -m coverage run -m unittest discover -s tests -q",
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
