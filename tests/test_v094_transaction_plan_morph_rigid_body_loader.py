"""Tests for strict morph/rigid-body structural transaction-plan authoring."""

from __future__ import annotations

import json
import math
import unittest

import mmd_registry.pmx.transaction_plan as transaction_plan
from mmd_registry.pmx.transaction_plan import (
    PmxStructuralTransactionPlanDecodeError,
    PmxStructuralTransactionPlanError,
    parse_pmx_structural_transaction_plan_json,
)
from mmd_registry.services.structural_morph import (
    PmxStructuralMorphBoneOffset,
    PmxStructuralMorphFlipOffset,
    PmxStructuralMorphGroupOffset,
    PmxStructuralMorphImpulseOffset,
    PmxStructuralMorphInsertion,
    PmxStructuralMorphMaterialOffset,
    PmxStructuralMorphUvOffset,
    PmxStructuralMorphVertexOffset,
)
from mmd_registry.services.structural_reference import PmxStructuralNewReference
from mmd_registry.services.structural_rigid_body import (
    PmxStructuralRigidBodyInsertion,
)


def _plan(*operations: dict[str, object]) -> str:
    return json.dumps(
        {"schema_version": 1, "operations": list(operations)},
        separators=(",", ":"),
    )


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


class V094TransactionPlanMorphRigidBodyLoaderTests(unittest.TestCase):
    def test_morph_minimal_payload_uses_exact_released_defaults(self) -> None:
        plan = parse_pmx_structural_transaction_plan_json(
            _plan(
                {
                    "op": "insert_morph",
                    "local_name": "M",
                    "morph_type": "vertex",
                }
            )
        )
        self.assertEqual(
            plan.operations,
            (PmxStructuralMorphInsertion("M", "vertex"),),
        )

    def test_morph_requires_local_name_and_morph_type(self) -> None:
        cases = (
            ({"op": "insert_morph", "morph_type": "vertex"}, "local_name"),
            ({"op": "insert_morph", "local_name": "M"}, "morph_type"),
        )
        for payload, field in cases:
            with self.subTest(field=field):
                with self.assertRaises(PmxStructuralTransactionPlanError) as caught:
                    parse_pmx_structural_transaction_plan_json(_plan(payload))
                self.assertEqual(caught.exception.field, field)

    def test_morph_rejects_unknown_top_level_fields_deterministically(self) -> None:
        with self.assertRaises(PmxStructuralTransactionPlanError) as caught:
            parse_pmx_structural_transaction_plan_json(
                _plan(
                    {
                        "op": "insert_morph",
                        "local_name": "M",
                        "morph_type": "vertex",
                        "writer": "raw",
                        "final_index": 1,
                    }
                )
            )
        self.assertEqual(caught.exception.field, "final_index")

    def test_morph_type_vocabulary_is_exact(self) -> None:
        valid = (
            "group",
            "vertex",
            "bone",
            "uv",
            "additional_uv_1",
            "additional_uv_2",
            "additional_uv_3",
            "additional_uv_4",
            "material",
            "flip",
            "impulse",
        )
        for morph_type in valid:
            with self.subTest(morph_type=morph_type):
                plan = parse_pmx_structural_transaction_plan_json(
                    _plan(
                        {
                            "op": "insert_morph",
                            "local_name": "M",
                            "morph_type": morph_type,
                        }
                    )
                )
                self.assertEqual(plan.operations[0].morph_type, morph_type)

        for invalid in ("additional_uv_5", "physics", 1):
            with self.subTest(invalid=invalid):
                with self.assertRaises(PmxStructuralTransactionPlanError):
                    parse_pmx_structural_transaction_plan_json(
                        _plan(
                            {
                                "op": "insert_morph",
                                "local_name": "M",
                                "morph_type": invalid,
                            }
                        )
                    )

    def test_morph_panel_vocabulary_and_string_type_are_exact(self) -> None:
        for panel in ("system", "eyebrow", "eye", "mouth", "other"):
            with self.subTest(panel=panel):
                plan = parse_pmx_structural_transaction_plan_json(
                    _plan(
                        {
                            "op": "insert_morph",
                            "local_name": "M",
                            "morph_type": "vertex",
                            "panel": panel,
                        }
                    )
                )
                self.assertEqual(plan.operations[0].panel, panel)

        for invalid in ("face", 1):
            with self.subTest(invalid=invalid):
                with self.assertRaises(PmxStructuralTransactionPlanError):
                    parse_pmx_structural_transaction_plan_json(
                        _plan(
                            {
                                "op": "insert_morph",
                                "local_name": "M",
                                "morph_type": "vertex",
                                "panel": invalid,
                            }
                        )
                    )

    def test_offsets_must_be_json_array(self) -> None:
        with self.assertRaises(PmxStructuralTransactionPlanError) as caught:
            parse_pmx_structural_transaction_plan_json(
                _plan(
                    {
                        "op": "insert_morph",
                        "local_name": "M",
                        "morph_type": "vertex",
                        "offsets": {},
                    }
                )
            )
        self.assertEqual(caught.exception.field, "offsets")

    def test_group_offset_maps_exactly_and_keeps_same_target_ref_source_only(self) -> None:
        plan = parse_pmx_structural_transaction_plan_json(
            _plan(
                {
                    "op": "insert_morph",
                    "local_name": "G",
                    "morph_type": "group",
                    "offsets": [{"type": "group", "morph_index": 0, "weight": 0.5}],
                }
            )
        )
        self.assertEqual(
            plan.operations[0].offsets,
            (PmxStructuralMorphGroupOffset(0, 0.5),),
        )

        new_ref = {"ref": "new", "target_kind": "morph", "new_id": "morph-a"}
        with self.assertRaises(PmxStructuralTransactionPlanError):
            parse_pmx_structural_transaction_plan_json(
                _plan(
                    {
                        "op": "insert_morph",
                        "local_name": "G",
                        "morph_type": "group",
                        "offsets": [
                            {
                                "type": "group",
                                "morph_index": new_ref,
                                "weight": 0.5,
                            }
                        ],
                    }
                )
            )

    def test_flip_offset_is_source_only_and_has_no_loader_version_policy(self) -> None:
        plan = parse_pmx_structural_transaction_plan_json(
            _plan(
                {
                    "op": "insert_morph",
                    "local_name": "F",
                    "morph_type": "flip",
                    "offsets": [{"type": "flip", "morph_index": 0, "weight": 1.0}],
                }
            )
        )
        self.assertEqual(
            plan.operations[0].offsets,
            (PmxStructuralMorphFlipOffset(0, 1.0),),
        )

    def test_group_and_flip_indices_reject_bool_float_negative(self) -> None:
        for morph_type in ("group", "flip"):
            for value in (True, 1.0, -1):
                with self.subTest(morph_type=morph_type, value=value):
                    with self.assertRaises(PmxStructuralTransactionPlanError):
                        parse_pmx_structural_transaction_plan_json(
                            _plan(
                                {
                                    "op": "insert_morph",
                                    "local_name": "M",
                                    "morph_type": morph_type,
                                    "offsets": [
                                        {
                                            "type": morph_type,
                                            "morph_index": value,
                                            "weight": 0.5,
                                        }
                                    ],
                                }
                            )
                        )

    def test_vertex_offset_accepts_existing_and_reviewed_new_vertex_refs(self) -> None:
        existing = parse_pmx_structural_transaction_plan_json(
            _plan(
                {
                    "op": "insert_morph",
                    "local_name": "V",
                    "morph_type": "vertex",
                    "offsets": [
                        {
                            "type": "vertex",
                            "vertex_index": 0,
                            "translation": [0.1, 0.2, 0.3],
                        }
                    ],
                }
            )
        )
        self.assertEqual(
            existing.operations[0].offsets,
            (PmxStructuralMorphVertexOffset(0, (0.1, 0.2, 0.3)),),
        )

        ref = {"ref": "new", "target_kind": "vertex", "new_id": "vertex-a"}
        plan = parse_pmx_structural_transaction_plan_json(
            _plan(
                {
                    "op": "insert_vertex",
                    "vertex_position": [0.0, 0.0, 0.0],
                    "normal": [0.0, 1.0, 0.0],
                    "uv": [0.0, 0.0],
                    "additional_uvs": [],
                    "deform": {"type": "bdef1", "bone_index": -1},
                    "edge_scale": 1.0,
                    "new_id": "vertex-a",
                },
                {
                    "op": "insert_morph",
                    "local_name": "V",
                    "morph_type": "vertex",
                    "offsets": [
                        {
                            "type": "vertex",
                            "vertex_index": ref,
                            "translation": [0.1, 0.2, 0.3],
                        }
                    ],
                },
            )
        )
        self.assertEqual(
            plan.operations[1].offsets[0].vertex_index,
            PmxStructuralNewReference("vertex", "vertex-a"),
        )

    def test_bone_offset_accepts_reviewed_new_bone_reference(self) -> None:
        ref = {"ref": "new", "target_kind": "bone", "new_id": "bone-a"}
        plan = parse_pmx_structural_transaction_plan_json(
            _plan(
                {"op": "insert_bone", "local_name": "B", "new_id": "bone-a"},
                {
                    "op": "insert_morph",
                    "local_name": "BM",
                    "morph_type": "bone",
                    "offsets": [
                        {
                            "type": "bone",
                            "bone_index": ref,
                            "translation": [0.1, 0.2, 0.3],
                            "rotation": [0.0, 0.0, 0.0, 1.0],
                        }
                    ],
                },
            )
        )
        offset = plan.operations[1].offsets[0]
        self.assertIsInstance(offset, PmxStructuralMorphBoneOffset)
        self.assertEqual(
            offset.bone_index,
            PmxStructuralNewReference("bone", "bone-a"),
        )

    def test_uv_and_additional_uv_morphs_share_exact_uv_offset_shape(self) -> None:
        for morph_type in (
            "uv",
            "additional_uv_1",
            "additional_uv_2",
            "additional_uv_3",
            "additional_uv_4",
        ):
            with self.subTest(morph_type=morph_type):
                plan = parse_pmx_structural_transaction_plan_json(
                    _plan(
                        {
                            "op": "insert_morph",
                            "local_name": "UV",
                            "morph_type": morph_type,
                            "offsets": [
                                {
                                    "type": "uv",
                                    "vertex_index": 0,
                                    "uv_offset": [0.1, 0.2, 0.3, 0.4],
                                }
                            ],
                        }
                    )
                )
                self.assertEqual(
                    plan.operations[0].offsets,
                    (PmxStructuralMorphUvOffset(0, (0.1, 0.2, 0.3, 0.4)),),
                )

    def test_material_offset_maps_complete_payload_and_minus_one_sentinel(self) -> None:
        plan = parse_pmx_structural_transaction_plan_json(
            _plan(
                {
                    "op": "insert_morph",
                    "local_name": "Mat",
                    "morph_type": "material",
                    "offsets": [_material_offset(-1)],
                }
            )
        )
        self.assertEqual(
            plan.operations[0].offsets,
            (
                PmxStructuralMorphMaterialOffset(
                    material_index=-1,
                    operation="add",
                    diffuse=(0.1, 0.1, 0.1, 0.1),
                    specular=(0.1, 0.1, 0.1),
                    specular_strength=0.1,
                    ambient=(0.1, 0.1, 0.1),
                    edge_color=(0.1, 0.1, 0.1, 0.1),
                    edge_scale=0.1,
                    texture_tint=(0.1, 0.1, 0.1, 0.1),
                    sphere_tint=(0.1, 0.1, 0.1, 0.1),
                    toon_tint=(0.1, 0.1, 0.1, 0.1),
                ),
            ),
        )

    def test_material_offset_accepts_reviewed_new_material_reference(self) -> None:
        ref = {"ref": "new", "target_kind": "material", "new_id": "mat-a"}
        plan = parse_pmx_structural_transaction_plan_json(
            _plan(
                {"op": "insert_material", "local_name": "Mat", "new_id": "mat-a"},
                {
                    "op": "insert_morph",
                    "local_name": "MM",
                    "morph_type": "material",
                    "offsets": [_material_offset(ref)],
                },
            )
        )
        self.assertEqual(
            plan.operations[1].offsets[0].material_index,
            PmxStructuralNewReference("material", "mat-a"),
        )

    def test_material_offset_operation_is_bounded(self) -> None:
        for operation in ("multiply", "add"):
            payload = _material_offset()
            payload["operation"] = operation
            plan = parse_pmx_structural_transaction_plan_json(
                _plan(
                    {
                        "op": "insert_morph",
                        "local_name": "MM",
                        "morph_type": "material",
                        "offsets": [payload],
                    }
                )
            )
            self.assertEqual(plan.operations[0].offsets[0].operation, operation)

        payload = _material_offset()
        payload["operation"] = "replace"
        with self.assertRaises(PmxStructuralTransactionPlanError):
            parse_pmx_structural_transaction_plan_json(
                _plan(
                    {
                        "op": "insert_morph",
                        "local_name": "MM",
                        "morph_type": "material",
                        "offsets": [payload],
                    }
                )
            )

    def test_impulse_offset_accepts_reviewed_new_rigid_body_reference(self) -> None:
        ref = {"ref": "new", "target_kind": "rigid_body", "new_id": "rigid-a"}
        plan = parse_pmx_structural_transaction_plan_json(
            _plan(
                {
                    "op": "insert_rigid_body",
                    "local_name": "R",
                    "new_id": "rigid-a",
                },
                {
                    "op": "insert_morph",
                    "local_name": "I",
                    "morph_type": "impulse",
                    "offsets": [
                        {
                            "type": "impulse",
                            "rigid_body_index": ref,
                            "local": True,
                            "velocity": [0.1, 0.2, 0.3],
                            "angular_torque": [0.4, 0.5, 0.6],
                        }
                    ],
                },
            )
        )
        offset = plan.operations[1].offsets[0]
        self.assertIsInstance(offset, PmxStructuralMorphImpulseOffset)
        self.assertEqual(
            offset.rigid_body_index,
            PmxStructuralNewReference("rigid_body", "rigid-a"),
        )
        self.assertTrue(offset.local)

    def test_impulse_local_requires_exact_json_boolean(self) -> None:
        for value in (0, 1, "true"):
            with self.subTest(value=value):
                with self.assertRaises(PmxStructuralTransactionPlanError):
                    parse_pmx_structural_transaction_plan_json(
                        _plan(
                            {
                                "op": "insert_morph",
                                "local_name": "I",
                                "morph_type": "impulse",
                                "offsets": [
                                    {
                                        "type": "impulse",
                                        "rigid_body_index": 0,
                                        "local": value,
                                        "velocity": [0.0, 0.0, 0.0],
                                        "angular_torque": [0.0, 0.0, 0.0],
                                    }
                                ],
                            }
                        )
                    )

    def test_cross_target_reference_wrong_kind_and_bad_integer_types_are_rejected(self) -> None:
        cases = (
            (
                "vertex",
                {
                    "type": "vertex",
                    "vertex_index": {
                        "ref": "new",
                        "target_kind": "bone",
                        "new_id": "x",
                    },
                    "translation": [0.0, 0.0, 0.0],
                },
            ),
            (
                "bone",
                {
                    "type": "bone",
                    "bone_index": True,
                    "translation": [0.0, 0.0, 0.0],
                    "rotation": [0.0, 0.0, 0.0, 1.0],
                },
            ),
            (
                "impulse",
                {
                    "type": "impulse",
                    "rigid_body_index": -1,
                    "local": False,
                    "velocity": [0.0, 0.0, 0.0],
                    "angular_torque": [0.0, 0.0, 0.0],
                },
            ),
        )
        for morph_type, offset in cases:
            with self.subTest(morph_type=morph_type):
                with self.assertRaises(PmxStructuralTransactionPlanError):
                    parse_pmx_structural_transaction_plan_json(
                        _plan(
                            {
                                "op": "insert_morph",
                                "local_name": "M",
                                "morph_type": morph_type,
                                "offsets": [offset],
                            }
                        )
                    )

    def test_offset_discriminator_must_match_morph_type(self) -> None:
        with self.assertRaises(PmxStructuralTransactionPlanError) as caught:
            parse_pmx_structural_transaction_plan_json(
                _plan(
                    {
                        "op": "insert_morph",
                        "local_name": "M",
                        "morph_type": "vertex",
                        "offsets": [
                            {
                                "type": "bone",
                                "bone_index": 0,
                                "translation": [0.0, 0.0, 0.0],
                                "rotation": [0.0, 0.0, 0.0, 1.0],
                            }
                        ],
                    }
                )
            )
        self.assertEqual(caught.exception.field, "offsets[0].type")

    def test_offset_unknown_fields_are_rejected_deterministically(self) -> None:
        with self.assertRaises(PmxStructuralTransactionPlanError) as caught:
            parse_pmx_structural_transaction_plan_json(
                _plan(
                    {
                        "op": "insert_morph",
                        "local_name": "M",
                        "morph_type": "vertex",
                        "offsets": [
                            {
                                "type": "vertex",
                                "vertex_index": 0,
                                "translation": [0.0, 0.0, 0.0],
                                "remap": 1,
                                "final_index": 2,
                            }
                        ],
                    }
                )
            )
        self.assertEqual(caught.exception.field, "offsets[0].final_index")

    def test_morph_float_fields_require_exact_finite_json_floats(self) -> None:
        invalid = (
            {
                "op": "insert_morph",
                "local_name": "G",
                "morph_type": "group",
                "offsets": [{"type": "group", "morph_index": 0, "weight": 1}],
            },
            {
                "op": "insert_morph",
                "local_name": "V",
                "morph_type": "vertex",
                "offsets": [
                    {
                        "type": "vertex",
                        "vertex_index": 0,
                        "translation": [0, 0.0, 0.0],
                    }
                ],
            },
        )
        for payload in invalid:
            with self.subTest(payload=payload):
                with self.assertRaises(PmxStructuralTransactionPlanError):
                    parse_pmx_structural_transaction_plan_json(_plan(payload))

        text = json.dumps(
            {
                "schema_version": 1,
                "operations": [
                    {
                        "op": "insert_morph",
                        "local_name": "G",
                        "morph_type": "group",
                        "offsets": [
                            {
                                "type": "group",
                                "morph_index": 0,
                                "weight": math.inf,
                            }
                        ],
                    }
                ],
            },
            allow_nan=True,
            separators=(",", ":"),
        )
        with self.assertRaises(PmxStructuralTransactionPlanDecodeError):
            parse_pmx_structural_transaction_plan_json(text)

    def test_duplicate_nested_offset_members_are_rejected(self) -> None:
        text = (
            '{"schema_version":1,"operations":[{"op":"insert_morph",'
            '"local_name":"M","morph_type":"group","offsets":['
            '{"type":"group","morph_index":0,"morph_index":1,"weight":0.5}'
            ']}]}'
        )
        with self.assertRaisesRegex(
            PmxStructuralTransactionPlanDecodeError,
            "duplicate JSON member",
        ):
            parse_pmx_structural_transaction_plan_json(text)

    def test_morph_position_and_new_id_reuse_insertion_contract(self) -> None:
        plan = parse_pmx_structural_transaction_plan_json(
            _plan(
                {
                    "op": "insert_morph",
                    "local_name": "M",
                    "morph_type": "vertex",
                    "position": "insert_before",
                    "source_index": 0,
                    "new_id": "morph-a",
                }
            )
        )
        operation = plan.operations[0]
        self.assertEqual(operation.position, "insert_before")
        self.assertEqual(operation.source_index, 0)
        self.assertEqual(operation.new_id, "morph-a")

    def test_rigid_body_minimal_payload_uses_exact_released_defaults(self) -> None:
        plan = parse_pmx_structural_transaction_plan_json(
            _plan({"op": "insert_rigid_body", "local_name": "R"})
        )
        self.assertEqual(
            plan.operations,
            (PmxStructuralRigidBodyInsertion("R"),),
        )

    def test_rigid_body_requires_local_name_and_rejects_unknown_fields(self) -> None:
        with self.assertRaises(PmxStructuralTransactionPlanError) as missing:
            parse_pmx_structural_transaction_plan_json(
                _plan({"op": "insert_rigid_body"})
            )
        self.assertEqual(missing.exception.field, "local_name")

        with self.assertRaises(PmxStructuralTransactionPlanError) as unknown:
            parse_pmx_structural_transaction_plan_json(
                _plan(
                    {
                        "op": "insert_rigid_body",
                        "local_name": "R",
                        "writer": "raw",
                        "final_index": 1,
                    }
                )
            )
        self.assertEqual(unknown.exception.field, "final_index")

    def test_rigid_body_bone_ref_accepts_source_sentinel_and_new_bone(self) -> None:
        for value in (-1, 0):
            with self.subTest(value=value):
                plan = parse_pmx_structural_transaction_plan_json(
                    _plan(
                        {
                            "op": "insert_rigid_body",
                            "local_name": "R",
                            "bone_index": value,
                        }
                    )
                )
                self.assertEqual(plan.operations[0].bone_index, value)

        ref = {"ref": "new", "target_kind": "bone", "new_id": "bone-a"}
        plan = parse_pmx_structural_transaction_plan_json(
            _plan(
                {"op": "insert_bone", "local_name": "B", "new_id": "bone-a"},
                {
                    "op": "insert_rigid_body",
                    "local_name": "R",
                    "bone_index": ref,
                },
            )
        )
        self.assertEqual(
            plan.operations[1].bone_index,
            PmxStructuralNewReference("bone", "bone-a"),
        )

    def test_rigid_body_bone_ref_rejects_wrong_kind_bool_float_and_below_sentinel(self) -> None:
        invalid = (
            True,
            1.0,
            -2,
            {"ref": "new", "target_kind": "texture", "new_id": "x"},
        )
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(PmxStructuralTransactionPlanError):
                    parse_pmx_structural_transaction_plan_json(
                        _plan(
                            {
                                "op": "insert_rigid_body",
                                "local_name": "R",
                                "bone_index": value,
                            }
                        )
                    )

    def test_rigid_body_collision_domains_are_exact(self) -> None:
        valid = parse_pmx_structural_transaction_plan_json(
            _plan(
                {
                    "op": "insert_rigid_body",
                    "local_name": "R",
                    "collision_group": 15,
                    "collision_mask": 65535,
                }
            )
        )
        self.assertEqual(valid.operations[0].collision_group, 15)
        self.assertEqual(valid.operations[0].collision_mask, 65535)

        for field, value in (
            ("collision_group", -1),
            ("collision_group", 16),
            ("collision_group", True),
            ("collision_mask", -1),
            ("collision_mask", 65536),
            ("collision_mask", 1.0),
        ):
            with self.subTest(field=field, value=value):
                with self.assertRaises(PmxStructuralTransactionPlanError):
                    parse_pmx_structural_transaction_plan_json(
                        _plan(
                            {
                                "op": "insert_rigid_body",
                                "local_name": "R",
                                field: value,
                            }
                        )
                    )

    def test_rigid_body_shape_and_physics_mode_vocabularies_are_exact(self) -> None:
        for shape in ("sphere", "box", "capsule"):
            plan = parse_pmx_structural_transaction_plan_json(
                _plan(
                    {
                        "op": "insert_rigid_body",
                        "local_name": "R",
                        "shape": shape,
                    }
                )
            )
            self.assertEqual(plan.operations[0].shape, shape)

        for mode in (
            "bone_follow",
            "physics",
            "physics_with_bone_alignment",
        ):
            plan = parse_pmx_structural_transaction_plan_json(
                _plan(
                    {
                        "op": "insert_rigid_body",
                        "local_name": "R",
                        "physics_mode": mode,
                    }
                )
            )
            self.assertEqual(plan.operations[0].physics_mode, mode)

        for field, value in (("shape", "mesh"), ("physics_mode", "automatic")):
            with self.subTest(field=field):
                with self.assertRaises(PmxStructuralTransactionPlanError):
                    parse_pmx_structural_transaction_plan_json(
                        _plan(
                            {
                                "op": "insert_rigid_body",
                                "local_name": "R",
                                field: value,
                            }
                        )
                    )

    def test_rigid_body_vectors_require_exact_finite_floats_and_size_nonnegative(self) -> None:
        invalid = (
            ("size", [-1.0, 1.0, 1.0]),
            ("size", [1, 1.0, 1.0]),
            ("body_position", [0.0, 0.0]),
            ("rotation", [0.0, 0.0, math.inf]),
        )
        for field, value in invalid:
            with self.subTest(field=field):
                text = json.dumps(
                    {
                        "schema_version": 1,
                        "operations": [
                            {
                                "op": "insert_rigid_body",
                                "local_name": "R",
                                field: value,
                            }
                        ],
                    },
                    allow_nan=True,
                    separators=(",", ":"),
                )
                with self.assertRaises(
                    (
                        PmxStructuralTransactionPlanError,
                        PmxStructuralTransactionPlanDecodeError,
                    )
                ):
                    parse_pmx_structural_transaction_plan_json(text)

    def test_rigid_body_scalar_physics_values_require_nonnegative_exact_floats(self) -> None:
        for field in (
            "mass",
            "linear_damping",
            "angular_damping",
            "restitution",
            "friction",
        ):
            for value in (-0.1, 1, True):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(PmxStructuralTransactionPlanError):
                        parse_pmx_structural_transaction_plan_json(
                            _plan(
                                {
                                    "op": "insert_rigid_body",
                                    "local_name": "R",
                                    field: value,
                                }
                            )
                        )

    def test_rigid_body_complete_payload_maps_exactly(self) -> None:
        plan = parse_pmx_structural_transaction_plan_json(
            _plan(
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
            )
        )
        self.assertEqual(
            plan.operations[0],
            PmxStructuralRigidBodyInsertion(
                local_name="R",
                universal_name="R EN",
                bone_index=0,
                collision_group=7,
                collision_mask=4660,
                shape="box",
                size=(1.25, 2.5, 3.75),
                body_position=(4.0, -5.0, 6.0),
                rotation=(0.1, 0.2, 0.3),
                mass=2.0,
                linear_damping=0.2,
                angular_damping=0.3,
                restitution=0.4,
                friction=0.5,
                physics_mode="physics",
                position="insert_before",
                source_index=0,
                new_id="rigid-a",
            ),
        )

    def test_global_new_id_uniqueness_stays_released_request_authority(self) -> None:
        with self.assertRaisesRegex(PmxStructuralTransactionPlanError, "globally unique"):
            parse_pmx_structural_transaction_plan_json(
                _plan(
                    {
                        "op": "insert_morph",
                        "local_name": "M",
                        "morph_type": "vertex",
                        "new_id": "same",
                    },
                    {
                        "op": "insert_rigid_body",
                        "local_name": "R",
                        "new_id": "same",
                    },
                )
            )

    def test_mixed_morph_rigid_body_order_is_preserved(self) -> None:
        plan = parse_pmx_structural_transaction_plan_json(
            _plan(
                {"op": "insert_rigid_body", "local_name": "R"},
                {
                    "op": "insert_morph",
                    "local_name": "M",
                    "morph_type": "impulse",
                },
            )
        )
        self.assertEqual(
            tuple(type(operation).__name__ for operation in plan.operations),
            ("PmxStructuralRigidBodyInsertion", "PmxStructuralMorphInsertion"),
        )

    def test_all_schema_one_operation_discriminators_now_dispatch(self) -> None:
        for operation_name in (
            "insert_morph",
            "insert_rigid_body",
        ):
            with self.subTest(operation=operation_name):
                with self.assertRaises(PmxStructuralTransactionPlanError) as caught:
                    parse_pmx_structural_transaction_plan_json(
                        _plan({"op": operation_name})
                    )
                self.assertEqual(caught.exception.field, "local_name")
                self.assertNotIn("recognized by schema 1", str(caught.exception))

    def test_cp11_adds_no_new_public_namespace_names(self) -> None:
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
        self.assertTrue(expected.issubset(set(transaction_plan.__all__)))
        self.assertEqual(
            len(transaction_plan.__all__),
            len(set(transaction_plan.__all__)),
        )

    def test_morph_catalog_mappings_are_runtime_immutable(self) -> None:
        fields = transaction_plan._MORPH_OFFSET_FIELDS_BY_TYPE
        mapping = transaction_plan._MORPH_OFFSET_TYPE_BY_MORPH_TYPE
        self.assertEqual(type(fields).__name__, "mappingproxy")
        self.assertEqual(type(mapping).__name__, "mappingproxy")
        self.assertEqual(
            tuple(fields),
            ("group", "vertex", "bone", "uv", "material", "flip", "impulse"),
        )
        with self.assertRaises(TypeError):
            fields["group"] = frozenset()  # type: ignore[index]
        with self.assertRaises(TypeError):
            mapping["group"] = "vertex"  # type: ignore[index]

    def test_operation_mapping_remains_runtime_immutable_and_complete(self) -> None:
        mapping = transaction_plan._OPERATION_TYPE_BY_DISCRIMINATOR
        self.assertEqual(type(mapping).__name__, "mappingproxy")
        self.assertIs(mapping["insert_morph"], PmxStructuralMorphInsertion)
        self.assertIs(mapping["insert_rigid_body"], PmxStructuralRigidBodyInsertion)

    def test_cp11_loader_does_not_add_execution_writer_remap_version_or_final_index_authority(self) -> None:
        source = __import__("inspect").getsource(transaction_plan)
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


if __name__ == "__main__":
    unittest.main()
