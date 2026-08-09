"""Portable relative-path policy for explicit PMX texture edits."""

from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath


def validate_portable_texture_path(path: str) -> None:
    """Reject unsafe texture paths without normalizing the supplied text."""

    if not isinstance(path, str):
        raise TypeError("texture path must be a string.")
    if not path:
        raise ValueError("texture path cannot be empty.")
    if "\x00" in path:
        raise ValueError("texture path cannot contain NUL characters.")

    windows_path = PureWindowsPath(path)
    posix_path = PurePosixPath(path)
    if windows_path.drive or windows_path.root or posix_path.is_absolute():
        raise ValueError(
            "texture path must be portable and relative; absolute, rooted, "
            "and drive-qualified paths are not allowed."
        )

    if ".." in windows_path.parts:
        raise ValueError(
            "texture path cannot contain a '..' parent-directory component."
        )
