"""Tests for strict JSON loading of declarative PMX edit plans."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from mmd_registry.pmx.editing import (
    PmxEditPlanError,
    SetModelInfo,
    SetTexturePath,
    UpdateMaterial,
    load_pmx_edit_plan,
    parse_pmx_edit_plan_json,
)


def parse_payload(payload: object):
    """Encode one test payload as JSON and parse it through the public API."""

    return parse_pmx_edit_plan_json(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )


class PmxEditPlanJsonTests(unittest.TestCase):
    """Validate strict schema, exact types, Unicode, and conflicts."""

    def test_loads_all_operations_and_preserves_stable_unicode_data(self) -> None:
        source_hash = "a" * 64
        payload = {
            "schema_version": 1,
            "expected_source_sha256": source_hash,
            "operations": [
                {
                    "op": "set_model_info",
                    "local_name": "モデル 🌸",
                    "universal_name": "Model",
                    "local_comments": "安全な編集",
                    "universal_comments": "Safe edit",
                },
                {
                    "op": "set_texture_path",
                    "texture_index": 2,
                    "path": "textures/顔.png",
                },
                {
                    "op": "update_material",
                    "material_index": 1,
                    "local_name": "材質",
                    "universal_name": "Material",
                    "memo": "確認済み",
                    "texture_index": 0,
                    "sphere_texture_index": -1,
                    "sphere_mode": 2,
                    "toon_reference_mode": "shared",
                    "toon_reference_index": 4,
                    "diffuse": [0.1, 0.2, 0.3, 0.4],
                    "specular": [0.5, 0.6, 0.7],
                    "specular_strength": 0.8,
                    "ambient": [0.2, 0.3, 0.4],
                    "drawing_flags": 31,
                    "edge_color": [0.4, 0.3, 0.2, 0.1],
                    "edge_scale": 1.25,
                },
            ],
        }

        plan = parse_payload(payload)

        self.assertEqual(plan.to_dict(), payload)
        self.assertIsInstance(plan.operations[0], SetModelInfo)
        self.assertIsInstance(plan.operations[1], SetTexturePath)
        self.assertIsInstance(plan.operations[2], UpdateMaterial)
        self.assertEqual(plan.expected_source_sha256, source_hash)

    def test_file_loader_reads_utf8_from_string_and_path_objects(self) -> None:
        payload = {
            "schema_version": 1,
            "operations": [
                {"op": "set_model_info", "local_name": "モデル 🌸"}
            ],
        }
        text = json.dumps(payload, ensure_ascii=False)

        with tempfile.TemporaryDirectory() as directory:
            plan_path = Path(directory, "計画.json")
            plan_path.write_text(text, encoding="utf-8")

            from_path = load_pmx_edit_plan(plan_path)
            from_string = load_pmx_edit_plan(str(plan_path))

        self.assertEqual(from_path, from_string)
        self.assertEqual(from_path.to_dict(), payload)

    def test_file_loader_rejects_invalid_utf8_and_path_type(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plan_path = Path(directory, "invalid.json")
            plan_path.write_bytes(b"\xff\xfe")
            with self.assertRaisesRegex(PmxEditPlanError, "valid UTF-8"):
                load_pmx_edit_plan(plan_path)

        with self.assertRaisesRegex(TypeError, "path must be"):
            load_pmx_edit_plan(1)  # type: ignore[arg-type]

    def test_malformed_json_reports_line_and_column(self) -> None:
        with self.assertRaisesRegex(
            PmxEditPlanError,
            r"invalid JSON at line 1, column \d+",
        ):
            parse_pmx_edit_plan_json(
                '{"schema_version":1,"operations":['
            )

        with self.assertRaisesRegex(TypeError, "text must be a string"):
            parse_pmx_edit_plan_json(b"{}")  # type: ignore[arg-type]

    def test_top_level_value_must_be_an_exact_object(self) -> None:
        for payload in (None, [], "plan", 1, True):
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(
                    PmxEditPlanError,
                    "top-level JSON value must be an object",
                ):
                    parse_payload(payload)

    def test_top_level_required_and_unknown_fields_are_rejected(self) -> None:
        cases = (
            (
                {"operations": [{"op": "set_model_info", "local_name": "x"}]},
                r"edit plan\.schema_version.*required",
            ),
            (
                {"schema_version": 1},
                r"edit plan\.operations.*required",
            ),
            (
                {
                    "schema_version": 1,
                    "operations": [
                        {"op": "set_model_info", "local_name": "x"}
                    ],
                    "registry_schema": 3,
                },
                r"edit plan\.registry_schema.*unknown field",
            ),
        )
        for payload, pattern in cases:
            with self.subTest(pattern=pattern):
                with self.assertRaisesRegex(PmxEditPlanError, pattern):
                    parse_payload(payload)

    def test_schema_version_requires_exact_supported_integer(self) -> None:
        operation = {"op": "set_model_info", "local_name": "x"}
        for value in (True, 1.0, "1", None):
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    PmxEditPlanError,
                    r"edit plan\.schema_version.*JSON integer",
                ):
                    parse_payload(
                        {"schema_version": value, "operations": [operation]}
                    )

        with self.assertRaisesRegex(
            PmxEditPlanError,
            r"edit plan\.schema_version.*unsupported schema version 2",
        ):
            parse_payload({"schema_version": 2, "operations": [operation]})

    def test_operations_requires_nonempty_array_of_objects(self) -> None:
        for operations, pattern in (
            ({}, "JSON array"),
            (None, "JSON array"),
            ([], "at least one operation"),
            (["set_model_info"], "operation must be a JSON object"),
        ):
            with self.subTest(operations=operations):
                with self.assertRaisesRegex(PmxEditPlanError, pattern):
                    parse_payload(
                        {"schema_version": 1, "operations": operations}
                    )

    def test_operation_name_is_required_exact_and_supported(self) -> None:
        cases = (
            ({"local_name": "x"}, r"operations\[0\]\.op.*required"),
            (
                {"op": 1, "local_name": "x"},
                r"operations\[0\]\.op.*JSON string",
            ),
            (
                {"op": "rename_model", "local_name": "x"},
                r"operations\[0\]\.op.*unsupported operation name",
            ),
        )
        for operation, pattern in cases:
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(PmxEditPlanError, pattern):
                    parse_payload(
                        {"schema_version": 1, "operations": [operation]}
                    )

    def test_unknown_operation_fields_are_rejected_with_context(self) -> None:
        operations = (
            {
                "op": "set_model_info",
                "local_comment": "singular is not the schema field",
            },
            {
                "op": "set_texture_path",
                "texture_index": 0,
                "path": "x.png",
                "normalize": True,
            },
            {
                "op": "update_material",
                "material_index": 0,
                "surface_index_count": 3,
            },
        )
        expected_fields = ("local_comment", "normalize", "surface_index_count")
        for operation, field in zip(operations, expected_fields):
            with self.subTest(field=field):
                with self.assertRaisesRegex(
                    PmxEditPlanError,
                    rf"operations\[0\]\.{field}.*unknown field",
                ):
                    parse_payload(
                        {"schema_version": 1, "operations": [operation]}
                    )

    def test_duplicate_json_members_are_rejected(self) -> None:
        with self.assertRaisesRegex(
            PmxEditPlanError,
            "duplicate JSON member 'local_name'",
        ):
            parse_pmx_edit_plan_json(
                '{"schema_version":1,"operations":[{'
                '"op":"set_model_info","local_name":"a",'
                '"local_name":"b"}]}'
            )

    def test_duplicate_targets_are_rejected_before_returning_plan(self) -> None:
        payload = {
            "schema_version": 1,
            "operations": [
                {"op": "update_material", "material_index": 2, "memo": "a"},
                {"op": "update_material", "material_index": 2, "memo": "b"},
            ],
        }

        with self.assertRaisesRegex(
            PmxEditPlanError,
            r"operations\[1\]\.memo.*duplicate write.*operations\[0\]\.memo",
        ):
            parse_payload(payload)

    def test_model_info_payload_must_be_nonempty_exact_strings(self) -> None:
        for operation, pattern in (
            (
                {"op": "set_model_info"},
                r"operations\[0\].*at least one field",
            ),
            (
                {"op": "set_model_info", "local_name": None},
                r"operations\[0\]\.local_name.*JSON string",
            ),
            (
                {"op": "set_model_info", "local_comments": 1},
                r"operations\[0\]\.local_comments.*JSON string",
            ),
        ):
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(PmxEditPlanError, pattern):
                    parse_payload(
                        {"schema_version": 1, "operations": [operation]}
                    )

    def test_texture_operation_requires_exact_fields_and_index_type(self) -> None:
        cases = (
            (
                {"op": "set_texture_path", "path": "x.png"},
                r"texture_index.*required",
            ),
            (
                {"op": "set_texture_path", "texture_index": 0},
                r"path.*required",
            ),
            (
                {
                    "op": "set_texture_path",
                    "texture_index": True,
                    "path": "x.png",
                },
                r"texture_index.*JSON integer",
            ),
            (
                {
                    "op": "set_texture_path",
                    "texture_index": -1,
                    "path": "x.png",
                },
                r"texture_index.*cannot be negative",
            ),
            (
                {"op": "set_texture_path", "texture_index": 0, "path": None},
                r"path.*JSON string",
            ),
        )
        for operation, pattern in cases:
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(PmxEditPlanError, pattern):
                    parse_payload(
                        {"schema_version": 1, "operations": [operation]}
                    )

    def test_material_requires_index_and_nonempty_update(self) -> None:
        cases = (
            (
                {"op": "update_material", "memo": "x"},
                r"material_index.*required",
            ),
            (
                {"op": "update_material", "material_index": True, "memo": "x"},
                r"material_index.*JSON integer",
            ),
            (
                {"op": "update_material", "material_index": -1, "memo": "x"},
                r"material_index.*cannot be negative",
            ),
            (
                {"op": "update_material", "material_index": 0},
                r"operations\[0\].*at least one field",
            ),
        )
        for operation, pattern in cases:
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(PmxEditPlanError, pattern):
                    parse_payload(
                        {"schema_version": 1, "operations": [operation]}
                    )

    def test_material_scalar_and_reference_types_are_exact(self) -> None:
        cases = (
            ("memo", None, "JSON string"),
            ("texture_index", 0.0, "JSON integer"),
            ("sphere_texture_index", -2, "smaller than -1"),
            ("specular_strength", 1, "JSON float"),
            ("edge_scale", "1.0", "JSON float"),
            ("drawing_flags", False, "JSON integer"),
        )
        for field, value, reason in cases:
            with self.subTest(field=field):
                with self.assertRaisesRegex(
                    PmxEditPlanError,
                    rf"operations\[0\]\.{field}.*{reason}",
                ):
                    parse_payload(
                        {
                            "schema_version": 1,
                            "operations": [
                                {
                                    "op": "update_material",
                                    "material_index": 0,
                                    field: value,
                                }
                            ],
                        }
                    )

    def test_material_modes_and_drawing_flag_range_are_validated(self) -> None:
        cases = (
            ("sphere_mode", 4, "0 through 3"),
            ("toon_reference_mode", "auto", "texture.*shared"),
            ("drawing_flags", -1, "unsigned byte"),
            ("drawing_flags", 256, "unsigned byte"),
        )
        for field, value, reason in cases:
            with self.subTest(field=field, value=value):
                with self.assertRaisesRegex(
                    PmxEditPlanError,
                    rf"operations\[0\]\.{field}.*{reason}",
                ):
                    parse_payload(
                        {
                            "schema_version": 1,
                            "operations": [
                                {
                                    "op": "update_material",
                                    "material_index": 0,
                                    field: value,
                                }
                            ],
                        }
                    )

        with self.assertRaisesRegex(
            PmxEditPlanError,
            r"toon_reference_index.*0 through 9",
        ):
            parse_payload(
                {
                    "schema_version": 1,
                    "operations": [
                        {
                            "op": "update_material",
                            "material_index": 0,
                            "toon_reference_mode": "shared",
                            "toon_reference_index": 10,
                        }
                    ],
                }
            )

    def test_material_vectors_require_arrays_lengths_and_exact_floats(self) -> None:
        cases = (
            ("1.0,1.0,1.0,1.0", r"diffuse.*JSON array"),
            ([1.0, 1.0, 1.0], r"diffuse.*exactly 4"),
            ([1.0, 1, 1.0, 1.0], r"diffuse\[1\].*JSON float"),
            ([1.0, 1.0, None, 1.0], r"diffuse\[2\].*JSON float"),
        )
        for diffuse, pattern in cases:
            with self.subTest(diffuse=diffuse):
                with self.assertRaisesRegex(PmxEditPlanError, pattern):
                    parse_payload(
                        {
                            "schema_version": 1,
                            "operations": [
                                {
                                    "op": "update_material",
                                    "material_index": 0,
                                    "diffuse": diffuse,
                                }
                            ],
                        }
                    )

    def test_nonfinite_and_nonstandard_numbers_are_rejected(self) -> None:
        with self.assertRaisesRegex(
            PmxEditPlanError,
            r"operations\[0\]\.specular_strength.*must be finite",
        ):
            parse_pmx_edit_plan_json(
                '{"schema_version":1,"operations":[{'
                '"op":"update_material","material_index":0,'
                '"specular_strength":1e400}]}'
            )

        with self.assertRaisesRegex(
            PmxEditPlanError,
            r"numeric constant 'NaN' is not valid JSON",
        ):
            parse_pmx_edit_plan_json(
                '{"schema_version":1,"operations":[{'
                '"op":"update_material","material_index":0,'
                '"edge_scale":NaN}]}'
            )

    def test_expected_source_hash_is_strict_lowercase_sha256(self) -> None:
        operation = {"op": "set_model_info", "local_name": "x"}
        for value in (None, 1, "a" * 63, "A" * 64, "g" * 64):
            with self.subTest(value=value):
                reason = "JSON string" if not isinstance(value, str) else "lowercase"
                with self.assertRaisesRegex(
                    PmxEditPlanError,
                    rf"expected_source_sha256.*{reason}",
                ):
                    parse_payload(
                        {
                            "schema_version": 1,
                            "expected_source_sha256": value,
                            "operations": [operation],
                        }
                    )

    def test_loader_does_not_clamp_visual_values(self) -> None:
        payload = {
            "schema_version": 1,
            "operations": [
                {
                    "op": "update_material",
                    "material_index": 0,
                    "diffuse": [-2.0, 3.5, 8.0, -0.5],
                    "edge_scale": -1.25,
                }
            ],
        }

        plan = parse_payload(payload)

        self.assertEqual(plan.to_dict(), payload)

    def test_plan_dictionary_json_roundtrip_is_stable(self) -> None:
        first = parse_payload(
            {
                "schema_version": 1,
                "operations": [
                    {"op": "set_model_info", "local_name": "モデル"},
                    {
                        "op": "set_texture_path",
                        "texture_index": 0,
                        "path": "textures/顔.png",
                    },
                ],
            }
        )

        second = parse_pmx_edit_plan_json(
            json.dumps(first.to_dict(), ensure_ascii=False)
        )

        self.assertEqual(second, first)
        self.assertEqual(second.to_dict(), first.to_dict())


if __name__ == "__main__":
    unittest.main()
