"""Freeze the CP19 transaction serialization and reparse certificate seam."""

from __future__ import annotations

import builtins
from dataclasses import fields, replace
import hashlib
import importlib
import inspect
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import mmd_registry
import mmd_registry.pmx as pmx
import mmd_registry.services as services
from mmd_registry.pmx.collection_transform import PmxStructuralTransformIntent
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.structural_invariants import (
    PmxStructuralInvariantCertificate,
)
from mmd_registry.pmx.structural_output import (
    PmxStructuralOutputVerificationError,
    verify_pmx_structural_serialization,
)
from mmd_registry.pmx.structural_transaction_preview import (
    PmxStructuralTransactionPreview,
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
    PmxStructuralTransactionRequest,
)
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


TRANSACTION_MODULE_NAME = "mmd_registry.services.structural_transaction"
OUTPUT_MODULE_NAME = "mmd_registry.pmx.structural_output"
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
                "serialized material",
                texture_index=PmxStructuralNewReference(
                    "texture",
                    "serialized.texture",
                ),
            ),
            PmxStructuralTextureInsertion(
                "textures/serialized.png",
                new_id="serialized.texture",
            ),
        )
    )


def _different_valid_document(document):
    return replace(
        document,
        model_info=replace(
            document.model_info,
            local_name=document.model_info.local_name + " CP19 mismatch",
        ),
    )


class V093StructuralTransactionSerializationTests(unittest.TestCase):
    def test_private_seam_is_typed_nonexported_and_lazy(self) -> None:
        script = f"""
import sys
import mmd_registry
import mmd_registry.pmx as pmx
import mmd_registry.services as services
import {TRANSACTION_MODULE_NAME} as transaction

assert {OUTPUT_MODULE_NAME!r} not in sys.modules
assert hasattr(transaction, '_serialize_structural_transaction')
assert '_serialize_structural_transaction' not in transaction.__all__
assert not hasattr(mmd_registry, '_serialize_structural_transaction')
assert not hasattr(pmx, '_serialize_structural_transaction')
assert not hasattr(services, '_serialize_structural_transaction')
assert hasattr(transaction, 'apply_structural_transaction')
"""
        environment = dict(__import__("os").environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=Path(__file__).resolve().parents[1],
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

        transaction = importlib.import_module(TRANSACTION_MODULE_NAME)
        serializer = transaction._serialize_structural_transaction
        self.assertEqual(
            tuple(inspect.signature(serializer).parameters),
            ("document", "request"),
        )
        self.assertEqual(
            inspect.signature(serializer).return_annotation,
            "_PmxStructuralTransactionSerializationResult",
        )

    def test_result_shape_is_private_immutable_and_bytes_are_hidden(self) -> None:
        output = importlib.import_module(OUTPUT_MODULE_NAME)
        result_type = output._PmxStructuralTransactionSerializationResult

        self.assertNotIn(result_type.__name__, output.__all__)
        self.assertFalse(hasattr(mmd_registry, result_type.__name__))
        self.assertFalse(hasattr(pmx, result_type.__name__))
        self.assertEqual(
            tuple((item.name, item.init, item.repr) for item in fields(result_type)),
            (
                ("preview", True, True),
                ("serialized_bytes", False, False),
                ("reparsed_certificate", False, True),
                ("output_sha256", False, True),
            ),
        )

    def test_service_plans_once_and_passes_the_exact_preview(self) -> None:
        transaction = importlib.import_module(TRANSACTION_MODULE_NAME)
        output = importlib.import_module(OUTPUT_MODULE_NAME)
        document = _clean_document()
        request = _forward_reference_request()
        planned = transaction._plan_structural_transaction(document, request)
        sentinel = object()

        with (
            patch.object(
                transaction,
                "_plan_structural_transaction",
                return_value=planned,
            ) as planner,
            patch.object(
                output,
                "_PmxStructuralTransactionSerializationResult",
                return_value=sentinel,
            ) as result_factory,
        ):
            result = transaction._serialize_structural_transaction(
                document,
                request,
            )

        self.assertIs(result, sentinel)
        planner.assert_called_once_with(document, request)
        result_factory.assert_called_once_with(planned)

    def test_exact_bytes_hash_and_fresh_reparse_certificate(self) -> None:
        transaction = importlib.import_module(TRANSACTION_MODULE_NAME)
        document = _clean_document()
        request = _forward_reference_request()

        with patch.object(
            builtins,
            "open",
            side_effect=AssertionError("CP19 must not access the filesystem"),
        ):
            result = transaction._serialize_structural_transaction(
                document,
                request,
            )

        self.assertIsInstance(result.preview, PmxStructuralTransactionPreview)
        self.assertEqual(
            result.serialized_bytes,
            serialize_pmx(result.preview.certificate.document),
        )
        self.assertEqual(
            result.output_sha256,
            hashlib.sha256(result.serialized_bytes).hexdigest(),
        )
        self.assertEqual(result.output_size_bytes, len(result.serialized_bytes))
        self.assertIsInstance(
            result.reparsed_certificate,
            PmxStructuralInvariantCertificate,
        )
        self.assertIsNot(
            result.reparsed_certificate,
            result.preview.certificate,
        )
        self.assertIsNot(
            result.reparsed_certificate.document,
            result.preview.certificate.document,
        )

    def test_reparse_consumes_the_exact_serialized_bytes(self) -> None:
        transaction = importlib.import_module(TRANSACTION_MODULE_NAME)
        output = importlib.import_module(OUTPUT_MODULE_NAME)
        real_load_pmx = output.load_pmx
        consumed: list[bytes] = []

        def capture_load(stream):
            consumed.append(stream.read())
            stream.seek(0)
            return real_load_pmx(stream)

        with patch.object(output, "load_pmx", side_effect=capture_load):
            result = transaction._serialize_structural_transaction(
                _clean_document(),
                _forward_reference_request(),
            )

        self.assertEqual(consumed, [result.serialized_bytes])

    def test_cp19_stops_before_semantic_compare_and_publication(self) -> None:
        transaction = importlib.import_module(TRANSACTION_MODULE_NAME)
        output = importlib.import_module(OUTPUT_MODULE_NAME)
        document = _clean_document()
        request = _forward_reference_request()
        planned = transaction._plan_structural_transaction(document, request)
        reparsed = _different_valid_document(planned.certificate.document)

        with (
            patch.object(
                transaction,
                "_plan_structural_transaction",
                return_value=planned,
            ),
            patch.object(output, "load_pmx", return_value=reparsed),
            patch.object(
                output._edit_output,
                "_commit_verified_bytes",
                side_effect=AssertionError("CP19 must not publish"),
            ) as publish,
        ):
            result = transaction._serialize_structural_transaction(
                document,
                request,
            )

        self.assertIs(result.reparsed_certificate.document, reparsed)
        self.assertNotEqual(reparsed, planned.certificate.document)
        publish.assert_not_called()

    def test_reparse_and_fresh_certification_fail_closed(self) -> None:
        transaction = importlib.import_module(TRANSACTION_MODULE_NAME)
        output = importlib.import_module(OUTPUT_MODULE_NAME)
        document = _clean_document()
        request = _forward_reference_request()
        planned = transaction._plan_structural_transaction(document, request)

        with (
            patch.object(
                transaction,
                "_plan_structural_transaction",
                return_value=planned,
            ),
            patch.object(output, "load_pmx", side_effect=ValueError("broken")),
        ):
            with self.assertRaisesRegex(
                PmxStructuralOutputVerificationError,
                "could not be reparsed",
            ):
                transaction._serialize_structural_transaction(document, request)

        with (
            patch.object(
                transaction,
                "_plan_structural_transaction",
                return_value=planned,
            ),
            patch.object(
                output,
                "PmxStructuralInvariantCertificate",
                side_effect=ValueError("uncertified"),
            ),
        ):
            with self.assertRaisesRegex(
                PmxStructuralOutputVerificationError,
                "failed complete invariant certification",
            ):
                transaction._serialize_structural_transaction(document, request)

    def test_process_control_exceptions_are_not_downgraded(self) -> None:
        transaction = importlib.import_module(TRANSACTION_MODULE_NAME)
        output = importlib.import_module(OUTPUT_MODULE_NAME)
        document = _clean_document()
        request = PmxStructuralTransactionRequest()
        planned = transaction._plan_structural_transaction(document, request)

        for exception in (KeyboardInterrupt(), SystemExit(7)):
            with (
                self.subTest(exception=type(exception).__name__),
                patch.object(
                    transaction,
                    "_plan_structural_transaction",
                    return_value=planned,
                ),
                patch.object(output, "load_pmx", side_effect=exception),
            ):
                with self.assertRaises(type(exception)):
                    transaction._serialize_structural_transaction(
                        document,
                        request,
                    )

    def test_legacy_serialization_retains_semantic_comparison(self) -> None:
        output = importlib.import_module(OUTPUT_MODULE_NAME)
        document = _clean_document()
        different = _different_valid_document(document)

        with patch.object(output, "load_pmx", return_value=different):
            with self.assertRaisesRegex(
                PmxStructuralOutputVerificationError,
                "does not match the intended certified document",
            ):
                verify_pmx_structural_serialization(
                    document,
                    PmxStructuralTransformIntent(),
                )

    def test_public_surface_and_plan_schema_remain_frozen(self) -> None:
        transaction = importlib.import_module(TRANSACTION_MODULE_NAME)
        public_before = tuple(transaction.__all__)
        plan = transaction._plan_structural_transaction(
            _clean_document(),
            PmxStructuralTransactionRequest(),
        )

        self.assertEqual(tuple(transaction.__all__), public_before)
        self.assertEqual(plan.plan_sha256, NOOP_PLAN_SHA256)
        self.assertEqual(
            tuple(plan.to_dict()),
            (
                "plan",
                "status",
                "dry_run",
                "operations",
                "effects",
                "references",
                "dependencies",
                "counts",
                "capacity",
                "output",
                "verification",
            ),
        )
        self.assertNotIn("serialized_bytes", plan.to_dict())
        self.assertNotIn("output_sha256", plan.to_dict())


if __name__ == "__main__":
    unittest.main()
