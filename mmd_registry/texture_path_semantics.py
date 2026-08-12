"""Host-independent lexical semantics for declared PMX texture paths."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath, PureWindowsPath


class TexturePathKind(StrEnum):
    """Stable lexical classifications for one declared texture path."""

    EMPTY = "empty"
    RELATIVE = "relative"
    POSIX_ABSOLUTE = "posix_absolute"
    WINDOWS_ABSOLUTE = "windows_absolute"
    WINDOWS_DRIVE_RELATIVE = "windows_drive_relative"
    WINDOWS_ROOTED = "windows_rooted"
    WINDOWS_UNC = "windows_unc"


@dataclass(frozen=True, slots=True)
class TexturePathLexicalAnalysis:
    """Pure lexical facts derived from one declared PMX texture path."""

    declared_path: str
    normalized_path: str
    kind: TexturePathKind
    contains_nul: bool
    contains_parent_reference: bool
    contains_current_reference: bool
    uses_forward_separator: bool
    uses_backslash_separator: bool
    mixed_separators: bool
    windows_is_absolute: bool
    windows_has_drive: bool
    windows_has_root: bool
    posix_is_absolute: bool
    normalized_posix_is_absolute: bool

    @property
    def is_empty(self) -> bool:
        """Return whether the declaration is empty."""

        return self.kind is TexturePathKind.EMPTY

    @property
    def is_absolute(self) -> bool:
        """Return whether either Windows or POSIX syntax is absolute."""

        return self.windows_is_absolute or self.posix_is_absolute

    @property
    def is_drive_qualified(self) -> bool:
        """Return whether Windows syntax carries a drive or UNC share."""

        return self.windows_has_drive

    @property
    def is_rooted(self) -> bool:
        """Return whether syntax is rooted independently of drive qualification."""

        return self.windows_has_root or self.posix_is_absolute

    @property
    def is_plain_relative(self) -> bool:
        """Return whether the declaration is lexically safe for edit-policy use."""

        return (
            self.kind is TexturePathKind.RELATIVE
            and not self.contains_nul
            and not self.contains_parent_reference
        )

    def to_dict(self) -> dict[str, object]:
        """Return a deterministic JSON-ready lexical representation."""

        return {
            "declared_path": self.declared_path,
            "normalized_path": self.normalized_path,
            "kind": self.kind.value,
            "contains_nul": self.contains_nul,
            "contains_parent_reference": self.contains_parent_reference,
            "contains_current_reference": self.contains_current_reference,
            "uses_forward_separator": self.uses_forward_separator,
            "uses_backslash_separator": self.uses_backslash_separator,
            "mixed_separators": self.mixed_separators,
            "is_absolute": self.is_absolute,
            "is_drive_qualified": self.is_drive_qualified,
            "is_rooted": self.is_rooted,
        }


def _normalized_texture_path(path: str, windows_path: PureWindowsPath) -> str:
    """Return the existing diagnostic separator-normalized representation."""

    if path == "":
        return ""
    if "\\" in path or windows_path.drive or windows_path.root:
        return windows_path.as_posix()
    return PurePosixPath(path).as_posix()


def _contains_current_reference(path: str) -> bool:
    """Return whether an explicit '.' component appears in the declaration."""

    if not path:
        return False
    components = path.replace("\\", "/").split("/")
    return "." in components


def _classify_texture_path_kind(
    path: str,
    *,
    windows_path: PureWindowsPath,
    posix_path: PurePosixPath,
) -> TexturePathKind:
    """Classify path syntax without consulting the host operating system."""

    if path == "":
        return TexturePathKind.EMPTY

    if windows_path.is_absolute():
        if windows_path.drive.startswith("\\\\"):
            return TexturePathKind.WINDOWS_UNC
        return TexturePathKind.WINDOWS_ABSOLUTE

    if windows_path.drive:
        return TexturePathKind.WINDOWS_DRIVE_RELATIVE

    if path.startswith("\\"):
        return TexturePathKind.WINDOWS_ROOTED

    if posix_path.is_absolute():
        return TexturePathKind.POSIX_ABSOLUTE

    return TexturePathKind.RELATIVE


def analyze_texture_path(path: str) -> TexturePathLexicalAnalysis:
    """Analyze one PMX texture declaration without filesystem access."""

    if not isinstance(path, str):
        raise TypeError("texture path must be a string.")

    windows_path = PureWindowsPath(path)
    normalized_path = _normalized_texture_path(path, windows_path)
    posix_path = PurePosixPath(path)
    normalized_posix_path = PurePosixPath(normalized_path)
    path_kind = _classify_texture_path_kind(
        path,
        windows_path=windows_path,
        posix_path=posix_path,
    )

    contains_parent_reference = (
        ".." in windows_path.parts or ".." in posix_path.parts
    )
    uses_forward_separator = "/" in path
    uses_backslash_separator = "\\" in path

    return TexturePathLexicalAnalysis(
        declared_path=path,
        normalized_path=normalized_path,
        kind=path_kind,
        contains_nul="\x00" in path,
        contains_parent_reference=contains_parent_reference,
        contains_current_reference=_contains_current_reference(path),
        uses_forward_separator=uses_forward_separator,
        uses_backslash_separator=uses_backslash_separator,
        mixed_separators=uses_forward_separator and uses_backslash_separator,
        windows_is_absolute=windows_path.is_absolute(),
        windows_has_drive=bool(windows_path.drive),
        windows_has_root=bool(windows_path.root),
        posix_is_absolute=posix_path.is_absolute(),
        normalized_posix_is_absolute=normalized_posix_path.is_absolute(),
    )
