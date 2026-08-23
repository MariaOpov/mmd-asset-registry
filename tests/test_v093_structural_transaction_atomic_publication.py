"""Freeze CP21 atomic publication and failure cleanup for transactions."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import importlib
import inspect
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import mmd_registry
import mmd_registry.pmx as pmx
import mmd_registry.pmx.editing.output as edit_output
import mmd_registry.services as services
from mmd_registry.pmx.editing.errors import (
    PmxEditPathError,
    PmxEditVerificationError,
)
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.structural_output import (
    PmxStructuralOutputPathError,
    PmxStructuralOutputVerificationError,
    PmxStructuralWriteResult,
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
PUBLIC_TRANSACTION_SURFACE = (
    "PmxStructuralTransactionOperation",
    "PmxStructuralTransactionRequest",
    "PmxStructuralTransactionPreviewResult",
    "preview_structural_transaction",
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
                "published material",
                texture_index=PmxStructuralNewReference(
                    "texture",
                    "published.texture",
                ),
            ),
            PmxStructuralTextureInsertion(
                "textures/published.png",
                new_id="published.texture",
            ),
        )
    )


class V093StructuralTransactionAtomicPublicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source.pmx"
        self.source_bytes = serialize_pmx(_clean_document())
        self.source.write_bytes(self.source_bytes)
        self.request = _forward_reference_request()

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def _temporary_outputs(destination: Path) -> list[Path]:
        return list(destination.parent.glob(f".{destination.name}.*.tmp"))

    def _captured_document(self):
        return load_pmx(io.BytesIO(self.source_bytes))

    def test_private_writer_is_typed_nonexported_and_lazy(self) -> None:
        script = f"""
import inspect
import sys
import mmd_registry
import mmd_registry.pmx as pmx
import mmd_registry.services as services
import {TRANSACTION_MODULE_NAME} as transaction

assert {OUTPUT_MODULE_NAME!r} not in sys.modules
assert hasattr(transaction, '_write_structural_transaction')
assert '_write_structural_transaction' not in transaction.__all__
assert not hasattr(transaction, 'apply_structural_transaction')
assert not hasattr(mmd_registry, 'apply_structural_transaction')
assert not hasattr(pmx, 'apply_structural_transaction')
assert not hasattr(services, 'apply_structural_transaction')
signature = inspect.signature(transaction._write_structural_transaction)
assert tuple(signature.parameters) == (
    'input_path', 'output_path', 'request', 'overwrite'
)
assert signature.parameters['overwrite'].kind is inspect.Parameter.KEYWORD_ONLY
assert signature.parameters['overwrite'].default is False
assert signature.return_annotation == 'PmxStructuralWriteResult'
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

    def test_service_delegates_once_and_factory_returns_cp20_wrapper(self) -> None:
        transaction = importlib.import_module(TRANSACTION_MODULE_NAME)
        output = importlib.import_module(OUTPUT_MODULE_NAME)
        sentinel = object()

        with patch.object(
            output,
            "_write_verified_structural_transaction",
            return_value=sentinel,
        ) as writer:
            result = transaction._write_structural_transaction(
                "source.pmx",
                "output.pmx",
                self.request,
                overwrite=True,
            )

        self.assertIs(result, sentinel)
        writer.assert_called_once()
        call = writer.call_args
        self.assertEqual(call.args[:2], ("source.pmx", "output.pmx"))
        self.assertIs(call.kwargs["overwrite"], True)
        factory = call.args[2]
        verified = factory(self._captured_document(), None)
        self.assertIsInstance(
            verified,
            output._PmxVerifiedStructuralTransactionSerializationResult,
        )

    def test_invalid_request_and_overwrite_fail_before_path_resolution(self) -> None:
        transaction = importlib.import_module(TRANSACTION_MODULE_NAME)
        output = importlib.import_module(OUTPUT_MODULE_NAME)

        with patch.object(
            output._edit_output,
            "_resolve_edit_paths",
            side_effect=AssertionError("path resolution must not run"),
        ) as resolve:
            with self.assertRaisesRegex(TypeError, "request"):
                transaction._write_structural_transaction(
                    self.source,
                    self.root / "invalid-request.pmx",
                    object(),
                )
            with self.assertRaisesRegex(TypeError, "overwrite"):
                transaction._write_structural_transaction(
                    self.source,
                    self.root / "invalid-overwrite.pmx",
                    self.request,
                    overwrite=1,
                )

        resolve.assert_not_called()

    def test_cp19_unverified_result_cannot_reach_commit_kernel(self) -> None:
        transaction = importlib.import_module(TRANSACTION_MODULE_NAME)
        output = importlib.import_module(OUTPUT_MODULE_NAME)
        destination = self.root / "cp19-refused.pmx"
        unverified = transaction._serialize_structural_transaction(
            self._captured_document(),
            self.request,
        )

        with patch.object(
            output._edit_output,
            "_commit_verified_bytes",
            side_effect=AssertionError("CP19 must not publish"),
        ) as commit:
            with self.assertRaisesRegex(
                TypeError,
                "verified structural serialization",
            ):
                output._write_verified_structural_transaction(
                    self.source,
                    destination,
                    lambda _document, _stage_callback: unverified,
                )

        commit.assert_not_called()
        self.assertFalse(destination.exists())
        self.assertEqual(self.source.read_bytes(), self.source_bytes)
        self.assertEqual(self._temporary_outputs(destination), [])

    def test_success_publishes_exact_verified_bytes_and_complete_evidence(self) -> None:
        transaction = importlib.import_module(TRANSACTION_MODULE_NAME)
        output = importlib.import_module(OUTPUT_MODULE_NAME)
        destination = self.root / "verified-output.pmx"
        expected = transaction._verify_structural_transaction_serialization(
            self._captured_document(),
            self.request,
        )

        with patch.object(
            output._edit_output,
            "_commit_verified_bytes",
            wraps=output._edit_output._commit_verified_bytes,
        ) as commit:
            result = transaction._write_structural_transaction(
                self.source,
                destination,
                self.request,
            )

        commit.assert_called_once()
        self.assertIsInstance(result, PmxStructuralWriteResult)
        self.assertIsInstance(
            result.serialization,
            output._PmxVerifiedStructuralTransactionSerializationResult,
        )
        self.assertEqual(destination.read_bytes(), expected.serialized_bytes)
        self.assertEqual(result.output_sha256, expected.output_sha256)
        self.assertEqual(
            result.output_sha256,
            hashlib.sha256(destination.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            result.serialization.preview.plan_sha256,
            expected.preview.plan_sha256,
        )
        self.assertEqual(result.status, "written")
        report = result.to_dict()
        self.assertIs(report["output"]["written"], True)
        self.assertEqual(report["output"]["sha256"], result.output_sha256)
        self.assertEqual(
            report["plan"]["sha256"],
            expected.preview.plan_sha256,
        )
        self.assertIs(report["verification"]["input_unchanged"], True)
        self.assertEqual(self.source.read_bytes(), self.source_bytes)
        self.assertEqual(self._temporary_outputs(destination), [])

    def test_existing_destination_is_preserved_without_overwrite(self) -> None:
        transaction = importlib.import_module(TRANSACTION_MODULE_NAME)
        destination = self.root / "existing.pmx"
        old_bytes = b"pre-existing destination"
        destination.write_bytes(old_bytes)

        with patch.object(
            transaction,
            "_verify_structural_transaction_serialization",
            side_effect=AssertionError("serialization must not run"),
        ) as verify:
            with self.assertRaisesRegex(
                PmxStructuralOutputPathError,
                "already exists",
            ):
                transaction._write_structural_transaction(
                    self.source,
                    destination,
                    self.request,
                )

        verify.assert_not_called()
        self.assertEqual(destination.read_bytes(), old_bytes)
        self.assertEqual(self.source.read_bytes(), self.source_bytes)
        self.assertEqual(self._temporary_outputs(destination), [])

    def test_overwrite_preserves_old_bytes_until_single_atomic_replace(self) -> None:
        transaction = importlib.import_module(TRANSACTION_MODULE_NAME)
        destination = self.root / "overwrite.pmx"
        old_bytes = b"old destination"
        destination.write_bytes(old_bytes)
        original_replace = edit_output.os.replace
        observed_old_destination = False

        def inspect_then_replace(source, target, *args, **kwargs):
            nonlocal observed_old_destination
            self.assertEqual(Path(target).read_bytes(), old_bytes)
            observed_old_destination = True
            return original_replace(source, target, *args, **kwargs)

        with patch.object(
            edit_output.os,
            "replace",
            side_effect=inspect_then_replace,
        ) as replace_call:
            result = transaction._write_structural_transaction(
                self.source,
                destination,
                self.request,
                overwrite=True,
            )

        replace_call.assert_called_once()
        self.assertTrue(observed_old_destination)
        self.assertEqual(destination.read_bytes(), result.serialization.serialized_bytes)
        self.assertEqual(self.source.read_bytes(), self.source_bytes)
        self.assertEqual(self._temporary_outputs(destination), [])

    def test_no_clobber_publish_failure_leaves_no_output_or_success_result(self) -> None:
        transaction = importlib.import_module(TRANSACTION_MODULE_NAME)
        destination = self.root / "publish-failure.pmx"

        with (
            patch.object(
                edit_output,
                "_publish_no_clobber",
                side_effect=OSError("simulated publish failure"),
            ),
            patch.object(PmxStructuralWriteResult, "_from_committed") as committed,
        ):
            with self.assertRaisesRegex(OSError, "publish failure"):
                transaction._write_structural_transaction(
                    self.source,
                    destination,
                    self.request,
                )

        committed.assert_not_called()
        self.assertFalse(destination.exists())
        self.assertEqual(self.source.read_bytes(), self.source_bytes)
        self.assertEqual(self._temporary_outputs(destination), [])

    def test_replace_failure_preserves_destination_and_cleans_temporary(self) -> None:
        transaction = importlib.import_module(TRANSACTION_MODULE_NAME)
        destination = self.root / "replace-failure.pmx"
        old_bytes = b"destination must survive"
        destination.write_bytes(old_bytes)

        with (
            patch.object(
                edit_output.os,
                "replace",
                side_effect=OSError("simulated replace failure"),
            ),
            patch.object(PmxStructuralWriteResult, "_from_committed") as committed,
        ):
            with self.assertRaisesRegex(OSError, "replace failure"):
                transaction._write_structural_transaction(
                    self.source,
                    destination,
                    self.request,
                    overwrite=True,
                )

        committed.assert_not_called()
        self.assertEqual(destination.read_bytes(), old_bytes)
        self.assertEqual(self.source.read_bytes(), self.source_bytes)
        self.assertEqual(self._temporary_outputs(destination), [])

    def test_source_reverification_failure_prevents_publication(self) -> None:
        transaction = importlib.import_module(TRANSACTION_MODULE_NAME)
        destination = self.root / "source-race.pmx"

        with (
            patch.object(
                edit_output,
                "_verify_source_unchanged",
                side_effect=PmxEditVerificationError("simulated source race"),
            ),
            patch.object(edit_output, "_publish_no_clobber") as publish,
        ):
            with self.assertRaisesRegex(
                PmxStructuralOutputVerificationError,
                "source race",
            ):
                transaction._write_structural_transaction(
                    self.source,
                    destination,
                    self.request,
                )

        publish.assert_not_called()
        self.assertFalse(destination.exists())
        self.assertEqual(self.source.read_bytes(), self.source_bytes)
        self.assertEqual(self._temporary_outputs(destination), [])

    def test_destination_revalidation_failure_preserves_all_paths(self) -> None:
        transaction = importlib.import_module(TRANSACTION_MODULE_NAME)
        destination = self.root / "destination-race.pmx"
        original_validate = edit_output._validate_destination_state
        validate_calls = 0

        def fail_second_validation(
            source: Path,
            output: Path,
            *,
            overwrite: bool,
        ) -> None:
            nonlocal validate_calls
            validate_calls += 1
            if validate_calls == 2:
                raise PmxEditPathError("simulated destination race")
            return original_validate(source, output, overwrite=overwrite)

        with (
            patch.object(
                edit_output,
                "_validate_destination_state",
                side_effect=fail_second_validation,
            ),
            patch.object(edit_output, "_publish_no_clobber") as publish,
        ):
            with self.assertRaisesRegex(
                PmxStructuralOutputPathError,
                "destination race",
            ):
                transaction._write_structural_transaction(
                    self.source,
                    destination,
                    self.request,
                )

        self.assertEqual(validate_calls, 2)
        publish.assert_not_called()
        self.assertFalse(destination.exists())
        self.assertEqual(self.source.read_bytes(), self.source_bytes)
        self.assertEqual(self._temporary_outputs(destination), [])

    def test_fsync_failure_cleans_temporary_and_publishes_nothing(self) -> None:
        transaction = importlib.import_module(TRANSACTION_MODULE_NAME)
        destination = self.root / "fsync-failure.pmx"

        with (
            patch.object(
                edit_output.os,
                "fsync",
                side_effect=OSError("simulated fsync failure"),
            ),
            patch.object(edit_output, "_publish_no_clobber") as publish,
        ):
            with self.assertRaisesRegex(OSError, "fsync failure"):
                transaction._write_structural_transaction(
                    self.source,
                    destination,
                    self.request,
                )

        publish.assert_not_called()
        self.assertFalse(destination.exists())
        self.assertEqual(self.source.read_bytes(), self.source_bytes)
        self.assertEqual(self._temporary_outputs(destination), [])

    def test_success_result_is_constructed_only_after_publication(self) -> None:
        transaction = importlib.import_module(TRANSACTION_MODULE_NAME)
        destination = self.root / "result-after-publication.pmx"
        original_from_committed = PmxStructuralWriteResult._from_committed
        observed_destination = False

        def inspect_then_construct(**kwargs):
            nonlocal observed_destination
            output_path = kwargs["output_path"]
            self.assertTrue(output_path.is_file())
            self.assertEqual(
                output_path.read_bytes(),
                kwargs["serialization"].serialized_bytes,
            )
            observed_destination = True
            return original_from_committed(**kwargs)

        with patch.object(
            PmxStructuralWriteResult,
            "_from_committed",
            side_effect=inspect_then_construct,
        ):
            transaction._write_structural_transaction(
                self.source,
                destination,
                self.request,
            )

        self.assertTrue(observed_destination)
        self.assertEqual(self._temporary_outputs(destination), [])

    def test_public_surface_schema_and_legacy_kernel_remain_frozen(self) -> None:
        transaction = importlib.import_module(TRANSACTION_MODULE_NAME)
        output = importlib.import_module(OUTPUT_MODULE_NAME)

        self.assertEqual(transaction.__all__, PUBLIC_TRANSACTION_SURFACE)
        self.assertNotIn("_write_structural_transaction", transaction.__all__)
        self.assertFalse(hasattr(transaction, "apply_structural_transaction"))
        self.assertFalse(hasattr(services, "apply_structural_transaction"))
        self.assertFalse(hasattr(mmd_registry, "apply_structural_transaction"))
        self.assertFalse(hasattr(pmx, "apply_structural_transaction"))
        self.assertEqual(
            output.__all__,
            (
                "PMX_STRUCTURAL_PREVIEW_SCHEMA_VERSION",
                "PmxStructuralOutputPathError",
                "PmxStructuralOutputVerificationError",
                "PmxStructuralSerializationResult",
                "PmxStructuralWriteResult",
                "verify_pmx_structural_serialization",
                "write_pmx_structural_transform",
            ),
        )
        plan = transaction._plan_structural_transaction(
            self._captured_document(),
            PmxStructuralTransactionRequest(),
        )
        self.assertEqual(
            plan.to_dict()["plan"]["schema"],
            "mmd_registry.structural_transaction.plan.v1",
        )
        self.assertEqual(
            inspect.signature(transaction._verify_structural_transaction_serialization)
            .parameters.keys(),
            {"document": None, "request": None}.keys(),
        )


if __name__ == "__main__":
    unittest.main()
