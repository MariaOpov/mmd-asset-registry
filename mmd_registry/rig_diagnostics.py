"""Structured diagnostics for hierarchy-aware PMX rig semantics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Literal, Sequence, TypeAlias

from mmd_registry.bone_explorer import build_bone_views
from mmd_registry.bone_hierarchy import (
    BoneHierarchy,
    build_bone_hierarchy,
)
from mmd_registry.bone_semantic_inference import (
    expected_child_semantic_roles,
    infer_bone_semantics,
)
from mmd_registry.bone_semantic_resolver import (
    DEFAULT_BONE_SEMANTIC_RESOLVER,
    BoneSemanticResolver,
)
from mmd_registry.bone_semantics import (
    BoneSemanticResult,
    BoneSemanticRole,
    base_bone_semantic_role,
)
from mmd_registry.model_scanning import PmxBone


RigDiagnosticSeverity: TypeAlias = Literal[
    "info",
    "warning",
    "error",
]

RigDiagnosticCode: TypeAlias = Literal[
    "duplicate_bone_index",
    "invalid_parent_reference",
    "hierarchy_cycle",
    "missing_expected_role",
    "duplicate_semantic_role",
    "left_right_asymmetry",
    "ambiguous_semantic_role",
    "semantic_evidence_conflict",
    "side_conflict",
    "suspicious_parent_role",
    "missing_ik_definition",
    "unexpected_ik_definition",
    "invalid_ik_target",
    "invalid_ik_link",
    "missing_ik_chain",
    "suspicious_ik_target_role",
    "suspicious_ik_chain",
    "unclassified_bones",
]


@dataclass(frozen=True, slots=True)
class RigDiagnostic:
    """One stable, non-fatal rig diagnostic."""

    code: RigDiagnosticCode
    severity: RigDiagnosticSeverity
    bone_indices: tuple[int, ...]
    message: str
    evidence: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "code": self.code,
            "severity": self.severity,
            "bone_indices": list(self.bone_indices),
            "message": self.message,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True, slots=True)
class RigDiagnosticProfile:
    """Replaceable policy for expected and paired semantic roles."""

    name: str
    required_roles: tuple[BoneSemanticRole, ...]
    paired_roles: tuple[BoneSemanticRole, ...]
    duplicate_exempt_roles: tuple[BoneSemanticRole, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "name": self.name,
            "required_roles": list(self.required_roles),
            "paired_roles": list(self.paired_roles),
            "duplicate_exempt_roles": list(self.duplicate_exempt_roles),
        }


@dataclass(frozen=True, slots=True)
class RigDiagnosticReport:
    """Deterministic aggregate diagnostics for one PMX rig."""

    profile_name: str
    bone_count: int
    issues: tuple[RigDiagnostic, ...]

    @property
    def status(self) -> Literal["ok", "warning", "error"]:
        """Return the highest actionable diagnostic status."""

        if any(issue.severity == "error" for issue in self.issues):
            return "error"

        if any(issue.severity == "warning" for issue in self.issues):
            return "warning"

        return "ok"

    @property
    def severity_counts(self) -> dict[RigDiagnosticSeverity, int]:
        """Return stable counts for every severity tier."""

        return {
            severity: sum(issue.severity == severity for issue in self.issues)
            for severity in (
                "info",
                "warning",
                "error",
            )
        }

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "status": self.status,
            "profile_name": self.profile_name,
            "bone_count": self.bone_count,
            "issue_count": len(self.issues),
            "severity_counts": self.severity_counts,
            "issues": [issue.to_dict() for issue in self.issues],
        }


DEFAULT_RIG_DIAGNOSTIC_PROFILE: Final[RigDiagnosticProfile] = RigDiagnosticProfile(
    name="mmd-standard-v1",
    required_roles=(
        "center",
        "lower_body",
        "upper_body",
        "neck",
        "head",
    ),
    paired_roles=(
        "eye",
        "shoulder",
        "arm",
        "elbow",
        "wrist",
        "thigh",
        "knee",
        "ankle",
        "toe",
        "leg_ik",
        "toe_ik",
    ),
    duplicate_exempt_roles=("finger",),
)

_STRICT_PARENT_ROLES: Final[frozenset[BoneSemanticRole]] = frozenset(
    {
        "neck",
        "head",
        "shoulder",
        "arm",
        "elbow",
        "wrist",
        "thigh",
        "knee",
        "ankle",
        "leg_ik_parent",
    }
)

_ACTIVE_IK_ROLES: Final[frozenset[BoneSemanticRole]] = frozenset(
    {
        "leg_ik",
        "toe_ik",
    }
)

_EXPECTED_IK_TARGET_ROLE: Final[dict[BoneSemanticRole, BoneSemanticRole]] = {
    "leg_ik": "ankle",
    "toe_ik": "toe",
}

_EXPECTED_IK_LINK_ROLE: Final[dict[BoneSemanticRole, BoneSemanticRole]] = {
    "leg_ik": "knee",
    "toe_ik": "ankle",
}

_SEMANTIC_CONFLICT_EVIDENCE: Final[tuple[str, ...]] = (
    "alias_conflict",
    "naming_conflict",
    "category_conflict",
)


def _hierarchy_issues(
    hierarchy: BoneHierarchy,
) -> tuple[RigDiagnostic, ...]:
    """Convert safe hierarchy issues into rig diagnostics."""

    code_by_hierarchy_issue: dict[
        str,
        tuple[RigDiagnosticCode, RigDiagnosticSeverity],
    ] = {
        "duplicate_index": (
            "duplicate_bone_index",
            "error",
        ),
        "invalid_parent": (
            "invalid_parent_reference",
            "warning",
        ),
        "cycle": (
            "hierarchy_cycle",
            "error",
        ),
    }
    diagnostics: list[RigDiagnostic] = []

    for issue in hierarchy.issues:
        mapped = code_by_hierarchy_issue.get(issue.code)

        if mapped is None:
            continue

        code, severity = mapped
        diagnostics.append(
            RigDiagnostic(
                code=code,
                severity=severity,
                bone_indices=issue.bone_indices,
                message=issue.message,
                evidence=(f"hierarchy_issue={issue.code}",),
            )
        )

    return tuple(diagnostics)


def _semantic_conflict_issues(
    semantics: Sequence[BoneSemanticResult],
) -> tuple[RigDiagnostic, ...]:
    """Report ambiguous names, convention conflicts, and side conflicts."""

    diagnostics: list[RigDiagnostic] = []

    for result in semantics:
        conflicts = tuple(
            code for code in _SEMANTIC_CONFLICT_EVIDENCE if code in result.evidence
        )

        if conflicts:
            diagnostic_code: RigDiagnosticCode = (
                "ambiguous_semantic_role"
                if result.role == "unknown"
                else "semantic_evidence_conflict"
            )
            diagnostics.append(
                RigDiagnostic(
                    code=diagnostic_code,
                    severity="warning",
                    bone_indices=(result.index,),
                    message=(
                        f"Bone {result.index} has conflicting semantic "
                        "name evidence and was not resolved confidently."
                    ),
                    evidence=tuple(f"semantic_evidence={code}" for code in conflicts),
                )
            )

        if "side_conflict" in result.evidence:
            diagnostics.append(
                RigDiagnostic(
                    code="side_conflict",
                    severity="warning",
                    bone_indices=(result.index,),
                    message=(
                        f"Bone {result.index} contains conflicting left/right evidence."
                    ),
                    evidence=(
                        f"resolved_role={result.role}",
                        "semantic_evidence=side_conflict",
                    ),
                )
            )

    return tuple(diagnostics)


def _missing_role_issues(
    semantics: Sequence[BoneSemanticResult],
    profile: RigDiagnosticProfile,
) -> tuple[RigDiagnostic, ...]:
    """Report core roles absent from the resolved rig."""

    present_roles = {
        base_bone_semantic_role(result.role)
        for result in semantics
        if result.role != "unknown"
    }

    return tuple(
        RigDiagnostic(
            code="missing_expected_role",
            severity="warning",
            bone_indices=(),
            message=f"Expected semantic role '{role}' was not found.",
            evidence=(f"expected_role={role}",),
        )
        for role in profile.required_roles
        if base_bone_semantic_role(role) not in present_roles
    )


def _duplicate_role_issues(
    semantics: Sequence[BoneSemanticResult],
    profile: RigDiagnosticProfile,
) -> tuple[RigDiagnostic, ...]:
    """Report duplicate non-repeatable roles for the same resolved side."""

    exempt_roles = {
        base_bone_semantic_role(role) for role in profile.duplicate_exempt_roles
    }
    grouped: dict[tuple[BoneSemanticRole, str], list[int]] = {}

    for result in semantics:
        base_role = base_bone_semantic_role(result.role)

        if (
            result.role == "unknown"
            or base_role in exempt_roles
            or result.category in {"helper", "physics"}
            or result.side == "none"
        ):
            continue

        grouped.setdefault(
            (base_role, result.side),
            [],
        ).append(result.index)

    diagnostics: list[RigDiagnostic] = []

    for (role, side), indices in sorted(grouped.items()):
        if len(indices) < 2:
            continue

        diagnostics.append(
            RigDiagnostic(
                code="duplicate_semantic_role",
                severity="warning",
                bone_indices=tuple(indices),
                message=(
                    f"Semantic role '{role}' on side '{side}' was resolved "
                    f"for {len(indices)} bones."
                ),
                evidence=(
                    f"role={role}",
                    f"side={side}",
                    f"count={len(indices)}",
                ),
            )
        )

    return tuple(diagnostics)


def _asymmetry_issues(
    semantics: Sequence[BoneSemanticResult],
    profile: RigDiagnosticProfile,
) -> tuple[RigDiagnostic, ...]:
    """Report unequal left/right counts only for roles that are present."""

    diagnostics: list[RigDiagnostic] = []

    for configured_role in profile.paired_roles:
        role = base_bone_semantic_role(configured_role)
        left = tuple(
            result.index
            for result in semantics
            if base_bone_semantic_role(result.role) == role
            and result.side == "left"
            and result.category not in {"helper", "physics"}
        )
        right = tuple(
            result.index
            for result in semantics
            if base_bone_semantic_role(result.role) == role
            and result.side == "right"
            and result.category not in {"helper", "physics"}
        )

        if not left and not right:
            continue

        if len(left) == len(right):
            continue

        diagnostics.append(
            RigDiagnostic(
                code="left_right_asymmetry",
                severity="warning",
                bone_indices=(*left, *right),
                message=(
                    f"Semantic role '{role}' has {len(left)} left and "
                    f"{len(right)} right bone(s)."
                ),
                evidence=(
                    f"role={role}",
                    f"left_count={len(left)}",
                    f"right_count={len(right)}",
                ),
            )
        )

    return tuple(diagnostics)


def _parent_role_issues(
    hierarchy: BoneHierarchy,
    semantics: Sequence[BoneSemanticResult],
) -> tuple[RigDiagnostic, ...]:
    """Report suspicious direct relationships for strict semantic chains."""

    results_by_index = {result.index: result for result in semantics}
    diagnostics: list[RigDiagnostic] = []

    for node in hierarchy.nodes:
        parent = results_by_index.get(node.bone.index)

        if parent is None or parent.role == "unknown":
            continue

        parent_role = base_bone_semantic_role(parent.role)

        if parent_role not in _STRICT_PARENT_ROLES or parent.confidence not in {
            "medium",
            "high",
        }:
            continue

        expected_children = expected_child_semantic_roles(parent_role)

        for child_index in node.child_indices:
            child = results_by_index.get(child_index)

            if (
                child is None
                or child.role == "unknown"
                or child.category in {"helper", "physics"}
                or child.confidence not in {"medium", "high"}
            ):
                continue

            child_role = base_bone_semantic_role(child.role)

            if child_role == parent_role or child_role in expected_children:
                continue

            diagnostics.append(
                RigDiagnostic(
                    code="suspicious_parent_role",
                    severity="warning",
                    bone_indices=(parent.index, child.index),
                    message=(
                        f"Bone {child.index} with role '{child_role}' has "
                        f"unexpected parent role '{parent_role}'."
                    ),
                    evidence=(
                        f"parent_role={parent_role}",
                        f"child_role={child_role}",
                    ),
                )
            )

    return tuple(diagnostics)


def _known_base_role_for_diagnostics(
    result: BoneSemanticResult | None,
) -> BoneSemanticRole | None:
    """Return one known base role for diagnostic comparisons."""

    if result is None or result.role == "unknown":
        return None

    return base_bone_semantic_role(result.role)


def _ik_issues(
    bones: Sequence[PmxBone],
    semantics: Sequence[BoneSemanticResult],
) -> tuple[RigDiagnostic, ...]:
    """Validate semantic IK roles, targets, and link chains safely."""

    results_by_index = {result.index: result for result in semantics}
    diagnostics: list[RigDiagnostic] = []
    bone_count = len(bones)

    for bone_index, bone in enumerate(bones):
        result = results_by_index.get(bone_index)
        role = base_bone_semantic_role(result.role) if result is not None else "unknown"
        ik = bone.ik

        if role in _ACTIVE_IK_ROLES and ik is None:
            diagnostics.append(
                RigDiagnostic(
                    code="missing_ik_definition",
                    severity="warning",
                    bone_indices=(bone_index,),
                    message=(
                        f"Bone {bone_index} resolves as '{role}' but has no "
                        "IK definition."
                    ),
                    evidence=(f"resolved_role={role}",),
                )
            )
            continue

        if ik is None:
            continue

        if role not in _ACTIVE_IK_ROLES and role != "unknown":
            diagnostics.append(
                RigDiagnostic(
                    code="unexpected_ik_definition",
                    severity="warning",
                    bone_indices=(bone_index,),
                    message=(
                        f"Bone {bone_index} has an IK definition but resolves "
                        f"as non-IK role '{role}'."
                    ),
                    evidence=(f"resolved_role={role}",),
                )
            )

        target_is_valid = 0 <= ik.target_bone_index < bone_count

        if not target_is_valid:
            diagnostics.append(
                RigDiagnostic(
                    code="invalid_ik_target",
                    severity="error",
                    bone_indices=(bone_index,),
                    message=(
                        f"Bone {bone_index} references invalid IK target "
                        f"{ik.target_bone_index}."
                    ),
                    evidence=(f"target_index={ik.target_bone_index}",),
                )
            )

        if not ik.links:
            diagnostics.append(
                RigDiagnostic(
                    code="missing_ik_chain",
                    severity="warning",
                    bone_indices=(bone_index,),
                    message=f"Bone {bone_index} has an empty IK link chain.",
                    evidence=("ik_link_count=0",),
                )
            )

        valid_link_indices: list[int] = []

        for link in ik.links:
            if 0 <= link.bone_index < bone_count:
                valid_link_indices.append(link.bone_index)
                continue

            diagnostics.append(
                RigDiagnostic(
                    code="invalid_ik_link",
                    severity="error",
                    bone_indices=(bone_index,),
                    message=(
                        f"Bone {bone_index} references invalid IK link "
                        f"{link.bone_index}."
                    ),
                    evidence=(f"link_index={link.bone_index}",),
                )
            )

        expected_target_role = _EXPECTED_IK_TARGET_ROLE.get(role)

        if target_is_valid and expected_target_role is not None:
            target = results_by_index.get(ik.target_bone_index)
            target_role = _known_base_role_for_diagnostics(target)

            if target_role is not None and target_role != expected_target_role:
                diagnostics.append(
                    RigDiagnostic(
                        code="suspicious_ik_target_role",
                        severity="warning",
                        bone_indices=(bone_index, ik.target_bone_index),
                        message=(
                            f"Bone {bone_index} expects IK target role "
                            f"'{expected_target_role}' but targets "
                            f"'{target_role}'."
                        ),
                        evidence=(
                            f"expected_target_role={expected_target_role}",
                            f"actual_target_role={target_role}",
                        ),
                    )
                )

        expected_link_role = _EXPECTED_IK_LINK_ROLE.get(role)

        if expected_link_role is not None and valid_link_indices:
            link_roles = {
                resolved_role
                for link_index in valid_link_indices
                if (
                    resolved_role := _known_base_role_for_diagnostics(
                        results_by_index.get(link_index)
                    )
                )
                is not None
            }

            if link_roles and expected_link_role not in link_roles:
                diagnostics.append(
                    RigDiagnostic(
                        code="suspicious_ik_chain",
                        severity="warning",
                        bone_indices=(bone_index, *valid_link_indices),
                        message=(
                            f"Bone {bone_index} IK links do not include "
                            f"expected role '{expected_link_role}'."
                        ),
                        evidence=(
                            f"expected_link_role={expected_link_role}",
                            "actual_link_roles=" + ",".join(sorted(link_roles)),
                        ),
                    )
                )

    return tuple(diagnostics)


def _unclassified_issue(
    semantics: Sequence[BoneSemanticResult],
) -> tuple[RigDiagnostic, ...]:
    """Group unresolved bones into one bounded informational issue."""

    indices = tuple(result.index for result in semantics if result.role == "unknown")

    if not indices:
        return ()

    return (
        RigDiagnostic(
            code="unclassified_bones",
            severity="info",
            bone_indices=indices,
            message=f"{len(indices)} bone(s) remain semantically unclassified.",
            evidence=(f"unclassified_count={len(indices)}",),
        ),
    )


def diagnose_rig(
    bones: Sequence[PmxBone],
    *,
    resolver: BoneSemanticResolver = DEFAULT_BONE_SEMANTIC_RESOLVER,
    profile: RigDiagnosticProfile = DEFAULT_RIG_DIAGNOSTIC_PROFILE,
) -> RigDiagnosticReport:
    """Run structured rig diagnostics without modifying PMX records."""

    source_bones = tuple(bones)
    semantics = infer_bone_semantics(
        source_bones,
        resolver=resolver,
    )
    hierarchy = build_bone_hierarchy(build_bone_views(source_bones))
    issues = (
        *_hierarchy_issues(hierarchy),
        *_semantic_conflict_issues(semantics),
        *_missing_role_issues(semantics, profile),
        *_duplicate_role_issues(semantics, profile),
        *_asymmetry_issues(semantics, profile),
        *_parent_role_issues(hierarchy, semantics),
        *_ik_issues(source_bones, semantics),
        *_unclassified_issue(semantics),
    )

    return RigDiagnosticReport(
        profile_name=profile.name,
        bone_count=len(source_bones),
        issues=issues,
    )
