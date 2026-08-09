"""Generated end-to-end tests for complete PMX editing and previews."""

from __future__ import annotations

import hashlib
import io
import json
import unittest
from dataclasses import replace
from unittest.mock import patch

from mmd_registry.pmx import (
    PmxValidationError,
    load_pmx,
    serialize_pmx,
    validate_pmx_document,
)
from mmd_registry.pmx.editing import (
    PMX_EDIT_PREVIEW_SCHEMA_VERSION,
    PmxEditAudit,
    PmxEditPlan,
    PmxEditPlanError,
    PmxEditVerificationError,
    SetModelInfo,
    SetTexturePath,
    UpdateMaterial,
    apply_pmx_edit_plan,
    calculate_pmx_edit_plan_sha256,
    dry_run_pmx_edit,
    render_pmx_edit_preview_json,
    render_pmx_edit_preview_text,
)
from tests.mmd_fixtures import (
    build_pmx_bone,
    build_pmx_material,
    build_pmx_structure,
)


def build_source_bytes(*, encoding_flag: int = 1) -> bytes:
    """Build one complete PMX with two material partitions."""

    materials = (
        build_pmx_material(
            local_name="Body",
            universal_name="Body EN",
            texture_index=0,
            sphere_texture_index=1,
            sphere_mode=2,
            toon_reference_mode=0,
            toon_reference_index=2,
            memo="Body memo",
            surface_index_count=3,
            encoding_flag=encoding_flag,
        ),
        build_pmx_material(
            local_name="Face",
            universal_name="Face EN",
            texture_index=1,
            sphere_texture_index=-1,
            sphere_mode=0,
            toon_reference_mode=1,
            toon_reference_index=4,
            memo="Face memo",
            surface_index_count=3,
            encoding_flag=encoding_flag,
        ),
    )
    return build_pmx_structure(
        encoding_flag=encoding_flag,
        surface_indices=(0, 0, 0, 0, 0, 0),
        texture_paths=(
            "textures/body.png",
            "textures/sphere.spa",
            "textures/toon.bmp",
        ),
        materials=materials,
        bones=(build_pmx_bone(encoding_flag=encoding_flag),),
    )


def build_complete_plan(
    *,
    expected_source_sha256: str | None = None,
) -> PmxEditPlan:
    """Build one mixed-operation plan with seven effective changes."""

    return PmxEditPlan(
        operations=(
            SetModelInfo(
                local_name="モデル 🌸",
                universal_comments="Verified preview",
            ),
            SetTexturePath(
                texture_index=0,
                path="textures/顔.png",
            ),
            UpdateMaterial(
                material_index=0,
                memo="Reviewed safely",
                texture_index=2,
            ),
            UpdateMaterial(
                material_index=1,
                diffuse=(0.1, 0.2, 0.3, 0.4),
                drawing_flags=0x1F,
            ),
        ),
        expected_source_sha256=expected_source_sha256,
    )


class CompletePmxEditEngineTests(unittest.TestCase):
    """Validate atomic plan application and deterministic audit merging."""

    def test_applies_mixed_plan_and_merges_audit_in_operation_order(self) -> None:
        source_bytes = build_source_bytes()
        source = load_pmx(io.BytesIO(source_bytes))
        source_snapshot = source
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()
        plan = build_complete_plan(expected_source_sha256=source_sha256)

        result = apply_pmx_edit_plan(
            source,
            plan,
            source_sha256=source_sha256,
        )

        self.assertEqual(source, source_snapshot)
        self.assertEqual(source.model_info.local_name, "Test PMX Model")
        self.assertEqual(result.document.model_info.local_name, "モデル 🌸")
        self.assertEqual(result.document.texture_paths[0], "textures/顔.png")
        self.assertEqual(result.document.materials[0].memo, "Reviewed safely")
        self.assertEqual(result.document.materials[0].texture_index, 2)
        self.assertEqual(result.document.materials[1].drawing_flags, 0x1F)
        self.assertEqual(
            tuple(change.operation_index for change in result.audit.changes),
            (0, 0, 1, 2, 2, 3, 3),
        )
        self.assertEqual(
            tuple(change.field_path for change in result.audit.changes),
            (
                "model_info.local_name",
                "model_info.universal_comments",
                "textures[0].path",
                "materials[0].memo",
                "materials[0].texture_index",
                "materials[1].diffuse",
                "materials[1].drawing_flags",
            ),
        )
        self.assertEqual(result.audit.category_count("model"), 2)
        self.assertEqual(result.audit.category_count("texture"), 1)
        self.assertEqual(result.audit.category_count("material"), 4)
        validate_pmx_document(result.document)

    def test_noop_plan_returns_original_document_and_empty_audit(self) -> None:
        source = load_pmx(io.BytesIO(build_source_bytes()))
        plan = PmxEditPlan(
            operations=(
                SetModelInfo(local_name=source.model_info.local_name),
                SetTexturePath(
                    texture_index=0,
                    path=source.texture_paths[0],
                ),
                UpdateMaterial(
                    material_index=0,
                    memo=source.materials[0].memo,
                ),
            )
        )

        result = apply_pmx_edit_plan(source, plan)

        self.assertIs(result.document, source)
        self.assertEqual(result.audit, PmxEditAudit())

    def test_expected_source_hash_is_required_and_must_match(self) -> None:
        source = load_pmx(io.BytesIO(build_source_bytes()))
        expected = "a" * 64
        plan = PmxEditPlan(
            operations=(SetModelInfo(local_name="Changed"),),
            expected_source_sha256=expected,
        )

        with self.assertRaisesRegex(
            PmxEditPlanError,
            r"edit plan\.expected_source_sha256.*required",
        ):
            apply_pmx_edit_plan(source, plan)

        with self.assertRaisesRegex(
            PmxEditPlanError,
            r"edit plan\.expected_source_sha256.*mismatch.*received",
        ):
            apply_pmx_edit_plan(
                source,
                plan,
                source_sha256="b" * 64,
            )

    def test_actual_source_hash_argument_is_strict_when_provided(self) -> None:
        source = load_pmx(io.BytesIO(build_source_bytes()))
        plan = PmxEditPlan(
            operations=(SetModelInfo(local_name="Changed"),)
        )

        with self.assertRaisesRegex(TypeError, "source_sha256"):
            apply_pmx_edit_plan(
                source,
                plan,
                source_sha256=1,  # type: ignore[arg-type]
            )
        with self.assertRaisesRegex(ValueError, "64 lowercase"):
            apply_pmx_edit_plan(source, plan, source_sha256="A" * 64)

    def test_late_operation_failure_leaves_source_unchanged(self) -> None:
        source = load_pmx(io.BytesIO(build_source_bytes()))
        source_snapshot = source
        source_serialized = serialize_pmx(source)
        plan = PmxEditPlan(
            operations=(
                SetModelInfo(local_name="Would have changed"),
                SetTexturePath(texture_index=99, path="textures/missing.png"),
            )
        )

        with self.assertRaisesRegex(
            PmxEditPlanError,
            r"operations\[1\]\.texture_index.*out of range",
        ):
            apply_pmx_edit_plan(source, plan)

        self.assertEqual(source, source_snapshot)
        self.assertEqual(serialize_pmx(source), source_serialized)
        self.assertEqual(source.model_info.local_name, "Test PMX Model")

    def test_duplicate_targets_are_rejected_before_any_operation(self) -> None:
        source = load_pmx(io.BytesIO(build_source_bytes()))
        plan = PmxEditPlan(
            operations=(
                SetModelInfo(local_name="First"),
                SetModelInfo(local_name="Second"),
            )
        )

        with self.assertRaisesRegex(PmxEditPlanError, "duplicate write"):
            apply_pmx_edit_plan(source, plan)

        self.assertEqual(source.model_info.local_name, "Test PMX Model")

    def test_invalid_source_document_is_rejected_before_editing(self) -> None:
        source = load_pmx(io.BytesIO(build_source_bytes()))
        invalid_geometry = replace(
            source.geometry,
            surface_indices=(2, *source.surface_indices[1:]),
        )
        invalid_source = replace(source, geometry=invalid_geometry)
        plan = PmxEditPlan(
            operations=(SetModelInfo(local_name="Changed"),)
        )

        with self.assertRaisesRegex(PmxValidationError, "surface_indices"):
            apply_pmx_edit_plan(invalid_source, plan)

    def test_complete_engine_rejects_wrong_public_argument_types(self) -> None:
        source = load_pmx(io.BytesIO(build_source_bytes()))
        plan = PmxEditPlan(
            operations=(SetModelInfo(local_name="Changed"),)
        )

        with self.assertRaisesRegex(TypeError, "PmxDocument"):
            apply_pmx_edit_plan(object(), plan)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "PmxEditPlan"):
            apply_pmx_edit_plan(source, object())  # type: ignore[arg-type]


class PmxEditPreviewTests(unittest.TestCase):
    """Validate in-memory verification and stable text/JSON reports."""

    def test_dry_run_verifies_generated_pmx_without_writing_output(self) -> None:
        source_bytes = build_source_bytes()
        source_snapshot = bytes(source_bytes)
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()
        plan = build_complete_plan(expected_source_sha256=source_sha256)

        preview = dry_run_pmx_edit(source_bytes, plan)
        report = preview.to_dict()

        self.assertEqual(source_bytes, source_snapshot)
        self.assertEqual(preview.source_sha256, source_sha256)
        self.assertEqual(preview.source_size_bytes, len(source_bytes))
        self.assertEqual(preview.audit.changed_fields, 7)
        self.assertEqual(preview.status, "changes_pending")
        self.assertEqual(preview.document.model_info.local_name, "モデル 🌸")
        self.assertEqual(
            load_pmx(io.BytesIO(serialize_pmx(preview.document))),
            preview.document,
        )
        self.assertEqual(report["preview_schema_version"], 1)
        self.assertTrue(report["dry_run"])
        self.assertEqual(report["status"], "changes_pending")
        self.assertEqual(
            report["output"],
            {"written": False, "sha256": None},
        )
        self.assertEqual(
            report["verification"],
            {"semantic": "passed", "input_unchanged": True},
        )

    def test_dry_run_supports_utf8_and_utf16le_generated_documents(self) -> None:
        for encoding_flag in (0, 1):
            with self.subTest(encoding_flag=encoding_flag):
                source_bytes = build_source_bytes(encoding_flag=encoding_flag)
                source_sha256 = hashlib.sha256(source_bytes).hexdigest()
                preview = dry_run_pmx_edit(
                    source_bytes,
                    build_complete_plan(
                        expected_source_sha256=source_sha256,
                    ),
                )

                self.assertEqual(
                    preview.document.model_info.local_name,
                    "モデル 🌸",
                )
                self.assertEqual(preview.audit.changed_fields, 7)

    def test_dry_run_noop_has_explicit_no_changes_contract(self) -> None:
        source_bytes = build_source_bytes()
        source = load_pmx(io.BytesIO(source_bytes))
        plan = PmxEditPlan(
            operations=(
                SetModelInfo(local_name=source.model_info.local_name),
            )
        )

        preview = dry_run_pmx_edit(source_bytes, plan)
        report = preview.to_dict()
        text = render_pmx_edit_preview_text(preview)

        self.assertEqual(preview.status, "no_changes")
        self.assertEqual(preview.audit, PmxEditAudit())
        self.assertEqual(report["status"], "no_changes")
        self.assertEqual(
            report["audit"]["summary"]["changed_fields"],  # type: ignore[index]
            0,
        )
        self.assertIn("Status: no changes", text)
        self.assertNotIn("Changes:", text)

    def test_dry_run_rejects_source_hash_mismatch_before_changes(self) -> None:
        source_bytes = build_source_bytes()
        plan = build_complete_plan(expected_source_sha256="0" * 64)

        with self.assertRaisesRegex(
            PmxEditPlanError,
            r"expected_source_sha256.*mismatch",
        ):
            dry_run_pmx_edit(source_bytes, plan)

    def test_semantic_reparse_mismatch_raises_verification_error(self) -> None:
        source_bytes = build_source_bytes()
        source_document = load_pmx(io.BytesIO(source_bytes))
        plan = PmxEditPlan(
            operations=(SetModelInfo(local_name="Changed"),)
        )

        with patch(
            "mmd_registry.pmx.editing.preview.load_pmx",
            return_value=source_document,
        ):
            with self.assertRaisesRegex(
                PmxEditVerificationError,
                "does not match the intended edited document",
            ):
                dry_run_pmx_edit(source_bytes, plan)

    def test_plan_hash_uses_stable_canonical_unicode_json(self) -> None:
        plan = PmxEditPlan(
            operations=(SetModelInfo(local_name="モデル 🌸"),)
        )
        canonical = json.dumps(
            plan.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        expected = hashlib.sha256(canonical).hexdigest()

        self.assertEqual(calculate_pmx_edit_plan_sha256(plan), expected)
        self.assertEqual(
            calculate_pmx_edit_plan_sha256(plan),
            calculate_pmx_edit_plan_sha256(plan),
        )
        with self.assertRaisesRegex(TypeError, "PmxEditPlan"):
            calculate_pmx_edit_plan_sha256(object())  # type: ignore[arg-type]

    def test_text_preview_is_deterministic_compact_and_unicode_safe(self) -> None:
        source_bytes = build_source_bytes()
        preview = dry_run_pmx_edit(source_bytes, build_complete_plan())

        first = render_pmx_edit_preview_text(preview)
        second = render_pmx_edit_preview_text(preview)
        summary_only = render_pmx_edit_preview_text(
            preview,
            include_changes=False,
        )

        self.assertEqual(first, second)
        self.assertTrue(first.startswith("PMX EDIT PREVIEW\n"))
        self.assertIn("Status: 7 fields changed", first)
        self.assertIn("Model: 2 fields changed", first)
        self.assertIn("Textures: 1 path changed", first)
        self.assertIn("Materials: 4 fields changed", first)
        self.assertIn("Output written: no (dry-run)", first)
        self.assertIn(
            '- model_info.local_name: "Test PMX Model" -> "モデル 🌸"',
            first,
        )
        self.assertNotIn("Changes:", summary_only)

    def test_json_preview_is_stable_unicode_safe_and_gui_friendly(self) -> None:
        preview = dry_run_pmx_edit(
            build_source_bytes(),
            build_complete_plan(),
        )

        first = render_pmx_edit_preview_json(preview)
        second = render_pmx_edit_preview_json(preview)
        compact = render_pmx_edit_preview_json(preview, indent=None)

        self.assertEqual(first, second)
        self.assertTrue(first.endswith("\n"))
        self.assertIn("モデル 🌸", first)
        self.assertNotIn("\\u30e2", first)
        self.assertEqual(json.loads(first), preview.to_dict())
        self.assertEqual(json.loads(compact), preview.to_dict())
        self.assertEqual(
            preview.to_dict()["preview_schema_version"],
            PMX_EDIT_PREVIEW_SCHEMA_VERSION,
        )

    def test_preview_apis_reject_wrong_argument_types(self) -> None:
        plan = PmxEditPlan(
            operations=(SetModelInfo(local_name="Changed"),)
        )
        preview = dry_run_pmx_edit(build_source_bytes(), plan)

        with self.assertRaisesRegex(TypeError, "source_bytes"):
            dry_run_pmx_edit(  # type: ignore[arg-type]
                bytearray(build_source_bytes()),
                plan,
            )
        with self.assertRaisesRegex(TypeError, "PmxEditPlan"):
            dry_run_pmx_edit(build_source_bytes(), object())  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "PmxEditPreview"):
            render_pmx_edit_preview_text(object())  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "include_changes"):
            render_pmx_edit_preview_text(
                preview,
                include_changes=1,  # type: ignore[arg-type]
            )
        with self.assertRaisesRegex(TypeError, "indent"):
            render_pmx_edit_preview_json(preview, indent=True)
        with self.assertRaisesRegex(ValueError, "cannot be negative"):
            render_pmx_edit_preview_json(preview, indent=-1)


if __name__ == "__main__":
    unittest.main()
