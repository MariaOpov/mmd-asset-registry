"""Public contracts for the pre-0.9.0 service diagnostic boundary."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

import mmd_registry.diagnostics as diagnostics
from mmd_registry.binary_reader import BinaryParseError
from mmd_registry.pmx.editing.errors import (
    PmxEditPathError,
    PmxEditPlanError,
    PmxEditVerificationError,
)
from mmd_registry.pmx.errors import PmxValidationError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRIVATE_DETAIL = r"C:\private\秘密-model.pmx"


class PublicDiagnosticsApiTests(unittest.TestCase):
    """Keep reusable failures typed, deterministic, and disclosure-safe."""

    def test_namespace_has_one_explicit_canonical_surface(self) -> None:
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

        namespace: dict[str, object] = {}
        exec("from mmd_registry.diagnostics import *", namespace)
        exported_names = {name for name in namespace if name != "__builtins__"}
        self.assertEqual(exported_names, set(diagnostics.__all__))

    def test_operations_cover_only_current_public_services(self) -> None:
        self.assertEqual(
            tuple(operation.value for operation in diagnostics.PmxServiceOperation),
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
        serialized = " ".join(
            operation.value for operation in diagnostics.PmxServiceOperation
        )
        for unsupported in (
            "create_model",
            "plugin_loading",
            "unrestricted_physics_editing",
            "vmd_editing",
        ):
            with self.subTest(unsupported=unsupported):
                self.assertNotIn(unsupported, serialized)


    def test_structural_execution_vocabularies_are_public_and_additive(self) -> None:
        self.assertEqual(
            diagnostics.PmxServiceOperation.APPLY_STRUCTURAL_EDIT.value,
            "apply_structural_edit",
        )
        self.assertEqual(
            diagnostics.PmxServiceDiagnosticCode.STRUCTURAL_PATH_UNSAFE.value,
            "structural_path_unsafe",
        )
        self.assertEqual(
            diagnostics.PmxServiceDiagnosticCode.STRUCTURAL_VERIFICATION_FAILED.value,
            "structural_verification_failed",
        )

    def test_diagnostic_is_immutable_deterministic_and_json_ready(self) -> None:
        diagnostic = diagnostics.PmxServiceDiagnostic(
            code=diagnostics.PmxServiceDiagnosticCode.EDIT_PLAN_INVALID,
            operation=diagnostics.PmxServiceOperation.PREVIEW_EDIT,
            message="Plan is invalid.",
            details=(("operation_index", 2), ("field", "path")),
        )

        self.assertEqual(
            diagnostic.to_dict(),
            {
                "code": "edit_plan_invalid",
                "operation": "preview_edit",
                "message": "Plan is invalid.",
                "details": {"field": "path", "operation_index": 2},
            },
        )
        self.assertEqual(diagnostic.to_dict(), diagnostic.to_dict())
        with self.assertRaises(FrozenInstanceError):
            diagnostic.message = "changed"  # type: ignore[misc]

    def test_diagnostic_rejects_ambiguous_or_mutable_fields(self) -> None:
        valid = {
            "code": diagnostics.PmxServiceDiagnosticCode.INVALID_ARGUMENT,
            "operation": diagnostics.PmxServiceOperation.INSPECT_DOCUMENT,
            "message": "Invalid input.",
        }
        invalid_overrides = (
            {"code": "invalid_argument"},
            {"operation": "inspect_document"},
            {"message": ""},
            {"details": []},
            {"details": (("bad-key", 1),)},
            {"details": (("field", 1), ("field", 2))},
            {"details": (("field", object()),)},
        )

        for override in invalid_overrides:
            with self.subTest(override=override):
                arguments = valid | override
                with self.assertRaises((TypeError, ValueError)):
                    diagnostics.PmxServiceDiagnostic(**arguments)

    def test_service_error_wraps_only_one_public_diagnostic(self) -> None:
        diagnostic = diagnostics.PmxServiceDiagnostic(
            code=diagnostics.PmxServiceDiagnosticCode.SOURCE_INVALID,
            operation=diagnostics.PmxServiceOperation.LOAD_DOCUMENT,
            message="Source PMX data is invalid.",
        )
        error = diagnostics.PmxServiceError(diagnostic)

        self.assertIs(error.diagnostic, diagnostic)
        self.assertEqual(str(error), diagnostic.message)
        self.assertEqual(error.to_dict(), diagnostic.to_dict())
        with self.assertRaises(TypeError):
            diagnostics.PmxServiceError("invalid")  # type: ignore[arg-type]

    def test_structured_domain_errors_keep_only_stable_context(self) -> None:
        parse_error = BinaryParseError(
            format_name="PMX",
            section="bones",
            record_index=4,
            offset=128,
            operation="reading bone flags",
            reason=PRIVATE_DETAIL,
        )
        parse_diagnostic = diagnostics.diagnostic_from_service_error(
            diagnostics.PmxServiceOperation.LOAD_DOCUMENT,
            parse_error,
        )
        self.assertEqual(
            parse_diagnostic.code,
            diagnostics.PmxServiceDiagnosticCode.SOURCE_INVALID,
        )
        self.assertEqual(
            parse_diagnostic.to_dict()["details"],
            {
                "format_name": "PMX",
                "offset": 128,
                "parse_operation": "reading bone flags",
                "record_index": 4,
                "section": "bones",
            },
        )
        self.assertNotIn(PRIVATE_DETAIL, repr(parse_diagnostic.to_dict()))

        validation_error = PmxValidationError(
            section="bones",
            record_index=4,
            field="parent_index",
            reason="index 20 is invalid for 5 bones.",
        )
        validation_diagnostic = diagnostics.diagnostic_from_service_error(
            diagnostics.PmxServiceOperation.VALIDATE_DOCUMENT,
            validation_error,
        )
        self.assertEqual(
            validation_diagnostic.code,
            diagnostics.PmxServiceDiagnosticCode.DOCUMENT_INVALID,
        )
        self.assertEqual(
            validation_diagnostic.to_dict()["details"],
            {
                "field": "parent_index",
                "reason": "index 20 is invalid for 5 bones.",
                "record_index": 4,
                "section": "bones",
            },
        )

        plan_error = PmxEditPlanError(
            "path is invalid.",
            operation_index=2,
            operation_type="set_texture_path",
            field="path",
        )
        plan_diagnostic = diagnostics.diagnostic_from_service_error(
            diagnostics.PmxServiceOperation.PREVIEW_EDIT,
            plan_error,
        )
        self.assertEqual(
            plan_diagnostic.code,
            diagnostics.PmxServiceDiagnosticCode.EDIT_PLAN_INVALID,
        )
        self.assertEqual(plan_diagnostic.message, plan_error.reason)

    def test_sensitive_exception_text_is_never_exposed(self) -> None:
        cases = (
            (
                PmxEditPathError(PRIVATE_DETAIL),
                diagnostics.PmxServiceDiagnosticCode.EDIT_PATH_UNSAFE,
            ),
            (
                PmxEditVerificationError(PRIVATE_DETAIL),
                diagnostics.PmxServiceDiagnosticCode.EDIT_VERIFICATION_FAILED,
            ),
            (
                PermissionError(13, PRIVATE_DETAIL),
                diagnostics.PmxServiceDiagnosticCode.IO_FAILED,
            ),
            (
                TypeError(PRIVATE_DETAIL),
                diagnostics.PmxServiceDiagnosticCode.INVALID_ARGUMENT,
            ),
            (
                RuntimeError(PRIVATE_DETAIL),
                diagnostics.PmxServiceDiagnosticCode.INTERNAL_ERROR,
            ),
        )

        for error, expected_code in cases:
            with self.subTest(error=type(error).__name__):
                diagnostic = diagnostics.diagnostic_from_service_error(
                    diagnostics.PmxServiceOperation.APPLY_EDIT,
                    error,
                )
                self.assertEqual(diagnostic.code, expected_code)
                self.assertNotIn(PRIVATE_DETAIL, repr(diagnostic.to_dict()))
                self.assertNotIn(type(error).__name__, repr(diagnostic.to_dict()))

    def test_adapter_rejects_noncanonical_inputs(self) -> None:
        with self.assertRaises(TypeError):
            diagnostics.diagnostic_from_service_error(
                "load_document",  # type: ignore[arg-type]
                ValueError("invalid"),
            )
        with self.assertRaises(TypeError):
            diagnostics.diagnostic_from_service_error(
                diagnostics.PmxServiceOperation.LOAD_DOCUMENT,
                "invalid",  # type: ignore[arg-type]
            )
        with self.assertRaises(TypeError):
            diagnostics.diagnostic_from_service_error(
                diagnostics.PmxServiceOperation.LOAD_DOCUMENT,
                KeyboardInterrupt(),  # type: ignore[arg-type]
            )

    def test_public_import_is_quiet_cli_independent_and_cwd_independent(self) -> None:
        code = "\n".join(
            (
                "import sys",
                "import mmd_registry.diagnostics as diagnostics",
                "assert diagnostics.__all__",
                "assert diagnostics.PmxServiceOperation.LOAD_DOCUMENT",
                "assert 'mmd_registry.cli' not in sys.modules",
                "assert 'argparse' not in sys.modules",
            )
        )
        environment = os.environ.copy()
        environment["MMD_REGISTRY_PRIVATE_PMX"] = PRIVATE_DETAIL
        python_path = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = os.pathsep.join(
            part for part in (str(PROJECT_ROOT), python_path) if part
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            result = subprocess.run(
                [sys.executable, "-c", code],
                cwd=temporary_directory,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
