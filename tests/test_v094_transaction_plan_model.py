"""Tests for the v0.9.4 immutable structural transaction-plan model."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
import inspect
import unittest

import mmd_registry
import mmd_registry.pmx as pmx
import mmd_registry.services as services
from mmd_registry.pmx.transaction_plan import (
    PMX_STRUCTURAL_TRANSACTION_PLAN_SCHEMA_VERSION,
    PmxStructuralTransactionPlan,
)
from mmd_registry.services import (
    PmxReferenceTargetKind,
    PmxStructuralCollectionEdit,
)
from mmd_registry.services.structural_reference import PmxStructuralNewReference
from mmd_registry.services.structural_texture import PmxStructuralTextureInsertion
from mmd_registry.services.structural_transaction import (
    PmxStructuralTransactionRequest,
)


class V094TransactionPlanModelTests(unittest.TestCase):
    def test_module_exports_only_the_cp05_model_foundation(self) -> None:
        import mmd_registry.pmx.transaction_plan as module

        self.assertEqual(
            module.__all__,
            (
                "PMX_STRUCTURAL_TRANSACTION_PLAN_SCHEMA_VERSION",
                "PmxStructuralTransactionPlan",
            ),
        )
        self.assertEqual(PMX_STRUCTURAL_TRANSACTION_PLAN_SCHEMA_VERSION, 1)

    def test_model_has_one_frozen_slotted_contract_shape(self) -> None:
        self.assertTrue(PmxStructuralTransactionPlan.__dataclass_params__.frozen)
        self.assertEqual(
            tuple(field.name for field in fields(PmxStructuralTransactionPlan)),
            ("operations", "schema_version", "expected_source_sha256"),
        )
        self.assertNotIn("__dict__", PmxStructuralTransactionPlan.__slots__)

    def test_empty_operations_are_a_valid_immutable_noop(self) -> None:
        plan = PmxStructuralTransactionPlan(operations=())

        self.assertEqual(plan.operations, ())
        self.assertEqual(plan.schema_version, 1)
        self.assertIsNone(plan.expected_source_sha256)
        self.assertEqual(PmxStructuralTransactionRequest(operations=plan.operations).operations, ())

    def test_model_preserves_operation_tuple_identity_and_order(self) -> None:
        first = PmxStructuralTextureInsertion(path="a.png", new_id="texture-a")
        second = PmxStructuralTextureInsertion(path="b.png", new_id="texture-b")
        operations = (first, second)

        plan = PmxStructuralTransactionPlan(operations=operations)

        self.assertIs(plan.operations, operations)
        self.assertEqual(plan.operations, (first, second))

    def test_model_rejects_mutable_or_unsupported_operation_containers(self) -> None:
        with self.assertRaisesRegex(TypeError, "operations must be a tuple"):
            PmxStructuralTransactionPlan(operations=[])  # type: ignore[arg-type]

        with self.assertRaises(TypeError):
            PmxStructuralTransactionPlan(operations=(object(),))  # type: ignore[arg-type]

    def test_model_reuses_request_duplicate_collection_target_authority(self) -> None:
        first = PmxStructuralCollectionEdit(
            target_kind=PmxReferenceTargetKind.TEXTURE,
            old_indices_in_new_order=(0,),
        )
        second = PmxStructuralCollectionEdit(
            target_kind=PmxReferenceTargetKind.TEXTURE,
            old_indices_in_new_order=(0,),
        )

        request_error = None
        try:
            PmxStructuralTransactionRequest(operations=(first, second))
        except ValueError as exc:
            request_error = str(exc)

        self.assertIsNotNone(request_error)
        with self.assertRaisesRegex(ValueError, "cannot repeat"):
            PmxStructuralTransactionPlan(operations=(first, second))

    def test_model_reuses_request_global_new_id_authority(self) -> None:
        first = PmxStructuralTextureInsertion(path="a.png", new_id="same-id")
        second = PmxStructuralTextureInsertion(path="b.png", new_id="same-id")

        with self.assertRaisesRegex(ValueError, "globally unique"):
            PmxStructuralTransactionRequest(operations=(first, second))
        with self.assertRaisesRegex(ValueError, "globally unique"):
            PmxStructuralTransactionPlan(operations=(first, second))

    def test_schema_version_requires_exact_supported_integer(self) -> None:
        with self.assertRaisesRegex(TypeError, "schema_version must be an integer"):
            PmxStructuralTransactionPlan(operations=(), schema_version=True)

        with self.assertRaisesRegex(TypeError, "schema_version must be an integer"):
            PmxStructuralTransactionPlan(operations=(), schema_version=1.0)  # type: ignore[arg-type]

        with self.assertRaisesRegex(ValueError, "Unsupported structural transaction-plan"):
            PmxStructuralTransactionPlan(operations=(), schema_version=2)

    def test_expected_source_sha256_is_optional_lowercase_exact_hash(self) -> None:
        digest = "a" * 64
        plan = PmxStructuralTransactionPlan(
            operations=(),
            expected_source_sha256=digest,
        )
        self.assertEqual(plan.expected_source_sha256, digest)

        for invalid in ("A" * 64, "a" * 63, "g" * 64, ""):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    PmxStructuralTransactionPlan(
                        operations=(),
                        expected_source_sha256=invalid,
                    )

        with self.assertRaises(TypeError):
            PmxStructuralTransactionPlan(
                operations=(),
                expected_source_sha256=b"a" * 64,  # type: ignore[arg-type]
            )

    def test_model_is_immutable_and_hashable(self) -> None:
        plan = PmxStructuralTransactionPlan(operations=())

        hash(plan)
        with self.assertRaises(FrozenInstanceError):
            plan.schema_version = 2  # type: ignore[misc]

    def test_cp05_does_not_promote_authoring_names_to_legacy_roots(self) -> None:
        reserved = (
            "PMX_STRUCTURAL_TRANSACTION_PLAN_SCHEMA_VERSION",
            "PmxStructuralTransactionPlan",
        )
        for root in (mmd_registry, pmx, services):
            for name in reserved:
                self.assertFalse(hasattr(root, name), (root.__name__, name))

    def test_model_does_not_own_rendering_or_execution_authority(self) -> None:
        names = set(vars(PmxStructuralTransactionPlan))
        self.assertNotIn("to_dict", names)
        self.assertNotIn("render", names)
        self.assertNotIn("preview", names)
        self.assertNotIn("apply", names)

        source = inspect.getsource(
            __import__(
                "mmd_registry.pmx.transaction_plan",
                fromlist=["PmxStructuralTransactionPlan"],
            )
        )
        for forbidden in (
            "remap_pmx_references",
            "write_pmx_structural_output",
            "_write_structural_transaction",
            "_plan_structural_transaction",
            "final_index",
            "publication_callback",
        ):
            self.assertNotIn(forbidden, source)

    def test_new_reference_semantics_remain_owned_by_released_dto(self) -> None:
        reference = PmxStructuralNewReference(
            target_kind="texture",
            new_id="texture-a",
        )
        self.assertEqual(reference.target_kind, "texture")
        self.assertEqual(reference.new_id, "texture-a")


if __name__ == "__main__":
    unittest.main()
