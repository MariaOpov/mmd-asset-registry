"""Human-readable presentation models for PMX bones."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Final, Sequence, TypeAlias

from mmd_registry.model_scanning import PmxBone


BoneNameResolver: TypeAlias = Callable[[PmxBone], str]

_BONE_FLAG_LABELS: Final[dict[str, str]] = {
    "tail_index": "Tail: Bone",
    "rotatable": "Rotate",
    "translatable": "Move",
    "visible": "Visible",
    "enabled": "Enabled",
    "ik": "IK",
    "local_append": "Local Append",
    "inherit_rotation": "Inherits Rotation",
    "inherit_translation": "Inherits Translation",
    "fixed_axis": "Fixed Axis",
    "local_axes": "Local Axes",
    "after_physics": "After Physics",
    "external_parent": "External Parent",
}


def _normalize_display_name(value: str) -> str:
    """Collapse presentation-only whitespace in one bone name."""

    return " ".join(value.split())


def default_bone_name_resolver(bone: PmxBone) -> str:
    """Resolve a safe display name without translating the source text."""

    universal_name = _normalize_display_name(bone.universal_name)

    if universal_name:
        return universal_name

    local_name = _normalize_display_name(bone.local_name)

    if local_name:
        return local_name

    return "[unnamed]"


def format_bone_flag(flag_name: str) -> str:
    """Convert one stable scanner flag name into a readable label."""

    return _BONE_FLAG_LABELS.get(
        flag_name,
        flag_name.replace("_", " ").title(),
    )


def build_bone_tags(bone: PmxBone) -> tuple[str, ...]:
    """Return readable presentation tags for one bone."""

    return tuple(format_bone_flag(name) for name in bone.flag_names)


@dataclass(frozen=True, slots=True)
class BoneView:
    """Human-readable presentation data for one PMX bone."""

    index: int
    display_name: str
    local_name: str
    universal_name: str
    parent_index: int
    parent_display_name: str | None
    position: tuple[float, float, float]
    tags: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "index": self.index,
            "display_name": self.display_name,
            "local_name": self.local_name,
            "universal_name": self.universal_name,
            "parent_index": self.parent_index,
            "parent_display_name": self.parent_display_name,
            "position": list(self.position),
            "tags": list(self.tags),
        }


def build_bone_views(
    bones: Sequence[PmxBone],
    *,
    name_resolver: BoneNameResolver = default_bone_name_resolver,
) -> tuple[BoneView, ...]:
    """Build presentation records without modifying scanner data."""

    source_bones = tuple(bones)
    display_names = tuple(
        _normalize_display_name(name_resolver(bone)) or default_bone_name_resolver(bone)
        for bone in source_bones
    )

    views: list[BoneView] = []

    for index, bone in enumerate(source_bones):
        parent_index = bone.parent_bone_index
        parent_display_name = (
            display_names[parent_index]
            if 0 <= parent_index < len(display_names)
            else None
        )

        views.append(
            BoneView(
                index=index,
                display_name=display_names[index],
                local_name=bone.local_name,
                universal_name=bone.universal_name,
                parent_index=parent_index,
                parent_display_name=parent_display_name,
                position=bone.position,
                tags=build_bone_tags(bone),
            )
        )

    return tuple(views)
