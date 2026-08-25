"""CP25 cross-generation compatibility gates for structural transactions."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import fields, replace
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import mmd_registry
import mmd_registry.pmx as pmx
import mmd_registry.services as services
from mmd_registry import capabilities, cli, constants, diagnostics
from mmd_registry.pmx.editing.json_loader import parse_pmx_edit_plan_json
from mmd_registry.pmx.editing.output import write_pmx_edit
from mmd_registry.pmx.editing.plan import PMX_EDIT_PLAN_SCHEMA_VERSION
from mmd_registry.pmx.editing.preview import dry_run_pmx_edit
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.writer import serialize_pmx
from mmd_registry.services import structural_transaction as transactions
from mmd_registry.services.structural_texture import (
    PmxStructuralTextureInsertion,
)
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


RELEASED_SERVICE_EXPORTS = (
    "PmxDocumentMetadata",
    "PmxDocumentValidationResult",
    "apply_edit",
    "get_capabilities",
    "inspect_document",
    "load_document",
    "preview_edit",
    "validate_document",
    "PmxReferenceAnalysisResult",
    "PmxReferenceDiagnostic",
    "PmxReferenceDiagnosticCode",
    "PmxReferenceImpact",
    "PmxReferenceNode",
    "PmxReferenceTargetKind",
    "analyze_reference_node",
    "analyze_references",
    "PmxStructuralCollectionEdit",
    "PmxStructuralPreviewRequest",
    "PmxStructuralPreviewResult",
    "preview_structural_edit",
    "PmxStructuralEditRequest",
    "PmxStructuralExecutionResult",
    "apply_structural_edit",
)
TRANSACTION_EXPORTS = (
    "PmxStructuralTransactionOperation",
    "PmxStructuralTransactionRequest",
    "PmxStructuralTransactionPreviewResult",
    "preview_structural_transaction",
    "apply_structural_transaction",
)
CAPABILITY_FIELDS = (
    "pmx_versions",
    "text_encodings",
    "index_sizes",
    "deform_types",
    "morph_types",
    "soft_body_support",
    "roundtrip_contract",
    "edit_operation_types",
    "texture_portability",
    "private_runtime_required",
    "structural_preview",
    "structural_write",
    "structural_target_kinds",
    "structural_contract",
    "structural_insert",
)
EDIT_REPORT_KEYS = {
    "preview_schema_version",
    "status",
    "dry_run",
    "source",
    "plan",
    "output",
    "verification",
    "audit",
}


def _clean_document():
    return replace(
        load_pmx(
            io.BytesIO(
                build_pmx_roundtrip_fixture(
                    version=2.1,
                    index_size=1,
                )
            )
        ),
        trailing_data=b"",
    )


def _legacy_collection_request(document):
    order = tuple(reversed(range(len(document.texture_paths))))
    return services.PmxStructuralPreviewRequest(
        (
            services.PmxStructuralCollectionEdit(
                services.PmxReferenceTargetKind.TEXTURE,
                order,
            ),
        )
    )


def _legacy_insertion_request(label: str):
    return services.PmxStructuralPreviewRequest(
        texture_insertions=(
            PmxStructuralTextureInsertion(f"textures/{label}.png"),
        )
    )


def _transaction_request(label: str):
    return transactions.PmxStructuralTransactionRequest(
        (
            PmxStructuralTextureInsertion(f"textures/{label}.png"),
        )
    )


def _invalid_transaction_request(document):
    return transactions.PmxStructuralTransactionRequest(
        (
            services.PmxStructuralCollectionEdit(
                services.PmxReferenceTargetKind.TEXTURE,
                (len(document.texture_paths),),
            ),
        )
    )


def _invalid_legacy_request(document):
    return services.PmxStructuralPreviewRequest(
        (
            services.PmxStructuralCollectionEdit(
                services.PmxReferenceTargetKind.TEXTURE,
                (len(document.texture_paths),),
            ),
        )
    )


def _legacy_edit_plan(source_bytes: bytes):
    payload = {
        "schema_version": 1,
        "expected_source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "operations": [
            {
                "op": "set_model_info",
                "local_name": "CP25 Legacy Compatibility",
            }
        ],
    }
    return parse_pmx_edit_plan_json(json.dumps(payload))


def _normalized_output_report(result) -> dict[str, object]:
    report = result.to_dict()
    output = report["output"]
    assert isinstance(output, dict)
    output["path"] = "<caller-destination>"
    return report


def _capture_cli(arguments: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = cli.run(arguments)
    return exit_code, stdout.getvalue(), stderr.getvalue()


class V093StructuralTransactionBackwardCompatibilityTests(unittest.TestCase):
    """Prove transaction work stays additive to v0.8-v0.9.2 facades."""

    def test_transaction_api_is_explicit_and_not_promoted_to_old_facades(
        self,
    ) -> None:
        self.assertEqual(mmd_registry.__all__, ("__version__",))
        self.assertEqual(len(services.__all__), len(set(services.__all__)))
        service_positions = tuple(
            services.__all__.index(name) for name in RELEASED_SERVICE_EXPORTS
        )
        self.assertEqual(service_positions, tuple(sorted(service_positions)))
        for name in RELEASED_SERVICE_EXPORTS:
            self.assertTrue(hasattr(services, name), name)
        self.assertEqual(transactions.__all__, TRANSACTION_EXPORTS)
        self.assertEqual(len(transactions.__all__), len(set(transactions.__all__)))

        for name in TRANSACTION_EXPORTS:
            with self.subTest(name=name):
                self.assertTrue(hasattr(transactions, name))
                self.assertNotIn(name, mmd_registry.__all__)
                self.assertNotIn(name, pmx.__all__)
                self.assertNotIn(name, services.__all__)
                self.assertFalse(hasattr(services, name))

        manifest_fields = tuple(
            field.name for field in fields(capabilities.PmxCapabilityManifest)
        )
        self.assertGreaterEqual(len(manifest_fields), len(CAPABILITY_FIELDS))
        self.assertEqual(
            manifest_fields[: len(CAPABILITY_FIELDS)],
            CAPABILITY_FIELDS,
        )
        self.assertEqual(
            manifest_fields[len(CAPABILITY_FIELDS) :],
            ("structural_transaction",),
        )
        self.assertTrue(
            capabilities.get_capabilities().structural_transaction
        )
        legacy_manifest = capabilities.PmxCapabilityManifest(
            pmx_versions=(2.0, 2.1),
            text_encodings=("utf-16-le", "utf-8"),
            index_sizes=(1, 2, 4),
            deform_types=(0, 1, 2, 3, 4),
            morph_types=tuple(range(11)),
            soft_body_support=True,
            roundtrip_contract="validated_semantic_roundtrip",
            edit_operation_types=(
                "set_model_info",
                "set_texture_path",
                "update_material",
            ),
            texture_portability=True,
            private_runtime_required=False,
        )
        self.assertFalse(legacy_manifest.structural_transaction)
        self.assertEqual(mmd_registry.__version__, "0.9.3")

    def test_v08_edit_preview_and_write_survive_transaction_activity(self) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)
        plan = _legacy_edit_plan(source_bytes)
        preview_before = dry_run_pmx_edit(source_bytes, plan).to_dict()

        transactions.preview_structural_transaction(
            document,
            _transaction_request("v08-preview"),
        )
        with self.assertRaises(diagnostics.PmxServiceError):
            transactions.preview_structural_transaction(
                document,
                _invalid_transaction_request(document),
            )

        preview_after = dry_run_pmx_edit(source_bytes, plan).to_dict()
        self.assertEqual(preview_before, preview_after)
        self.assertEqual(set(preview_after), EDIT_REPORT_KEYS)
        self.assertEqual(PMX_EDIT_PLAN_SCHEMA_VERSION, 1)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            edit_before = root / "edit-before.pmx"
            transaction_output = root / "transaction.pmx"
            edit_after = root / "edit-after.pmx"
            source.write_bytes(source_bytes)

            first = write_pmx_edit(source, edit_before, plan)
            transactions.apply_structural_transaction(
                source,
                transaction_output,
                _transaction_request("v08-execution"),
            )
            second = write_pmx_edit(source, edit_after, plan)

            self.assertEqual(
                _normalized_output_report(first),
                _normalized_output_report(second),
            )
            self.assertEqual(edit_before.read_bytes(), edit_after.read_bytes())
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_v090_preview_survives_transaction_success_and_failure(self) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)
        legacy_request = _legacy_collection_request(document)
        before = services.preview_structural_edit(document, legacy_request)

        transaction_preview = transactions.preview_structural_transaction(
            document,
            _transaction_request("v090-success"),
        )
        with self.assertRaises(diagnostics.PmxServiceError):
            transactions.preview_structural_transaction(
                document,
                _invalid_transaction_request(document),
            )
        after = services.preview_structural_edit(document, legacy_request)

        self.assertEqual(before.to_dict(), after.to_dict())
        self.assertEqual(before.document, after.document)
        self.assertEqual(serialize_pmx(document), source_bytes)
        self.assertEqual(
            len(transaction_preview.document.texture_paths),
            len(document.texture_paths) + 1,
        )

    def test_v091_execution_survives_transaction_publication(self) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)
        legacy_request = _legacy_collection_request(document)
        legacy_preview = services.preview_structural_edit(document, legacy_request)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            legacy_before = root / "legacy-before.pmx"
            transaction_output = root / "transaction.pmx"
            legacy_after = root / "legacy-after.pmx"
            source.write_bytes(source_bytes)

            first = services.apply_structural_edit(
                source,
                legacy_before,
                legacy_request,
            )
            transactions.apply_structural_transaction(
                source,
                transaction_output,
                _transaction_request("v091-transaction"),
            )
            second = services.apply_structural_edit(
                source,
                legacy_after,
                legacy_request,
            )

            self.assertEqual(
                _normalized_output_report(first),
                _normalized_output_report(second),
            )
            self.assertEqual(first.document, legacy_preview.document)
            self.assertEqual(second.document, legacy_preview.document)
            self.assertEqual(legacy_before.read_bytes(), legacy_after.read_bytes())
            self.assertEqual(load_pmx(legacy_after), legacy_preview.document)
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_v092_insertion_survives_transaction_activity(self) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)
        legacy_request = _legacy_insertion_request("v092-legacy")
        preview_before = services.preview_structural_edit(document, legacy_request)

        transactions.preview_structural_transaction(
            document,
            _transaction_request("v092-preview"),
        )
        with self.assertRaises(diagnostics.PmxServiceError):
            transactions.preview_structural_transaction(
                document,
                _invalid_transaction_request(document),
            )
        preview_after = services.preview_structural_edit(document, legacy_request)

        self.assertEqual(preview_before.to_dict(), preview_after.to_dict())
        self.assertEqual(preview_before.document, preview_after.document)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            insertion_before = root / "insertion-before.pmx"
            transaction_output = root / "transaction.pmx"
            insertion_after = root / "insertion-after.pmx"
            source.write_bytes(source_bytes)

            first = services.apply_structural_edit(
                source,
                insertion_before,
                legacy_request,
            )
            transactions.apply_structural_transaction(
                source,
                transaction_output,
                _transaction_request("v092-execution"),
            )
            second = services.apply_structural_edit(
                source,
                insertion_after,
                legacy_request,
            )

            self.assertEqual(
                _normalized_output_report(first),
                _normalized_output_report(second),
            )
            self.assertEqual(
                insertion_before.read_bytes(),
                insertion_after.read_bytes(),
            )
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_capability_schema_and_legacy_diagnostics_remain_exact(self) -> None:
        document = _clean_document()
        capabilities_before = services.get_capabilities().to_dict()
        with self.assertRaises(diagnostics.PmxServiceError) as legacy_before:
            services.preview_structural_edit(
                document,
                _invalid_legacy_request(document),
            )

        transactions.preview_structural_transaction(
            document,
            _transaction_request("capability"),
        )
        with self.assertRaises(diagnostics.PmxServiceError):
            transactions.preview_structural_transaction(
                document,
                _invalid_transaction_request(document),
            )

        capabilities_after = services.get_capabilities().to_dict()
        with self.assertRaises(diagnostics.PmxServiceError) as legacy_after:
            services.preview_structural_edit(
                document,
                _invalid_legacy_request(document),
            )

        self.assertEqual(capabilities_before, capabilities_after)
        self.assertEqual(
            capabilities.get_pmx_capability_manifest().to_dict(),
            capabilities_after,
        )
        self.assertEqual(
            legacy_before.exception.to_dict(),
            legacy_after.exception.to_dict(),
        )
        self.assertEqual(constants.LATEST_SCHEMA_VERSION, "0.3")
        self.assertEqual(
            constants.SUPPORTED_SCHEMA_VERSIONS,
            frozenset(("0.2", "0.3")),
        )
        self.assertEqual(PMX_EDIT_PLAN_SCHEMA_VERSION, 1)

    def test_legacy_cli_contract_is_stable_after_transaction_failures(self) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            plan_path = root / "invalid-plan.json"
            source.write_bytes(source_bytes)
            plan_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "operations": [
                            {
                                "op": "rename_model",
                                "local_name": "unsupported",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            arguments = [
                "edit",
                str(source),
                "--plan",
                str(plan_path),
                "--dry-run",
                "--json",
            ]

            before = _capture_cli(arguments)
            with self.assertRaises(diagnostics.PmxServiceError):
                transactions.preview_structural_transaction(
                    document,
                    _invalid_transaction_request(document),
                )
            after = _capture_cli(arguments)

        self.assertEqual(before, after)
        self.assertEqual(before[0], 1)
        self.assertEqual(before[2], "")
        payload = json.loads(before[1])
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error_type"], "invalid_plan")
        self.assertEqual(payload["error"]["code"], "edit_plan_invalid")
        self.assertEqual(payload["error"]["phase"], "plan_validate")

    def test_cross_generation_sequence_is_repeatable(self) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)
        plan = _legacy_edit_plan(source_bytes)
        legacy_request = _legacy_collection_request(document)
        insertion_request = _legacy_insertion_request("sequence")
        transaction_request = _transaction_request("sequence")

        def capture_sequence() -> tuple[object, ...]:
            return (
                dry_run_pmx_edit(source_bytes, plan).to_dict(),
                services.preview_structural_edit(
                    document,
                    legacy_request,
                ).to_dict(),
                services.preview_structural_edit(
                    document,
                    insertion_request,
                ).to_dict(),
                transactions.preview_structural_transaction(
                    document,
                    transaction_request,
                ).to_dict(),
                services.get_capabilities().to_dict(),
            )

        before = capture_sequence()
        with self.assertRaises(diagnostics.PmxServiceError):
            transactions.preview_structural_transaction(
                document,
                _invalid_transaction_request(document),
            )
        after = capture_sequence()

        self.assertEqual(before, after)
        self.assertEqual(serialize_pmx(document), source_bytes)


if __name__ == "__main__":
    unittest.main()
