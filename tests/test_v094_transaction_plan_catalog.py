"""Tests for the v0.9.4 transaction operation discriminator catalog."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
import typing
import unittest

import mmd_registry
import mmd_registry.pmx as pmx
import mmd_registry.services as services
import mmd_registry.pmx.transaction_plan as transaction_plan
from mmd_registry.pmx.transaction_plan import (
    PMX_STRUCTURAL_TRANSACTION_PLAN_SCHEMA_VERSION,
    PmxStructuralTransactionOperationCatalog,
    PmxStructuralTransactionOperationCatalogEntry,
    PmxStructuralTransactionOperationType,
    get_pmx_structural_transaction_operation_catalog,
)
from mmd_registry.services import PmxStructuralCollectionEdit
from mmd_registry.services.structural_bone import PmxStructuralBoneInsertion
from mmd_registry.services.structural_material import PmxStructuralMaterialInsertion
from mmd_registry.services.structural_morph import PmxStructuralMorphInsertion
from mmd_registry.services.structural_rigid_body import PmxStructuralRigidBodyInsertion
from mmd_registry.services.structural_texture import PmxStructuralTextureInsertion
from mmd_registry.services.structural_transaction import (
    PmxStructuralTransactionOperation,
)
from mmd_registry.services.structural_vertex import PmxStructuralVertexInsertion


EXPECTED_DISCRIMINATORS = (
    "transform_collection",
    "insert_texture",
    "insert_material",
    "insert_bone",
    "insert_morph",
    "insert_rigid_body",
    "insert_vertex",
)

EXPECTED_DTO_TYPES = (
    PmxStructuralCollectionEdit,
    PmxStructuralTextureInsertion,
    PmxStructuralMaterialInsertion,
    PmxStructuralBoneInsertion,
    PmxStructuralMorphInsertion,
    PmxStructuralRigidBodyInsertion,
    PmxStructuralVertexInsertion,
)


class V094TransactionPlanCatalogTests(unittest.TestCase):
    def test_discriminator_enum_is_exact_ordered_schema_one_vocabulary(self) -> None:
        self.assertEqual(
            tuple(value.value for value in PmxStructuralTransactionOperationType),
            EXPECTED_DISCRIMINATORS,
        )
        self.assertEqual(PMX_STRUCTURAL_TRANSACTION_PLAN_SCHEMA_VERSION, 1)

    def test_internal_mapping_is_one_to_one_with_released_transaction_union(self) -> None:
        released = typing.get_args(PmxStructuralTransactionOperation)
        self.assertEqual(released, EXPECTED_DTO_TYPES)
        self.assertEqual(
            tuple(transaction_plan._OPERATION_TYPE_BY_DISCRIMINATOR),
            EXPECTED_DISCRIMINATORS,
        )
        self.assertEqual(
            tuple(transaction_plan._OPERATION_TYPE_BY_DISCRIMINATOR.values()),
            released,
        )

    def test_catalog_covers_every_discriminator_in_exact_order(self) -> None:
        catalog = get_pmx_structural_transaction_operation_catalog()

        self.assertEqual(
            tuple(entry.operation_type.value for entry in catalog.operations),
            EXPECTED_DISCRIMINATORS,
        )
        self.assertEqual(len(catalog.operations), 7)

    def test_catalog_entries_have_stable_nonempty_purpose(self) -> None:
        catalog = get_pmx_structural_transaction_operation_catalog()

        for entry in catalog.operations:
            with self.subTest(operation=entry.operation_type.value):
                self.assertIs(type(entry.purpose), str)
                self.assertTrue(entry.purpose)
                self.assertNotIn("\n", entry.purpose)

    def test_catalog_serialization_is_deterministic_json_safe_and_class_free(self) -> None:
        first = get_pmx_structural_transaction_operation_catalog().to_dict()
        second = get_pmx_structural_transaction_operation_catalog().to_dict()

        self.assertEqual(first, second)
        self.assertEqual(first["schema_version"], 1)

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
        for forbidden in (
            "mmd_registry.",
            "__module__",
            "__class__",
            "PmxStructural",
            "callback",
            "writer",
            "remap",
            "final_index",
        ):
            self.assertNotIn(forbidden, first_json)

    def test_catalog_and_entries_are_immutable(self) -> None:
        catalog = get_pmx_structural_transaction_operation_catalog()

        with self.assertRaises(FrozenInstanceError):
            catalog.operations = ()  # type: ignore[misc]

        with self.assertRaises(FrozenInstanceError):
            catalog.operations[0].purpose = "changed"  # type: ignore[misc]

    def test_catalog_validation_rejects_wrong_and_duplicate_entries(self) -> None:
        with self.assertRaises(ValueError):
            PmxStructuralTransactionOperationCatalog(operations=())

        with self.assertRaises(TypeError):
            PmxStructuralTransactionOperationCatalog(
                operations=(object(),),  # type: ignore[arg-type]
            )

        entry = PmxStructuralTransactionOperationCatalogEntry(
            operation_type=PmxStructuralTransactionOperationType.INSERT_TEXTURE,
            purpose="Insert texture.",
        )
        with self.assertRaisesRegex(ValueError, "must be unique"):
            PmxStructuralTransactionOperationCatalog(
                operations=(entry, entry),
            )

    def test_catalog_entry_validation_is_strict(self) -> None:
        with self.assertRaises(TypeError):
            PmxStructuralTransactionOperationCatalogEntry(
                operation_type="insert_texture",  # type: ignore[arg-type]
                purpose="Insert texture.",
            )
        with self.assertRaises(ValueError):
            PmxStructuralTransactionOperationCatalogEntry(
                operation_type=PmxStructuralTransactionOperationType.INSERT_TEXTURE,
                purpose="",
            )

    def test_cp06_namespace_is_additive_and_not_promoted_to_legacy_roots(self) -> None:
        self.assertEqual(
            transaction_plan.__all__,
            (
                "PMX_STRUCTURAL_TRANSACTION_PLAN_SCHEMA_VERSION",
                "PmxStructuralTransactionOperationType",
                "PmxStructuralTransactionOperationCatalogEntry",
                "PmxStructuralTransactionOperationCatalog",
                "get_pmx_structural_transaction_operation_catalog",
                "PmxStructuralTransactionPlan",
            ),
        )

        for root in (mmd_registry, pmx, services):
            for name in transaction_plan.__all__:
                self.assertFalse(hasattr(root, name), (root.__name__, name))

    def test_catalog_foundation_does_not_add_parser_renderer_or_execution_authority(self) -> None:
        public_names = set(transaction_plan.__all__)
        for forbidden in (
            "parse_pmx_structural_transaction_plan_json",
            "load_pmx_structural_transaction_plan",
            "render_pmx_structural_transaction_plan_json",
            "preview_structural_transaction",
            "apply_structural_transaction",
        ):
            self.assertNotIn(forbidden, public_names)

        module_source = __import__("inspect").getsource(transaction_plan)
        for forbidden in (
            "remap_pmx_references",
            "write_pmx_structural_output",
            "_write_structural_transaction",
            "_plan_structural_transaction",
            "publication_callback",
            "final_index",
        ):
            self.assertNotIn(forbidden, module_source)


if __name__ == "__main__":
    unittest.main()
