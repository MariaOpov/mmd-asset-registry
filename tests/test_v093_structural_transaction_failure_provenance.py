"""CP22 frozen structural-transaction failure provenance regression gates."""

from __future__ import annotations

from dataclasses import replace
import inspect
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import mmd_registry
import mmd_registry.pmx as pmx
import mmd_registry.pmx.editing.output as edit_output
import mmd_registry.services as services
import mmd_registry.services.structural_transaction as transaction
from mmd_registry.diagnostics import (
    PmxServiceDiagnosticCode,
    PmxServiceError,
    PmxServiceOperation,
)
from mmd_registry.pmx.editing.errors import (
    PmxEditPathError,
    PmxEditVerificationError,
)
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.pmx.structural_output import (
    PmxStructuralOutputVerificationError,
)
from mmd_registry.pmx.structural_transaction_preview import (
    PmxStructuralTransactionPreviewError,
)
from mmd_registry.pmx.writer import serialize_pmx
from mmd_registry.services import PmxStructuralExecutionResult
from mmd_registry.services.structural_transaction import (
    PmxStructuralTransactionRequest,
    apply_structural_transaction,
    preview_structural_transaction,
)
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


PRIVATE_DETAIL = r"C:\private\秘密-cp22-provenance.pmx"
EXPECTED_PROVENANCE = (
    ("service_validation", "service_boundary"),
    ("path_resolution", "safe_output"),
    ("source_snapshot", "source_input"),
    ("source_parse", "source_input"),
    ("transaction_normalization", "transaction_plan"),
    ("reference_resolution", "transaction_plan"),
    ("dependency_resolution", "transaction_plan"),
    ("capacity_preflight", "transaction_plan"),
    ("transform", "structural_pipeline"),
    ("structural_certification", "structural_pipeline"),
    ("serialization", "structural_pipeline"),
    ("reparse", "structural_pipeline"),
    ("reparse_certification", "structural_pipeline"),
    ("semantic_compare", "structural_pipeline"),
    ("source_reverify", "safe_output"),
    ("output_commit", "safe_output"),
)
SUCCESS_STAGES = tuple(stage for stage, _provenance in EXPECTED_PROVENANCE[1:])


def _clean_document():
    return replace(
        load_pmx(io.BytesIO(build_pmx_roundtrip_fixture(version=2.1))),
        trailing_data=b"",
    )


def _details(error: PmxServiceError) -> dict[str, object]:
    details = error.to_dict()["details"]
    assert isinstance(details, dict)
    return details


class V093StructuralTransactionFailureProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source.pmx"
        self.source_bytes = serialize_pmx(_clean_document())
        self.source.write_bytes(self.source_bytes)
        self.request = PmxStructuralTransactionRequest()

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def _temporary_outputs(destination: Path) -> list[Path]:
        return list(destination.parent.glob(f".{destination.name}.*.tmp"))

    def test_public_surface_signature_and_operation_are_exactly_additive(self) -> None:
        self.assertEqual(
            transaction.__all__,
            (
                "PmxStructuralTransactionOperation",
                "PmxStructuralTransactionRequest",
                "PmxStructuralTransactionPreviewResult",
                "preview_structural_transaction",
                "apply_structural_transaction",
            ),
        )
        signature = inspect.signature(apply_structural_transaction)
        self.assertEqual(
            tuple(signature.parameters),
            ("input_path", "output_path", "request", "overwrite"),
        )
        self.assertIs(
            signature.parameters["overwrite"].kind,
            inspect.Parameter.KEYWORD_ONLY,
        )
        self.assertIs(signature.parameters["overwrite"].default, False)
        self.assertEqual(
            signature.return_annotation,
            "PmxStructuralExecutionResult",
        )
        self.assertEqual(
            PmxServiceOperation.APPLY_STRUCTURAL_TRANSACTION.value,
            "apply_structural_transaction",
        )
        self.assertFalse(hasattr(mmd_registry, "apply_structural_transaction"))
        self.assertFalse(hasattr(pmx, "apply_structural_transaction"))
        self.assertFalse(hasattr(services, "apply_structural_transaction"))

    def test_failure_provenance_table_is_immutable_complete_and_exact(self) -> None:
        table = transaction._TRANSACTION_FAILURE_PROVENANCE
        self.assertIsInstance(table, tuple)
        self.assertEqual(table, EXPECTED_PROVENANCE)
        self.assertTrue(
            all(
                type(item) is tuple
                and len(item) == 2
                and all(type(value) is str for value in item)
                for item in table
            )
        )
        for stage, provenance in table:
            self.assertEqual(
                transaction._transaction_failure_provenance(stage),
                provenance,
            )
        with self.assertRaises(AssertionError):
            transaction._transaction_failure_provenance("unknown_stage")

    def test_success_reports_exact_stage_order_and_reuses_result_vocabulary(
        self,
    ) -> None:
        destination = self.root / "internal-output.pmx"
        stages: list[str] = []
        internal = transaction._write_structural_transaction_with_stage_callback(
            self.source,
            destination,
            self.request,
            overwrite=False,
            stage_callback=stages.append,
        )
        self.assertEqual(tuple(stages), SUCCESS_STAGES)
        self.assertEqual(destination.read_bytes(), internal.serialization.serialized_bytes)

        public_destination = self.root / "public-output.pmx"
        result = apply_structural_transaction(
            self.source,
            public_destination,
            self.request,
        )
        preview = preview_structural_transaction(_clean_document(), self.request)
        self.assertIsInstance(result, PmxStructuralExecutionResult)
        self.assertEqual(result.source_sha256, internal.source_sha256)
        self.assertEqual(result.output_sha256, internal.output_sha256)
        self.assertEqual(
            result.to_dict()["plan"]["sha256"],
            preview.plan_sha256,
        )
        self.assertEqual(self.source.read_bytes(), self.source_bytes)
        self.assertEqual(public_destination.read_bytes(), self.source_bytes)
        self.assertEqual(self._temporary_outputs(public_destination), [])

    def test_service_validation_failures_are_deterministic_and_nonpublishing(
        self,
    ) -> None:
        destination = self.root / "invalid.pmx"
        cases = (
            {"request": object(), "overwrite": False},
            {"request": self.request, "overwrite": 1},
        )
        reports: list[dict[str, object]] = []
        with patch.object(
            transaction,
            "_write_structural_transaction_with_stage_callback",
            side_effect=AssertionError("writer must not run"),
        ) as writer:
            for arguments in cases:
                with self.subTest(arguments=arguments):
                    with self.assertRaises(PmxServiceError) as raised:
                        apply_structural_transaction(
                            self.source,
                            destination,
                            arguments["request"],  # type: ignore[arg-type]
                            overwrite=arguments["overwrite"],  # type: ignore[arg-type]
                        )
                    reports.append(raised.exception.to_dict())
                    self.assertEqual(
                        raised.exception.diagnostic.code,
                        PmxServiceDiagnosticCode.INVALID_ARGUMENT,
                    )
                    self.assertEqual(
                        raised.exception.diagnostic.message,
                        "Invalid service input.",
                    )
                    self.assertEqual(
                        _details(raised.exception),
                        {
                            "destination_published": False,
                            "provenance": "service_boundary",
                            "source_bytes_read": False,
                            "source_modified": False,
                            "stage": "service_validation",
                        },
                    )
        writer.assert_not_called()
        self.assertEqual(reports[0], reports[1])
        self.assertFalse(destination.exists())

    def test_path_and_source_failures_freeze_read_state_and_redaction(self) -> None:
        with self.assertRaises(PmxServiceError) as path_raised:
            apply_structural_transaction(
                self.source,
                self.source,
                self.request,
            )
        self.assertEqual(
            path_raised.exception.diagnostic.code,
            PmxServiceDiagnosticCode.STRUCTURAL_PATH_UNSAFE,
        )
        self.assertEqual(
            path_raised.exception.diagnostic.message,
            "Structural output path failed safety validation.",
        )
        self.assertEqual(
            _details(path_raised.exception),
            {
                "destination_published": False,
                "provenance": "safe_output",
                "source_bytes_read": False,
                "source_modified": False,
                "stage": "path_resolution",
            },
        )

        snapshot_destination = self.root / "snapshot-failure.pmx"
        with patch.object(
            Path,
            "read_bytes",
            side_effect=PermissionError(13, PRIVATE_DETAIL),
        ):
            with self.assertRaises(PmxServiceError) as snapshot_raised:
                apply_structural_transaction(
                    self.source,
                    snapshot_destination,
                    self.request,
                )
        self.assertEqual(
            snapshot_raised.exception.diagnostic.code,
            PmxServiceDiagnosticCode.IO_FAILED,
        )
        self.assertEqual(
            _details(snapshot_raised.exception),
            {
                "destination_published": False,
                "errno": 13,
                "provenance": "source_input",
                "source_bytes_read": False,
                "source_modified": False,
                "stage": "source_snapshot",
            },
        )
        self.assertNotIn(PRIVATE_DETAIL, repr(snapshot_raised.exception.to_dict()))
        self.assertFalse(snapshot_destination.exists())

        invalid_source = self.root / "invalid-source.pmx"
        parse_destination = self.root / "parse-failure.pmx"
        invalid_source.write_bytes(b"not a pmx document")
        with self.assertRaises(PmxServiceError) as parse_raised:
            apply_structural_transaction(
                invalid_source,
                parse_destination,
                self.request,
            )
        self.assertEqual(
            parse_raised.exception.diagnostic.code,
            PmxServiceDiagnosticCode.SOURCE_INVALID,
        )
        parse_details = _details(parse_raised.exception)
        self.assertEqual(parse_details["stage"], "source_parse")
        self.assertEqual(parse_details["provenance"], "source_input")
        self.assertIs(parse_details["source_bytes_read"], True)
        self.assertIs(parse_details["source_modified"], False)
        self.assertIs(parse_details["destination_published"], False)
        self.assertFalse(parse_destination.exists())

    def test_planning_blockers_preserve_bounded_operation_context(self) -> None:
        stages = (
            "transaction_normalization",
            "reference_resolution",
            "dependency_resolution",
            "capacity_preflight",
            "transform",
            "structural_certification",
        )
        for stage in stages:
            destination = self.root / f"{stage}.pmx"

            def fail_plan(
                _input_path: str | Path,
                _output_path: str | Path,
                _request: PmxStructuralTransactionRequest,
                *,
                overwrite: bool,
                stage_callback,
            ) -> None:
                self.assertIs(overwrite, False)
                stage_callback("source_parse")
                stage_callback(stage)
                raise PmxStructuralTransactionPreviewError(
                    stage,
                    operation_index=2,
                    target_kind=PmxReferenceTargetKind.TEXTURE,
                    new_id="cp22.texture",
                    relationship_id="material.texture",
                )

            with self.subTest(stage=stage):
                with patch.object(
                    transaction,
                    "_write_structural_transaction_with_stage_callback",
                    side_effect=fail_plan,
                ):
                    with self.assertRaises(PmxServiceError) as raised:
                        apply_structural_transaction(
                            self.source,
                            destination,
                            self.request,
                        )
                self.assertEqual(
                    raised.exception.diagnostic.code,
                    PmxServiceDiagnosticCode.STRUCTURAL_VERIFICATION_FAILED,
                )
                self.assertEqual(
                    raised.exception.diagnostic.message,
                    "Structural execution failed reference-safety validation.",
                )
                self.assertEqual(
                    _details(raised.exception),
                    {
                        "destination_published": False,
                        "new_id": "cp22.texture",
                        "operation_index": 2,
                        "provenance": dict(EXPECTED_PROVENANCE)[stage],
                        "relationship_id": "material.texture",
                        "source_bytes_read": True,
                        "source_modified": False,
                        "stage": stage,
                        "target_kind": "texture",
                    },
                )
                self.assertFalse(destination.exists())

    def test_pipeline_blockers_are_redacted_and_never_publish(self) -> None:
        stages = (
            "serialization",
            "reparse",
            "reparse_certification",
            "semantic_compare",
            "source_reverify",
        )
        for stage in stages:
            destination = self.root / f"{stage}.pmx"

            def fail_pipeline(
                _input_path: str | Path,
                _output_path: str | Path,
                _request: PmxStructuralTransactionRequest,
                *,
                overwrite: bool,
                stage_callback,
            ) -> None:
                self.assertIs(overwrite, False)
                stage_callback("source_parse")
                stage_callback(stage)
                raise PmxStructuralOutputVerificationError(PRIVATE_DETAIL)

            with self.subTest(stage=stage):
                with patch.object(
                    transaction,
                    "_write_structural_transaction_with_stage_callback",
                    side_effect=fail_pipeline,
                ):
                    with self.assertRaises(PmxServiceError) as raised:
                        apply_structural_transaction(
                            self.source,
                            destination,
                            self.request,
                        )
                self.assertEqual(
                    raised.exception.diagnostic.code,
                    PmxServiceDiagnosticCode.STRUCTURAL_VERIFICATION_FAILED,
                )
                self.assertEqual(
                    _details(raised.exception),
                    {
                        "destination_published": False,
                        "provenance": dict(EXPECTED_PROVENANCE)[stage],
                        "source_bytes_read": True,
                        "source_modified": False,
                        "stage": stage,
                    },
                )
                self.assertNotIn(PRIVATE_DETAIL, repr(raised.exception.to_dict()))
                self.assertFalse(destination.exists())

    def test_source_reverify_and_destination_race_have_distinct_stages(self) -> None:
        source_race_output = self.root / "source-race.pmx"
        with patch.object(
            edit_output,
            "_verify_source_unchanged",
            side_effect=PmxEditVerificationError(PRIVATE_DETAIL),
        ):
            with self.assertRaises(PmxServiceError) as source_race:
                apply_structural_transaction(
                    self.source,
                    source_race_output,
                    self.request,
                )
        self.assertEqual(
            source_race.exception.diagnostic.code,
            PmxServiceDiagnosticCode.STRUCTURAL_VERIFICATION_FAILED,
        )
        self.assertEqual(
            _details(source_race.exception),
            {
                "destination_published": False,
                "provenance": "safe_output",
                "source_bytes_read": True,
                "source_modified": False,
                "stage": "source_reverify",
            },
        )
        self.assertFalse(source_race_output.exists())
        self.assertEqual(self._temporary_outputs(source_race_output), [])

        destination_race_output = self.root / "destination-race.pmx"
        original_validate = edit_output._validate_destination_state
        calls = 0

        def fail_second_validation(
            source: Path,
            output: Path,
            *,
            overwrite: bool,
        ) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise PmxEditPathError(PRIVATE_DETAIL)
            return original_validate(source, output, overwrite=overwrite)

        with patch.object(
            edit_output,
            "_validate_destination_state",
            side_effect=fail_second_validation,
        ):
            with self.assertRaises(PmxServiceError) as destination_race:
                apply_structural_transaction(
                    self.source,
                    destination_race_output,
                    self.request,
                )
        self.assertEqual(calls, 2)
        self.assertEqual(
            destination_race.exception.diagnostic.code,
            PmxServiceDiagnosticCode.STRUCTURAL_PATH_UNSAFE,
        )
        self.assertEqual(
            _details(destination_race.exception),
            {
                "destination_published": False,
                "provenance": "safe_output",
                "source_bytes_read": True,
                "source_modified": False,
                "stage": "output_commit",
            },
        )
        self.assertNotIn(PRIVATE_DETAIL, repr(destination_race.exception.to_dict()))
        self.assertFalse(destination_race_output.exists())
        self.assertEqual(self._temporary_outputs(destination_race_output), [])

    def test_publication_io_failure_is_bounded_and_cleans_temporary_output(
        self,
    ) -> None:
        destination = self.root / "publish-failure.pmx"
        with patch.object(
            edit_output,
            "_publish_no_clobber",
            side_effect=PermissionError(13, PRIVATE_DETAIL),
        ):
            with self.assertRaises(PmxServiceError) as raised:
                apply_structural_transaction(
                    self.source,
                    destination,
                    self.request,
                )
        self.assertEqual(
            raised.exception.diagnostic.code,
            PmxServiceDiagnosticCode.IO_FAILED,
        )
        self.assertEqual(
            _details(raised.exception),
            {
                "destination_published": False,
                "errno": 13,
                "provenance": "safe_output",
                "source_bytes_read": True,
                "source_modified": False,
                "stage": "output_commit",
            },
        )
        self.assertNotIn(PRIVATE_DETAIL, repr(raised.exception.to_dict()))
        self.assertEqual(self.source.read_bytes(), self.source_bytes)
        self.assertFalse(destination.exists())
        self.assertEqual(self._temporary_outputs(destination), [])

    def test_process_control_exceptions_are_not_downgraded(self) -> None:
        destination = self.root / "process-control.pmx"
        for failure in (KeyboardInterrupt(), SystemExit(17)):
            with self.subTest(failure=type(failure).__name__):
                with patch.object(
                    transaction,
                    "_write_structural_transaction_with_stage_callback",
                    side_effect=failure,
                ):
                    with self.assertRaises(type(failure)) as raised:
                        apply_structural_transaction(
                            self.source,
                            destination,
                            self.request,
                        )
                if isinstance(failure, SystemExit):
                    self.assertEqual(raised.exception.code, 17)
        self.assertFalse(destination.exists())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
