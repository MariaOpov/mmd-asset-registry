"""Freeze the CP20 whole-document transaction semantic equality gate."""

from __future__ import annotations

import builtins
from dataclasses import FrozenInstanceError, fields, replace
import hashlib
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
from mmd_registry.pmx.collection_transform import PmxStructuralTransformIntent
from mmd_registry.pmx.document import PmxDocument
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.structural_invariants import (
    PmxStructuralInvariantCertificate,
)
from mmd_registry.pmx.structural_output import (
    PmxStructuralOutputVerificationError,
    verify_pmx_structural_serialization,
)
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
DOCUMENT_FIELDS = (
    "header",
    "model_info",
    "geometry",
    "texture_paths",
    "materials",
    "bones",
    "morphs",
    "display_frames",
    "rigid_bodies",
    "joints",
    "soft_bodies",
    "trailing_data",
)


def _clean_document() -> PmxDocument:
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
                "semantic material",
                texture_index=PmxStructuralNewReference(
                    "texture",
                    "semantic.texture",
                ),
            ),
            PmxStructuralTextureInsertion(
                "textures/semantic.png",
                new_id="semantic.texture",
            ),
        )
    )


def _different_valid_document(document: PmxDocument) -> PmxDocument:
    return replace(
        document,
        model_info=replace(
            document.model_info,
            local_comments=document.model_info.local_comments + " CP20 mismatch",
        ),
    )


class V093StructuralTransactionSemanticEqualityTests(unittest.TestCase):
    def test_private_verifier_is_typed_nonexported_and_lazy(self) -> None:
        script = f"""
import sys
import mmd_registry
import mmd_registry.pmx as pmx
import mmd_registry.services as services
import {TRANSACTION_MODULE_NAME} as transaction

assert {OUTPUT_MODULE_NAME!r} not in sys.modules
assert hasattr(transaction, '_verify_structural_transaction_serialization')
assert '_verify_structural_transaction_serialization' not in transaction.__all__
assert not hasattr(mmd_registry, '_verify_structural_transaction_serialization')
assert not hasattr(pmx, '_verify_structural_transaction_serialization')
assert not hasattr(services, '_verify_structural_transaction_serialization')
assert hasattr(transaction, 'apply_structural_transaction')
"""
        environment = dict(os.environ)
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
        verifier = transaction._verify_structural_transaction_serialization
        self.assertEqual(
            tuple(inspect.signature(verifier).parameters),
            ("document", "request"),
        )
        self.assertEqual(
            inspect.signature(verifier).return_annotation,
            "_PmxVerifiedStructuralTransactionSerializationResult",
        )

    def test_verifier_delegates_once_and_wraps_the_exact_cp19_result(self) -> None:
        transaction = importlib.import_module(TRANSACTION_MODULE_NAME)
        output = importlib.import_module(OUTPUT_MODULE_NAME)
        document = _clean_document()
        request = _forward_reference_request()
        serialization = object()
        verified = object()

        with (
            patch.object(
                transaction,
                "_serialize_structural_transaction",
                return_value=serialization,
            ) as serializer,
            patch.object(
                output,
                "_PmxVerifiedStructuralTransactionSerializationResult",
                return_value=verified,
            ) as result_factory,
        ):
            result = transaction._verify_structural_transaction_serialization(
                document,
                request,
            )

        self.assertIs(result, verified)
        serializer.assert_called_once_with(document, request)
        result_factory.assert_called_once_with(serialization)

    def test_verified_result_is_private_immutable_and_forwards_exact_evidence(
        self,
    ) -> None:
        transaction = importlib.import_module(TRANSACTION_MODULE_NAME)
        output = importlib.import_module(OUTPUT_MODULE_NAME)
        result_type = output._PmxVerifiedStructuralTransactionSerializationResult
        result = transaction._verify_structural_transaction_serialization(
            _clean_document(),
            _forward_reference_request(),
        )

        self.assertIsInstance(result, result_type)
        self.assertNotIn(result_type.__name__, output.__all__)
        self.assertEqual(
            tuple((item.name, item.init, item.repr) for item in fields(result_type)),
            (("serialization", True, False),),
        )
        self.assertIs(result.preview, result.serialization.preview)
        self.assertIs(result.serialized_bytes, result.serialization.serialized_bytes)
        self.assertIs(
            result.reparsed_certificate,
            result.serialization.reparsed_certificate,
        )
        self.assertEqual(result.output_sha256, result.serialization.output_sha256)
        self.assertEqual(
            result.output_size_bytes,
            result.serialization.output_size_bytes,
        )
        self.assertNotIn(repr(result.serialized_bytes), repr(result))
        with self.assertRaises(FrozenInstanceError):
            result.serialization = object()  # type: ignore[misc]

    def test_success_proves_complete_document_equality_and_exact_hash(self) -> None:
        transaction = importlib.import_module(TRANSACTION_MODULE_NAME)
        result = transaction._verify_structural_transaction_serialization(
            _clean_document(),
            _forward_reference_request(),
        )

        self.assertEqual(tuple(item.name for item in fields(PmxDocument)), DOCUMENT_FIELDS)
        self.assertEqual(
            result.reparsed_certificate.document,
            result.preview.certificate.document,
        )
        self.assertEqual(
            result.output_sha256,
            hashlib.sha256(result.serialized_bytes).hexdigest(),
        )

    def test_cp19_result_precedes_cp20_and_mismatch_fails_only_at_cp20(self) -> None:
        transaction = importlib.import_module(TRANSACTION_MODULE_NAME)
        output = importlib.import_module(OUTPUT_MODULE_NAME)
        document = _clean_document()
        request = _forward_reference_request()
        planned = transaction._plan_structural_transaction(document, request)
        different = _different_valid_document(planned.certificate.document)

        with (
            patch.object(
                transaction,
                "_plan_structural_transaction",
                return_value=planned,
            ),
            patch.object(output, "load_pmx", return_value=different),
        ):
            serialization = transaction._serialize_structural_transaction(
                document,
                request,
            )

        self.assertIs(serialization.reparsed_certificate.document, different)
        self.assertNotEqual(
            serialization.reparsed_certificate.document,
            serialization.preview.certificate.document,
        )
        with self.assertRaisesRegex(
            PmxStructuralOutputVerificationError,
            "does not match the intended certified document",
        ):
            output._PmxVerifiedStructuralTransactionSerializationResult(
                serialization
            )

    def test_transaction_mismatch_fails_closed_without_publication(self) -> None:
        transaction = importlib.import_module(TRANSACTION_MODULE_NAME)
        output = importlib.import_module(OUTPUT_MODULE_NAME)
        document = _clean_document()
        request = _forward_reference_request()
        planned = transaction._plan_structural_transaction(document, request)
        different = _different_valid_document(planned.certificate.document)

        with (
            patch.object(
                transaction,
                "_plan_structural_transaction",
                return_value=planned,
            ),
            patch.object(output, "load_pmx", return_value=different),
            patch.object(
                output._edit_output,
                "_commit_verified_bytes",
                side_effect=AssertionError("CP20 must not publish"),
            ) as publish,
        ):
            with self.assertRaisesRegex(
                PmxStructuralOutputVerificationError,
                "does not match the intended certified document",
            ):
                transaction._verify_structural_transaction_serialization(
                    document,
                    request,
                )

        publish.assert_not_called()

    def test_canonical_equality_authority_requires_two_fresh_certificates(
        self,
    ) -> None:
        output = importlib.import_module(OUTPUT_MODULE_NAME)
        certificate = PmxStructuralInvariantCertificate(_clean_document())

        with self.assertRaisesRegex(TypeError, "intended_certificate"):
            output._require_canonical_structural_document_equality(
                object(),
                certificate,
            )
        with self.assertRaisesRegex(TypeError, "reparsed_certificate"):
            output._require_canonical_structural_document_equality(
                certificate,
                object(),
            )

    def test_transaction_and_legacy_paths_share_one_equality_authority(self) -> None:
        transaction = importlib.import_module(TRANSACTION_MODULE_NAME)
        output = importlib.import_module(OUTPUT_MODULE_NAME)
        authority = output._require_canonical_structural_document_equality

        with patch.object(output, authority.__name__, wraps=authority) as shared:
            transaction._verify_structural_transaction_serialization(
                _clean_document(),
                PmxStructuralTransactionRequest(),
            )
        shared.assert_called_once()

        with patch.object(output, authority.__name__, wraps=authority) as shared:
            verify_pmx_structural_serialization(
                _clean_document(),
                PmxStructuralTransformIntent(),
            )
        shared.assert_called_once()

    def test_success_has_no_filesystem_or_publication_authority(self) -> None:
        transaction = importlib.import_module(TRANSACTION_MODULE_NAME)
        output = importlib.import_module(OUTPUT_MODULE_NAME)
        document = _clean_document()
        request = _forward_reference_request()

        with (
            patch.object(
                builtins,
                "open",
                side_effect=AssertionError("CP20 must not access files"),
            ),
            patch.object(
                output._edit_output,
                "_commit_verified_bytes",
                side_effect=AssertionError("CP20 must not publish"),
            ) as publish,
        ):
            transaction._verify_structural_transaction_serialization(
                document,
                request,
            )

        publish.assert_not_called()

    def test_public_surface_plan_schema_and_digest_remain_frozen(self) -> None:
        transaction = importlib.import_module(TRANSACTION_MODULE_NAME)
        public_surface = (
            "PmxStructuralTransactionOperation",
            "PmxStructuralTransactionRequest",
            "PmxStructuralTransactionPreviewResult",
            "preview_structural_transaction",
            "apply_structural_transaction",
        )
        plan = transaction._plan_structural_transaction(
            _clean_document(),
            PmxStructuralTransactionRequest(),
        )

        self.assertEqual(transaction.__all__, public_surface)
        self.assertTrue(hasattr(transaction, "apply_structural_transaction"))
        self.assertFalse(hasattr(services, "apply_structural_transaction"))
        self.assertFalse(hasattr(mmd_registry, "apply_structural_transaction"))
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


if __name__ == "__main__":
    unittest.main()
