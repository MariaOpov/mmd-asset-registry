"""Freeze CP14 mixed six-target transaction composition."""

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
from mmd_registry.pmx.structural_insert_intent import PmxStructuralInsertPosition
from mmd_registry.pmx.structural_transaction_insertion import (
    PmxStructuralTransactionInsertionOperation,
)


COMPOSITION_MODULE_NAME = (
    "mmd_registry.pmx.structural_transaction_composition"
)


def _composition_module():
    return importlib.import_module(COMPOSITION_MODULE_NAME)


def _source_counts(
    **overrides: int,
) -> tuple[tuple[PmxReferenceTargetKind, int], ...]:
    return tuple(
        (target_kind, overrides.get(target_kind.value, 0))
        for target_kind in PmxReferenceTargetKind
    )


def _index_widths(
    **overrides: int,
) -> tuple[tuple[PmxReferenceTargetKind, int], ...]:
    return tuple(
        (target_kind, overrides.get(target_kind.value, 4))
        for target_kind in PmxReferenceTargetKind
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


def _mixed_inputs():
    source_counts = _source_counts(
        vertex=4,
        texture=3,
        material=4,
        bone=4,
        morph=4,
        rigid_body=3,
    )
    transforms = (
        _transform(
            PmxReferenceTargetKind.VERTEX,
            (2, 0, 3),
            source_count=4,
        ),
        _transform(
            PmxReferenceTargetKind.MATERIAL,
            (3, 1, 0),
            source_count=4,
        ),
        _transform(
            PmxReferenceTargetKind.BONE,
            (1, 3, 0, 2),
            source_count=4,
        ),
        _transform(
            PmxReferenceTargetKind.MORPH,
            (2, 0),
            source_count=4,
        ),
        _transform(
            PmxReferenceTargetKind.RIGID_BODY,
            (2, 0),
            source_count=3,
        ),
    )
    operations = (
        _operation(
            0,
            PmxReferenceTargetKind.TEXTURE,
            new_id="texture.new",
        ),
        _operation(
            1,
            PmxReferenceTargetKind.BONE,
            new_id="bone.new",
        ),
        _operation(
            2,
            PmxReferenceTargetKind.MATERIAL,
            position=PmxStructuralInsertPosition.insert_before(1),
            new_id="material.new",
        ),
        _operation(
            3,
            PmxReferenceTargetKind.RIGID_BODY,
            position=PmxStructuralInsertPosition.insert_before(0),
            new_id="rigid.new",
        ),
        _operation(
            4,
            PmxReferenceTargetKind.VERTEX,
            position=PmxStructuralInsertPosition.insert_before(0),
            new_id="vertex.new",
        ),
        _operation(
            5,
            PmxReferenceTargetKind.MORPH,
            new_id="morph.new",
        ),
    )
    return source_counts, transforms, operations


def _plan(
    *,
    source_counts=None,
    index_widths=None,
    transforms=(),
    operations=(),
):
    return _composition_module().compose_structural_transaction(
        source_counts=(
            _source_counts() if source_counts is None else source_counts
        ),
        index_widths=(
            _index_widths() if index_widths is None else index_widths
        ),
        transforms=transforms,
        operations=operations,
    )


class V093StructuralTransactionMixedSixTargetTests(unittest.TestCase):
    def test_internal_composition_is_frozen_and_not_publicly_exported(
        self,
    ) -> None:
        composition = _composition_module()
        expected_exports = (
            "PmxStructuralTransactionComposition",
            "compose_structural_transaction",
        )
        self.assertEqual(composition.__all__, expected_exports)
        for name in expected_exports:
            self.assertFalse(hasattr(mmd_registry, name), name)
            self.assertFalse(hasattr(pmx, name), name)
            self.assertFalse(hasattr(services, name), name)

        plan = _plan()
        self.assertTrue(is_dataclass(plan))
        self.assertFalse(hasattr(plan, "__dict__"))
        self.assertEqual(
            tuple(field.name for field in fields(plan)),
            (
                "source_counts",
                "index_widths",
                "transforms",
                "operations",
                "dependency",
                "placements",
                "bindings",
                "identities",
                "preflight",
                "reference_resolver",
            ),
        )
        with self.assertRaises(FrozenInstanceError):
            plan.placements = ()

        source = inspect.getsource(composition)
        self.assertNotIn("mmd_registry.services", source)
        for forbidden in (
            "PmxStructuralNewReference",
            "preview_structural_transaction",
            "apply_structural_transaction",
            "PmxDocument",
            "open(",
        ):
            self.assertNotIn(forbidden, source)

    def test_empty_and_explicit_identity_inputs_do_not_create_changes(
        self,
    ) -> None:
        source_counts = _source_counts(texture=2)
        empty = _plan(source_counts=source_counts)
        self.assertEqual(empty.changed_targets, ())
        self.assertEqual(empty.placements, ())
        self.assertEqual(empty.bindings, ())
        self.assertEqual(empty.identities, ())
        self.assertEqual(empty.dependency.materialization_order, ())

        identity = PmxCollectionTransform.identity(
            PmxReferenceTargetKind.TEXTURE,
            2,
        )
        explicit = _plan(
            source_counts=source_counts,
            transforms=(identity,),
        )
        self.assertEqual(explicit.changed_targets, ())
        self.assertEqual(len(explicit.placements), 1)
        self.assertIs(explicit.placements[0].transform, identity)
        self.assertEqual(
            explicit.reference_resolver.resolve_source_reference(
                PmxReferenceTargetKind.TEXTURE,
                1,
                allow_sentinel=False,
                field_name="texture_index",
            ),
            1,
        )

    def test_full_mixed_transaction_composes_all_six_target_maps(self) -> None:
        source_counts, transforms, operations = _mixed_inputs()
        plan = _plan(
            source_counts=source_counts,
            transforms=transforms,
            operations=operations,
        )

        self.assertEqual(plan.changed_targets, tuple(PmxReferenceTargetKind))
        self.assertEqual(
            tuple(placement.target_kind for placement in plan.placements),
            tuple(PmxReferenceTargetKind),
        )
        self.assertEqual(plan.total_insert_count, 6)
        self.assertEqual(
            plan.preflight.final_counts,
            (
                (PmxReferenceTargetKind.VERTEX, 4),
                (PmxReferenceTargetKind.TEXTURE, 4),
                (PmxReferenceTargetKind.MATERIAL, 4),
                (PmxReferenceTargetKind.BONE, 5),
                (PmxReferenceTargetKind.MORPH, 3),
                (PmxReferenceTargetKind.RIGID_BODY, 3),
            ),
        )
        expected_maps = {
            PmxReferenceTargetKind.VERTEX: ((2, None, 0, 3), (1,)),
            PmxReferenceTargetKind.TEXTURE: ((0, 1, 2), (3,)),
            PmxReferenceTargetKind.MATERIAL: ((3, 2, None, 0), (1,)),
            PmxReferenceTargetKind.BONE: ((2, 0, 3, 1), (4,)),
            PmxReferenceTargetKind.MORPH: ((1, None, 0, None), (2,)),
            PmxReferenceTargetKind.RIGID_BODY: ((2, None, 0), (1,)),
        }
        for target_kind, (targets, new_only) in expected_maps.items():
            with self.subTest(target_kind=target_kind):
                placement = plan.placement_for(target_kind)
                assert placement is not None
                self.assertEqual(placement.remap.targets, targets)
                self.assertEqual(
                    placement.remap.new_indices_without_old_source,
                    new_only,
                )

        self.assertEqual(
            tuple(
                (
                    binding.request_ordinal,
                    binding.target_kind,
                    binding.final_index,
                )
                for binding in plan.bindings
            ),
            (
                (0, PmxReferenceTargetKind.TEXTURE, 3),
                (1, PmxReferenceTargetKind.BONE, 4),
                (2, PmxReferenceTargetKind.MATERIAL, 1),
                (3, PmxReferenceTargetKind.RIGID_BODY, 1),
                (4, PmxReferenceTargetKind.VERTEX, 1),
                (5, PmxReferenceTargetKind.MORPH, 2),
            ),
        )
        self.assertEqual(
            tuple(
                (
                    identity.target_kind,
                    identity.new_id,
                    identity.operation_index,
                    identity.final_index,
                )
                for identity in plan.identities
            ),
            (
                (PmxReferenceTargetKind.VERTEX, "vertex.new", 4, 1),
                (PmxReferenceTargetKind.TEXTURE, "texture.new", 0, 3),
                (PmxReferenceTargetKind.MATERIAL, "material.new", 2, 1),
                (PmxReferenceTargetKind.BONE, "bone.new", 1, 4),
                (PmxReferenceTargetKind.MORPH, "morph.new", 5, 2),
                (PmxReferenceTargetKind.RIGID_BODY, "rigid.new", 3, 1),
            ),
        )

    def test_six_target_dependency_and_authorized_reference_results_agree(
        self,
    ) -> None:
        source_counts, transforms, operations = _mixed_inputs()
        plan = _plan(
            source_counts=source_counts,
            transforms=transforms,
            operations=operations,
        )
        self.assertEqual(
            tuple(
                (edge.provider_target, edge.consumer_target)
                for edge in plan.dependency.edges
            ),
            (
                (
                    PmxReferenceTargetKind.TEXTURE,
                    PmxReferenceTargetKind.MATERIAL,
                ),
                (PmxReferenceTargetKind.BONE, PmxReferenceTargetKind.VERTEX),
                (
                    PmxReferenceTargetKind.BONE,
                    PmxReferenceTargetKind.RIGID_BODY,
                ),
                (PmxReferenceTargetKind.MATERIAL, PmxReferenceTargetKind.MORPH),
                (PmxReferenceTargetKind.BONE, PmxReferenceTargetKind.MORPH),
                (PmxReferenceTargetKind.VERTEX, PmxReferenceTargetKind.MORPH),
                (
                    PmxReferenceTargetKind.RIGID_BODY,
                    PmxReferenceTargetKind.MORPH,
                ),
            ),
        )
        self.assertEqual(
            plan.dependency.materialization_order,
            (
                PmxReferenceTargetKind.TEXTURE,
                PmxReferenceTargetKind.MATERIAL,
                PmxReferenceTargetKind.BONE,
                PmxReferenceTargetKind.VERTEX,
                PmxReferenceTargetKind.RIGID_BODY,
                PmxReferenceTargetKind.MORPH,
            ),
        )

        resolver = plan.reference_resolver
        for target_kind, new_id, expected in (
            (PmxReferenceTargetKind.TEXTURE, "texture.new", 3),
            (PmxReferenceTargetKind.MATERIAL, "material.new", 1),
            (PmxReferenceTargetKind.BONE, "bone.new", 4),
            (PmxReferenceTargetKind.VERTEX, "vertex.new", 1),
            (PmxReferenceTargetKind.RIGID_BODY, "rigid.new", 1),
        ):
            with self.subTest(target_kind=target_kind, new_id=new_id):
                self.assertEqual(
                    resolver.resolve_new_reference(
                        target_kind,
                        new_id,
                        field_name=f"{target_kind.value}_reference",
                    ),
                    expected,
                )
        self.assertEqual(
            resolver.resolve_source_reference(
                PmxReferenceTargetKind.BONE,
                2,
                allow_sentinel=False,
                field_name="bone_index",
            ),
            3,
        )
        with self.assertRaisesRegex(
            ValueError,
            r"removed captured-source vertex\[1\]",
        ):
            resolver.resolve_source_reference(
                PmxReferenceTargetKind.VERTEX,
                1,
                allow_sentinel=False,
                field_name="vertex_index",
            )

    def test_cross_target_validation_fails_before_composition(self) -> None:
        source_counts = _source_counts(vertex=2, texture=2, material=2)
        duplicate_id_operations = (
            _operation(0, PmxReferenceTargetKind.VERTEX, new_id="shared"),
            _operation(1, PmxReferenceTargetKind.TEXTURE, new_id="shared"),
        )
        with self.assertRaisesRegex(ValueError, r"globally unique"):
            _plan(
                source_counts=source_counts,
                operations=duplicate_id_operations,
            )

        vertex = PmxCollectionTransform.identity(
            PmxReferenceTargetKind.VERTEX,
            2,
        )
        material = PmxCollectionTransform.identity(
            PmxReferenceTargetKind.MATERIAL,
            2,
        )
        with self.assertRaisesRegex(ValueError, r"canonical"):
            _plan(
                source_counts=source_counts,
                transforms=(material, vertex),
            )
        with self.assertRaisesRegex(ValueError, r"old_size must match"):
            _plan(
                source_counts=source_counts,
                transforms=(
                    PmxCollectionTransform.identity(
                        PmxReferenceTargetKind.VERTEX,
                        1,
                    ),
                ),
            )

        deleting_vertex = _transform(
            PmxReferenceTargetKind.VERTEX,
            (1,),
            source_count=2,
        )
        deleted_anchor = _operation(
            0,
            PmxReferenceTargetKind.VERTEX,
            position=PmxStructuralInsertPosition.insert_before(0),
        )
        with self.assertRaisesRegex(ValueError, r"anchor vertex\[0\] is deleted"):
            _plan(
                source_counts=source_counts,
                transforms=(deleting_vertex,),
                operations=(deleted_anchor,),
            )

    def test_repeated_full_composition_is_deterministic_and_input_immutable(
        self,
    ) -> None:
        source_counts, transforms, operations = _mixed_inputs()
        original_transform_state = tuple(
            (transform.kind, transform.remap.targets, transform.remap.new_size)
            for transform in transforms
        )
        plans = tuple(
            _plan(
                source_counts=source_counts,
                transforms=transforms,
                operations=operations,
            )
            for _ in range(25)
        )

        self.assertTrue(all(plan == plans[0] for plan in plans))
        self.assertIs(plans[0].source_counts, source_counts)
        self.assertIs(plans[0].transforms, transforms)
        self.assertIs(plans[0].operations, operations)
        self.assertEqual(
            tuple(
                (
                    transform.kind,
                    transform.remap.targets,
                    transform.remap.new_size,
                )
                for transform in transforms
            ),
            original_transform_state,
        )
        self.assertEqual(
            tuple(
                plans[0].binding_for_operation(ordinal).final_index
                for ordinal in range(6)
            ),
            (3, 4, 1, 1, 1, 2),
        )


if __name__ == "__main__":
    unittest.main()
