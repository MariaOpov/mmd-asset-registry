"""v0.9.5 rich diff contracts for certified structural preview evidence."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import inspect
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import mmd_registry.services as services
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.writer import serialize_pmx
from mmd_registry.services import structural_authoring_diff as diff_service
from mmd_registry.services.structural_transaction_plan import (
    parse_structural_transaction_plan_json,
)
from mmd_registry.services.structural_transaction_plan_preview import (
    PmxStructuralTransactionPlanPreviewResult,
    preview_structural_transaction_plan,
)
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


def _clean_source_bytes() -> bytes:
    fixture = build_pmx_roundtrip_fixture(version=2.1, index_size=1)
    document = replace(
        load_pmx(io.BytesIO(fixture)),
        trailing_data=b"",
    )
    return serialize_pmx(document)


class StructuralAuthoringDiffTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.source_path = self.root / "source.pmx"
        self.source_path.write_bytes(_clean_source_bytes())

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _preview(
        self,
        operations: list[dict[str, object]],
    ) -> PmxStructuralTransactionPlanPreviewResult:
        validated = parse_structural_transaction_plan_json(
            json.dumps(
                {
                    "schema_version": 1,
                    "operations": operations,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return preview_structural_transaction_plan(
            self.source_path,
            validated,
        )

    def test_noop_preview_projects_all_target_kinds_without_guessing(self) -> None:
        preview = self._preview([])
        result = diff_service.build_structural_authoring_diff(preview)

        self.assertEqual(result.status, "no_changes")
        self.assertEqual(result.changed_targets, ())
        self.assertEqual(result.inserted_count, 0)
        self.assertEqual(result.deleted_count, 0)
        self.assertEqual(result.reordered_target_count, 0)
        self.assertEqual(
            tuple(item.target_kind for item in result.collections),
            tuple(diff_service.PmxReferenceTargetKind),
        )
        for item in result.collections:
            self.assertEqual(item.captured_count, item.final_count)
            self.assertEqual(item.count_delta, 0)
            self.assertFalse(item.changed)
            self.assertEqual(item.insertions, ())
            self.assertEqual(item.deleted_old_indices, ())

    def test_texture_append_projects_certified_count_and_final_index(self) -> None:
        preview = self._preview(
            [
                {
                    "op": "insert_texture",
                    "path": "テクスチャ/追加.png",
                }
            ]
        )
        result = diff_service.build_structural_authoring_diff(preview)
        texture = next(
            item
            for item in result.collections
            if item.target_kind.value == "texture"
        )

        self.assertEqual(result.status, "changes_pending")
        self.assertEqual(
            tuple(item.value for item in result.changed_targets),
            ("texture",),
        )
        self.assertEqual(result.inserted_count, 1)
        self.assertEqual(result.deleted_count, 0)
        self.assertEqual(texture.count_delta, 1)
        self.assertTrue(texture.changed)
        self.assertEqual(len(texture.insertions), 1)
        self.assertEqual(texture.insertions[0].request_ordinal, 0)
        self.assertEqual(
            texture.insertions[0].final_index,
            texture.captured_count,
        )
        self.assertEqual(
            tuple(item.value for item in result.dependency_materialization_order),
            ("texture",),
        )

    def test_projection_preserves_only_public_certified_identity_status(self) -> None:
        result = diff_service.build_structural_authoring_diff(self._preview([]))
        payload = result.to_dict()

        self.assertEqual(
            payload["source_identity"],
            {
                "expected_source_sha256_declared": False,
                "status": "not_declared",
            },
        )
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn(str(self.source_path), serialized)
        self.assertNotIn('"source_sha256"', serialized)
        self.assertNotIn('"semantic_sha256"', serialized)
        self.assertEqual(len(payload["plan_sha256"]), 64)

    def test_projection_is_repeatable_frozen_and_json_safe(self) -> None:
        preview = self._preview(
            [{"op": "insert_texture", "path": "textures/new.png"}]
        )
        first = diff_service.build_structural_authoring_diff(preview)
        second = diff_service.build_structural_authoring_diff(preview)

        self.assertEqual(first, second)
        self.assertEqual(first.to_dict(), second.to_dict())
        json.dumps(first.to_dict(), ensure_ascii=False, allow_nan=False)
        with self.assertRaises(FrozenInstanceError):
            first.status = "no_changes"  # type: ignore[misc]

    def test_wrong_input_is_invalid_argument(self) -> None:
        with self.assertRaises(
            diff_service.PmxStructuralAuthoringDiffServiceError
        ) as raised:
            diff_service.build_structural_authoring_diff(
                object(),  # type: ignore[arg-type]
            )
        self.assertEqual(
            raised.exception.to_dict(),
            {
                "code": "invalid_argument",
                "operation": "build_structural_authoring_diff",
                "message": "Invalid structural authoring diff input.",
            },
        )

    def test_malformed_certified_evidence_fails_closed_without_value_disclosure(
        self,
    ) -> None:
        preview = self._preview([])
        secret = "SECRET-PREVIEW-VALUE"
        with patch.object(
            PmxStructuralTransactionPlanPreviewResult,
            "to_dict",
            return_value={"effects": secret},
        ):
            with self.assertRaises(
                diff_service.PmxStructuralAuthoringDiffServiceError
            ) as raised:
                diff_service.build_structural_authoring_diff(preview)

        self.assertEqual(
            raised.exception.to_dict(),
            {
                "code": "certified_preview_evidence_invalid",
                "operation": "build_structural_authoring_diff",
                "message": "Certified structural preview evidence is invalid.",
            },
        )
        self.assertNotIn(secret, str(raised.exception.to_dict()))

    def test_projection_does_not_touch_document_or_private_preview(self) -> None:
        source = inspect.getsource(diff_service)
        for forbidden in (
            "preview.document",
            "._preview",
            "source_document",
            "preview.source_sha256",
            "preview.semantic_sha256",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_service_does_not_import_execution_writer_remap_or_filesystem(self) -> None:
        source = inspect.getsource(diff_service)
        for forbidden in (
            "structural_transaction import",
            "preview_structural_transaction(",
            "structural_output",
            "index_remap",
            "writer",
            "write_pmx",
            "serialize_pmx",
            "load_document",
            "Path(",
            ".open(",
            "hashlib",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

        self.assertNotIn(
            "build_structural_authoring_diff",
            services.__all__,
        )

    def test_totals_are_checked_against_projected_collection_evidence(self) -> None:
        preview = self._preview([])
        payload = preview.to_dict()
        payload["effects"]["inserted_count"] = 1

        with patch.object(
            PmxStructuralTransactionPlanPreviewResult,
            "to_dict",
            return_value=payload,
        ):
            with self.assertRaises(
                diff_service.PmxStructuralAuthoringDiffServiceError
            ) as raised:
                diff_service.build_structural_authoring_diff(preview)

        self.assertEqual(
            raised.exception.to_dict()["code"],
            "certified_preview_evidence_invalid",
        )

    def test_process_control_exceptions_escape(self) -> None:
        preview = self._preview([])
        with patch.object(
            PmxStructuralTransactionPlanPreviewResult,
            "to_dict",
            side_effect=KeyboardInterrupt(),
        ):
            with self.assertRaises(KeyboardInterrupt):
                diff_service.build_structural_authoring_diff(preview)


if __name__ == "__main__":
    unittest.main()
