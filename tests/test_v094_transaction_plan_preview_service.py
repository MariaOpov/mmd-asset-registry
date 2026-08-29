"""Tests for CP17 source-bound structural transaction-plan preview service."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, is_dataclass, replace
import hashlib
import inspect
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import mmd_registry.services as root_services
import mmd_registry.services.structural_transaction_plan_preview as preview_service
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.writer import serialize_pmx
from mmd_registry.services.structural_transaction_plan import (
    parse_structural_transaction_plan_json,
)
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


def _clean_source_bytes() -> bytes:
    fixture = build_pmx_roundtrip_fixture(version=2.1, index_size=1)
    document = replace(
        load_pmx(io.BytesIO(fixture)),
        trailing_data=b"",
    )
    return serialize_pmx(document)


def _validated_plan(
    *,
    expected_source_sha256: str | None,
    operations: list[dict[str, object]] | None = None,
):
    payload: dict[str, object] = {
        "schema_version": 1,
        "operations": [] if operations is None else operations,
    }
    if expected_source_sha256 is not None:
        payload["expected_source_sha256"] = expected_source_sha256
    return parse_structural_transaction_plan_json(
        json.dumps(payload, separators=(",", ":"))
    )


class V094TransactionPlanPreviewServiceTests(unittest.TestCase):
    """Freeze the CP17 single-snapshot preview service boundary."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.source_path = self.root / "source.pmx"
        self.source_bytes = _clean_source_bytes()
        self.source_sha256 = hashlib.sha256(self.source_bytes).hexdigest()
        self.source_path.write_bytes(self.source_bytes)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_public_namespace_is_exact_and_never_root_promoted(self) -> None:
        self.assertEqual(
            preview_service.__all__,
            (
                "PmxStructuralTransactionPlanPreviewServiceOperation",
                "PmxStructuralTransactionPlanPreviewServiceDiagnosticCode",
                "PmxStructuralTransactionPlanPreviewServiceDiagnostic",
                "PmxStructuralTransactionPlanPreviewServiceError",
                "PmxStructuralTransactionPlanPreviewResult",
                "preview_structural_transaction_plan",
            ),
        )
        for name in preview_service.__all__:
            self.assertFalse(hasattr(root_services, name), name)

    def test_success_captures_once_then_loads_and_previews_same_snapshot(
        self,
    ) -> None:
        validated = _validated_plan(
            expected_source_sha256=self.source_sha256
        )

        with (
            patch.object(
                root_services,
                "load_document",
                wraps=root_services.load_document,
            ) as load_document,
            patch.object(
                preview_service,
                "preview_structural_transaction",
                wraps=preview_service.preview_structural_transaction,
            ) as released_preview,
        ):
            result = preview_service.preview_structural_transaction_plan(
                self.source_path,
                validated,
            )

        self.assertEqual(result.status, "no_changes")
        self.assertEqual(result.source_identity_status, "matched")
        self.assertTrue(result.expected_source_sha256_declared)
        load_document.assert_called_once()
        released_preview.assert_called_once()

        source_stream = load_document.call_args.args[0]
        self.assertIsInstance(source_stream, io.BytesIO)
        self.assertEqual(source_stream.getvalue(), self.source_bytes)
        self.assertIs(
            released_preview.call_args.args[1],
            validated.request,
        )

        payload = result.to_dict()
        self.assertEqual(
            payload["source_identity"],
            {
                "algorithm": "sha256",
                "expected_source_sha256_declared": True,
                "status": "matched",
            },
        )
        self.assertTrue(payload["dry_run"])
        self.assertFalse(payload["output"]["source_touched"])
        self.assertFalse(payload["output"]["destination_touched"])

    def test_undeclared_identity_is_explicit_without_synthetic_digest(self) -> None:
        validated = _validated_plan(expected_source_sha256=None)

        result = preview_service.preview_structural_transaction_plan(
            self.source_path,
            validated,
        )
        payload = result.to_dict()

        self.assertFalse(result.expected_source_sha256_declared)
        self.assertEqual(result.source_identity_status, "not_declared")
        self.assertEqual(
            payload["source_identity"],
            {
                "algorithm": "sha256",
                "expected_source_sha256_declared": False,
                "status": "not_declared",
            },
        )
        self.assertNotIn("expected", payload["source_identity"])
        self.assertNotIn("actual", payload["source_identity"])

    def test_hash_mismatch_blocks_parse_and_preview_without_disclosure(
        self,
    ) -> None:
        validated = _validated_plan(expected_source_sha256="0" * 64)

        with (
            patch.object(root_services, "load_document") as load_document,
            patch.object(
                preview_service,
                "preview_structural_transaction",
            ) as released_preview,
            self.assertRaises(
                preview_service.PmxStructuralTransactionPlanPreviewServiceError
            ) as raised,
        ):
            preview_service.preview_structural_transaction_plan(
                self.source_path,
                validated,
            )

        load_document.assert_not_called()
        released_preview.assert_not_called()
        diagnostic = raised.exception.to_dict()
        self.assertEqual(diagnostic["code"], "source_identity_mismatch")
        self.assertEqual(
            diagnostic["operation"],
            "preview_structural_transaction_plan",
        )
        self.assertEqual(
            diagnostic["details"],
            {
                "expected_source_sha256_declared": True,
                "preview_performed": False,
                "source_parsed": False,
                "source_snapshot_captured": True,
            },
        )
        serialized = json.dumps(diagnostic, ensure_ascii=False)
        self.assertNotIn("0" * 64, serialized)
        self.assertNotIn(self.source_sha256, serialized)
        self.assertNotIn(str(self.source_path), serialized)

    def test_missing_source_reports_io_without_path_disclosure(self) -> None:
        missing = self.root / "秘密-source.pmx"
        validated = _validated_plan(expected_source_sha256=None)

        with self.assertRaises(
            preview_service.PmxStructuralTransactionPlanPreviewServiceError
        ) as raised:
            preview_service.preview_structural_transaction_plan(
                missing,
                validated,
            )

        diagnostic = raised.exception.to_dict()
        self.assertEqual(diagnostic["code"], "service_io_failed")
        self.assertEqual(
            diagnostic["operation"],
            "preview_structural_transaction_plan",
        )
        self.assertNotIn(str(missing), json.dumps(diagnostic, ensure_ascii=False))

    def test_invalid_source_translates_released_load_diagnostic_safely(self) -> None:
        self.source_path.write_bytes(b"not-a-pmx")
        validated = _validated_plan(expected_source_sha256=None)

        with self.assertRaises(
            preview_service.PmxStructuralTransactionPlanPreviewServiceError
        ) as raised:
            preview_service.preview_structural_transaction_plan(
                self.source_path,
                validated,
            )

        diagnostic = raised.exception.to_dict()
        self.assertEqual(diagnostic["code"], "source_invalid")
        self.assertEqual(diagnostic["details"]["cause_operation"], "load_document")
        self.assertEqual(diagnostic["details"]["cause_code"], "source_invalid")
        self.assertNotIn(
            str(self.source_path),
            json.dumps(diagnostic, ensure_ascii=False),
        )

    def test_released_preview_blocker_is_translated_without_reimplementation(
        self,
    ) -> None:
        validated = _validated_plan(
            expected_source_sha256=None,
            operations=[
                {
                    "op": "transform_collection",
                    "target_kind": "vertex",
                    "old_indices_in_new_order": [9999],
                }
            ],
        )

        with self.assertRaises(
            preview_service.PmxStructuralTransactionPlanPreviewServiceError
        ) as raised:
            preview_service.preview_structural_transaction_plan(
                self.source_path,
                validated,
            )

        diagnostic = raised.exception.to_dict()
        self.assertEqual(diagnostic["code"], "structural_preview_failed")
        self.assertEqual(
            diagnostic["details"]["cause_operation"],
            "preview_structural_transaction",
        )
        self.assertIn("stage", diagnostic["details"])
        self.assertFalse(diagnostic["details"]["destination_published"])

    def test_invalid_service_argument_is_local_invalid_argument(self) -> None:
        with self.assertRaises(
            preview_service.PmxStructuralTransactionPlanPreviewServiceError
        ) as raised:
            preview_service.preview_structural_transaction_plan(
                self.source_path,
                object(),  # type: ignore[arg-type]
            )

        self.assertEqual(raised.exception.to_dict()["code"], "invalid_argument")

    def test_process_control_exceptions_escape_service_boundary(self) -> None:
        validated = _validated_plan(expected_source_sha256=None)

        with (
            patch.object(
                preview_service,
                "_capture_source_snapshot",
                side_effect=KeyboardInterrupt,
            ),
            self.assertRaises(KeyboardInterrupt),
        ):
            preview_service.preview_structural_transaction_plan(
                self.source_path,
                validated,
            )

    def test_result_and_diagnostics_are_frozen_strict_and_deterministic(
        self,
    ) -> None:
        validated = _validated_plan(expected_source_sha256=None)
        result = preview_service.preview_structural_transaction_plan(
            self.source_path,
            validated,
        )

        self.assertTrue(is_dataclass(result))
        self.assertFalse(hasattr(result, "__dict__"))
        self.assertEqual(
            tuple(item.name for item in fields(result)),
            (
                "_preview",
                "expected_source_sha256_declared",
                "source_identity_status",
            ),
        )
        with self.assertRaises(FrozenInstanceError):
            result.source_identity_status = "matched"

        with self.assertRaises(TypeError):
            preview_service.PmxStructuralTransactionPlanPreviewResult(
                _preview=object(),  # type: ignore[arg-type]
                expected_source_sha256_declared=False,
                source_identity_status="not_declared",
            )
        with self.assertRaises(ValueError):
            preview_service.PmxStructuralTransactionPlanPreviewResult(
                _preview=result._preview,
                expected_source_sha256_declared=True,
                source_identity_status="not_declared",
            )

        diagnostic = (
            preview_service.PmxStructuralTransactionPlanPreviewServiceDiagnostic(
                code=(
                    preview_service
                    .PmxStructuralTransactionPlanPreviewServiceDiagnosticCode
                    .SOURCE_IDENTITY_MISMATCH
                ),
                operation=(
                    preview_service
                    .PmxStructuralTransactionPlanPreviewServiceOperation
                    .PREVIEW
                ),
                message="safe",
                details=(("source_parsed", False),),
            )
        )
        self.assertEqual(
            diagnostic.to_dict(),
            {
                "code": "source_identity_mismatch",
                "operation": "preview_structural_transaction_plan",
                "message": "safe",
                "details": {"source_parsed": False},
            },
        )

    def test_source_is_captured_once_and_never_hash_then_reopened(self) -> None:
        source = inspect.getsource(preview_service)
        capture_source = inspect.getsource(
            preview_service._capture_source_snapshot
        )

        self.assertEqual(capture_source.count('.open("rb")'), 1)
        self.assertIn("file.read()", capture_source)
        for forbidden in (
            "hash_file_sha256",
            "check_file_sha256",
            "load_document(source",
            "load_document(Path",
            "preview_structural_transaction(source",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_cp17_adds_no_apply_writer_remap_or_publication_authority(self) -> None:
        source = inspect.getsource(preview_service)
        for forbidden in (
            "apply_structural_transaction",
            "structural_output",
            "write_pmx",
            "serialize_pmx",
            "PmxIndexRemap",
            "final_index",
            "output_path",
            "overwrite=",
            "publish(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_import_is_explicit_and_does_not_load_cli_or_output_service(self) -> None:
        script = "\n".join(
            (
                "import sys",
                "import mmd_registry.services."
                "structural_transaction_plan_preview as module",
                "assert module.__all__",
                "assert 'mmd_registry.cli' not in sys.modules",
                "assert 'mmd_registry.pmx.structural_output' not in sys.modules",
            )
        )
        subprocess.check_call(
            (sys.executable, "-c", script),
            cwd=Path(__file__).resolve().parents[1],
        )

    def test_function_signature_is_exact(self) -> None:
        signature = inspect.signature(
            preview_service.preview_structural_transaction_plan
        )
        self.assertEqual(
            tuple(signature.parameters),
            ("source", "validated_plan"),
        )


if __name__ == "__main__":
    unittest.main()
