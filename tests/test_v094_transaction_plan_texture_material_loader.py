"""Tests for strict texture/material transaction-plan authoring."""

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
from mmd_registry.services import (
    PmxReferenceTargetKind,
    PmxStructuralCollectionEdit,
)
from mmd_registry.services.structural_material import (
    PmxStructuralMaterialInsertion,
)
from mmd_registry.services.structural_reference import (
    PmxStructuralNewReference,
)
from mmd_registry.services.structural_texture import (
    PmxStructuralTextureInsertion,
)


def _plan(*operations: dict[str, object]) -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "operations": list(operations),
        },
        separators=(",", ":"),
    )


class V094TransactionPlanTextureMaterialLoaderTests(unittest.TestCase):
    def test_texture_minimal_payload_uses_released_dto_defaults(self) -> None:
        plan = parse_pmx_structural_transaction_plan_json(
            _plan({"op": "insert_texture", "path": "tex/diffuse.png"})
        )
        self.assertEqual(
            plan.operations,
            (PmxStructuralTextureInsertion(path="tex/diffuse.png"),),
        )

    def test_texture_insert_before_and_new_id_are_preserved(self) -> None:
        plan = parse_pmx_structural_transaction_plan_json(
            _plan(
                {
                    "op": "insert_texture",
                    "path": "tex/a.png",
                    "position": "insert_before",
                    "source_index": 3,
                    "new_id": "tex-a",
                }
            )
        )
        operation = plan.operations[0]
        self.assertEqual(operation.position, "insert_before")
        self.assertEqual(operation.source_index, 3)
        self.assertEqual(operation.new_id, "tex-a")

    def test_texture_requires_exact_path_and_rejects_unknown_fields(self) -> None:
        for payload, field in (
            ({"op": "insert_texture"}, "path"),
            ({"op": "insert_texture", "path": 1}, "path"),
            ({"op": "insert_texture", "path": "x", "writer": "raw"}, "writer"),
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(PmxStructuralTransactionPlanError) as caught:
                    parse_pmx_structural_transaction_plan_json(_plan(payload))
                self.assertEqual(caught.exception.field, field)

    def test_texture_position_and_source_index_contract_is_exact(self) -> None:
        cases = (
            (
                {"op": "insert_texture", "path": "x", "position": "append", "source_index": 0},
                "source_index",
            ),
            (
                {"op": "insert_texture", "path": "x", "position": "insert_before"},
                "source_index",
            ),
            (
                {"op": "insert_texture", "path": "x", "position": "insert_before", "source_index": True},
                "source_index",
            ),
            (
                {"op": "insert_texture", "path": "x", "position": "insert_before", "source_index": -1},
                "source_index",
            ),
            (
                {"op": "insert_texture", "path": "x", "position": "after"},
                "position",
            ),
        )
        for payload, field in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(PmxStructuralTransactionPlanError) as caught:
                    parse_pmx_structural_transaction_plan_json(_plan(payload))
                self.assertEqual(caught.exception.field, field)

    def test_texture_new_id_is_optional_but_exact_string_when_authored(self) -> None:
        with self.assertRaises(PmxStructuralTransactionPlanError):
            parse_pmx_structural_transaction_plan_json(
                _plan({"op": "insert_texture", "path": "x", "new_id": None})
            )
        with self.assertRaisesRegex(
            PmxStructuralTransactionPlanError,
            "new_id must contain",
        ):
            parse_pmx_structural_transaction_plan_json(
                _plan({"op": "insert_texture", "path": "x", "new_id": "1bad"})
            )

    def test_material_minimal_payload_uses_exact_released_defaults(self) -> None:
        plan = parse_pmx_structural_transaction_plan_json(
            _plan({"op": "insert_material", "local_name": "Body"})
        )
        self.assertEqual(
            plan.operations,
            (PmxStructuralMaterialInsertion(local_name="Body"),),
        )

    def test_material_full_scalar_and_vector_payload_maps_exactly(self) -> None:
        payload = {
            "op": "insert_material",
            "local_name": "Body",
            "universal_name": "Body EN",
            "memo": "memo",
            "texture_index": 2,
            "sphere_texture_index": -1,
            "sphere_mode": 1,
            "toon_reference_mode": "texture",
            "toon_reference_index": 4,
            "diffuse": [0.1, 0.2, 0.3, 0.4],
            "specular": [0.5, 0.6, 0.7],
            "specular_strength": 0.8,
            "ambient": [0.2, 0.3, 0.4],
            "drawing_flags": 31,
            "edge_color": [0.0, 0.1, 0.2, 1.0],
            "edge_scale": 1.5,
            "position": "insert_before",
            "source_index": 2,
            "new_id": "material-body",
        }
        plan = parse_pmx_structural_transaction_plan_json(_plan(payload))
        self.assertEqual(
            plan.operations[0],
            PmxStructuralMaterialInsertion(
                local_name="Body",
                universal_name="Body EN",
                memo="memo",
                texture_index=2,
                sphere_texture_index=-1,
                sphere_mode=1,
                toon_reference_mode="texture",
                toon_reference_index=4,
                diffuse=(0.1, 0.2, 0.3, 0.4),
                specular=(0.5, 0.6, 0.7),
                specular_strength=0.8,
                ambient=(0.2, 0.3, 0.4),
                drawing_flags=31,
                edge_color=(0.0, 0.1, 0.2, 1.0),
                edge_scale=1.5,
                position="insert_before",
                source_index=2,
                new_id="material-body",
            ),
        )

    def test_material_texture_reference_fields_accept_existing_integers(self) -> None:
        plan = parse_pmx_structural_transaction_plan_json(
            _plan(
                {
                    "op": "insert_material",
                    "local_name": "M",
                    "texture_index": -1,
                    "sphere_texture_index": 0,
                    "toon_reference_index": 1,
                }
            )
        )
        operation = plan.operations[0]
        self.assertEqual(operation.texture_index, -1)
        self.assertEqual(operation.sphere_texture_index, 0)
        self.assertEqual(operation.toon_reference_index, 1)

    def test_material_texture_reference_fields_accept_new_texture_references(self) -> None:
        ref = {"ref": "new", "target_kind": "texture", "new_id": "tex-a"}
        plan = parse_pmx_structural_transaction_plan_json(
            _plan(
                {
                    "op": "insert_texture",
                    "path": "a.png",
                    "new_id": "tex-a",
                },
                {
                    "op": "insert_material",
                    "local_name": "M",
                    "texture_index": ref,
                    "sphere_texture_index": ref,
                    "toon_reference_index": ref,
                },
            )
        )
        material = plan.operations[1]
        expected = PmxStructuralNewReference(
            target_kind="texture",
            new_id="tex-a",
        )
        self.assertEqual(material.texture_index, expected)
        self.assertEqual(material.sphere_texture_index, expected)
        self.assertEqual(material.toon_reference_index, expected)

    def test_new_reference_shape_is_exact_and_texture_bounded(self) -> None:
        invalid_refs = (
            {"ref": "old", "target_kind": "texture", "new_id": "tex-a"},
            {"ref": "new", "target_kind": "bone", "new_id": "tex-a"},
            {"ref": "new", "target_kind": "texture", "new_id": "tex-a", "final_index": 3},
            {"ref": "new", "target_kind": "texture"},
        )
        for value in invalid_refs:
            with self.subTest(value=value):
                with self.assertRaises(PmxStructuralTransactionPlanError):
                    parse_pmx_structural_transaction_plan_json(
                        _plan(
                            {
                                "op": "insert_material",
                                "local_name": "M",
                                "texture_index": value,
                            }
                        )
                    )

    def test_material_shared_toon_requires_plain_integer_zero_through_nine(self) -> None:
        valid = parse_pmx_structural_transaction_plan_json(
            _plan(
                {
                    "op": "insert_material",
                    "local_name": "M",
                    "toon_reference_mode": "shared",
                    "toon_reference_index": 9,
                }
            )
        )
        self.assertEqual(valid.operations[0].toon_reference_index, 9)

        for value in (None, True, 1.0, -1, 10, {"ref": "new", "target_kind": "texture", "new_id": "x"}):
            payload = {
                "op": "insert_material",
                "local_name": "M",
                "toon_reference_mode": "shared",
            }
            if value is not None:
                payload["toon_reference_index"] = value
            with self.subTest(value=value):
                with self.assertRaises(PmxStructuralTransactionPlanError):
                    parse_pmx_structural_transaction_plan_json(_plan(payload))

    def test_material_vectors_require_exact_lengths_and_exact_finite_floats(self) -> None:
        invalid = (
            ("diffuse", [0.0, 0.0, 0.0]),
            ("diffuse", [0, 0.0, 0.0, 1.0]),
            ("specular", [0.0, 0.0, 0.0, 0.0]),
            ("ambient", [0.0, 0.0, math.inf]),
            ("edge_color", "not-an-array"),
        )
        for field, value in invalid:
            with self.subTest(field=field, value=value):
                text = json.dumps(
                    {
                        "schema_version": 1,
                        "operations": [
                            {
                                "op": "insert_material",
                                "local_name": "M",
                                field: value,
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

    def test_material_float_scalars_reject_integer_bool_and_nonfinite(self) -> None:
        for field in ("specular_strength", "edge_scale"):
            for value in (1, True, math.inf):
                with self.subTest(field=field, value=value):
                    text = json.dumps(
                        {
                            "schema_version": 1,
                            "operations": [
                                {
                                    "op": "insert_material",
                                    "local_name": "M",
                                    field: value,
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

    def test_material_integer_fields_reject_bool_float_and_out_of_bounds(self) -> None:
        invalid = (
            ("texture_index", True),
            ("texture_index", 1.0),
            ("texture_index", -2),
            ("sphere_texture_index", -2),
            ("sphere_mode", True),
            ("sphere_mode", 4),
            ("drawing_flags", True),
            ("drawing_flags", -1),
            ("drawing_flags", 256),
        )
        for field, value in invalid:
            with self.subTest(field=field, value=value):
                with self.assertRaises(PmxStructuralTransactionPlanError):
                    parse_pmx_structural_transaction_plan_json(
                        _plan(
                            {
                                "op": "insert_material",
                                "local_name": "M",
                                field: value,
                            }
                        )
                    )

    def test_material_string_fields_are_not_coerced(self) -> None:
        for field in ("local_name", "universal_name", "memo", "toon_reference_mode"):
            payload: dict[str, object] = {
                "op": "insert_material",
                "local_name": "M",
                field: 1,
            }
            with self.subTest(field=field):
                with self.assertRaises(PmxStructuralTransactionPlanError):
                    parse_pmx_structural_transaction_plan_json(_plan(payload))

    def test_material_position_and_source_index_contract_matches_texture(self) -> None:
        with self.assertRaises(PmxStructuralTransactionPlanError) as caught:
            parse_pmx_structural_transaction_plan_json(
                _plan(
                    {
                        "op": "insert_material",
                        "local_name": "M",
                        "source_index": 0,
                    }
                )
            )
        self.assertEqual(caught.exception.field, "source_index")

        plan = parse_pmx_structural_transaction_plan_json(
            _plan(
                {
                    "op": "insert_material",
                    "local_name": "M",
                    "position": "insert_before",
                    "source_index": 0,
                }
            )
        )
        self.assertEqual(plan.operations[0].position, "insert_before")
        self.assertEqual(plan.operations[0].source_index, 0)

    def test_material_new_id_uses_released_identity_validation(self) -> None:
        with self.assertRaisesRegex(
            PmxStructuralTransactionPlanError,
            "new_id must contain",
        ):
            parse_pmx_structural_transaction_plan_json(
                _plan(
                    {
                        "op": "insert_material",
                        "local_name": "M",
                        "new_id": "_bad",
                    }
                )
            )

    def test_global_new_id_uniqueness_remains_released_request_authority(self) -> None:
        with self.assertRaisesRegex(
            PmxStructuralTransactionPlanError,
            "globally unique",
        ):
            parse_pmx_structural_transaction_plan_json(
                _plan(
                    {
                        "op": "insert_texture",
                        "path": "a.png",
                        "new_id": "same",
                    },
                    {
                        "op": "insert_material",
                        "local_name": "M",
                        "new_id": "same",
                    },
                )
            )

    def test_mixed_collection_texture_material_order_is_preserved(self) -> None:
        plan = parse_pmx_structural_transaction_plan_json(
            _plan(
                {
                    "op": "transform_collection",
                    "target_kind": "bone",
                    "old_indices_in_new_order": [],
                },
                {"op": "insert_texture", "path": "a.png"},
                {"op": "insert_material", "local_name": "M"},
            )
        )
        self.assertIsInstance(plan.operations[0], PmxStructuralCollectionEdit)
        self.assertIsInstance(plan.operations[1], PmxStructuralTextureInsertion)
        self.assertIsInstance(plan.operations[2], PmxStructuralMaterialInsertion)
        self.assertEqual(plan.operations[0].target_kind, PmxReferenceTargetKind.BONE)

    def test_cp11_closes_remaining_schema_one_insertion_dispatch_gap(self) -> None:
        for operation_name in ("insert_morph", "insert_rigid_body"):
            with self.subTest(operation=operation_name):
                with self.assertRaises(PmxStructuralTransactionPlanError) as caught:
                    parse_pmx_structural_transaction_plan_json(
                        _plan({"op": operation_name})
                    )
                self.assertEqual(caught.exception.field, "local_name")
                self.assertNotIn("recognized by schema 1", str(caught.exception))

    def test_texture_and_material_duplicate_nested_members_are_rejected(self) -> None:
        texts = (
            '{"schema_version":1,"operations":[{"op":"insert_texture","path":"a","path":"b"}]}',
            (
                '{"schema_version":1,"operations":[{"op":"insert_material",'
                '"local_name":"M","texture_index":{"ref":"new","ref":"new",'
                '"target_kind":"texture","new_id":"x"}}]}'
            ),
        )
        for text in texts:
            with self.subTest(text=text):
                with self.assertRaisesRegex(
                    PmxStructuralTransactionPlanDecodeError,
                    "duplicate JSON member",
                ):
                    parse_pmx_structural_transaction_plan_json(text)

    def test_material_unknown_fields_are_rejected_deterministically(self) -> None:
        with self.assertRaises(PmxStructuralTransactionPlanError) as caught:
            parse_pmx_structural_transaction_plan_json(
                _plan(
                    {
                        "op": "insert_material",
                        "local_name": "M",
                        "writer": "raw",
                        "final_index": 1,
                    }
                )
            )
        self.assertEqual(caught.exception.field, "final_index")

    def test_cp08_adds_no_new_public_namespace_names(self) -> None:
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

    def test_discriminator_mapping_is_runtime_immutable(self) -> None:
        mapping = transaction_plan._OPERATION_TYPE_BY_DISCRIMINATOR
        original = mapping["insert_texture"]

        with self.assertRaises(TypeError):
            mapping["insert_texture"] = object()  # type: ignore[index]

        self.assertIs(mapping["insert_texture"], original)

    def test_cp08_loader_does_not_add_execution_writer_or_remap_authority(self) -> None:
        module_source = __import__("inspect").getsource(transaction_plan)
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
            self.assertNotIn(forbidden, module_source)


if __name__ == "__main__":
    unittest.main()
