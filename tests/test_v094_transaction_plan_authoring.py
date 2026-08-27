"""Tests for CP13 transaction-plan templates, catalog metadata, and explain."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import inspect
import json
from types import MappingProxyType
import unittest

import mmd_registry
import mmd_registry.pmx as pmx
import mmd_registry.services as services
import mmd_registry.pmx.transaction_plan as transaction_plan
from mmd_registry.pmx.transaction_plan import (
    PMX_STRUCTURAL_TRANSACTION_PLAN_SCHEMA_VERSION,
    PmxStructuralTransactionOperationExplanation,
    PmxStructuralTransactionOperationType,
    PmxStructuralTransactionPlan,
    PmxStructuralTransactionPlanExplanation,
    explain_pmx_structural_transaction_plan,
    get_pmx_structural_transaction_operation_catalog,
    get_pmx_structural_transaction_plan_template,
    parse_pmx_structural_transaction_plan_json,
    render_pmx_structural_transaction_plan_json,
)
import mmd_registry.services.structural_transaction as transactions


EXPECTED_PUBLIC_EXPORTS = (
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
    "get_pmx_structural_transaction_plan_template",
    "PmxStructuralTransactionOperationExplanation",
    "PmxStructuralTransactionPlanExplanation",
    "explain_pmx_structural_transaction_plan",
)


def _load(payload: dict[str, object]) -> PmxStructuralTransactionPlan:
    return parse_pmx_structural_transaction_plan_json(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )


class V094TransactionPlanAuthoringTests(unittest.TestCase):
    def test_catalog_entries_gain_deterministic_top_level_field_metadata(self) -> None:
        catalog = get_pmx_structural_transaction_operation_catalog()
        self.assertIsInstance(
            transaction_plan._OPERATION_FIELDS_BY_TYPE,
            MappingProxyType,
        )

        for entry in catalog.operations:
            with self.subTest(operation=entry.operation_type.value):
                allowed = transaction_plan._OPERATION_FIELDS_BY_TYPE[
                    entry.operation_type
                ]
                self.assertEqual(entry.field_names[0], "op")
                self.assertEqual(
                    entry.field_names[1:],
                    tuple(sorted(allowed - {"op"})),
                )
                self.assertEqual(set(entry.field_names), set(allowed))
                self.assertEqual(
                    entry.to_dict()["fields"],
                    list(entry.field_names),
                )

    def test_catalog_richness_does_not_change_cp06_constructor_shape(self) -> None:
        parameters = tuple(
            inspect.signature(
                transaction_plan.PmxStructuralTransactionOperationCatalogEntry
            ).parameters
        )
        self.assertEqual(parameters, ("operation_type", "purpose"))

    def test_catalog_field_metadata_is_immutable_and_repeatable(self) -> None:
        first = get_pmx_structural_transaction_operation_catalog()
        second = get_pmx_structural_transaction_operation_catalog()
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(
            tuple(entry.field_names for entry in first.operations),
            tuple(entry.field_names for entry in second.operations),
        )
        with self.assertRaises(TypeError):
            transaction_plan._OPERATION_FIELDS_BY_TYPE[
                PmxStructuralTransactionOperationType.INSERT_TEXTURE
            ] = frozenset()  # type: ignore[index]

    def test_template_is_safe_empty_schema_one_plan(self) -> None:
        template = get_pmx_structural_transaction_plan_template()
        self.assertEqual(
            template,
            PmxStructuralTransactionPlan(operations=()),
        )
        self.assertEqual(
            render_pmx_structural_transaction_plan_json(template),
            '{"schema_version":1,"operations":[]}\n',
        )
        self.assertEqual(
            parse_pmx_structural_transaction_plan_json(
                render_pmx_structural_transaction_plan_json(template)
            ),
            template,
        )

    def test_template_can_declare_identity_without_source_io(self) -> None:
        source_hash = "a" * 64
        template = get_pmx_structural_transaction_plan_template(
            expected_source_sha256=source_hash
        )
        self.assertEqual(template.expected_source_sha256, source_hash)
        self.assertEqual(template.operations, ())

        with self.assertRaises(ValueError):
            get_pmx_structural_transaction_plan_template(
                expected_source_sha256="A" * 64
            )

    def test_template_surface_cannot_guess_or_create_operations(self) -> None:
        signature = inspect.signature(get_pmx_structural_transaction_plan_template)
        self.assertEqual(tuple(signature.parameters), ("expected_source_sha256",))
        parameter = signature.parameters["expected_source_sha256"]
        self.assertIs(parameter.kind, inspect.Parameter.KEYWORD_ONLY)

    def test_explain_preserves_operation_order_and_catalog_purpose(self) -> None:
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
        explanation = explain_pmx_structural_transaction_plan(plan)
        self.assertEqual(explanation.operation_count, 3)
        self.assertEqual(
            tuple(item.operation_type.value for item in explanation.operations),
            ("insert_texture", "insert_bone", "insert_rigid_body"),
        )

        catalog = {
            entry.operation_type: entry
            for entry in get_pmx_structural_transaction_operation_catalog().operations
        }
        for item in explanation.operations:
            self.assertEqual(item.purpose, catalog[item.operation_type].purpose)

    def test_explain_reports_canonical_field_order_without_values(self) -> None:
        plan = _load(
            {
                "schema_version": 1,
                "operations": [
                    {
                        "op": "insert_texture",
                        "path": "private/secret-texture.png",
                        "position": "insert_before",
                        "source_index": 3,
                        "new_id": "private-texture-id",
                    }
                ],
            }
        )
        item = explain_pmx_structural_transaction_plan(plan).operations[0]
        self.assertEqual(
            item.canonical_fields,
            ("path", "position", "source_index", "new_id"),
        )
        rendered = json.dumps(
            item.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        self.assertNotIn("private/secret-texture.png", rendered)
        self.assertNotIn("private-texture-id", rendered)

    def test_explain_hides_expected_source_hash(self) -> None:
        source_hash = "b" * 64
        plan = get_pmx_structural_transaction_plan_template(
            expected_source_sha256=source_hash
        )
        explanation = explain_pmx_structural_transaction_plan(plan)
        self.assertTrue(explanation.expected_source_sha256_declared)
        rendered = json.dumps(
            explanation.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        self.assertNotIn(source_hash, rendered)

    def test_explain_is_deterministic_and_does_not_mutate_plan(self) -> None:
        plan = _load(
            {
                "schema_version": 1,
                "operations": [
                    {"op": "insert_texture", "path": "a.png"},
                    {"op": "insert_morph", "local_name": "M", "morph_type": "vertex"},
                ],
            }
        )
        before = render_pmx_structural_transaction_plan_json(plan)
        first = explain_pmx_structural_transaction_plan(plan)
        second = explain_pmx_structural_transaction_plan(plan)
        self.assertEqual(first, second)
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(render_pmx_structural_transaction_plan_json(plan), before)

    def test_explanation_models_are_frozen_and_strict(self) -> None:
        plan = _load(
            {
                "schema_version": 1,
                "operations": [{"op": "insert_texture", "path": "a.png"}],
            }
        )
        explanation = explain_pmx_structural_transaction_plan(plan)
        operation = explanation.operations[0]

        with self.assertRaises(FrozenInstanceError):
            explanation.schema_version = 2  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            operation.purpose = "changed"  # type: ignore[misc]

        with self.assertRaises(ValueError):
            PmxStructuralTransactionOperationExplanation(
                operation_index=-1,
                operation_type=PmxStructuralTransactionOperationType.INSERT_TEXTURE,
                purpose="Insert texture.",
                canonical_fields=("path",),
            )
        with self.assertRaises(TypeError):
            PmxStructuralTransactionOperationExplanation(
                operation_index=0,
                operation_type="insert_texture",  # type: ignore[arg-type]
                purpose="Insert texture.",
                canonical_fields=("path",),
            )
        with self.assertRaises(TypeError):
            PmxStructuralTransactionPlanExplanation(
                schema_version=PMX_STRUCTURAL_TRANSACTION_PLAN_SCHEMA_VERSION,
                expected_source_sha256_declared=True,
                operations=[],  # type: ignore[arg-type]
            )

    def test_explain_requires_typed_plan(self) -> None:
        with self.assertRaisesRegex(TypeError, "PmxStructuralTransactionPlan"):
            explain_pmx_structural_transaction_plan(object())  # type: ignore[arg-type]

    def test_cp13_public_namespace_is_exact_additive_and_not_root_promoted(
        self,
    ) -> None:
        self.assertEqual(transaction_plan.__all__, EXPECTED_PUBLIC_EXPORTS)
        self.assertEqual(
            len(transaction_plan.__all__),
            len(set(transaction_plan.__all__)),
        )

        new_names = EXPECTED_PUBLIC_EXPORTS[-4:]
        for root in (mmd_registry, pmx, services):
            for name in new_names:
                self.assertFalse(hasattr(root, name), (root.__name__, name))

    def test_cp13_helpers_add_no_execution_filesystem_or_remap_authority(self) -> None:
        sources = (
            inspect.getsource(get_pmx_structural_transaction_plan_template),
            inspect.getsource(explain_pmx_structural_transaction_plan),
        )
        for source in sources:
            for forbidden in (
                "preview_structural_transaction",
                "apply_structural_transaction",
                "write_pmx",
                "remap",
                "final_index",
                "read_text",
                "write_text",
                "open(",
            ):
                self.assertNotIn(forbidden, source)

    def test_released_transaction_execution_namespace_remains_unchanged(self) -> None:
        self.assertEqual(
            transactions.__all__,
            (
                "PmxStructuralTransactionOperation",
                "PmxStructuralTransactionRequest",
                "PmxStructuralTransactionPreviewResult",
                "preview_structural_transaction",
                "apply_structural_transaction",
            ),
        )


if __name__ == "__main__":
    unittest.main()
