"""Tests for pure immutable PMX model-metadata editing."""

from __future__ import annotations

import io
import unittest
from dataclasses import FrozenInstanceError, replace

from mmd_registry.pmx import (
    PmxValidationError,
    load_pmx,
    serialize_pmx,
    validate_pmx_document,
)
from mmd_registry.pmx.editing import (
    PmxEditAudit,
    PmxEditPlanError,
    PmxEditResult,
    SetModelInfo,
    SetTexturePath,
    apply_set_model_info,
)
from tests.mmd_fixtures import build_pmx_bone, build_pmx_structure


def load_document(*, encoding_flag: int = 1):
    """Return one valid generated PMX document with the requested encoding."""

    return load_pmx(
        io.BytesIO(
            build_pmx_structure(
                encoding_flag=encoding_flag,
                texture_paths=("textures/body.png",),
                bones=(build_pmx_bone(encoding_flag=encoding_flag),),
            )
        )
    )


class PmxMetadataEditingTests(unittest.TestCase):
    """Validate pure model-information replacement and exact auditing."""

    def test_updates_all_four_fields_in_stable_order(self) -> None:
        source = load_document()
        operation = SetModelInfo(
            local_name="新しいモデル",
            universal_name="New Model",
            local_comments="安全な編集",
            universal_comments="Safe edit",
        )

        result = apply_set_model_info(source, operation, operation_index=3)

        self.assertEqual(result.document.model_info.local_name, "新しいモデル")
        self.assertEqual(result.document.model_info.universal_name, "New Model")
        self.assertEqual(result.document.model_info.local_comments, "安全な編集")
        self.assertEqual(result.document.model_info.universal_comments, "Safe edit")
        self.assertEqual(
            tuple(change.field_path for change in result.audit.changes),
            (
                "model_info.local_name",
                "model_info.universal_name",
                "model_info.local_comments",
                "model_info.universal_comments",
            ),
        )
        self.assertTrue(
            all(change.operation_index == 3 for change in result.audit.changes)
        )
        self.assertEqual(result.audit.category_count("model"), 4)
        validate_pmx_document(result.document)

    def test_exact_before_after_values_are_audited(self) -> None:
        source = load_document()

        result = apply_set_model_info(
            source,
            SetModelInfo(local_name="Renamed"),
        )

        self.assertEqual(len(result.audit.changes), 1)
        change = result.audit.changes[0]
        self.assertEqual(change.category, "model")
        self.assertIsNone(change.target_index)
        self.assertEqual(change.target_name, "Test PMX Model")
        self.assertEqual(change.field_path, "model_info.local_name")
        self.assertEqual(change.before, "Test PMX Model")
        self.assertEqual(change.after, "Renamed")
        self.assertEqual(change.operation_index, 0)

    def test_noop_returns_source_without_fake_audit_records(self) -> None:
        source = load_document()

        result = apply_set_model_info(
            source,
            SetModelInfo(
                local_name=source.model_info.local_name,
                local_comments=source.model_info.local_comments,
            ),
        )

        self.assertIs(result.document, source)
        self.assertEqual(result.audit, PmxEditAudit())
        self.assertEqual(result.audit.changed_fields, 0)

    def test_mixed_noop_and_effective_fields_only_audits_changes(self) -> None:
        source = load_document()

        result = apply_set_model_info(
            source,
            SetModelInfo(
                local_name=source.model_info.local_name,
                universal_name="Changed",
            ),
        )

        self.assertEqual(result.audit.changed_fields, 1)
        self.assertEqual(
            result.audit.changes[0].field_path,
            "model_info.universal_name",
        )

    def test_source_document_and_unrelated_sections_remain_unchanged(self) -> None:
        source = load_document()
        source_bytes = serialize_pmx(source)

        result = apply_set_model_info(
            source,
            SetModelInfo(local_comments="Updated comment"),
        )

        self.assertEqual(serialize_pmx(source), source_bytes)
        self.assertEqual(source.model_info.local_comments, "")
        self.assertIs(result.document.header, source.header)
        self.assertIs(result.document.geometry, source.geometry)
        self.assertIs(result.document.texture_paths, source.texture_paths)
        self.assertIs(result.document.materials, source.materials)
        self.assertIs(result.document.bones, source.bones)
        self.assertIs(result.document.morphs, source.morphs)
        self.assertIs(result.document.display_frames, source.display_frames)
        self.assertIs(result.document.rigid_bodies, source.rigid_bodies)
        self.assertIs(result.document.joints, source.joints)
        self.assertIs(result.document.soft_bodies, source.soft_bodies)
        self.assertIs(result.document.trailing_data, source.trailing_data)

    def test_utf8_unicode_edit_roundtrips_semantically(self) -> None:
        source = load_document(encoding_flag=1)
        result = apply_set_model_info(
            source,
            SetModelInfo(
                local_name="初音ミク ✨",
                universal_comments="Unicode ✓",
            ),
        )

        reparsed = load_pmx(io.BytesIO(serialize_pmx(result.document)))

        self.assertEqual(reparsed, result.document)
        self.assertEqual(reparsed.header.encoding, "utf-8")

    def test_utf16_unicode_edit_roundtrips_semantically(self) -> None:
        source = load_document(encoding_flag=0)
        result = apply_set_model_info(
            source,
            SetModelInfo(
                local_name="初音ミク 🌸",
                local_comments="UTF-16LE を保持",
            ),
        )

        reparsed = load_pmx(io.BytesIO(serialize_pmx(result.document)))

        self.assertEqual(reparsed, result.document)
        self.assertEqual(reparsed.header.encoding, "utf-16-le")

    def test_unencodable_text_has_operation_and_field_context(self) -> None:
        for encoding_flag in (0, 1):
            with self.subTest(encoding_flag=encoding_flag):
                source = load_document(encoding_flag=encoding_flag)

                with self.assertRaisesRegex(
                    PmxEditPlanError,
                    r"operations\[2\]\.local_name.*cannot be encoded",
                ) as context:
                    apply_set_model_info(
                        source,
                        SetModelInfo(local_name="\ud800"),
                        operation_index=2,
                    )

                self.assertEqual(context.exception.operation_index, 2)
                self.assertEqual(context.exception.field, "local_name")
                self.assertEqual(source.model_info.local_name, "Test PMX Model")

    def test_complete_document_validation_is_reused(self) -> None:
        source = load_document()
        invalid_geometry = replace(
            source.geometry,
            surface_indices=(len(source.vertices), 0, 0),
        )
        invalid_source = replace(source, geometry=invalid_geometry)

        with self.assertRaisesRegex(
            PmxValidationError,
            r"surface_indices\[0\].*index 1 is invalid",
        ):
            apply_set_model_info(
                invalid_source,
                SetModelInfo(local_name="Changed"),
            )

    def test_rejects_wrong_argument_types_and_operation_index(self) -> None:
        source = load_document()
        operation = SetModelInfo(local_name="Changed")

        with self.assertRaisesRegex(TypeError, "PmxDocument"):
            apply_set_model_info(object(), operation)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "SetModelInfo"):
            apply_set_model_info(
                source,
                SetTexturePath(  # type: ignore[arg-type]
                    texture_index=0,
                    path="changed.png",
                ),
            )
        for invalid_index in (True, 1.0, "1"):
            with self.subTest(invalid_index=invalid_index):
                with self.assertRaisesRegex(TypeError, "operation_index"):
                    apply_set_model_info(  # type: ignore[arg-type]
                        source,
                        operation,
                        operation_index=invalid_index,
                    )
        with self.assertRaisesRegex(ValueError, "cannot be negative"):
            apply_set_model_info(source, operation, operation_index=-1)

    def test_result_record_is_immutable_and_strictly_typed(self) -> None:
        source = load_document()
        result = apply_set_model_info(
            source,
            SetModelInfo(local_name="Changed"),
        )

        with self.assertRaises(FrozenInstanceError):
            result.document = source  # type: ignore[misc]
        with self.assertRaisesRegex(TypeError, "PmxDocument"):
            PmxEditResult(  # type: ignore[arg-type]
                document=object(),
                audit=result.audit,
            )
        with self.assertRaisesRegex(TypeError, "PmxEditAudit"):
            PmxEditResult(document=source, audit=object())  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
