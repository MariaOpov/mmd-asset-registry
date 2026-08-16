"""Contracts for the internal CP10 structural transform intent model."""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

import mmd_registry.pmx as pmx
import mmd_registry.services as services
from mmd_registry.pmx.collection_transform import (
    PmxCollectionTransform,
    PmxStructuralTransformIntent,
)
from mmd_registry.pmx.index_remap import PmxIndexRemap
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind


class PmxCollectionTransformTests(unittest.TestCase):
    """Freeze keep/delete/reorder/no-op and coordinated-intent semantics."""

    def test_identity_proposal_is_immutable_hashable_and_noop(self) -> None:
        transform = PmxCollectionTransform.identity(
            PmxReferenceTargetKind.VERTEX,
            3,
        )

        self.assertEqual(transform.old_size, 3)
        self.assertEqual(transform.new_size, 3)
        self.assertEqual(transform.old_indices_in_new_order, (0, 1, 2))
        self.assertEqual(transform.removed_old_indices, ())
        self.assertFalse(transform.has_deletions)
        self.assertFalse(transform.has_reorder)
        self.assertTrue(transform.is_noop)
        self.assertEqual(hash(transform), hash(transform))

        with self.assertRaises(FrozenInstanceError):
            transform.kind = PmxReferenceTargetKind.BONE  # type: ignore[misc]

    def test_delete_only_preserves_survivor_order(self) -> None:
        transform = PmxCollectionTransform(
            kind=PmxReferenceTargetKind.MATERIAL,
            remap=PmxIndexRemap(
                targets=(0, None, 1, None, 2),
                new_size=3,
            ),
        )

        self.assertEqual(transform.old_indices_in_new_order, (0, 2, 4))
        self.assertEqual(transform.removed_old_indices, (1, 3))
        self.assertTrue(transform.has_deletions)
        self.assertFalse(transform.has_reorder)
        self.assertFalse(transform.is_noop)

    def test_reorder_only_derives_new_collection_order_from_remap(self) -> None:
        transform = PmxCollectionTransform(
            kind=PmxReferenceTargetKind.BONE,
            remap=PmxIndexRemap(
                targets=(2, 0, 1),
                new_size=3,
            ),
        )

        self.assertEqual(transform.old_indices_in_new_order, (1, 2, 0))
        self.assertEqual(transform.removed_old_indices, ())
        self.assertFalse(transform.has_deletions)
        self.assertTrue(transform.has_reorder)
        self.assertFalse(transform.is_noop)

    def test_delete_and_reorder_can_coexist_without_second_mapping_authority(
        self,
    ) -> None:
        transform = PmxCollectionTransform(
            kind=PmxReferenceTargetKind.RIGID_BODY,
            remap=PmxIndexRemap(
                targets=(1, None, 0, 2),
                new_size=3,
            ),
        )

        self.assertEqual(transform.old_indices_in_new_order, (2, 0, 3))
        self.assertEqual(transform.removed_old_indices, (1,))
        self.assertTrue(transform.has_deletions)
        self.assertTrue(transform.has_reorder)

    def test_rejects_future_new_only_indices_in_v090_transform_intent(self) -> None:
        remap = PmxIndexRemap(
            targets=(1, 2),
            new_size=3,
            new_indices_without_old_source=(0,),
        )

        with self.assertRaisesRegex(ValueError, "do not authorize new indices"):
            PmxCollectionTransform(
                kind=PmxReferenceTargetKind.TEXTURE,
                remap=remap,
            )

    def test_rejects_invalid_kind_and_remap_types(self) -> None:
        remap = PmxIndexRemap.identity(0)

        with self.assertRaises(TypeError):
            PmxCollectionTransform(  # type: ignore[arg-type]
                kind="vertex",
                remap=remap,
            )
        with self.assertRaises(TypeError):
            PmxCollectionTransform(  # type: ignore[arg-type]
                kind=PmxReferenceTargetKind.VERTEX,
                remap=object(),
            )

    def test_coordinated_intent_is_canonical_hashable_and_queryable(self) -> None:
        vertex = PmxCollectionTransform(
            kind=PmxReferenceTargetKind.VERTEX,
            remap=PmxIndexRemap(targets=(None, 0), new_size=1),
        )
        material = PmxCollectionTransform.identity(
            PmxReferenceTargetKind.MATERIAL,
            2,
        )
        bone = PmxCollectionTransform(
            kind=PmxReferenceTargetKind.BONE,
            remap=PmxIndexRemap(targets=(1, 0), new_size=2),
        )

        intent = PmxStructuralTransformIntent(
            transforms=(vertex, material, bone),
        )

        self.assertEqual(
            intent.changed_kinds,
            (
                PmxReferenceTargetKind.VERTEX,
                PmxReferenceTargetKind.BONE,
            ),
        )
        self.assertFalse(intent.is_noop)
        self.assertIs(intent.transform_for(PmxReferenceTargetKind.VERTEX), vertex)
        self.assertIs(intent.transform_for(PmxReferenceTargetKind.MATERIAL), material)
        self.assertIsNone(intent.transform_for(PmxReferenceTargetKind.MORPH))
        self.assertEqual(hash(intent), hash(intent))

    def test_empty_and_all_identity_coordinated_intents_are_noop(self) -> None:
        empty = PmxStructuralTransformIntent()
        identities = PmxStructuralTransformIntent(
            transforms=(
                PmxCollectionTransform.identity(
                    PmxReferenceTargetKind.TEXTURE,
                    0,
                ),
                PmxCollectionTransform.identity(
                    PmxReferenceTargetKind.BONE,
                    1,
                ),
            )
        )

        self.assertTrue(empty.is_noop)
        self.assertEqual(empty.changed_kinds, ())
        self.assertTrue(identities.is_noop)
        self.assertEqual(identities.changed_kinds, ())

    def test_coordinated_intent_rejects_duplicate_target_kinds(self) -> None:
        first = PmxCollectionTransform.identity(
            PmxReferenceTargetKind.MORPH,
            1,
        )
        second = PmxCollectionTransform(
            kind=PmxReferenceTargetKind.MORPH,
            remap=PmxIndexRemap(targets=(None,), new_size=0),
        )

        with self.assertRaisesRegex(ValueError, "duplicate target kinds"):
            PmxStructuralTransformIntent(transforms=(first, second))

    def test_coordinated_intent_rejects_noncanonical_kind_order(self) -> None:
        texture = PmxCollectionTransform.identity(
            PmxReferenceTargetKind.TEXTURE,
            1,
        )
        vertex = PmxCollectionTransform.identity(
            PmxReferenceTargetKind.VERTEX,
            1,
        )

        with self.assertRaisesRegex(ValueError, "canonical"):
            PmxStructuralTransformIntent(transforms=(texture, vertex))

    def test_coordinated_intent_rejects_mutable_or_invalid_transform_sequence(
        self,
    ) -> None:
        transform = PmxCollectionTransform.identity(
            PmxReferenceTargetKind.VERTEX,
            0,
        )

        with self.assertRaises(TypeError):
            PmxStructuralTransformIntent(  # type: ignore[arg-type]
                transforms=[transform],
            )
        with self.assertRaises(TypeError):
            PmxStructuralTransformIntent(
                transforms=(object(),),  # type: ignore[arg-type]
            )

    def test_transform_for_requires_typed_target_kind(self) -> None:
        intent = PmxStructuralTransformIntent()

        with self.assertRaises(TypeError):
            intent.transform_for("vertex")  # type: ignore[arg-type]

    def test_cp10_remains_internal_and_does_not_expand_public_boundaries(self) -> None:
        for name in ("PmxCollectionTransform", "PmxStructuralTransformIntent"):
            self.assertNotIn(name, pmx.__all__)
            self.assertNotIn(name, services.__all__)


if __name__ == "__main__":
    unittest.main()
