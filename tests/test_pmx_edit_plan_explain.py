"""Tests for pure deterministic PMX edit-plan explanations."""

from __future__ import annotations

import json
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import patch

from mmd_registry.pmx.editing.errors import PmxEditPlanError
from mmd_registry.pmx.editing.explain import (
    PmxEditOperationExplanation,
    explain_pmx_edit_plan,
    render_pmx_edit_plan_explanation_json,
    render_pmx_edit_plan_explanation_text,
)
from mmd_registry.pmx.editing.operations import (
    SetModelInfo,
    SetTexturePath,
    UpdateMaterial,
)
from mmd_registry.pmx.editing.plan import PmxEditPlan


class PmxEditPlanExplanationTests(unittest.TestCase):
    """Lock explain ordering, targets, field intent, and pure behavior."""

    def test_model_info_target_and_fields_follow_operation_order(self) -> None:
        plan = PmxEditPlan(
            operations=(
                SetModelInfo(
                    local_name="モデル名",
                    universal_comments="authoring note",
                ),
            ),
        )

        explanation = explain_pmx_edit_plan(plan)
        operation = explanation.operations[0]

        self.assertEqual(operation.index, 0)
        self.assertEqual(operation.operation_type, "set_model_info")
        self.assertEqual(operation.target, "model")
        self.assertEqual(
            operation.fields,
            ("local_name", "universal_comments"),
        )

    def test_texture_target_identity_comes_from_selector(self) -> None:
        plan = PmxEditPlan(
            operations=(
                SetTexturePath(
                    texture_index=2,
                    path="textures/body.png",
                ),
            ),
        )

        operation = explain_pmx_edit_plan(plan).operations[0]

        self.assertEqual(operation.target, "texture[2]")
        self.assertEqual(operation.fields, ("path",))

    def test_material_target_and_fields_preserve_catalog_order(self) -> None:
        plan = PmxEditPlan(
            operations=(
                UpdateMaterial(
                    material_index=4,
                    diffuse=(1.0, 0.5, 0.25, 1.0),
                    edge_scale=1.25,
                    memo="説明",
                ),
            ),
        )

        operation = explain_pmx_edit_plan(plan).operations[0]

        self.assertEqual(operation.target, "material[4]")
        self.assertEqual(
            operation.fields,
            ("memo", "diffuse", "edge_scale"),
        )

    def test_operation_indexes_and_order_match_the_plan(self) -> None:
        plan = PmxEditPlan(
            operations=(
                SetModelInfo(local_name="A"),
                SetTexturePath(texture_index=1, path="textures/a.png"),
                UpdateMaterial(material_index=3, edge_scale=2.0),
            ),
        )

        explanation = explain_pmx_edit_plan(plan)

        self.assertEqual(
            tuple(operation.index for operation in explanation.operations),
            (0, 1, 2),
        )
        self.assertEqual(
            tuple(
                operation.operation_type
                for operation in explanation.operations
            ),
            (
                "set_model_info",
                "set_texture_path",
                "update_material",
            ),
        )

    def test_expected_source_hash_is_reported_only_as_presence(self) -> None:
        digest = "a" * 64
        plan = PmxEditPlan(
            operations=(SetModelInfo(local_name="A"),),
            expected_source_sha256=digest,
        )

        explanation = explain_pmx_edit_plan(plan)
        text = render_pmx_edit_plan_explanation_text(explanation)
        json_text = render_pmx_edit_plan_explanation_json(explanation)

        self.assertTrue(explanation.expected_source_sha256)
        self.assertIn("Expected source SHA-256: present", text)
        self.assertNotIn(digest, text)
        self.assertNotIn(digest, json_text)

    def test_explain_output_contains_no_intended_values_or_absolute_paths(self) -> None:
        secret_windows_path = r"C:\Users\Alice\private\texture.png"
        secret_posix_text = "/home/alice/private/model-note"
        plan = PmxEditPlan(
            operations=(
                SetModelInfo(local_comments=secret_posix_text),
                SetTexturePath(
                    texture_index=7,
                    path=secret_windows_path,
                ),
                UpdateMaterial(
                    material_index=2,
                    memo="private-material-value",
                ),
            ),
        )

        explanation = explain_pmx_edit_plan(plan)
        text = render_pmx_edit_plan_explanation_text(explanation)
        json_text = render_pmx_edit_plan_explanation_json(explanation)

        for sensitive_value in (
            secret_windows_path,
            secret_posix_text,
            "private-material-value",
        ):
            self.assertNotIn(sensitive_value, text)
            self.assertNotIn(sensitive_value, json_text)

        self.assertIn("texture[7]", text)
        self.assertIn("local_comments", text)
        self.assertIn("memo", text)

    def test_text_renderer_is_deterministic_and_does_not_claim_results(self) -> None:
        plan = PmxEditPlan(
            operations=(
                SetModelInfo(local_name="A"),
                UpdateMaterial(material_index=1, edge_scale=1.0),
            ),
        )
        explanation = explain_pmx_edit_plan(plan)

        first = render_pmx_edit_plan_explanation_text(explanation)
        second = render_pmx_edit_plan_explanation_text(
            explain_pmx_edit_plan(plan)
        )

        self.assertEqual(first, second)
        self.assertTrue(first.endswith("\n"))
        self.assertIn("Execution: not performed", first)
        self.assertNotIn("before", first.lower())
        self.assertNotIn("after", first.lower())
        self.assertNotIn("verification: passed", first.lower())

    def test_json_renderer_is_deterministic_and_has_stable_shape(self) -> None:
        plan = PmxEditPlan(
            operations=(
                SetTexturePath(texture_index=5, path="textures/a.png"),
            ),
        )
        explanation = explain_pmx_edit_plan(plan)

        first = render_pmx_edit_plan_explanation_json(explanation)
        second = render_pmx_edit_plan_explanation_json(
            explain_pmx_edit_plan(plan)
        )
        payload = json.loads(first)

        self.assertEqual(first, second)
        self.assertTrue(first.endswith("\n"))
        self.assertEqual(
            tuple(payload),
            (
                "status",
                "schema_version",
                "expected_source_sha256",
                "operation_count",
                "operations",
            ),
        )
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["operation_count"], 1)
        self.assertEqual(
            tuple(payload["operations"][0]),
            ("index", "type", "target", "fields"),
        )
        self.assertNotIn("object at", first)

    def test_compact_json_renderer_is_deterministic(self) -> None:
        explanation = explain_pmx_edit_plan(
            PmxEditPlan(
                operations=(SetModelInfo(local_name="A"),),
            )
        )

        first = render_pmx_edit_plan_explanation_json(
            explanation,
            indent=None,
        )
        second = render_pmx_edit_plan_explanation_json(
            explanation,
            indent=None,
        )

        self.assertEqual(first, second)
        self.assertTrue(first.endswith("\n"))

    def test_explain_does_not_mutate_plan(self) -> None:
        plan = PmxEditPlan(
            operations=(
                SetModelInfo(local_name="A"),
                UpdateMaterial(material_index=0, memo="B"),
            ),
        )
        before = plan.to_dict()

        explain_pmx_edit_plan(plan)

        self.assertEqual(plan.to_dict(), before)

    def test_explain_reuses_plan_validation(self) -> None:
        plan = PmxEditPlan(
            operations=(
                SetModelInfo(local_name="A"),
                SetModelInfo(local_name="B"),
            ),
        )

        with self.assertRaises(PmxEditPlanError):
            explain_pmx_edit_plan(plan)

    def test_explain_does_not_load_apply_serialize_or_dry_run_pmx(self) -> None:
        plan = PmxEditPlan(
            operations=(
                SetTexturePath(texture_index=0, path="textures/a.png"),
            ),
        )

        with (
            patch(
                "mmd_registry.pmx.load_pmx",
                side_effect=AssertionError("load_pmx must not be called"),
            ),
            patch(
                "mmd_registry.pmx.serialize_pmx",
                side_effect=AssertionError("serialize_pmx must not be called"),
            ),
            patch(
                "mmd_registry.pmx.editing.engine.apply_pmx_edit_plan",
                side_effect=AssertionError(
                    "apply_pmx_edit_plan must not be called"
                ),
            ),
            patch(
                "mmd_registry.pmx.editing.preview.dry_run_pmx_edit",
                side_effect=AssertionError(
                    "dry_run_pmx_edit must not be called"
                ),
            ),
        ):
            explanation = explain_pmx_edit_plan(plan)

        self.assertEqual(explanation.operations[0].target, "texture[0]")

    def test_explanation_models_are_immutable(self) -> None:
        explanation = explain_pmx_edit_plan(
            PmxEditPlan(
                operations=(SetModelInfo(local_name="A"),),
            )
        )

        with self.assertRaises(FrozenInstanceError):
            explanation.schema_version = 2  # type: ignore[misc]

        operation = explanation.operations[0]
        with self.assertRaises(FrozenInstanceError):
            operation.target = "changed"  # type: ignore[misc]

    def test_renderers_reject_invalid_types_and_indent_without_coercion(self) -> None:
        explanation = explain_pmx_edit_plan(
            PmxEditPlan(
                operations=(SetModelInfo(local_name="A"),),
            )
        )

        with self.assertRaises(TypeError):
            explain_pmx_edit_plan(object())  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            render_pmx_edit_plan_explanation_text(
                object()  # type: ignore[arg-type]
            )
        with self.assertRaises(TypeError):
            render_pmx_edit_plan_explanation_json(
                object()  # type: ignore[arg-type]
            )
        with self.assertRaises(TypeError):
            render_pmx_edit_plan_explanation_json(
                explanation,
                indent=True,  # type: ignore[arg-type]
            )
        with self.assertRaises(ValueError):
            render_pmx_edit_plan_explanation_json(
                explanation,
                indent=-1,
            )

    def test_operation_explanation_requires_nonempty_intended_fields(self) -> None:
        with self.assertRaises(ValueError):
            PmxEditOperationExplanation(
                index=0,
                operation_type="set_model_info",
                target="model",
                fields=(),
            )


if __name__ == "__main__":
    unittest.main()
