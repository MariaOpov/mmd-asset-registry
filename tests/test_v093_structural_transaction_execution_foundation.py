"""Freeze the CP18 shared structural transaction planning authority."""

from __future__ import annotations

import builtins
from dataclasses import replace
import importlib
import inspect
import io
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import mmd_registry
import mmd_registry.pmx as pmx
import mmd_registry.services as services
from mmd_registry.diagnostics import (
    PmxServiceDiagnosticCode,
    PmxServiceError,
    PmxServiceOperation,
)
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.structural_transaction_preview import (
    PmxStructuralTransactionPreview,
    PmxStructuralTransactionPreviewError,
)
from mmd_registry.pmx.writer import serialize_pmx
from mmd_registry.services.structural_material import (
    PmxStructuralMaterialInsertion,
)
from mmd_registry.services.structural_reference import (
    PmxStructuralNewReference,
)
from mmd_registry.services.structural_texture import (
    PmxStructuralTextureInsertion,
)
from mmd_registry.services.structural_transaction import (
    PmxStructuralTransactionPreviewResult,
    PmxStructuralTransactionRequest,
    preview_structural_transaction,
)
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


TRANSACTION_MODULE_NAME = "mmd_registry.services.structural_transaction"
PUBLIC_TRANSACTION_SURFACE = (
    "PmxStructuralTransactionOperation",
    "PmxStructuralTransactionRequest",
    "PmxStructuralTransactionPreviewResult",
    "preview_structural_transaction",
)
NOOP_PLAN_SHA256 = (
    "9640b9df4b009c6f5e6688cdf7ea6385a56446abcdd6964e6783b7387441d77b"
)


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


def _forward_reference_request() -> PmxStructuralTransactionRequest:
    return PmxStructuralTransactionRequest(
        (
            PmxStructuralMaterialInsertion(
                "shared authority material",
                texture_index=PmxStructuralNewReference(
                    "texture",
                    "shared.texture",
                ),
            ),
            PmxStructuralTextureInsertion(
                "textures/shared-authority.png",
                new_id="shared.texture",
            ),
        )
    )


def _details(error: PmxServiceError) -> dict[str, object]:
    value = error.to_dict().get("details")
    assert isinstance(value, dict)
    return value


class V093StructuralTransactionExecutionFoundationTests(unittest.TestCase):
    def test_private_planner_is_exact_typed_nonexported_seam(self) -> None:
        transaction = importlib.import_module(TRANSACTION_MODULE_NAME)
        planner = transaction._plan_structural_transaction

        self.assertEqual(
            tuple(inspect.signature(planner).parameters),
            ("document", "request"),
        )
        self.assertIs(
            inspect.get_annotations(planner, eval_str=True)["return"],
            PmxStructuralTransactionPreview,
        )
        self.assertNotIn("_plan_structural_transaction", transaction.__all__)
        self.assertFalse(hasattr(mmd_registry, "_plan_structural_transaction"))
        self.assertFalse(hasattr(services, "_plan_structural_transaction"))
        self.assertFalse(hasattr(pmx, "_plan_structural_transaction"))

        source = inspect.getsource(transaction)
        for forbidden in (
            "structural_output",
            "apply_structural_transaction",
            "open(",
            "pathlib",
        ):
            self.assertNotIn(forbidden, source)

    def test_public_preview_delegates_once_and_wraps_exact_plan(self) -> None:
        transaction = importlib.import_module(TRANSACTION_MODULE_NAME)
        document = _clean_document()
        request = _forward_reference_request()
        planned = transaction._plan_structural_transaction(document, request)

        with patch.object(
            transaction,
            "_plan_structural_transaction",
            return_value=planned,
        ) as planner:
            result = transaction.preview_structural_transaction(
                document,
                request,
            )

        planner.assert_called_once_with(document, request)
        self.assertIsInstance(result, PmxStructuralTransactionPreviewResult)
        self.assertIs(result._preview, planned)

    def test_private_and_public_plans_have_exact_evidence_parity(self) -> None:
        transaction = importlib.import_module(TRANSACTION_MODULE_NAME)
        document = _clean_document()
        request = _forward_reference_request()

        internal = transaction._plan_structural_transaction(document, request)
        public = preview_structural_transaction(document, request)

        self.assertIsNot(internal, public._preview)
        self.assertEqual(internal, public._preview)
        self.assertEqual(internal.certificate.document, public.document)
        self.assertEqual(internal.plan_sha256, public.plan_sha256)
        self.assertEqual(internal.to_dict(), public.to_dict())

    def test_captured_typed_source_rebuilds_plan_without_prior_evidence(
        self,
    ) -> None:
        transaction = importlib.import_module(TRANSACTION_MODULE_NAME)
        source = _clean_document()
        captured = load_pmx(io.BytesIO(serialize_pmx(source)))
        request = _forward_reference_request()

        with patch.object(
            builtins,
            "open",
            side_effect=AssertionError("typed planning must not access files"),
        ):
            first = transaction._plan_structural_transaction(captured, request)
            second = transaction._plan_structural_transaction(captured, request)

        self.assertIsNot(first, second)
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(first.plan_sha256, second.plan_sha256)
        self.assertEqual(first.certificate.document, second.certificate.document)

        changed = replace(
            captured,
            model_info=replace(
                captured.model_info,
                local_name="changed captured source",
            ),
        )
        changed_plan = transaction._plan_structural_transaction(changed, request)
        self.assertNotEqual(first.plan_sha256, changed_plan.plan_sha256)

    def test_private_blocker_and_public_diagnostic_preserve_provenance(
        self,
    ) -> None:
        transaction = importlib.import_module(TRANSACTION_MODULE_NAME)
        document = _clean_document()
        request = PmxStructuralTransactionRequest(
            (
                PmxStructuralMaterialInsertion(
                    "missing reference",
                    texture_index=PmxStructuralNewReference(
                        "texture",
                        "missing.texture",
                    ),
                ),
            )
        )

        with self.assertRaises(PmxStructuralTransactionPreviewError) as private:
            transaction._plan_structural_transaction(document, request)
        self.assertEqual(private.exception.stage, "reference_resolution")
        self.assertEqual(private.exception.provenance, "transaction_plan")
        self.assertEqual(private.exception.operation_index, 0)
        self.assertEqual(private.exception.new_id, "missing.texture")
        self.assertEqual(
            private.exception.relationship_id,
            "material.texture",
        )

        with self.assertRaises(PmxServiceError) as public:
            preview_structural_transaction(document, request)
        error = public.exception
        details = _details(error)
        self.assertEqual(
            error.diagnostic.code,
            PmxServiceDiagnosticCode.STRUCTURAL_PREVIEW_FAILED,
        )
        self.assertEqual(
            error.diagnostic.operation,
            PmxServiceOperation.PREVIEW_STRUCTURAL_TRANSACTION,
        )
        self.assertEqual(details["stage"], private.exception.stage)
        self.assertEqual(details["provenance"], private.exception.provenance)
        self.assertEqual(details["operation_index"], 0)
        self.assertEqual(details["new_id"], "missing.texture")
        self.assertEqual(details["relationship_id"], "material.texture")
        self.assertFalse(details["source_bytes_read"])
        self.assertFalse(details["source_modified"])
        self.assertFalse(details["destination_published"])
        self.assertIsNone(error.__cause__)
        self.assertIsNone(error.__context__)
        self.assertTrue(error.__suppress_context__)

    def test_process_control_exceptions_escape_public_boundary(self) -> None:
        transaction = importlib.import_module(TRANSACTION_MODULE_NAME)
        document = _clean_document()
        request = PmxStructuralTransactionRequest()

        with patch.object(
            transaction,
            "_plan_structural_transaction",
            side_effect=KeyboardInterrupt(),
        ):
            with self.assertRaises(KeyboardInterrupt):
                preview_structural_transaction(document, request)

        with patch.object(
            transaction,
            "_plan_structural_transaction",
            side_effect=SystemExit(7),
        ):
            with self.assertRaises(SystemExit) as raised:
                preview_structural_transaction(document, request)
        self.assertEqual(raised.exception.code, 7)

    def test_public_contract_digest_and_lazy_import_boundary_stay_frozen(
        self,
    ) -> None:
        transaction = importlib.import_module(TRANSACTION_MODULE_NAME)
        self.assertEqual(transaction.__all__, PUBLIC_TRANSACTION_SURFACE)
        self.assertFalse(hasattr(transaction, "apply_structural_transaction"))
        self.assertFalse(hasattr(services, "apply_structural_transaction"))
        self.assertFalse(hasattr(mmd_registry, "apply_structural_transaction"))

        result = preview_structural_transaction(
            _clean_document(),
            PmxStructuralTransactionRequest(),
        )
        self.assertEqual(result.plan_sha256, NOOP_PLAN_SHA256)
        self.assertEqual(
            result.to_dict()["plan"]["schema"],
            "mmd_registry.structural_transaction.plan.v1",
        )

        script = "\n".join(
            (
                "import sys",
                "import mmd_registry.services.structural_transaction as transaction",
                "assert hasattr(transaction, '_plan_structural_transaction')",
                "assert 'mmd_registry.pmx.structural_output' not in sys.modules",
                "assert 'mmd_registry.cli' not in sys.modules",
                "assert 'argparse' not in sys.modules",
            )
        )
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        subprocess.check_call(
            (sys.executable, "-c", script),
            cwd=Path(__file__).resolve().parents[1],
            env=environment,
        )


if __name__ == "__main__":
    unittest.main()
