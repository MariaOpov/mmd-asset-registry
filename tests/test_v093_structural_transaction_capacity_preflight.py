"""Freeze CP15 whole-transaction capacity preflight."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, is_dataclass
import importlib
import inspect
import unittest
from unittest.mock import patch

import mmd_registry
import mmd_registry.pmx as pmx
import mmd_registry.services as services
from mmd_registry.pmx.collection_transform import PmxCollectionTransform
from mmd_registry.pmx.index_remap import PmxIndexRemap
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.pmx.structural_capacity import analyze_structural_capacity
from mmd_registry.pmx.structural_insert_intent import PmxStructuralInsertPosition
from mmd_registry.pmx.structural_transaction_insertion import (
    PmxStructuralTransactionInsertionOperation,
)
from mmd_registry.pmx.validation import MAX_INT32


PREFLIGHT_MODULE_NAME = "mmd_registry.pmx.structural_transaction_preflight"
COMPOSITION_MODULE_NAME = (
    "mmd_registry.pmx.structural_transaction_composition"
)


def _preflight_module():
    return importlib.import_module(PREFLIGHT_MODULE_NAME)


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


def _operation(
    request_ordinal: int,
    target_kind: PmxReferenceTargetKind,
) -> PmxStructuralTransactionInsertionOperation:
    return PmxStructuralTransactionInsertionOperation(
        request_ordinal=request_ordinal,
        target_kind=target_kind,
        position=PmxStructuralInsertPosition.append(),
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


def _preflight(
    *,
    source_counts=None,
    index_widths=None,
    transforms=(),
    operations=(),
):
    return _preflight_module().preflight_structural_transaction_capacity(
        source_counts=(
            _source_counts() if source_counts is None else source_counts
        ),
        index_widths=(
            _index_widths() if index_widths is None else index_widths
        ),
        transforms=transforms,
        operations=operations,
    )


class V093StructuralTransactionCapacityPreflightTests(unittest.TestCase):
    def test_internal_preflight_is_frozen_slotted_and_not_exported(self) -> None:
        preflight_module = _preflight_module()
        expected_exports = (
            "PmxStructuralTransactionCapacityPreflight",
            "PmxStructuralTransactionCapacityPreflightError",
            "preflight_structural_transaction_capacity",
        )
        self.assertEqual(preflight_module.__all__, expected_exports)
        for name in expected_exports:
            self.assertFalse(hasattr(mmd_registry, name), name)
            self.assertFalse(hasattr(pmx, name), name)
            self.assertFalse(hasattr(services, name), name)

        evidence = _preflight()
        self.assertTrue(is_dataclass(evidence))
        self.assertFalse(hasattr(evidence, "__dict__"))
        self.assertEqual(
            tuple(field.name for field in fields(evidence)),
            (
                "source_counts",
                "index_widths",
                "transforms",
                "operations",
                "analyses",
            ),
        )
        self.assertEqual(len(evidence.analyses), 6)
        with self.assertRaises(FrozenInstanceError):
            evidence.analyses = ()

        source = inspect.getsource(preflight_module)
        self.assertNotIn("mmd_registry.services", source)
        for forbidden in (
            "preview_structural_transaction",
            "apply_structural_transaction",
            "PmxDocument",
            "serialize",
            "open(",
        ):
            self.assertNotIn(forbidden, source)

    def test_noop_preflight_covers_all_six_declared_widths(self) -> None:
        source_counts = _source_counts(
            vertex=200,
            texture=100,
            material=1000,
            bone=100,
            morph=1000,
            rigid_body=10,
        )
        index_widths = _index_widths(
            vertex=1,
            texture=1,
            material=2,
            bone=1,
            morph=2,
            rigid_body=1,
        )
        evidence = _preflight(
            source_counts=source_counts,
            index_widths=index_widths,
        )

        self.assertIs(evidence.source_counts, source_counts)
        self.assertIs(evidence.index_widths, index_widths)
        self.assertTrue(evidence.all_representable)
        self.assertEqual(evidence.final_counts, source_counts)
        self.assertEqual(
            tuple(analysis.target_kind for analysis in evidence.analyses),
            tuple(PmxReferenceTargetKind),
        )
        for position, analysis in enumerate(evidence.analyses):
            self.assertEqual(analysis.current_count, source_counts[position][1])
            self.assertEqual(analysis.insert_count, 0)
            self.assertEqual(analysis.index_width, index_widths[position][1])
            self.assertFalse(analysis.expansion_required)

    def test_mixed_composition_owns_matching_all_target_final_counts(self) -> None:
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
                PmxReferenceTargetKind.MORPH,
                (2, 0),
                source_count=4,
            ),
        )
        operations = tuple(
            _operation(ordinal, target_kind)
            for ordinal, target_kind in enumerate(PmxReferenceTargetKind)
        )
        standalone = _preflight(
            source_counts=source_counts,
            transforms=transforms,
            operations=operations,
        )
        composition = _composition_module().compose_structural_transaction(
            source_counts=source_counts,
            index_widths=_index_widths(),
            transforms=transforms,
            operations=operations,
        )

        expected = (
            (PmxReferenceTargetKind.VERTEX, 4),
            (PmxReferenceTargetKind.TEXTURE, 4),
            (PmxReferenceTargetKind.MATERIAL, 4),
            (PmxReferenceTargetKind.BONE, 5),
            (PmxReferenceTargetKind.MORPH, 3),
            (PmxReferenceTargetKind.RIGID_BODY, 4),
        )
        self.assertEqual(standalone.final_counts, expected)
        self.assertEqual(composition.preflight, standalone)
        for target_kind, final_count in expected:
            placement = composition.placement_for(target_kind)
            assert placement is not None
            self.assertEqual(placement.result_count, final_count)
            self.assertEqual(
                standalone.analysis_for(target_kind),
                placement.capacity,
            )

    def test_exact_one_byte_boundaries_pass_without_width_expansion(self) -> None:
        source_counts = tuple(
            (
                target_kind,
                256 if target_kind is PmxReferenceTargetKind.VERTEX else 128,
            )
            for target_kind in PmxReferenceTargetKind
        )
        index_widths = tuple(
            (target_kind, 1) for target_kind in PmxReferenceTargetKind
        )
        evidence = _preflight(
            source_counts=source_counts,
            index_widths=index_widths,
        )

        self.assertTrue(evidence.all_representable)
        for analysis in evidence.analyses:
            self.assertTrue(analysis.width_representable)
            self.assertTrue(analysis.count_representable)
            self.assertFalse(analysis.expansion_required)
            self.assertEqual(analysis.index_width, 1)
            self.assertEqual(
                analysis.result_count,
                analysis.index_addressable_count,
            )

    def test_all_boundary_plus_one_blockers_are_canonical_and_no_retry_occurs(
        self,
    ) -> None:
        preflight_module = _preflight_module()
        source_counts = tuple(
            (
                target_kind,
                256 if target_kind is PmxReferenceTargetKind.VERTEX else 128,
            )
            for target_kind in PmxReferenceTargetKind
        )
        index_widths = tuple(
            (target_kind, 1) for target_kind in PmxReferenceTargetKind
        )
        operations = tuple(
            _operation(ordinal, target_kind)
            for ordinal, target_kind in enumerate(PmxReferenceTargetKind)
        )
        calls: list[tuple[PmxReferenceTargetKind, int]] = []

        def recording_analysis(target_kind, **kwargs):
            calls.append((target_kind, kwargs["index_width"]))
            return analyze_structural_capacity(target_kind, **kwargs)

        error = preflight_module.PmxStructuralTransactionCapacityPreflightError
        with patch.object(
            preflight_module,
            "analyze_structural_capacity",
            side_effect=recording_analysis,
        ):
            with self.assertRaises(error) as raised:
                _preflight(
                    source_counts=source_counts,
                    index_widths=index_widths,
                    operations=operations,
                )

        self.assertEqual(
            tuple(calls),
            tuple((target_kind, 1) for target_kind in PmxReferenceTargetKind),
        )
        message = str(raised.exception)
        self.assertIn("without automatic width expansion", message)
        positions = tuple(
            message.index(f"{target_kind.value}(")
            for target_kind in PmxReferenceTargetKind
        )
        self.assertEqual(positions, tuple(sorted(positions)))
        self.assertEqual(
            message.count("reason=declared_index_width"),
            6,
        )
        self.assertEqual(
            index_widths,
            tuple((kind, 1) for kind in PmxReferenceTargetKind),
        )

    def test_survivor_count_and_section_count_limits_are_independent(self) -> None:
        material_transform = _transform(
            PmxReferenceTargetKind.MATERIAL,
            (125, *range(125)),
            source_count=130,
        )
        accepted = _preflight(
            source_counts=_source_counts(material=130),
            index_widths=_index_widths(material=1),
            transforms=(material_transform,),
            operations=(
                _operation(0, PmxReferenceTargetKind.MATERIAL),
                _operation(1, PmxReferenceTargetKind.MATERIAL),
            ),
        )
        material = accepted.analysis_for(PmxReferenceTargetKind.MATERIAL)
        self.assertEqual(material.current_count, 126)
        self.assertEqual(material.insert_count, 2)
        self.assertEqual(material.result_count, 128)

        error = _preflight_module().PmxStructuralTransactionCapacityPreflightError
        with self.assertRaisesRegex(error, r"reason=section_count"):
            _preflight(
                source_counts=_source_counts(vertex=MAX_INT32),
                index_widths=_index_widths(vertex=4),
                operations=(
                    _operation(0, PmxReferenceTargetKind.VERTEX),
                ),
            )
        self.assertEqual(material_transform.old_size, 130)
        self.assertEqual(material_transform.new_size, 126)


if __name__ == "__main__":
    unittest.main()
