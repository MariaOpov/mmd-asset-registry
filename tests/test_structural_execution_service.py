"""Reviewed public structural execution service contracts for CP16."""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import mmd_registry.pmx as pmx_public
import mmd_registry.services as services
from mmd_registry.diagnostics import (
    PmxServiceDiagnosticCode,
    PmxServiceError,
    PmxServiceOperation,
)
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.writer import serialize_pmx
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRIVATE_DETAIL = r"C:\private\秘密-structural-execution.pmx"


def _clean_document():
    return replace(
        load_pmx(io.BytesIO(build_pmx_roundtrip_fixture(version=2.1))),
        trailing_data=b"",
    )


def _reverse_texture_request(document):
    return services.PmxStructuralEditRequest(
        (
            services.PmxStructuralCollectionEdit(
                services.PmxReferenceTargetKind.TEXTURE,
                tuple(reversed(range(len(document.texture_paths)))),
            ),
        )
    )


class StructuralExecutionServiceTests(unittest.TestCase):
    def test_public_surface_is_service_neutral_and_raw_kernel_stays_private(self) -> None:
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

        raw_writer_names = (
            "PmxStructuralWriteResult",
            "verify_pmx_structural_serialization",
            "write_pmx_structural_transform",
        )
        for name in raw_writer_names:
            with self.subTest(name=name):
                self.assertNotIn(name, services.__all__)
                self.assertFalse(hasattr(pmx_public, name))

        for name in (
            "PmxStructuralTransformIntent",
            "PmxCollectionTransform",
            "PmxIndexRemap",
        ):
            with self.subTest(service_mutation_primitive=name):
                self.assertNotIn(name, services.__all__)

    def test_capability_and_diagnostic_vocabulary_promote_execution_additively(self) -> None:
        manifest = services.get_capabilities()
        self.assertTrue(manifest.structural_preview)
        self.assertTrue(manifest.structural_write)
        self.assertEqual(manifest.structural_contract, "reference_safe_execution")
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

    def test_apply_structural_edit_writes_verified_output_and_preserves_source(self) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)
        request = _reverse_texture_request(document)
        preview = services.preview_structural_edit(document, request)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)

            result = services.apply_structural_edit(source, output, request)

            self.assertIsInstance(result, services.PmxStructuralExecutionResult)
            self.assertEqual(result.status, "written")
            self.assertEqual(result.input_path, source.resolve())
            self.assertEqual(result.output_path, output.resolve())
            self.assertEqual(result.document, preview.document)
            self.assertEqual(load_pmx(output), preview.document)
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(result.output_size_bytes, output.stat().st_size)
            report = result.to_dict()
            self.assertFalse(report["dry_run"])
            self.assertTrue(report["output"]["written"])
            self.assertEqual(report["verification"]["serialization"], "passed")
            self.assertTrue(report["verification"]["input_unchanged"])

    def test_noop_execution_still_uses_verified_distinct_output(self) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)
        request = services.PmxStructuralEditRequest()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "noop.pmx"
            source.write_bytes(source_bytes)

            result = services.apply_structural_edit(source, output, request)

            self.assertEqual(result.status, "no_changes")
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertTrue(output.is_file())
            self.assertEqual(load_pmx(output), document)

    def test_in_place_execution_is_structured_path_failure(self) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)
        request = _reverse_texture_request(document)

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.pmx"
            source.write_bytes(source_bytes)

            with self.assertRaises(PmxServiceError) as raised:
                services.apply_structural_edit(
                    source,
                    source,
                    request,
                    overwrite=True,
                )

            self.assertEqual(
                raised.exception.to_dict(),
                {
                    "code": "structural_path_unsafe",
                    "operation": "apply_structural_edit",
                    "message": "Structural output path failed safety validation.",
                    "details": {
                        "provenance": "safe_output",
                        "stage": "path_resolution",
                    },
                },
            )
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_existing_destination_is_preserved_without_overwrite(self) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)
        request = _reverse_texture_request(document)
        old_destination = b"existing-destination"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)
            output.write_bytes(old_destination)

            with self.assertRaises(PmxServiceError) as raised:
                services.apply_structural_edit(source, output, request)

            self.assertEqual(
                raised.exception.diagnostic.code,
                PmxServiceDiagnosticCode.STRUCTURAL_PATH_UNSAFE,
            )
            self.assertEqual(output.read_bytes(), old_destination)
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_out_of_range_request_is_structural_verification_failure(self) -> None:
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
                raised.exception.to_dict(),
                {
                    "code": "structural_verification_failed",
                    "operation": "apply_structural_edit",
                    "message": "Structural execution failed reference-safety validation.",
                    "details": {
                        "provenance": "service_boundary",
                        "stage": "intent_resolution",
                    },
                },
            )
            self.assertFalse(output.exists())
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_wrong_arguments_remain_invalid_argument_failures(self) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)

            cases = (
                (object(), False),
                (services.PmxStructuralEditRequest(), 1),
            )
            for request, overwrite in cases:
                with self.subTest(request=type(request).__name__, overwrite=overwrite):
                    with self.assertRaises(PmxServiceError) as raised:
                        services.apply_structural_edit(  # type: ignore[arg-type]
                            source,
                            output,
                            request,
                            overwrite=overwrite,
                        )
                    self.assertEqual(
                        raised.exception.diagnostic.code,
                        PmxServiceDiagnosticCode.INVALID_ARGUMENT,
                    )
                    self.assertEqual(
                        raised.exception.diagnostic.operation,
                        PmxServiceOperation.APPLY_STRUCTURAL_EDIT,
                    )
                    self.assertEqual(
                        raised.exception.to_dict()["details"],
                        {
                            "provenance": "service_boundary",
                            "stage": "service_validation",
                        },
                    )
                    self.assertFalse(output.exists())

    def test_source_change_after_request_resolution_fails_before_publication(self) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)
        request = _reverse_texture_request(document)
        original_builder = services._build_structural_preview_intent
        captured_document = None

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)

            def build_then_race(parsed_document, candidate_request):
                nonlocal captured_document
                captured_document = parsed_document
                intent = original_builder(parsed_document, candidate_request)
                source.write_bytes(source_bytes + b"race")
                return intent

            with patch(
                "mmd_registry.services._build_structural_preview_intent",
                side_effect=build_then_race,
            ):
                with self.assertRaises(PmxServiceError) as raised:
                    services.apply_structural_edit(source, output, request)

            self.assertEqual(captured_document, document)
            self.assertEqual(
                raised.exception.diagnostic.code,
                PmxServiceDiagnosticCode.STRUCTURAL_VERIFICATION_FAILED,
            )
            self.assertEqual(
                raised.exception.to_dict()["details"],
                {
                    "provenance": "safe_output",
                    "stage": "output_commit",
                },
            )
            self.assertFalse(output.exists())

    def test_unexpected_failure_is_redacted_and_context_suppressed(self) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)
        request = _reverse_texture_request(document)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)

            with patch(
                "mmd_registry.pmx.structural_output._write_pmx_structural_transaction",
                side_effect=RuntimeError(PRIVATE_DETAIL),
            ):
                with self.assertRaises(PmxServiceError) as raised:
                    services.apply_structural_edit(source, output, request)

            error = raised.exception
            self.assertEqual(error.diagnostic.code, PmxServiceDiagnosticCode.INTERNAL_ERROR)
            self.assertEqual(
                error.diagnostic.operation,
                PmxServiceOperation.APPLY_STRUCTURAL_EDIT,
            )
            self.assertEqual(
                error.to_dict()["details"],
                {
                    "provenance": "safe_output",
                    "stage": "path_resolution",
                },
            )
            self.assertNotIn(PRIVATE_DETAIL, repr(error.to_dict()))
            self.assertNotIn("RuntimeError", repr(error.to_dict()))
            self.assertIsNone(error.__cause__)
            self.assertIsNone(error.__context__)
            self.assertTrue(error.__suppress_context__)
            self.assertFalse(output.exists())

    def test_process_control_exceptions_are_not_converted(self) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)
        request = _reverse_texture_request(document)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)

            with patch(
                "mmd_registry.pmx.structural_output._write_pmx_structural_transaction",
                side_effect=KeyboardInterrupt(),
            ):
                with self.assertRaises(KeyboardInterrupt):
                    services.apply_structural_edit(source, output, request)

            with patch(
                "mmd_registry.pmx.structural_output._write_pmx_structural_transaction",
                side_effect=SystemExit(7),
            ):
                with self.assertRaises(SystemExit) as raised:
                    services.apply_structural_edit(source, output, request)
            self.assertEqual(raised.exception.code, 7)

    def test_service_import_remains_quiet_and_structural_writer_is_lazy(self) -> None:
        code = "\n".join(
            (
                "import sys",
                "import mmd_registry.services as services",
                "assert services.get_capabilities().structural_write is True",
                "assert 'mmd_registry.pmx.structural_output' not in sys.modules",
                "assert 'mmd_registry.cli' not in sys.modules",
                "assert 'argparse' not in sys.modules",
            )
        )
        environment = os.environ.copy()
        python_path = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = os.pathsep.join(
            part for part in (str(PROJECT_ROOT), python_path) if part
        )

        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run(
                [sys.executable, "-c", code],
                cwd=directory,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "")
        self.assertEqual(completed.stderr, "")


if __name__ == "__main__":
    unittest.main()
