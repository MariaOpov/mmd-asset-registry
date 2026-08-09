"""Tests for immutable declarative PMX editing foundations."""

from __future__ import annotations

import math
import unittest
from dataclasses import FrozenInstanceError

from mmd_registry.pmx.editing import (
    PMX_EDIT_PLAN_SCHEMA_VERSION,
    PmxEditAudit,
    PmxEditChange,
    PmxEditPlan,
    PmxEditPlanError,
    SetModelInfo,
    SetTexturePath,
    UpdateMaterial,
    validate_pmx_edit_plan,
)


class EditOperationTests(unittest.TestCase):
    """Validate strict immutable operation records."""

    def test_model_info_operation_is_immutable_and_stable(self) -> None:
        operation = SetModelInfo(
            local_name="モデル",
            universal_comments="Safe edit",
        )

        with self.assertRaises(FrozenInstanceError):
            operation.local_name = "changed"  # type: ignore[misc]

        self.assertEqual(
            operation.to_dict(),
            {
                "op": "set_model_info",
                "local_name": "モデル",
                "universal_comments": "Safe edit",
            },
        )

    def test_model_info_rejects_empty_or_wrong_typed_payload(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one field"):
            SetModelInfo()
        with self.assertRaisesRegex(TypeError, "local_name must be a string"):
            SetModelInfo(local_name=1)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            SetModelInfo(display_name="unsupported")  # type: ignore[call-arg]

    def test_texture_path_operation_is_immutable_and_stable(self) -> None:
        operation = SetTexturePath(
            texture_index=2,
            path="textures/顔.png",
        )

        with self.assertRaises(FrozenInstanceError):
            operation.path = "changed.png"  # type: ignore[misc]

        self.assertEqual(
            operation.to_dict(),
            {
                "op": "set_texture_path",
                "texture_index": 2,
                "path": "textures/顔.png",
            },
        )

    def test_texture_path_rejects_invalid_index_and_path_types(self) -> None:
        for invalid_index in (True, -1, 1.0, "1"):
            with self.subTest(invalid_index=invalid_index):
                with self.assertRaises((TypeError, ValueError)):
                    SetTexturePath(  # type: ignore[arg-type]
                        texture_index=invalid_index,
                        path="texture.png",
                    )

        with self.assertRaisesRegex(TypeError, "path must be a string"):
            SetTexturePath(texture_index=0, path=PathLike())  # type: ignore[arg-type]

    def test_material_operation_preserves_stable_field_order(self) -> None:
        operation = UpdateMaterial(
            material_index=1,
            local_name="Body",
            memo="Reviewed",
            texture_index=0,
            sphere_mode=2,
            toon_reference_mode="shared",
            toon_reference_index=4,
            diffuse=(1.0, 0.5, 0.25, 1.0),
            specular_strength=0.75,
            drawing_flags=0x1F,
            edge_scale=1.25,
        )

        self.assertEqual(
            operation.to_dict(),
            {
                "op": "update_material",
                "material_index": 1,
                "local_name": "Body",
                "memo": "Reviewed",
                "texture_index": 0,
                "sphere_mode": 2,
                "toon_reference_mode": "shared",
                "toon_reference_index": 4,
                "diffuse": [1.0, 0.5, 0.25, 1.0],
                "specular_strength": 0.75,
                "drawing_flags": 31,
                "edge_scale": 1.25,
            },
        )

    def test_material_operation_rejects_empty_payload(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one field"):
            UpdateMaterial(material_index=0)

    def test_material_operation_rejects_invalid_indices_and_booleans(self) -> None:
        with self.assertRaisesRegex(TypeError, "material_index"):
            UpdateMaterial(material_index=True, memo="x")  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "cannot be smaller than -1"):
            UpdateMaterial(material_index=0, texture_index=-2)
        with self.assertRaisesRegex(TypeError, "drawing_flags"):
            UpdateMaterial(material_index=0, drawing_flags=True)

    def test_material_operation_rejects_invalid_modes(self) -> None:
        with self.assertRaisesRegex(ValueError, "sphere_mode"):
            UpdateMaterial(material_index=0, sphere_mode=4)
        with self.assertRaisesRegex(ValueError, "toon_reference_mode"):
            UpdateMaterial(
                material_index=0,
                toon_reference_mode="automatic",  # type: ignore[arg-type]
            )
        with self.assertRaisesRegex(ValueError, "shared toon_reference_index"):
            UpdateMaterial(
                material_index=0,
                toon_reference_mode="shared",
                toon_reference_index=10,
            )

    def test_material_operation_rejects_invalid_vectors(self) -> None:
        with self.assertRaisesRegex(TypeError, "diffuse must be a tuple"):
            UpdateMaterial(  # type: ignore[arg-type]
                material_index=0,
                diffuse=[1.0, 1.0, 1.0, 1.0],
            )
        with self.assertRaisesRegex(ValueError, "exactly 4"):
            UpdateMaterial(
                material_index=0,
                diffuse=(1.0, 1.0, 1.0),  # type: ignore[arg-type]
            )
        with self.assertRaisesRegex(TypeError, "diffuse value must be a float"):
            UpdateMaterial(
                material_index=0,
                diffuse=(1.0, 1.0, 1.0, 1),  # type: ignore[arg-type]
            )
        with self.assertRaisesRegex(ValueError, "specular_strength must be finite"):
            UpdateMaterial(material_index=0, specular_strength=math.inf)


class PathLike:
    """Non-string sentinel used to verify that paths are not coerced."""

    def __str__(self) -> str:
        return "texture.png"


class EditPlanTests(unittest.TestCase):
    """Validate immutable plans and cross-operation conflict detection."""

    def test_plan_is_immutable_and_has_schema_one(self) -> None:
        plan = PmxEditPlan(operations=(SetModelInfo(local_name="Model"),))

        self.assertEqual(plan.schema_version, PMX_EDIT_PLAN_SCHEMA_VERSION)
        with self.assertRaises(FrozenInstanceError):
            plan.schema_version = 2  # type: ignore[misc]

    def test_plan_requires_nonempty_tuple_of_supported_operations(self) -> None:
        with self.assertRaisesRegex(TypeError, "operations must be a tuple"):
            PmxEditPlan(operations=[])  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "at least one operation"):
            PmxEditPlan(operations=())
        with self.assertRaisesRegex(TypeError, "unsupported operation"):
            PmxEditPlan(operations=(object(),))  # type: ignore[arg-type]

    def test_plan_rejects_bool_or_unsupported_schema_version(self) -> None:
        operation = SetModelInfo(local_name="Model")
        with self.assertRaisesRegex(TypeError, "schema_version"):
            PmxEditPlan(operations=(operation,), schema_version=True)
        with self.assertRaisesRegex(ValueError, "Unsupported.*schema version 2"):
            PmxEditPlan(operations=(operation,), schema_version=2)

    def test_plan_rejects_invalid_expected_source_hash(self) -> None:
        operation = SetModelInfo(local_name="Model")
        for invalid_hash in (
            123,
            "a" * 63,
            "A" * 64,
            "g" * 64,
        ):
            with self.subTest(invalid_hash=invalid_hash):
                with self.assertRaises((TypeError, ValueError)):
                    PmxEditPlan(  # type: ignore[arg-type]
                        operations=(operation,),
                        expected_source_sha256=invalid_hash,
                    )

    def test_plan_representation_is_stable_and_unicode_safe(self) -> None:
        source_hash = "a" * 64
        plan = PmxEditPlan(
            operations=(
                SetModelInfo(local_name="モデル"),
                SetTexturePath(texture_index=0, path="textures/顔.png"),
            ),
            expected_source_sha256=source_hash,
        )

        self.assertEqual(
            plan.to_dict(),
            {
                "schema_version": 1,
                "expected_source_sha256": source_hash,
                "operations": [
                    {"op": "set_model_info", "local_name": "モデル"},
                    {
                        "op": "set_texture_path",
                        "texture_index": 0,
                        "path": "textures/顔.png",
                    },
                ],
            },
        )
        self.assertEqual(plan.to_dict(), plan.to_dict())

    def test_validation_rejects_duplicate_model_field(self) -> None:
        plan = PmxEditPlan(
            operations=(
                SetModelInfo(local_name="First"),
                SetModelInfo(local_name="Second"),
            )
        )

        with self.assertRaisesRegex(
            PmxEditPlanError,
            r"operations\[1\]\.local_name.*model_info\.local_name.*"
            r"operations\[0\]\.local_name",
        ):
            validate_pmx_edit_plan(plan)

    def test_validation_rejects_duplicate_indexed_fields(self) -> None:
        cases = (
            (
                SetTexturePath(texture_index=2, path="first.png"),
                SetTexturePath(texture_index=2, path="second.png"),
                r"textures\[2\]\.path",
            ),
            (
                UpdateMaterial(material_index=3, memo="first"),
                UpdateMaterial(material_index=3, memo="second"),
                r"materials\[3\]\.memo",
            ),
        )
        for first, second, target_path in cases:
            with self.subTest(target_path=target_path):
                with self.assertRaisesRegex(PmxEditPlanError, target_path):
                    validate_pmx_edit_plan(
                        PmxEditPlan(operations=(first, second))
                    )

    def test_validation_allows_distinct_fields_and_indices(self) -> None:
        plan = PmxEditPlan(
            operations=(
                SetModelInfo(local_name="Model"),
                SetModelInfo(universal_name="Model EN"),
                SetTexturePath(texture_index=0, path="zero.png"),
                SetTexturePath(texture_index=1, path="one.png"),
                UpdateMaterial(material_index=0, local_name="Body"),
                UpdateMaterial(material_index=0, memo="Reviewed"),
            )
        )

        self.assertIsNone(validate_pmx_edit_plan(plan))

    def test_validation_requires_a_typed_plan(self) -> None:
        with self.assertRaisesRegex(TypeError, "PmxEditPlan"):
            validate_pmx_edit_plan(object())  # type: ignore[arg-type]


class EditAuditTests(unittest.TestCase):
    """Validate stable effective-change records and summaries."""

    def test_change_is_immutable_and_serializes_vectors_as_lists(self) -> None:
        change = PmxEditChange(
            category="material",
            target_index=1,
            target_name="Body",
            field_path="materials[1].diffuse",
            before=(1.0, 1.0, 1.0, 1.0),
            after=(0.5, 0.5, 0.5, 1.0),
            operation_index=2,
        )

        with self.assertRaises(FrozenInstanceError):
            change.after = (0.0, 0.0, 0.0, 0.0)  # type: ignore[misc]

        self.assertEqual(
            change.to_dict(),
            {
                "category": "material",
                "target_index": 1,
                "target_name": "Body",
                "field_path": "materials[1].diffuse",
                "before": [1.0, 1.0, 1.0, 1.0],
                "after": [0.5, 0.5, 0.5, 1.0],
                "operation_index": 2,
            },
        )

    def test_change_rejects_noop_and_bool_values(self) -> None:
        common = {
            "category": "model",
            "target_index": None,
            "target_name": "Model",
            "field_path": "model_info.local_name",
            "operation_index": 0,
        }
        with self.assertRaisesRegex(ValueError, "different values"):
            PmxEditChange(  # type: ignore[arg-type]
                before="same",
                after="same",
                **common,
            )
        with self.assertRaisesRegex(TypeError, "cannot be a boolean"):
            PmxEditChange(before=False, after=1, **common)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "after must be finite"):
            PmxEditChange(  # type: ignore[arg-type]
                before=0.0,
                after=math.nan,
                **common,
            )

    def test_change_requires_category_appropriate_target_index(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot have a target_index"):
            PmxEditChange(
                category="model",
                target_index=0,
                target_name=None,
                field_path="model_info.local_name",
                before="a",
                after="b",
                operation_index=0,
            )
        with self.assertRaisesRegex(TypeError, "target_index"):
            PmxEditChange(
                category="texture",
                target_index=None,
                target_name=None,
                field_path="textures[0].path",
                before="a.png",
                after="b.png",
                operation_index=0,
            )

    def test_audit_counts_categories_and_preserves_order(self) -> None:
        changes = (
            PmxEditChange(
                category="model",
                target_index=None,
                target_name="Old model",
                field_path="model_info.local_name",
                before="Old model",
                after="New model",
                operation_index=0,
            ),
            PmxEditChange(
                category="texture",
                target_index=0,
                target_name=None,
                field_path="textures[0].path",
                before="old.png",
                after="new.png",
                operation_index=1,
            ),
            PmxEditChange(
                category="material",
                target_index=0,
                target_name="Body",
                field_path="materials[0].memo",
                before="",
                after="Reviewed",
                operation_index=2,
            ),
        )
        audit = PmxEditAudit(changes=changes)

        self.assertEqual(audit.changed_fields, 3)
        self.assertEqual(audit.category_count("model"), 1)
        self.assertEqual(audit.category_count("texture"), 1)
        self.assertEqual(audit.category_count("material"), 1)
        audit_payload = audit.to_dict()
        self.assertEqual(
            [
                item["field_path"]
                for item in audit_payload["changes"]  # type: ignore[union-attr]
            ],
            [change.field_path for change in changes],
        )
        self.assertEqual(
            audit_payload["summary"],
            {
                "changed_fields": 3,
                "model_fields": 1,
                "texture_fields": 1,
                "material_fields": 1,
            },
        )

    def test_empty_audit_is_a_stable_noop_summary(self) -> None:
        self.assertEqual(
            PmxEditAudit().to_dict(),
            {
                "summary": {
                    "changed_fields": 0,
                    "model_fields": 0,
                    "texture_fields": 0,
                    "material_fields": 0,
                },
                "changes": [],
            },
        )

    def test_audit_rejects_unstable_order_and_duplicate_paths(self) -> None:
        later = PmxEditChange(
            category="model",
            target_index=None,
            target_name=None,
            field_path="model_info.local_name",
            before="a",
            after="b",
            operation_index=1,
        )
        earlier = PmxEditChange(
            category="model",
            target_index=None,
            target_name=None,
            field_path="model_info.universal_name",
            before="a",
            after="b",
            operation_index=0,
        )
        duplicate = PmxEditChange(
            category="model",
            target_index=None,
            target_name=None,
            field_path="model_info.local_name",
            before="b",
            after="c",
            operation_index=2,
        )

        with self.assertRaisesRegex(ValueError, "nondecreasing"):
            PmxEditAudit(changes=(later, earlier))
        with self.assertRaisesRegex(ValueError, "duplicate field path"):
            PmxEditAudit(changes=(later, duplicate))


if __name__ == "__main__":
    unittest.main()
