"""Human-readable presentation models for PMX bones."""

from __future__ import annotations

import unicodedata
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

_MAX_NAME_COLUMN_WIDTH: Final[int] = 28
_MAX_ORIGINAL_COLUMN_WIDTH: Final[int] = 20
_MAX_PARENT_COLUMN_WIDTH: Final[int] = 32
_MAX_TAGS_COLUMN_WIDTH: Final[int] = 48


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


def _character_display_width(character: str) -> int:
    """Return an approximate terminal width for one Unicode character."""

    if unicodedata.combining(character):
        return 0

    if unicodedata.east_asian_width(character) in {"F", "W"}:
        return 2

    return 1


def _terminal_display_width(value: str) -> int:
    """Return the approximate terminal width of one string."""

    return sum(_character_display_width(character) for character in value)


def _truncate_table_text(value: str, max_width: int) -> str:
    """Truncate text to a terminal width using an ASCII marker."""

    if _terminal_display_width(value) <= max_width:
        return value

    marker = "..."

    if max_width <= len(marker):
        return marker[:max_width]

    available_width = max_width - len(marker)
    characters: list[str] = []
    used_width = 0

    for character in value:
        character_width = _character_display_width(character)

        if used_width + character_width > available_width:
            break

        characters.append(character)
        used_width += character_width

    return "".join(characters) + marker


def _fit_table_text(value: str, width: int) -> str:
    """Truncate and pad one table cell to its terminal width."""

    fitted = _truncate_table_text(value, width)
    padding = width - _terminal_display_width(fitted)
    return fitted + (" " * padding)


def _bounded_column_width(
    header: str,
    values: Sequence[str],
    maximum: int,
) -> int:
    """Return a content-aware column width with a safe upper bound."""

    width = _terminal_display_width(header)

    for value in values:
        width = max(width, _terminal_display_width(value))

    return min(width, maximum)


def _format_parent_cell(view: BoneView) -> str:
    """Return a compact parent reference for one bone."""

    if view.parent_index == -1:
        return "-"

    if view.parent_display_name is None:
        return f"[{view.parent_index}] [invalid]"

    parent_name = _normalize_display_name(view.parent_display_name) or "[unnamed]"

    return f"[{view.parent_index}] {parent_name}"


def _render_table_row(
    values: Sequence[str],
    widths: Sequence[int],
) -> str:
    """Render one table row without trailing padding."""

    cells = [
        _fit_table_text(value, width) for value, width in zip(values[:-1], widths[:-1])
    ]
    cells.append(_truncate_table_text(values[-1], widths[-1]))

    return "  ".join(cells)


def render_bone_table(views: Sequence[BoneView]) -> str:
    """Render bone presentation records as a compact text table."""

    if not views:
        return "No bones found."

    rows: list[tuple[str, str, str, str, str]] = []

    for view in views:
        display_name = _normalize_display_name(view.display_name) or "[unnamed]"
        original_name = _normalize_display_name(view.local_name) or "-"
        parent = _format_parent_cell(view)
        tags = ", ".join(view.tags) or "-"

        rows.append(
            (
                str(view.index),
                display_name,
                original_name,
                parent,
                tags,
            )
        )

    headers = ("Idx", "Name", "Original", "Parent", "Tags")

    index_width = max(
        len(headers[0]),
        max(len(row[0]) for row in rows),
    )
    name_width = _bounded_column_width(
        headers[1],
        tuple(row[1] for row in rows),
        _MAX_NAME_COLUMN_WIDTH,
    )
    original_width = _bounded_column_width(
        headers[2],
        tuple(row[2] for row in rows),
        _MAX_ORIGINAL_COLUMN_WIDTH,
    )
    parent_width = _bounded_column_width(
        headers[3],
        tuple(row[3] for row in rows),
        _MAX_PARENT_COLUMN_WIDTH,
    )
    tags_width = _bounded_column_width(
        headers[4],
        tuple(row[4] for row in rows),
        _MAX_TAGS_COLUMN_WIDTH,
    )

    widths = (
        index_width,
        name_width,
        original_width,
        parent_width,
        tags_width,
    )

    lines = [
        _render_table_row(headers, widths),
        "  ".join("-" * width for width in widths),
    ]
    lines.extend(_render_table_row(row, widths) for row in rows)

    return "\n".join(lines)
