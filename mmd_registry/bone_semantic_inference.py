"""Hierarchy-aware refinement for resolved PMX bone semantics."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Final, Sequence

from mmd_registry.bone_explorer import build_bone_views
from mmd_registry.bone_hierarchy import (
    BoneHierarchy,
    build_bone_hierarchy,
)
from mmd_registry.bone_semantic_resolver import (
    DEFAULT_BONE_SEMANTIC_RESOLVER,
    BoneSemanticResolver,
    resolve_bone_semantics,
)
from mmd_registry.bone_semantics import (
    BoneCategory,
    BoneConfidence,
    BoneEvidenceCode,
    BoneSemanticResult,
    BoneSemanticRole,
    BoneSide,
    base_bone_semantic_role,
    default_bone_category_for_role,
    order_bone_evidence,
    specialize_bone_semantic_role,
)
from mmd_registry.model_scanning import PmxBone


_EXPECTED_CHILD_ROLES: Final[dict[BoneSemanticRole, frozenset[BoneSemanticRole]]] = {
    "root": frozenset({"view_control", "center"}),
    "view_control": frozenset({"center"}),
    "center": frozenset({"groove", "lower_body", "upper_body"}),
    "groove": frozenset({"lower_body", "upper_body"}),
    "waist": frozenset({"lower_body", "upper_body", "thigh"}),
    "lower_body": frozenset({"upper_body", "upper_body_2", "thigh"}),
    "upper_body": frozenset({"upper_body_2", "neck", "shoulder"}),
    "upper_body_2": frozenset({"neck", "shoulder"}),
    "neck": frozenset({"head"}),
    "head": frozenset({"eye"}),
    "shoulder": frozenset({"arm"}),
    "arm": frozenset({"elbow"}),
    "elbow": frozenset({"wrist"}),
    "wrist": frozenset({"finger"}),
    "thigh": frozenset({"knee"}),
    "knee": frozenset({"ankle"}),
    "ankle": frozenset({"toe"}),
    "leg_ik_parent": frozenset({"leg_ik"}),
}

_CENTER_BASE_ROLES: Final[frozenset[BoneSemanticRole]] = frozenset(
    {
        "root",
        "view_control",
        "center",
        "groove",
        "waist",
        "lower_body",
        "upper_body",
        "upper_body_2",
        "neck",
        "head",
    }
)

_PAIRED_BASE_ROLES: Final[frozenset[BoneSemanticRole]] = frozenset(
    {
        "eye",
        "shoulder",
        "arm",
        "elbow",
        "wrist",
        "finger",
        "thigh",
        "knee",
        "ankle",
        "toe",
        "leg_ik_parent",
        "leg_ik",
        "toe_ik",
    }
)

_BLOCKING_ROLE_EVIDENCE: Final[frozenset[BoneEvidenceCode]] = frozenset(
    {
        "alias_conflict",
        "naming_conflict",
        "category_conflict",
    }
)


def _build_parent_roles_by_child() -> dict[
    BoneSemanticRole,
    frozenset[BoneSemanticRole],
]:
    """Build the deterministic reverse relation for inference."""

    parents: dict[BoneSemanticRole, set[BoneSemanticRole]] = {}

    for parent_role, child_roles in _EXPECTED_CHILD_ROLES.items():
        for child_role in child_roles:
            parents.setdefault(child_role, set()).add(parent_role)

    return {
        child_role: frozenset(parent_roles)
        for child_role, parent_roles in parents.items()
    }


_PARENT_ROLES_BY_CHILD: Final[dict[BoneSemanticRole, frozenset[BoneSemanticRole]]] = (
    _build_parent_roles_by_child()
)


@dataclass(frozen=True, slots=True)
class _InferenceCandidate:
    """One unique hierarchy candidate and its supporting directions."""

    role: BoneSemanticRole
    parent_evidence: bool
    child_evidence: bool


def _build_relationship_maps(
    hierarchy: BoneHierarchy,
) -> tuple[
    dict[int, int],
    dict[int, tuple[int, ...]],
]:
    """Build flat safe parent and child maps from the existing hierarchy."""

    parent_by_index: dict[int, int] = {}
    children_by_index: dict[int, tuple[int, ...]] = {}

    for node in hierarchy.nodes:
        bone_index = node.bone.index
        children_by_index[bone_index] = node.child_indices

        for child_index in node.child_indices:
            parent_by_index[child_index] = bone_index

    return parent_by_index, children_by_index


def _known_base_role(
    result: BoneSemanticResult | None,
) -> BoneSemanticRole | None:
    """Return one known base role or None for unresolved semantics."""

    if result is None or result.role == "unknown":
        return None

    return base_bone_semantic_role(result.role)


def _intersect_role_sets(
    role_sets: Sequence[frozenset[BoneSemanticRole]],
) -> frozenset[BoneSemanticRole] | None:
    """Intersect non-empty contextual role sets deterministically."""

    if not role_sets:
        return None

    intersection = set(role_sets[0])

    for role_set in role_sets[1:]:
        intersection.intersection_update(role_set)

    return frozenset(intersection)


def _find_inference_candidate(
    bone_index: int,
    results_by_index: dict[int, BoneSemanticResult],
    parent_by_index: dict[int, int],
    children_by_index: dict[int, tuple[int, ...]],
) -> _InferenceCandidate | None:
    """Find one unambiguous role supported by parent and/or children."""

    parent_candidates: frozenset[BoneSemanticRole] | None = None
    parent_index = parent_by_index.get(bone_index)

    if parent_index is not None:
        parent_role = _known_base_role(results_by_index.get(parent_index))

        if parent_role is not None:
            parent_candidates = _EXPECTED_CHILD_ROLES.get(parent_role)

    child_role_sets: list[frozenset[BoneSemanticRole]] = []

    for child_index in children_by_index.get(bone_index, ()):
        child_role = _known_base_role(results_by_index.get(child_index))

        if child_role is None:
            continue

        candidate_parents = _PARENT_ROLES_BY_CHILD.get(child_role)

        if candidate_parents is not None:
            child_role_sets.append(candidate_parents)

    child_candidates = _intersect_role_sets(child_role_sets)

    if parent_candidates is not None and child_candidates is not None:
        combined = parent_candidates.intersection(child_candidates)

        if len(combined) == 1:
            return _InferenceCandidate(
                role=next(iter(combined)),
                parent_evidence=True,
                child_evidence=True,
            )

        return None

    if parent_candidates is not None and len(parent_candidates) == 1:
        return _InferenceCandidate(
            role=next(iter(parent_candidates)),
            parent_evidence=True,
            child_evidence=False,
        )

    if child_candidates is not None and len(child_candidates) == 1:
        return _InferenceCandidate(
            role=next(iter(child_candidates)),
            parent_evidence=False,
            child_evidence=True,
        )

    return None


def _find_relation_support(
    bone_index: int,
    role: BoneSemanticRole,
    results_by_index: dict[int, BoneSemanticResult],
    parent_by_index: dict[int, int],
    children_by_index: dict[int, tuple[int, ...]],
) -> tuple[bool, tuple[int, ...]]:
    """Return supporting parent status and supporting child indices."""

    base_role = base_bone_semantic_role(role)
    parent_support = False
    parent_index = parent_by_index.get(bone_index)

    if parent_index is not None:
        parent_role = _known_base_role(results_by_index.get(parent_index))

        if parent_role is not None:
            parent_support = base_role in _EXPECTED_CHILD_ROLES.get(
                parent_role,
                (),
            )

    expected_children = _EXPECTED_CHILD_ROLES.get(base_role, ())
    supporting_children = tuple(
        child_index
        for child_index in children_by_index.get(bone_index, ())
        if _known_base_role(results_by_index.get(child_index)) in expected_children
    )

    return parent_support, supporting_children


def _supporting_side_candidates(
    bone_index: int,
    role: BoneSemanticRole,
    results_by_index: dict[int, BoneSemanticResult],
    parent_by_index: dict[int, int],
    supporting_children: tuple[int, ...],
    *,
    parent_support: bool,
) -> frozenset[BoneSide]:
    """Collect left/right sides only from supporting relationships."""

    sides: set[BoneSide] = set()

    if parent_support:
        parent_index = parent_by_index.get(bone_index)

        if parent_index is not None:
            parent = results_by_index.get(parent_index)

            if parent is not None and parent.side in {"left", "right"}:
                sides.add(parent.side)

    for child_index in supporting_children:
        child = results_by_index.get(child_index)

        if child is not None and child.side in {"left", "right"}:
            sides.add(child.side)

    base_role = base_bone_semantic_role(role)

    if base_role not in _PAIRED_BASE_ROLES:
        return frozenset()

    return frozenset(sides)


def _refine_side(
    result: BoneSemanticResult,
    results_by_index: dict[int, BoneSemanticResult],
    parent_by_index: dict[int, int],
    supporting_children: tuple[int, ...],
    *,
    parent_support: bool,
    evidence: set[BoneEvidenceCode],
    confidence: BoneConfidence,
) -> tuple[BoneSide, BoneConfidence]:
    """Safely inherit a side only from role-compatible relationships."""

    base_role = base_bone_semantic_role(result.role)

    if result.side == "none" and base_role in _CENTER_BASE_ROLES:
        return "center", confidence

    side_candidates = _supporting_side_candidates(
        result.index,
        result.role,
        results_by_index,
        parent_by_index,
        supporting_children,
        parent_support=parent_support,
    )

    if result.side == "none":
        if len(side_candidates) == 1:
            evidence.add("hierarchy_side")
            return next(iter(side_candidates)), confidence

        if len(side_candidates) > 1:
            evidence.add("side_conflict")
            return "none", "low"

        return "none", confidence

    if side_candidates == {result.side}:
        evidence.add("hierarchy_side")

    return result.side, confidence


def _infer_unknown_result(
    result: BoneSemanticResult,
    results_by_index: dict[int, BoneSemanticResult],
    parent_by_index: dict[int, int],
    children_by_index: dict[int, tuple[int, ...]],
) -> BoneSemanticResult:
    """Infer one clean unknown result from an unambiguous context."""

    if _BLOCKING_ROLE_EVIDENCE.intersection(result.evidence):
        return result

    candidate = _find_inference_candidate(
        result.index,
        results_by_index,
        parent_by_index,
        children_by_index,
    )

    if candidate is None:
        return result

    if result.category == "helper" and not (
        candidate.parent_evidence and candidate.child_evidence
    ):
        return result

    if result.category in {"deform", "helper"}:
        category = result.category
        role = specialize_bone_semantic_role(
            candidate.role,
            category,
        )
    else:
        category = default_bone_category_for_role(candidate.role)
        role = candidate.role
    evidence = set(result.evidence)

    if candidate.parent_evidence:
        evidence.add("parent_role")

    if candidate.child_evidence:
        evidence.add("child_role")

    confidence: BoneConfidence = (
        "medium" if candidate.parent_evidence and candidate.child_evidence else "low"
    )
    inferred = replace(
        result,
        role=role,
        category=category,
        confidence=confidence,
        evidence=order_bone_evidence(evidence),
    )
    parent_support, supporting_children = _find_relation_support(
        result.index,
        inferred.role,
        results_by_index,
        parent_by_index,
        children_by_index,
    )
    side, confidence = _refine_side(
        inferred,
        results_by_index,
        parent_by_index,
        supporting_children,
        parent_support=parent_support,
        evidence=evidence,
        confidence=inferred.confidence,
    )

    return replace(
        inferred,
        side=side,
        confidence=confidence,
        evidence=order_bone_evidence(evidence),
    )


def _refine_known_result(
    result: BoneSemanticResult,
    results_by_index: dict[int, BoneSemanticResult],
    parent_by_index: dict[int, int],
    children_by_index: dict[int, tuple[int, ...]],
) -> BoneSemanticResult:
    """Add hierarchy evidence without replacing a known role."""

    parent_support, supporting_children = _find_relation_support(
        result.index,
        result.role,
        results_by_index,
        parent_by_index,
        children_by_index,
    )
    child_support = bool(supporting_children)

    if not parent_support and not child_support:
        return result

    evidence = set(result.evidence)

    if parent_support:
        evidence.add("parent_role")

    if child_support:
        evidence.add("child_role")

    confidence = result.confidence
    has_name_evidence = bool(
        {"local_name_alias", "universal_name_alias"}.intersection(evidence)
    )
    has_blocking_evidence = bool(_BLOCKING_ROLE_EVIDENCE.intersection(evidence))

    if confidence == "medium" and has_name_evidence and not has_blocking_evidence:
        confidence = "high"
    elif (
        confidence == "low"
        and parent_support
        and child_support
        and not has_blocking_evidence
    ):
        confidence = "medium"

    refined = replace(
        result,
        confidence=confidence,
        evidence=order_bone_evidence(evidence),
    )
    side, confidence = _refine_side(
        refined,
        results_by_index,
        parent_by_index,
        supporting_children,
        parent_support=parent_support,
        evidence=evidence,
        confidence=refined.confidence,
    )

    return replace(
        refined,
        side=side,
        confidence=confidence,
        evidence=order_bone_evidence(evidence),
    )


def _apply_hierarchy_inference(
    semantics: tuple[BoneSemanticResult, ...],
    hierarchy: BoneHierarchy,
) -> tuple[BoneSemanticResult, ...]:
    """Refine semantics iteratively without recursion or source mutation."""

    parent_by_index, children_by_index = _build_relationship_maps(hierarchy)
    current = semantics

    for _ in range(max(len(current), 1)):
        results_by_index = {result.index: result for result in current}
        updated = tuple(
            (
                _infer_unknown_result(
                    result,
                    results_by_index,
                    parent_by_index,
                    children_by_index,
                )
                if result.role == "unknown"
                else _refine_known_result(
                    result,
                    results_by_index,
                    parent_by_index,
                    children_by_index,
                )
            )
            for result in current
        )

        if updated == current:
            break

        current = updated

    return current


def infer_bone_semantics(
    bones: Sequence[PmxBone],
    *,
    resolver: BoneSemanticResolver = DEFAULT_BONE_SEMANTIC_RESOLVER,
) -> tuple[BoneSemanticResult, ...]:
    """Resolve names, then refine them with a safe parent-child hierarchy."""

    source_bones = tuple(bones)
    semantics = resolve_bone_semantics(
        source_bones,
        resolver=resolver,
    )
    views = build_bone_views(source_bones)
    hierarchy = build_bone_hierarchy(views)

    return _apply_hierarchy_inference(
        semantics,
        hierarchy,
    )
