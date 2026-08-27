"""Tests for the v0.9.4 strict transform-collection transaction loader."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import mmd_registry
import mmd_registry.pmx as pmx
import mmd_registry.services as services
import mmd_registry.pmx.transaction_plan as transaction_plan
from mmd_registry.pmx.transaction_plan import (
    PmxStructuralTransactionPlanDecodeError,
    PmxStructuralTransactionPlanError,
    load_pmx_structural_transaction_plan,
    parse_pmx_structural_transaction_plan_json,
)
from mmd_registry.services import (
    PmxReferenceTargetKind,
    PmxStructuralCollectionEdit,
)


def _plan(operation: dict[str, object] | None = None) -> str:
    operations = [] if operation is None else [operation]
    return json.dumps(
        {
            "schema_version": 1,
            "operations": operations,
        },
        separators=(",", ":"),
    )


class V094TransactionPlanCollectionLoaderTests(unittest.TestCase):
    def test_empty_operation_array_is_a_valid_noop_plan(self) -> None:
        plan = parse_pmx_structural_transaction_plan_json(_plan())

        self.assertEqual(plan.schema_version, 1)
        self.assertEqual(plan.operations, ())
        self.assertIsNone(plan.expected_source_sha256)

    def test_transform_collection_maps_to_exact_released_dto(self) -> None:
        plan = parse_pmx_structural_transaction_plan_json(
            _plan(
                {
                    "op": "transform_collection",
                    "target_kind": "texture",
                    "old_indices_in_new_order": [2, 0],
                }
            )
        )

        self.assertEqual(
            plan.operations,
            (
                PmxStructuralCollectionEdit(
                    target_kind=PmxReferenceTargetKind.TEXTURE,
                    old_indices_in_new_order=(2, 0),
                ),
            ),
        )

    def test_all_six_collection_target_kinds_are_supported(self) -> None:
        expected = (
            "vertex",
            "texture",
            "material",
            "bone",
            "morph",
            "rigid_body",
        )
        for target_kind in expected:
            with self.subTest(target_kind=target_kind):
                plan = parse_pmx_structural_transaction_plan_json(
                    _plan(
                        {
                            "op": "transform_collection",
                            "target_kind": target_kind,
                            "old_indices_in_new_order": [],
                        }
                    )
                )
                operation = plan.operations[0]
                self.assertIsInstance(operation, PmxStructuralCollectionEdit)
                self.assertEqual(operation.target_kind.value, target_kind)
                self.assertEqual(operation.old_indices_in_new_order, ())

    def test_multiple_collection_operations_preserve_source_order(self) -> None:
        text = json.dumps(
            {
                "schema_version": 1,
                "operations": [
                    {
                        "op": "transform_collection",
                        "target_kind": "texture",
                        "old_indices_in_new_order": [1, 0],
                    },
                    {
                        "op": "transform_collection",
                        "target_kind": "material",
                        "old_indices_in_new_order": [0],
                    },
                ],
            },
            separators=(",", ":"),
        )
        plan = parse_pmx_structural_transaction_plan_json(text)

        self.assertEqual(
            tuple(operation.target_kind.value for operation in plan.operations),
            ("texture", "material"),
        )

    def test_top_level_shape_is_strict(self) -> None:
        for text, field in (
            ('{"schema_version":1}', "operations"),
            ('{"operations":[]}', "schema_version"),
            ('{"schema_version":1,"operations":[],"extra":1}', "extra"),
        ):
            with self.subTest(text=text):
                with self.assertRaises(PmxStructuralTransactionPlanError) as caught:
                    parse_pmx_structural_transaction_plan_json(text)
                self.assertEqual(caught.exception.field, field)

        with self.assertRaisesRegex(
            PmxStructuralTransactionPlanError,
            "top-level JSON value must be an object",
        ):
            parse_pmx_structural_transaction_plan_json("[]")

    def test_duplicate_json_members_are_rejected_at_any_object_depth(self) -> None:
        for text in (
            '{"schema_version":1,"schema_version":1,"operations":[]}',
            (
                '{"schema_version":1,"operations":[{'
                '"op":"transform_collection","op":"transform_collection",'
                '"target_kind":"texture","old_indices_in_new_order":[]'
                '}]}'
            ),
        ):
            with self.subTest(text=text):
                with self.assertRaisesRegex(
                    PmxStructuralTransactionPlanDecodeError,
                    "duplicate JSON member",
                ):
                    parse_pmx_structural_transaction_plan_json(text)

    def test_schema_version_requires_exact_integer_one(self) -> None:
        for value in ("true", "1.0", "2"):
            with self.subTest(value=value):
                with self.assertRaises(PmxStructuralTransactionPlanError) as caught:
                    parse_pmx_structural_transaction_plan_json(
                        f'{{"schema_version":{value},"operations":[]}}'
                    )
                self.assertEqual(caught.exception.field, "schema_version")

    def test_operations_must_be_an_array_of_objects(self) -> None:
        with self.assertRaises(PmxStructuralTransactionPlanError) as caught:
            parse_pmx_structural_transaction_plan_json(
                '{"schema_version":1,"operations":{}}'
            )
        self.assertEqual(caught.exception.field, "operations")

        with self.assertRaisesRegex(
            PmxStructuralTransactionPlanError,
            "operation must be a JSON object",
        ):
            parse_pmx_structural_transaction_plan_json(
                '{"schema_version":1,"operations":[1]}'
            )

    def test_operation_discriminator_is_required_string_and_known(self) -> None:
        cases = (
            (
                '{"schema_version":1,"operations":[{}]}',
                "field is required",
            ),
            (
                '{"schema_version":1,"operations":[{"op":1}]}',
                "JSON string",
            ),
            (
                '{"schema_version":1,"operations":[{"op":"unknown"}]}',
                "unsupported operation name",
            ),
        )
        for text, message in cases:
            with self.subTest(text=text):
                with self.assertRaisesRegex(
                    PmxStructuralTransactionPlanError,
                    message,
                ) as caught:
                    parse_pmx_structural_transaction_plan_json(text)
                self.assertEqual(caught.exception.operation_index, 0)
                self.assertEqual(caught.exception.field, "op")

    def test_unimplemented_insertion_discriminators_fail_closed_until_later_checkpoints(self) -> None:
        for operation_name in (
            "insert_bone",
            "insert_morph",
            "insert_rigid_body",
            "insert_vertex",
        ):
            with self.subTest(operation=operation_name):
                with self.assertRaisesRegex(
                    PmxStructuralTransactionPlanError,
                    "recognized by schema 1",
                ) as caught:
                    parse_pmx_structural_transaction_plan_json(
                        _plan({"op": operation_name})
                    )
                self.assertEqual(caught.exception.operation_type, operation_name)
                self.assertEqual(caught.exception.field, "op")

    def test_transform_collection_rejects_unknown_or_missing_fields(self) -> None:
        with self.assertRaises(PmxStructuralTransactionPlanError) as caught:
            parse_pmx_structural_transaction_plan_json(
                _plan(
                    {
                        "op": "transform_collection",
                        "target_kind": "texture",
                        "old_indices_in_new_order": [],
                        "remap": [],
                    }
                )
            )
        self.assertEqual(caught.exception.field, "remap")

        for missing in ("target_kind", "old_indices_in_new_order"):
            operation = {
                "op": "transform_collection",
                "target_kind": "texture",
                "old_indices_in_new_order": [],
            }
            del operation[missing]
            with self.subTest(missing=missing):
                with self.assertRaises(PmxStructuralTransactionPlanError) as caught:
                    parse_pmx_structural_transaction_plan_json(_plan(operation))
                self.assertEqual(caught.exception.field, missing)

    def test_target_kind_requires_exact_supported_string(self) -> None:
        for target_kind in ("display_frame", "Texture", "", 1, True):
            with self.subTest(target_kind=target_kind):
                with self.assertRaises(PmxStructuralTransactionPlanError) as caught:
                    parse_pmx_structural_transaction_plan_json(
                        _plan(
                            {
                                "op": "transform_collection",
                                "target_kind": target_kind,
                                "old_indices_in_new_order": [],
                            }
                        )
                    )
                self.assertEqual(caught.exception.field, "target_kind")

    def test_source_indices_require_unique_nonnegative_plain_integers(self) -> None:
        invalid = (
            "not-an-array",
            [0, True],
            [0, 1.0],
            [-1],
            [1, 1],
        )
        for indices in invalid:
            with self.subTest(indices=indices):
                with self.assertRaises(PmxStructuralTransactionPlanError):
                    parse_pmx_structural_transaction_plan_json(
                        _plan(
                            {
                                "op": "transform_collection",
                                "target_kind": "texture",
                                "old_indices_in_new_order": indices,
                            }
                        )
                    )

    def test_duplicate_collection_target_is_rejected_by_released_request_authority(self) -> None:
        text = json.dumps(
            {
                "schema_version": 1,
                "operations": [
                    {
                        "op": "transform_collection",
                        "target_kind": "texture",
                        "old_indices_in_new_order": [],
                    },
                    {
                        "op": "transform_collection",
                        "target_kind": "texture",
                        "old_indices_in_new_order": [],
                    },
                ],
            },
            separators=(",", ":"),
        )
        with self.assertRaisesRegex(
            PmxStructuralTransactionPlanError,
            "cannot repeat one PmxStructuralCollectionEdit target_kind",
        ):
            parse_pmx_structural_transaction_plan_json(text)

    def test_expected_source_sha256_is_strict_and_preserved(self) -> None:
        digest = "a" * 64
        plan = parse_pmx_structural_transaction_plan_json(
            json.dumps(
                {
                    "schema_version": 1,
                    "expected_source_sha256": digest,
                    "operations": [],
                },
                separators=(",", ":"),
            )
        )
        self.assertEqual(plan.expected_source_sha256, digest)

        for invalid in ("A" * 64, "a" * 63, "", 1):
            with self.subTest(invalid=invalid):
                text = json.dumps(
                    {
                        "schema_version": 1,
                        "expected_source_sha256": invalid,
                        "operations": [],
                    },
                    separators=(",", ":"),
                )
                with self.assertRaises(PmxStructuralTransactionPlanError) as caught:
                    parse_pmx_structural_transaction_plan_json(text)
                self.assertEqual(caught.exception.field, "expected_source_sha256")

    def test_nonstandard_numeric_constants_and_invalid_json_are_rejected(self) -> None:
        for text in (
            '{"schema_version":1,"operations":[],"x":NaN}',
            '{"schema_version":1,"operations":[],"x":Infinity}',
            "{",
            "",
        ):
            with self.subTest(text=text):
                with self.assertRaises(PmxStructuralTransactionPlanDecodeError):
                    parse_pmx_structural_transaction_plan_json(text)

    def test_file_loader_is_utf8_only_and_reuses_text_parser(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            path.write_text(
                _plan(
                    {
                        "op": "transform_collection",
                        "target_kind": "bone",
                        "old_indices_in_new_order": [0],
                    }
                ),
                encoding="utf-8",
            )
            plan = load_pmx_structural_transaction_plan(path)
            self.assertEqual(plan.operations[0].target_kind.value, "bone")

            bad = Path(directory) / "bad.json"
            bad.write_bytes(b"\xff")
            with self.assertRaises(PmxStructuralTransactionPlanDecodeError):
                load_pmx_structural_transaction_plan(bad)

    def test_loader_exports_are_additive_and_not_promoted_to_legacy_roots(self) -> None:
        cp07_exports = (
            "PmxStructuralTransactionPlanError",
            "PmxStructuralTransactionPlanDecodeError",
            "parse_pmx_structural_transaction_plan_json",
            "load_pmx_structural_transaction_plan",
        )
        for name in cp07_exports:
            self.assertIn(name, transaction_plan.__all__)

        for root in (mmd_registry, pmx, services):
            for name in transaction_plan.__all__:
                self.assertFalse(hasattr(root, name), (root.__name__, name))

    def test_collection_loader_does_not_own_execution_or_remap_authority(self) -> None:
        module_source = __import__("inspect").getsource(transaction_plan)
        for forbidden in (
            "remap_pmx_references",
            "write_pmx_structural_output",
            "_write_structural_transaction",
            "_plan_structural_transaction",
            "publication_callback",
            "preview_structural_transaction(",
            "apply_structural_transaction(",
        ):
            self.assertNotIn(forbidden, module_source)


if __name__ == "__main__":
    unittest.main()
