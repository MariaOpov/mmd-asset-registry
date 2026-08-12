"""Tests for the deterministic PMX edit-operation authoring catalog."""

from __future__ import annotations

import json
import unittest
from dataclasses import FrozenInstanceError, fields

from mmd_registry.pmx.editing import (
    PmxEditEffectKind,
    PmxEditFieldRole,
    PmxEditJsonType,
    PmxEditTargetKind,
    get_pmx_edit_operation_catalog,
)
from mmd_registry.pmx.editing.operations import (
    MATERIAL_FIELDS,
    MODEL_INFO_FIELDS,
    SUPPORTED_OPERATION_TYPES,
)


class PmxEditOperationCatalogTests(unittest.TestCase):
    """Lock catalog coverage, ordering, field metadata, and immutability."""

    def setUp(self) -> None:
        self.catalog = get_pmx_edit_operation_catalog()
        self.by_type = {
            operation.operation_type: operation
            for operation in self.catalog.operations
        }

    def test_catalog_covers_authoritative_supported_operation_types_in_order(self) -> None:
        expected = tuple(
            operation_type.operation_name
            for operation_type in SUPPORTED_OPERATION_TYPES
        )

        self.assertEqual(
            tuple(
                operation.operation_type
                for operation in self.catalog.operations
            ),
            expected,
        )
        self.assertEqual(len(expected), len(set(expected)))

    def test_catalog_field_names_match_operation_dataclass_fields(self) -> None:
        for operation_type, catalog_entry in zip(
            SUPPORTED_OPERATION_TYPES,
            self.catalog.operations,
        ):
            with self.subTest(operation=catalog_entry.operation_type):
                self.assertEqual(
                    tuple(field.name for field in fields(operation_type)),
                    tuple(field.name for field in catalog_entry.fields),
                )

    def test_required_and_optional_fields_match_current_operation_contract(self) -> None:
        self.assertEqual(
            self.by_type["set_model_info"].required_fields,
            (),
        )
        self.assertEqual(
            self.by_type["set_model_info"].optional_fields,
            MODEL_INFO_FIELDS,
        )
        self.assertEqual(
            self.by_type["set_texture_path"].required_fields,
            ("texture_index", "path"),
        )
        self.assertEqual(
            self.by_type["set_texture_path"].optional_fields,
            (),
        )
        self.assertEqual(
            self.by_type["update_material"].required_fields,
            ("material_index",),
        )
        self.assertEqual(
            self.by_type["update_material"].optional_fields,
            MATERIAL_FIELDS,
        )

    def test_target_and_effect_kinds_are_explicit(self) -> None:
        model = self.by_type["set_model_info"]
        texture = self.by_type["set_texture_path"]
        material = self.by_type["update_material"]

        self.assertIs(model.target_kind, PmxEditTargetKind.MODEL)
        self.assertIs(model.effect_kind, PmxEditEffectKind.MODEL_METADATA)
        self.assertIs(texture.target_kind, PmxEditTargetKind.TEXTURE)
        self.assertIs(texture.effect_kind, PmxEditEffectKind.TEXTURE_PATH)
        self.assertIs(material.target_kind, PmxEditTargetKind.MATERIAL)
        self.assertIs(material.effect_kind, PmxEditEffectKind.MATERIAL_STATE)

    def test_field_metadata_preserves_exact_json_types_and_constraints(self) -> None:
        texture_fields = {
            field.name: field
            for field in self.by_type["set_texture_path"].fields
        }
        material_fields = {
            field.name: field
            for field in self.by_type["update_material"].fields
        }

        self.assertIs(
            texture_fields["texture_index"].json_type,
            PmxEditJsonType.INTEGER,
        )
        self.assertEqual(texture_fields["texture_index"].minimum, 0)
        self.assertIs(
            texture_fields["texture_index"].role,
            PmxEditFieldRole.SELECTOR,
        )

        self.assertIs(
            material_fields["specular_strength"].json_type,
            PmxEditJsonType.FLOAT,
        )
        self.assertTrue(material_fields["specular_strength"].finite)
        self.assertIs(
            material_fields["diffuse"].json_type,
            PmxEditJsonType.ARRAY,
        )
        self.assertEqual(material_fields["diffuse"].array_length, 4)
        self.assertTrue(material_fields["diffuse"].finite)
        self.assertEqual(
            material_fields["toon_reference_mode"].choices,
            ("texture", "shared"),
        )
        self.assertEqual(
            material_fields["sphere_mode"].choices,
            (0, 1, 2, 3),
        )
        self.assertEqual(material_fields["drawing_flags"].minimum, 0)
        self.assertEqual(material_fields["drawing_flags"].maximum, 255)

    def test_catalog_and_nested_metadata_are_immutable(self) -> None:
        with self.assertRaises(FrozenInstanceError):
            self.catalog.operations = ()  # type: ignore[misc]

        operation = self.catalog.operations[0]
        with self.assertRaises(FrozenInstanceError):
            operation.purpose = "changed"  # type: ignore[misc]

        field = operation.fields[0]
        with self.assertRaises(FrozenInstanceError):
            field.name = "changed"  # type: ignore[misc]

    def test_catalog_serialization_is_deterministic_and_json_safe(self) -> None:
        first = self.catalog.to_dict()
        second = get_pmx_edit_operation_catalog().to_dict()

        self.assertEqual(first, second)
        first_json = json.dumps(
            first,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        second_json = json.dumps(
            second,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        self.assertEqual(first_json, second_json)
        self.assertNotIn("object at", first_json)

    def test_catalog_contains_no_unsupported_operation(self) -> None:
        supported_names = {
            operation_type.operation_name
            for operation_type in SUPPORTED_OPERATION_TYPES
        }

        self.assertEqual(set(self.by_type), supported_names)


if __name__ == "__main__":
    unittest.main()
