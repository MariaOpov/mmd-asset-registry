"""v0.9.5.8 confirmed Smart Material apply integration — incremental TDD gates."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import importlib
import io
import inspect
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import mmd_registry
import mmd_registry.cli as cli
import mmd_registry.services as services
import mmd_registry.services._smart_material_draft as smart_material_draft
import mmd_registry.pmx.editing.output as edit_output
from mmd_registry.pmx import (
    load_pmx,
    serialize_pmx,
    validate_pmx_document,
)
from mmd_registry.diagnostics import (
    PmxServiceDiagnostic,
    PmxServiceDiagnosticCode,
    PmxServiceError,
    PmxServiceOperation,
)
from mmd_registry.pmx.editing import (
    PMX_EDIT_PREVIEW_SCHEMA_VERSION,
    calculate_pmx_edit_plan_sha256,
)
from mmd_registry.smart_parts import SmartPartKind
from tests.test_v0956_smart_material_draft import build_source_bytes


MODULE_NAME = "mmd_registry.services._smart_material_apply"
ENTRY_NAME = "apply_smart_material_color_draft"
ERROR_NAME = "SmartMaterialApplyError"
CONFIRMATION_NAME = "SmartMaterialApplyConfirmation"

EXPECTED_RED_MARKER = "EXPECTED_CP06_RED_MISSING_SMART_MATERIAL_APPLY_INTEGRATION"
EXPECTED_CONFIRMATION_RED_MARKER = "EXPECTED_CP06_RED_MISSING_CONFIRMATION_CONTRACT"
EXPECTED_TYPED_CONFIRMATION_RED_MARKER = (
    "EXPECTED_CP06_RED_MISSING_TYPED_CONFIRMATION"
)
EXPECTED_IDENTITY_RED_MARKER = (
    "EXPECTED_CP06_RED_MISSING_CONFIRMATION_IDENTITY_BINDING"
)
EXPECTED_SOURCE_DRIFT_RED_MARKER = (
    "EXPECTED_CP06_RED_MISSING_SOURCE_EVIDENCE_BINDING"
)
EXPECTED_PREVIEW_REPLAY_RED_MARKER = (
    "EXPECTED_CP06_RED_MISSING_PREVIEW_REPLAY_PARITY"
)
EXPECTED_APPLY_DELEGATION_RED_MARKER = (
    "EXPECTED_CP06_RED_MISSING_EXACT_APPLY_DELEGATION"
)
EXPECTED_APPLY_RESULT_PARITY_RED_MARKER = (
    "EXPECTED_CP06_RED_MISSING_APPLY_RESULT_PREVIEW_PARITY"
)
EXPECTED_POST_WRITE_HASH_RED_MARKER = (
    "EXPECTED_CP06_RED_MISSING_POST_WRITE_HASH_CERTIFICATION"
)
EXPECTED_POST_WRITE_REPARSE_RED_MARKER = (
    "EXPECTED_CP06_RED_MISSING_POST_WRITE_REPARSE_CERTIFICATION"
)
EXPECTED_POST_WRITE_SEMANTIC_RED_MARKER = (
    "EXPECTED_CP06_RED_MISSING_POST_WRITE_SEMANTIC_EQUALITY"
)
EXPECTED_POST_WRITE_VALIDATION_RED_MARKER = (
    "EXPECTED_CP06_RED_MISSING_POST_WRITE_VALIDATION_CERTIFICATION"
)
EXPECTED_POST_WRITE_SOURCE_RECHECK_RED_MARKER = (
    "EXPECTED_CP06_RED_MISSING_POST_WRITE_SOURCE_RECHECK"
)
EXPECTED_CP07_EXACT_CONFIRMATION_TYPE_RED_MARKER = (
    "EXPECTED_CP07_RED_MISSING_EXACT_CONFIRMATION_TYPE_GATE"
)
EXPECTED_CP08_PREVIEW_PLAN_IDENTITY_RED_MARKER = (
    "EXPECTED_CP08_RED_MISSING_PREVIEW_PLAN_IDENTITY_GATE"
)
EXPECTED_CP08_PREVIEW_PLAN_SCHEMA_RED_MARKER = (
    "EXPECTED_CP08_RED_MISSING_PREVIEW_PLAN_SCHEMA_GATE"
)
EXPECTED_CP08_PREVIEW_OPERATION_COUNT_RED_MARKER = (
    "EXPECTED_CP08_RED_MISSING_PREVIEW_OPERATION_COUNT_GATE"
)


def _load_apply_module() -> object:
    try:
        return importlib.import_module(MODULE_NAME)
    except ModuleNotFoundError as error:
        if error.name == MODULE_NAME:
            raise AssertionError(EXPECTED_RED_MARKER) from None
        raise


def _load_apply_entry() -> object:
    module = _load_apply_module()
    entry = getattr(module, ENTRY_NAME, None)
    if not callable(entry):
        raise AssertionError(EXPECTED_RED_MARKER + "_ENTRY")
    return entry


def _load_apply_error_type() -> type[BaseException]:
    module = _load_apply_module()
    error_type = getattr(module, ERROR_NAME, None)
    if (
        not isinstance(error_type, type)
        or not issubclass(error_type, BaseException)
    ):
        raise AssertionError(EXPECTED_CONFIRMATION_RED_MARKER)
    return error_type


def _load_confirmation_type() -> type[object]:
    module = _load_apply_module()
    confirmation_type = getattr(module, CONFIRMATION_NAME, None)
    if not isinstance(confirmation_type, type):
        raise AssertionError(EXPECTED_TYPED_CONFIRMATION_RED_MARKER)
    return confirmation_type


def _draft(source_bytes: bytes):
    return smart_material_draft.build_smart_material_color_draft(
        source_bytes,
        SmartPartKind.EYES,
        "red",
    )


def _confirmation(confirmation_type: type[object], preview: object, draft: object):
    return confirmation_type(
        preview_schema_version=PMX_EDIT_PREVIEW_SCHEMA_VERSION,
        source_sha256=preview.source_sha256,
        plan_sha256=calculate_pmx_edit_plan_sha256(draft),
    )


class SmartMaterialApplyIntegrationTests(unittest.TestCase):
    def test_private_apply_integration_boundary_exists(self) -> None:
        entry = _load_apply_entry()
        self.assertTrue(callable(entry))

    def test_missing_confirmation_fails_closed_before_apply(self) -> None:
        entry = _load_apply_entry()
        error_type = _load_apply_error_type()

        with self.assertRaises(error_type) as raised:
            entry(
                "source.pmx",
                "destination.pmx",
                object(),
                object(),
                confirmation=None,
            )

        self.assertEqual(
            getattr(raised.exception, "reason", None),
            "confirmation_required",
        )

    def test_confirmation_is_exact_frozen_typed_identity(self) -> None:
        confirmation_type = _load_confirmation_type()

        self.assertTrue(dataclasses.is_dataclass(confirmation_type))
        self.assertEqual(
            tuple(field.name for field in dataclasses.fields(confirmation_type)),
            (
                "preview_schema_version",
                "source_sha256",
                "plan_sha256",
            ),
        )

        confirmation = confirmation_type(
            preview_schema_version=1,
            source_sha256="a" * 64,
            plan_sha256="b" * 64,
        )

        self.assertEqual(confirmation.preview_schema_version, 1)
        self.assertEqual(confirmation.source_sha256, "a" * 64)
        self.assertEqual(confirmation.plan_sha256, "b" * 64)

        with self.assertRaises(dataclasses.FrozenInstanceError):
            confirmation.plan_sha256 = "c" * 64

    def test_confirmation_identity_mismatch_fails_before_apply(self) -> None:
        entry = _load_apply_entry()
        error_type = _load_apply_error_type()
        confirmation_type = _load_confirmation_type()

        source_bytes = build_source_bytes()
        draft = _draft(source_bytes)
        preview = services.preview_edit(source_bytes, draft)

        valid_values = {
            "preview_schema_version": PMX_EDIT_PREVIEW_SCHEMA_VERSION,
            "source_sha256": preview.source_sha256,
            "plan_sha256": calculate_pmx_edit_plan_sha256(draft),
        }

        mismatches = (
            (
                "preview_schema_version",
                PMX_EDIT_PREVIEW_SCHEMA_VERSION + 1,
            ),
            ("source_sha256", "0" * 64),
            ("plan_sha256", "f" * 64),
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.pmx"
            destination_path = root / "destination.pmx"
            source_path.write_bytes(source_bytes)

            for field_name, wrong_value in mismatches:
                with self.subTest(field=field_name):
                    values = dict(valid_values)
                    values[field_name] = wrong_value
                    confirmation = confirmation_type(**values)

                    with patch.object(
                        services,
                        "apply_edit",
                        side_effect=AssertionError(
                            "apply_edit must not run on confirmation mismatch"
                        ),
                    ) as apply_mock:
                        try:
                            entry(
                                source_path,
                                destination_path,
                                draft,
                                preview,
                                confirmation=confirmation,
                            )
                        except error_type as error:
                            self.assertEqual(
                                getattr(error, "reason", None),
                                "confirmation_mismatch",
                            )
                        except Exception:
                            raise AssertionError(
                                EXPECTED_IDENTITY_RED_MARKER
                            ) from None
                        else:
                            raise AssertionError(
                                EXPECTED_IDENTITY_RED_MARKER
                            )

                    apply_mock.assert_not_called()
                    self.assertFalse(destination_path.exists())

    def test_source_drift_fails_before_preview_replay_or_apply(self) -> None:
        entry = _load_apply_entry()
        error_type = _load_apply_error_type()
        confirmation_type = _load_confirmation_type()

        source_a = build_source_bytes()
        source_b = build_source_bytes(eye_rgb=(0.21, 0.31, 0.41))
        draft = _draft(source_a)
        preview = services.preview_edit(source_a, draft)
        confirmation = _confirmation(confirmation_type, preview, draft)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.pmx"
            destination_path = root / "destination.pmx"
            source_path.write_bytes(source_a)
            source_path.write_bytes(source_b)

            with (
                patch.object(
                    services,
                    "preview_edit",
                    side_effect=AssertionError(
                        "preview_edit must not run after source drift"
                    ),
                ) as preview_mock,
                patch.object(
                    services,
                    "apply_edit",
                    side_effect=AssertionError(
                        "apply_edit must not run after source drift"
                    ),
                ) as apply_mock,
            ):
                try:
                    entry(
                        source_path,
                        destination_path,
                        draft,
                        preview,
                        confirmation=confirmation,
                    )
                except error_type as error:
                    self.assertEqual(
                        getattr(error, "reason", None),
                        "source_evidence_mismatch",
                    )
                except Exception:
                    raise AssertionError(
                        EXPECTED_SOURCE_DRIFT_RED_MARKER
                    ) from None
                else:
                    raise AssertionError(
                        EXPECTED_SOURCE_DRIFT_RED_MARKER
                    )

            preview_mock.assert_not_called()
            apply_mock.assert_not_called()
            self.assertFalse(destination_path.exists())
            self.assertEqual(source_path.read_bytes(), source_b)

    def test_preview_replay_mismatch_fails_before_apply(self) -> None:
        entry = _load_apply_entry()
        error_type = _load_apply_error_type()
        confirmation_type = _load_confirmation_type()

        source_bytes = build_source_bytes()
        draft = _draft(source_bytes)
        approved_preview = services.preview_edit(source_bytes, draft)
        confirmation = _confirmation(
            confirmation_type,
            approved_preview,
            draft,
        )
        replay_mismatch = dataclasses.replace(
            approved_preview,
            plan_sha256="f" * 64,
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.pmx"
            destination_path = root / "destination.pmx"
            source_path.write_bytes(source_bytes)

            with (
                patch.object(
                    services,
                    "preview_edit",
                    return_value=replay_mismatch,
                ) as preview_mock,
                patch.object(
                    services,
                    "apply_edit",
                    side_effect=AssertionError(
                        "apply_edit must not run after preview replay mismatch"
                    ),
                ) as apply_mock,
            ):
                try:
                    entry(
                        source_path,
                        destination_path,
                        draft,
                        approved_preview,
                        confirmation=confirmation,
                    )
                except error_type as error:
                    self.assertEqual(
                        getattr(error, "reason", None),
                        "preview_apply_mismatch",
                    )
                except Exception:
                    raise AssertionError(
                        EXPECTED_PREVIEW_REPLAY_RED_MARKER
                    ) from None
                else:
                    raise AssertionError(
                        EXPECTED_PREVIEW_REPLAY_RED_MARKER
                    )

            preview_mock.assert_called_once_with(source_bytes, draft)
            apply_mock.assert_not_called()
            self.assertFalse(destination_path.exists())
            self.assertEqual(source_path.read_bytes(), source_bytes)

    def test_exact_apply_delegation_uses_existing_authority_once(self) -> None:
        entry = _load_apply_entry()
        confirmation_type = _load_confirmation_type()

        source_bytes = build_source_bytes()
        draft = _draft(source_bytes)
        approved_preview = services.preview_edit(source_bytes, draft)
        confirmation = _confirmation(
            confirmation_type,
            approved_preview,
            draft,
        )
        published_bytes = serialize_pmx(approved_preview.document)
        sentinel_result = SimpleNamespace(
            preview=approved_preview,
            output_sha256=hashlib.sha256(published_bytes).hexdigest(),
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.pmx"
            destination_path = root / "destination.pmx"
            source_path.write_bytes(source_bytes)

            def delegated_apply(*args: object, **kwargs: object):
                destination_path.write_bytes(published_bytes)
                return sentinel_result

            with (
                patch.object(
                    services,
                    "preview_edit",
                    return_value=approved_preview,
                ) as preview_mock,
                patch.object(
                    services,
                    "apply_edit",
                    side_effect=delegated_apply,
                ) as apply_mock,
            ):
                try:
                    result = entry(
                        source_path,
                        destination_path,
                        draft,
                        approved_preview,
                        confirmation=confirmation,
                    )
                except Exception:
                    raise AssertionError(
                        EXPECTED_APPLY_DELEGATION_RED_MARKER
                    ) from None

            preview_mock.assert_called_once_with(source_bytes, draft)
            apply_mock.assert_called_once_with(
                source_path,
                destination_path,
                draft,
                overwrite=False,
            )
            self.assertIs(result, sentinel_result)
            self.assertEqual(result.preview, approved_preview)
            self.assertEqual(source_path.read_bytes(), source_bytes)


    def test_apply_result_preview_mismatch_fails_closed(self) -> None:
        entry = _load_apply_entry()
        error_type = _load_apply_error_type()
        confirmation_type = _load_confirmation_type()

        source_bytes = build_source_bytes()
        draft = _draft(source_bytes)
        approved_preview = services.preview_edit(source_bytes, draft)
        confirmation = _confirmation(
            confirmation_type,
            approved_preview,
            draft,
        )
        mismatched_preview = dataclasses.replace(
            approved_preview,
            plan_sha256="f" * 64,
        )
        mismatched_result = SimpleNamespace(preview=mismatched_preview)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.pmx"
            destination_path = root / "destination.pmx"
            source_path.write_bytes(source_bytes)

            with (
                patch.object(
                    services,
                    "preview_edit",
                    return_value=approved_preview,
                ) as preview_mock,
                patch.object(
                    services,
                    "apply_edit",
                    return_value=mismatched_result,
                ) as apply_mock,
            ):
                try:
                    entry(
                        source_path,
                        destination_path,
                        draft,
                        approved_preview,
                        confirmation=confirmation,
                    )
                except error_type as error:
                    self.assertEqual(
                        getattr(error, "reason", None),
                        "preview_apply_mismatch",
                    )
                except Exception:
                    raise AssertionError(
                        EXPECTED_APPLY_RESULT_PARITY_RED_MARKER
                    ) from None
                else:
                    raise AssertionError(
                        EXPECTED_APPLY_RESULT_PARITY_RED_MARKER
                    )

            preview_mock.assert_called_once_with(source_bytes, draft)
            apply_mock.assert_called_once_with(
                source_path,
                destination_path,
                draft,
                overwrite=False,
            )
            self.assertEqual(source_path.read_bytes(), source_bytes)


    def test_post_write_destination_hash_mismatch_fails_certification(self) -> None:
        entry = _load_apply_entry()
        error_type = _load_apply_error_type()
        confirmation_type = _load_confirmation_type()

        source_bytes = build_source_bytes()
        draft = _draft(source_bytes)
        approved_preview = services.preview_edit(source_bytes, draft)
        confirmation = _confirmation(
            confirmation_type,
            approved_preview,
            draft,
        )

        claimed_output_bytes = b"claimed verified publication bytes"
        actual_destination_bytes = b"tampered published destination bytes"
        claimed_output_sha256 = hashlib.sha256(
            claimed_output_bytes
        ).hexdigest()
        sentinel_result = SimpleNamespace(
            preview=approved_preview,
            output_sha256=claimed_output_sha256,
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.pmx"
            destination_path = root / "destination.pmx"
            source_path.write_bytes(source_bytes)

            def apply_then_leave_hash_mismatch(*args: object, **kwargs: object):
                destination_path.write_bytes(actual_destination_bytes)
                return sentinel_result

            with (
                patch.object(
                    services,
                    "preview_edit",
                    return_value=approved_preview,
                ) as preview_mock,
                patch.object(
                    services,
                    "apply_edit",
                    side_effect=apply_then_leave_hash_mismatch,
                ) as apply_mock,
            ):
                try:
                    entry(
                        source_path,
                        destination_path,
                        draft,
                        approved_preview,
                        confirmation=confirmation,
                    )
                except error_type as error:
                    self.assertEqual(
                        getattr(error, "reason", None),
                        "post_write_certification_failed",
                    )
                except Exception:
                    raise AssertionError(
                        EXPECTED_POST_WRITE_HASH_RED_MARKER
                    ) from None
                else:
                    raise AssertionError(
                        EXPECTED_POST_WRITE_HASH_RED_MARKER
                    )

            preview_mock.assert_called_once_with(source_bytes, draft)
            apply_mock.assert_called_once_with(
                source_path,
                destination_path,
                draft,
                overwrite=False,
            )
            self.assertTrue(destination_path.exists())
            self.assertEqual(
                destination_path.read_bytes(),
                actual_destination_bytes,
            )
            self.assertEqual(source_path.read_bytes(), source_bytes)


    def test_post_write_reparse_failure_fails_certification(self) -> None:
        apply_module = _load_apply_module()
        entry = _load_apply_entry()
        error_type = _load_apply_error_type()
        confirmation_type = _load_confirmation_type()

        source_bytes = build_source_bytes()
        draft = _draft(source_bytes)
        approved_preview = services.preview_edit(source_bytes, draft)
        confirmation = _confirmation(
            confirmation_type,
            approved_preview,
            draft,
        )

        published_bytes = b"published bytes with a certified matching hash"
        sentinel_result = SimpleNamespace(
            preview=approved_preview,
            output_sha256=hashlib.sha256(published_bytes).hexdigest(),
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.pmx"
            destination_path = root / "destination.pmx"
            source_path.write_bytes(source_bytes)

            def delegated_apply(*args: object, **kwargs: object):
                destination_path.write_bytes(published_bytes)
                return sentinel_result

            reparsed_inputs: list[bytes] = []

            def fail_reparse(source: object):
                reparsed_inputs.append(source.read())
                raise ValueError("synthetic destination reparse failure")

            with (
                patch.object(
                    services,
                    "preview_edit",
                    return_value=approved_preview,
                ) as preview_mock,
                patch.object(
                    services,
                    "apply_edit",
                    side_effect=delegated_apply,
                ) as apply_mock,
                patch.object(
                    apply_module,
                    "load_pmx",
                    side_effect=fail_reparse,
                    create=True,
                ) as load_mock,
            ):
                try:
                    entry(
                        source_path,
                        destination_path,
                        draft,
                        approved_preview,
                        confirmation=confirmation,
                    )
                except error_type as error:
                    self.assertEqual(
                        getattr(error, "reason", None),
                        "post_write_certification_failed",
                    )
                except Exception:
                    raise AssertionError(
                        EXPECTED_POST_WRITE_REPARSE_RED_MARKER
                    ) from None
                else:
                    raise AssertionError(
                        EXPECTED_POST_WRITE_REPARSE_RED_MARKER
                    )

            preview_mock.assert_called_once_with(source_bytes, draft)
            apply_mock.assert_called_once_with(
                source_path,
                destination_path,
                draft,
                overwrite=False,
            )
            load_mock.assert_called_once()
            self.assertEqual(reparsed_inputs, [published_bytes])
            self.assertTrue(destination_path.exists())
            self.assertEqual(destination_path.read_bytes(), published_bytes)
            self.assertEqual(source_path.read_bytes(), source_bytes)



    def test_post_write_reparsed_document_mismatch_fails_certification(self) -> None:
        apply_module = _load_apply_module()
        entry = _load_apply_entry()
        error_type = _load_apply_error_type()
        confirmation_type = _load_confirmation_type()

        source_bytes = build_source_bytes()
        draft = _draft(source_bytes)
        approved_preview = services.preview_edit(source_bytes, draft)
        confirmation = _confirmation(
            confirmation_type,
            approved_preview,
            draft,
        )

        published_bytes = serialize_pmx(approved_preview.document)
        sentinel_result = SimpleNamespace(
            preview=approved_preview,
            output_sha256=hashlib.sha256(published_bytes).hexdigest(),
        )

        mismatch_document = load_pmx(io.BytesIO(source_bytes))
        self.assertNotEqual(mismatch_document, approved_preview.document)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.pmx"
            destination_path = root / "destination.pmx"
            source_path.write_bytes(source_bytes)

            def delegated_apply(*args: object, **kwargs: object):
                destination_path.write_bytes(published_bytes)
                return sentinel_result

            reparsed_inputs: list[bytes] = []

            def return_mismatched_document(source: object):
                reparsed_inputs.append(source.read())
                return mismatch_document

            with (
                patch.object(
                    services,
                    "preview_edit",
                    return_value=approved_preview,
                ) as preview_mock,
                patch.object(
                    services,
                    "apply_edit",
                    side_effect=delegated_apply,
                ) as apply_mock,
                patch.object(
                    apply_module,
                    "load_pmx",
                    side_effect=return_mismatched_document,
                ) as load_mock,
            ):
                try:
                    entry(
                        source_path,
                        destination_path,
                        draft,
                        approved_preview,
                        confirmation=confirmation,
                    )
                except error_type as error:
                    self.assertEqual(
                        getattr(error, "reason", None),
                        "post_write_certification_failed",
                    )
                except Exception:
                    raise AssertionError(
                        EXPECTED_POST_WRITE_SEMANTIC_RED_MARKER
                    ) from None
                else:
                    raise AssertionError(
                        EXPECTED_POST_WRITE_SEMANTIC_RED_MARKER
                    )

            preview_mock.assert_called_once_with(source_bytes, draft)
            apply_mock.assert_called_once_with(
                source_path,
                destination_path,
                draft,
                overwrite=False,
            )
            load_mock.assert_called_once()
            self.assertEqual(reparsed_inputs, [published_bytes])
            self.assertTrue(destination_path.exists())
            self.assertEqual(destination_path.read_bytes(), published_bytes)
            self.assertEqual(source_path.read_bytes(), source_bytes)



    def test_post_write_validation_failure_fails_certification(self) -> None:
        apply_module = _load_apply_module()
        entry = _load_apply_entry()
        error_type = _load_apply_error_type()
        confirmation_type = _load_confirmation_type()

        source_bytes = build_source_bytes()
        draft = _draft(source_bytes)
        approved_preview = services.preview_edit(source_bytes, draft)
        confirmation = _confirmation(
            confirmation_type,
            approved_preview,
            draft,
        )

        published_bytes = serialize_pmx(approved_preview.document)
        sentinel_result = SimpleNamespace(
            preview=approved_preview,
            output_sha256=hashlib.sha256(published_bytes).hexdigest(),
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.pmx"
            destination_path = root / "destination.pmx"
            source_path.write_bytes(source_bytes)

            def delegated_apply(*args: object, **kwargs: object):
                destination_path.write_bytes(published_bytes)
                return sentinel_result

            reparsed_inputs: list[bytes] = []

            def return_approved_document(source: object):
                reparsed_inputs.append(source.read())
                return approved_preview.document

            with (
                patch.object(
                    services,
                    "preview_edit",
                    return_value=approved_preview,
                ) as preview_mock,
                patch.object(
                    services,
                    "apply_edit",
                    side_effect=delegated_apply,
                ) as apply_mock,
                patch.object(
                    apply_module,
                    "load_pmx",
                    side_effect=return_approved_document,
                ) as load_mock,
                patch.object(
                    apply_module,
                    "validate_pmx_document",
                    side_effect=ValueError(
                        "synthetic post-write validation failure"
                    ),
                    create=True,
                ) as validate_mock,
            ):
                try:
                    entry(
                        source_path,
                        destination_path,
                        draft,
                        approved_preview,
                        confirmation=confirmation,
                    )
                except error_type as error:
                    self.assertEqual(
                        getattr(error, "reason", None),
                        "post_write_certification_failed",
                    )
                except Exception:
                    raise AssertionError(
                        EXPECTED_POST_WRITE_VALIDATION_RED_MARKER
                    ) from None
                else:
                    raise AssertionError(
                        EXPECTED_POST_WRITE_VALIDATION_RED_MARKER
                    )

            preview_mock.assert_called_once_with(source_bytes, draft)
            apply_mock.assert_called_once_with(
                source_path,
                destination_path,
                draft,
                overwrite=False,
            )
            load_mock.assert_called_once()
            self.assertEqual(reparsed_inputs, [published_bytes])
            validate_mock.assert_called_once_with(approved_preview.document)
            self.assertTrue(destination_path.exists())
            self.assertEqual(destination_path.read_bytes(), published_bytes)
            self.assertEqual(source_path.read_bytes(), source_bytes)



    def test_post_write_source_drift_fails_certification_without_rollback(self) -> None:
        entry = _load_apply_entry()
        error_type = _load_apply_error_type()
        confirmation_type = _load_confirmation_type()

        source_a = build_source_bytes()
        source_b = build_source_bytes(eye_rgb=(0.91, 0.17, 0.23))
        self.assertNotEqual(source_a, source_b)

        draft = _draft(source_a)
        approved_preview = services.preview_edit(source_a, draft)
        confirmation = _confirmation(
            confirmation_type,
            approved_preview,
            draft,
        )

        published_bytes = serialize_pmx(approved_preview.document)
        sentinel_result = SimpleNamespace(
            preview=approved_preview,
            output_sha256=hashlib.sha256(published_bytes).hexdigest(),
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.pmx"
            destination_path = root / "destination.pmx"
            source_path.write_bytes(source_a)

            def delegated_apply(*args: object, **kwargs: object):
                destination_path.write_bytes(published_bytes)
                source_path.write_bytes(source_b)
                return sentinel_result

            with (
                patch.object(
                    services,
                    "preview_edit",
                    return_value=approved_preview,
                ) as preview_mock,
                patch.object(
                    services,
                    "apply_edit",
                    side_effect=delegated_apply,
                ) as apply_mock,
            ):
                try:
                    entry(
                        source_path,
                        destination_path,
                        draft,
                        approved_preview,
                        confirmation=confirmation,
                    )
                except error_type as error:
                    self.assertEqual(
                        getattr(error, "reason", None),
                        "post_write_certification_failed",
                    )
                except Exception:
                    raise AssertionError(
                        EXPECTED_POST_WRITE_SOURCE_RECHECK_RED_MARKER
                    ) from None
                else:
                    raise AssertionError(
                        EXPECTED_POST_WRITE_SOURCE_RECHECK_RED_MARKER
                    )

            preview_mock.assert_called_once_with(source_a, draft)
            apply_mock.assert_called_once_with(
                source_path,
                destination_path,
                draft,
                overwrite=False,
            )
            self.assertTrue(destination_path.exists())
            self.assertEqual(destination_path.read_bytes(), published_bytes)
            self.assertEqual(source_path.read_bytes(), source_b)



    def test_lower_apply_service_error_propagates_unchanged(self) -> None:
        entry = _load_apply_entry()
        confirmation_type = _load_confirmation_type()

        source_bytes = build_source_bytes()
        draft = _draft(source_bytes)
        approved_preview = services.preview_edit(source_bytes, draft)
        confirmation = _confirmation(
            confirmation_type,
            approved_preview,
            draft,
        )

        sentinel_error = PmxServiceError(
            PmxServiceDiagnostic(
                code=PmxServiceDiagnosticCode.EDIT_PATH_UNSAFE,
                operation=PmxServiceOperation.APPLY_EDIT,
                message="Synthetic lower-authority apply failure.",
            )
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.pmx"
            destination_path = root / "destination.pmx"
            source_path.write_bytes(source_bytes)

            with (
                patch.object(
                    services,
                    "preview_edit",
                    return_value=approved_preview,
                ) as preview_mock,
                patch.object(
                    services,
                    "apply_edit",
                    side_effect=sentinel_error,
                ) as apply_mock,
            ):
                with self.assertRaises(PmxServiceError) as raised:
                    entry(
                        source_path,
                        destination_path,
                        draft,
                        approved_preview,
                        confirmation=confirmation,
                    )

            self.assertIs(raised.exception, sentinel_error)
            preview_mock.assert_called_once_with(source_bytes, draft)
            apply_mock.assert_called_once_with(
                source_path,
                destination_path,
                draft,
                overwrite=False,
            )
            self.assertFalse(destination_path.exists())
            self.assertEqual(source_path.read_bytes(), source_bytes)



    def test_smart_apply_has_no_second_mutation_or_publication_authority(self) -> None:
        apply_module = _load_apply_module()
        source = inspect.getsource(apply_module)

        self.assertEqual(source.count("services.apply_edit("), 1)

        for forbidden in (
            "serialize_pmx",
            "write_pmx_edit",
            "write_pmx(",
            "apply_pmx_edit_plan",
            "index_remap",
            "transaction_plan",
            ".write_bytes(",
            ".write_text(",
            "os.replace",
            "os.rename",
            "os.link",
            "os.unlink",
            "os.remove",
            "Path.unlink",
            "tempfile",
            "mkstemp",
            "NamedTemporaryFile",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)



    def test_private_smart_apply_is_not_public_and_smart_cli_remains_inspect_only(
        self,
    ) -> None:
        self.assertEqual(mmd_registry.__all__, ("__version__",))

        private_names = (
            "apply_smart_material_color_draft",
            "SmartMaterialApplyConfirmation",
            "SmartMaterialApplyError",
        )
        for name in private_names:
            with self.subTest(surface="package_root", name=name):
                self.assertFalse(hasattr(mmd_registry, name), name)
                self.assertNotIn(name, getattr(mmd_registry, "__all__", ()))

            with self.subTest(surface="services", name=name):
                self.assertFalse(hasattr(services, name), name)
                self.assertNotIn(name, getattr(services, "__all__", ()))

        parser = cli._build_application_argument_parser()
        top_level_actions = [
            action
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        ]
        self.assertEqual(len(top_level_actions), 1)

        smart_parser = top_level_actions[0].choices["smart"]
        smart_actions = [
            action
            for action in smart_parser._actions
            if isinstance(action, argparse._SubParsersAction)
        ]
        self.assertEqual(len(smart_actions), 1)
        self.assertEqual(tuple(smart_actions[0].choices), ("inspect",))



    def test_wrong_confirmation_type_fails_before_apply(self) -> None:
        entry = _load_apply_entry()

        source_bytes = build_source_bytes()
        draft = _draft(source_bytes)
        preview = services.preview_edit(source_bytes, draft)

        forged_confirmation = SimpleNamespace(
            preview_schema_version=PMX_EDIT_PREVIEW_SCHEMA_VERSION,
            source_sha256=preview.source_sha256,
            plan_sha256=calculate_pmx_edit_plan_sha256(draft),
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.pmx"
            destination_path = root / "destination.pmx"
            source_path.write_bytes(source_bytes)

            with patch.object(
                services,
                "apply_edit",
                side_effect=AssertionError(
                    EXPECTED_CP07_EXACT_CONFIRMATION_TYPE_RED_MARKER
                ),
            ) as apply_mock:
                with self.assertRaises(TypeError):
                    entry(
                        source_path,
                        destination_path,
                        draft,
                        preview,
                        confirmation=forged_confirmation,
                    )

            apply_mock.assert_not_called()
            self.assertFalse(destination_path.exists())
            self.assertEqual(source_path.read_bytes(), source_bytes)



    def test_confirmation_replays_for_same_identity_across_distinct_destinations(
        self,
    ) -> None:
        entry = _load_apply_entry()
        confirmation_type = _load_confirmation_type()

        source_bytes = build_source_bytes()
        draft = _draft(source_bytes)
        approved_preview = services.preview_edit(source_bytes, draft)
        confirmation = _confirmation(
            confirmation_type,
            approved_preview,
            draft,
        )

        self.assertFalse(hasattr(confirmation, "destination_path"))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.pmx"
            destination_a = root / "destination-a.pmx"
            destination_b = root / "destination-b.pmx"
            source_path.write_bytes(source_bytes)

            result_a = entry(
                source_path,
                destination_a,
                draft,
                approved_preview,
                confirmation=confirmation,
            )
            result_b = entry(
                source_path,
                destination_b,
                draft,
                approved_preview,
                confirmation=confirmation,
            )

            self.assertEqual(result_a.preview, approved_preview)
            self.assertEqual(result_b.preview, approved_preview)
            self.assertEqual(result_a.output_sha256, result_b.output_sha256)

            self.assertTrue(destination_a.exists())
            self.assertTrue(destination_b.exists())
            self.assertEqual(
                destination_a.read_bytes(),
                destination_b.read_bytes(),
            )
            self.assertEqual(
                load_pmx(destination_a),
                approved_preview.document,
            )
            self.assertEqual(
                load_pmx(destination_b),
                approved_preview.document,
            )
            self.assertEqual(source_path.read_bytes(), source_bytes)



    def test_stale_confirmation_from_another_source_fails_before_replay_or_apply(
        self,
    ) -> None:
        entry = _load_apply_entry()
        error_type = _load_apply_error_type()
        confirmation_type = _load_confirmation_type()

        source_a = build_source_bytes(eye_rgb=(0.2, 0.3, 0.4))
        draft_a = _draft(source_a)
        preview_a = services.preview_edit(source_a, draft_a)
        confirmation_a = _confirmation(
            confirmation_type,
            preview_a,
            draft_a,
        )

        source_b = build_source_bytes(eye_rgb=(0.25, 0.35, 0.45))
        draft_b = _draft(source_b)
        preview_b = services.preview_edit(source_b, draft_b)

        self.assertNotEqual(preview_a.source_sha256, preview_b.source_sha256)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source-b.pmx"
            destination_path = root / "destination.pmx"
            source_path.write_bytes(source_b)

            with patch.object(
                services,
                "preview_edit",
                side_effect=AssertionError(
                    "preview replay must not run for stale source confirmation"
                ),
            ) as preview_mock, patch.object(
                services,
                "apply_edit",
                side_effect=AssertionError(
                    "apply must not run for stale source confirmation"
                ),
            ) as apply_mock:
                with self.assertRaises(error_type) as raised:
                    entry(
                        source_path,
                        destination_path,
                        draft_b,
                        preview_b,
                        confirmation=confirmation_a,
                    )

            self.assertEqual(
                getattr(raised.exception, "reason", None),
                "confirmation_mismatch",
            )
            preview_mock.assert_not_called()
            apply_mock.assert_not_called()
            self.assertFalse(destination_path.exists())
            self.assertEqual(source_path.read_bytes(), source_b)

    def test_stale_confirmation_from_another_plan_fails_before_replay_or_apply(
        self,
    ) -> None:
        entry = _load_apply_entry()
        error_type = _load_apply_error_type()
        confirmation_type = _load_confirmation_type()

        source_bytes = build_source_bytes()
        draft_red = _draft(source_bytes)
        preview_red = services.preview_edit(source_bytes, draft_red)
        confirmation_red = _confirmation(
            confirmation_type,
            preview_red,
            draft_red,
        )

        draft_blue = smart_material_draft.build_smart_material_color_draft(
            source_bytes,
            SmartPartKind.EYES,
            "blue",
        )
        preview_blue = services.preview_edit(source_bytes, draft_blue)

        self.assertNotEqual(
            calculate_pmx_edit_plan_sha256(draft_red),
            calculate_pmx_edit_plan_sha256(draft_blue),
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.pmx"
            destination_path = root / "destination.pmx"
            source_path.write_bytes(source_bytes)

            with patch.object(
                services,
                "preview_edit",
                side_effect=AssertionError(
                    "preview replay must not run for stale plan confirmation"
                ),
            ) as preview_mock, patch.object(
                services,
                "apply_edit",
                side_effect=AssertionError(
                    "apply must not run for stale plan confirmation"
                ),
            ) as apply_mock:
                with self.assertRaises(error_type) as raised:
                    entry(
                        source_path,
                        destination_path,
                        draft_blue,
                        preview_blue,
                        confirmation=confirmation_red,
                    )

            self.assertEqual(
                getattr(raised.exception, "reason", None),
                "confirmation_mismatch",
            )
            preview_mock.assert_not_called()
            apply_mock.assert_not_called()
            self.assertFalse(destination_path.exists())
            self.assertEqual(source_path.read_bytes(), source_bytes)



    def test_preview_plan_sha_identity_mismatch_fails_before_replay_or_apply(
        self,
    ) -> None:
        entry = _load_apply_entry()
        error_type = _load_apply_error_type()
        confirmation_type = _load_confirmation_type()

        source_bytes = build_source_bytes()
        draft = _draft(source_bytes)
        approved_preview = services.preview_edit(source_bytes, draft)
        confirmation = _confirmation(
            confirmation_type,
            approved_preview,
            draft,
        )

        replacement_plan_sha = "0" * 64
        if replacement_plan_sha == approved_preview.plan_sha256:
            replacement_plan_sha = "1" * 64

        forged_preview = dataclasses.replace(
            approved_preview,
            plan_sha256=replacement_plan_sha,
        )
        self.assertNotEqual(
            forged_preview.plan_sha256,
            approved_preview.plan_sha256,
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.pmx"
            destination_path = root / "destination.pmx"
            source_path.write_bytes(source_bytes)

            with patch.object(
                services,
                "preview_edit",
                side_effect=AssertionError(
                    EXPECTED_CP08_PREVIEW_PLAN_IDENTITY_RED_MARKER
                ),
            ) as preview_mock, patch.object(
                services,
                "apply_edit",
                side_effect=AssertionError(
                    "apply must not run for mismatched preview plan identity"
                ),
            ) as apply_mock:
                with self.assertRaises(error_type) as raised:
                    entry(
                        source_path,
                        destination_path,
                        draft,
                        forged_preview,
                        confirmation=confirmation,
                    )

            self.assertEqual(
                getattr(raised.exception, "reason", None),
                "confirmation_mismatch",
            )
            preview_mock.assert_not_called()
            apply_mock.assert_not_called()
            self.assertFalse(destination_path.exists())
            self.assertEqual(source_path.read_bytes(), source_bytes)



    def test_preview_plan_schema_mismatch_fails_before_replay_or_apply(
        self,
    ) -> None:
        entry = _load_apply_entry()
        error_type = _load_apply_error_type()
        confirmation_type = _load_confirmation_type()

        source_bytes = build_source_bytes()
        draft = _draft(source_bytes)
        approved_preview = services.preview_edit(source_bytes, draft)
        confirmation = _confirmation(
            confirmation_type,
            approved_preview,
            draft,
        )

        forged_preview = dataclasses.replace(
            approved_preview,
            plan_schema_version=draft.schema_version + 1,
        )
        self.assertNotEqual(
            forged_preview.plan_schema_version,
            draft.schema_version,
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.pmx"
            destination_path = root / "destination.pmx"
            source_path.write_bytes(source_bytes)

            with patch.object(
                services,
                "preview_edit",
                side_effect=AssertionError(
                    EXPECTED_CP08_PREVIEW_PLAN_SCHEMA_RED_MARKER
                ),
            ) as preview_mock, patch.object(
                services,
                "apply_edit",
                side_effect=AssertionError(
                    "apply must not run for mismatched preview plan schema"
                ),
            ) as apply_mock:
                with self.assertRaises(error_type) as raised:
                    entry(
                        source_path,
                        destination_path,
                        draft,
                        forged_preview,
                        confirmation=confirmation,
                    )

            self.assertEqual(
                getattr(raised.exception, "reason", None),
                "confirmation_mismatch",
            )
            preview_mock.assert_not_called()
            apply_mock.assert_not_called()
            self.assertFalse(destination_path.exists())
            self.assertEqual(source_path.read_bytes(), source_bytes)



    def test_preview_operation_count_mismatch_fails_before_replay_or_apply(
        self,
    ) -> None:
        entry = _load_apply_entry()
        error_type = _load_apply_error_type()
        confirmation_type = _load_confirmation_type()

        source_bytes = build_source_bytes()
        draft = _draft(source_bytes)
        approved_preview = services.preview_edit(source_bytes, draft)
        confirmation = _confirmation(
            confirmation_type,
            approved_preview,
            draft,
        )

        forged_preview = dataclasses.replace(
            approved_preview,
            operation_count=approved_preview.operation_count + 1,
        )
        self.assertNotEqual(
            forged_preview.operation_count,
            len(draft.operations),
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.pmx"
            destination_path = root / "destination.pmx"
            source_path.write_bytes(source_bytes)

            with patch.object(
                services,
                "preview_edit",
                side_effect=AssertionError(
                    EXPECTED_CP08_PREVIEW_OPERATION_COUNT_RED_MARKER
                ),
            ) as preview_mock, patch.object(
                services,
                "apply_edit",
                side_effect=AssertionError(
                    "apply must not run for mismatched preview operation count"
                ),
            ) as apply_mock:
                with self.assertRaises(error_type) as raised:
                    entry(
                        source_path,
                        destination_path,
                        draft,
                        forged_preview,
                        confirmation=confirmation,
                    )

            self.assertEqual(
                getattr(raised.exception, "reason", None),
                "confirmation_mismatch",
            )
            preview_mock.assert_not_called()
            apply_mock.assert_not_called()
            self.assertFalse(destination_path.exists())
            self.assertEqual(source_path.read_bytes(), source_bytes)



    def test_existing_destination_is_never_overwritten_and_source_stays_unchanged(
        self,
    ) -> None:
        entry = _load_apply_entry()
        confirmation_type = _load_confirmation_type()

        source_bytes = build_source_bytes()
        draft = _draft(source_bytes)
        approved_preview = services.preview_edit(source_bytes, draft)
        confirmation = _confirmation(
            confirmation_type,
            approved_preview,
            draft,
        )
        original_destination_bytes = b"existing-destination-must-not-be-overwritten"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.pmx"
            destination_path = root / "destination.pmx"
            source_path.write_bytes(source_bytes)
            destination_path.write_bytes(original_destination_bytes)

            with self.assertRaises(PmxServiceError):
                entry(
                    source_path,
                    destination_path,
                    draft,
                    approved_preview,
                    confirmation=confirmation,
                )

            self.assertEqual(source_path.read_bytes(), source_bytes)
            self.assertEqual(
                destination_path.read_bytes(),
                original_destination_bytes,
            )



    def test_source_equal_destination_fails_through_lower_path_authority(
        self,
    ) -> None:
        entry = _load_apply_entry()
        confirmation_type = _load_confirmation_type()

        source_bytes = build_source_bytes()
        draft = _draft(source_bytes)
        approved_preview = services.preview_edit(source_bytes, draft)
        confirmation = _confirmation(
            confirmation_type,
            approved_preview,
            draft,
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.pmx"
            source_path.write_bytes(source_bytes)

            with self.assertRaises(PmxServiceError):
                entry(
                    source_path,
                    source_path,
                    draft,
                    approved_preview,
                    confirmation=confirmation,
                )

            self.assertEqual(source_path.read_bytes(), source_bytes)



    def test_successful_real_apply_preserves_source_byte_identity(
        self,
    ) -> None:
        entry = _load_apply_entry()
        confirmation_type = _load_confirmation_type()

        source_bytes = build_source_bytes()
        source_sha256_before = hashlib.sha256(source_bytes).hexdigest()
        draft = _draft(source_bytes)
        approved_preview = services.preview_edit(source_bytes, draft)
        confirmation = _confirmation(
            confirmation_type,
            approved_preview,
            draft,
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.pmx"
            destination_path = root / "destination.pmx"
            source_path.write_bytes(source_bytes)

            result = entry(
                source_path,
                destination_path,
                draft,
                approved_preview,
                confirmation=confirmation,
            )

            self.assertTrue(destination_path.exists())
            self.assertEqual(result.preview, approved_preview)
            self.assertEqual(source_path.read_bytes(), source_bytes)
            self.assertEqual(
                hashlib.sha256(source_path.read_bytes()).hexdigest(),
                source_sha256_before,
            )
            self.assertEqual(
                hashlib.sha256(source_path.read_bytes()).hexdigest(),
                approved_preview.source_sha256,
            )
            self.assertEqual(
                load_pmx(destination_path),
                approved_preview.document,
            )



    def test_successful_real_apply_post_write_certification_is_exact(
        self,
    ) -> None:
        entry = _load_apply_entry()
        confirmation_type = _load_confirmation_type()

        source_bytes = build_source_bytes()
        draft = _draft(source_bytes)
        approved_preview = services.preview_edit(source_bytes, draft)
        confirmation = _confirmation(
            confirmation_type,
            approved_preview,
            draft,
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.pmx"
            destination_path = root / "destination.pmx"
            source_path.write_bytes(source_bytes)

            result = entry(
                source_path,
                destination_path,
                draft,
                approved_preview,
                confirmation=confirmation,
            )

            destination_bytes = destination_path.read_bytes()
            destination_sha256 = hashlib.sha256(destination_bytes).hexdigest()
            reparsed_document = load_pmx(io.BytesIO(destination_bytes))

            self.assertEqual(destination_sha256, result.output_sha256)
            validate_pmx_document(reparsed_document)
            self.assertEqual(reparsed_document, approved_preview.document)
            self.assertEqual(result.preview, approved_preview)
            self.assertEqual(source_path.read_bytes(), source_bytes)



    def test_source_drift_after_replay_before_apply_is_rejected_by_lower_authority(
        self,
    ) -> None:
        entry = _load_apply_entry()
        confirmation_type = _load_confirmation_type()

        source_a = build_source_bytes()
        source_b = build_source_bytes(eye_rgb=(0.23, 0.33, 0.43))
        draft = _draft(source_a)
        approved_preview = services.preview_edit(source_a, draft)
        confirmation = _confirmation(
            confirmation_type,
            approved_preview,
            draft,
        )
        original_preview_edit = services.preview_edit

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.pmx"
            destination_path = root / "destination.pmx"
            source_path.write_bytes(source_a)

            replay_calls = 0

            def replay_then_drift(source_bytes, replay_draft):
                nonlocal replay_calls
                replay_calls += 1
                replay = original_preview_edit(source_bytes, replay_draft)
                source_path.write_bytes(source_b)
                return replay

            with patch.object(
                services,
                "preview_edit",
                side_effect=replay_then_drift,
            ):
                with self.assertRaises(PmxServiceError):
                    entry(
                        source_path,
                        destination_path,
                        draft,
                        approved_preview,
                        confirmation=confirmation,
                    )

            self.assertEqual(replay_calls, 1)
            self.assertFalse(destination_path.exists())
            self.assertEqual(source_path.read_bytes(), source_b)

    def test_source_drift_during_lower_apply_before_commit_is_rejected_and_temp_cleaned(
        self,
    ) -> None:
        entry = _load_apply_entry()
        confirmation_type = _load_confirmation_type()

        source_a = build_source_bytes()
        source_b = build_source_bytes(eye_rgb=(0.27, 0.37, 0.47))
        draft = _draft(source_a)
        approved_preview = services.preview_edit(source_a, draft)
        confirmation = _confirmation(
            confirmation_type,
            approved_preview,
            draft,
        )
        original_serialize = edit_output.serialize_pmx

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.pmx"
            destination_path = root / "destination.pmx"
            source_path.write_bytes(source_a)

            serialize_calls = 0

            def serialize_then_drift(document):
                nonlocal serialize_calls
                serialize_calls += 1
                data = original_serialize(document)
                source_path.write_bytes(source_b)
                return data

            with patch.object(
                edit_output,
                "serialize_pmx",
                side_effect=serialize_then_drift,
            ):
                with self.assertRaises(PmxServiceError):
                    entry(
                        source_path,
                        destination_path,
                        draft,
                        approved_preview,
                        confirmation=confirmation,
                    )

            self.assertEqual(serialize_calls, 1)
            self.assertFalse(destination_path.exists())
            self.assertEqual(source_path.read_bytes(), source_b)
            self.assertEqual(
                list(root.glob(f".{destination_path.name}.*.tmp")),
                [],
            )

    def test_destination_publish_racer_is_preserved_and_temp_cleaned(
        self,
    ) -> None:
        entry = _load_apply_entry()
        confirmation_type = _load_confirmation_type()

        source_bytes = build_source_bytes()
        draft = _draft(source_bytes)
        approved_preview = services.preview_edit(source_bytes, draft)
        confirmation = _confirmation(
            confirmation_type,
            approved_preview,
            draft,
        )
        racer_bytes = b"CP11 destination publish racer"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.pmx"
            destination_path = root / "destination.pmx"
            source_path.write_bytes(source_bytes)

            def publish_collision(temporary, target):
                temporary_path = Path(temporary)
                target_path = Path(target)
                self.assertTrue(temporary_path.is_file())
                self.assertFalse(target_path.exists())
                target_path.write_bytes(racer_bytes)
                raise FileExistsError("simulated CP11 no-clobber race")

            with patch.object(
                edit_output,
                "_publish_no_clobber",
                side_effect=publish_collision,
            ):
                with self.assertRaises(PmxServiceError):
                    entry(
                        source_path,
                        destination_path,
                        draft,
                        approved_preview,
                        confirmation=confirmation,
                    )

            self.assertEqual(destination_path.read_bytes(), racer_bytes)
            self.assertEqual(source_path.read_bytes(), source_bytes)
            self.assertEqual(
                list(root.glob(f".{destination_path.name}.*.tmp")),
                [],
            )

    def test_second_destination_check_rejects_hardlink_race_through_smart_boundary(
        self,
    ) -> None:
        entry = _load_apply_entry()
        confirmation_type = _load_confirmation_type()

        source_bytes = build_source_bytes()
        draft = _draft(source_bytes)
        approved_preview = services.preview_edit(source_bytes, draft)
        confirmation = _confirmation(
            confirmation_type,
            approved_preview,
            draft,
        )
        original_validate = edit_output._validate_destination_state

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.pmx"
            destination_path = root / "destination.pmx"
            source_path.write_bytes(source_bytes)
            calls = 0

            def race(source: Path, output: Path, *, overwrite: bool) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    os.link(source, output)
                original_validate(source, output, overwrite=overwrite)

            with patch.object(
                edit_output,
                "_validate_destination_state",
                side_effect=race,
            ):
                with self.assertRaises(PmxServiceError):
                    entry(
                        source_path,
                        destination_path,
                        draft,
                        approved_preview,
                        confirmation=confirmation,
                    )

            self.assertEqual(calls, 2)
            self.assertTrue(source_path.samefile(destination_path))
            self.assertEqual(source_path.read_bytes(), source_bytes)
            self.assertEqual(
                list(root.glob(f".{destination_path.name}.*.tmp")),
                [],
            )



    def test_source_identity_replacement_with_same_bytes_is_rejected_before_commit(
        self,
    ) -> None:
        entry = _load_apply_entry()
        confirmation_type = _load_confirmation_type()

        source_bytes = build_source_bytes()
        draft = _draft(source_bytes)
        approved_preview = services.preview_edit(source_bytes, draft)
        confirmation = _confirmation(
            confirmation_type,
            approved_preview,
            draft,
        )
        original_serialize = edit_output.serialize_pmx

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.pmx"
            replacement_path = root / "replacement.pmx"
            destination_path = root / "destination.pmx"
            source_path.write_bytes(source_bytes)
            replacement_path.write_bytes(source_bytes)

            serialize_calls = 0

            def serialize_then_replace_source(document):
                nonlocal serialize_calls
                serialize_calls += 1
                data = original_serialize(document)
                os.replace(replacement_path, source_path)
                return data

            with patch.object(
                edit_output,
                "serialize_pmx",
                side_effect=serialize_then_replace_source,
            ):
                with self.assertRaises(PmxServiceError):
                    entry(
                        source_path,
                        destination_path,
                        draft,
                        approved_preview,
                        confirmation=confirmation,
                    )

            self.assertEqual(serialize_calls, 1)
            self.assertFalse(destination_path.exists())
            self.assertFalse(replacement_path.exists())
            self.assertEqual(source_path.read_bytes(), source_bytes)
            self.assertEqual(
                list(root.glob(f".{destination_path.name}.*.tmp")),
                [],
            )



    def test_repeated_real_apply_to_independent_destinations_is_byte_deterministic(
        self,
    ) -> None:
        entry = _load_apply_entry()
        confirmation_type = _load_confirmation_type()

        source_bytes = build_source_bytes()
        draft = _draft(source_bytes)
        approved_preview = services.preview_edit(source_bytes, draft)
        confirmation = _confirmation(
            confirmation_type,
            approved_preview,
            draft,
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.pmx"
            destination_a = root / "destination-a.pmx"
            destination_b = root / "destination-b.pmx"
            source_path.write_bytes(source_bytes)

            result_a = entry(
                source_path,
                destination_a,
                draft,
                approved_preview,
                confirmation=confirmation,
            )
            result_b = entry(
                source_path,
                destination_b,
                draft,
                approved_preview,
                confirmation=confirmation,
            )

            bytes_a = destination_a.read_bytes()
            bytes_b = destination_b.read_bytes()
            self.assertEqual(bytes_a, bytes_b)
            self.assertEqual(result_a.output_sha256, result_b.output_sha256)
            self.assertEqual(
                hashlib.sha256(bytes_a).hexdigest(),
                result_a.output_sha256,
            )
            self.assertEqual(
                load_pmx(io.BytesIO(bytes_a)),
                load_pmx(io.BytesIO(bytes_b)),
            )
            self.assertEqual(
                load_pmx(io.BytesIO(bytes_a)),
                approved_preview.document,
            )
            self.assertEqual(source_path.read_bytes(), source_bytes)
            self.assertEqual(
                list(root.glob(".destination-*.pmx.*.tmp")),
                [],
            )

    def test_real_apply_preserves_alpha_untouched_fields_and_non_target_materials(
        self,
    ) -> None:
        entry = _load_apply_entry()
        confirmation_type = _load_confirmation_type()

        source_bytes = build_source_bytes()
        source_document = load_pmx(io.BytesIO(source_bytes))
        draft = smart_material_draft.build_smart_material_color_draft(
            source_bytes,
            SmartPartKind.EYES,
            "purple",
        )
        approved_preview = services.preview_edit(source_bytes, draft)
        confirmation = _confirmation(
            confirmation_type,
            approved_preview,
            draft,
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.pmx"
            destination_path = root / "destination.pmx"
            source_path.write_bytes(source_bytes)

            result = entry(
                source_path,
                destination_path,
                draft,
                approved_preview,
                confirmation=confirmation,
            )
            output_document = load_pmx(destination_path)

            self.assertEqual(result.preview, approved_preview)
            self.assertEqual(output_document, approved_preview.document)
            self.assertEqual(
                output_document.materials[0],
                source_document.materials[0],
            )
            self.assertEqual(
                tuple(operation.material_index for operation in draft.operations),
                (1, 2),
            )

            for operation in draft.operations:
                index = operation.material_index
                source_material = source_document.materials[index]
                output_material = output_document.materials[index]

                self.assertEqual(
                    output_material.diffuse[:3],
                    operation.diffuse[:3],
                )
                self.assertEqual(
                    output_material.diffuse[3],
                    source_material.diffuse[3],
                )
                for field in dataclasses.fields(source_material):
                    if field.name == "diffuse":
                        continue
                    self.assertEqual(
                        getattr(output_material, field.name),
                        getattr(source_material, field.name),
                        msg=f"material_index={index} field={field.name}",
                    )

            self.assertEqual(source_path.read_bytes(), source_bytes)

    def test_malformed_non_plan_draft_is_rejected_before_replay_or_apply(
        self,
    ) -> None:
        entry = _load_apply_entry()
        confirmation_type = _load_confirmation_type()
        malformed_draft = SimpleNamespace(
            schema_version=1,
            operations=(),
            expected_source_sha256="0" * 64,
        )
        fake_preview = SimpleNamespace(
            source_sha256="0" * 64,
            plan_sha256="0" * 64,
            plan_schema_version=1,
            operation_count=0,
        )
        confirmation = confirmation_type(
            preview_schema_version=PMX_EDIT_PREVIEW_SCHEMA_VERSION,
            source_sha256="0" * 64,
            plan_sha256="0" * 64,
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source-does-not-need-to-exist.pmx"
            destination_path = root / "destination.pmx"

            with patch.object(
                services,
                "preview_edit",
                side_effect=AssertionError("preview replay must not run"),
            ) as replay_mock:
                with patch.object(
                    services,
                    "apply_edit",
                    side_effect=AssertionError("apply must not run"),
                ) as apply_mock:
                    with self.assertRaises(TypeError):
                        entry(
                            source_path,
                            destination_path,
                            malformed_draft,
                            fake_preview,
                            confirmation=confirmation,
                        )

            replay_mock.assert_not_called()
            apply_mock.assert_not_called()
            self.assertFalse(destination_path.exists())


if __name__ == "__main__":
    unittest.main()
