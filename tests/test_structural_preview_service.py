"""Public preview-only service and capability contracts for CP19."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from unittest.mock import patch

import mmd_registry.capabilities as capabilities
import mmd_registry.pmx as pmx_public
import mmd_registry.services as services
from mmd_registry.diagnostics import (
    PmxServiceDiagnosticCode,
    PmxServiceError,
    PmxServiceOperation,
)
from mmd_registry.pmx.reader import load_pmx
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRIVATE_DETAIL = r"C:\private\秘密-structural.pmx"


def _clean_document():
    return replace(
        load_pmx(io.BytesIO(build_pmx_roundtrip_fixture(version=2.1))),
        trailing_data=b"",
    )


class StructuralPreviewServiceTests(unittest.TestCase):
    def test_public_service_surface_keeps_preview_and_adds_bounded_execution(self) -> None:
        expected_suffix = (
            "PmxStructuralCollectionEdit",
            "PmxStructuralPreviewRequest",
            "PmxStructuralPreviewResult",
            "preview_structural_edit",
            "PmxStructuralEditRequest",
            "PmxStructuralExecutionResult",
            "apply_structural_edit",
        )

        self.assertEqual(services.__all__[-len(expected_suffix) :], expected_suffix)
        self.assertIs(
            services.PmxStructuralEditRequest,
            services.PmxStructuralPreviewRequest,
        )
        self.assertNotIn("write_pmx_structural_transform", services.__all__)
        self.assertNotIn("PmxStructuralWriteResult", services.__all__)
        self.assertFalse(hasattr(services, "PmxStructuralPreview"))
        self.assertFalse(hasattr(services, "preview_pmx_structural_transform"))

    def test_structural_write_kernel_remains_outside_public_namespaces(self) -> None:
        for namespace in (services, pmx_public):
            with self.subTest(namespace=namespace.__name__):
                self.assertFalse(hasattr(namespace, "write_pmx_structural_transform"))
                self.assertFalse(hasattr(namespace, "PmxStructuralWriteResult"))

    def test_service_operation_adds_reviewed_structural_execution(self) -> None:
        values = tuple(operation.value for operation in PmxServiceOperation)

        self.assertEqual(values[-2:], ("preview_structural_edit", "apply_structural_edit"))
        self.assertEqual(values.count("preview_structural_edit"), 1)
        self.assertEqual(values.count("apply_structural_edit"), 1)

    def test_collection_edit_and_request_are_immutable_and_hashable(self) -> None:
        edit = services.PmxStructuralCollectionEdit(
            services.PmxReferenceTargetKind.TEXTURE,
            (1, 0),
        )
        request = services.PmxStructuralPreviewRequest((edit,))

        self.assertEqual(hash(edit), hash(edit))
        self.assertEqual(hash(request), hash(request))
        with self.assertRaises(FrozenInstanceError):
            edit.old_indices_in_new_order = ()  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            request.collection_edits = ()  # type: ignore[misc]

    def test_request_rejects_non_tuple_bool_negative_duplicate_and_kind_reuse(self) -> None:
        kind = services.PmxReferenceTargetKind.TEXTURE

        with self.assertRaises(TypeError):
            services.PmxStructuralCollectionEdit(
                kind,
                [0],  # type: ignore[arg-type]
            )
        with self.assertRaises(TypeError):
            services.PmxStructuralCollectionEdit(
                kind,
                (True,),  # type: ignore[arg-type]
            )
        with self.assertRaises(ValueError):
            services.PmxStructuralCollectionEdit(kind, (-1,))
        with self.assertRaises(ValueError):
            services.PmxStructuralCollectionEdit(kind, (0, 0))
        with self.assertRaises(TypeError):
            services.PmxStructuralCollectionEdit(  # type: ignore[arg-type]
                object(),
                (),
            )

        edit = services.PmxStructuralCollectionEdit(kind, ())
        with self.assertRaises(TypeError):
            services.PmxStructuralPreviewRequest([edit])  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            services.PmxStructuralPreviewRequest((edit, edit))

    def test_preview_reorders_texture_collection_without_filesystem_side_effect(self) -> None:
        document = _clean_document()
        order = tuple(reversed(range(len(document.texture_paths))))
        request = services.PmxStructuralPreviewRequest(
            (
                services.PmxStructuralCollectionEdit(
                    services.PmxReferenceTargetKind.TEXTURE,
                    order,
                ),
            )
        )
        stdout = io.StringIO()
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as temporary_directory:
            sentinel = Path(temporary_directory) / "sentinel.pmx"
            sentinel.write_bytes(b"sentinel")
            with redirect_stdout(stdout), redirect_stderr(stderr):
                first = services.preview_structural_edit(document, request)
                second = services.preview_structural_edit(document, request)

            self.assertEqual(tuple(Path(temporary_directory).iterdir()), (sentinel,))
            self.assertEqual(sentinel.read_bytes(), b"sentinel")

        self.assertIsInstance(first, services.PmxStructuralPreviewResult)
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(
            first.document.texture_paths,
            tuple(document.texture_paths[index] for index in order),
        )
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")

    def test_preview_accepts_empty_request_as_certified_noop(self) -> None:
        document = _clean_document()
        result = services.preview_structural_edit(
            document,
            services.PmxStructuralPreviewRequest(),
        )

        self.assertEqual(result.status, "no_changes")
        self.assertIs(result.document, document)
        self.assertEqual(
            result.to_dict()["verification"]["serialization"],
            "not_performed",
        )

    def test_out_of_range_request_is_structured_reference_safety_failure(self) -> None:
        document = _clean_document()
        request = services.PmxStructuralPreviewRequest(
            (
                services.PmxStructuralCollectionEdit(
                    services.PmxReferenceTargetKind.TEXTURE,
                    (len(document.texture_paths),),
                ),
            )
        )

        with self.assertRaises(PmxServiceError) as raised:
            services.preview_structural_edit(document, request)

        self.assertEqual(
            raised.exception.to_dict(),
            {
                "code": "structural_preview_failed",
                "operation": "preview_structural_edit",
                "message": "Structural preview failed reference-safety validation.",
            },
        )

    def test_invalid_document_keeps_document_invalid_diagnostic(self) -> None:
        document = _clean_document()
        invalid = replace(
            document,
            model_info=replace(document.model_info, local_name="\ud800"),
        )

        with self.assertRaises(PmxServiceError) as raised:
            services.preview_structural_edit(
                invalid,
                services.PmxStructuralPreviewRequest(),
            )

        self.assertEqual(
            raised.exception.diagnostic.code,
            PmxServiceDiagnosticCode.DOCUMENT_INVALID,
        )
        self.assertEqual(
            raised.exception.diagnostic.operation,
            PmxServiceOperation.PREVIEW_STRUCTURAL_EDIT,
        )

    def test_wrong_service_arguments_use_invalid_argument_diagnostic(self) -> None:
        document = _clean_document()
        request = services.PmxStructuralPreviewRequest()

        cases = (
            (object(), request),
            (document, object()),
        )
        for candidate_document, candidate_request in cases:
            with self.subTest(
                document_type=type(candidate_document).__name__,
                request_type=type(candidate_request).__name__,
            ):
                with self.assertRaises(PmxServiceError) as raised:
                    services.preview_structural_edit(  # type: ignore[arg-type]
                        candidate_document,
                        candidate_request,
                    )
                self.assertEqual(
                    raised.exception.diagnostic.code,
                    PmxServiceDiagnosticCode.INVALID_ARGUMENT,
                )
                self.assertEqual(
                    raised.exception.diagnostic.operation,
                    PmxServiceOperation.PREVIEW_STRUCTURAL_EDIT,
                )

    def test_unexpected_failure_is_redacted_and_context_suppressed(self) -> None:
        document = _clean_document()
        request = services.PmxStructuralPreviewRequest()

        with patch(
            "mmd_registry.services._preview_pmx_structural_transform",
            side_effect=RuntimeError(PRIVATE_DETAIL),
        ):
            with self.assertRaises(PmxServiceError) as raised:
                services.preview_structural_edit(document, request)

        error = raised.exception
        self.assertEqual(
            error.diagnostic.code,
            PmxServiceDiagnosticCode.INTERNAL_ERROR,
        )
        self.assertEqual(
            error.diagnostic.operation,
            PmxServiceOperation.PREVIEW_STRUCTURAL_EDIT,
        )
        self.assertNotIn(PRIVATE_DETAIL, repr(error.to_dict()))
        self.assertNotIn("RuntimeError", repr(error.to_dict()))
        self.assertIsNone(error.__cause__)
        self.assertIsNone(error.__context__)
        self.assertTrue(error.__suppress_context__)

    def test_process_control_exceptions_are_not_converted(self) -> None:
        document = _clean_document()
        request = services.PmxStructuralPreviewRequest()

        with patch(
            "mmd_registry.services._preview_pmx_structural_transform",
            side_effect=KeyboardInterrupt(),
        ):
            with self.assertRaises(KeyboardInterrupt):
                services.preview_structural_edit(document, request)

        with patch(
            "mmd_registry.services._preview_pmx_structural_transform",
            side_effect=SystemExit(7),
        ):
            with self.assertRaises(SystemExit) as raised:
                services.preview_structural_edit(document, request)
        self.assertEqual(raised.exception.code, 7)

    def test_capability_manifest_advertises_reviewed_structural_execution(self) -> None:
        manifest = services.get_capabilities()

        self.assertTrue(manifest.structural_preview)
        self.assertTrue(manifest.structural_write)
        self.assertEqual(manifest.structural_contract, "reference_safe_execution")
        self.assertEqual(
            manifest.structural_target_kinds,
            ("vertex", "texture", "material", "bone", "morph", "rigid_body"),
        )
        payload = manifest.to_dict()
        self.assertTrue(payload["structural_preview"])
        self.assertTrue(payload["structural_write"])
        self.assertNotIn("write_pmx_structural_transform", json.dumps(payload))

    def test_capability_manifest_old_constructor_shape_remains_accepted(self) -> None:
        manifest = capabilities.PmxCapabilityManifest(
            pmx_versions=(2.0, 2.1),
            text_encodings=("utf-16-le", "utf-8"),
            index_sizes=(1, 2, 4),
            deform_types=(0, 1, 2, 3, 4),
            morph_types=tuple(range(11)),
            soft_body_support=True,
            roundtrip_contract="validated_semantic_roundtrip",
            edit_operation_types=("set_model_info",),
            texture_portability=True,
            private_runtime_required=False,
        )

        self.assertTrue(manifest.structural_preview)
        self.assertFalse(manifest.structural_write)
        self.assertEqual(manifest.structural_contract, "reference_safe_preview")

    def test_capability_structural_target_copy_cannot_mutate_manifest(self) -> None:
        manifest = capabilities.get_capabilities()
        payload = manifest.to_dict()
        targets = payload["structural_target_kinds"]

        self.assertIsInstance(targets, list)
        targets.append("unsupported")  # type: ignore[union-attr]

        self.assertEqual(
            manifest.structural_target_kinds,
            ("vertex", "texture", "material", "bone", "morph", "rigid_body"),
        )
        self.assertNotIn(
            "unsupported",
            manifest.to_dict()["structural_target_kinds"],
        )

    def test_public_service_import_does_not_pull_structural_output_writer(self) -> None:
        code = "\n".join(
            (
                "import sys",
                "import mmd_registry.services as services",
                "assert services.get_capabilities().structural_preview is True",
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
