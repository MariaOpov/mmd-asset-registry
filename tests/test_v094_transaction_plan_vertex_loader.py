"""Tests for strict vertex/deform structural transaction-plan authoring."""

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
from mmd_registry.services.structural_reference import PmxStructuralNewReference
from mmd_registry.services.structural_vertex import (
    PmxStructuralVertexBdef1,
    PmxStructuralVertexBdef2,
    PmxStructuralVertexBdef4,
    PmxStructuralVertexInsertion,
    PmxStructuralVertexQdef,
    PmxStructuralVertexSdef,
)


def _plan(*operations: dict[str, object]) -> str:
    return json.dumps(
        {"schema_version": 1, "operations": list(operations)},
        separators=(",", ":"),
    )


def _vertex(deform: object, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "op": "insert_vertex",
        "vertex_position": [1.0, 2.0, 3.0],
        "normal": [0.0, 1.0, 0.0],
        "uv": [0.25, 0.75],
        "additional_uvs": [],
        "deform": deform,
        "edge_scale": 1.0,
    }
    payload.update(overrides)
    return payload


class V094TransactionPlanVertexLoaderTests(unittest.TestCase):
    def test_bdef1_minimal_vertex_maps_exactly(self) -> None:
        plan = parse_pmx_structural_transaction_plan_json(
            _plan(_vertex({"type": "bdef1", "bone_index": 0}))
        )
        self.assertEqual(
            plan.operations,
            (
                PmxStructuralVertexInsertion(
                    vertex_position=(1.0, 2.0, 3.0),
                    normal=(0.0, 1.0, 0.0),
                    uv=(0.25, 0.75),
                    additional_uvs=(),
                    deform=PmxStructuralVertexBdef1(0),
                    edge_scale=1.0,
                ),
            ),
        )

    def test_insert_vertex_requires_all_six_semantic_payload_fields(self) -> None:
        required = (
            "vertex_position",
            "normal",
            "uv",
            "additional_uvs",
            "deform",
            "edge_scale",
        )
        base = _vertex({"type": "bdef1", "bone_index": 0})
        for field in required:
            payload = dict(base)
            payload.pop(field)
            with self.subTest(field=field):
                with self.assertRaises(PmxStructuralTransactionPlanError) as caught:
                    parse_pmx_structural_transaction_plan_json(_plan(payload))
                self.assertEqual(caught.exception.field, field)

    def test_insert_vertex_rejects_unknown_fields_deterministically(self) -> None:
        payload = _vertex(
            {"type": "bdef1", "bone_index": 0},
            writer="raw",
            final_index=1,
        )
        with self.assertRaises(PmxStructuralTransactionPlanError) as caught:
            parse_pmx_structural_transaction_plan_json(_plan(payload))
        self.assertEqual(caught.exception.field, "final_index")

    def test_vertex_vectors_require_exact_lengths_and_exact_finite_floats(self) -> None:
        invalid = (
            ("vertex_position", [0.0, 0.0]),
            ("vertex_position", [0, 0.0, 0.0]),
            ("normal", [0.0, math.inf, 0.0]),
            ("uv", [0.0, 0.0, 0.0]),
        )
        for field, value in invalid:
            with self.subTest(field=field):
                text = json.dumps(
                    {
                        "schema_version": 1,
                        "operations": [
                            _vertex(
                                {"type": "bdef1", "bone_index": 0},
                                **{field: value},
                            )
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

    def test_additional_uvs_accept_zero_through_four_exact_vectors(self) -> None:
        for count in range(5):
            values = [
                [float(i), float(i + 1), float(i + 2), float(i + 3)]
                for i in range(count)
            ]
            with self.subTest(count=count):
                plan = parse_pmx_structural_transaction_plan_json(
                    _plan(
                        _vertex(
                            {"type": "bdef1", "bone_index": 0},
                            additional_uvs=values,
                        )
                    )
                )
                self.assertEqual(len(plan.operations[0].additional_uvs), count)

    def test_additional_uvs_reject_bad_container_count_shape_and_float_types(self) -> None:
        invalid = (
            "not-an-array",
            [[0.0, 0.0, 0.0, 0.0]] * 5,
            [[0.0, 0.0, 0.0]],
            [[0, 0.0, 0.0, 0.0]],
        )
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(PmxStructuralTransactionPlanError):
                    parse_pmx_structural_transaction_plan_json(
                        _plan(
                            _vertex(
                                {"type": "bdef1", "bone_index": 0},
                                additional_uvs=value,
                            )
                        )
                    )

    def test_edge_scale_requires_exact_finite_json_float(self) -> None:
        for value in (1, True, math.inf):
            with self.subTest(value=value):
                text = json.dumps(
                    {
                        "schema_version": 1,
                        "operations": [
                            _vertex(
                                {"type": "bdef1", "bone_index": 0},
                                edge_scale=value,
                            )
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

    def test_deform_requires_exact_object_and_type_discriminator(self) -> None:
        invalid = (
            1,
            {},
            {"type": 1},
            {"type": "linear", "bone_index": 0},
        )
        for deform in invalid:
            with self.subTest(deform=deform):
                with self.assertRaises(PmxStructuralTransactionPlanError):
                    parse_pmx_structural_transaction_plan_json(
                        _plan(_vertex(deform))
                    )

    def test_deform_unknown_fields_are_rejected_deterministically(self) -> None:
        with self.assertRaises(PmxStructuralTransactionPlanError) as caught:
            parse_pmx_structural_transaction_plan_json(
                _plan(
                    _vertex(
                        {
                            "type": "bdef1",
                            "bone_index": 0,
                            "remap": 1,
                            "final_index": 2,
                        }
                    )
                )
            )
        self.assertEqual(caught.exception.field, "deform.final_index")

    def test_bdef1_accepts_source_and_new_bone_references(self) -> None:
        ref = {"ref": "new", "target_kind": "bone", "new_id": "bone-a"}
        plan = parse_pmx_structural_transaction_plan_json(
            _plan(
                {"op": "insert_bone", "local_name": "Provider", "new_id": "bone-a"},
                _vertex({"type": "bdef1", "bone_index": ref}),
            )
        )
        deform = plan.operations[1].deform
        self.assertIsInstance(deform, PmxStructuralVertexBdef1)
        self.assertEqual(
            deform.bone_index,
            PmxStructuralNewReference("bone", "bone-a"),
        )

        sentinel = parse_pmx_structural_transaction_plan_json(
            _plan(_vertex({"type": "bdef1", "bone_index": -1}))
        )
        self.assertEqual(sentinel.operations[0].deform.bone_index, -1)

    def test_vertex_bone_new_reference_must_target_bone(self) -> None:
        ref = {"ref": "new", "target_kind": "texture", "new_id": "tex-a"}
        with self.assertRaises(PmxStructuralTransactionPlanError):
            parse_pmx_structural_transaction_plan_json(
                _plan(_vertex({"type": "bdef1", "bone_index": ref}))
            )

    def test_vertex_bone_reference_rejects_bool_float_and_below_sentinel(self) -> None:
        for value in (True, 1.0, -2):
            with self.subTest(value=value):
                with self.assertRaises(PmxStructuralTransactionPlanError):
                    parse_pmx_structural_transaction_plan_json(
                        _plan(_vertex({"type": "bdef1", "bone_index": value}))
                    )

    def test_bdef2_maps_exact_two_bones_and_weight(self) -> None:
        plan = parse_pmx_structural_transaction_plan_json(
            _plan(
                _vertex(
                    {
                        "type": "bdef2",
                        "bone_indices": [0, 1],
                        "bone_1_weight": 0.25,
                    }
                )
            )
        )
        self.assertEqual(
            plan.operations[0].deform,
            PmxStructuralVertexBdef2((0, 1), 0.25),
        )

    def test_bdef2_rejects_bad_bone_shape_and_non_float_weight(self) -> None:
        invalid = (
            {"type": "bdef2", "bone_indices": [0], "bone_1_weight": 0.5},
            {"type": "bdef2", "bone_indices": [0, 1], "bone_1_weight": 1},
        )
        for deform in invalid:
            with self.subTest(deform=deform):
                with self.assertRaises(PmxStructuralTransactionPlanError):
                    parse_pmx_structural_transaction_plan_json(
                        _plan(_vertex(deform))
                    )

    def test_bdef4_maps_exact_bones_and_weights_without_normalization(self) -> None:
        plan = parse_pmx_structural_transaction_plan_json(
            _plan(
                _vertex(
                    {
                        "type": "bdef4",
                        "bone_indices": [0, 1, -1, 0],
                        "weights": [0.2, 0.2, 0.2, 0.2],
                    }
                )
            )
        )
        deform = plan.operations[0].deform
        self.assertEqual(
            deform,
            PmxStructuralVertexBdef4(
                (0, 1, -1, 0),
                (0.2, 0.2, 0.2, 0.2),
            ),
        )
        self.assertNotEqual(sum(deform.weights), 1.0)

    def test_bdef4_rejects_bad_bone_or_weight_shapes(self) -> None:
        invalid = (
            {
                "type": "bdef4",
                "bone_indices": [0, 1, 2],
                "weights": [0.25, 0.25, 0.25, 0.25],
            },
            {
                "type": "bdef4",
                "bone_indices": [0, 1, 2, 3],
                "weights": [0.25, 0.25, 0.25],
            },
            {
                "type": "bdef4",
                "bone_indices": [0, 1, 2, 3],
                "weights": [0.25, 0.25, 0.25, 1],
            },
        )
        for deform in invalid:
            with self.subTest(deform=deform):
                with self.assertRaises(PmxStructuralTransactionPlanError):
                    parse_pmx_structural_transaction_plan_json(
                        _plan(_vertex(deform))
                    )

    def test_sdef_maps_exact_semantic_payload(self) -> None:
        plan = parse_pmx_structural_transaction_plan_json(
            _plan(
                _vertex(
                    {
                        "type": "sdef",
                        "bone_indices": [0, 1],
                        "bone_1_weight": 0.5,
                        "c": [0.1, 0.2, 0.3],
                        "r0": [0.4, 0.5, 0.6],
                        "r1": [0.7, 0.8, 0.9],
                    }
                )
            )
        )
        self.assertEqual(
            plan.operations[0].deform,
            PmxStructuralVertexSdef(
                (0, 1),
                0.5,
                (0.1, 0.2, 0.3),
                (0.4, 0.5, 0.6),
                (0.7, 0.8, 0.9),
            ),
        )

    def test_sdef_rejects_missing_or_bad_vectors(self) -> None:
        invalid = (
            {
                "type": "sdef",
                "bone_indices": [0, 1],
                "bone_1_weight": 0.5,
                "r0": [0.0, 0.0, 0.0],
                "r1": [0.0, 0.0, 0.0],
            },
            {
                "type": "sdef",
                "bone_indices": [0, 1],
                "bone_1_weight": 0.5,
                "c": [0.0, 0.0],
                "r0": [0.0, 0.0, 0.0],
                "r1": [0.0, 0.0, 0.0],
            },
        )
        for deform in invalid:
            with self.subTest(deform=deform):
                with self.assertRaises(PmxStructuralTransactionPlanError):
                    parse_pmx_structural_transaction_plan_json(
                        _plan(_vertex(deform))
                    )

    def test_qdef_maps_exact_payload_without_version_policy(self) -> None:
        plan = parse_pmx_structural_transaction_plan_json(
            _plan(
                _vertex(
                    {
                        "type": "qdef",
                        "bone_indices": [0, 1, 2, 3],
                        "weights": [0.25, 0.25, 0.25, 0.25],
                    }
                )
            )
        )
        self.assertEqual(
            plan.operations[0].deform,
            PmxStructuralVertexQdef(
                (0, 1, 2, 3),
                (0.25, 0.25, 0.25, 0.25),
            ),
        )

    def test_all_deform_bone_arrays_accept_reviewed_new_bone_references(self) -> None:
        ref = {"ref": "new", "target_kind": "bone", "new_id": "bone-a"}
        deforms = (
            {"type": "bdef2", "bone_indices": [ref, 0], "bone_1_weight": 0.5},
            {
                "type": "bdef4",
                "bone_indices": [ref, 0, 0, 0],
                "weights": [0.25, 0.25, 0.25, 0.25],
            },
            {
                "type": "sdef",
                "bone_indices": [ref, 0],
                "bone_1_weight": 0.5,
                "c": [0.0, 0.0, 0.0],
                "r0": [0.0, 0.0, 0.0],
                "r1": [0.0, 0.0, 0.0],
            },
            {
                "type": "qdef",
                "bone_indices": [ref, 0, 0, 0],
                "weights": [0.25, 0.25, 0.25, 0.25],
            },
        )
        for deform in deforms:
            with self.subTest(type=deform["type"]):
                plan = parse_pmx_structural_transaction_plan_json(
                    _plan(
                        {
                            "op": "insert_bone",
                            "local_name": "Provider",
                            "new_id": "bone-a",
                        },
                        _vertex(deform),
                    )
                )
                vertex = plan.operations[1]
                refs = (
                    vertex.deform.bone_indices
                    if hasattr(vertex.deform, "bone_indices")
                    else ()
                )
                self.assertEqual(refs[0], PmxStructuralNewReference("bone", "bone-a"))

    def test_new_reference_shape_remains_exact_no_final_index(self) -> None:
        invalid_refs = (
            {
                "ref": "new",
                "target_kind": "bone",
                "new_id": "bone-a",
                "final_index": 1,
            },
            {"ref": "old", "target_kind": "bone", "new_id": "bone-a"},
            {"ref": "new", "target_kind": "bone"},
        )
        for ref in invalid_refs:
            with self.subTest(ref=ref):
                with self.assertRaises(PmxStructuralTransactionPlanError):
                    parse_pmx_structural_transaction_plan_json(
                        _plan(_vertex({"type": "bdef1", "bone_index": ref}))
                    )

    def test_duplicate_nested_deform_members_are_rejected(self) -> None:
        text = (
            '{"schema_version":1,"operations":[{"op":"insert_vertex",'
            '"vertex_position":[1.0,2.0,3.0],"normal":[0.0,1.0,0.0],'
            '"uv":[0.0,0.0],"additional_uvs":[],"edge_scale":1.0,'
            '"deform":{"type":"bdef1","bone_index":0,"bone_index":1}}]}'
        )
        with self.assertRaisesRegex(
            PmxStructuralTransactionPlanDecodeError,
            "duplicate JSON member",
        ):
            parse_pmx_structural_transaction_plan_json(text)

    def test_position_source_index_and_new_id_reuse_insertion_contract(self) -> None:
        plan = parse_pmx_structural_transaction_plan_json(
            _plan(
                _vertex(
                    {"type": "bdef1", "bone_index": 0},
                    position="insert_before",
                    source_index=2,
                    new_id="vertex-a",
                )
            )
        )
        operation = plan.operations[0]
        self.assertEqual(operation.position, "insert_before")
        self.assertEqual(operation.source_index, 2)
        self.assertEqual(operation.new_id, "vertex-a")

        with self.assertRaises(PmxStructuralTransactionPlanError):
            parse_pmx_structural_transaction_plan_json(
                _plan(
                    _vertex(
                        {"type": "bdef1", "bone_index": 0},
                        source_index=0,
                    )
                )
            )

    def test_global_new_id_uniqueness_remains_released_request_authority(self) -> None:
        with self.assertRaisesRegex(
            PmxStructuralTransactionPlanError,
            "globally unique",
        ):
            parse_pmx_structural_transaction_plan_json(
                _plan(
                    {"op": "insert_texture", "path": "a.png", "new_id": "same"},
                    _vertex({"type": "bdef1", "bone_index": 0}, new_id="same"),
                )
            )

    def test_mixed_bone_and_vertex_order_is_preserved(self) -> None:
        plan = parse_pmx_structural_transaction_plan_json(
            _plan(
                {"op": "insert_bone", "local_name": "B"},
                _vertex({"type": "bdef1", "bone_index": 0}),
            )
        )
        self.assertEqual(
            tuple(type(operation).__name__ for operation in plan.operations),
            ("PmxStructuralBoneInsertion", "PmxStructuralVertexInsertion"),
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

    def test_cp10_adds_no_new_public_namespace_names(self) -> None:
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

    def test_deform_field_catalog_is_runtime_immutable(self) -> None:
        mapping = transaction_plan._VERTEX_DEFORM_FIELDS_BY_TYPE
        self.assertEqual(type(mapping).__name__, "mappingproxy")
        self.assertEqual(
            tuple(mapping),
            ("bdef1", "bdef2", "bdef4", "sdef", "qdef"),
        )
        with self.assertRaises(TypeError):
            mapping["bdef1"] = frozenset()  # type: ignore[index]

    def test_cp10_preserves_runtime_immutable_operation_mapping(self) -> None:
        mapping = transaction_plan._OPERATION_TYPE_BY_DISCRIMINATOR
        self.assertEqual(type(mapping).__name__, "mappingproxy")
        self.assertIs(mapping["insert_vertex"], PmxStructuralVertexInsertion)

    def test_cp10_loader_does_not_add_execution_writer_remap_version_or_final_index_authority(self) -> None:
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
