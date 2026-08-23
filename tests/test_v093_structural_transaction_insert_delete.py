from __future__ import annotations

import importlib
import unittest

from mmd_registry.pmx.collection_transform import PmxCollectionTransform
from mmd_registry.pmx.index_remap import PmxIndexRemap
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.pmx.structural_insert_intent import PmxStructuralInsertPosition
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
    source_count: int,
) -> PmxCollectionTransform:
    targets: list[int | None] = [None] * source_count
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


class V093StructuralTransactionInsertDeleteTests(unittest.TestCase):
    def test_survivor_anchor_and_append_share_one_combined_remap(self) -> None:
        target_kind = PmxReferenceTargetKind.TEXTURE
        transform = _transform(
            target_kind,
            (0, 2, 3),
            source_count=4,
        )
        operations = (
            _operation(0, target_kind, new_id="append"),
            _operation(
                1,
                target_kind,
                position=PmxStructuralInsertPosition.insert_before(2),
                new_id="before",
            ),
        )
        plan = _plan(transform, operations=operations)

        self.assertTrue(transform.has_deletions)
        self.assertFalse(transform.has_reorder)
        self.assertEqual(plan.capacity.current_count, 3)
        self.assertEqual(plan.capacity.insert_count, 2)
        self.assertEqual(plan.result_count, 5)
        self.assertEqual(plan.remap.targets, (0, None, 2, 3))
        self.assertEqual(plan.remap.new_indices_without_old_source, (1, 4))
        self.assertEqual(plan.new_indices_in_request_order, (4, 1))
        self.assertEqual(
            tuple(
                (identity.new_id, identity.final_index)
                for identity in plan.identities
            ),
            (("before", 1), ("append", 4)),
        )
        self.assertEqual(transform.old_indices_in_new_order, (0, 2, 3))
        self.assertEqual(operations, plan.operations)
        for _ in range(20):
            self.assertEqual(_plan(transform, operations=operations), plan)

    def test_deleted_anchor_fails_without_append_or_neighbor_repair(self) -> None:
        target_kind = PmxReferenceTargetKind.BONE
        transform = _transform(
            target_kind,
            (0, 2),
            source_count=3,
        )
        operation = _operation(
            0,
            target_kind,
            position=PmxStructuralInsertPosition.insert_before(1),
        )
        placement_error = _placement_module().PmxStructuralTransactionPlacementError

        with self.assertRaisesRegex(
            placement_error,
            r"insert_before anchor bone\[1\] is deleted by the same transaction",
        ):
            _plan(transform, operations=(operation,))

    def test_surviving_required_owner_blocks_without_dependent_deletion(
        self,
    ) -> None:
        target_kind = PmxReferenceTargetKind.TEXTURE
        transform = _transform(
            target_kind,
            (0, 2),
            source_count=3,
        )
        plan = _plan(transform)
        source_counts = _source_counts(texture=3, material=2)
        resolver = PmxStructuralTransactionReferenceResolver(
            source_counts=source_counts,
            target_remaps=(plan.target_remap,),
        )

        with self.assertRaisesRegex(
            ValueError,
            r"material\[0\]\.texture_index references removed "
            r"captured-source texture\[1\]",
        ):
            resolver.resolve_source_reference(
                target_kind,
                1,
                allow_sentinel=False,
                field_name="material[0].texture_index",
            )
        self.assertEqual(
            resolver.resolve_source_reference(
                PmxReferenceTargetKind.MATERIAL,
                0,
                allow_sentinel=False,
                field_name="surviving material owner",
            ),
            0,
        )
        self.assertEqual(resolver.source_counts, source_counts)
        self.assertEqual(transform.remap.targets, (0, None, 1))

    def test_deleted_source_reference_fails_even_when_replacement_id_exists(
        self,
    ) -> None:
        target_kind = PmxReferenceTargetKind.TEXTURE
        transform = _transform(
            target_kind,
            (0, 2),
            source_count=3,
        )
        plan = _plan(
            transform,
            operations=(
                _operation(4, target_kind, new_id="replacement"),
            ),
        )
        resolver = PmxStructuralTransactionReferenceResolver(
            source_counts=_source_counts(texture=3),
            target_remaps=(plan.target_remap,),
            identities=plan.identities,
        )

        with self.assertRaisesRegex(
            ValueError,
            r"references removed captured-source texture\[1\]",
        ):
            resolver.resolve_source_reference(
                target_kind,
                1,
                allow_sentinel=True,
                field_name="inserted_material.texture_index",
            )
        self.assertEqual(
            resolver.resolve_source_reference(
                target_kind,
                2,
                allow_sentinel=False,
                field_name="texture_index",
            ),
            1,
        )
        self.assertEqual(
            resolver.resolve_new_reference(
                target_kind,
                "replacement",
                field_name="texture_index",
            ),
            2,
        )
        self.assertEqual(
            resolver.resolve_source_reference(
                target_kind,
                -1,
                allow_sentinel=True,
                field_name="texture_index",
            ),
            -1,
        )
        with self.assertRaisesRegex(ValueError, r"does not allow the -1 sentinel"):
            resolver.resolve_source_reference(
                target_kind,
                -1,
                allow_sentinel=False,
                field_name="texture_index",
            )

    def test_empty_survivor_set_accepts_append_but_no_source_anchor(self) -> None:
        target_kind = PmxReferenceTargetKind.MORPH
        transform = _transform(target_kind, (), source_count=2)
        operations = (
            _operation(0, target_kind, new_id="first"),
            _operation(1, target_kind, new_id="second"),
        )
        plan = _plan(transform, operations=operations)

        self.assertEqual(plan.remap.targets, (None, None))
        self.assertEqual(plan.remap.new_indices_without_old_source, (0, 1))
        self.assertEqual(plan.new_indices_in_request_order, (0, 1))
        self.assertEqual(plan.result_count, 2)

        placement_error = _placement_module().PmxStructuralTransactionPlacementError
        with self.assertRaisesRegex(
            placement_error,
            r"insert_before anchor morph\[0\] is deleted",
        ):
            _plan(
                transform,
                operations=(
                    _operation(
                        0,
                        target_kind,
                        position=PmxStructuralInsertPosition.insert_before(0),
                    ),
                ),
            )

    def test_capacity_uses_survivors_after_deletion(self) -> None:
        target_kind = PmxReferenceTargetKind.MATERIAL
        operations = (
            _operation(0, target_kind),
            _operation(1, target_kind),
        )
        accepted = _plan(
            _transform(
                target_kind,
                tuple(range(126)),
                source_count=130,
            ),
            index_width=1,
            operations=operations,
        )
        self.assertEqual(accepted.capacity.current_count, 126)
        self.assertEqual(accepted.result_count, 128)
        self.assertTrue(accepted.capacity.representable)

        placement_error = _placement_module().PmxStructuralTransactionPlacementError
        with self.assertRaisesRegex(
            placement_error,
            r"cannot plan material combined placement",
        ):
            _plan(
                _transform(
                    target_kind,
                    tuple(range(127)),
                    source_count=130,
                ),
                index_width=1,
                operations=operations,
            )

    def test_delete_plus_reorder_remains_deferred_to_cp13(self) -> None:
        target_kind = PmxReferenceTargetKind.RIGID_BODY
        transform = _transform(
            target_kind,
            (2, 0),
            source_count=3,
        )
        self.assertTrue(transform.has_deletions)
        self.assertTrue(transform.has_reorder)

        placement_error = _placement_module().PmxStructuralTransactionPlacementError
        with self.assertRaisesRegex(
            placement_error,
            r"delete-plus-reorder is deferred to CP13",
        ):
            _plan(
                transform,
                operations=(
                    _operation(0, target_kind),
                ),
            )


if __name__ == "__main__":
    unittest.main()
