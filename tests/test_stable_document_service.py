"""Stable public contracts for the pre-0.9.0 PMX document service."""

from __future__ import annotations

import io
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

import mmd_registry.services as services
from mmd_registry.binary_reader import BinaryParseError
from mmd_registry.diagnostics import (
    PmxServiceDiagnosticCode,
    PmxServiceError,
    PmxServiceOperation,
)
from mmd_registry.pmx import PmxDocument, load_pmx
from tests.mmd_fixtures import build_pmx_structure


PRIVATE_DETAIL = r"C:\private\秘密-model.pmx"


def build_document_source() -> bytes:
    """Build one small complete PMX document for service contracts."""

    return build_pmx_structure(
        deform_types=(),
        surface_indices=(),
        materials=(),
    )


class StableDocumentServiceTests(unittest.TestCase):
    """Keep loading and inspection typed, quiet, and failure-safe."""

    def test_load_document_accepts_path_or_caller_owned_stream(self) -> None:
        source_bytes = build_document_source()
        stream = io.BytesIO(source_bytes)

        stream_document = services.load_document(stream)

        self.assertIsInstance(stream_document, PmxDocument)
        self.assertFalse(stream.closed)
        self.assertEqual(stream.tell(), len(source_bytes))

        with tempfile.TemporaryDirectory() as temporary_directory:
            source_path = Path(temporary_directory) / "document.pmx"
            source_path.write_bytes(source_bytes)
            path_document = services.load_document(source_path)

        self.assertEqual(path_document, stream_document)

    def test_inspection_is_immutable_typed_and_repeatable(self) -> None:
        document = services.load_document(io.BytesIO(build_document_source()))

        first = services.inspect_document(document)
        second = services.inspect_document(document)

        self.assertIsInstance(first, services.PmxDocumentMetadata)
        self.assertEqual(first, second)
        self.assertEqual(first.version, 2.0)
        self.assertEqual(first.encoding, "utf-8")
        self.assertEqual(first.local_name, "Test PMX Model")
        self.assertEqual(first.universal_name, "Test PMX Model")
        self.assertEqual(first.local_comments, "")
        self.assertEqual(first.universal_comments, "")
        with self.assertRaises(FrozenInstanceError):
            first.local_name = "changed"  # type: ignore[misc]

    def test_malformed_source_raises_structured_load_failure(self) -> None:
        with self.assertRaises(PmxServiceError) as raised:
            services.load_document(io.BytesIO(b"bad"))

        error = raised.exception
        self.assertEqual(
            error.to_dict(),
            {
                "code": "source_invalid",
                "operation": "load_document",
                "message": "Source PMX data is invalid.",
                "details": {
                    "format_name": "PMX",
                    "offset": 0,
                    "parse_operation": "reading PMX signature",
                    "record_index": None,
                    "section": "signature",
                },
            },
        )
        self.assertEqual(error.diagnostic.code, PmxServiceDiagnosticCode.SOURCE_INVALID)
        self.assertEqual(error.diagnostic.operation, PmxServiceOperation.LOAD_DOCUMENT)
        self._assert_no_wrapped_failure_context(error)

    def test_missing_path_raises_redacted_io_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            missing_path = Path(temporary_directory) / "秘密-model.pmx"
            with self.assertRaises(PmxServiceError) as raised:
                services.load_document(missing_path)

        error = raised.exception
        self.assertEqual(error.diagnostic.code, PmxServiceDiagnosticCode.IO_FAILED)
        self.assertEqual(error.diagnostic.operation, PmxServiceOperation.LOAD_DOCUMENT)
        self.assertEqual(error.diagnostic.message, "Service file operation failed.")
        self.assertNotIn(str(missing_path), repr(error.to_dict()))
        self._assert_no_wrapped_failure_context(error)

    def test_invalid_document_inputs_use_operation_specific_diagnostics(self) -> None:
        calls = (
            (
                lambda: services.load_document(object()),  # type: ignore[arg-type]
                PmxServiceOperation.LOAD_DOCUMENT,
            ),
            (
                lambda: services.inspect_document(object()),  # type: ignore[arg-type]
                PmxServiceOperation.INSPECT_DOCUMENT,
            ),
        )

        for call, operation in calls:
            with self.subTest(operation=operation.value):
                with self.assertRaises(PmxServiceError) as raised:
                    call()
                error = raised.exception
                self.assertEqual(
                    error.diagnostic.code,
                    PmxServiceDiagnosticCode.INVALID_ARGUMENT,
                )
                self.assertEqual(error.diagnostic.operation, operation)
                self.assertEqual(error.diagnostic.message, "Invalid service input.")
                self._assert_no_wrapped_failure_context(error)

    def test_unexpected_failure_is_redacted_without_exception_identity(self) -> None:
        with patch(
            "mmd_registry.services.load_pmx",
            side_effect=RuntimeError(PRIVATE_DETAIL),
        ):
            with self.assertRaises(PmxServiceError) as raised:
                services.load_document(io.BytesIO(build_document_source()))

        error = raised.exception
        self.assertEqual(
            error.to_dict(),
            {
                "code": "service_internal_error",
                "operation": "load_document",
                "message": "Unexpected internal service failure.",
            },
        )
        serialized = repr(error.to_dict())
        self.assertNotIn(PRIVATE_DETAIL, serialized)
        self.assertNotIn("RuntimeError", serialized)
        self._assert_no_wrapped_failure_context(error)

    def test_process_control_exceptions_are_not_converted(self) -> None:
        with patch(
            "mmd_registry.services.load_pmx",
            side_effect=KeyboardInterrupt(),
        ):
            with self.assertRaises(KeyboardInterrupt):
                services.load_document(io.BytesIO(build_document_source()))

    def test_legacy_core_loader_keeps_its_existing_domain_exception(self) -> None:
        with self.assertRaises(BinaryParseError):
            load_pmx(io.BytesIO(b"bad"))

    def _assert_no_wrapped_failure_context(self, error: PmxServiceError) -> None:
        self.assertIsNone(error.__cause__)
        self.assertIsNone(error.__context__)
        self.assertTrue(error.__suppress_context__)


if __name__ == "__main__":
    unittest.main()
