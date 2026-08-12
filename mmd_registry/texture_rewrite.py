"""Deterministic safe rewrite proposals for PMX texture declarations."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable, Sequence

from mmd_registry.pmx.editing.json_loader import parse_pmx_edit_plan_json
from mmd_registry.pmx.editing.operations import SetTexturePath
from mmd_registry.pmx.editing.path_policy import validate_portable_texture_path
from mmd_registry.pmx.editing.plan import PmxEditPlan
from mmd_registry.texture_path_semantics import (
    TexturePathKind,
    analyze_texture_path,
)
from mmd_registry.texture_portability import (
    TexturePortabilityEntry,
    TexturePortabilityReport,
    analyze_texture_portability,
)


class TextureRewriteDisposition(StrEnum):
    """Stable outcomes for one declared texture path."""

    NO_CHANGE = "no_change"
    SAFE_REWRITE = "safe_rewrite"
    BLOCKED = "blocked"


class TextureRewriteCandidateSource(StrEnum):
    """Source used to derive one safe candidate path."""

    LEXICAL = "lexical"
    FILESYSTEM = "filesystem"


@dataclass(frozen=True, slots=True)
class TextureRewriteProposal:
    """One immutable rewrite proposal for a declared texture entry."""

    texture_index: int
    declared_path: str
    is_referenced: bool
    disposition: TextureRewriteDisposition
    candidate_path: str | None
    candidate_source: TextureRewriteCandidateSource | None
    source_issue_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if isinstance(self.texture_index, bool) or not isinstance(
            self.texture_index, int
        ):
            raise TypeError("texture_index must be an integer.")
        if self.texture_index < 0:
            raise ValueError("texture_index cannot be negative.")
        if type(self.declared_path) is not str:
            raise TypeError("declared_path must be a string.")
        if type(self.is_referenced) is not bool:
            raise TypeError("is_referenced must be a boolean.")
        if not isinstance(self.disposition, TextureRewriteDisposition):
            raise TypeError("disposition must be a TextureRewriteDisposition.")
        if type(self.source_issue_codes) is not tuple or any(
            type(code) is not str or not code for code in self.source_issue_codes
        ):
            raise TypeError("source_issue_codes must contain non-empty strings.")

        if self.disposition is TextureRewriteDisposition.SAFE_REWRITE:
            if type(self.candidate_path) is not str or not self.candidate_path:
                raise ValueError("safe rewrites require a candidate path.")
            if not isinstance(
                self.candidate_source,
                TextureRewriteCandidateSource,
            ):
                raise ValueError("safe rewrites require a candidate source.")
            validate_portable_texture_path(self.candidate_path)
            if self.candidate_path == self.declared_path:
                raise ValueError("safe rewrite candidate must change the declaration.")
            return

        if self.candidate_path is not None or self.candidate_source is not None:
            raise ValueError(
                "non-rewrite proposals cannot expose a candidate path or source."
            )

    def to_dict(self) -> dict[str, Any]:
        """Return a deterministic JSON-ready representation."""

        return {
            "texture_index": self.texture_index,
            "declared_path": self.declared_path,
            "is_referenced": self.is_referenced,
            "disposition": self.disposition.value,
            "candidate_path": self.candidate_path,
            "candidate_source": (
                self.candidate_source.value
                if self.candidate_source is not None
                else None
            ),
            "source_issue_codes": list(self.source_issue_codes),
        }


@dataclass(frozen=True, slots=True)
class TextureRewriteReport:
    """Aggregate rewrite proposals in texture-index order."""

    declared_texture_count: int
    safe_rewrite_count: int
    no_change_count: int
    blocked_count: int
    proposals: tuple[TextureRewriteProposal, ...]

    def __post_init__(self) -> None:
        if type(self.proposals) is not tuple or not all(
            isinstance(proposal, TextureRewriteProposal)
            for proposal in self.proposals
        ):
            raise TypeError("proposals must contain TextureRewriteProposal values.")
        expected_indices = tuple(range(len(self.proposals)))
        actual_indices = tuple(
            proposal.texture_index for proposal in self.proposals
        )
        if actual_indices != expected_indices:
            raise ValueError("rewrite proposals must be in exact texture-index order.")

        expected_counts = (
            len(self.proposals),
            sum(
                proposal.disposition is TextureRewriteDisposition.SAFE_REWRITE
                for proposal in self.proposals
            ),
            sum(
                proposal.disposition is TextureRewriteDisposition.NO_CHANGE
                for proposal in self.proposals
            ),
            sum(
                proposal.disposition is TextureRewriteDisposition.BLOCKED
                for proposal in self.proposals
            ),
        )
        actual_counts = (
            self.declared_texture_count,
            self.safe_rewrite_count,
            self.no_change_count,
            self.blocked_count,
        )
        if actual_counts != expected_counts:
            raise ValueError("rewrite report counts must match proposals.")

    def to_dict(self) -> dict[str, Any]:
        """Return a deterministic JSON-ready report."""

        return {
            "declared_texture_count": self.declared_texture_count,
            "safe_rewrite_count": self.safe_rewrite_count,
            "no_change_count": self.no_change_count,
            "blocked_count": self.blocked_count,
            "proposals": [proposal.to_dict() for proposal in self.proposals],
        }


@dataclass(frozen=True, slots=True)
class TextureRewriteEditPlan:
    """Existing edit-plan bridge for safe texture rewrite proposals."""

    rewrite_report: TextureRewriteReport
    plan: PmxEditPlan | None
    json_text: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.rewrite_report, TextureRewriteReport):
            raise TypeError("rewrite_report must be a TextureRewriteReport.")

        rewrite_count = self.rewrite_report.safe_rewrite_count
        if rewrite_count == 0:
            if self.plan is not None or self.json_text is not None:
                raise ValueError("empty rewrite reports cannot expose an edit plan.")
            return

        if not isinstance(self.plan, PmxEditPlan):
            raise ValueError("safe rewrites require a PmxEditPlan.")
        if type(self.json_text) is not str or not self.json_text:
            raise ValueError("safe rewrites require strict JSON plan text.")
        if len(self.plan.operations) != rewrite_count:
            raise ValueError("edit-plan operation count must match safe rewrites.")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready bridge summary without reparsing plan text."""

        return {
            "rewrite_report": self.rewrite_report.to_dict(),
            "has_edit_plan": self.plan is not None,
            "edit_plan": self.plan.to_dict() if self.plan is not None else None,
        }


def _collapse_relative_components(normalized_path: str) -> str | None:
    """Collapse '.' and bounded '..' components without filesystem access."""

    analysis = analyze_texture_path(normalized_path)
    if analysis.is_empty or analysis.is_absolute or analysis.is_drive_qualified:
        return None
    if analysis.windows_has_root or analysis.contains_nul:
        return None

    components: list[str] = []
    for component in normalized_path.split("/"):
        if component in ("", "."):
            continue
        if component == "..":
            if not components:
                return None
            components.pop()
            continue
        components.append(component)

    if not components:
        return None
    candidate = "/".join(components)
    candidate_analysis = analyze_texture_path(candidate)
    if not candidate_analysis.is_plain_relative:
        return None
    return candidate


def _candidate_from_relative_entry(
    entry: TexturePortabilityEntry,
) -> tuple[str, TextureRewriteCandidateSource] | None:
    """Derive a lexical candidate while requiring positive file evidence."""

    filesystem = entry.filesystem
    if (
        filesystem.resolution_supported is not True
        or filesystem.resolution_failed
        or filesystem.outside_model_directory is not False
        or filesystem.exists is not True
        or filesystem.is_file is not True
    ):
        return None

    candidate = _collapse_relative_components(entry.normalized_path)
    if candidate is None:
        return None
    validate_portable_texture_path(candidate)
    return candidate, TextureRewriteCandidateSource.LEXICAL


def _candidate_from_absolute_entry(
    *,
    model_path: str | Path,
    entry: TexturePortabilityEntry,
) -> tuple[str, TextureRewriteCandidateSource] | None:
    """Relativize a native absolute path only from resolved file evidence."""

    filesystem = entry.filesystem
    if (
        not entry.lexical.is_absolute
        or filesystem.resolution_supported is not True
        or filesystem.resolution_failed
        or filesystem.outside_model_directory is not False
        or filesystem.exists is not True
        or filesystem.is_file is not True
        or filesystem.resolved_path is None
    ):
        return None

    model_directory = Path(model_path).parent.resolve(strict=False)
    resolved_texture = Path(filesystem.resolved_path)

    try:
        relative = resolved_texture.relative_to(model_directory)
    except ValueError:
        return None

    candidate = relative.as_posix()
    if not candidate or candidate == ".":
        return None

    validate_portable_texture_path(candidate)
    return candidate, TextureRewriteCandidateSource.FILESYSTEM


def _derive_safe_candidate(
    *,
    model_path: str | Path,
    entry: TexturePortabilityEntry,
) -> tuple[str, TextureRewriteCandidateSource] | None:
    """Return one deterministic candidate or None when evidence is insufficient."""

    if entry.lexical.kind is TexturePathKind.RELATIVE:
        return _candidate_from_relative_entry(entry)
    if entry.lexical.is_absolute:
        return _candidate_from_absolute_entry(
            model_path=model_path,
            entry=entry,
        )
    return None


def build_texture_rewrite_report(
    *,
    model_path: str | Path,
    portability_report: TexturePortabilityReport,
) -> TextureRewriteReport:
    """Build safe proposals without fuzzy matching or filesystem mutation."""

    if not isinstance(portability_report, TexturePortabilityReport):
        raise TypeError("portability_report must be a TexturePortabilityReport.")

    proposals: list[TextureRewriteProposal] = []
    for entry in portability_report.entries:
        candidate = _derive_safe_candidate(
            model_path=model_path,
            entry=entry,
        )

        if candidate is None:
            disposition = TextureRewriteDisposition.BLOCKED
            candidate_path = None
            candidate_source = None
        else:
            candidate_path, candidate_source = candidate
            if candidate_path == entry.declared_path:
                disposition = TextureRewriteDisposition.NO_CHANGE
                candidate_path = None
                candidate_source = None
            else:
                disposition = TextureRewriteDisposition.SAFE_REWRITE

        proposals.append(
            TextureRewriteProposal(
                texture_index=entry.texture_index,
                declared_path=entry.declared_path,
                is_referenced=entry.is_referenced,
                disposition=disposition,
                candidate_path=candidate_path,
                candidate_source=candidate_source,
                source_issue_codes=entry.issue_codes,
            )
        )

    immutable = tuple(proposals)
    return TextureRewriteReport(
        declared_texture_count=len(immutable),
        safe_rewrite_count=sum(
            proposal.disposition is TextureRewriteDisposition.SAFE_REWRITE
            for proposal in immutable
        ),
        no_change_count=sum(
            proposal.disposition is TextureRewriteDisposition.NO_CHANGE
            for proposal in immutable
        ),
        blocked_count=sum(
            proposal.disposition is TextureRewriteDisposition.BLOCKED
            for proposal in immutable
        ),
        proposals=immutable,
    )


def analyze_texture_rewrites(
    model_path: str | Path,
    texture_paths: Sequence[str],
    referenced_texture_indices: Iterable[int] = (),
) -> TextureRewriteReport:
    """Analyze portability and derive rewrite proposals in one read-only flow."""

    portability_report = analyze_texture_portability(
        model_path=model_path,
        texture_paths=texture_paths,
        referenced_texture_indices=referenced_texture_indices,
    )
    return build_texture_rewrite_report(
        model_path=model_path,
        portability_report=portability_report,
    )


def build_texture_rewrite_edit_plan(
    rewrite_report: TextureRewriteReport,
    *,
    expected_source_sha256: str | None = None,
) -> TextureRewriteEditPlan:
    """Bridge safe proposals into existing strict set_texture_path operations."""

    if not isinstance(rewrite_report, TextureRewriteReport):
        raise TypeError("rewrite_report must be a TextureRewriteReport.")

    safe_proposals = tuple(
        proposal
        for proposal in rewrite_report.proposals
        if proposal.disposition is TextureRewriteDisposition.SAFE_REWRITE
    )
    if not safe_proposals:
        return TextureRewriteEditPlan(
            rewrite_report=rewrite_report,
            plan=None,
            json_text=None,
        )

    operations: list[SetTexturePath] = []
    for proposal in safe_proposals:
        assert proposal.candidate_path is not None
        validate_portable_texture_path(proposal.candidate_path)
        operations.append(
            SetTexturePath(
                texture_index=proposal.texture_index,
                path=proposal.candidate_path,
            )
        )

    candidate_plan = PmxEditPlan(
        operations=tuple(operations),
        expected_source_sha256=expected_source_sha256,
    )
    json_text = (
        json.dumps(
            candidate_plan.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )
        + "\n"
    )

    # A portability-generated plan is successful only if the existing strict
    # loader accepts the exact serialized document.
    strict_loaded_plan = parse_pmx_edit_plan_json(json_text)
    if strict_loaded_plan != candidate_plan:
        raise RuntimeError(
            "strict edit-plan loader changed the generated rewrite plan."
        )

    return TextureRewriteEditPlan(
        rewrite_report=rewrite_report,
        plan=strict_loaded_plan,
        json_text=json_text,
    )
