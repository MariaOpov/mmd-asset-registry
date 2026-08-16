"""Contracts for the immutable CP09 index-remap primitive."""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from mmd_registry.pmx.index_remap import PmxIndexRemap


class PmxIndexRemapTests(unittest.TestCase):
    """Freeze deterministic old->new/removed mapping invariants."""

    def test_identity_is_immutable_hashable_and_empty_safe(self) -> None:
        empty = PmxIndexRemap.identity(0)
        mapping = PmxIndexRemap.identity(4)

        self.assertEqual(empty.targets, ())
        self.assertEqual(empty.old_size, 0)
        self.assertEqual(empty.new_size, 0)
        self.assertTrue(empty.is_identity)

        self.assertEqual(mapping.targets, (0, 1, 2, 3))
        self.assertEqual(mapping.old_size, 4)
        self.assertEqual(mapping.removed_old_indices, ())
        self.assertFalse(mapping.has_new_indices_without_old_source)
        self.assertTrue(mapping.is_identity)
        self.assertEqual(hash(mapping), hash(mapping))

        with self.assertRaises(FrozenInstanceError):
            mapping.new_size = 3  # type: ignore[misc]

    def test_delete_and_reorder_mapping_is_explicit_and_deterministic(self) -> None:
        mapping = PmxIndexRemap(
            targets=(2, None, 0, 1),
            new_size=3,
        )

        self.assertEqual(mapping.old_size, 4)
        self.assertEqual(mapping.new_size, 3)
        self.assertEqual(mapping.removed_old_indices, (1,))
        self.assertFalse(mapping.is_identity)
        self.assertEqual(
            tuple(mapping.target_for(index) for index in range(mapping.old_size)),
            (2, None, 0, 1),
        )

    def test_complete_removal_is_legal_at_primitive_level(self) -> None:
        mapping = PmxIndexRemap(
            targets=(None, None, None),
            new_size=0,
        )

        self.assertEqual(mapping.old_size, 3)
        self.assertEqual(mapping.new_size, 0)
        self.assertEqual(mapping.removed_old_indices, (0, 1, 2))
        self.assertEqual(mapping.target_for(1), None)

    def test_future_new_only_indices_can_complete_the_dense_target_range(self) -> None:
        mapping = PmxIndexRemap(
            targets=(1, 2),
            new_size=3,
            new_indices_without_old_source=(0,),
        )

        self.assertEqual(mapping.old_size, 2)
        self.assertEqual(mapping.new_size, 3)
        self.assertEqual(mapping.target_for(0), 1)
        self.assertEqual(mapping.target_for(1), 2)
        self.assertEqual(mapping.new_indices_without_old_source, (0,))
        self.assertTrue(mapping.has_new_indices_without_old_source)
        self.assertFalse(mapping.is_identity)

    def test_new_collection_can_be_entirely_new_without_changing_old_domain_model(
        self,
    ) -> None:
        mapping = PmxIndexRemap(
            targets=(),
            new_size=2,
            new_indices_without_old_source=(0, 1),
        )

        self.assertEqual(mapping.old_size, 0)
        self.assertEqual(mapping.new_size, 2)
        self.assertTrue(mapping.has_new_indices_without_old_source)

    def test_rejects_non_tuple_collections_and_invalid_size_types(self) -> None:
        with self.assertRaises(TypeError):
            PmxIndexRemap(targets=[], new_size=0)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            PmxIndexRemap(targets=(), new_size=True)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            PmxIndexRemap(targets=(), new_size=0.0)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            PmxIndexRemap(  # type: ignore[arg-type]
                targets=(),
                new_size=0,
                new_indices_without_old_source=[],
            )
        with self.assertRaises(TypeError):
            PmxIndexRemap.identity(False)  # type: ignore[arg-type]

    def test_rejects_boolean_float_and_negative_mapping_targets(self) -> None:
        for target in (True, False, 0.0, "0"):
            with self.subTest(target=target):
                with self.assertRaises(TypeError):
                    PmxIndexRemap(
                        targets=(target,),  # type: ignore[arg-type]
                        new_size=1,
                    )

        with self.assertRaisesRegex(ValueError, "use None for removal"):
            PmxIndexRemap(targets=(-1,), new_size=1)

    def test_rejects_out_of_range_mapping_and_new_only_indices(self) -> None:
        with self.assertRaisesRegex(ValueError, "outside new_size"):
            PmxIndexRemap(targets=(1,), new_size=1)

        with self.assertRaisesRegex(ValueError, "outside new_size"):
            PmxIndexRemap(
                targets=(),
                new_size=1,
                new_indices_without_old_source=(1,),
            )

        with self.assertRaisesRegex(ValueError, "negative"):
            PmxIndexRemap(
                targets=(),
                new_size=1,
                new_indices_without_old_source=(-1,),
            )

        with self.assertRaises(TypeError):
            PmxIndexRemap(
                targets=(),
                new_size=1,
                new_indices_without_old_source=(True,),  # type: ignore[arg-type]
            )

    def test_rejects_duplicate_new_targets_and_mapped_new_only_overlap(self) -> None:
        with self.assertRaisesRegex(ValueError, "mapped more than once"):
            PmxIndexRemap(targets=(0, 0), new_size=1)

        with self.assertRaisesRegex(ValueError, "both mapped and new-only"):
            PmxIndexRemap(
                targets=(0,),
                new_size=1,
                new_indices_without_old_source=(0,),
            )

    def test_rejects_sparse_or_nondeterministic_new_only_ranges(self) -> None:
        with self.assertRaisesRegex(ValueError, "densely cover"):
            PmxIndexRemap(targets=(0, 2), new_size=3)

        # Dense-range validation must be proportional to supplied mapping data,
        # not to an arbitrarily large declared new_size.
        with self.assertRaisesRegex(ValueError, "densely cover"):
            PmxIndexRemap(targets=(), new_size=10**12)

        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            PmxIndexRemap(
                targets=(),
                new_size=2,
                new_indices_without_old_source=(1, 0),
            )

        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            PmxIndexRemap(
                targets=(),
                new_size=1,
                new_indices_without_old_source=(0, 0),
            )

    def test_target_for_rejects_invalid_old_indices_and_booleans(self) -> None:
        mapping = PmxIndexRemap.identity(2)

        with self.assertRaises(TypeError):
            mapping.target_for(True)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            mapping.target_for(-1)
        with self.assertRaisesRegex(ValueError, "outside old_size"):
            mapping.target_for(2)

    def test_removed_state_is_none_and_never_minus_one(self) -> None:
        mapping = PmxIndexRemap(
            targets=(None, 0),
            new_size=1,
        )

        self.assertIsNone(mapping.target_for(0))
        self.assertEqual(mapping.target_for(1), 0)

        with self.assertRaisesRegex(ValueError, "use None for removal"):
            PmxIndexRemap(targets=(-1, 0), new_size=1)


if __name__ == "__main__":
    unittest.main()
