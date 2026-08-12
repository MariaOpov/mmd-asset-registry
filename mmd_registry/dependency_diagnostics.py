"""Filesystem diagnostics for dependencies referenced by MMD model files."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Sequence

from mmd_registry.texture_path_semantics import analyze_texture_path


ISSUE_SEVERITIES = frozenset({"warning", "error"})


@dataclass(frozen=True, slots=True)
class DependencyIssue:
    """One stable, JSON-serializable dependency diagnostic finding."""

    code: str
    severity: str
    message: str

    def __post_init__(self) -> None:
        if self.severity not in ISSUE_SEVERITIES:
            raise ValueError(f"Unsupported dependency issue severity: {self.severity}")

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-serializable representation."""

        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class TextureDependencyDiagnostic:
    """Resolved filesystem state for one declared PMX texture path."""

    texture_index: int
    raw_path: str
    normalized_path: str
    resolved_path: str | None
    is_referenced: bool
    is_absolute: bool
    is_portable: bool
    contains_parent_reference: bool
    outside_model_directory: bool | None
    exists: bool | None
    is_file: bool | None
    issues: tuple[DependencyIssue, ...]

    @property
    def status(self) -> str:
        """Return the highest severity for this dependency."""

        if any(issue.severity == "error" for issue in self.issues):
            return "error"
        if self.issues:
            return "warning"
        return "ok"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "texture_index": self.texture_index,
            "raw_path": self.raw_path,
            "normalized_path": self.normalized_path,
            "resolved_path": self.resolved_path,
            "is_referenced": self.is_referenced,
            "is_absolute": self.is_absolute,
            "is_portable": self.is_portable,
            "contains_parent_reference": self.contains_parent_reference,
            "outside_model_directory": self.outside_model_directory,
            "exists": self.exists,
            "is_file": self.is_file,
            "status": self.status,
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class TextureDependencyDiagnostics:
    """Aggregate diagnostics for all texture paths declared by one model."""

    model_path: str
    model_directory: str
    declared_texture_count: int
    referenced_texture_count: int
    unreferenced_texture_count: int
    existing_file_count: int
    missing_file_count: int
    unresolved_path_count: int
    absolute_path_count: int
    outside_model_directory_count: int
    portable_path_count: int
    non_portable_path_count: int
    warning_count: int
    error_count: int
    dependencies: tuple[TextureDependencyDiagnostic, ...]

    @property
    def status(self) -> str:
        """Return the highest aggregate diagnostic severity."""

        if self.error_count:
            return "error"
        if self.warning_count:
            return "warning"
        return "ok"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "model_path": self.model_path,
            "model_directory": self.model_directory,
            "status": self.status,
            "declared_texture_count": self.declared_texture_count,
            "referenced_texture_count": self.referenced_texture_count,
            "unreferenced_texture_count": self.unreferenced_texture_count,
            "existing_file_count": self.existing_file_count,
            "missing_file_count": self.missing_file_count,
            "unresolved_path_count": self.unresolved_path_count,
            "absolute_path_count": self.absolute_path_count,
            "outside_model_directory_count": (self.outside_model_directory_count),
            "portable_path_count": self.portable_path_count,
            "non_portable_path_count": self.non_portable_path_count,
            "warning_count": self.warning_count,
            "error_count": self.error_count,
            "dependencies": [dependency.to_dict() for dependency in self.dependencies],
        }


def _path_text(path: Path) -> str:
    """Return stable forward-slash path text for diagnostics."""

    return path.as_posix()


def _native_candidate(
    *,
    raw_path: str,
    normalized_path: str,
    flavor: str,
    model_directory: Path,
) -> Path | None:
    """Build a native filesystem candidate when the path is resolvable."""

    if flavor == "windows":
        if os.name != "nt":
            return None
        return Path(raw_path)

    if flavor == "posix":
        if os.name == "nt":
            return None
        return Path(normalized_path)

    relative_parts = PurePosixPath(normalized_path).parts
    return model_directory.joinpath(*relative_parts)


def _is_outside_directory(
    candidate: Path,
    model_directory: Path,
) -> bool:
    """Return whether a candidate resolves outside the model directory."""

    candidate_resolved = candidate.resolve(strict=False)
    model_directory_resolved = model_directory.resolve(strict=False)

    try:
        candidate_resolved.relative_to(model_directory_resolved)
    except ValueError:
        return True

    return False


def _dependency_severity(is_referenced: bool) -> str:
    """Referenced broken dependencies are errors; unused ones are warnings."""

    return "error" if is_referenced else "warning"


def _diagnose_texture_path(
    *,
    texture_index: int,
    raw_path: str,
    is_referenced: bool,
    model_directory: Path,
) -> TextureDependencyDiagnostic:
    """Diagnose one declared texture path."""

    lexical = analyze_texture_path(raw_path)
    normalized_path = lexical.normalized_path
    is_absolute = lexical.windows_is_absolute or lexical.normalized_posix_is_absolute
    is_rooted = lexical.windows_has_root or lexical.windows_has_drive
    contains_parent_reference = lexical.contains_parent_reference

    if (
        lexical.windows_is_absolute
        or lexical.windows_has_drive
        or lexical.windows_has_root
    ):
        flavor = "windows"
    elif lexical.normalized_posix_is_absolute:
        flavor = "posix"
    else:
        flavor = "relative"

    issues: list[DependencyIssue] = []

    if raw_path == "":
        issues.append(
            DependencyIssue(
                code="empty_path",
                severity=_dependency_severity(is_referenced),
                message="The declared texture path is empty.",
            )
        )

    if is_absolute:
        issues.append(
            DependencyIssue(
                code="absolute_path",
                severity="warning",
                message=(
                    "The texture uses an absolute path and may not be "
                    "portable to another machine."
                ),
            )
        )
    elif is_rooted:
        issues.append(
            DependencyIssue(
                code="rooted_path",
                severity="warning",
                message=(
                    "The texture uses a drive-relative or rooted path "
                    "and may not be portable."
                ),
            )
        )

    candidate: Path | None = None
    resolved_path: str | None = None
    outside_model_directory: bool | None = None
    exists: bool | None = None
    is_file: bool | None = None

    if raw_path != "":
        try:
            candidate = _native_candidate(
                raw_path=raw_path,
                normalized_path=normalized_path,
                flavor=flavor,
                model_directory=model_directory,
            )

            if candidate is not None:
                resolved_candidate = candidate.resolve(strict=False)
                resolved_path = _path_text(resolved_candidate)
                outside_model_directory = _is_outside_directory(
                    candidate,
                    model_directory,
                )
                exists = resolved_candidate.exists()
                is_file = resolved_candidate.is_file() if exists else False
        except (OSError, RuntimeError, ValueError) as error:
            issues.append(
                DependencyIssue(
                    code="invalid_path",
                    severity=_dependency_severity(is_referenced),
                    message=f"The texture path cannot be resolved: {error}",
                )
            )

    if outside_model_directory:
        issues.append(
            DependencyIssue(
                code="outside_model_directory",
                severity="warning",
                message=(
                    "The texture resolves outside the directory containing the model."
                ),
            )
        )

    if exists is False:
        issues.append(
            DependencyIssue(
                code="missing_file",
                severity=_dependency_severity(is_referenced),
                message="The resolved texture file does not exist.",
            )
        )
    elif exists is True and is_file is False:
        issues.append(
            DependencyIssue(
                code="not_a_file",
                severity=_dependency_severity(is_referenced),
                message="The resolved texture path is not a regular file.",
            )
        )

    is_portable = (
        raw_path != ""
        and not is_absolute
        and not is_rooted
        and outside_model_directory is False
        and not any(issue.code == "invalid_path" for issue in issues)
    )

    return TextureDependencyDiagnostic(
        texture_index=texture_index,
        raw_path=raw_path,
        normalized_path=normalized_path,
        resolved_path=resolved_path,
        is_referenced=is_referenced,
        is_absolute=is_absolute,
        is_portable=is_portable,
        contains_parent_reference=contains_parent_reference,
        outside_model_directory=outside_model_directory,
        exists=exists,
        is_file=is_file,
        issues=tuple(issues),
    )


def _validate_reference_indices(
    indices: Iterable[int],
    texture_count: int,
) -> frozenset[int]:
    """Validate and normalize referenced texture indices."""

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


def diagnose_texture_dependencies(
    model_path: str | Path,
    texture_paths: Sequence[str],
    referenced_texture_indices: Iterable[int] = (),
) -> TextureDependencyDiagnostics:
    """Resolve and diagnose all texture paths declared by one PMX model.

    The function only inspects path metadata and filesystem state. It never
    opens, decodes, or modifies the model or texture files.
    """

    model = Path(model_path)
    model_directory = model.parent

    for texture_path in texture_paths:
        if not isinstance(texture_path, str):
            raise TypeError("Declared texture paths must be strings.")

    referenced_indices = _validate_reference_indices(
        referenced_texture_indices,
        len(texture_paths),
    )

    dependencies = tuple(
        _diagnose_texture_path(
            texture_index=index,
            raw_path=raw_path,
            is_referenced=index in referenced_indices,
            model_directory=model_directory,
        )
        for index, raw_path in enumerate(texture_paths)
    )

    issues = [issue for dependency in dependencies for issue in dependency.issues]

    return TextureDependencyDiagnostics(
        model_path=_path_text(model),
        model_directory=_path_text(model_directory),
        declared_texture_count=len(dependencies),
        referenced_texture_count=sum(
            dependency.is_referenced for dependency in dependencies
        ),
        unreferenced_texture_count=sum(
            not dependency.is_referenced for dependency in dependencies
        ),
        existing_file_count=sum(
            dependency.exists is True and dependency.is_file is True
            for dependency in dependencies
        ),
        missing_file_count=sum(
            dependency.exists is False for dependency in dependencies
        ),
        unresolved_path_count=sum(
            dependency.exists is None for dependency in dependencies
        ),
        absolute_path_count=sum(dependency.is_absolute for dependency in dependencies),
        outside_model_directory_count=sum(
            dependency.outside_model_directory is True for dependency in dependencies
        ),
        portable_path_count=sum(dependency.is_portable for dependency in dependencies),
        non_portable_path_count=sum(
            not dependency.is_portable for dependency in dependencies
        ),
        warning_count=sum(issue.severity == "warning" for issue in issues),
        error_count=sum(issue.severity == "error" for issue in issues),
        dependencies=dependencies,
    )
