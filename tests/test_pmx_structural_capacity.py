from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

import mmd_registry.pmx as pmx
import mmd_registry.services as services
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.pmx.structural_capacity import (
    PmxStructuralCapacityAnalysis,
    analyze_structural_capacity,
)
from mmd_registry.pmx.validation import MAX_INT32


class PmxStructuralCapacityTests(unittest.TestCase):
    def test_target_signedness_matches_validator_contract(self) -> None:
        for target_kind in PmxReferenceTargetKind:
            with self.subTest(target_kind=target_kind):
                analysis = analyze_structural_capacity(
                    target_kind,
                    current_count=0,
                    insert_count=0,
                    index_width=1,
                )
                self.assertIs(
                    analysis.signed,
                    target_kind is not PmxReferenceTargetKind.VERTEX,
                )

    def test_exact_one_byte_signed_boundary_is_representable(self) -> None:
        analysis = analyze_structural_capacity(
            PmxReferenceTargetKind.BONE,
            current_count=120,
            insert_count=8,
            index_width=1,
        )

        self.assertEqual(analysis.result_count, 128)
        self.assertEqual(analysis.maximum_addressable_index, 127)
        self.assertEqual(analysis.index_addressable_count, 128)
        self.assertEqual(analysis.effective_max_count, 128)
        self.assertTrue(analysis.width_representable)
        self.assertTrue(analysis.count_representable)
        self.assertTrue(analysis.representable)
        self.assertFalse(analysis.expansion_required)

    def test_one_byte_signed_overflow_requires_width_expansion(self) -> None:
        analysis = analyze_structural_capacity(
            PmxReferenceTargetKind.BONE,
            current_count=120,
            insert_count=9,
            index_width=1,
        )

        self.assertEqual(analysis.result_count, 129)
        self.assertFalse(analysis.width_representable)
        self.assertTrue(analysis.count_representable)
        self.assertFalse(analysis.representable)
        self.assertTrue(analysis.expansion_required)

    def test_vertex_uses_unsigned_index_capacity(self) -> None:
        analysis = analyze_structural_capacity(
            PmxReferenceTargetKind.VERTEX,
            current_count=255,
            insert_count=1,
            index_width=1,
        )

        self.assertEqual(analysis.maximum_addressable_index, 255)
        self.assertEqual(analysis.index_addressable_count, 256)
        self.assertTrue(analysis.representable)
        self.assertFalse(analysis.expansion_required)

    def test_signed_32_bit_section_count_is_an_independent_limit(self) -> None:
        vertex = analyze_structural_capacity(
            PmxReferenceTargetKind.VERTEX,
            current_count=MAX_INT32,
            insert_count=1,
            index_width=4,
        )
        bone = analyze_structural_capacity(
            PmxReferenceTargetKind.BONE,
            current_count=MAX_INT32,
            insert_count=1,
            index_width=4,
        )

        for analysis in (vertex, bone):
            with self.subTest(target_kind=analysis.target_kind):
                self.assertEqual(analysis.result_count, MAX_INT32 + 1)
                self.assertTrue(analysis.width_representable)
                self.assertFalse(analysis.count_representable)
                self.assertFalse(analysis.representable)
                self.assertFalse(analysis.expansion_required)
                self.assertEqual(analysis.effective_max_count, MAX_INT32)

    def test_inputs_reject_booleans_negatives_and_invalid_widths(self) -> None:
        with self.assertRaises(TypeError):
            analyze_structural_capacity(
                PmxReferenceTargetKind.TEXTURE,
                current_count=True,  # type: ignore[arg-type]
                insert_count=0,
                index_width=1,
            )
        with self.assertRaises(TypeError):
            analyze_structural_capacity(
                PmxReferenceTargetKind.TEXTURE,
                current_count=0,
                insert_count=False,  # type: ignore[arg-type]
                index_width=1,
            )
        with self.assertRaises(ValueError):
            analyze_structural_capacity(
                PmxReferenceTargetKind.TEXTURE,
                current_count=-1,
                insert_count=0,
                index_width=1,
            )
        with self.assertRaises(ValueError):
            analyze_structural_capacity(
                PmxReferenceTargetKind.TEXTURE,
                current_count=0,
                insert_count=-1,
                index_width=1,
            )
        for invalid_width in (0, 3, 8, True):
            with self.subTest(index_width=invalid_width):
                expected = TypeError if invalid_width is True else ValueError
                with self.assertRaises(expected):
                    analyze_structural_capacity(
                        PmxReferenceTargetKind.TEXTURE,
                        current_count=0,
                        insert_count=0,
                        index_width=invalid_width,  # type: ignore[arg-type]
                    )

    def test_target_kind_must_be_typed(self) -> None:
        with self.assertRaises(TypeError):
            analyze_structural_capacity(
                "bone",  # type: ignore[arg-type]
                current_count=0,
                insert_count=0,
                index_width=1,
            )

    def test_analysis_is_frozen_and_deterministic(self) -> None:
        first = analyze_structural_capacity(
            PmxReferenceTargetKind.MATERIAL,
            current_count=7,
            insert_count=3,
            index_width=2,
        )
        second = analyze_structural_capacity(
            PmxReferenceTargetKind.MATERIAL,
            current_count=7,
            insert_count=3,
            index_width=2,
        )

        self.assertEqual(first, second)
        self.assertEqual(first.to_dict(), second.to_dict())
        with self.assertRaises(FrozenInstanceError):
            first.current_count = 8  # type: ignore[misc]

    def test_json_ready_evidence_contains_reviewed_fields(self) -> None:
        analysis = PmxStructuralCapacityAnalysis(
            target_kind=PmxReferenceTargetKind.TEXTURE,
            current_count=10,
            insert_count=2,
            index_width=1,
        )

        self.assertEqual(
            tuple(analysis.to_dict()),
            (
                "target_kind",
                "current_count",
                "insert_count",
                "result_count",
                "index_width",
                "signed",
                "maximum_addressable_index",
                "index_addressable_count",
                "section_count_limit",
                "effective_max_count",
                "width_representable",
                "count_representable",
                "representable",
                "expansion_required",
            ),
        )

    def test_cp03_does_not_promote_public_service_or_root_pmx_surface(self) -> None:
        self.assertNotIn("analyze_structural_capacity", services.__all__)
        self.assertFalse(hasattr(services, "analyze_structural_capacity"))
        self.assertNotIn("PmxStructuralCapacityAnalysis", pmx.__all__)
        self.assertNotIn("analyze_structural_capacity", pmx.__all__)


if __name__ == "__main__":
    unittest.main()
