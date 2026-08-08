"""Tests for individual PMX bone detail presentation."""

from __future__ import annotations

import json
import unittest
from typing import Literal

from mmd_registry.bone_details import (
    build_bone_capabilities,
    build_bone_detail,
    render_bone_detail,
)
from mmd_registry.model_scanning import PmxBone


def make_bone(
    *,
    local_name: str = "Bone",
    universal_name: str = "",
    position: tuple[float, float, float] = (
        0.0,
        0.0,
        0.0,
    ),
    parent_index: int = -1,
    transform_layer: int = 0,
    flag_names: tuple[str, ...] = (),
    tail_mode: Literal["bone", "offset"] = "offset",
    tail_bone_index: int | None = None,
    tail_offset: tuple[float, float, float] | None = (
        0.0,
        1.0,
        0.0,
    ),
) -> PmxBone:
    """Build one small scanner record for detail tests."""

    return PmxBone(
        local_name=local_name,
        universal_name=universal_name,
        position=position,
        parent_bone_index=parent_index,
        transform_layer=transform_layer,
        flags=0,
        flag_names=flag_names,
        tail_mode=tail_mode,
        tail_bone_index=tail_bone_index,
        tail_offset=tail_offset,
        inherit_parent_bone_index=None,
        inherit_weight=None,
        fixed_axis=None,
        local_axis_x=None,
        local_axis_z=None,
        external_parent_key=None,
        ik=None,
    )


class BoneDetailTests(unittest.TestCase):
    """Tests for bone detail records and text output."""

    def test_invalid_index_returns_none(self) -> None:
        bones = (make_bone(),)

        self.assertIsNone(
            build_bone_detail(
                bones,
                -1,
            )
        )
        self.assertIsNone(
            build_bone_detail(
                bones,
                1,
            )
        )

    def test_builds_parent_and_tail_references(self) -> None:
        bones = (
            make_bone(
                local_name="全ての親",
                universal_name="Root",
            ),
            make_bone(
                local_name="左ひざD",
                universal_name="Bip001 L CalfD",
                parent_index=0,
                transform_layer=2,
                tail_mode="bone",
                tail_bone_index=0,
                tail_offset=None,
            ),
        )

        detail = build_bone_detail(
            bones,
            1,
        )

        self.assertIsNotNone(detail)
        assert detail is not None

        self.assertEqual(
            detail.bone.display_name,
            "Bip001 L CalfD",
        )
        self.assertEqual(
            detail.bone.parent_display_name,
            "Root",
        )
        self.assertEqual(
            detail.transform_layer,
            2,
        )
        self.assertEqual(
            detail.tail_display_name,
            "Root",
        )

    def test_builds_enabled_and_disabled_capabilities(self) -> None:
        capabilities = build_bone_capabilities(
            make_bone(
                flag_names=(
                    "rotatable",
                    "visible",
                    "ik",
                ),
            )
        )
        enabled_by_key = {
            capability.key: capability.enabled for capability in capabilities
        }

        self.assertTrue(
            enabled_by_key["rotatable"],
        )
        self.assertTrue(
            enabled_by_key["visible"],
        )
        self.assertTrue(
            enabled_by_key["ik"],
        )
        self.assertFalse(
            enabled_by_key["translatable"],
        )
        self.assertFalse(
            enabled_by_key["inherit_rotation"],
        )

    def test_name_resolver_applies_to_detail_references(self) -> None:
        bones = (
            make_bone(
                local_name="親",
            ),
            make_bone(
                local_name="子",
                parent_index=0,
                tail_mode="bone",
                tail_bone_index=0,
                tail_offset=None,
            ),
        )

        detail = build_bone_detail(
            bones,
            1,
            name_resolver=(lambda bone: f"Friendly {bone.local_name}"),
        )

        self.assertIsNotNone(detail)
        assert detail is not None

        self.assertEqual(
            detail.bone.display_name,
            "Friendly 子",
        )
        self.assertEqual(
            detail.bone.parent_display_name,
            "Friendly 親",
        )
        self.assertEqual(
            detail.tail_display_name,
            "Friendly 親",
        )

    def test_renders_readable_detail_report(self) -> None:
        bones = (
            make_bone(
                local_name="左足D",
                universal_name="Bip001 L ThighD",
            ),
            make_bone(
                local_name="左ひざD",
                universal_name="Bip001 L CalfD",
                position=(
                    0.9329758,
                    7.7174044,
                    -0.3604323,
                ),
                parent_index=0,
                flag_names=(
                    "rotatable",
                    "visible",
                    "enabled",
                    "inherit_rotation",
                ),
            ),
        )
        detail = build_bone_detail(
            bones,
            1,
        )

        self.assertIsNotNone(detail)
        assert detail is not None

        report = render_bone_detail(detail)

        self.assertIn(
            "Bone #1",
            report,
        )
        self.assertIn(
            "Display name:   Bip001 L CalfD",
            report,
        )
        self.assertIn(
            "Original name:  左ひざD",
            report,
        )
        self.assertIn(
            "Parent:          [0] Bip001 L ThighD",
            report,
        )
        self.assertIn(
            "X: 0.933",
            report,
        )
        self.assertIn(
            "Y: 7.717",
            report,
        )
        self.assertIn(
            "Z: -0.360",
            report,
        )
        self.assertIn(
            "✓ Rotatable",
            report,
        )
        self.assertIn(
            "✓ Inherits Rotation",
            report,
        )
        self.assertIn(
            "✗ Translatable",
            report,
        )
        self.assertIn(
            "✗ IK",
            report,
        )

    def test_renders_root_and_offset_tail(self) -> None:
        detail = build_bone_detail(
            (
                make_bone(
                    local_name="センター",
                    tail_mode="offset",
                    tail_offset=(
                        0.0,
                        1.5,
                        0.0,
                    ),
                ),
            ),
            0,
        )

        self.assertIsNotNone(detail)
        assert detail is not None

        report = render_bone_detail(detail)

        self.assertIn(
            "Universal name: [not provided]",
            report,
        )
        self.assertIn(
            "Parent:          [root]",
            report,
        )
        self.assertIn(
            "Tail:            Offset (0.000, 1.500, 0.000)",
            report,
        )

    def test_invalid_parent_and_tail_are_readable(self) -> None:
        detail = build_bone_detail(
            (
                make_bone(
                    parent_index=99,
                    tail_mode="bone",
                    tail_bone_index=88,
                    tail_offset=None,
                ),
            ),
            0,
        )

        self.assertIsNotNone(detail)
        assert detail is not None

        report = render_bone_detail(detail)

        self.assertIn(
            "Parent:          [99] [invalid]",
            report,
        )
        self.assertIn(
            "Tail:            Bone [88] [invalid]",
            report,
        )

    def test_minus_one_tail_is_readable(self) -> None:
        detail = build_bone_detail(
            (
                make_bone(
                    tail_mode="bone",
                    tail_bone_index=-1,
                    tail_offset=None,
                ),
            ),
            0,
        )

        self.assertIsNotNone(detail)
        assert detail is not None

        self.assertIn(
            "Tail:            Bone [none]",
            render_bone_detail(detail),
        )

    def test_detail_is_json_serializable(self) -> None:
        detail = build_bone_detail(
            (
                make_bone(
                    flag_names=("rotatable",),
                ),
            ),
            0,
        )

        self.assertIsNotNone(detail)
        assert detail is not None

        report = detail.to_dict()
        encoded = json.dumps(
            report,
            ensure_ascii=False,
        )

        self.assertEqual(
            report["bone"]["index"],
            0,
        )
        self.assertEqual(
            report["tail_offset"],
            [0.0, 1.0, 0.0],
        )
        self.assertIn(
            '"Rotatable"',
            encoded,
        )


if __name__ == "__main__":
    unittest.main()
