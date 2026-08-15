"""Stable public contracts for the pre-0.9.0 PMX validation service."""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError, replace
from unittest.mock import patch

import mmd_registry.services as services
from mmd_registry.diagnostics import (
    PmxServiceDiagnosticCode,
    PmxServiceError,
    PmxServiceOperation,
)
from mmd_registry.pmx.errors import PmxValidationError, PmxValidationIssue
from mmd_registry.pmx.validation import validate_pmx_document
from tests.mmd_fixtures import build_pmx_structure


PRIVATE_DETAIL = r"C:\private\秘密-validation.pmx"


def build_validation_document():
    """Build one small complete typed document for validation contracts."""

    return services.load_document(
        io.BytesIO(
            build_pmx_structure(
                deform_types=(),
                surface_indices=(),
                materials=(),
            )
        )
    )


class StableValidationServiceTests(unittest.TestCase):
    """Keep validation typed, deterministic, quiet, and failure-safe."""

    def test_valid_result_is_immutable_repeatable_and_json_ready(self) -> None:
        document = build_validation_document()
        output = io.StringIO()
        error_output = io.StringIO()

        with redirect_stdout(output), redirect_stderr(error_output):
            first = services.validate_document(document)
            second = services.validate_document(document)

        self.assertIsInstance(first, services.PmxDocumentValidationResult)
        self.assertEqual(first, second)
        self.assertTrue(first.is_valid)
        self.assertEqual(first.issues, ())
        self.assertEqual(first.to_dict(), {"is_valid": True, "issues": []})
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(error_output.getvalue(), "")
        with self.assertRaises(FrozenInstanceError):
            first.issues = ()  # type: ignore[misc]

    def test_invalid_document_returns_one_deterministic_structured_issue(self) -> None:
        document = build_validation_document()
        invalid_document = replace(
            document,
            geometry=replace(document.geometry, surface_indices=(0, 0, 0)),
        )

        first = services.validate_document(invalid_document)
        second = services.validate_document(invalid_document)

        self.assertEqual(first, second)
        self.assertFalse(first.is_valid)
        self.assertEqual(len(first.issues), 1)
        self.assertIsInstance(first.issues[0], PmxValidationIssue)
        self.assertEqual(
            first.to_dict(),
            {
                "is_valid": False,
                "issues": [
                    {
                        "section": "surface_indices",
                        "record_index": 0,
                        "field": "vertex_index",
                        "reason": "index 0 is invalid; expected no value.",
                    }
                ],
            },
        )

    def test_result_rejects_untyped_issue_collections(self) -> None:
        with self.assertRaisesRegex(TypeError, "issues must be a tuple"):
            services.PmxDocumentValidationResult(issues=[])  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "PmxValidationIssue"):
            services.PmxDocumentValidationResult(issues=(object(),))  # type: ignore[arg-type]

    def test_invalid_service_input_uses_validation_diagnostic(self) -> None:
        with self.assertRaises(PmxServiceError) as raised:
            services.validate_document(object())  # type: ignore[arg-type]

        error = raised.exception
        self.assertEqual(
            error.to_dict(),
            {
                "code": "invalid_argument",
                "operation": "validate_document",
                "message": "Invalid service input.",
            },
        )
        self.assertEqual(
            error.diagnostic.code,
            PmxServiceDiagnosticCode.INVALID_ARGUMENT,
        )
        self.assertEqual(
            error.diagnostic.operation,
            PmxServiceOperation.VALIDATE_DOCUMENT,
        )
        self._assert_no_wrapped_failure_context(error)

    def test_unexpected_failure_is_redacted_without_exception_identity(self) -> None:
        with patch(
            "mmd_registry.services.validate_pmx_document",
            side_effect=RuntimeError(PRIVATE_DETAIL),
        ):
            with self.assertRaises(PmxServiceError) as raised:
                services.validate_document(build_validation_document())

        error = raised.exception
        self.assertEqual(
            error.to_dict(),
            {
                "code": "service_internal_error",
                "operation": "validate_document",
                "message": "Unexpected internal service failure.",
            },
        )
        serialized = repr(error.to_dict())
        self.assertNotIn(PRIVATE_DETAIL, serialized)
        self.assertNotIn("RuntimeError", serialized)
        self._assert_no_wrapped_failure_context(error)

    def test_process_control_exceptions_are_not_converted(self) -> None:
        with patch(
            "mmd_registry.services.validate_pmx_document",
            side_effect=KeyboardInterrupt(),
        ):
            with self.assertRaises(KeyboardInterrupt):
                services.validate_document(build_validation_document())

    def test_legacy_core_validator_keeps_domain_exception(self) -> None:
        document = build_validation_document()
        invalid_document = replace(
            document,
            geometry=replace(document.geometry, surface_indices=(0, 0, 0)),
        )

        with self.assertRaises(PmxValidationError) as raised:
            validate_pmx_document(invalid_document)

        self.assertEqual(raised.exception.issue.section, "surface_indices")
        self.assertEqual(raised.exception.issue.field, "vertex_index")

    def _assert_no_wrapped_failure_context(self, error: PmxServiceError) -> None:
        self.assertIsNone(error.__cause__)
        self.assertIsNone(error.__context__)
        self.assertTrue(error.__suppress_context__)


if __name__ == "__main__":
    unittest.main()
