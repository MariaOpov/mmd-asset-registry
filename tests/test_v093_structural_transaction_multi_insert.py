"""Freeze v0.9.3 insertion-only transaction composition."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, is_dataclass
import importlib
import inspect
import unittest

import mmd_registry
import mmd_registry.pmx as pmx
import mmd_registry.services as services
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.pmx.structural_insert_intent import PmxStructuralInsertPosition
from mmd_registry.pmx.structural_reference_shift import (
    PmxStructuralReferenceShiftError,
)
from mmd_registry.services.structural_material import (
    PmxStructuralMaterialInsertion,
)
from mmd_registry.services.structural_reference import PmxStructuralNewReference
from mmd_registry.services.structural_rigid_body import (
    PmxStructuralRigidBodyInsertion,
)


INSERTION_MODULE_NAME = "mmd_registry.pmx.structural_transaction_insertion"


def _insertion_module():
    return importlib.import_module(INSERTION_MODULE_NAME)


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


def _operation(
    request_ordinal: int,
    target_kind: PmxReferenceTargetKind,
    *,
    position: PmxStructuralInsertPosition | None = None,
    new_id: str | None = None,
):
    return _insertion_module().PmxStructuralTransactionInsertionOperation(
        request_ordinal=request_ordinal,
        target_kind=target_kind,
        position=(
            PmxStructuralInsertPosition.append()
            if position is None
            else position
        ),
        new_id=new_id,
    )


def _plan(*, source_counts=None, index_widths=None, operations=()):
    return _insertion_module().plan_structural_transaction_insertions(
        source_counts=(
            _source_counts() if source_counts is None else source_counts
        ),
        index_widths=(
            _index_widths() if index_widths is None else index_widths
        ),
        operations=operations,
    )


class V093StructuralTransactionMultiInsertTests(unittest.TestCase):
    """Keep CP10 immutable, insertion-only and authority-reusing."""

    def test_internal_plan_is_frozen_slotted_and_not_root_exported(self) -> None:
        insertion = _insertion_module()
        expected_exports = (
            "PmxStructuralTransactionInsertionBinding",
            "PmxStructuralTransactionInsertionOperation",
            "PmxStructuralTransactionInsertionPlan",
            "plan_structural_transaction_insertions",
        )
        self.assertEqual(insertion.__all__, expected_exports)
        for name in expected_exports:
            self.assertFalse(hasattr(mmd_registry, name), name)
            self.assertFalse(hasattr(pmx, name), name)
            self.assertFalse(hasattr(services, name), name)

        operation = _operation(
            0,
            PmxReferenceTargetKind.TEXTURE,
            new_id="texture",
        )
        plan = _plan(operations=(operation,))
        binding = plan.bindings[0]
        for value in (operation, binding, plan):
            self.assertTrue(is_dataclass(value))
            self.assertFalse(hasattr(value, "__dict__"))

        self.assertEqual(
            tuple(field.name for field in fields(operation)),
            ("request_ordinal", "target_kind", "position", "new_id"),
        )
        self.assertEqual(
            tuple(field.name for field in fields(binding)),
            (
                "request_ordinal",
                "target_kind",
                "target_insertion_index",
                "final_index",
            ),
        )
        self.assertEqual(
            tuple(field.name for field in fields(plan)),
            (
                "source_counts",
                "index_widths",
                "operations",
                "dependency",
                "shifts",
                "bindings",
                "identities",
                "reference_resolver",
            ),
        )
        with self.assertRaises(FrozenInstanceError):
            operation.new_id = "changed"
        with self.assertRaises(FrozenInstanceError):
            binding.final_index = 99
        with self.assertRaises(FrozenInstanceError):
            plan.operations = ()

        source = inspect.getsource(insertion)
        self.assertNotIn("mmd_registry.services", source)
        for forbidden in (
            "preview_structural_transaction",
            "apply_structural_transaction",
            "execute_structural_transaction",
            "PmxDocument",
            "open(",
        ):
            self.assertNotIn(forbidden, source)

    def test_empty_plan_is_a_deterministic_immutable_no_op(self) -> None:
        source_counts = _source_counts(bone=2)
        index_widths = _index_widths()
        plan = _plan(
            source_counts=source_counts,
            index_widths=index_widths,
        )
        self.assertIs(plan.source_counts, source_counts)
        self.assertIs(plan.index_widths, index_widths)
        self.assertEqual(plan.total_insert_count, 0)
        self.assertEqual(plan.changed_targets, ())
        self.assertEqual(plan.shifts, ())
        self.assertEqual(plan.bindings, ())
        self.assertEqual(plan.identities, ())
        self.assertEqual(plan.dependency.nodes, ())
        self.assertEqual(plan.dependency.edges, ())
        self.assertEqual(plan.dependency.materialization_order, ())
        self.assertEqual(
            plan.reference_resolver.resolve_source_reference(
                PmxReferenceTargetKind.BONE,
                1,
                allow_sentinel=False,
                field_name="bone_index",
            ),
            1,
        )

    def test_same_kind_insertions_keep_request_ties_and_final_indices(self) -> None:
        operations = (
            _operation(
                2,
                PmxReferenceTargetKind.TEXTURE,
                new_id="append",
            ),
            _operation(
                5,
                PmxReferenceTargetKind.TEXTURE,
                position=PmxStructuralInsertPosition.insert_before(1),
                new_id="before_a",
            ),
            _operation(
                8,
                PmxReferenceTargetKind.TEXTURE,
                position=PmxStructuralInsertPosition.insert_before(1),
                new_id="before_b",
            ),
        )
        source_counts = _source_counts(texture=3)
        plan = _plan(source_counts=source_counts, operations=operations)
        shift = plan.shift_for(PmxReferenceTargetKind.TEXTURE)
        assert shift is not None

        self.assertEqual(plan.total_insert_count, 3)
        self.assertEqual(plan.changed_targets, (PmxReferenceTargetKind.TEXTURE,))
        self.assertEqual(shift.remap.targets, (0, 3, 4))
        self.assertEqual(shift.remap.new_indices_without_old_source, (1, 2, 5))
        self.assertEqual(shift.new_indices_in_request_order, (5, 1, 2))
        self.assertEqual(
            tuple(
                (
                    binding.request_ordinal,
                    binding.target_insertion_index,
                    binding.final_index,
                )
                for binding in plan.bindings
            ),
            ((2, 0, 5), (5, 1, 1), (8, 2, 2)),
        )
        self.assertEqual(
            tuple(
                (identity.new_id, identity.operation_index, identity.final_index)
                for identity in plan.identities
            ),
            (("before_a", 5, 1), ("before_b", 8, 2), ("append", 2, 5)),
        )

        resolver = plan.reference_resolver
        self.assertEqual(
            resolver.resolve_source_reference(
                PmxReferenceTargetKind.TEXTURE,
                1,
                allow_sentinel=False,
                field_name="texture_index",
            ),
            3,
        )
        for new_id, expected in (("append", 5), ("before_a", 1), ("before_b", 2)):
            with self.subTest(new_id=new_id):
                self.assertEqual(
                    resolver.resolve_new_reference(
                        PmxReferenceTargetKind.TEXTURE,
                        new_id,
                        field_name="texture_index",
                    ),
                    expected,
                )

        self.assertEqual(source_counts, _source_counts(texture=3))
        self.assertEqual(operations, plan.operations)
        for _ in range(20):
            self.assertEqual(
                _plan(source_counts=source_counts, operations=operations),
                plan,
            )

    def test_cross_kind_forward_new_references_use_one_final_state(self) -> None:
        texture_reference = PmxStructuralNewReference("texture", "texture")
        bone_reference = PmxStructuralNewReference("bone", "bone")
        material = PmxStructuralMaterialInsertion(
            "material",
            texture_index=texture_reference,
            sphere_texture_index=texture_reference,
            toon_reference_index=texture_reference,
            new_id="material",
        )
        rigid_body = PmxStructuralRigidBodyInsertion(
            "rigid",
            bone_index=bone_reference,
            new_id="rigid_body",
        )
        operations = (
            _operation(
                0,
                PmxReferenceTargetKind.MATERIAL,
                new_id=material.new_id,
            ),
            _operation(
                1,
                PmxReferenceTargetKind.RIGID_BODY,
                new_id=rigid_body.new_id,
            ),
            _operation(
                2,
                PmxReferenceTargetKind.TEXTURE,
                position=PmxStructuralInsertPosition.insert_before(0),
                new_id="texture",
            ),
            _operation(
                3,
                PmxReferenceTargetKind.BONE,
                new_id="bone",
            ),
        )
        plan = _plan(
            source_counts=_source_counts(texture=1, material=1, bone=1),
            operations=operations,
        )

        self.assertEqual(
            plan.changed_targets,
            (
                PmxReferenceTargetKind.TEXTURE,
                PmxReferenceTargetKind.MATERIAL,
                PmxReferenceTargetKind.BONE,
                PmxReferenceTargetKind.RIGID_BODY,
            ),
        )
        self.assertEqual(
            plan.dependency.materialization_order,
            (
                PmxReferenceTargetKind.TEXTURE,
                PmxReferenceTargetKind.MATERIAL,
                PmxReferenceTargetKind.BONE,
                PmxReferenceTargetKind.RIGID_BODY,
            ),
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
                (
                    PmxReferenceTargetKind.BONE,
                    PmxReferenceTargetKind.RIGID_BODY,
                ),
            ),
        )
        self.assertEqual(
            tuple(
                (binding.request_ordinal, binding.final_index)
                for binding in plan.bindings
            ),
            ((0, 1), (1, 0), (2, 0), (3, 1)),
        )

        resolver = plan.reference_resolver
        for reference, kind, field_name, expected in (
            (
                material.texture_index,
                PmxReferenceTargetKind.TEXTURE,
                "texture_index",
                0,
            ),
            (
                rigid_body.bone_index,
                PmxReferenceTargetKind.BONE,
                "bone_index",
                1,
            ),
        ):
            assert isinstance(reference, PmxStructuralNewReference)
            self.assertEqual(reference.target_kind, kind.value)
            self.assertEqual(
                resolver.resolve_new_reference(
                    kind,
                    reference.new_id,
                    field_name=field_name,
                ),
                expected,
            )

        self.assertEqual(
            resolver.resolve_source_reference(
                PmxReferenceTargetKind.TEXTURE,
                0,
                allow_sentinel=False,
                field_name="texture_index",
            ),
            1,
        )

    def test_capacity_is_checked_for_every_changed_target_before_a_plan(self) -> None:
        two_vertices = (
            _operation(0, PmxReferenceTargetKind.VERTEX),
            _operation(1, PmxReferenceTargetKind.VERTEX),
        )
        vertex_boundary = _plan(
            source_counts=_source_counts(vertex=254),
            index_widths=_index_widths(vertex=1),
            operations=two_vertices,
        )
        vertex_shift = vertex_boundary.shift_for(
            PmxReferenceTargetKind.VERTEX
        )
        assert vertex_shift is not None
        self.assertEqual(vertex_shift.result_count, 256)
        self.assertTrue(vertex_shift.capacity.representable)

        with self.assertRaisesRegex(
            PmxStructuralReferenceShiftError,
            r"cannot plan vertex insertion shift",
        ):
            _plan(
                source_counts=_source_counts(vertex=255),
                index_widths=_index_widths(vertex=1),
                operations=two_vertices,
            )

        two_materials = (
            _operation(0, PmxReferenceTargetKind.MATERIAL),
            _operation(1, PmxReferenceTargetKind.MATERIAL),
        )
        material_boundary = _plan(
            source_counts=_source_counts(material=126),
            index_widths=_index_widths(material=1),
            operations=two_materials,
        )
        material_shift = material_boundary.shift_for(
            PmxReferenceTargetKind.MATERIAL
        )
        assert material_shift is not None
        self.assertEqual(material_shift.result_count, 128)
        self.assertTrue(material_shift.capacity.representable)

        with self.assertRaisesRegex(
            PmxStructuralReferenceShiftError,
            r"cannot plan material insertion shift",
        ):
            _plan(
                source_counts=_source_counts(material=127),
                index_widths=_index_widths(material=1),
                operations=two_materials,
            )

    def test_invalid_environment_operations_and_anchors_fail_closed(self) -> None:
        insertion = _insertion_module()
        operation_type = insertion.PmxStructuralTransactionInsertionOperation
        cases = (
            (
                lambda: _plan(source_counts=[]),
                TypeError,
                r"source_counts must be a tuple",
            ),
            (
                lambda: _plan(source_counts=tuple(reversed(_source_counts()))),
                ValueError,
                r"source_counts.*canonical order",
            ),
            (
                lambda: _plan(source_counts=_source_counts(texture=True)),
                TypeError,
                r"source_counts\[1\] count must be an integer",
            ),
            (
                lambda: _plan(index_widths=_index_widths(texture=3)),
                ValueError,
                r"index_widths\[1\] width must be one of",
            ),
            (
                lambda: _plan(operations=[]),
                TypeError,
                r"operations must be a tuple",
            ),
            (
                lambda: _plan(operations=(object(),)),
                TypeError,
                r"operations\[0\].*InsertionOperation",
            ),
            (
                lambda: _plan(
                    operations=(
                        _operation(2, PmxReferenceTargetKind.TEXTURE),
                        _operation(1, PmxReferenceTargetKind.MATERIAL),
                    )
                ),
                ValueError,
                r"strictly increasing unique request_ordinal",
            ),
            (
                lambda: _plan(
                    operations=(
                        _operation(1, PmxReferenceTargetKind.TEXTURE),
                        _operation(1, PmxReferenceTargetKind.MATERIAL),
                    )
                ),
                ValueError,
                r"strictly increasing unique request_ordinal",
            ),
            (
                lambda: _plan(
                    operations=(
                        _operation(
                            0,
                            PmxReferenceTargetKind.TEXTURE,
                            position=PmxStructuralInsertPosition.insert_before(0),
                        ),
                    )
                ),
                ValueError,
                r"source_index must be less than current_count",
            ),
            (
                lambda: operation_type(
                    True,
                    PmxReferenceTargetKind.TEXTURE,
                    PmxStructuralInsertPosition.append(),
                ),
                TypeError,
                r"request_ordinal must be an integer",
            ),
            (
                lambda: operation_type(
                    0,
                    PmxReferenceTargetKind.TEXTURE,
                    PmxStructuralInsertPosition.append(),
                    123,
                ),
                TypeError,
                r"new_id must be a string or None",
            ),
        )
        for build, error, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(error, message):
                    build()

        duplicate_ids_with_impossible_capacity = (
            _operation(
                0,
                PmxReferenceTargetKind.TEXTURE,
                new_id="duplicate",
            ),
            _operation(
                1,
                PmxReferenceTargetKind.MATERIAL,
                new_id="duplicate",
            ),
        )
        with self.assertRaisesRegex(
            ValueError,
            r"new_id 'duplicate' must be globally unique",
        ):
            _plan(
                source_counts=_source_counts(texture=256),
                index_widths=_index_widths(texture=1),
                operations=duplicate_ids_with_impossible_capacity,
            )


if __name__ == "__main__":
    unittest.main()
