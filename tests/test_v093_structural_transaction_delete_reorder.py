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


class V093StructuralTransactionDeleteReorderTests(unittest.TestCase):
    def test_legacy_delete_reorder_remap_is_preserved_without_insertions(
        self,
    ) -> None:
        target_kind = PmxReferenceTargetKind.RIGID_BODY
        transform = _transform(
            target_kind,
            (2, 0, 3),
            source_count=4,
        )
        plan = _plan(transform)

        self.assertTrue(transform.has_deletions)
        self.assertTrue(transform.has_reorder)
        self.assertEqual(transform.remap.targets, (1, None, 0, 2))
        self.assertEqual(transform.old_indices_in_new_order, (2, 0, 3))
        self.assertEqual(transform.removed_old_indices, (1,))
        self.assertEqual(plan.remap, transform.remap)
        self.assertIs(plan.target_remap.remap, plan.remap)
        self.assertEqual(plan.remap.new_indices_without_old_source, ())
        self.assertEqual(plan.new_indices_in_request_order, ())
        self.assertEqual(plan.bindings, ())
        self.assertEqual(plan.identities, ())
        self.assertEqual(plan.capacity.current_count, 3)
        self.assertEqual(plan.capacity.insert_count, 0)
        for _ in range(20):
            self.assertEqual(_plan(transform), plan)

    def test_insertions_interleave_with_final_delete_reorder_survivors(
        self,
    ) -> None:
        target_kind = PmxReferenceTargetKind.BONE
        transform = _transform(
            target_kind,
            (4, 1, 5, 0),
            source_count=6,
        )
        operations = (
            _operation(0, target_kind, new_id="append"),
            _operation(
                1,
                target_kind,
                position=PmxStructuralInsertPosition.insert_before(0),
                new_id="before-zero",
            ),
            _operation(
                2,
                target_kind,
                position=PmxStructuralInsertPosition.insert_before(4),
                new_id="before-four",
            ),
            _operation(
                3,
                target_kind,
                position=PmxStructuralInsertPosition.insert_before(1),
                new_id="before-one",
            ),
        )
        plan = _plan(transform, operations=operations)

        self.assertEqual(transform.remap.targets, (3, 1, None, None, 0, 2))
        self.assertEqual(plan.remap.targets, (6, 3, None, None, 1, 4))
        self.assertEqual(
            plan.remap.new_indices_without_old_source,
            (0, 2, 5, 7),
        )
        self.assertEqual(plan.new_indices_in_request_order, (7, 5, 0, 2))
        self.assertEqual(
            tuple(
                (identity.new_id, identity.final_index)
                for identity in plan.identities
            ),
            (
                ("before-four", 0),
                ("before-one", 2),
                ("before-zero", 5),
                ("append", 7),
            ),
        )
        self.assertEqual(plan.result_count, 8)
        self.assertEqual(transform.old_indices_in_new_order, (4, 1, 5, 0))
        self.assertEqual(operations, plan.operations)

    def test_final_resolver_uses_combined_delete_reorder_mapping(self) -> None:
        target_kind = PmxReferenceTargetKind.TEXTURE
        transform = _transform(
            target_kind,
            (3, 0, 4),
            source_count=5,
        )
        plan = _plan(
            transform,
            operations=(
                _operation(7, target_kind, new_id="new-texture"),
            ),
        )
        resolver = PmxStructuralTransactionReferenceResolver(
            source_counts=_source_counts(texture=5),
            target_remaps=(plan.target_remap,),
            identities=plan.identities,
        )

        self.assertEqual(plan.remap.targets, (1, None, None, 0, 2))
        self.assertEqual(
            tuple(
                resolver.resolve_source_reference(
                    target_kind,
                    old_index,
                    allow_sentinel=False,
                    field_name="texture_index",
                )
                for old_index in (0, 3, 4)
            ),
            (1, 0, 2),
        )
        for deleted_index in (1, 2):
            with self.subTest(deleted_index=deleted_index):
                with self.assertRaisesRegex(
                    ValueError,
                    rf"removed captured-source texture\[{deleted_index}\]",
                ):
                    resolver.resolve_source_reference(
                        target_kind,
                        deleted_index,
                        allow_sentinel=True,
                        field_name="texture_index",
                    )
        self.assertEqual(
            resolver.resolve_new_reference(
                target_kind,
                "new-texture",
                field_name="texture_index",
            ),
            3,
        )

    def test_deleted_anchor_stays_blocked_after_reorder_is_enabled(self) -> None:
        target_kind = PmxReferenceTargetKind.MORPH
        transform = _transform(
            target_kind,
            (3, 0),
            source_count=4,
        )
        operation = _operation(
            0,
            target_kind,
            position=PmxStructuralInsertPosition.insert_before(2),
        )
        placement_error = _placement_module().PmxStructuralTransactionPlacementError

        with self.assertRaisesRegex(
            placement_error,
            r"insert_before anchor morph\[2\] is deleted by the same transaction",
        ):
            _plan(transform, operations=(operation,))
        self.assertEqual(transform.remap.targets, (1, None, None, 0))

    def test_all_target_kinds_share_one_delete_reorder_rule(self) -> None:
        for target_kind in PmxReferenceTargetKind:
            with self.subTest(target_kind=target_kind):
                transform = _transform(
                    target_kind,
                    (2, 0, 3),
                    source_count=4,
                )
                operations = (
                    _operation(0, target_kind, new_id="tail"),
                    _operation(
                        1,
                        target_kind,
                        position=PmxStructuralInsertPosition.insert_before(0),
                        new_id="anchored",
                    ),
                )
                plan = _plan(transform, operations=operations)

                self.assertEqual(plan.remap.targets, (2, None, 0, 3))
                self.assertEqual(
                    plan.remap.new_indices_without_old_source,
                    (1, 4),
                )
                self.assertEqual(plan.new_indices_in_request_order, (4, 1))
                self.assertEqual(plan.result_count, 5)

    def test_capacity_uses_reordered_survivors_after_deletion(self) -> None:
        target_kind = PmxReferenceTargetKind.MATERIAL
        operations = (
            _operation(0, target_kind),
            _operation(1, target_kind),
        )
        accepted_order = (125, *range(125))
        accepted = _plan(
            _transform(
                target_kind,
                accepted_order,
                source_count=130,
            ),
            index_width=1,
            operations=operations,
        )
        self.assertEqual(accepted.capacity.current_count, 126)
        self.assertEqual(accepted.result_count, 128)

        rejected_order = (126, *range(126))
        placement_error = _placement_module().PmxStructuralTransactionPlacementError
        with self.assertRaisesRegex(
            placement_error,
            r"cannot plan material combined placement",
        ):
            _plan(
                _transform(
                    target_kind,
                    rejected_order,
                    source_count=130,
                ),
                index_width=1,
                operations=operations,
            )


if __name__ == "__main__":
    unittest.main()
