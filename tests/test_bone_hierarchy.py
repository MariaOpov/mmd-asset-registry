"""Tests for safe PMX bone hierarchy construction."""

from __future__ import annotations

import unittest

from mmd_registry.bone_explorer import BoneView
from mmd_registry.bone_hierarchy import (
    build_bone_hierarchy,
    render_bone_tree,
)


def make_view(
    index: int,
    *,
    name: str | None = None,
    parent_index: int = -1,
) -> BoneView:
    """Build one small bone presentation record."""

    display_name = name or f"Bone {index}"

    return BoneView(
        index=index,
        display_name=display_name,
        local_name=display_name,
        universal_name="",
        parent_index=parent_index,
        parent_display_name=None,
        position=(0.0, 0.0, 0.0),
        tags=(),
    )


class BoneHierarchyTests(unittest.TestCase):
    """Tests for hierarchy construction and rendering."""

    def test_empty_hierarchy_is_safe(self) -> None:
        hierarchy = build_bone_hierarchy(())

        self.assertEqual(
            hierarchy.root_indices,
            (),
        )
        self.assertEqual(
            hierarchy.nodes,
            (),
        )
        self.assertEqual(
            hierarchy.issues,
            (),
        )

    def test_resolves_parent_that_appears_later(self) -> None:
        hierarchy = build_bone_hierarchy(
            (
                make_view(
                    2,
                    name="Child",
                    parent_index=1,
                ),
                make_view(
                    1,
                    name="Root",
                ),
            )
        )
        nodes = {node.bone.index: node for node in hierarchy.nodes}

        self.assertEqual(
            hierarchy.root_indices,
            (1,),
        )
        self.assertEqual(
            nodes[1].child_indices,
            (2,),
        )
        self.assertEqual(
            nodes[2].child_indices,
            (),
        )

    def test_roots_and_children_are_sorted_by_index(self) -> None:
        hierarchy = build_bone_hierarchy(
            (
                make_view(5),
                make_view(
                    4,
                    parent_index=1,
                ),
                make_view(1),
                make_view(
                    3,
                    parent_index=1,
                ),
            )
        )
        nodes = {node.bone.index: node for node in hierarchy.nodes}

        self.assertEqual(
            hierarchy.root_indices,
            (1, 5),
        )
        self.assertEqual(
            nodes[1].child_indices,
            (3, 4),
        )

    def test_invalid_parent_becomes_root_with_issue(self) -> None:
        hierarchy = build_bone_hierarchy(
            (
                make_view(
                    7,
                    parent_index=99,
                ),
            )
        )

        self.assertEqual(
            hierarchy.root_indices,
            (7,),
        )
        self.assertEqual(
            hierarchy.issues[0].code,
            "invalid_parent",
        )
        self.assertEqual(
            hierarchy.issues[0].bone_indices,
            (7,),
        )

    def test_cycle_links_are_broken_safely(self) -> None:
        hierarchy = build_bone_hierarchy(
            (
                make_view(
                    0,
                    parent_index=1,
                ),
                make_view(
                    1,
                    parent_index=0,
                ),
                make_view(
                    2,
                    parent_index=1,
                ),
            )
        )
        nodes = {node.bone.index: node for node in hierarchy.nodes}
        cycle_issues = [issue for issue in hierarchy.issues if issue.code == "cycle"]

        self.assertEqual(
            hierarchy.root_indices,
            (0, 1),
        )
        self.assertEqual(
            nodes[1].child_indices,
            (2,),
        )
        self.assertEqual(
            len(cycle_issues),
            1,
        )
        self.assertEqual(
            cycle_issues[0].bone_indices,
            (0, 1),
        )

    def test_self_parent_is_reported_as_cycle(self) -> None:
        hierarchy = build_bone_hierarchy(
            (
                make_view(
                    3,
                    parent_index=3,
                ),
            )
        )

        self.assertEqual(
            hierarchy.root_indices,
            (3,),
        )
        self.assertEqual(
            hierarchy.issues[0].code,
            "cycle",
        )
        self.assertEqual(
            hierarchy.issues[0].bone_indices,
            (3,),
        )

    def test_duplicate_index_keeps_first_record(self) -> None:
        hierarchy = build_bone_hierarchy(
            (
                make_view(
                    4,
                    name="First",
                ),
                make_view(
                    4,
                    name="Second",
                ),
            )
        )

        self.assertEqual(
            len(hierarchy.nodes),
            1,
        )
        self.assertEqual(
            hierarchy.nodes[0].bone.display_name,
            "First",
        )
        self.assertEqual(
            hierarchy.issues[0].code,
            "duplicate_index",
        )

    def test_deep_hierarchy_does_not_require_recursion(self) -> None:
        views = tuple(
            make_view(
                index,
                parent_index=(-1 if index == 0 else index - 1),
            )
            for index in range(1500)
        )

        hierarchy = build_bone_hierarchy(views)

        self.assertEqual(
            hierarchy.root_indices,
            (0,),
        )
        self.assertEqual(
            len(hierarchy.nodes),
            1500,
        )
        self.assertEqual(
            hierarchy.nodes[-1].child_indices,
            (),
        )

    def test_hierarchy_is_json_serializable(self) -> None:
        hierarchy = build_bone_hierarchy(
            (
                make_view(0),
                make_view(
                    1,
                    parent_index=0,
                ),
            )
        )

        report = hierarchy.to_dict()

        self.assertEqual(
            report["root_indices"],
            [0],
        )
        self.assertEqual(
            report["node_count"],
            2,
        )
        self.assertEqual(
            report["nodes"][0]["child_indices"],
            [1],
        )

    def test_renders_branching_tree(self) -> None:
        hierarchy = build_bone_hierarchy(
            (
                make_view(
                    3,
                    name="Leaf",
                    parent_index=1,
                ),
                make_view(
                    2,
                    name="Right",
                    parent_index=0,
                ),
                make_view(
                    0,
                    name="Root",
                ),
                make_view(
                    1,
                    name="Left",
                    parent_index=0,
                ),
            )
        )

        tree = render_bone_tree(hierarchy)

        self.assertEqual(
            tree,
            "\n".join(
                (
                    "[0] Root",
                    "├── [1] Left",
                    "│   └── [3] Leaf",
                    "└── [2] Right",
                )
            ),
        )

    def test_renders_multiple_roots_in_index_order(self) -> None:
        hierarchy = build_bone_hierarchy(
            (
                make_view(
                    5,
                    name="Second Root",
                ),
                make_view(
                    1,
                    name="First Root",
                ),
            )
        )

        self.assertEqual(
            render_bone_tree(hierarchy),
            "\n".join(
                (
                    "[1] First Root",
                    "[5] Second Root",
                )
            ),
        )

    def test_cycle_diagnostics_still_render_safely(self) -> None:
        hierarchy = build_bone_hierarchy(
            (
                make_view(
                    0,
                    name="Cycle A",
                    parent_index=1,
                ),
                make_view(
                    1,
                    name="Cycle B",
                    parent_index=0,
                ),
            )
        )

        self.assertEqual(
            render_bone_tree(hierarchy),
            "\n".join(
                (
                    "[0] Cycle A",
                    "[1] Cycle B",
                )
            ),
        )
        self.assertEqual(
            hierarchy.issues[0].code,
            "cycle",
        )

    def test_tree_normalizes_multiline_name(self) -> None:
        hierarchy = build_bone_hierarchy(
            (
                make_view(
                    0,
                    name="左\nひざ",
                ),
            )
        )

        self.assertEqual(
            render_bone_tree(hierarchy),
            "[0] 左 ひざ",
        )

    def test_empty_tree_is_readable(self) -> None:
        hierarchy = build_bone_hierarchy(())

        self.assertEqual(
            render_bone_tree(hierarchy),
            "No bones found.",
        )

    def test_deep_tree_renderer_does_not_recurse(self) -> None:
        views = tuple(
            make_view(
                index,
                parent_index=(-1 if index == 0 else index - 1),
            )
            for index in range(1200)
        )
        hierarchy = build_bone_hierarchy(views)

        lines = render_bone_tree(hierarchy).splitlines()

        self.assertEqual(
            len(lines),
            1200,
        )
        self.assertIn(
            "[1199] Bone 1199",
            lines[-1],
        )


if __name__ == "__main__":
    unittest.main()
