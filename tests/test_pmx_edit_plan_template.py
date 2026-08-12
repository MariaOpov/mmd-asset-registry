"""Tests for safe deterministic PMX edit-plan starter templates."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from dataclasses import FrozenInstanceError

from mmd_registry.pmx.editing.catalog import get_pmx_edit_operation_catalog
from mmd_registry.pmx.editing.errors import PmxEditPlanError
from mmd_registry.pmx.editing.json_loader import parse_pmx_edit_plan_json
from mmd_registry.pmx.editing.operations import PmxEditFieldRole
from mmd_registry.pmx.editing.template import (
    PMX_EDIT_PLAN_TEMPLATE_FORMAT_VERSION,
    PMX_EDIT_PLAN_TEMPLATE_MARKER,
    PMX_EDIT_PLAN_TEMPLATE_PLACEHOLDER,
    PmxEditPlanTemplate,
    get_pmx_edit_plan_template,
    render_pmx_edit_plan_template_json,
)


class PmxEditPlanTemplateTests(unittest.TestCase):
    """Lock template determinism, coverage, and fail-closed safety."""

    def setUp(self) -> None:
        self.catalog = get_pmx_edit_operation_catalog()
        self.supported = tuple(
            entry.operation_type for entry in self.catalog.operations
        )

    def test_plan_skeleton_is_marked_non_executable(self) -> None:
        template = get_pmx_edit_plan_template()
        payload = template.to_dict()

        self.assertIsNone(template.operation_type)
        self.assertFalse(template.executable)
        self.assertEqual(
            template.template_format_version,
            PMX_EDIT_PLAN_TEMPLATE_FORMAT_VERSION,
        )
        self.assertEqual(payload["operations"], [])
        self.assertEqual(
            payload[PMX_EDIT_PLAN_TEMPLATE_MARKER]["executable"],
            False,
        )
        self.assertEqual(
            tuple(
                payload[PMX_EDIT_PLAN_TEMPLATE_MARKER][
                    "supported_operation_types"
                ]
            ),
            self.supported,
        )

    def test_operation_specific_templates_cover_supported_operations(self) -> None:
        for operation_type in self.supported:
            with self.subTest(operation=operation_type):
                template = get_pmx_edit_plan_template(operation_type)
                payload = template.to_dict()

                self.assertEqual(template.operation_type, operation_type)
                self.assertEqual(
                    payload["operations"][0]["op"],
                    operation_type,
                )
                self.assertEqual(
                    payload[PMX_EDIT_PLAN_TEMPLATE_MARKER]["operation_type"],
                    operation_type,
                )

    def test_starter_fields_are_derived_from_catalog_roles(self) -> None:
        for entry in self.catalog.operations:
            with self.subTest(operation=entry.operation_type):
                template = get_pmx_edit_plan_template(entry.operation_type)
                self.assertIsNotNone(template.operation)
                starter_fields = template.operation.placeholder_fields

                required_names = {
                    field.name for field in entry.fields if field.required
                }
                self.assertTrue(
                    required_names
                    <= {field.name for field in starter_fields}
                )
                self.assertTrue(
                    any(
                        field.role is PmxEditFieldRole.VALUE
                        for field in starter_fields
                    )
                )

    def test_current_operation_starter_field_order_is_stable(self) -> None:
        expected = {
            "set_model_info": ("local_name",),
            "set_texture_path": ("texture_index", "path"),
            "update_material": ("material_index", "local_name"),
        }

        for operation_type, field_names in expected.items():
            with self.subTest(operation=operation_type):
                template = get_pmx_edit_plan_template(operation_type)
                self.assertEqual(
                    template.operation.placeholder_field_names,
                    field_names,
                )

    def test_placeholders_are_objects_not_legitimate_scalar_values(self) -> None:
        for operation_type in self.supported:
            with self.subTest(operation=operation_type):
                operation = get_pmx_edit_plan_template(
                    operation_type
                ).to_dict()["operations"][0]

                for field_name, value in operation.items():
                    if field_name == "op":
                        continue
                    self.assertIs(type(value), dict)
                    self.assertEqual(
                        tuple(value),
                        (PMX_EDIT_PLAN_TEMPLATE_PLACEHOLDER,),
                    )
                    self.assertIs(
                        type(value[PMX_EDIT_PLAN_TEMPLATE_PLACEHOLDER]),
                        dict,
                    )

    def test_strict_loader_rejects_template_marker_for_every_template(self) -> None:
        templates = [get_pmx_edit_plan_template()]
        templates.extend(
            get_pmx_edit_plan_template(operation_type)
            for operation_type in self.supported
        )

        for template in templates:
            with self.subTest(operation=template.operation_type):
                with self.assertRaises(PmxEditPlanError) as context:
                    parse_pmx_edit_plan_json(
                        render_pmx_edit_plan_template_json(template)
                    )
                self.assertEqual(
                    context.exception.field,
                    PMX_EDIT_PLAN_TEMPLATE_MARKER,
                )

    def test_removing_marker_does_not_make_unfinished_template_executable(self) -> None:
        templates = [get_pmx_edit_plan_template()]
        templates.extend(
            get_pmx_edit_plan_template(operation_type)
            for operation_type in self.supported
        )

        for template in templates:
            with self.subTest(operation=template.operation_type):
                payload = template.to_dict()
                del payload[PMX_EDIT_PLAN_TEMPLATE_MARKER]
                text = json.dumps(
                    payload,
                    ensure_ascii=False,
                    allow_nan=False,
                )
                with self.assertRaises(PmxEditPlanError):
                    parse_pmx_edit_plan_json(text)

    def test_json_renderer_is_deterministic_and_newline_terminated(self) -> None:
        first = render_pmx_edit_plan_template_json(
            get_pmx_edit_plan_template("update_material")
        )
        second = render_pmx_edit_plan_template_json(
            get_pmx_edit_plan_template("update_material")
        )

        self.assertEqual(first, second)
        self.assertTrue(first.endswith("\n"))
        self.assertEqual(json.loads(first), json.loads(second))

    def test_json_renderer_preserves_unicode_instead_of_ascii_escaping(self) -> None:
        rendered = render_pmx_edit_plan_template_json(
            get_pmx_edit_plan_template("set_model_info")
        )

        self.assertIn("モデル名", rendered)
        self.assertNotIn("\\u30e2", rendered.lower())
        self.assertEqual(
            rendered.encode("utf-8").decode("utf-8"),
            rendered,
        )

    def test_compact_json_renderer_is_deterministic(self) -> None:
        template = get_pmx_edit_plan_template("set_texture_path")

        first = render_pmx_edit_plan_template_json(template, indent=None)
        second = render_pmx_edit_plan_template_json(template, indent=None)

        self.assertEqual(first, second)
        self.assertTrue(first.endswith("\n"))

    def test_template_models_are_immutable(self) -> None:
        template = get_pmx_edit_plan_template("set_model_info")

        with self.assertRaises(FrozenInstanceError):
            template.executable = True  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            template.operation.operation_type = "changed"  # type: ignore[misc]

    def test_to_dict_returns_fresh_payloads(self) -> None:
        template = get_pmx_edit_plan_template("set_model_info")
        first = template.to_dict()
        first[PMX_EDIT_PLAN_TEMPLATE_MARKER]["instructions"].append("changed")
        first["operations"][0]["local_name"] = "changed"

        second = template.to_dict()
        self.assertNotIn(
            "changed",
            second[PMX_EDIT_PLAN_TEMPLATE_MARKER]["instructions"],
        )
        self.assertIs(
            type(second["operations"][0]["local_name"]),
            dict,
        )

    def test_generation_does_not_mutate_filesystem(self) -> None:
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as temporary_directory:
            sentinel = os.path.join(temporary_directory, "sentinel.txt")
            with open(sentinel, "w", encoding="utf-8") as stream:
                stream.write("unchanged")
            before = sorted(os.listdir(temporary_directory))

            try:
                os.chdir(temporary_directory)
                for operation_type in (None, *self.supported):
                    template = get_pmx_edit_plan_template(operation_type)
                    render_pmx_edit_plan_template_json(template)
            finally:
                os.chdir(original_cwd)

            after = sorted(os.listdir(temporary_directory))
            with open(sentinel, "r", encoding="utf-8") as stream:
                sentinel_text = stream.read()

            self.assertEqual(before, after)
            self.assertEqual(sentinel_text, "unchanged")

    def test_operation_type_is_strict_and_not_normalized(self) -> None:
        with self.assertRaises(TypeError):
            get_pmx_edit_plan_template(1)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            get_pmx_edit_plan_template("")
        with self.assertRaises(ValueError):
            get_pmx_edit_plan_template(" SET_MODEL_INFO ")
        with self.assertRaises(ValueError) as context:
            get_pmx_edit_plan_template("unsupported")

        self.assertIn("set_model_info", str(context.exception))
        self.assertIn("set_texture_path", str(context.exception))
        self.assertIn("update_material", str(context.exception))

    def test_renderer_rejects_invalid_indent_without_coercion(self) -> None:
        template = get_pmx_edit_plan_template()

        with self.assertRaises(TypeError):
            render_pmx_edit_plan_template_json(
                template,
                indent=True,  # type: ignore[arg-type]
            )
        with self.assertRaises(ValueError):
            render_pmx_edit_plan_template_json(template, indent=-1)


if __name__ == "__main__":
    unittest.main()
