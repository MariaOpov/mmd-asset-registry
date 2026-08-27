"""Tests for canonical deterministic structural transaction-plan rendering."""

from __future__ import annotations

import json
import unittest

import mmd_registry
import mmd_registry.pmx as pmx
import mmd_registry.pmx.transaction_plan as transaction_plan
import mmd_registry.services as services
from mmd_registry.pmx.transaction_plan import (
    PmxStructuralTransactionPlan,
    parse_pmx_structural_transaction_plan_json,
    render_pmx_structural_transaction_plan_json,
)


def _load(payload: dict[str, object]) -> PmxStructuralTransactionPlan:
    return parse_pmx_structural_transaction_plan_json(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )


def _vertex(deform: object, **extra: object) -> dict[str, object]:
    value: dict[str, object] = {
        "op": "insert_vertex",
        "vertex_position": [0.0, 0.0, 0.0],
        "normal": [0.0, 1.0, 0.0],
        "uv": [0.0, 0.0],
        "additional_uvs": [],
        "deform": deform,
        "edge_scale": 1.0,
    }
    value.update(extra)
    return value


def _material_offset(material_index: object = -1) -> dict[str, object]:
    return {
        "type": "material",
        "material_index": material_index,
        "operation": "add",
        "diffuse": [0.1, 0.1, 0.1, 0.1],
        "specular": [0.1, 0.1, 0.1],
        "specular_strength": 0.1,
        "ambient": [0.1, 0.1, 0.1],
        "edge_color": [0.1, 0.1, 0.1, 0.1],
        "edge_scale": 0.1,
        "texture_tint": [0.1, 0.1, 0.1, 0.1],
        "sphere_tint": [0.1, 0.1, 0.1, 0.1],
        "toon_tint": [0.1, 0.1, 0.1, 0.1],
    }


class V094TransactionPlanRendererTests(unittest.TestCase):
    def test_renderer_requires_plan_instance(self) -> None:
        with self.assertRaisesRegex(TypeError, "PmxStructuralTransactionPlan"):
            render_pmx_structural_transaction_plan_json(object())  # type: ignore[arg-type]

    def test_empty_plan_has_exact_canonical_text(self) -> None:
        plan = PmxStructuralTransactionPlan(operations=())
        self.assertEqual(
            render_pmx_structural_transaction_plan_json(plan),
            '{"schema_version":1,"operations":[]}\n',
        )

    def test_expected_source_hash_has_frozen_top_level_position(self) -> None:
        value = "a" * 64
        plan = PmxStructuralTransactionPlan(
            operations=(),
            expected_source_sha256=value,
        )
        self.assertEqual(
            render_pmx_structural_transaction_plan_json(plan),
            '{"schema_version":1,"expected_source_sha256":"'
            + value
            + '","operations":[]}\n',
        )

    def test_renderer_is_deterministic_across_repeated_calls(self) -> None:
        plan = _load(
            {
                "schema_version": 1,
                "operations": [{"op": "insert_texture", "path": "a.png"}],
            }
        )
        values = {
            render_pmx_structural_transaction_plan_json(plan)
            for _ in range(10)
        }
        self.assertEqual(len(values), 1)

    def test_unicode_is_not_ascii_escaped_and_output_ends_in_one_newline(self) -> None:
        plan = _load(
            {
                "schema_version": 1,
                "operations": [
                    {"op": "insert_texture", "path": "テクスチャ/顔.png"}
                ],
            }
        )
        rendered = render_pmx_structural_transaction_plan_json(plan)
        self.assertIn("テクスチャ/顔.png", rendered)
        self.assertNotIn("\\u", rendered)
        self.assertTrue(rendered.endswith("\n"))
        self.assertFalse(rendered.endswith("\n\n"))

    def test_transform_collection_has_exact_schema_field_order(self) -> None:
        plan = _load(
            {
                "schema_version": 1,
                "operations": [
                    {
                        "op": "transform_collection",
                        "target_kind": "texture",
                        "old_indices_in_new_order": [2, 0],
                    }
                ],
            }
        )
        self.assertEqual(
            render_pmx_structural_transaction_plan_json(plan),
            '{"schema_version":1,"operations":[{"op":"transform_collection",'
            '"target_kind":"texture","old_indices_in_new_order":[2,0]}]}\n',
        )

    def test_texture_defaults_are_omitted(self) -> None:
        plan = _load(
            {
                "schema_version": 1,
                "operations": [
                    {
                        "op": "insert_texture",
                        "path": "a.png",
                        "position": "append",
                    }
                ],
            }
        )
        self.assertEqual(
            render_pmx_structural_transaction_plan_json(plan),
            '{"schema_version":1,"operations":[{"op":"insert_texture",'
            '"path":"a.png"}]}\n',
        )

    def test_insert_before_and_new_id_are_rendered_in_schema_order(self) -> None:
        plan = _load(
            {
                "schema_version": 1,
                "operations": [
                    {
                        "op": "insert_texture",
                        "path": "a.png",
                        "position": "insert_before",
                        "source_index": 2,
                        "new_id": "texture-a",
                    }
                ],
            }
        )
        operation = json.loads(
            render_pmx_structural_transaction_plan_json(plan)
        )["operations"][0]
        self.assertEqual(
            tuple(operation),
            ("op", "path", "position", "source_index", "new_id"),
        )

    def test_material_released_defaults_collapse_to_minimal_canonical_form(self) -> None:
        plan = _load(
            {
                "schema_version": 1,
                "operations": [
                    {
                        "op": "insert_material",
                        "local_name": "M",
                        "universal_name": "",
                        "memo": "",
                        "texture_index": -1,
                        "sphere_texture_index": -1,
                        "sphere_mode": 0,
                        "toon_reference_mode": "texture",
                        "toon_reference_index": -1,
                        "diffuse": [1.0, 1.0, 1.0, 1.0],
                        "specular": [0.0, 0.0, 0.0],
                        "specular_strength": 0.0,
                        "ambient": [0.5, 0.5, 0.5],
                        "drawing_flags": 0,
                        "edge_color": [0.0, 0.0, 0.0, 1.0],
                        "edge_scale": 1.0,
                    }
                ],
            }
        )
        self.assertEqual(
            render_pmx_structural_transaction_plan_json(plan),
            '{"schema_version":1,"operations":[{"op":"insert_material",'
            '"local_name":"M"}]}\n',
        )

    def test_material_new_texture_references_render_in_bounded_shape(self) -> None:
        ref = {"ref": "new", "target_kind": "texture", "new_id": "texture-a"}
        plan = _load(
            {
                "schema_version": 1,
                "operations": [
                    {"op": "insert_texture", "path": "a.png", "new_id": "texture-a"},
                    {
                        "op": "insert_material",
                        "local_name": "M",
                        "texture_index": ref,
                        "sphere_texture_index": ref,
                        "toon_reference_index": ref,
                    },
                ],
            }
        )
        operation = json.loads(
            render_pmx_structural_transaction_plan_json(plan)
        )["operations"][1]
        for field in (
            "texture_index",
            "sphere_texture_index",
            "toon_reference_index",
        ):
            self.assertEqual(
                tuple(operation[field]),
                ("ref", "target_kind", "new_id"),
            )
            self.assertEqual(operation[field], ref)

    def test_shared_toon_mode_and_index_are_not_lost(self) -> None:
        plan = _load(
            {
                "schema_version": 1,
                "operations": [
                    {
                        "op": "insert_material",
                        "local_name": "M",
                        "toon_reference_mode": "shared",
                        "toon_reference_index": 0,
                    }
                ],
            }
        )
        operation = json.loads(
            render_pmx_structural_transaction_plan_json(plan)
        )["operations"][0]
        self.assertEqual(operation["toon_reference_mode"], "shared")
        self.assertEqual(operation["toon_reference_index"], 0)

    def test_bone_minimal_defaults_omit_default_tail_offset(self) -> None:
        plan = _load(
            {
                "schema_version": 1,
                "operations": [{"op": "insert_bone", "local_name": "B"}],
            }
        )
        self.assertEqual(
            render_pmx_structural_transaction_plan_json(plan),
            '{"schema_version":1,"operations":[{"op":"insert_bone",'
            '"local_name":"B"}]}\n',
        )

    def test_bone_tail_index_mode_is_rendered_without_null_tail_offset(self) -> None:
        plan = _load(
            {
                "schema_version": 1,
                "operations": [
                    {
                        "op": "insert_bone",
                        "local_name": "B",
                        "tail_bone_index": 0,
                    }
                ],
            }
        )
        rendered = render_pmx_structural_transaction_plan_json(plan)
        operation = json.loads(rendered)["operations"][0]
        self.assertEqual(operation["tail_bone_index"], 0)
        self.assertNotIn("tail_offset", operation)
        self.assertNotIn("null", rendered)

    def test_bone_inherit_and_ik_payload_roundtrip_canonically(self) -> None:
        payload = {
            "schema_version": 1,
            "operations": [
                {
                    "op": "insert_bone",
                    "local_name": "B",
                    "inherit_rotation": True,
                    "inherit_parent_bone_index": 0,
                    "inherit_weight": 0.5,
                    "ik": {
                        "target_bone_index": 0,
                        "loop_count": 2,
                        "angle_limit": 0.5,
                        "links": [
                            {
                                "bone_index": 1,
                                "lower_limit": [-0.1, -0.2, -0.3],
                                "upper_limit": [0.1, 0.2, 0.3],
                            }
                        ],
                    },
                }
            ],
        }
        first = _load(payload)
        rendered = render_pmx_structural_transaction_plan_json(first)
        second = parse_pmx_structural_transaction_plan_json(rendered)
        self.assertEqual(second, first)
        operation = json.loads(rendered)["operations"][0]
        self.assertNotIn("inherit_translation", operation)

    def test_bone_ik_defaults_are_omitted_but_required_target_remains(self) -> None:
        plan = _load(
            {
                "schema_version": 1,
                "operations": [
                    {
                        "op": "insert_bone",
                        "local_name": "B",
                        "ik": {
                            "target_bone_index": 0,
                            "loop_count": 1,
                            "angle_limit": 0.0,
                            "links": [],
                        },
                    }
                ],
            }
        )
        ik = json.loads(
            render_pmx_structural_transaction_plan_json(plan)
        )["operations"][0]["ik"]
        self.assertEqual(ik, {"target_bone_index": 0})

    def test_vertex_required_fields_are_never_omitted(self) -> None:
        plan = _load(
            {
                "schema_version": 1,
                "operations": [_vertex({"type": "bdef1", "bone_index": -1})],
            }
        )
        operation = json.loads(
            render_pmx_structural_transaction_plan_json(plan)
        )["operations"][0]
        self.assertEqual(
            tuple(operation)[:7],
            (
                "op",
                "vertex_position",
                "normal",
                "uv",
                "additional_uvs",
                "deform",
                "edge_scale",
            ),
        )
        self.assertEqual(operation["additional_uvs"], [])

    def test_all_vertex_deform_types_roundtrip(self) -> None:
        deforms = (
            {"type": "bdef1", "bone_index": -1},
            {"type": "bdef2", "bone_indices": [0, 1], "bone_1_weight": 0.5},
            {
                "type": "bdef4",
                "bone_indices": [0, 1, 2, 3],
                "weights": [0.1, 0.2, 0.3, 0.4],
            },
            {
                "type": "sdef",
                "bone_indices": [0, 1],
                "bone_1_weight": 0.5,
                "c": [0.0, 0.0, 0.0],
                "r0": [0.0, 0.0, 0.0],
                "r1": [0.0, 0.0, 0.0],
            },
            {
                "type": "qdef",
                "bone_indices": [0, 1, 2, 3],
                "weights": [0.25, 0.25, 0.25, 0.25],
            },
        )
        for deform in deforms:
            with self.subTest(deform=deform["type"]):
                first = _load(
                    {"schema_version": 1, "operations": [_vertex(deform)]}
                )
                rendered = render_pmx_structural_transaction_plan_json(first)
                second = parse_pmx_structural_transaction_plan_json(rendered)
                self.assertEqual(second, first)
                self.assertEqual(
                    json.loads(rendered)["operations"][0]["deform"]["type"],
                    deform["type"],
                )

    def test_vertex_new_bone_reference_is_preserved_exactly(self) -> None:
        ref = {"ref": "new", "target_kind": "bone", "new_id": "bone-a"}
        plan = _load(
            {
                "schema_version": 1,
                "operations": [
                    {"op": "insert_bone", "local_name": "B", "new_id": "bone-a"},
                    _vertex({"type": "bdef1", "bone_index": ref}),
                ],
            }
        )
        rendered_ref = json.loads(
            render_pmx_structural_transaction_plan_json(plan)
        )["operations"][1]["deform"]["bone_index"]
        self.assertEqual(rendered_ref, ref)

    def test_morph_released_defaults_collapse_to_required_fields(self) -> None:
        plan = _load(
            {
                "schema_version": 1,
                "operations": [
                    {
                        "op": "insert_morph",
                        "local_name": "M",
                        "morph_type": "vertex",
                        "universal_name": "",
                        "panel": "other",
                        "offsets": [],
                    }
                ],
            }
        )
        self.assertEqual(
            render_pmx_structural_transaction_plan_json(plan),
            '{"schema_version":1,"operations":[{"op":"insert_morph",'
            '"local_name":"M","morph_type":"vertex"}]}\n',
        )

    def test_all_morph_offset_types_roundtrip(self) -> None:
        cases = (
            ("group", {"type": "group", "morph_index": 0, "weight": 0.5}),
            (
                "vertex",
                {
                    "type": "vertex",
                    "vertex_index": 0,
                    "translation": [0.1, 0.2, 0.3],
                },
            ),
            (
                "bone",
                {
                    "type": "bone",
                    "bone_index": 0,
                    "translation": [0.1, 0.2, 0.3],
                    "rotation": [0.0, 0.0, 0.0, 1.0],
                },
            ),
            (
                "uv",
                {
                    "type": "uv",
                    "vertex_index": 0,
                    "uv_offset": [0.1, 0.2, 0.3, 0.4],
                },
            ),
            ("material", _material_offset()),
            ("flip", {"type": "flip", "morph_index": 0, "weight": 0.5}),
            (
                "impulse",
                {
                    "type": "impulse",
                    "rigid_body_index": 0,
                    "local": False,
                    "velocity": [0.1, 0.2, 0.3],
                    "angular_torque": [0.4, 0.5, 0.6],
                },
            ),
        )
        for morph_type, offset in cases:
            with self.subTest(morph_type=morph_type):
                first = _load(
                    {
                        "schema_version": 1,
                        "operations": [
                            {
                                "op": "insert_morph",
                                "local_name": "M",
                                "morph_type": morph_type,
                                "offsets": [offset],
                            }
                        ],
                    }
                )
                rendered = render_pmx_structural_transaction_plan_json(first)
                second = parse_pmx_structural_transaction_plan_json(rendered)
                self.assertEqual(second, first)

    def test_additional_uv_morph_uses_uv_offset_discriminator(self) -> None:
        plan = _load(
            {
                "schema_version": 1,
                "operations": [
                    {
                        "op": "insert_morph",
                        "local_name": "UV",
                        "morph_type": "additional_uv_4",
                        "offsets": [
                            {
                                "type": "uv",
                                "vertex_index": 0,
                                "uv_offset": [0.1, 0.2, 0.3, 0.4],
                            }
                        ],
                    }
                ],
            }
        )
        operation = json.loads(
            render_pmx_structural_transaction_plan_json(plan)
        )["operations"][0]
        self.assertEqual(operation["morph_type"], "additional_uv_4")
        self.assertEqual(operation["offsets"][0]["type"], "uv")

    def test_group_and_flip_source_only_indices_remain_plain_integers(self) -> None:
        for morph_type in ("group", "flip"):
            plan = _load(
                {
                    "schema_version": 1,
                    "operations": [
                        {
                            "op": "insert_morph",
                            "local_name": "M",
                            "morph_type": morph_type,
                            "offsets": [
                                {
                                    "type": morph_type,
                                    "morph_index": 0,
                                    "weight": 0.5,
                                }
                            ],
                        }
                    ],
                }
            )
            value = json.loads(
                render_pmx_structural_transaction_plan_json(plan)
            )["operations"][0]["offsets"][0]["morph_index"]
            self.assertIs(type(value), int)

    def test_rigid_body_released_defaults_collapse_to_minimal_form(self) -> None:
        plan = _load(
            {
                "schema_version": 1,
                "operations": [
                    {
                        "op": "insert_rigid_body",
                        "local_name": "R",
                        "universal_name": "",
                        "bone_index": -1,
                        "collision_group": 0,
                        "collision_mask": 65535,
                        "shape": "sphere",
                        "size": [1.0, 1.0, 1.0],
                        "body_position": [0.0, 0.0, 0.0],
                        "rotation": [0.0, 0.0, 0.0],
                        "mass": 1.0,
                        "linear_damping": 0.5,
                        "angular_damping": 0.5,
                        "restitution": 0.0,
                        "friction": 0.5,
                        "physics_mode": "bone_follow",
                    }
                ],
            }
        )
        self.assertEqual(
            render_pmx_structural_transaction_plan_json(plan),
            '{"schema_version":1,"operations":[{"op":"insert_rigid_body",'
            '"local_name":"R"}]}\n',
        )

    def test_rigid_body_complete_nondefault_payload_roundtrips(self) -> None:
        payload = {
            "schema_version": 1,
            "operations": [
                {
                    "op": "insert_rigid_body",
                    "local_name": "R",
                    "universal_name": "R EN",
                    "bone_index": 0,
                    "collision_group": 7,
                    "collision_mask": 4660,
                    "shape": "box",
                    "size": [1.25, 2.5, 3.75],
                    "body_position": [4.0, -5.0, 6.0],
                    "rotation": [0.1, 0.2, 0.3],
                    "mass": 2.0,
                    "linear_damping": 0.2,
                    "angular_damping": 0.3,
                    "restitution": 0.4,
                    "friction": 0.5,
                    "physics_mode": "physics",
                    "position": "insert_before",
                    "source_index": 0,
                    "new_id": "rigid-a",
                }
            ],
        }
        first = _load(payload)
        rendered = render_pmx_structural_transaction_plan_json(first)
        second = parse_pmx_structural_transaction_plan_json(rendered)
        self.assertEqual(second, first)

    def test_cross_target_new_references_remain_exact(self) -> None:
        payload = {
            "schema_version": 1,
            "operations": [
                {"op": "insert_bone", "local_name": "B", "new_id": "bone-a"},
                {
                    "op": "insert_rigid_body",
                    "local_name": "R",
                    "bone_index": {
                        "ref": "new",
                        "target_kind": "bone",
                        "new_id": "bone-a",
                    },
                    "new_id": "rigid-a",
                },
                {
                    "op": "insert_morph",
                    "local_name": "I",
                    "morph_type": "impulse",
                    "offsets": [
                        {
                            "type": "impulse",
                            "rigid_body_index": {
                                "ref": "new",
                                "target_kind": "rigid_body",
                                "new_id": "rigid-a",
                            },
                            "local": False,
                            "velocity": [0.0, 0.0, 0.0],
                            "angular_torque": [0.0, 0.0, 0.0],
                        }
                    ],
                },
            ],
        }
        rendered = json.loads(
            render_pmx_structural_transaction_plan_json(_load(payload))
        )
        self.assertEqual(
            rendered["operations"][1]["bone_index"],
            {"ref": "new", "target_kind": "bone", "new_id": "bone-a"},
        )
        self.assertEqual(
            rendered["operations"][2]["offsets"][0]["rigid_body_index"],
            {
                "ref": "new",
                "target_kind": "rigid_body",
                "new_id": "rigid-a",
            },
        )

    def test_negative_zero_collapses_to_positive_zero(self) -> None:
        plan = _load(
            {
                "schema_version": 1,
                "operations": [
                    _vertex(
                        {"type": "bdef2", "bone_indices": [0, 1], "bone_1_weight": -0.0},
                        vertex_position=[-0.0, 1.0, 2.0],
                    )
                ],
            }
        )
        rendered = render_pmx_structural_transaction_plan_json(plan)
        self.assertNotIn("-0.0", rendered)
        reparsed = parse_pmx_structural_transaction_plan_json(rendered)
        self.assertEqual(reparsed, plan)

    def test_equivalent_explicit_defaults_collapse_to_same_text(self) -> None:
        minimal = _load(
            {
                "schema_version": 1,
                "operations": [
                    {"op": "insert_rigid_body", "local_name": "R"}
                ],
            }
        )
        explicit = _load(
            {
                "operations": [
                    {
                        "physics_mode": "bone_follow",
                        "friction": 0.5,
                        "restitution": 0.0,
                        "angular_damping": 0.5,
                        "linear_damping": 0.5,
                        "mass": 1.0,
                        "rotation": [0.0, 0.0, 0.0],
                        "body_position": [0.0, 0.0, 0.0],
                        "size": [1.0, 1.0, 1.0],
                        "shape": "sphere",
                        "collision_mask": 65535,
                        "collision_group": 0,
                        "bone_index": -1,
                        "universal_name": "",
                        "local_name": "R",
                        "op": "insert_rigid_body",
                    }
                ],
                "schema_version": 1,
            }
        )
        self.assertEqual(minimal, explicit)
        self.assertEqual(
            render_pmx_structural_transaction_plan_json(minimal),
            render_pmx_structural_transaction_plan_json(explicit),
        )

    def test_load_render_load_semantic_equality_covers_all_seven_operations(self) -> None:
        payload = {
            "schema_version": 1,
            "expected_source_sha256": "b" * 64,
            "operations": [
                {
                    "op": "transform_collection",
                    "target_kind": "texture",
                    "old_indices_in_new_order": [1, 0],
                },
                {"op": "insert_texture", "path": "a.png"},
                {"op": "insert_material", "local_name": "M"},
                {"op": "insert_bone", "local_name": "B"},
                {
                    "op": "insert_morph",
                    "local_name": "Morph",
                    "morph_type": "group",
                    "offsets": [{"type": "group", "morph_index": 0, "weight": 0.5}],
                },
                {"op": "insert_rigid_body", "local_name": "R"},
                _vertex({"type": "bdef1", "bone_index": -1}),
            ],
        }
        first = _load(payload)
        rendered = render_pmx_structural_transaction_plan_json(first)
        second = parse_pmx_structural_transaction_plan_json(rendered)
        self.assertEqual(second, first)
        self.assertEqual(
            render_pmx_structural_transaction_plan_json(second),
            rendered,
        )

    def test_parse_render_parse_render_is_text_idempotent(self) -> None:
        raw = (
            '{ "operations" : [ { "path" : "a.png", "position":"append",'
            ' "op":"insert_texture" } ], "schema_version" : 1 }'
        )
        first = parse_pmx_structural_transaction_plan_json(raw)
        canonical = render_pmx_structural_transaction_plan_json(first)
        second = parse_pmx_structural_transaction_plan_json(canonical)
        self.assertEqual(
            render_pmx_structural_transaction_plan_json(second),
            canonical,
        )

    def test_rendered_output_is_strict_loader_accepted_json(self) -> None:
        plan = _load(
            {
                "schema_version": 1,
                "operations": [
                    {"op": "insert_morph", "local_name": "M", "morph_type": "vertex"}
                ],
            }
        )
        rendered = render_pmx_structural_transaction_plan_json(plan)
        self.assertEqual(
            parse_pmx_structural_transaction_plan_json(rendered),
            plan,
        )
        self.assertEqual(json.loads(rendered)["schema_version"], 1)

    def test_renderer_is_public_only_in_authoring_namespace(self) -> None:
        self.assertIn(
            "render_pmx_structural_transaction_plan_json",
            transaction_plan.__all__,
        )
        self.assertIs(
            transaction_plan.render_pmx_structural_transaction_plan_json,
            render_pmx_structural_transaction_plan_json,
        )
        for root in (mmd_registry, pmx, services):
            self.assertFalse(
                hasattr(root, "render_pmx_structural_transaction_plan_json")
            )

    def test_cp12_public_namespace_is_unique_and_contains_prior_exports(self) -> None:
        expected = {
            "PMX_STRUCTURAL_TRANSACTION_PLAN_SCHEMA_VERSION",
            "PmxStructuralTransactionOperationType",
            "PmxStructuralTransactionOperationCatalogEntry",
            "PmxStructuralTransactionOperationCatalog",
            "get_pmx_structural_transaction_operation_catalog",
            "PmxStructuralTransactionPlanError",
            "PmxStructuralTransactionPlanDecodeError",
            "parse_pmx_structural_transaction_plan_json",
            "load_pmx_structural_transaction_plan",
            "render_pmx_structural_transaction_plan_json",
            "PmxStructuralTransactionPlan",
        }
        self.assertEqual(set(transaction_plan.__all__), expected)
        self.assertEqual(
            len(transaction_plan.__all__),
            len(set(transaction_plan.__all__)),
        )

    def test_renderer_adds_no_execution_writer_remap_or_version_authority(self) -> None:
        inspect = __import__("inspect")
        source = inspect.getsource(render_pmx_structural_transaction_plan_json)
        module_source = inspect.getsource(transaction_plan)
        for forbidden in (
            "remap_pmx_references",
            "write_pmx_structural_output",
            "_write_structural_transaction",
            "_plan_structural_transaction",
            "publication_callback",
            "preview_structural_transaction(",
            "apply_structural_transaction(",
            "final_index=",
            "PMX 2.1",
            "version >=",
        ):
            self.assertNotIn(forbidden, source)
            self.assertNotIn(forbidden, module_source)

    def test_renderer_uses_no_sort_keys_or_generic_dataclass_serializer(self) -> None:
        source = __import__("inspect").getsource(
            render_pmx_structural_transaction_plan_json
        )
        self.assertNotIn("sort_keys=True", source)
        self.assertNotIn("asdict(", source)

    def test_renderer_does_not_emit_null_for_valid_released_defaults(self) -> None:
        plan = _load(
            {
                "schema_version": 1,
                "operations": [
                    {"op": "insert_bone", "local_name": "B"},
                    {"op": "insert_texture", "path": "a.png"},
                    {"op": "insert_morph", "local_name": "M", "morph_type": "vertex"},
                ],
            }
        )
        rendered = render_pmx_structural_transaction_plan_json(plan)
        self.assertNotIn(":null", rendered)

    def test_operation_order_is_preserved_exactly(self) -> None:
        plan = _load(
            {
                "schema_version": 1,
                "operations": [
                    {"op": "insert_texture", "path": "a.png"},
                    {"op": "insert_bone", "local_name": "B"},
                    {"op": "insert_rigid_body", "local_name": "R"},
                ],
            }
        )
        operations = json.loads(
            render_pmx_structural_transaction_plan_json(plan)
        )["operations"]
        self.assertEqual(
            tuple(operation["op"] for operation in operations),
            ("insert_texture", "insert_bone", "insert_rigid_body"),
        )


if __name__ == "__main__":
    unittest.main()
