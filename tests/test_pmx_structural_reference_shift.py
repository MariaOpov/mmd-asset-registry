from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
import unittest

import mmd_registry.pmx as pmx
import mmd_registry.services as services
from mmd_registry.pmx.collection_transform import PmxCollectionTransform
from mmd_registry.pmx.index_remap import PmxIndexRemap
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.pmx.structural_capacity import analyze_structural_capacity
from mmd_registry.pmx.structural_insert_intent import (
    PmxCollectionInsertionIntent,
    PmxStructuralInsertPosition,
)
from mmd_registry.pmx.structural_reference_shift import (
    PmxCollectionReferenceShiftPlan,
    PmxStructuralReferenceShiftError,
    plan_collection_reference_shift,
)
from mmd_registry.pmx.validation import MAX_INT32


def _intent(
    target_kind: PmxReferenceTargetKind,
    *positions: PmxStructuralInsertPosition,
) -> PmxCollectionInsertionIntent:
    return PmxCollectionInsertionIntent(target_kind, tuple(positions))


class PmxStructuralReferenceShiftTests(unittest.TestCase):
    def test_append_only_preserves_old_indices_and_places_new_records_after_source(
        self,
    ) -> None:
        plan = plan_collection_reference_shift(
            _intent(
                PmxReferenceTargetKind.TEXTURE,
                PmxStructuralInsertPosition.append(),
                PmxStructuralInsertPosition.append(),
            ),
            current_count=3,
            index_width=1,
        )

        self.assertEqual(plan.remap.targets, (0, 1, 2))
        self.assertEqual(plan.remap.new_size, 5)
        self.assertEqual(plan.remap.new_indices_without_old_source, (3, 4))
        self.assertEqual(plan.new_indices_in_request_order, (3, 4))
        self.assertEqual(plan.result_count, 5)

    def test_insert_before_zero_shifts_every_old_record(self) -> None:
        plan = plan_collection_reference_shift(
            _intent(
                PmxReferenceTargetKind.TEXTURE,
                PmxStructuralInsertPosition.insert_before(0),
                PmxStructuralInsertPosition.insert_before(0),
            ),
            current_count=3,
            index_width=1,
        )

        self.assertEqual(plan.remap.targets, (2, 3, 4))
        self.assertEqual(plan.remap.new_indices_without_old_source, (0, 1))
        self.assertEqual(plan.new_indices_in_request_order, (0, 1))

    def test_mixed_source_anchors_derive_dense_shift_and_request_order_evidence(
        self,
    ) -> None:
        plan = plan_collection_reference_shift(
            _intent(
                PmxReferenceTargetKind.TEXTURE,
                PmxStructuralInsertPosition.insert_before(2),
                PmxStructuralInsertPosition.insert_before(0),
                PmxStructuralInsertPosition.insert_before(2),
                PmxStructuralInsertPosition.append(),
            ),
            current_count=4,
            index_width=1,
        )

        self.assertEqual(plan.remap.targets, (1, 2, 5, 6))
        self.assertEqual(
            plan.remap.new_indices_without_old_source,
            (0, 3, 4, 7),
        )
        self.assertEqual(plan.new_indices_in_request_order, (3, 0, 4, 7))
        self.assertEqual(
            tuple(plan.new_index_for_insertion(index) for index in range(4)),
            (3, 0, 4, 7),
        )

    def test_same_anchor_and_append_order_is_stable_across_repeated_planning(
        self,
    ) -> None:
        insertion = _intent(
            PmxReferenceTargetKind.BONE,
            PmxStructuralInsertPosition.insert_before(1),
            PmxStructuralInsertPosition.insert_before(1),
            PmxStructuralInsertPosition.append(),
            PmxStructuralInsertPosition.append(),
        )

        first = plan_collection_reference_shift(
            insertion,
            current_count=2,
            index_width=1,
        )
        second = plan_collection_reference_shift(
            insertion,
            current_count=2,
            index_width=1,
        )

        self.assertEqual(first, second)
        self.assertEqual(first.remap.targets, (0, 3))
        self.assertEqual(first.new_indices_in_request_order, (1, 2, 4, 5))
        self.assertEqual(
            first.remap.new_indices_without_old_source,
            (1, 2, 4, 5),
        )

    def test_empty_source_supports_append_and_entire_new_range_is_new_only(
        self,
    ) -> None:
        plan = plan_collection_reference_shift(
            _intent(
                PmxReferenceTargetKind.MATERIAL,
                PmxStructuralInsertPosition.append(),
                PmxStructuralInsertPosition.append(),
            ),
            current_count=0,
            index_width=1,
        )

        self.assertEqual(plan.remap.targets, ())
        self.assertEqual(plan.remap.new_size, 2)
        self.assertEqual(plan.remap.new_indices_without_old_source, (0, 1))
        self.assertEqual(plan.new_indices_in_request_order, (0, 1))

    def test_source_domain_validation_fails_before_planning(self) -> None:
        insertion = _intent(
            PmxReferenceTargetKind.TEXTURE,
            PmxStructuralInsertPosition.insert_before(2),
        )

        with self.assertRaisesRegex(ValueError, "less than current_count"):
            plan_collection_reference_shift(
                insertion,
                current_count=2,
                index_width=1,
            )
        with self.assertRaises(TypeError):
            plan_collection_reference_shift(
                insertion,
                current_count=True,  # type: ignore[arg-type]
                index_width=1,
            )

    def test_width_overflow_fails_closed_before_remap_construction(self) -> None:
        insertion = _intent(
            PmxReferenceTargetKind.TEXTURE,
            PmxStructuralInsertPosition.append(),
        )
        evidence = analyze_structural_capacity(
            PmxReferenceTargetKind.TEXTURE,
            current_count=128,
            insert_count=1,
            index_width=1,
        )
        self.assertFalse(evidence.width_representable)
        self.assertTrue(evidence.expansion_required)

        with self.assertRaisesRegex(
            PmxStructuralReferenceShiftError,
            "declared index width",
        ):
            plan_collection_reference_shift(
                insertion,
                current_count=128,
                index_width=1,
            )

    def test_four_byte_section_count_overflow_fails_before_large_remap_allocation(
        self,
    ) -> None:
        insertion = _intent(
            PmxReferenceTargetKind.VERTEX,
            PmxStructuralInsertPosition.append(),
        )
        evidence = analyze_structural_capacity(
            PmxReferenceTargetKind.VERTEX,
            current_count=MAX_INT32,
            insert_count=1,
            index_width=4,
        )
        self.assertTrue(evidence.width_representable)
        self.assertFalse(evidence.count_representable)
        self.assertFalse(evidence.expansion_required)

        with self.assertRaisesRegex(
            PmxStructuralReferenceShiftError,
            "signed 32-bit section-count",
        ):
            plan_collection_reference_shift(
                insertion,
                current_count=MAX_INT32,
                index_width=4,
            )

    def test_unsigned_vertex_one_byte_boundary_is_preserved(self) -> None:
        insertion = _intent(
            PmxReferenceTargetKind.VERTEX,
            PmxStructuralInsertPosition.append(),
        )

        accepted = plan_collection_reference_shift(
            insertion,
            current_count=255,
            index_width=1,
        )
        self.assertEqual(accepted.result_count, 256)
        self.assertTrue(accepted.capacity.representable)

        with self.assertRaises(PmxStructuralReferenceShiftError):
            plan_collection_reference_shift(
                insertion,
                current_count=256,
                index_width=1,
            )

    def test_successful_plan_is_immutable_hashable_and_self_consistent(self) -> None:
        plan = plan_collection_reference_shift(
            _intent(
                PmxReferenceTargetKind.MORPH,
                PmxStructuralInsertPosition.insert_before(0),
            ),
            current_count=1,
            index_width=1,
        )

        self.assertEqual(hash(plan), hash(plan))
        self.assertEqual(plan.target_kind, PmxReferenceTargetKind.MORPH)
        self.assertEqual(plan.insert_count, 1)
        self.assertEqual(plan.result_count, 2)
        with self.assertRaises(FrozenInstanceError):
            plan.current_count = 2  # type: ignore[misc]

        with self.assertRaises(ValueError):
            replace(
                plan,
                remap=PmxIndexRemap(
                    targets=(0,),
                    new_size=2,
                    new_indices_without_old_source=(1,),
                ),
            )

    def test_plan_constructor_rejects_semantically_wrong_old_target_mapping(self) -> None:
        insertion = _intent(
            PmxReferenceTargetKind.TEXTURE,
            PmxStructuralInsertPosition.insert_before(0),
        )
        capacity = analyze_structural_capacity(
            PmxReferenceTargetKind.TEXTURE,
            current_count=2,
            insert_count=1,
            index_width=1,
        )

        with self.assertRaisesRegex(
            ValueError,
            "source-domain insertion shift semantics",
        ):
            PmxCollectionReferenceShiftPlan(
                insertion=insertion,
                current_count=2,
                index_width=1,
                capacity=capacity,
                remap=PmxIndexRemap(
                    targets=(2, 1),
                    new_size=3,
                    new_indices_without_old_source=(0,),
                ),
                new_indices_in_request_order=(0,),
            )

    def test_plan_constructor_revalidates_source_domain_anchor_bounds(self) -> None:
        insertion = _intent(
            PmxReferenceTargetKind.TEXTURE,
            PmxStructuralInsertPosition.insert_before(2),
        )
        capacity = analyze_structural_capacity(
            PmxReferenceTargetKind.TEXTURE,
            current_count=2,
            insert_count=1,
            index_width=1,
        )

        with self.assertRaisesRegex(ValueError, "less than current_count"):
            PmxCollectionReferenceShiftPlan(
                insertion=insertion,
                current_count=2,
                index_width=1,
                capacity=capacity,
                remap=PmxIndexRemap(
                    targets=(0, 1),
                    new_size=3,
                    new_indices_without_old_source=(2,),
                ),
                new_indices_in_request_order=(2,),
            )

    def test_insertion_ordinal_lookup_rejects_invalid_indices_and_booleans(self) -> None:
        plan = plan_collection_reference_shift(
            _intent(
                PmxReferenceTargetKind.RIGID_BODY,
                PmxStructuralInsertPosition.append(),
            ),
            current_count=1,
            index_width=1,
        )

        self.assertEqual(plan.new_index_for_insertion(0), 1)
        with self.assertRaises(TypeError):
            plan.new_index_for_insertion(True)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            plan.new_index_for_insertion(-1)
        with self.assertRaises(ValueError):
            plan.new_index_for_insertion(1)

    def test_json_ready_evidence_contains_capacity_remap_and_request_mapping(self) -> None:
        plan = plan_collection_reference_shift(
            _intent(
                PmxReferenceTargetKind.TEXTURE,
                PmxStructuralInsertPosition.insert_before(1),
                PmxStructuralInsertPosition.append(),
            ),
            current_count=2,
            index_width=1,
        )

        report = plan.to_dict()
        self.assertEqual(report["target_kind"], "texture")
        self.assertEqual(report["current_count"], 2)
        self.assertEqual(report["insert_count"], 2)
        self.assertEqual(report["result_count"], 4)
        self.assertEqual(report["new_indices_in_request_order"], [1, 3])
        self.assertEqual(
            report["remap"],
            {
                "targets": [0, 2],
                "new_size": 4,
                "new_indices_without_old_source": [1, 3],
            },
        )
        self.assertTrue(report["capacity"]["representable"])

    def test_plan_surface_contains_no_payload_or_legacy_transform_authority(self) -> None:
        self.assertEqual(
            tuple(field.name for field in fields(PmxCollectionReferenceShiftPlan)),
            (
                "insertion",
                "current_count",
                "index_width",
                "capacity",
                "remap",
                "new_indices_in_request_order",
            ),
        )

        remap = PmxIndexRemap(
            targets=(1,),
            new_size=2,
            new_indices_without_old_source=(0,),
        )
        with self.assertRaisesRegex(ValueError, "do not authorize new indices"):
            PmxCollectionTransform(
                PmxReferenceTargetKind.TEXTURE,
                remap,
            )

    def test_planner_remains_internal_and_does_not_promote_insertion_capability(
        self,
    ) -> None:
        internal_names = (
            "PmxStructuralReferenceShiftError",
            "PmxCollectionReferenceShiftPlan",
            "plan_collection_reference_shift",
        )
        for name in internal_names:
            with self.subTest(name=name):
                self.assertNotIn(name, pmx.__all__)
                self.assertFalse(hasattr(pmx, name))
                self.assertNotIn(name, services.__all__)
                self.assertFalse(hasattr(services, name))

        self.assertIs(
            services.PmxStructuralEditRequest,
            services.PmxStructuralPreviewRequest,
        )


if __name__ == "__main__":
    unittest.main()
