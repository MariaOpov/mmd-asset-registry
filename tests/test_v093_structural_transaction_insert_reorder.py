from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, is_dataclass
import importlib
import inspect
import unittest

import mmd_registry
import mmd_registry.pmx as pmx
import mmd_registry.services as services
from mmd_registry.pmx.collection_transform import PmxCollectionTransform
from mmd_registry.pmx.index_remap import PmxIndexRemap
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.pmx.structural_insert_intent import (
    PmxCollectionInsertionIntent,
    PmxStructuralInsertPosition,
)
from mmd_registry.pmx.structural_reference_shift import (
    plan_collection_reference_shift,
)
from mmd_registry.pmx.structural_transaction_insertion import (
    PmxStructuralTransactionInsertionOperation,
)
from mmd_registry.pmx.structural_transaction_reference import (
    PmxStructuralTransactionReferenceResolver,
)


def _placement_module():
    return importlib.import_module(
        "mmd_registry.pmx.structural_transaction_placement"
    )


def _operation(
    request_ordinal: int,
    target_kind: PmxReferenceTargetKind,
    *,
    position: PmxStructuralInsertPosition | None = None,
    new_id: str | None = None,
) -> PmxStructuralTransactionInsertionOperation:
    return PmxStructuralTransactionInsertionOperation(
        request_ordinal=request_ordinal,
        target_kind=target_kind,
        position=(
            PmxStructuralInsertPosition.append()
            if position is None
            else position
        ),
        new_id=new_id,
    )


def _transform(
    target_kind: PmxReferenceTargetKind,
    old_indices_in_new_order: tuple[int, ...],
    *,
    source_count: int | None = None,
) -> PmxCollectionTransform:
    old_size = (
        len(old_indices_in_new_order)
        if source_count is None
        else source_count
    )
    targets: list[int | None] = [None] * old_size
    for new_index, old_index in enumerate(old_indices_in_new_order):
        targets[old_index] = new_index
    return PmxCollectionTransform(
        kind=target_kind,
        remap=PmxIndexRemap(
            targets=tuple(targets),
            new_size=len(old_indices_in_new_order),
        ),
    )


def _source_counts(**overrides: int):
    return tuple(
        (target_kind, overrides.get(target_kind.value, 0))
        for target_kind in PmxReferenceTargetKind
    )


def _plan(
    transform: PmxCollectionTransform,
    *,
    index_width: int = 4,
    operations: tuple[PmxStructuralTransactionInsertionOperation, ...] = (),
):
    return _placement_module().plan_structural_transaction_collection_placement(
        transform,
        index_width=index_width,
        operations=operations,
    )


class V093StructuralTransactionInsertReorderTests(unittest.TestCase):
    def test_internal_model_is_frozen_slotted_and_not_root_exported(self) -> None:
        placement_module = _placement_module()
        expected_exports = (
            "PmxStructuralTransactionCollectionPlacement",
            "PmxStructuralTransactionPlacementError",
            "plan_structural_transaction_collection_placement",
        )
        self.assertEqual(placement_module.__all__, expected_exports)
        for name in expected_exports:
            self.assertFalse(hasattr(mmd_registry, name), name)
            self.assertFalse(hasattr(pmx, name), name)
            self.assertFalse(hasattr(services, name), name)

        transform = _transform(PmxReferenceTargetKind.TEXTURE, (1, 0))
        operation = _operation(
            3,
            PmxReferenceTargetKind.TEXTURE,
            new_id="inserted",
        )
        plan = _plan(transform, operations=(operation,))
        self.assertTrue(is_dataclass(plan))
        self.assertFalse(hasattr(plan, "__dict__"))
        self.assertEqual(
            tuple(field.name for field in fields(plan)),
            (
                "transform",
                "index_width",
                "operations",
                "capacity",
                "remap",
                "bindings",
                "identities",
                "target_remap",
            ),
        )
        with self.assertRaises(FrozenInstanceError):
            plan.index_width = 2

        source = inspect.getsource(placement_module)
        self.assertNotIn("mmd_registry.services", source)
        for forbidden in (
            "PmxDocument",
            "open(",
            "preview_structural_transaction",
            "apply_structural_transaction",
            "execute_structural_transaction",
            "materialize",
        ):
            self.assertNotIn(forbidden, source)

    def test_anchor_follows_named_source_record_through_reorder(self) -> None:
        transform = _transform(PmxReferenceTargetKind.TEXTURE, (2, 0, 1))
        operations = (
            _operation(
                5,
                PmxReferenceTargetKind.TEXTURE,
                position=PmxStructuralInsertPosition.insert_before(1),
                new_id="inserted",
            ),
        )
        plan = _plan(transform, operations=operations)

        self.assertEqual(plan.target_kind, PmxReferenceTargetKind.TEXTURE)
        self.assertEqual(plan.source_count, 3)
        self.assertEqual(plan.result_count, 4)
        self.assertEqual(plan.remap.targets, (1, 3, 0))
        self.assertEqual(plan.remap.new_indices_without_old_source, (2,))
        self.assertEqual(plan.new_indices_in_request_order, (2,))
        self.assertEqual(plan.new_index_for_operation(5), 2)
        self.assertEqual(plan.target_remap.remap, plan.remap)

        resolver = PmxStructuralTransactionReferenceResolver(
            source_counts=_source_counts(texture=3),
            target_remaps=(plan.target_remap,),
            identities=plan.identities,
        )
        self.assertEqual(
            resolver.resolve_source_reference(
                PmxReferenceTargetKind.TEXTURE,
                1,
                allow_sentinel=False,
                field_name="texture_index",
            ),
            3,
        )
        self.assertEqual(
            resolver.resolve_source_reference(
                PmxReferenceTargetKind.TEXTURE,
                2,
                allow_sentinel=False,
                field_name="texture_index",
            ),
            0,
        )
        self.assertEqual(
            resolver.resolve_new_reference(
                PmxReferenceTargetKind.TEXTURE,
                "inserted",
                field_name="texture_index",
            ),
            2,
        )
        self.assertEqual(transform.old_indices_in_new_order, (2, 0, 1))
        self.assertEqual(operations, plan.operations)
        for _ in range(20):
            self.assertEqual(_plan(transform, operations=operations), plan)

    def test_final_survivor_groups_control_order_and_request_ties(self) -> None:
        target_kind = PmxReferenceTargetKind.BONE
        transform = _transform(target_kind, (2, 0, 3, 1))
        operations = (
            _operation(
                0,
                target_kind,
                position=PmxStructuralInsertPosition.insert_before(0),
                new_id="old0_a",
            ),
            _operation(
                1,
                target_kind,
                position=PmxStructuralInsertPosition.insert_before(2),
                new_id="old2_a",
            ),
            _operation(
                2,
                target_kind,
                position=PmxStructuralInsertPosition.insert_before(2),
                new_id="old2_b",
            ),
            _operation(3, target_kind, new_id="append"),
            _operation(
                4,
                target_kind,
                position=PmxStructuralInsertPosition.insert_before(0),
                new_id="old0_b",
            ),
        )
        plan = _plan(transform, operations=operations)

        self.assertEqual(plan.remap.targets, (5, 7, 2, 6))
        self.assertEqual(
            plan.remap.new_indices_without_old_source,
            (0, 1, 3, 4, 8),
        )
        self.assertEqual(
            plan.new_indices_in_request_order,
            (3, 0, 1, 8, 4),
        )
        self.assertEqual(
            tuple(
                (binding.request_ordinal, binding.final_index)
                for binding in plan.bindings
            ),
            ((0, 3), (1, 0), (2, 1), (3, 8), (4, 4)),
        )
        self.assertEqual(
            tuple(
                (identity.new_id, identity.operation_index, identity.final_index)
                for identity in plan.identities
            ),
            (
                ("old2_a", 1, 0),
                ("old2_b", 2, 1),
                ("old0_a", 0, 3),
                ("old0_b", 4, 4),
                ("append", 3, 8),
            ),
        )

    def test_noop_transform_matches_released_standalone_insertion(self) -> None:
        target_kind = PmxReferenceTargetKind.MATERIAL
        operations = (
            _operation(2, target_kind, new_id="append"),
            _operation(
                5,
                target_kind,
                position=PmxStructuralInsertPosition.insert_before(1),
                new_id="before",
            ),
        )
        transform = PmxCollectionTransform.identity(target_kind, 3)
        combined = _plan(transform, operations=operations)
        standalone = plan_collection_reference_shift(
            PmxCollectionInsertionIntent(
                target_kind=target_kind,
                positions=tuple(operation.position for operation in operations),
            ),
            current_count=3,
            index_width=4,
        )

        self.assertEqual(combined.remap, standalone.remap)
        self.assertEqual(
            combined.new_indices_in_request_order,
            standalone.new_indices_in_request_order,
        )

        reorder_only = _plan(
            _transform(PmxReferenceTargetKind.VERTEX, (2, 0, 1))
        )
        self.assertEqual(reorder_only.remap, reorder_only.transform.remap)
        self.assertEqual(reorder_only.new_indices_in_request_order, ())

    def test_capacity_uses_final_reordered_survivor_count(self) -> None:
        placement_error = _placement_module().PmxStructuralTransactionPlacementError
        vertex_operations = (
            _operation(0, PmxReferenceTargetKind.VERTEX),
            _operation(1, PmxReferenceTargetKind.VERTEX),
        )
        accepted_vertex = _plan(
            _transform(
                PmxReferenceTargetKind.VERTEX,
                tuple(reversed(range(254))),
            ),
            index_width=1,
            operations=vertex_operations,
        )
        self.assertEqual(accepted_vertex.result_count, 256)
        self.assertTrue(accepted_vertex.capacity.representable)

        with self.assertRaisesRegex(
            placement_error,
            r"cannot plan vertex combined placement",
        ):
            _plan(
                _transform(
                    PmxReferenceTargetKind.VERTEX,
                    tuple(reversed(range(255))),
                ),
                index_width=1,
                operations=vertex_operations,
            )

        material_operations = (
            _operation(0, PmxReferenceTargetKind.MATERIAL),
            _operation(1, PmxReferenceTargetKind.MATERIAL),
        )
        accepted_material = _plan(
            _transform(
                PmxReferenceTargetKind.MATERIAL,
                tuple(reversed(range(126))),
            ),
            index_width=1,
            operations=material_operations,
        )
        self.assertEqual(accepted_material.result_count, 128)

        with self.assertRaisesRegex(
            placement_error,
            r"cannot plan material combined placement",
        ):
            _plan(
                _transform(
                    PmxReferenceTargetKind.MATERIAL,
                    tuple(reversed(range(127))),
                ),
                index_width=1,
                operations=material_operations,
            )

    def test_invalid_or_delete_capable_inputs_fail_closed(self) -> None:
        placement_module = _placement_module()
        placement_error = placement_module.PmxStructuralTransactionPlacementError
        texture_transform = _transform(
            PmxReferenceTargetKind.TEXTURE,
            (1, 0),
        )
        cases = (
            (
                lambda: _plan(object()),
                TypeError,
                r"transform must be a PmxCollectionTransform",
            ),
            (
                lambda: _plan(texture_transform, operations=[]),
                TypeError,
                r"operations must be a tuple",
            ),
            (
                lambda: _plan(texture_transform, operations=(object(),)),
                TypeError,
                r"operations\[0\].*InsertionOperation",
            ),
            (
                lambda: _plan(
                    texture_transform,
                    operations=(
                        _operation(0, PmxReferenceTargetKind.MATERIAL),
                    ),
                ),
                ValueError,
                r"target_kind must match transform kind",
            ),
            (
                lambda: _plan(
                    texture_transform,
                    operations=(
                        _operation(2, PmxReferenceTargetKind.TEXTURE),
                        _operation(1, PmxReferenceTargetKind.TEXTURE),
                    ),
                ),
                ValueError,
                r"strictly increasing unique request_ordinal",
            ),
            (
                lambda: _plan(
                    texture_transform,
                    operations=(
                        _operation(
                            0,
                            PmxReferenceTargetKind.TEXTURE,
                            new_id="duplicate",
                        ),
                        _operation(
                            1,
                            PmxReferenceTargetKind.TEXTURE,
                            new_id="duplicate",
                        ),
                    ),
                ),
                ValueError,
                r"new_id 'duplicate' must be globally unique",
            ),
            (
                lambda: _plan(
                    texture_transform,
                    operations=(
                        _operation(
                            0,
                            PmxReferenceTargetKind.TEXTURE,
                            position=PmxStructuralInsertPosition.insert_before(2),
                        ),
                    ),
                ),
                ValueError,
                r"source_index must be less than current_count",
            ),
            (
                lambda: _plan(texture_transform, index_width=True),
                TypeError,
                r"index_width must be an integer",
            ),
        )
        for build, error, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(error, message):
                    build()

        delete_transform = _transform(
            PmxReferenceTargetKind.TEXTURE,
            (1,),
            source_count=2,
        )
        with self.assertRaisesRegex(
            placement_error,
            r"CP11.*does not authorize deletion",
        ):
            _plan(
                delete_transform,
                operations=(
                    _operation(
                        0,
                        PmxReferenceTargetKind.TEXTURE,
                        position=PmxStructuralInsertPosition.insert_before(1),
                    ),
                ),
            )

        plan = _plan(
            texture_transform,
            operations=(
                _operation(4, PmxReferenceTargetKind.TEXTURE),
            ),
        )
        with self.assertRaisesRegex(TypeError, r"request_ordinal must be an integer"):
            plan.new_index_for_operation(True)
        with self.assertRaisesRegex(ValueError, r"is not an insertion"):
            plan.new_index_for_operation(9)


if __name__ == "__main__":
    unittest.main()
