"""Human-readable detail presentation for individual PMX bones."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Literal, Sequence

from mmd_registry.bone_explorer import (
    BoneNameResolver,
    BoneView,
    build_bone_views,
    default_bone_name_resolver,
)
from mmd_registry.model_scanning import PmxBone


_CAPABILITY_DEFINITIONS: Final[tuple[tuple[str, str], ...]] = (
    ("rotatable", "Rotatable"),
    ("translatable", "Translatable"),
    ("visible", "Visible"),
    ("enabled", "Enabled"),
    ("ik", "IK"),
    ("inherit_rotation", "Inherits Rotation"),
    (
        "inherit_translation",
        "Inherits Translation",
    ),
    ("local_append", "Local Append Mode"),
    ("fixed_axis", "Fixed Axis"),
    ("local_axes", "Local Axes"),
    ("after_physics", "After Physics"),
    ("external_parent", "External Parent"),
)


@dataclass(frozen=True, slots=True)
class BoneCapabilityView:
    """One readable boolean capability for a PMX bone."""

    key: str
    label: str
    enabled: bool

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "key": self.key,
            "label": self.label,
            "enabled": self.enabled,
        }


@dataclass(frozen=True, slots=True)
class BoneDetailView:
    """Human-readable detail data for one PMX bone."""

    bone: BoneView
    transform_layer: int
    tail_mode: Literal["bone", "offset"]
    tail_bone_index: int | None
    tail_display_name: str | None
    tail_offset: tuple[float, float, float] | None
    capabilities: tuple[BoneCapabilityView, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "bone": self.bone.to_dict(),
            "transform_layer": self.transform_layer,
            "tail_mode": self.tail_mode,
            "tail_bone_index": self.tail_bone_index,
            "tail_display_name": self.tail_display_name,
            "tail_offset": (
                list(self.tail_offset) if self.tail_offset is not None else None
            ),
            "capabilities": [capability.to_dict() for capability in self.capabilities],
        }


def build_bone_capabilities(
    bone: PmxBone,
) -> tuple[BoneCapabilityView, ...]:
    """Build readable enabled/disabled capability records."""

    enabled_flags = set(bone.flag_names)

    return tuple(
        BoneCapabilityView(
            key=key,
            label=label,
            enabled=key in enabled_flags,
        )
        for key, label in _CAPABILITY_DEFINITIONS
    )


def build_bone_detail(
    bones: Sequence[PmxBone],
    bone_index: int,
    *,
    name_resolver: BoneNameResolver = (default_bone_name_resolver),
) -> BoneDetailView | None:
    """Build one detail view or return None for an invalid index."""

    source_bones = tuple(bones)

    if bone_index < 0 or bone_index >= len(source_bones):
        return None

    views = build_bone_views(
        source_bones,
        name_resolver=name_resolver,
    )
    source_bone = source_bones[bone_index]
    view = views[bone_index]

    tail_display_name: str | None = None
    tail_bone_index = source_bone.tail_bone_index

    if (
        source_bone.tail_mode == "bone"
        and tail_bone_index is not None
        and 0 <= tail_bone_index < len(views)
    ):
        tail_display_name = views[tail_bone_index].display_name

    return BoneDetailView(
        bone=view,
        transform_layer=source_bone.transform_layer,
        tail_mode=source_bone.tail_mode,
        tail_bone_index=tail_bone_index,
        tail_display_name=tail_display_name,
        tail_offset=source_bone.tail_offset,
        capabilities=build_bone_capabilities(source_bone),
    )


def _normalize_detail_text(
    value: str,
) -> str:
    """Return safe one-line detail text."""

    return " ".join(value.split())


def _format_parent(
    view: BoneView,
) -> str:
    """Return a readable parent reference."""

    if view.parent_index == -1:
        return "[root]"

    if view.parent_display_name is None:
        return f"[{view.parent_index}] [invalid]"

    parent_name = _normalize_detail_text(view.parent_display_name) or "[unnamed]"

    return f"[{view.parent_index}] {parent_name}"


def _format_tail(
    detail: BoneDetailView,
) -> str:
    """Return a readable tail reference or offset."""

    if detail.tail_mode == "bone":
        if detail.tail_bone_index is None or detail.tail_bone_index == -1:
            return "Bone [none]"

        if detail.tail_display_name is None:
            return f"Bone [{detail.tail_bone_index}] [invalid]"

        tail_name = _normalize_detail_text(detail.tail_display_name) or "[unnamed]"

        return f"Bone [{detail.tail_bone_index}] {tail_name}"

    if detail.tail_offset is None:
        return "Offset [not provided]"

    x, y, z = detail.tail_offset

    return f"Offset ({x:.3f}, {y:.3f}, {z:.3f})"


def render_bone_detail(
    detail: BoneDetailView,
) -> str:
    """Render one human-readable bone detail report."""

    view = detail.bone
    display_name = _normalize_detail_text(view.display_name) or "[unnamed]"
    original_name = _normalize_detail_text(view.local_name) or "[not provided]"
    universal_name = _normalize_detail_text(view.universal_name) or "[not provided]"
    x, y, z = view.position

    lines = [
        f"Bone #{view.index}",
        "",
        f"Display name:   {display_name}",
        f"Original name:  {original_name}",
        f"Universal name: {universal_name}",
        "",
        f"Parent:          {_format_parent(view)}",
        f"Transform layer: {detail.transform_layer}",
        f"Tail:            {_format_tail(detail)}",
        "",
        "Position:",
        f"  X: {x:.3f}",
        f"  Y: {y:.3f}",
        f"  Z: {z:.3f}",
        "",
        "Capabilities:",
    ]

    lines.extend(
        ("  ✓ " if capability.enabled else "  ✗ ") + capability.label
        for capability in detail.capabilities
    )

    return "\n".join(lines)
