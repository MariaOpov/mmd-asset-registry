from __future__ import annotations

import unittest

import mmd_registry.smart_part_detection as detection
from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringMaterialCatalogEntry,
)
from mmd_registry.smart_parts import SmartPartKind


class SmartPartDetectionCoreTests(unittest.TestCase):
    def test_generic_alias_table_follows_smart_part_declaration_order(self) -> None:
        self.assertEqual(
            tuple(kind for kind, _aliases in detection._GENERIC_EXACT_ALIASES),
            tuple(SmartPartKind),
        )

    def test_every_kind_has_at_least_one_generic_exact_alias(self) -> None:
        for kind, aliases in detection._GENERIC_EXACT_ALIASES:
            with self.subTest(kind=kind):
                self.assertIs(type(aliases), tuple)
                self.assertGreaterEqual(len(aliases), 1)
                self.assertTrue(all(type(alias) is str for alias in aliases))

    def test_generic_canonical_aliases_match_exactly(self) -> None:
        expected = {
            "eyes": SmartPartKind.EYES,
            "hair": SmartPartKind.HAIR,
            "face": SmartPartKind.FACE,
            "skin": SmartPartKind.SKIN,
            "chest": SmartPartKind.CHEST,
            "upper body": SmartPartKind.UPPER_BODY,
            "lower body": SmartPartKind.LOWER_BODY,
            "arms": SmartPartKind.ARMS,
            "hands": SmartPartKind.HANDS,
            "legs": SmartPartKind.LEGS,
            "feet": SmartPartKind.FEET,
            "clothing": SmartPartKind.CLOTHING,
            "shoes": SmartPartKind.SHOES,
            "accessories": SmartPartKind.ACCESSORIES,
            "materials": SmartPartKind.MATERIALS,
        }
        for alias, kind in expected.items():
            with self.subTest(alias=alias):
                self.assertIs(detection._exact_alias_kind(alias), kind)

    def test_upper_and_lower_body_underscore_aliases_are_exact(self) -> None:
        self.assertIs(
            detection._exact_alias_kind("upper_body"),
            SmartPartKind.UPPER_BODY,
        )
        self.assertIs(
            detection._exact_alias_kind("lower_body"),
            SmartPartKind.LOWER_BODY,
        )

    def test_exact_match_uses_frozen_normalization(self) -> None:
        cases = (
            ("  ＦＡＣＥ　", SmartPartKind.FACE),
            ("UPPER\t BODY", SmartPartKind.UPPER_BODY),
            ("  Accessories  ", SmartPartKind.ACCESSORIES),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertIs(detection._exact_alias_kind(value), expected)

    def test_empty_and_unknown_text_do_not_match(self) -> None:
        for value in ("", " \t\r\n ", "unknown", "custom material"):
            with self.subTest(value=value):
                self.assertIsNone(detection._exact_alias_kind(value))

    def test_substrings_and_near_misses_do_not_match(self) -> None:
        for value in (
            "facial",
            "face helper",
            "brightarms",
            "upper body 2",
            "shoes.001",
            "my accessories",
        ):
            with self.subTest(value=value):
                self.assertIsNone(detection._exact_alias_kind(value))

    def test_normalized_alias_index_is_tuple_sorted_and_unique(self) -> None:
        index = detection._NORMALIZED_ALIAS_INDEX
        self.assertIs(type(index), tuple)
        aliases = tuple(alias for alias, _kind in index)
        self.assertEqual(aliases, tuple(sorted(aliases)))
        self.assertEqual(len(aliases), len(set(aliases)))

    def test_alias_index_rejects_cross_kind_collision(self) -> None:
        table = (
            (SmartPartKind.FACE, ("same",)),
            (SmartPartKind.HAIR, (" SAME ",)),
        )
        with self.assertRaises(ValueError):
            detection._build_normalized_alias_index(table)

    def test_alias_index_deduplicates_same_kind_normalized_duplicate(self) -> None:
        table = (
            (SmartPartKind.FACE, ("Face", " Ｆａｃｅ ")),
        )
        self.assertEqual(
            detection._build_normalized_alias_index(table),
            (("face", SmartPartKind.FACE),),
        )

    def test_alias_index_rejects_empty_normalized_alias(self) -> None:
        table = ((SmartPartKind.FACE, ("   ",)),)
        with self.assertRaises(ValueError):
            detection._build_normalized_alias_index(table)

    def test_alias_index_rejects_non_tuple_table(self) -> None:
        with self.assertRaises(TypeError):
            detection._build_normalized_alias_index([])  # type: ignore[arg-type]

    def test_generic_exact_alias_core_remains_separate_from_family_tables(self) -> None:
        self.assertIs(
            detection._exact_alias_kind("face"),
            SmartPartKind.FACE,
        )
        self.assertIsNone(detection._exact_alias_kind("右腕"))


if __name__ == "__main__":
    unittest.main()
