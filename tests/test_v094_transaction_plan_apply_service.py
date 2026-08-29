"""Tests for CP18 source-bound structural transaction-plan apply service."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, is_dataclass, replace
import hashlib
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

import mmd_registry.pmx.structural_output as structural_output
import mmd_registry.services as root_services
import mmd_registry.services.structural_transaction as transaction
import mmd_registry.services.structural_transaction_plan_apply as apply_service
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


def _validated_plan(*, expected_source_sha256: str | None):
    payload: dict[str, object] = {
        "schema_version": 1,
        "operations": [],
    }
    if expected_source_sha256 is not None:
        payload["expected_source_sha256"] = expected_source_sha256
    return parse_structural_transaction_plan_json(
        json.dumps(payload, separators=(",", ":"))
    )


class _ValidatorBlocked(RuntimeError):
    pass


class V094TransactionPlanApplyServiceTests(unittest.TestCase):
    """Freeze the CP18 source-bound atomic apply service boundary."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.source_path = self.root / "source.pmx"
        self.output_path = self.root / "output.pmx"
        self.source_bytes = _clean_source_bytes()
        self.source_sha256 = hashlib.sha256(self.source_bytes).hexdigest()
        self.source_path.write_bytes(self.source_bytes)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_public_namespace_is_exact_and_never_root_promoted(self) -> None:
        self.assertEqual(
            apply_service.__all__,
            (
                "PmxStructuralTransactionPlanApplyServiceOperation",
                "PmxStructuralTransactionPlanApplyServiceDiagnosticCode",
                "PmxStructuralTransactionPlanApplyServiceDiagnostic",
                "PmxStructuralTransactionPlanApplyServiceError",
                "PmxStructuralTransactionPlanApplyResult",
                "apply_structural_transaction_plan",
            ),
        )
        for name in apply_service.__all__:
            self.assertFalse(hasattr(root_services, name), name)

    def test_function_and_private_extension_signatures_are_exact(self) -> None:
        public_signature = inspect.signature(
            transaction.apply_structural_transaction
        )
        wrapper_signature = inspect.signature(
            transaction._write_structural_transaction
        )
        staged_signature = inspect.signature(
            transaction._write_structural_transaction_with_stage_callback
        )
        kernel_signature = inspect.signature(
            structural_output._write_verified_structural_transaction
        )
        service_signature = inspect.signature(
            apply_service.apply_structural_transaction_plan
        )

        self.assertEqual(
            tuple(public_signature.parameters),
            ("input_path", "output_path", "request", "overwrite"),
        )
        self.assertEqual(
            tuple(wrapper_signature.parameters),
            ("input_path", "output_path", "request", "overwrite"),
        )
        self.assertEqual(
            tuple(staged_signature.parameters),
            (
                "input_path",
                "output_path",
                "request",
                "overwrite",
                "stage_callback",
                "_source_sha256_validator",
            ),
        )
        self.assertEqual(
            tuple(kernel_signature.parameters),
            (
                "input_path",
                "output_path",
                "serialization_factory",
                "overwrite",
                "_stage_callback",
                "_source_sha256_validator",
            ),
        )
        self.assertEqual(
            tuple(service_signature.parameters),
            ("source", "output", "validated_plan", "overwrite"),
        )
        self.assertIs(
            service_signature.parameters["overwrite"].kind,
            inspect.Parameter.KEYWORD_ONLY,
        )
        self.assertIs(
            staged_signature.parameters["_source_sha256_validator"].default,
            None,
        )
        self.assertIs(
            kernel_signature.parameters["_source_sha256_validator"].default,
            None,
        )

    def test_generic_kernel_validator_runs_after_snapshot_before_parse(self) -> None:
        observed: list[str] = []

        def validator(actual_sha256: str) -> None:
            observed.append(actual_sha256)
            raise _ValidatorBlocked("stop before parse")

        with (
            patch.object(
                structural_output,
                "load_pmx",
                side_effect=AssertionError("parse must not run"),
            ) as parse,
            patch.object(
                structural_output._edit_output,
                "_commit_verified_bytes",
                side_effect=AssertionError("commit must not run"),
            ) as commit,
            self.assertRaises(_ValidatorBlocked),
        ):
            structural_output._write_verified_structural_transaction(
                self.source_path,
                self.output_path,
                lambda _document, _callback: object(),
                _source_sha256_validator=validator,
            )

        self.assertEqual(observed, [self.source_sha256])
        parse.assert_not_called()
        commit.assert_not_called()
        self.assertFalse(self.output_path.exists())
        self.assertEqual(self.source_path.read_bytes(), self.source_bytes)

    def test_private_staged_writer_passes_validator_to_existing_kernel(self) -> None:
        sentinel = object()
        validator = lambda _actual: None

        with patch.object(
            structural_output,
            "_write_verified_structural_transaction",
            return_value=sentinel,
        ) as writer:
            result = transaction._write_structural_transaction_with_stage_callback(
                "source.pmx",
                "output.pmx",
                transaction.PmxStructuralTransactionRequest(),
                overwrite=True,
                stage_callback=lambda _stage: None,
                _source_sha256_validator=validator,
            )

        self.assertIs(result, sentinel)
        writer.assert_called_once()
        self.assertIs(
            writer.call_args.kwargs["_source_sha256_validator"],
            validator,
        )
        self.assertIs(writer.call_args.kwargs["overwrite"], True)

    def test_matching_expected_identity_uses_atomic_authority_and_bounded_result(
        self,
    ) -> None:
        validated = _validated_plan(
            expected_source_sha256=self.source_sha256
        )

        result = apply_service.apply_structural_transaction_plan(
            self.source_path,
            self.output_path,
            validated,
        )

        self.assertEqual(result.status, "no_changes")
        self.assertTrue(result.expected_source_sha256_declared)
        self.assertEqual(result.source_identity_status, "matched")
        self.assertTrue(self.output_path.exists())
        self.assertEqual(self.source_path.read_bytes(), self.source_bytes)

        payload = result.to_dict()
        self.assertEqual(
            payload["source_identity"],
            {
                "algorithm": "sha256",
                "expected_source_sha256_declared": True,
                "status": "matched",
            },
        )
        self.assertFalse(payload["dry_run"])
        self.assertTrue(payload["output"]["written"])
        self.assertNotIn("path", payload["output"])
        self.assertNotIn("sha256", payload["output"])
        self.assertNotIn("source", payload)
        self.assertNotIn(
            "semantic_sha256",
            payload["plan"]["source"],
        )
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn(self.source_sha256, serialized)
        self.assertNotIn(str(self.source_path), serialized)
        self.assertNotIn(str(self.output_path), serialized)

    def test_undeclared_identity_remains_explicit_and_publishes_atomically(self) -> None:
        validated = _validated_plan(expected_source_sha256=None)

        result = apply_service.apply_structural_transaction_plan(
            self.source_path,
            self.output_path,
            validated,
        )

        self.assertFalse(result.expected_source_sha256_declared)
        self.assertEqual(result.source_identity_status, "not_declared")
        self.assertTrue(self.output_path.exists())
        self.assertEqual(
            result.to_dict()["source_identity"],
            {
                "algorithm": "sha256",
                "expected_source_sha256_declared": False,
                "status": "not_declared",
            },
        )

    def test_hash_mismatch_blocks_parse_serialization_and_publication(self) -> None:
        validated = _validated_plan(expected_source_sha256="0" * 64)

        with (
            patch.object(
                structural_output,
                "load_pmx",
                side_effect=AssertionError("parse must not run"),
            ) as parse,
            patch.object(
                transaction,
                "_verify_structural_transaction_serialization_with_stage_callback",
                side_effect=AssertionError("serialization must not run"),
            ) as serialize,
            patch.object(
                structural_output._edit_output,
                "_commit_verified_bytes",
                side_effect=AssertionError("publication must not run"),
            ) as commit,
            self.assertRaises(
                apply_service.PmxStructuralTransactionPlanApplyServiceError
            ) as raised,
        ):
            apply_service.apply_structural_transaction_plan(
                self.source_path,
                self.output_path,
                validated,
            )

        parse.assert_not_called()
        serialize.assert_not_called()
        commit.assert_not_called()
        self.assertFalse(self.output_path.exists())
        self.assertEqual(self.source_path.read_bytes(), self.source_bytes)

        diagnostic = raised.exception.to_dict()
        self.assertEqual(diagnostic["code"], "source_identity_mismatch")
        self.assertEqual(
            diagnostic["operation"],
            "apply_structural_transaction_plan",
        )
        self.assertEqual(
            diagnostic["details"],
            {
                "destination_published": False,
                "expected_source_sha256_declared": True,
                "source_parsed": False,
                "source_snapshot_captured": True,
            },
        )
        serialized = json.dumps(diagnostic, ensure_ascii=False)
        self.assertNotIn("0" * 64, serialized)
        self.assertNotIn(self.source_sha256, serialized)
        self.assertNotIn(str(self.source_path), serialized)
        self.assertNotIn(str(self.output_path), serialized)

    def test_existing_output_is_local_path_error_without_disclosure(self) -> None:
        self.output_path.write_bytes(b"private destination")
        validated = _validated_plan(expected_source_sha256=None)

        with self.assertRaises(
            apply_service.PmxStructuralTransactionPlanApplyServiceError
        ) as raised:
            apply_service.apply_structural_transaction_plan(
                self.source_path,
                self.output_path,
                validated,
            )

        diagnostic = raised.exception.to_dict()
        self.assertEqual(diagnostic["code"], "output_path_unsafe")
        self.assertNotIn(
            str(self.output_path),
            json.dumps(diagnostic, ensure_ascii=False),
        )
        self.assertEqual(self.output_path.read_bytes(), b"private destination")

    def test_invalid_source_translates_released_execution_error_safely(self) -> None:
        self.source_path.write_bytes(b"not-a-pmx")
        validated = _validated_plan(expected_source_sha256=None)

        with self.assertRaises(
            apply_service.PmxStructuralTransactionPlanApplyServiceError
        ) as raised:
            apply_service.apply_structural_transaction_plan(
                self.source_path,
                self.output_path,
                validated,
            )

        diagnostic = raised.exception.to_dict()
        self.assertEqual(diagnostic["code"], "source_invalid")
        self.assertEqual(
            diagnostic["operation"],
            "apply_structural_transaction_plan",
        )
        self.assertFalse(self.output_path.exists())
        self.assertNotIn(
            str(self.source_path),
            json.dumps(diagnostic, ensure_ascii=False),
        )

    def test_invalid_service_arguments_fail_before_execution(self) -> None:
        validated = _validated_plan(expected_source_sha256=None)

        with patch.object(
            apply_service,
            "_write_structural_transaction_with_stage_callback",
            side_effect=AssertionError("execution must not run"),
        ) as writer:
            with self.assertRaises(
                apply_service.PmxStructuralTransactionPlanApplyServiceError
            ) as invalid_plan:
                apply_service.apply_structural_transaction_plan(
                    self.source_path,
                    self.output_path,
                    object(),
                )
            with self.assertRaises(
                apply_service.PmxStructuralTransactionPlanApplyServiceError
            ) as invalid_overwrite:
                apply_service.apply_structural_transaction_plan(
                    self.source_path,
                    self.output_path,
                    validated,
                    overwrite=1,
                )

        writer.assert_not_called()
        self.assertEqual(invalid_plan.exception.to_dict()["code"], "invalid_argument")
        self.assertEqual(
            invalid_overwrite.exception.to_dict()["code"],
            "invalid_argument",
        )

    def test_process_control_exceptions_escape_service_boundary(self) -> None:
        validated = _validated_plan(expected_source_sha256=None)

        for failure in (KeyboardInterrupt(), SystemExit(18)):
            with (
                self.subTest(failure=type(failure).__name__),
                patch.object(
                    apply_service,
                    "_write_structural_transaction_with_stage_callback",
                    side_effect=failure,
                ),
                self.assertRaises(type(failure)) as raised,
            ):
                apply_service.apply_structural_transaction_plan(
                    self.source_path,
                    self.output_path,
                    validated,
                )
            if isinstance(failure, SystemExit):
                self.assertEqual(raised.exception.code, 18)

    def test_result_and_diagnostics_are_frozen_strict_and_deterministic(self) -> None:
        diagnostic = apply_service.PmxStructuralTransactionPlanApplyServiceDiagnostic(
            code=(
                apply_service.PmxStructuralTransactionPlanApplyServiceDiagnosticCode
                .SOURCE_IDENTITY_MISMATCH
            ),
            operation=(
                apply_service.PmxStructuralTransactionPlanApplyServiceOperation
                .APPLY
            ),
            message="blocked",
            details=(("source_snapshot_captured", True),),
        )
        self.assertTrue(is_dataclass(diagnostic))
        with self.assertRaises(FrozenInstanceError):
            diagnostic.message = "changed"  # type: ignore[misc]
        self.assertEqual(
            tuple(field.name for field in fields(diagnostic)),
            ("code", "operation", "message", "details"),
        )
        self.assertEqual(
            diagnostic.to_dict(),
            {
                "code": "source_identity_mismatch",
                "operation": "apply_structural_transaction_plan",
                "message": "blocked",
                "details": {"source_snapshot_captured": True},
            },
        )

    def test_cp18_service_adds_no_second_io_writer_or_publication_authority(
        self,
    ) -> None:
        source = inspect.getsource(apply_service)
        for forbidden in (
            "hashlib",
            ".open(",
            "read_bytes",
            "load_pmx",
            "load_document",
            "serialize_pmx",
            "_commit_verified_bytes",
            "write_pmx",
            "PmxIndexRemap",
            "final_index",
            "apply_structural_transaction(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)
        self.assertIn(
            "_write_structural_transaction_with_stage_callback",
            source,
        )
        self.assertIn("_source_sha256_validator", source)

    def test_import_is_explicit_and_does_not_promote_or_eagerly_load_cli(self) -> None:
        script = "\n".join(
            (
                "import sys",
                "import mmd_registry.services as root",
                "import mmd_registry.services.structural_transaction_plan_apply as module",
                "assert module.__all__",
                "assert 'mmd_registry.transaction_plan_cli' not in sys.modules",
                "assert not hasattr(root, 'apply_structural_transaction_plan')",
            )
        )
        subprocess.check_call(
            (sys.executable, "-c", script),
            cwd=Path(__file__).resolve().parents[1],
        )


if __name__ == "__main__":
    unittest.main()
