"""v0.9.5.7 Smart Material preview bridge TDD contract tests."""

from __future__ import annotations

import hashlib
import importlib
import sys
import unittest
from unittest.mock import patch

import mmd_registry
import mmd_registry.services as services
import mmd_registry.services._smart_material_draft as smart_material_draft
from mmd_registry.diagnostics import (
    PmxServiceDiagnosticCode,
    PmxServiceError,
    PmxServiceOperation,
)
from mmd_registry.pmx.editing import (
    PmxEditPlan,
    PmxEditPreview,
    calculate_pmx_edit_plan_sha256,
)
from mmd_registry.smart_parts import SmartPartKind
from tests.test_v0956_smart_material_draft import build_source_bytes


BRIDGE_MODULE_NAME = "mmd_registry.services._smart_material_preview"
BRIDGE_ENTRY_NAME = "preview_smart_material_color_draft"
EXPECTED_RED_MARKER = "EXPECTED_CP06_RED_MISSING_SMART_MATERIAL_PREVIEW_BRIDGE"


def _load_bridge() -> tuple[object, object]:
    try:
        module = importlib.import_module(BRIDGE_MODULE_NAME)
    except ModuleNotFoundError as error:
        if error.name == BRIDGE_MODULE_NAME:
            raise AssertionError(EXPECTED_RED_MARKER) from None
        raise

    entry = getattr(module, BRIDGE_ENTRY_NAME, None)
    if not callable(entry):
        raise AssertionError(
            EXPECTED_RED_MARKER + "_ENTRY"
        )
    return module, entry


def _draft(
    source_bytes: bytes,
    *,
    color: object = "red",
) -> PmxEditPlan:
    return smart_material_draft.build_smart_material_color_draft(
        source_bytes,
        SmartPartKind.EYES,
        color,  # type: ignore[arg-type]
    )


class SmartMaterialPreviewBridgeTests(unittest.TestCase):
    def test_certified_draft_previews_through_existing_authority(self) -> None:
        source_bytes = build_source_bytes()
        draft = _draft(source_bytes)
        _, bridge = _load_bridge()

        expected = services.preview_edit(source_bytes, draft)
        actual = bridge(source_bytes, draft)

        self.assertIsInstance(actual, PmxEditPreview)
        self.assertEqual(actual, expected)
        self.assertEqual(
            actual.plan_sha256,
            calculate_pmx_edit_plan_sha256(draft),
        )
        self.assertEqual(
            actual.source_sha256,
            hashlib.sha256(source_bytes).hexdigest(),
        )
        self.assertEqual(actual.plan_schema_version, 1)
        self.assertEqual(actual.operation_count, len(draft.operations))
        self.assertEqual(
            actual.to_dict()["output"],
            {"written": False, "sha256": None},
        )
        self.assertEqual(
            actual.to_dict()["verification"],
            {"semantic": "passed", "input_unchanged": True},
        )

    def test_exact_draft_preview_parity_uses_draft_targets(self) -> None:
        source_bytes = build_source_bytes()
        draft = _draft(source_bytes, color="purple")
        _, bridge = _load_bridge()

        preview = bridge(source_bytes, draft)

        expected_indices = tuple(
            operation.material_index
            for operation in draft.operations
        )
        observed_indices = tuple(
            change.target_index
            for change in preview.audit.changes
            if change.category == "material"
            and change.field_path.endswith(".diffuse")
        )
        self.assertEqual(observed_indices, expected_indices)

        expected_after = tuple(
            operation.diffuse
            for operation in draft.operations
        )
        observed_after = tuple(
            change.after
            for change in preview.audit.changes
            if change.category == "material"
            and change.field_path.endswith(".diffuse")
        )
        self.assertEqual(observed_after, expected_after)

    def test_source_bytes_remain_unchanged(self) -> None:
        source_bytes = build_source_bytes()
        draft = _draft(source_bytes, color="green")
        _, bridge = _load_bridge()
        before_bytes = bytes(source_bytes)
        before_sha = hashlib.sha256(source_bytes).hexdigest()

        bridge(source_bytes, draft)

        self.assertEqual(source_bytes, before_bytes)
        self.assertEqual(
            hashlib.sha256(source_bytes).hexdigest(),
            before_sha,
        )

    def test_bridge_does_not_invoke_apply_or_write_authority(self) -> None:
        source_bytes = build_source_bytes()
        draft = _draft(source_bytes, color="blue")
        _, bridge = _load_bridge()

        with (
            patch.object(
                services,
                "apply_edit",
                side_effect=AssertionError("apply_edit must not run"),
            ) as apply_mock,
            patch.object(
                services,
                "write_pmx_edit",
                side_effect=AssertionError("write_pmx_edit must not run"),
            ) as write_mock,
        ):
            result = bridge(source_bytes, draft)

        self.assertIsInstance(result, PmxEditPreview)
        apply_mock.assert_not_called()
        write_mock.assert_not_called()

    def test_bridge_forwards_exact_inputs_to_existing_preview_service(self) -> None:
        source_bytes = build_source_bytes()
        draft = _draft(source_bytes, color="red")
        sentinel = object()
        sys.modules.pop(BRIDGE_MODULE_NAME, None)

        try:
            with patch.object(
                services,
                "preview_edit",
                return_value=sentinel,
            ) as preview_mock:
                module = importlib.import_module(BRIDGE_MODULE_NAME)
                bridge = getattr(module, BRIDGE_ENTRY_NAME)
                result = bridge(source_bytes, draft)

            self.assertIs(result, sentinel)
            preview_mock.assert_called_once_with(source_bytes, draft)
        except ModuleNotFoundError as error:
            if error.name == BRIDGE_MODULE_NAME:
                raise AssertionError(EXPECTED_RED_MARKER) from None
            raise
        finally:
            sys.modules.pop(BRIDGE_MODULE_NAME, None)

    def test_stale_draft_against_different_valid_source_fails_closed(self) -> None:
        source_a = build_source_bytes()
        draft_a = _draft(source_a, color="red")
        source_b = build_source_bytes(eye_rgb=(0.21, 0.31, 0.41))
        _, bridge = _load_bridge()

        with self.assertRaises(PmxServiceError) as raised:
            bridge(source_b, draft_a)

        self.assertEqual(
            raised.exception.diagnostic.code,
            PmxServiceDiagnosticCode.EDIT_PLAN_INVALID,
        )
        self.assertEqual(
            raised.exception.diagnostic.operation,
            PmxServiceOperation.PREVIEW_EDIT,
        )
        self.assertEqual(
            dict(raised.exception.diagnostic.details),
            {
                "operation_index": None,
                "operation_type": None,
                "field": "expected_source_sha256",
            },
        )

    def test_root_public_api_remains_unchanged(self) -> None:
        self.assertEqual(mmd_registry.__all__, ("__version__",))

    def test_private_bridge_is_not_promoted_to_services_root(self) -> None:
        self.assertNotIn(BRIDGE_ENTRY_NAME, services.__all__)
        self.assertFalse(hasattr(services, BRIDGE_ENTRY_NAME))


if __name__ == "__main__":
    unittest.main()
