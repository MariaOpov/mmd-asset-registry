"""Portable relative-path policy for explicit PMX texture edits."""

from __future__ import annotations

from mmd_registry.texture_path_semantics import analyze_texture_path


def validate_portable_texture_path(path: str) -> None:
    """Reject unsafe texture paths without normalizing the supplied text."""

    if not isinstance(path, str):
        raise TypeError("texture path must be a string.")

    analysis = analyze_texture_path(path)

    if analysis.is_empty:
        raise ValueError("texture path cannot be empty.")
    if analysis.contains_nul:
        raise ValueError("texture path cannot contain NUL characters.")

    if (
        analysis.windows_has_drive
        or analysis.windows_has_root
        or analysis.posix_is_absolute
    ):
        raise ValueError(
            "texture path must be portable and relative; absolute, rooted, "
            "and drive-qualified paths are not allowed."
        )

    if analysis.contains_parent_reference:
        raise ValueError(
            "texture path cannot contain a '..' parent-directory component."
        )
