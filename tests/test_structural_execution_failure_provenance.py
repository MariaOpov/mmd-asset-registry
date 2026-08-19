"""CP17 bounded structural-execution failure provenance regression gates."""

from __future__ import annotations

import io
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import mmd_registry.pmx.structural_output as structural_output
import mmd_registry.services as services
from mmd_registry.diagnostics import (
    PmxServiceDiagnosticCode,
    PmxServiceError,
)
from mmd_registry.pmx.collection_transform import PmxStructuralTransformIntent
from mmd_registry.pmx.editing.errors import PmxEditVerificationError
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.writer import serialize_pmx
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


PRIVATE_DETAIL = r"C:\private\秘密-cp17-provenance.pmx"


def _clean_document():
    return replace(
        load_pmx(io.BytesIO(build_pmx_roundtrip_fixture(version=2.1))),
        trailing_data=b"",
    )


def _details(error: PmxServiceError) -> dict[str, object]:
    details = error.to_dict().get("details")
    if not isinstance(details, dict):
        raise AssertionError("structural execution failure must expose bounded details")
    return details


class StructuralExecutionFailureProvenanceTests(unittest.TestCase):
    def test_stage_provenance_lookup_uses_immutable_module_state(self) -> None:
        table = services._STRUCTURAL_FAILURE_PROVENANCE
        self.assertIsInstance(table, tuple)
        self.assertTrue(table)
        self.assertTrue(
            all(
                isinstance(item, tuple)
                and len(item) == 2
                and all(isinstance(value, str) for value in item)
                for item in table
            )
        )
        self.assertEqual(
            services._structural_failure_provenance("reparse"),
            "structural_pipeline",
        )
        with self.assertRaises(AssertionError):
            services._structural_failure_provenance("unknown_stage")

    def test_internal_transaction_reports_the_frozen_stage_order(self) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)
        stages: list[str] = []

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)

            result = structural_output._write_pmx_structural_transaction(
                source,
                output,
                lambda _document: PmxStructuralTransformIntent(),
                _stage_callback=stages.append,
            )

        self.assertNotIn("_stage_callback", repr(result.serialization))
        self.assertEqual(
            tuple(stages),
            (
                "path_resolution",
                "source_snapshot",
                "source_parse",
                "intent_resolution",
                "structural_certification",
                "serialization",
                "reparse",
                "reparse_certification",
                "semantic_compare",
                "output_commit",
            ),
        )

    def test_service_validation_failure_uses_service_boundary_provenance(self) -> None:
        with self.assertRaises(PmxServiceError) as raised:
            services.apply_structural_edit(
                "source.pmx",
                "output.pmx",
                object(),  # type: ignore[arg-type]
            )

        self.assertEqual(
            raised.exception.diagnostic.code,
            PmxServiceDiagnosticCode.INVALID_ARGUMENT,
        )
        self.assertEqual(
            _details(raised.exception),
            {
                "provenance": "service_boundary",
                "stage": "service_validation",
            },
        )

    def test_path_resolution_failure_is_safe_output_and_redacted(self) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.pmx"
            source.write_bytes(source_bytes)

            with self.assertRaises(PmxServiceError) as raised:
                services.apply_structural_edit(
                    source,
                    source,
                    services.PmxStructuralEditRequest(),
                    overwrite=True,
                )

        self.assertEqual(
            raised.exception.diagnostic.code,
            PmxServiceDiagnosticCode.STRUCTURAL_PATH_UNSAFE,
        )
        self.assertEqual(
            _details(raised.exception),
            {"provenance": "safe_output", "stage": "path_resolution"},
        )
        self.assertNotIn(str(source), repr(raised.exception.to_dict()))

    def test_source_snapshot_io_failure_has_source_input_provenance(self) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)

            with patch(
                "mmd_registry.pmx.structural_output._edit_output._file_identity",
                side_effect=PermissionError(13, PRIVATE_DETAIL),
            ):
                with self.assertRaises(PmxServiceError) as raised:
                    services.apply_structural_edit(
                        source,
                        output,
                        services.PmxStructuralEditRequest(),
                    )

        self.assertEqual(
            raised.exception.diagnostic.code,
            PmxServiceDiagnosticCode.IO_FAILED,
        )
        details = _details(raised.exception)
        self.assertEqual(details["provenance"], "source_input")
        self.assertEqual(details["stage"], "source_snapshot")
        self.assertEqual(details["errno"], 13)
        self.assertEqual(set(details), {"errno", "provenance", "stage"})
        self.assertNotIn(PRIVATE_DETAIL, repr(raised.exception.to_dict()))

    def test_intent_resolution_failure_is_service_boundary_provenance(self) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)
        request = services.PmxStructuralEditRequest(
            (
                services.PmxStructuralCollectionEdit(
                    services.PmxReferenceTargetKind.TEXTURE,
                    (len(document.texture_paths),),
                ),
            )
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)

            with self.assertRaises(PmxServiceError) as raised:
                services.apply_structural_edit(source, output, request)

        self.assertEqual(
            raised.exception.diagnostic.code,
            PmxServiceDiagnosticCode.STRUCTURAL_VERIFICATION_FAILED,
        )
        self.assertEqual(
            _details(raised.exception),
            {"provenance": "service_boundary", "stage": "intent_resolution"},
        )

    def test_structural_certification_failure_is_pipeline_provenance(self) -> None:
        unsafe_bytes = build_pmx_roundtrip_fixture(version=2.1)
        self.assertTrue(load_pmx(io.BytesIO(unsafe_bytes)).trailing_data)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(unsafe_bytes)

            with self.assertRaises(PmxServiceError) as raised:
                services.apply_structural_edit(
                    source,
                    output,
                    services.PmxStructuralEditRequest(),
                )

        self.assertEqual(
            _details(raised.exception),
            {
                "provenance": "structural_pipeline",
                "stage": "structural_certification",
            },
        )
        self.assertFalse(output.exists())

    def test_reparse_failure_reports_stage_without_private_exception_text(self) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)
        original_load = structural_output.load_pmx
        calls = 0

        def fail_second_load(source):
            nonlocal calls
            calls += 1
            if calls == 1:
                return original_load(source)
            raise ValueError(PRIVATE_DETAIL)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)

            with patch(
                "mmd_registry.pmx.structural_output.load_pmx",
                side_effect=fail_second_load,
            ):
                with self.assertRaises(PmxServiceError) as raised:
                    services.apply_structural_edit(
                        source,
                        output,
                        services.PmxStructuralEditRequest(),
                    )

        self.assertEqual(calls, 2)
        self.assertEqual(
            raised.exception.diagnostic.code,
            PmxServiceDiagnosticCode.STRUCTURAL_VERIFICATION_FAILED,
        )
        self.assertEqual(
            _details(raised.exception),
            {"provenance": "structural_pipeline", "stage": "reparse"},
        )
        self.assertNotIn(PRIVATE_DETAIL, repr(raised.exception.to_dict()))
        self.assertFalse(output.exists())

    def test_output_commit_failure_reports_safe_output_provenance(self) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)

            with patch(
                "mmd_registry.pmx.structural_output._edit_output."
                "_commit_verified_bytes",
                side_effect=PmxEditVerificationError(PRIVATE_DETAIL),
            ):
                with self.assertRaises(PmxServiceError) as raised:
                    services.apply_structural_edit(
                        source,
                        output,
                        services.PmxStructuralEditRequest(),
                    )

        self.assertEqual(
            raised.exception.diagnostic.code,
            PmxServiceDiagnosticCode.STRUCTURAL_VERIFICATION_FAILED,
        )
        self.assertEqual(
            _details(raised.exception),
            {"provenance": "safe_output", "stage": "output_commit"},
        )
        self.assertNotIn(PRIVATE_DETAIL, repr(raised.exception.to_dict()))
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
