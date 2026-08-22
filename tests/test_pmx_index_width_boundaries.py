from __future__ import annotations

import unittest

import mmd_registry.pmx as pmx
import mmd_registry.services as services
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.pmx.structural_capacity import analyze_structural_capacity
from mmd_registry.pmx.validation import MAX_INT32


SIGNED_TARGETS = (
    PmxReferenceTargetKind.TEXTURE,
    PmxReferenceTargetKind.MATERIAL,
    PmxReferenceTargetKind.BONE,
    PmxReferenceTargetKind.MORPH,
    PmxReferenceTargetKind.RIGID_BODY,
)


class PmxIndexWidthBoundaryTests(unittest.TestCase):
    def test_exact_unsigned_vertex_boundaries_for_all_widths(self) -> None:
        expected = {
            1: (255, 256, 256),
            2: (65535, 65536, 65536),
            4: (4294967295, 4294967296, MAX_INT32),
        }

        for width, (
            maximum_index,
            addressable_count,
            effective_max_count,
        ) in expected.items():
            with self.subTest(width=width):
                analysis = analyze_structural_capacity(
                    PmxReferenceTargetKind.VERTEX,
                    current_count=0,
                    insert_count=0,
                    index_width=width,
                )
                self.assertFalse(analysis.signed)
                self.assertEqual(
                    analysis.maximum_addressable_index,
                    maximum_index,
                )
                self.assertEqual(
                    analysis.index_addressable_count,
                    addressable_count,
                )
                self.assertEqual(
                    analysis.effective_max_count,
                    effective_max_count,
                )

    def test_exact_signed_boundaries_for_all_targets_and_widths(self) -> None:
        expected = {
            1: (127, 128, 128),
            2: (32767, 32768, 32768),
            4: (2147483647, 2147483648, MAX_INT32),
        }

        for target_kind in SIGNED_TARGETS:
            for width, (
                maximum_index,
                addressable_count,
                effective_max_count,
            ) in expected.items():
                with self.subTest(target_kind=target_kind, width=width):
                    analysis = analyze_structural_capacity(
                        target_kind,
                        current_count=0,
                        insert_count=0,
                        index_width=width,
                    )
                    self.assertTrue(analysis.signed)
                    self.assertEqual(
                        analysis.maximum_addressable_index,
                        maximum_index,
                    )
                    self.assertEqual(
                        analysis.index_addressable_count,
                        addressable_count,
                    )
                    self.assertEqual(
                        analysis.effective_max_count,
                        effective_max_count,
                    )

    def test_effective_maximum_is_representable_for_every_target_and_width(
        self,
    ) -> None:
        for target_kind in PmxReferenceTargetKind:
            for width in (1, 2, 4):
                baseline = analyze_structural_capacity(
                    target_kind,
                    current_count=0,
                    insert_count=0,
                    index_width=width,
                )
                analysis = analyze_structural_capacity(
                    target_kind,
                    current_count=baseline.effective_max_count,
                    insert_count=0,
                    index_width=width,
                )

                with self.subTest(target_kind=target_kind, width=width):
                    self.assertTrue(analysis.width_representable)
                    self.assertTrue(analysis.count_representable)
                    self.assertTrue(analysis.representable)
                    self.assertFalse(analysis.expansion_required)

    def test_effective_maximum_plus_one_fails_for_every_target_and_width(
        self,
    ) -> None:
        for target_kind in PmxReferenceTargetKind:
            for width in (1, 2, 4):
                baseline = analyze_structural_capacity(
                    target_kind,
                    current_count=0,
                    insert_count=0,
                    index_width=width,
                )
                analysis = analyze_structural_capacity(
                    target_kind,
                    current_count=baseline.effective_max_count,
                    insert_count=1,
                    index_width=width,
                )

                with self.subTest(target_kind=target_kind, width=width):
                    self.assertFalse(analysis.representable)

                    if width in (1, 2):
                        self.assertFalse(analysis.width_representable)
                        self.assertTrue(analysis.count_representable)
                        self.assertTrue(analysis.expansion_required)
                    else:
                        self.assertTrue(analysis.width_representable)
                        self.assertFalse(analysis.count_representable)
                        self.assertFalse(analysis.expansion_required)

    def test_four_byte_vertex_is_count_limited_before_index_space_exhaustion(
        self,
    ) -> None:
        analysis = analyze_structural_capacity(
            PmxReferenceTargetKind.VERTEX,
            current_count=MAX_INT32,
            insert_count=1,
            index_width=4,
        )

        self.assertEqual(analysis.result_count, MAX_INT32 + 1)
        self.assertEqual(analysis.index_addressable_count, 2**32)
        self.assertTrue(analysis.width_representable)
        self.assertFalse(analysis.count_representable)
        self.assertFalse(analysis.representable)
        self.assertFalse(analysis.expansion_required)

    def test_four_byte_signed_targets_are_also_count_limited_first(self) -> None:
        for target_kind in SIGNED_TARGETS:
            with self.subTest(target_kind=target_kind):
                analysis = analyze_structural_capacity(
                    target_kind,
                    current_count=MAX_INT32,
                    insert_count=1,
                    index_width=4,
                )
                self.assertEqual(
                    analysis.index_addressable_count,
                    2**31,
                )
                self.assertTrue(analysis.width_representable)
                self.assertFalse(analysis.count_representable)
                self.assertFalse(analysis.representable)
                self.assertFalse(analysis.expansion_required)

    def test_zero_and_noop_are_representable_for_every_target_and_width(
        self,
    ) -> None:
        for target_kind in PmxReferenceTargetKind:
            for width in (1, 2, 4):
                with self.subTest(target_kind=target_kind, width=width):
                    analysis = analyze_structural_capacity(
                        target_kind,
                        current_count=0,
                        insert_count=0,
                        index_width=width,
                    )
                    self.assertEqual(analysis.result_count, 0)
                    self.assertTrue(analysis.representable)
                    self.assertFalse(analysis.expansion_required)

    def test_boundary_analysis_does_not_promote_public_api(self) -> None:
        self.assertFalse(hasattr(pmx, "analyze_structural_capacity"))
        self.assertFalse(hasattr(services, "analyze_structural_capacity"))
        self.assertNotIn(
            "analyze_structural_capacity",
            services.__all__,
        )


if __name__ == "__main__":
    unittest.main()
