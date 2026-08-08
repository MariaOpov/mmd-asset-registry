"""Tests for PMX bone search and basic filtering."""

from __future__ import annotations

import unittest

from mmd_registry.bone_explorer import BoneView
from mmd_registry.bone_search import filter_bone_views


def make_view(
    index: int,
    *,
    display_name: str = "Bone",
    local_name: str = "",
    universal_name: str = "",
    tags: tuple[str, ...] = (),
) -> BoneView:
    """Build one small presented bone for search tests."""

    return BoneView(
        index=index,
        display_name=display_name,
        local_name=local_name,
        universal_name=universal_name,
        parent_index=-1,
        parent_display_name=None,
        position=(0.0, 0.0, 0.0),
        tags=tags,
    )


class BoneSearchTests(unittest.TestCase):
    """Tests for composable bone search and filtering."""

    def test_empty_input_is_safe(self) -> None:
        self.assertEqual(filter_bone_views(()), ())

    def test_missing_or_blank_search_returns_all_views(self) -> None:
        views = (
            make_view(0, display_name="Root"),
            make_view(1, display_name="Child"),
        )

        self.assertEqual(filter_bone_views(views), views)
        self.assertEqual(
            filter_bone_views(views, search_query=" \t "),
            views,
        )

    def test_matches_display_name_case_insensitively(self) -> None:
        views = (
            make_view(0, display_name="Bip001 L CalfD"),
            make_view(1, display_name="Bip001 R FootD"),
        )

        matches = filter_bone_views(
            views,
            search_query="calfd",
        )

        self.assertEqual(
            tuple(view.index for view in matches),
            (0,),
        )

    def test_matches_local_and_universal_names(self) -> None:
        views = (
            make_view(
                10,
                display_name="Friendly Knee",
                local_name="左ひざD",
                universal_name="Bip001 L CalfD",
            ),
            make_view(
                11,
                display_name="Friendly Foot",
                local_name="左足首D",
                universal_name="Bip001 L FootD",
            ),
        )

        self.assertEqual(
            tuple(
                view.index
                for view in filter_bone_views(
                    views,
                    search_query="ひざ",
                )
            ),
            (10,),
        )
        self.assertEqual(
            tuple(
                view.index
                for view in filter_bone_views(
                    views,
                    search_query="footd",
                )
            ),
            (11,),
        )

    def test_normalizes_unicode_width_and_whitespace(self) -> None:
        views = (
            make_view(
                6,
                display_name="Right Toe IK",
                local_name="右つま先ＩＫ",
            ),
        )

        self.assertEqual(
            filter_bone_views(
                views,
                search_query="toe   ik",
            ),
            views,
        )
        self.assertEqual(
            filter_bone_views(
                views,
                search_query="ｉｋ",
            ),
            views,
        )

    def test_matches_supported_exact_index_forms(self) -> None:
        views = (
            make_view(338, display_name="Thigh"),
            make_view(339, display_name="Calf"),
            make_view(340, display_name="Foot"),
        )

        for query in ("339", "#339", "[339]", "［３３９］"):
            with self.subTest(query=query):
                matches = filter_bone_views(
                    views,
                    search_query=query,
                )

                self.assertEqual(
                    tuple(view.index for view in matches),
                    (339,),
                )

    def test_numeric_query_does_not_search_name_substrings(self) -> None:
        views = (
            make_view(3, display_name="Bone Three"),
            make_view(30, display_name="Helper 3"),
        )

        matches = filter_bone_views(
            views,
            search_query="3",
        )

        self.assertEqual(
            tuple(view.index for view in matches),
            (3,),
        )

    def test_no_match_returns_empty_tuple(self) -> None:
        views = (make_view(0, display_name="Root"),)

        self.assertEqual(
            filter_bone_views(
                views,
                search_query="missing",
            ),
            (),
        )

    def test_ik_only_filter_uses_readable_tags(self) -> None:
        views = (
            make_view(
                0,
                display_name="Center",
                tags=("Rotate", "Move"),
            ),
            make_view(
                1,
                display_name="Left Leg IK",
                tags=("Rotate", "IK"),
            ),
            make_view(
                2,
                display_name="Right Leg IK",
                tags=("Rotate", "IK"),
            ),
        )

        matches = filter_bone_views(
            views,
            ik_only=True,
        )

        self.assertEqual(
            tuple(view.index for view in matches),
            (1, 2),
        )

    def test_search_and_ik_filter_compose(self) -> None:
        views = (
            make_view(
                1,
                display_name="Left Leg IK",
                tags=("IK",),
            ),
            make_view(
                2,
                display_name="Right Leg IK",
                tags=("IK",),
            ),
            make_view(
                3,
                display_name="Left Leg",
                tags=("Rotate",),
            ),
        )

        matches = filter_bone_views(
            views,
            search_query="left",
            ik_only=True,
        )

        self.assertEqual(
            tuple(view.index for view in matches),
            (1,),
        )

    def test_filter_preserves_source_order(self) -> None:
        views = (
            make_view(9, display_name="Helper C"),
            make_view(2, display_name="Helper A"),
            make_view(7, display_name="Helper B"),
        )

        matches = filter_bone_views(
            views,
            search_query="helper",
        )

        self.assertEqual(
            tuple(view.index for view in matches),
            (9, 2, 7),
        )


if __name__ == "__main__":
    unittest.main()
