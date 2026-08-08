"""Tests for shared PMX bone-name normalization."""

from __future__ import annotations

import unittest

from mmd_registry.bone_names import (
    normalize_bone_name,
    split_bone_name_tokens,
)


class BoneNameNormalizationTests(unittest.TestCase):
    """Tests for deterministic Unicode and convention normalization."""

    def test_empty_and_whitespace_only_names_are_safe(self) -> None:
        self.assertEqual(normalize_bone_name(""), "")
        self.assertEqual(normalize_bone_name(" \t\n "), "")
        self.assertEqual(split_bone_name_tokens(""), ())
        self.assertEqual(split_bone_name_tokens(" \t\n "), ())

    def test_normalizes_unicode_width_whitespace_and_case(self) -> None:
        self.assertEqual(
            normalize_bone_name(
                "  Ｂｉｐ００１　Ｌ   ＣａｌｆＤ  ",
            ),
            "bip001 l calfd",
        )

    def test_casefold_is_used_instead_of_ascii_lowering(self) -> None:
        self.assertEqual(
            normalize_bone_name("Straße"),
            "strasse",
        )

    def test_normalization_preserves_japanese_text(self) -> None:
        self.assertEqual(
            normalize_bone_name(" 左ひざＤ "),
            "左ひざd",
        )

    def test_splits_camel_case_acronyms_and_digits(self) -> None:
        self.assertEqual(
            split_bone_name_tokens("Bip001 L CalfD"),
            (
                "bip",
                "001",
                "l",
                "calf",
                "d",
            ),
        )
        self.assertEqual(
            split_bone_name_tokens("LeftLegIKParent"),
            (
                "left",
                "leg",
                "ik",
                "parent",
            ),
        )

    def test_splits_cjk_and_latin_convention_suffixes(self) -> None:
        self.assertEqual(
            split_bone_name_tokens("左ひざＤ"),
            (
                "左ひざ",
                "d",
            ),
        )
        self.assertEqual(
            split_bone_name_tokens("右つま先ＩＫ"),
            (
                "右つま先",
                "ik",
            ),
        )

    def test_splits_common_separators(self) -> None:
        self.assertEqual(
            split_bone_name_tokens("Left_Leg-IK.01"),
            (
                "left",
                "leg",
                "ik",
                "01",
            ),
        )

    def test_source_string_is_not_modified(self) -> None:
        source = " 左ひざＤ "

        normalize_bone_name(source)
        split_bone_name_tokens(source)

        self.assertEqual(source, " 左ひざＤ ")


if __name__ == "__main__":
    unittest.main()
