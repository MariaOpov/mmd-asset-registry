from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
import unittest

import mmd_registry.pmx as pmx
import mmd_registry.services as services
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.pmx.structural_insert_intent import (
    PmxCollectionInsertionIntent,
    PmxStructuralInsertionIntent,
    PmxStructuralInsertPosition,
    PmxStructuralInsertPositionMode,
)


class PmxStructuralInsertIntentTests(unittest.TestCase):
    def test_append_position_is_explicit_immutable_and_json_ready(self) -> None:
        position = PmxStructuralInsertPosition.append()

        self.assertIs(position.mode, PmxStructuralInsertPositionMode.APPEND)
        self.assertIsNone(position.source_index)
        self.assertEqual(
            position.to_dict(),
            {"mode": "append", "source_index": None},
        )
        self.assertEqual(hash(position), hash(position))
        with self.assertRaises(FrozenInstanceError):
            position.source_index = 1  # type: ignore[misc]

    def test_insert_before_requires_plain_nonnegative_source_index(self) -> None:
        position = PmxStructuralInsertPosition.insert_before(3)

        self.assertIs(
            position.mode,
            PmxStructuralInsertPositionMode.INSERT_BEFORE,
        )
        self.assertEqual(position.source_index, 3)

        for invalid in (True, -1, 1.5, "1"):
            with self.subTest(invalid=invalid):
                expected = ValueError if invalid == -1 else TypeError
                with self.assertRaises(expected):
                    PmxStructuralInsertPosition.insert_before(  # type: ignore[arg-type]
                        invalid
                    )

    def test_position_constructor_rejects_competing_or_incomplete_modes(self) -> None:
        with self.assertRaises(ValueError):
            PmxStructuralInsertPosition(
                PmxStructuralInsertPositionMode.APPEND,
                source_index=0,
            )
        with self.assertRaises(ValueError):
            PmxStructuralInsertPosition(
                PmxStructuralInsertPositionMode.INSERT_BEFORE,
                source_index=None,
            )
        with self.assertRaises(TypeError):
            PmxStructuralInsertPosition(  # type: ignore[arg-type]
                "append",
                source_index=None,
            )

    def test_source_domain_bounds_are_fail_closed(self) -> None:
        PmxStructuralInsertPosition.append().validate_for_source_size(0)
        PmxStructuralInsertPosition.append().validate_for_source_size(5)
        PmxStructuralInsertPosition.insert_before(0).validate_for_source_size(1)
        PmxStructuralInsertPosition.insert_before(4).validate_for_source_size(5)

        with self.assertRaises(ValueError):
            PmxStructuralInsertPosition.insert_before(0).validate_for_source_size(0)
        with self.assertRaises(ValueError):
            PmxStructuralInsertPosition.insert_before(5).validate_for_source_size(5)
        with self.assertRaises(TypeError):
            PmxStructuralInsertPosition.append().validate_for_source_size(True)
        with self.assertRaises(ValueError):
            PmxStructuralInsertPosition.append().validate_for_source_size(-1)

    def test_collection_intent_preserves_same_anchor_and_append_request_order(self) -> None:
        first = PmxStructuralInsertPosition.insert_before(2)
        second = PmxStructuralInsertPosition.insert_before(2)
        append_a = PmxStructuralInsertPosition.append()
        append_b = PmxStructuralInsertPosition.append()
        intent = PmxCollectionInsertionIntent(
            PmxReferenceTargetKind.TEXTURE,
            (first, second, append_a, append_b),
        )

        self.assertEqual(intent.positions, (first, second, append_a, append_b))
        self.assertEqual(intent.insert_count, 4)
        intent.validate_for_source_size(3)

    def test_collection_intent_is_typed_nonempty_and_validates_source_domain(self) -> None:
        with self.assertRaises(TypeError):
            PmxCollectionInsertionIntent(  # type: ignore[arg-type]
                "texture",
                (PmxStructuralInsertPosition.append(),),
            )
        with self.assertRaises(TypeError):
            PmxCollectionInsertionIntent(  # type: ignore[arg-type]
                PmxReferenceTargetKind.TEXTURE,
                [PmxStructuralInsertPosition.append()],
            )
        with self.assertRaises(ValueError):
            PmxCollectionInsertionIntent(PmxReferenceTargetKind.TEXTURE, ())
        with self.assertRaises(TypeError):
            PmxCollectionInsertionIntent(  # type: ignore[arg-type]
                PmxReferenceTargetKind.TEXTURE,
                (object(),),
            )

        intent = PmxCollectionInsertionIntent(
            PmxReferenceTargetKind.TEXTURE,
            (PmxStructuralInsertPosition.insert_before(2),),
        )
        with self.assertRaises(ValueError):
            intent.validate_for_source_size(2)

    def test_coordinated_intent_requires_unique_canonical_target_order(self) -> None:
        texture = PmxCollectionInsertionIntent(
            PmxReferenceTargetKind.TEXTURE,
            (PmxStructuralInsertPosition.append(),),
        )
        bone = PmxCollectionInsertionIntent(
            PmxReferenceTargetKind.BONE,
            (PmxStructuralInsertPosition.append(),),
        )

        coordinated = PmxStructuralInsertionIntent((texture, bone))
        self.assertEqual(coordinated.total_insert_count, 2)
        self.assertIs(
            coordinated.insertion_for(PmxReferenceTargetKind.TEXTURE),
            texture,
        )
        self.assertIsNone(
            coordinated.insertion_for(PmxReferenceTargetKind.MATERIAL)
        )

        with self.assertRaises(ValueError):
            PmxStructuralInsertionIntent((bone, texture))
        with self.assertRaises(ValueError):
            PmxStructuralInsertionIntent((texture, texture))
        with self.assertRaises(TypeError):
            PmxStructuralInsertionIntent([texture])  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            coordinated.insertion_for("texture")  # type: ignore[arg-type]

    def test_coordinated_empty_intent_is_deterministic_noop_evidence(self) -> None:
        first = PmxStructuralInsertionIntent()
        second = PmxStructuralInsertionIntent()

        self.assertEqual(first, second)
        self.assertEqual(first.total_insert_count, 0)
        self.assertEqual(
            first.to_dict(),
            {"collection_insertions": [], "total_insert_count": 0},
        )

    def test_foundation_contains_no_payload_or_raw_mutation_authority(self) -> None:
        self.assertEqual(
            tuple(field.name for field in fields(PmxStructuralInsertPosition)),
            ("mode", "source_index"),
        )
        self.assertEqual(
            tuple(field.name for field in fields(PmxCollectionInsertionIntent)),
            ("target_kind", "positions"),
        )
        self.assertEqual(
            tuple(field.name for field in fields(PmxStructuralInsertionIntent)),
            ("collection_insertions",),
        )

    def test_foundation_remains_internal_and_v091_request_alias_is_unchanged(self) -> None:
        internal_names = (
            "PmxStructuralInsertPositionMode",
            "PmxStructuralInsertPosition",
            "PmxCollectionInsertionIntent",
            "PmxStructuralInsertionIntent",
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
        request = services.PmxStructuralPreviewRequest(collection_edits=())
        self.assertEqual(request.collection_edits, ())


if __name__ == "__main__":
    unittest.main()
