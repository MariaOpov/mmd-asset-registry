"""Tests for strict bone/IK structural transaction-plan authoring."""

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
from mmd_registry.services.structural_bone import (
    PmxStructuralBoneIk,
    PmxStructuralBoneIkLink,
    PmxStructuralBoneInsertion,
)


def _plan(*operations: dict[str, object]) -> str:
    return json.dumps(
        {"schema_version": 1, "operations": list(operations)},
        separators=(",", ":"),
    )


class V094TransactionPlanBoneLoaderTests(unittest.TestCase):
    def test_bone_minimal_payload_uses_exact_released_defaults(self) -> None:
        plan = parse_pmx_structural_transaction_plan_json(
            _plan({"op": "insert_bone", "local_name": "Bone"})
        )
        self.assertEqual(
            plan.operations,
            (PmxStructuralBoneInsertion(local_name="Bone"),),
        )

    def test_bone_full_semantic_payload_maps_exactly(self) -> None:
        payload = {
            "op": "insert_bone",
            "local_name": "Full",
            "universal_name": "Full EN",
            "bone_position": [0.1, 0.2, 0.3],
            "parent_bone_index": 0,
            "transform_layer": 3,
            "rotatable": True,
            "translatable": True,
            "visible": True,
            "enabled": True,
            "local_append": True,
            "after_physics": True,
            "tail_offset": None,
            "tail_bone_index": 1,
            "inherit_rotation": True,
            "inherit_translation": True,
            "inherit_parent_bone_index": 0,
            "inherit_weight": 0.25,
            "fixed_axis": [0.0, 1.0, 0.0],
            "local_axis_x": [1.0, 0.0, 0.0],
            "local_axis_z": [0.0, 0.0, 1.0],
            "external_parent_key": 17,
            "ik": {
                "target_bone_index": 0,
                "loop_count": 8,
                "angle_limit": 0.1,
                "links": [
                    {"bone_index": 0},
                    {
                        "bone_index": 1,
                        "lower_limit": [-0.1, -0.2, -0.3],
                        "upper_limit": [0.1, 0.2, 0.3],
                    },
                ],
            },
            "position": "insert_before",
            "source_index": 2,
            "new_id": "bone-full",
        }
        plan = parse_pmx_structural_transaction_plan_json(_plan(payload))
        self.assertEqual(
            plan.operations[0],
            PmxStructuralBoneInsertion(
                local_name="Full",
                universal_name="Full EN",
                bone_position=(0.1, 0.2, 0.3),
                parent_bone_index=0,
                transform_layer=3,
                rotatable=True,
                translatable=True,
                visible=True,
                enabled=True,
                local_append=True,
                after_physics=True,
                tail_offset=None,
                tail_bone_index=1,
                inherit_rotation=True,
                inherit_translation=True,
                inherit_parent_bone_index=0,
                inherit_weight=0.25,
                fixed_axis=(0.0, 1.0, 0.0),
                local_axis_x=(1.0, 0.0, 0.0),
                local_axis_z=(0.0, 0.0, 1.0),
                external_parent_key=17,
                ik=PmxStructuralBoneIk(
                    target_bone_index=0,
                    loop_count=8,
                    angle_limit=0.1,
                    links=(
                        PmxStructuralBoneIkLink(0),
                        PmxStructuralBoneIkLink(
                            1,
                            lower_limit=(-0.1, -0.2, -0.3),
                            upper_limit=(0.1, 0.2, 0.3),
                        ),
                    ),
                ),
                position="insert_before",
                source_index=2,
                new_id="bone-full",
            ),
        )

    def test_bone_requires_local_name_and_rejects_unknown_raw_fields(self) -> None:
        cases = (
            ({"op": "insert_bone"}, "local_name"),
            ({"op": "insert_bone", "local_name": 1}, "local_name"),
            ({"op": "insert_bone", "local_name": "B", "flags": 1}, "flags"),
            ({"op": "insert_bone", "local_name": "B", "tail_mode": "index"}, "tail_mode"),
            ({"op": "insert_bone", "local_name": "B", "final_index": 1}, "final_index"),
        )
        for payload, field in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(PmxStructuralTransactionPlanError) as caught:
                    parse_pmx_structural_transaction_plan_json(_plan(payload))
                self.assertEqual(caught.exception.field, field)

    def test_bone_string_fields_are_not_coerced(self) -> None:
        for field in ("local_name", "universal_name"):
            payload: dict[str, object] = {
                "op": "insert_bone",
                "local_name": "B",
                field: 1,
            }
            with self.subTest(field=field):
                with self.assertRaises(PmxStructuralTransactionPlanError):
                    parse_pmx_structural_transaction_plan_json(_plan(payload))

    def test_bone_boolean_fields_require_exact_json_booleans(self) -> None:
        for field in (
            "rotatable",
            "translatable",
            "visible",
            "enabled",
            "local_append",
            "after_physics",
            "inherit_rotation",
            "inherit_translation",
        ):
            with self.subTest(field=field):
                with self.assertRaises(PmxStructuralTransactionPlanError) as caught:
                    parse_pmx_structural_transaction_plan_json(
                        _plan({"op": "insert_bone", "local_name": "B", field: 1})
                    )
                self.assertEqual(caught.exception.field, field)

    def test_bone_position_and_axis_vectors_require_exact_finite_floats(self) -> None:
        invalid = (
            ("bone_position", [0.0, 0.0]),
            ("bone_position", [0, 0.0, 0.0]),
            ("fixed_axis", [0.0, math.inf, 0.0]),
            ("local_axis_x", "x"),
        )
        for field, value in invalid:
            with self.subTest(field=field, value=value):
                text = json.dumps(
                    {
                        "schema_version": 1,
                        "operations": [
                            {"op": "insert_bone", "local_name": "B", field: value}
                        ],
                    },
                    allow_nan=True,
                    separators=(",", ":"),
                )
                with self.assertRaises(
                    (PmxStructuralTransactionPlanError, PmxStructuralTransactionPlanDecodeError)
                ):
                    parse_pmx_structural_transaction_plan_json(text)

    def test_parent_tail_and_inherit_references_are_captured_source_integers(self) -> None:
        plan = parse_pmx_structural_transaction_plan_json(
            _plan(
                {
                    "op": "insert_bone",
                    "local_name": "B",
                    "parent_bone_index": -1,
                    "tail_bone_index": 0,
                    "inherit_rotation": True,
                    "inherit_parent_bone_index": -1,
                    "inherit_weight": 0.5,
                }
            )
        )
        operation = plan.operations[0]
        self.assertEqual(operation.parent_bone_index, -1)
        self.assertEqual(operation.tail_bone_index, 0)
        self.assertIsNone(operation.tail_offset)
        self.assertEqual(operation.inherit_parent_bone_index, -1)

    def test_same_target_new_bone_references_are_rejected_everywhere(self) -> None:
        ref = {"ref": "new", "target_kind": "bone", "new_id": "bone-a"}
        cases = (
            ("parent_bone_index", ref),
            ("tail_bone_index", ref),
            ("inherit_parent_bone_index", ref),
        )
        for field, value in cases:
            payload: dict[str, object] = {
                "op": "insert_bone",
                "local_name": "B",
                field: value,
            }
            if field == "inherit_parent_bone_index":
                payload["inherit_rotation"] = True
                payload["inherit_weight"] = 0.5
            with self.subTest(field=field):
                with self.assertRaises(PmxStructuralTransactionPlanError):
                    parse_pmx_structural_transaction_plan_json(_plan(payload))

        with self.assertRaises(PmxStructuralTransactionPlanError):
            parse_pmx_structural_transaction_plan_json(
                _plan(
                    {
                        "op": "insert_bone",
                        "local_name": "B",
                        "ik": {"target_bone_index": ref},
                    }
                )
            )
        with self.assertRaises(PmxStructuralTransactionPlanError):
            parse_pmx_structural_transaction_plan_json(
                _plan(
                    {
                        "op": "insert_bone",
                        "local_name": "B",
                        "ik": {
                            "target_bone_index": 0,
                            "links": [{"bone_index": ref}],
                        },
                    }
                )
            )

    def test_bone_reference_lower_bounds_are_strict(self) -> None:
        invalid = (
            ("parent_bone_index", -2),
            ("tail_bone_index", -2),
        )
        for field, value in invalid:
            with self.subTest(field=field):
                with self.assertRaises(PmxStructuralTransactionPlanError):
                    parse_pmx_structural_transaction_plan_json(
                        _plan({"op": "insert_bone", "local_name": "B", field: value})
                    )

        for value in (-1, True, 1.0):
            with self.subTest(ik_target=value):
                with self.assertRaises(PmxStructuralTransactionPlanError):
                    parse_pmx_structural_transaction_plan_json(
                        _plan(
                            {
                                "op": "insert_bone",
                                "local_name": "B",
                                "ik": {"target_bone_index": value},
                            }
                        )
                    )

    def test_tail_defaults_to_offset_mode_when_neither_tail_field_is_authored(self) -> None:
        plan = parse_pmx_structural_transaction_plan_json(
            _plan({"op": "insert_bone", "local_name": "B"})
        )
        operation = plan.operations[0]
        self.assertEqual(operation.tail_offset, (0.0, 0.0, 0.0))
        self.assertIsNone(operation.tail_bone_index)

    def test_tail_bone_index_alone_switches_from_default_offset_mode(self) -> None:
        plan = parse_pmx_structural_transaction_plan_json(
            _plan(
                {
                    "op": "insert_bone",
                    "local_name": "B",
                    "tail_bone_index": 2,
                }
            )
        )
        operation = plan.operations[0]
        self.assertIsNone(operation.tail_offset)
        self.assertEqual(operation.tail_bone_index, 2)

    def test_tail_semantics_reject_both_or_neither_non_null(self) -> None:
        invalid = (
            {"tail_offset": [0.0, 1.0, 0.0], "tail_bone_index": 0},
            {"tail_offset": None, "tail_bone_index": None},
            {"tail_offset": None},
        )
        for extra in invalid:
            with self.subTest(extra=extra):
                with self.assertRaises(PmxStructuralTransactionPlanError):
                    parse_pmx_structural_transaction_plan_json(
                        _plan({"op": "insert_bone", "local_name": "B", **extra})
                    )

    def test_tail_explicit_null_plus_index_is_valid_semantic_index_mode(self) -> None:
        plan = parse_pmx_structural_transaction_plan_json(
            _plan(
                {
                    "op": "insert_bone",
                    "local_name": "B",
                    "tail_offset": None,
                    "tail_bone_index": 0,
                }
            )
        )
        self.assertIsNone(plan.operations[0].tail_offset)
        self.assertEqual(plan.operations[0].tail_bone_index, 0)

    def test_inherit_flags_require_parent_and_exact_float_weight(self) -> None:
        invalid = (
            {"inherit_rotation": True},
            {
                "inherit_rotation": True,
                "inherit_parent_bone_index": 0,
                "inherit_weight": 1,
            },
            {
                "inherit_parent_bone_index": 0,
                "inherit_weight": 0.5,
            },
        )
        for extra in invalid:
            with self.subTest(extra=extra):
                with self.assertRaises(PmxStructuralTransactionPlanError):
                    parse_pmx_structural_transaction_plan_json(
                        _plan({"op": "insert_bone", "local_name": "B", **extra})
                    )

    def test_local_axes_must_be_paired(self) -> None:
        for field in ("local_axis_x", "local_axis_z"):
            with self.subTest(field=field):
                with self.assertRaises(PmxStructuralTransactionPlanError):
                    parse_pmx_structural_transaction_plan_json(
                        _plan(
                            {
                                "op": "insert_bone",
                                "local_name": "B",
                                field: [1.0, 0.0, 0.0],
                            }
                        )
                    )

    def test_transform_layer_and_external_parent_key_are_signed_int32(self) -> None:
        for field in ("transform_layer", "external_parent_key"):
            for value in (True, 1.0, -(1 << 31) - 1, (1 << 31)):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(PmxStructuralTransactionPlanError):
                        parse_pmx_structural_transaction_plan_json(
                            _plan(
                                {
                                    "op": "insert_bone",
                                    "local_name": "B",
                                    field: value,
                                }
                            )
                        )

        plan = parse_pmx_structural_transaction_plan_json(
            _plan(
                {
                    "op": "insert_bone",
                    "local_name": "B",
                    "transform_layer": -(1 << 31),
                    "external_parent_key": (1 << 31) - 1,
                }
            )
        )
        self.assertEqual(plan.operations[0].transform_layer, -(1 << 31))
        self.assertEqual(plan.operations[0].external_parent_key, (1 << 31) - 1)

    def test_ik_minimal_payload_uses_exact_released_defaults(self) -> None:
        plan = parse_pmx_structural_transaction_plan_json(
            _plan(
                {
                    "op": "insert_bone",
                    "local_name": "B",
                    "ik": {"target_bone_index": 0},
                }
            )
        )
        self.assertEqual(
            plan.operations[0].ik,
            PmxStructuralBoneIk(target_bone_index=0),
        )

    def test_ik_loop_count_is_plain_nonnegative_signed_int32(self) -> None:
        for value in (True, 1.0, -1, (1 << 31)):
            with self.subTest(value=value):
                with self.assertRaises(PmxStructuralTransactionPlanError):
                    parse_pmx_structural_transaction_plan_json(
                        _plan(
                            {
                                "op": "insert_bone",
                                "local_name": "B",
                                "ik": {
                                    "target_bone_index": 0,
                                    "loop_count": value,
                                },
                            }
                        )
                    )

    def test_ik_angle_limit_requires_exact_finite_json_float(self) -> None:
        for value in (1, True, math.inf):
            with self.subTest(value=value):
                text = json.dumps(
                    {
                        "schema_version": 1,
                        "operations": [
                            {
                                "op": "insert_bone",
                                "local_name": "B",
                                "ik": {
                                    "target_bone_index": 0,
                                    "angle_limit": value,
                                },
                            }
                        ],
                    },
                    allow_nan=True,
                    separators=(",", ":"),
                )
                with self.assertRaises(
                    (PmxStructuralTransactionPlanError, PmxStructuralTransactionPlanDecodeError)
                ):
                    parse_pmx_structural_transaction_plan_json(text)

    def test_ik_links_require_objects_and_nonnegative_captured_source_indices(self) -> None:
        invalid_links = (
            1,
            {"bone_index": -1},
            {"bone_index": True},
            {"bone_index": 0, "final_index": 1},
        )
        for link in invalid_links:
            with self.subTest(link=link):
                with self.assertRaises(PmxStructuralTransactionPlanError):
                    parse_pmx_structural_transaction_plan_json(
                        _plan(
                            {
                                "op": "insert_bone",
                                "local_name": "B",
                                "ik": {
                                    "target_bone_index": 0,
                                    "links": [link],
                                },
                            }
                        )
                    )

    def test_ik_link_limits_must_be_paired_exact_three_finite_float_vectors(self) -> None:
        invalid_links = (
            {"bone_index": 0, "lower_limit": [-0.1, -0.2, -0.3]},
            {"bone_index": 0, "upper_limit": [0.1, 0.2, 0.3]},
            {
                "bone_index": 0,
                "lower_limit": [-0.1, -0.2],
                "upper_limit": [0.1, 0.2, 0.3],
            },
            {
                "bone_index": 0,
                "lower_limit": [-1, -0.2, -0.3],
                "upper_limit": [0.1, 0.2, 0.3],
            },
        )
        for link in invalid_links:
            with self.subTest(link=link):
                with self.assertRaises(PmxStructuralTransactionPlanError):
                    parse_pmx_structural_transaction_plan_json(
                        _plan(
                            {
                                "op": "insert_bone",
                                "local_name": "B",
                                "ik": {
                                    "target_bone_index": 0,
                                    "links": [link],
                                },
                            }
                        )
                    )

    def test_ik_and_link_unknown_fields_are_rejected_deterministically(self) -> None:
        cases = (
            (
                {
                    "op": "insert_bone",
                    "local_name": "B",
                    "ik": {"target_bone_index": 0, "writer": "raw"},
                },
                "ik.writer",
            ),
            (
                {
                    "op": "insert_bone",
                    "local_name": "B",
                    "ik": {
                        "target_bone_index": 0,
                        "links": [{"bone_index": 0, "remap": 1}],
                    },
                },
                "ik.links[0].remap",
            ),
        )
        for payload, field in cases:
            with self.subTest(field=field):
                with self.assertRaises(PmxStructuralTransactionPlanError) as caught:
                    parse_pmx_structural_transaction_plan_json(_plan(payload))
                self.assertEqual(caught.exception.field, field)

    def test_duplicate_nested_bone_ik_members_are_rejected(self) -> None:
        text = (
            '{"schema_version":1,"operations":[{"op":"insert_bone",'
            '"local_name":"B","ik":{"target_bone_index":0,'
            '"target_bone_index":1}}]}'
        )
        with self.assertRaisesRegex(
            PmxStructuralTransactionPlanDecodeError,
            "duplicate JSON member",
        ):
            parse_pmx_structural_transaction_plan_json(text)

    def test_bone_position_and_new_id_reuse_existing_insertion_contract(self) -> None:
        plan = parse_pmx_structural_transaction_plan_json(
            _plan(
                {
                    "op": "insert_bone",
                    "local_name": "B",
                    "position": "insert_before",
                    "source_index": 0,
                    "new_id": "bone-a",
                }
            )
        )
        operation = plan.operations[0]
        self.assertEqual(operation.position, "insert_before")
        self.assertEqual(operation.source_index, 0)
        self.assertEqual(operation.new_id, "bone-a")

        with self.assertRaises(PmxStructuralTransactionPlanError):
            parse_pmx_structural_transaction_plan_json(
                _plan(
                    {
                        "op": "insert_bone",
                        "local_name": "B",
                        "source_index": 0,
                    }
                )
            )

    def test_global_new_id_uniqueness_stays_released_request_authority(self) -> None:
        with self.assertRaisesRegex(
            PmxStructuralTransactionPlanError,
            "globally unique",
        ):
            parse_pmx_structural_transaction_plan_json(
                _plan(
                    {"op": "insert_texture", "path": "a.png", "new_id": "same"},
                    {"op": "insert_bone", "local_name": "B", "new_id": "same"},
                )
            )

    def test_mixed_texture_material_bone_order_is_preserved(self) -> None:
        plan = parse_pmx_structural_transaction_plan_json(
            _plan(
                {"op": "insert_texture", "path": "a.png"},
                {"op": "insert_material", "local_name": "M"},
                {"op": "insert_bone", "local_name": "B"},
            )
        )
        self.assertEqual(
            tuple(type(operation).__name__ for operation in plan.operations),
            (
                "PmxStructuralTextureInsertion",
                "PmxStructuralMaterialInsertion",
                "PmxStructuralBoneInsertion",
            ),
        )

    def test_cp11_closes_remaining_schema_one_insertion_dispatch_gap(self) -> None:
        for operation_name in ("insert_morph", "insert_rigid_body"):
            with self.subTest(operation=operation_name):
                with self.assertRaises(PmxStructuralTransactionPlanError) as caught:
                    parse_pmx_structural_transaction_plan_json(
                        _plan({"op": operation_name})
                    )
                self.assertEqual(caught.exception.field, "local_name")
                self.assertNotIn("recognized by schema 1", str(caught.exception))

    def test_cp09_adds_no_new_public_namespace_names(self) -> None:
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

    def test_cp09_preserves_runtime_immutable_discriminator_mapping(self) -> None:
        mapping = transaction_plan._OPERATION_TYPE_BY_DISCRIMINATOR
        self.assertEqual(type(mapping).__name__, "mappingproxy")
        self.assertIs(mapping["insert_bone"], PmxStructuralBoneInsertion)
        with self.assertRaises(TypeError):
            mapping["insert_bone"] = object()  # type: ignore[index]

    def test_cp09_loader_does_not_add_execution_writer_remap_or_final_index_authority(self) -> None:
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
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
