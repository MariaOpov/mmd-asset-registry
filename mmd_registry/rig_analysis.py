"""Complete read-only PMX rig analysis and bone-map models."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Final, Iterable, Literal, Sequence

from mmd_registry.bone_semantic_inference import infer_bone_semantics
from mmd_registry.bone_semantic_resolver import (
    DEFAULT_BONE_SEMANTIC_RESOLVER,
    BoneSemanticResolver,
)
from mmd_registry.bone_semantics import (
    BoneCategory,
    BoneConfidence,
    BoneEvidenceCode,
    BoneSemanticResult,
    BoneSemanticRole,
    BoneSide,
    base_bone_semantic_role,
)
from mmd_registry.model_scanning import PmxBone
from mmd_registry.rig_diagnostics import (
    DEFAULT_RIG_DIAGNOSTIC_PROFILE,
    RigDiagnosticProfile,
    RigDiagnosticReport,
    diagnose_resolved_rig,
)


RIG_ANALYSIS_SCHEMA_VERSION: Final[str] = "1.0"
BONE_MAP_SCHEMA_VERSION: Final[str] = "1.0"

_CATEGORY_ORDER: Final[tuple[str, ...]] = (
    "control",
    "deform",
    "helper",
    "ik",
    "physics",
    "unknown",
)

_SIDE_ORDER: Final[tuple[str, ...]] = (
    "left",
    "right",
    "center",
    "none",
)

_CONFIDENCE_ORDER: Final[tuple[str, ...]] = (
    "high",
    "medium",
    "low",
    "unknown",
)


def canonical_bone_map_key(
    role: BoneSemanticRole,
    side: BoneSide,
) -> str | None:
    """Return one stable base-role key for downstream bone lookup."""

    base_role = base_bone_semantic_role(role)

    if base_role == "unknown":
        return None

    if side in {"left", "right"}:
        return f"{side}_{base_role}"

    return base_role


@dataclass(frozen=True, slots=True)
class BoneMapEntry:
    """One traceable resolved bone in an exported semantic map."""

    key: str
    index: int
    local_name: str
    universal_name: str
    role: BoneSemanticRole
    base_role: BoneSemanticRole
    side: BoneSide
    category: BoneCategory
    confidence: BoneConfidence
    evidence: tuple[BoneEvidenceCode, ...]
    matched_aliases: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "key": self.key,
            "index": self.index,
            "local_name": self.local_name,
            "universal_name": self.universal_name,
            "role": self.role,
            "base_role": self.base_role,
            "side": self.side,
            "category": self.category,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "matched_aliases": list(self.matched_aliases),
        }


@dataclass(frozen=True, slots=True)
class BoneMap:
    """A duplicate-safe semantic bone map for downstream tools."""

    schema_version: str
    profile_name: str
    entries: tuple[BoneMapEntry, ...]
    unmapped_indices: tuple[int, ...]

    @property
    def bone_count(self) -> int:
        """Return the total mapped and unmapped bone count."""

        return len(self.entries) + len(self.unmapped_indices)

    @property
    def mapped_count(self) -> int:
        """Return the number of resolved bone records."""

        return len(self.entries)

    @property
    def unmapped_count(self) -> int:
        """Return the number of unresolved bone records."""

        return len(self.unmapped_indices)

    @property
    def role_index(self) -> dict[str, list[int]]:
        """Return sorted canonical keys mapped to all matching indices."""

        grouped: dict[str, list[int]] = {}

        for entry in self.entries:
            grouped.setdefault(entry.key, []).append(entry.index)

        return {key: grouped[key] for key in sorted(grouped)}

    def to_dict(self) -> dict[str, Any]:
        """Return a stable, JSON-serializable exported map."""

        return {
            "schema_version": self.schema_version,
            "profile_name": self.profile_name,
            "bone_count": self.bone_count,
            "mapped_count": self.mapped_count,
            "unmapped_count": self.unmapped_count,
            "roles": self.role_index,
            "entries": [entry.to_dict() for entry in self.entries],
            "unmapped_indices": list(self.unmapped_indices),
        }


@dataclass(frozen=True, slots=True)
class RigAnalysisSummary:
    """Immutable aggregate counts for one complete rig analysis."""

    bone_count: int
    resolved_bone_count: int
    unresolved_bone_count: int
    mapped_role_count: int
    diagnostic_count: int
    info_count: int
    warning_count: int
    error_count: int
    role_counts: tuple[tuple[str, int], ...]
    category_counts: tuple[tuple[str, int], ...]
    side_counts: tuple[tuple[str, int], ...]
    confidence_counts: tuple[tuple[str, int], ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "bone_count": self.bone_count,
            "resolved_bone_count": self.resolved_bone_count,
            "unresolved_bone_count": self.unresolved_bone_count,
            "mapped_role_count": self.mapped_role_count,
            "diagnostic_count": self.diagnostic_count,
            "severity_counts": {
                "info": self.info_count,
                "warning": self.warning_count,
                "error": self.error_count,
            },
            "role_counts": dict(self.role_counts),
            "category_counts": dict(self.category_counts),
            "side_counts": dict(self.side_counts),
            "confidence_counts": dict(self.confidence_counts),
        }


@dataclass(frozen=True, slots=True)
class RigAnalysisReport:
    """A stable complete semantic and diagnostic rig report."""

    schema_version: str
    semantic_profile_name: str
    diagnostic_profile_name: str
    summary: RigAnalysisSummary
    semantics: tuple[BoneSemanticResult, ...]
    diagnostics: RigDiagnosticReport
    bone_map: BoneMap

    @property
    def status(self) -> Literal["ok", "warning", "error"]:
        """Return the highest actionable diagnostic status."""

        return self.diagnostics.status

    def to_dict(self) -> dict[str, Any]:
        """Return the stable complete JSON report schema."""

        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "semantic_profile_name": self.semantic_profile_name,
            "diagnostic_profile_name": self.diagnostic_profile_name,
            "summary": self.summary.to_dict(),
            "bones": [result.to_dict() for result in self.semantics],
            "diagnostics": self.diagnostics.to_dict(),
            "bone_map": self.bone_map.to_dict(),
        }


def _count_values(
    values: Iterable[str],
    *,
    ordered_keys: Sequence[str] | None = None,
) -> tuple[tuple[str, int], ...]:
    """Count strings with explicit or alphabetical stable ordering."""

    counts = Counter(values)
    keys = tuple(ordered_keys) if ordered_keys is not None else tuple(sorted(counts))

    return tuple((key, counts[key]) for key in keys)


def build_bone_map(
    semantics: Sequence[BoneSemanticResult],
    *,
    profile_name: str,
) -> BoneMap:
    """Build a standalone, duplicate-safe map from semantic results."""

    entries: list[BoneMapEntry] = []
    unmapped_indices: list[int] = []

    for result in semantics:
        key = canonical_bone_map_key(
            result.role,
            result.side,
        )

        if key is None:
            unmapped_indices.append(result.index)
            continue

        entries.append(
            BoneMapEntry(
                key=key,
                index=result.index,
                local_name=result.local_name,
                universal_name=result.universal_name,
                role=result.role,
                base_role=base_bone_semantic_role(result.role),
                side=result.side,
                category=result.category,
                confidence=result.confidence,
                evidence=result.evidence,
                matched_aliases=result.matched_aliases,
            )
        )

    return BoneMap(
        schema_version=BONE_MAP_SCHEMA_VERSION,
        profile_name=profile_name,
        entries=tuple(entries),
        unmapped_indices=tuple(unmapped_indices),
    )


def build_rig_analysis_summary(
    semantics: Sequence[BoneSemanticResult],
    diagnostics: RigDiagnosticReport,
    bone_map: BoneMap,
) -> RigAnalysisSummary:
    """Build immutable stable counts for one complete analysis."""

    source_semantics = tuple(semantics)
    severity_counts = diagnostics.severity_counts

    return RigAnalysisSummary(
        bone_count=len(source_semantics),
        resolved_bone_count=bone_map.mapped_count,
        unresolved_bone_count=bone_map.unmapped_count,
        mapped_role_count=len(bone_map.role_index),
        diagnostic_count=len(diagnostics.issues),
        info_count=severity_counts["info"],
        warning_count=severity_counts["warning"],
        error_count=severity_counts["error"],
        role_counts=_count_values(result.role for result in source_semantics),
        category_counts=_count_values(
            (result.category for result in source_semantics),
            ordered_keys=_CATEGORY_ORDER,
        ),
        side_counts=_count_values(
            (result.side for result in source_semantics),
            ordered_keys=_SIDE_ORDER,
        ),
        confidence_counts=_count_values(
            (result.confidence for result in source_semantics),
            ordered_keys=_CONFIDENCE_ORDER,
        ),
    )


def analyze_rig(
    bones: Sequence[PmxBone],
    *,
    resolver: BoneSemanticResolver = DEFAULT_BONE_SEMANTIC_RESOLVER,
    diagnostic_profile: RigDiagnosticProfile = (DEFAULT_RIG_DIAGNOSTIC_PROFILE),
) -> RigAnalysisReport:
    """Build a complete read-only semantic, diagnostic, and map report."""

    source_bones = tuple(bones)
    semantics = infer_bone_semantics(
        source_bones,
        resolver=resolver,
    )
    diagnostics = diagnose_resolved_rig(
        source_bones,
        semantics,
        profile=diagnostic_profile,
    )
    bone_map = build_bone_map(
        semantics,
        profile_name=resolver.profile.name,
    )
    summary = build_rig_analysis_summary(
        semantics,
        diagnostics,
        bone_map,
    )

    return RigAnalysisReport(
        schema_version=RIG_ANALYSIS_SCHEMA_VERSION,
        semantic_profile_name=resolver.profile.name,
        diagnostic_profile_name=diagnostic_profile.name,
        summary=summary,
        semantics=semantics,
        diagnostics=diagnostics,
        bone_map=bone_map,
    )
