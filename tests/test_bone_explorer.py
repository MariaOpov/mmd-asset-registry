"""Tests for human-readable PMX bone presentation."""

from __future__ import annotations

import unittest

from mmd_registry.bone_explorer import (
    build_bone_tags,
    build_bone_views,
    default_bone_name_resolver,
)
from mmd_registry.model_scanning import PmxBone


def make_bone(
    *,
    local_name: str = "Bone",
    universal_name: str = "",
    parent_index: int = -1,
    flag_names: tuple[str, ...] = (),
) -> PmxBone:
    """Build one small scanner record for presentation tests."""

    return PmxBone(
        local_name=local_name,
        universal_name=universal_name,
        position=(1.0, 2.0, 3.0),
        parent_bone_index=parent_index,
        transform_layer=0,
        flags=0,
        flag_names=flag_names,
        tail_mode="offset",
        tail_bone_index=None,
        tail_offset=(0.0, 1.0, 0.0),
        inherit_parent_bone_index=None,
        inherit_weight=None,
        fixed_axis=None,
        local_axis_x=None,
        local_axis_z=None,
        external_parent_key=None,
        ik=None,
    )


class BoneExplorerTests(unittest.TestCase):
    """Tests for bone presentation records and naming."""

    def test_display_name_prefers_normalized_universal_name(self) -> None:
        bone = make_bone(
            local_name="左ひざD",
            universal_name="  Bip001   L CalfD  ",
        )

        self.assertEqual(
            default_bone_name_resolver(bone),
            "Bip001 L CalfD",
        )

    def test_display_name_falls_back_safely(self) -> None:
        self.assertEqual(
            default_bone_name_resolver(
                make_bone(local_name="  左ひざD  "),
            ),
            "左ひざD",
        )
        self.assertEqual(
            default_bone_name_resolver(
                make_bone(local_name=" ", universal_name="\t"),
            ),
            "[unnamed]",
        )

    def test_builds_forward_parent_relationship(self) -> None:
        bones = (
            make_bone(local_name="Child", parent_index=1),
            make_bone(local_name="Root", universal_name="Root EN"),
        )

        views = build_bone_views(bones)

        self.assertEqual(views[0].parent_index, 1)
        self.assertEqual(views[0].parent_display_name, "Root EN")
        self.assertIsNone(views[1].parent_display_name)

    def test_invalid_parent_is_safe(self) -> None:
        view = build_bone_views(
            (make_bone(parent_index=99),),
        )[0]

        self.assertEqual(view.parent_index, 99)
        self.assertIsNone(view.parent_display_name)

    def test_name_resolver_is_replaceable(self) -> None:
        views = build_bone_views(
            (make_bone(local_name="左腕"),),
            name_resolver=lambda bone: f"Friendly {bone.local_name}",
        )

        self.assertEqual(views[0].display_name, "Friendly 左腕")

    def test_builds_readable_tags(self) -> None:
        bone = make_bone(
            flag_names=(
                "tail_index",
                "rotatable",
                "inherit_rotation",
                "future_helper",
            ),
        )

        self.assertEqual(
            build_bone_tags(bone),
            (
                "Tail: Bone",
                "Rotate",
                "Inherits Rotation",
                "Future Helper",
            ),
        )

    def test_view_is_json_serializable(self) -> None:
        report = build_bone_views((make_bone(),))[0].to_dict()

        self.assertEqual(report["index"], 0)
        self.assertEqual(report["position"], [1.0, 2.0, 3.0])
        self.assertEqual(report["tags"], [])


if __name__ == "__main__":
    unittest.main()
