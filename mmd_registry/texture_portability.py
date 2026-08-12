"""Deterministic read-only portability analysis for PMX texture paths."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Sequence

from mmd_registry.texture_path_semantics import (
    TexturePathKind,
    TexturePathLexicalAnalysis,
    analyze_texture_path,
)


class TexturePortabilityIssueCode(StrEnum):
    """Stable machine-readable issue codes for portability analysis."""

    EMPTY_PATH = "empty_path"
    NUL_CHARACTER = "nul_character"
    ABSOLUTE_PATH = "absolute_path"
    ROOTED_PATH = "rooted_path"
    PARENT_REFERENCE = "parent_reference"
    FILESYSTEM_UNRESOLVED = "filesystem_unresolved"
    OUTSIDE_MODEL_DIRECTORY = "outside_model_directory"
    MISSING_FILE = "missing_file"
    NOT_A_FILE = "not_a_file"


class TexturePortabilityIssueStage(StrEnum):
    """Analysis stage that produced one portability issue."""

    LEXICAL = "lexical"
    FILESYSTEM = "filesystem"


@dataclass(frozen=True, slots=True)
class TexturePortabilityIssue:
    """One deterministic portability finding."""

    code: TexturePortabilityIssueCode
    stage: TexturePortabilityIssueStage

    def __post_init__(self) -> None:
        if not isinstance(self.code, TexturePortabilityIssueCode):
            raise TypeError("code must be a TexturePortabilityIssueCode.")
        if not isinstance(self.stage, TexturePortabilityIssueStage):
            raise TypeError("stage must be a TexturePortabilityIssueStage.")

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-ready issue representation."""

        return {"code": self.code.value, "stage": self.stage.value}


@dataclass(frozen=True, slots=True)
class TextureFilesystemEvidence:
    """Optional host filesystem evidence for one declared texture path."""

    resolution_supported: bool
    resolution_failed: bool
    resolved_path: str | None
    outside_model_directory: bool | None
    exists: bool | None
    is_file: bool | None

    def __post_init__(self) -> None:
        if not self.resolution_supported:
            if self.resolution_failed:
                raise ValueError(
                    "unsupported filesystem resolution cannot also be failed."
                )
            if any(
                value is not None
                for value in (
                    self.resolved_path,
                    self.outside_model_directory,
                    self.exists,
                    self.is_file,
                )
            ):
                raise ValueError(
                    "unsupported filesystem resolution cannot carry evidence."
                )
        if self.resolution_failed and any(
            value is not None
            for value in (
                self.resolved_path,
                self.outside_model_directory,
                self.exists,
                self.is_file,
            )
        ):
            raise ValueError("failed filesystem resolution cannot carry evidence.")
        if self.resolution_supported and not self.resolution_failed:
            if self.resolved_path is None:
                raise ValueError("resolved filesystem evidence requires a path.")
            if type(self.outside_model_directory) is not bool:
                raise ValueError(
                    "resolved filesystem evidence requires containment state."
                )
            if type(self.exists) is not bool or type(self.is_file) is not bool:
                raise ValueError(
                    "resolved filesystem evidence requires file-state booleans."
                )

    def to_dict(self) -> dict[str, object]:
        """Return a deterministic JSON-ready evidence representation."""

        return {
            "resolution_supported": self.resolution_supported,
            "resolution_failed": self.resolution_failed,
            "resolved_path": self.resolved_path,
            "outside_model_directory": self.outside_model_directory,
            "exists": self.exists,
            "is_file": self.is_file,
        }


@dataclass(frozen=True, slots=True)
class TexturePortabilityEntry:
    """Structured portability result for one declared texture path."""

    texture_index: int
    declared_path: str
    normalized_path: str
    is_referenced: bool
    lexical: TexturePathLexicalAnalysis
    filesystem: TextureFilesystemEvidence
    issues: tuple[TexturePortabilityIssue, ...]
    portable: bool
    candidate_path: str | None

    def __post_init__(self) -> None:
        if isinstance(self.texture_index, bool) or not isinstance(
            self.texture_index, int
        ):
            raise TypeError("texture_index must be an integer.")
        if self.texture_index < 0:
            raise ValueError("texture_index cannot be negative.")
        if type(self.is_referenced) is not bool or type(self.portable) is not bool:
            raise TypeError("portability state fields must be booleans.")
        if self.declared_path != self.lexical.declared_path:
            raise ValueError("declared_path must match lexical analysis.")
        if self.normalized_path != self.lexical.normalized_path:
            raise ValueError("normalized_path must match lexical analysis.")
        if type(self.issues) is not tuple or not all(
            isinstance(issue, TexturePortabilityIssue) for issue in self.issues
        ):
            raise TypeError("issues must contain TexturePortabilityIssue values.")
        if self.candidate_path is not None:
            if not self.portable:
                raise ValueError(
                    "non-portable entries cannot expose a candidate path."
                )
            candidate_analysis = analyze_texture_path(self.candidate_path)
            if not candidate_analysis.is_plain_relative:
                raise ValueError(
                    "candidate_path must be a safe relative texture path."
                )

    @property
    def issue_codes(self) -> tuple[str, ...]:
        """Return issue codes in deterministic analysis order."""

        return tuple(issue.code.value for issue in self.issues)

    def to_dict(self) -> dict[str, Any]:
        """Return a deterministic JSON-ready entry representation."""

        return {
            "texture_index": self.texture_index,
            "declared_path": self.declared_path,
            "normalized_path": self.normalized_path,
            "is_referenced": self.is_referenced,
            "portable": self.portable,
            "candidate_path": self.candidate_path,
            "lexical": self.lexical.to_dict(),
            "filesystem": self.filesystem.to_dict(),
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class TexturePortabilityReport:
    """Aggregate deterministic portability analysis for one model."""

    declared_texture_count: int
    referenced_texture_count: int
    portable_texture_count: int
    candidate_texture_count: int
    entries: tuple[TexturePortabilityEntry, ...]

    def __post_init__(self) -> None:
        if type(self.entries) is not tuple or not all(
            isinstance(entry, TexturePortabilityEntry) for entry in self.entries
        ):
            raise TypeError("entries must contain TexturePortabilityEntry values.")
        expected_counts = (
            len(self.entries),
            sum(entry.is_referenced for entry in self.entries),
            sum(entry.portable for entry in self.entries),
            sum(entry.candidate_path is not None for entry in self.entries),
        )
        actual_counts = (
            self.declared_texture_count,
            self.referenced_texture_count,
            self.portable_texture_count,
            self.candidate_texture_count,
        )
        if actual_counts != expected_counts:
            raise ValueError("portability report counts must match entries.")

    def to_dict(self) -> dict[str, Any]:
        """Return a deterministic JSON-ready report representation."""

        return {
            "declared_texture_count": self.declared_texture_count,
            "referenced_texture_count": self.referenced_texture_count,
            "portable_texture_count": self.portable_texture_count,
            "candidate_texture_count": self.candidate_texture_count,
            "entries": [entry.to_dict() for entry in self.entries],
        }


def _path_text(path: Path) -> str:
    return path.as_posix()


def _validate_reference_indices(
    indices: Iterable[int],
    texture_count: int,
) -> frozenset[int]:
    normalized: set[int] = set()
    for index in indices:
        if isinstance(index, bool) or not isinstance(index, int):
            raise TypeError("Texture reference indices must be integers.")
        if index < 0 or index >= texture_count:
            raise ValueError(
                "Texture reference index is outside the declared texture "
                f"range: {index}"
            )
        normalized.add(index)
    return frozenset(normalized)


def _filesystem_candidate(
    *,
    model_directory: Path,
    lexical: TexturePathLexicalAnalysis,
) -> Path | None:
    """Return a native candidate only when host resolution is deterministic."""

    if lexical.is_empty or lexical.contains_nul:
        return None

    if lexical.kind is TexturePathKind.RELATIVE:
        return model_directory.joinpath(
            *PurePosixPath(lexical.normalized_path).parts
        )

    if lexical.kind is TexturePathKind.POSIX_ABSOLUTE:
        if os.name == "nt":
            return None
        return Path(lexical.normalized_path)

    if lexical.kind in {
        TexturePathKind.WINDOWS_ABSOLUTE,
        TexturePathKind.WINDOWS_UNC,
    }:
        if os.name != "nt":
            return None
        return Path(lexical.declared_path)

    # Root-only and drive-relative Windows paths depend on implicit host state.
    return None


def _components_have_exact_spelling(
    *,
    start_directory: Path,
    components: tuple[str, ...],
) -> bool:
    """Require exact on-disk component spelling without case guessing."""

    current = start_directory
    for component in components:
        if component in ("", "."):
            continue
        if component == "..":
            current = current.parent
            continue

        try:
            with os.scandir(current) as entries:
                if not any(entry.name == component for entry in entries):
                    return False
        except (FileNotFoundError, NotADirectoryError):
            return False

        current = current / component

    return True


def _candidate_has_exact_spelling(
    *,
    model_directory: Path,
    lexical: TexturePathLexicalAnalysis,
    candidate: Path,
) -> bool:
    """Reject host-only case folding or other spelling substitutions."""

    if lexical.kind is TexturePathKind.RELATIVE:
        components: list[str] = []
        for component in PurePosixPath(lexical.normalized_path).parts:
            if component in ("", "."):
                continue
            if component == "..":
                if not components:
                    return False
                components.pop()
                continue
            components.append(component)

        if not components:
            return False
        return _components_have_exact_spelling(
            start_directory=model_directory,
            components=tuple(components),
        )

    native = candidate.absolute()
    anchor = native.anchor
    if not anchor:
        return False
    parts = native.parts
    components = tuple(parts[1:]) if parts and parts[0] == anchor else tuple(parts)
    return _components_have_exact_spelling(
        start_directory=Path(anchor),
        components=components,
    )


def _outside_model_directory(candidate: Path, model_directory: Path) -> bool:
    candidate_resolved = candidate.resolve(strict=False)
    model_directory_resolved = model_directory.resolve(strict=False)
    try:
        candidate_resolved.relative_to(model_directory_resolved)
    except ValueError:
        return True
    return False


def collect_texture_filesystem_evidence(
    *,
    model_path: str | Path,
    lexical: TexturePathLexicalAnalysis,
) -> TextureFilesystemEvidence:
    """Collect host filesystem evidence without mutating any file."""

    if not isinstance(lexical, TexturePathLexicalAnalysis):
        raise TypeError("lexical must be a TexturePathLexicalAnalysis.")

    model_directory = Path(model_path).parent
    candidate = _filesystem_candidate(
        model_directory=model_directory,
        lexical=lexical,
    )
    if candidate is None:
        return TextureFilesystemEvidence(
            resolution_supported=False,
            resolution_failed=False,
            resolved_path=None,
            outside_model_directory=None,
            exists=None,
            is_file=None,
        )

    try:
        resolved = candidate.resolve(strict=False)
        outside = _outside_model_directory(candidate, model_directory)
        spelling_matches = _candidate_has_exact_spelling(
            model_directory=model_directory,
            lexical=lexical,
            candidate=candidate,
        )
        exists = spelling_matches and resolved.exists()
        is_file = resolved.is_file() if exists else False
    except (OSError, RuntimeError, ValueError):
        return TextureFilesystemEvidence(
            resolution_supported=True,
            resolution_failed=True,
            resolved_path=None,
            outside_model_directory=None,
            exists=None,
            is_file=None,
        )

    return TextureFilesystemEvidence(
        resolution_supported=True,
        resolution_failed=False,
        resolved_path=_path_text(resolved),
        outside_model_directory=outside,
        exists=exists,
        is_file=is_file,
    )


def _build_issues(
    lexical: TexturePathLexicalAnalysis,
    filesystem: TextureFilesystemEvidence,
) -> tuple[TexturePortabilityIssue, ...]:
    issues: list[TexturePortabilityIssue] = []

    def add(
        code: TexturePortabilityIssueCode,
        stage: TexturePortabilityIssueStage,
    ) -> None:
        issues.append(TexturePortabilityIssue(code=code, stage=stage))

    if lexical.is_empty:
        add(
            TexturePortabilityIssueCode.EMPTY_PATH,
            TexturePortabilityIssueStage.LEXICAL,
        )
    if lexical.contains_nul:
        add(
            TexturePortabilityIssueCode.NUL_CHARACTER,
            TexturePortabilityIssueStage.LEXICAL,
        )
    if lexical.is_absolute:
        add(
            TexturePortabilityIssueCode.ABSOLUTE_PATH,
            TexturePortabilityIssueStage.LEXICAL,
        )
    elif lexical.is_drive_qualified or lexical.is_rooted:
        add(
            TexturePortabilityIssueCode.ROOTED_PATH,
            TexturePortabilityIssueStage.LEXICAL,
        )
    if lexical.contains_parent_reference:
        add(
            TexturePortabilityIssueCode.PARENT_REFERENCE,
            TexturePortabilityIssueStage.LEXICAL,
        )

    if filesystem.resolution_failed:
        add(
            TexturePortabilityIssueCode.FILESYSTEM_UNRESOLVED,
            TexturePortabilityIssueStage.FILESYSTEM,
        )
    if filesystem.outside_model_directory is True:
        add(
            TexturePortabilityIssueCode.OUTSIDE_MODEL_DIRECTORY,
            TexturePortabilityIssueStage.FILESYSTEM,
        )
    if filesystem.exists is False:
        add(
            TexturePortabilityIssueCode.MISSING_FILE,
            TexturePortabilityIssueStage.FILESYSTEM,
        )
    elif filesystem.exists is True and filesystem.is_file is False:
        add(
            TexturePortabilityIssueCode.NOT_A_FILE,
            TexturePortabilityIssueStage.FILESYSTEM,
        )

    return tuple(issues)


def _is_portable(
    lexical: TexturePathLexicalAnalysis,
    filesystem: TextureFilesystemEvidence,
) -> bool:
    return (
        lexical.is_plain_relative
        and filesystem.outside_model_directory is False
        and not filesystem.resolution_failed
    )


def _portable_candidate(
    *,
    lexical: TexturePathLexicalAnalysis,
    filesystem: TextureFilesystemEvidence,
    portable: bool,
) -> str | None:
    """Return only an existing regular model-relative candidate."""

    if not portable:
        return None
    if filesystem.exists is not True or filesystem.is_file is not True:
        return None
    return lexical.normalized_path


def analyze_texture_portability(
    model_path: str | Path,
    texture_paths: Sequence[str],
    referenced_texture_indices: Iterable[int] = (),
) -> TexturePortabilityReport:
    """Analyze declared texture paths without modifying model or texture files."""

    for texture_path in texture_paths:
        if not isinstance(texture_path, str):
            raise TypeError("Declared texture paths must be strings.")

    referenced_indices = _validate_reference_indices(
        referenced_texture_indices,
        len(texture_paths),
    )

    entries: list[TexturePortabilityEntry] = []
    for texture_index, declared_path in enumerate(texture_paths):
        lexical = analyze_texture_path(declared_path)
        filesystem = collect_texture_filesystem_evidence(
            model_path=model_path,
            lexical=lexical,
        )
        issues = _build_issues(lexical, filesystem)
        portable = _is_portable(lexical, filesystem)
        candidate_path = _portable_candidate(
            lexical=lexical,
            filesystem=filesystem,
            portable=portable,
        )
        entries.append(
            TexturePortabilityEntry(
                texture_index=texture_index,
                declared_path=declared_path,
                normalized_path=lexical.normalized_path,
                is_referenced=texture_index in referenced_indices,
                lexical=lexical,
                filesystem=filesystem,
                issues=issues,
                portable=portable,
                candidate_path=candidate_path,
            )
        )

    immutable_entries = tuple(entries)
    return TexturePortabilityReport(
        declared_texture_count=len(immutable_entries),
        referenced_texture_count=sum(entry.is_referenced for entry in immutable_entries),
        portable_texture_count=sum(entry.portable for entry in immutable_entries),
        candidate_texture_count=sum(
            entry.candidate_path is not None for entry in immutable_entries
        ),
        entries=immutable_entries,
    )
