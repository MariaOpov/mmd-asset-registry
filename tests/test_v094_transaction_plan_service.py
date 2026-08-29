"""Tests for the CP15 structural transaction-plan service boundary."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError
import importlib
import inspect
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import mmd_registry
import mmd_registry.diagnostics as diagnostics
import mmd_registry.pmx as pmx
import mmd_registry.services as services
import mmd_registry.services.structural_transaction as transaction
import mmd_registry.services.structural_transaction_plan as plan_service
from mmd_registry.pmx.transaction_plan import (
    PmxStructuralTransactionPlan,
    PmxStructuralTransactionPlanExplanation,
)
from mmd_registry.services.structural_transaction import (
    PmxStructuralTransactionRequest,
)


SERVICE_EXPORTS = (
    "PmxStructuralTransactionPlanServiceOperation",
    "PmxStructuralTransactionPlanServiceDiagnosticCode",
    "PmxStructuralTransactionPlanServiceDiagnostic",
    "PmxStructuralTransactionPlanServiceError",
    "PmxStructuralTransactionPlanValidationResult",
    "parse_structural_transaction_plan_json",
    "load_structural_transaction_plan",
    "validate_structural_transaction_plan",
    "explain_structural_transaction_plan",
)
TRANSACTION_EXPORTS = (
    "PmxStructuralTransactionOperation",
    "PmxStructuralTransactionRequest",
    "PmxStructuralTransactionPreviewResult",
    "preview_structural_transaction",
    "apply_structural_transaction",
)
RELEASED_DIAGNOSTIC_OPERATIONS = (
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
EXPECTED_HASH = "a" * 64


def _valid_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "expected_source_sha256": EXPECTED_HASH,
        "operations": [
            {"op": "insert_texture", "path": "textures/cp15.png"},
            {
                "op": "insert_material",
                "local_name": "CP15",
                "texture_index": 0,
            },
        ],
    }


def _dump(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class V094TransactionPlanServiceTests(unittest.TestCase):
    """Keep CP15 typed, deterministic, quiet, and execution-authority free."""

    def test_public_namespace_is_exact_and_never_root_promoted(self) -> None:
        self.assertEqual(plan_service.__all__, SERVICE_EXPORTS)
        self.assertEqual(transaction.__all__, TRANSACTION_EXPORTS)
        self.assertEqual(mmd_registry.__all__, ("__version__",))

        for name in SERVICE_EXPORTS:
            self.assertTrue(hasattr(plan_service, name), name)
            self.assertFalse(hasattr(mmd_registry, name))
            self.assertNotIn(name, pmx.__all__)
            self.assertFalse(hasattr(services, name))
            self.assertNotIn(name, services.__all__)

    def test_cp15_does_not_change_released_global_diagnostic_vocabularies(
        self,
    ) -> None:
        self.assertEqual(
            tuple(value.value for value in diagnostics.PmxServiceOperation),
            RELEASED_DIAGNOSTIC_OPERATIONS,
        )
        self.assertEqual(
            tuple(value.value for value in diagnostics.PmxServiceDiagnosticCode),
            RELEASED_DIAGNOSTIC_CODES,
        )

    def test_parse_compiles_exactly_one_released_request_in_authored_order(
        self,
    ) -> None:
        first = plan_service.parse_structural_transaction_plan_json(
            _dump(_valid_payload())
        )
        second = plan_service.parse_structural_transaction_plan_json(
            _dump(_valid_payload())
        )

        self.assertIsInstance(
            first,
            plan_service.PmxStructuralTransactionPlanValidationResult,
        )
        self.assertIsInstance(first.plan, PmxStructuralTransactionPlan)
        self.assertIsInstance(first.request, PmxStructuralTransactionRequest)
        self.assertIs(first.request.operations, first.plan.operations)
        self.assertEqual(first, second)
        self.assertEqual(
            tuple(type(item).__name__ for item in first.request.operations),
            (
                "PmxStructuralTextureInsertion",
                "PmxStructuralMaterialInsertion",
            ),
        )
        self.assertEqual(
            first.to_dict(),
            {
                "status": "valid",
                "schema_version": 1,
                "operation_count": 2,
                "expected_source_sha256_declared": True,
            },
        )
        self.assertNotIn(EXPECTED_HASH, json.dumps(first.to_dict()))

    def test_load_uses_bounded_core_loader_then_released_request_authority(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            path.write_text(_dump(_valid_payload()), encoding="utf-8")
            result = plan_service.load_structural_transaction_plan(path)

        self.assertIs(result.request.operations, result.plan.operations)
        self.assertEqual(result.operation_count, 2)
        self.assertTrue(result.expected_source_sha256_declared)

    def test_validate_typed_plan_is_pure_repeatable_and_json_ready(self) -> None:
        parsed = plan_service.parse_structural_transaction_plan_json(
            _dump(_valid_payload())
        )
        first = plan_service.validate_structural_transaction_plan(parsed.plan)
        second = plan_service.validate_structural_transaction_plan(parsed.plan)

        self.assertEqual(first, second)
        self.assertIs(first.plan, parsed.plan)
        self.assertIs(first.request.operations, parsed.plan.operations)
        self.assertEqual(first.to_dict(), second.to_dict())

    def test_explain_reuses_existing_value_free_authoring_explanation(self) -> None:
        validated = plan_service.parse_structural_transaction_plan_json(
            _dump(_valid_payload())
        )

        explanation = plan_service.explain_structural_transaction_plan(
            validated.plan
        )

        self.assertIsInstance(
            explanation,
            PmxStructuralTransactionPlanExplanation,
        )
        self.assertTrue(explanation.expected_source_sha256_declared)
        self.assertNotIn(EXPECTED_HASH, json.dumps(explanation.to_dict()))

    def test_plan_failure_is_contextual_but_disclosure_safe(self) -> None:
        payload = _valid_payload()
        operations = payload["operations"]
        assert isinstance(operations, list)
        operation = operations[0]
        assert isinstance(operation, dict)
        operation["private_payload"] = r"C:\private\秘密-model.pmx"

        with self.assertRaises(
            plan_service.PmxStructuralTransactionPlanServiceError
        ) as raised:
            plan_service.parse_structural_transaction_plan_json(_dump(payload))

        diagnostic = raised.exception.to_dict()
        self.assertEqual(
            diagnostic,
            {
                "code": "transaction_plan_invalid",
                "operation": "parse_structural_transaction_plan_json",
                "message": "Structural transaction plan is invalid.",
                "details": {
                    "field": "private_payload",
                    "operation_index": 0,
                    "operation_type": "insert_texture",
                },
            },
        )
        serialized = json.dumps(diagnostic, ensure_ascii=False)
        self.assertNotIn("秘密-model", serialized)
        self.assertNotIn("C:\\private", serialized)

    def test_missing_plan_file_reports_io_without_disclosing_path(self) -> None:
        private_path = Path(r"C:\private\秘密-plan.json")

        with self.assertRaises(
            plan_service.PmxStructuralTransactionPlanServiceError
        ) as raised:
            plan_service.load_structural_transaction_plan(private_path)

        diagnostic = raised.exception.to_dict()
        self.assertEqual(diagnostic["code"], "service_io_failed")
        self.assertEqual(
            diagnostic["operation"],
            "load_structural_transaction_plan",
        )
        self.assertEqual(
            diagnostic["message"],
            "Structural transaction-plan file operation failed.",
        )
        serialized = json.dumps(diagnostic, ensure_ascii=False)
        self.assertNotIn("秘密-plan", serialized)
        self.assertNotIn("C:\\private", serialized)

    def test_invalid_service_arguments_use_local_invalid_argument_code(
        self,
    ) -> None:
        calls = (
            (
                plan_service.validate_structural_transaction_plan,
                object(),
                "validate_structural_transaction_plan",
            ),
            (
                plan_service.explain_structural_transaction_plan,
                object(),
                "explain_structural_transaction_plan",
            ),
        )
        for function, value, operation in calls:
            with self.subTest(operation=operation):
                with self.assertRaises(
                    plan_service.PmxStructuralTransactionPlanServiceError
                ) as raised:
                    function(value)
                self.assertEqual(
                    raised.exception.to_dict(),
                    {
                        "code": "invalid_argument",
                        "operation": operation,
                        "message": (
                            "Invalid structural transaction-plan service input."
                        ),
                    },
                )

    def test_service_models_are_frozen_strict_and_deterministic(self) -> None:
        diagnostic = (
            plan_service.PmxStructuralTransactionPlanServiceDiagnostic(
                code=(
                    plan_service
                    .PmxStructuralTransactionPlanServiceDiagnosticCode
                    .INVALID_ARGUMENT
                ),
                operation=(
                    plan_service
                    .PmxStructuralTransactionPlanServiceOperation
                    .VALIDATE
                ),
                message="Invalid structural transaction-plan service input.",
            )
        )
        self.assertEqual(diagnostic.to_dict(), diagnostic.to_dict())
        with self.assertRaises(FrozenInstanceError):
            diagnostic.message = "changed"  # type: ignore[misc]

        with self.assertRaises(TypeError):
            plan_service.PmxStructuralTransactionPlanServiceDiagnostic(
                code="invalid_argument",  # type: ignore[arg-type]
                operation=(
                    plan_service
                    .PmxStructuralTransactionPlanServiceOperation
                    .VALIDATE
                ),
                message="Invalid.",
            )

        validated = plan_service.parse_structural_transaction_plan_json(
            _dump(_valid_payload())
        )
        with self.assertRaises(TypeError):
            plan_service.PmxStructuralTransactionPlanValidationResult(
                plan=object(),  # type: ignore[arg-type]
                request=validated.request,
            )

    def test_process_control_exceptions_escape_service_boundary(self) -> None:
        with patch.object(
            plan_service,
            "_parse_plan_json",
            side_effect=KeyboardInterrupt(),
        ):
            with self.assertRaises(KeyboardInterrupt):
                plan_service.parse_structural_transaction_plan_json("{}")

        with patch.object(
            plan_service,
            "_explain_plan",
            side_effect=SystemExit(7),
        ):
            parsed = plan_service.parse_structural_transaction_plan_json(
                _dump(_valid_payload())
            )
            with self.assertRaises(SystemExit) as raised:
                plan_service.explain_structural_transaction_plan(parsed.plan)
            self.assertEqual(raised.exception.code, 7)

    def test_service_is_quiet_and_does_not_mutate_typed_plan(self) -> None:
        validated = plan_service.parse_structural_transaction_plan_json(
            _dump(_valid_payload())
        )
        before = validated.plan
        output = io.StringIO()
        error_output = io.StringIO()

        with redirect_stdout(output), redirect_stderr(error_output):
            result = plan_service.validate_structural_transaction_plan(before)
            explanation = plan_service.explain_structural_transaction_plan(
                before
            )

        self.assertIs(result.plan, before)
        self.assertEqual(before, validated.plan)
        self.assertTrue(explanation.expected_source_sha256_declared)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(error_output.getvalue(), "")

    def test_cp15_adds_no_execution_hash_remap_or_publication_authority(
        self,
    ) -> None:
        source = inspect.getsource(plan_service)
        for forbidden in (
            "preview_structural_transaction",
            "apply_structural_transaction",
            "structural_output",
            "write_pmx",
            "PmxIndexRemap",
            "final_index",
            "hashlib",
            "source.read_bytes",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

        self.assertNotIn(
            "expected_source_sha256 ==",
            source,
        )
        self.assertNotIn(
            "expected_source_sha256 !=",
            source,
        )

    def test_import_is_side_effect_light_and_does_not_load_cli_or_writer(
        self,
    ) -> None:
        script = "\n".join(
            (
                "import sys",
                "import mmd_registry.services.structural_transaction_plan as service",
                "assert service.__all__",
                "assert 'mmd_registry.pmx.structural_output' not in sys.modules",
                "assert 'mmd_registry.cli' not in sys.modules",
                "assert 'argparse' not in sys.modules",
            )
        )
        subprocess.check_call(
            (sys.executable, "-c", script),
            cwd=Path(__file__).resolve().parents[1],
        )

    def test_imported_module_identity_is_the_explicit_service_submodule(
        self,
    ) -> None:
        module = importlib.import_module(
            "mmd_registry.services.structural_transaction_plan"
        )
        self.assertIs(module, plan_service)
        self.assertEqual(
            module.__name__,
            "mmd_registry.services.structural_transaction_plan",
        )


if __name__ == "__main__":
    unittest.main()
