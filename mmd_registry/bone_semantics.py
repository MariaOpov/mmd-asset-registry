"""Typed semantic vocabulary for read-only PMX rig analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Iterable, Literal, TypeAlias

from mmd_registry.model_scanning import PmxBone


BoneSemanticRole: TypeAlias = Literal[
    "unknown",
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
    "shoulder_deform",
    "arm_deform",
    "elbow_deform",
    "wrist_deform",
    "finger_deform",
    "thigh_deform",
    "knee_deform",
    "ankle_deform",
    "toe_deform",
    "shoulder_helper",
    "arm_helper",
    "elbow_helper",
    "wrist_helper",
    "finger_helper",
    "thigh_helper",
    "knee_helper",
    "ankle_helper",
    "toe_helper",
]

BoneSide: TypeAlias = Literal[
    "left",
    "right",
    "center",
    "none",
]

BoneCategory: TypeAlias = Literal[
    "control",
    "deform",
    "helper",
    "ik",
    "physics",
    "unknown",
]

BoneConfidence: TypeAlias = Literal[
    "high",
    "medium",
    "low",
    "unknown",
]

BoneEvidenceCode: TypeAlias = Literal[
    "local_name_alias",
    "universal_name_alias",
    "local_name_convention",
    "universal_name_convention",
    "side_marker",
    "bone_flags",
    "ik_definition",
    "parent_role",
    "child_role",
    "hierarchy_side",
    "physics_binding",
    "alias_conflict",
    "naming_conflict",
    "category_conflict",
    "side_conflict",
]


@dataclass(frozen=True, slots=True)
class BoneSemanticAlias:
    """One declarative alias for a canonical bone semantic role."""

    alias: str
    role: BoneSemanticRole
    category: BoneCategory
    side: BoneSide | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "alias": self.alias,
            "role": self.role,
            "category": self.category,
            "side": self.side,
        }


@dataclass(frozen=True, slots=True)
class BoneSemanticProfile:
    """A replaceable collection of declarative bone aliases."""

    name: str
    aliases: tuple[BoneSemanticAlias, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "name": self.name,
            "aliases": [alias.to_dict() for alias in self.aliases],
        }


@dataclass(frozen=True, slots=True)
class BoneSemanticResult:
    """One deterministic semantic classification for a PMX bone."""

    index: int
    local_name: str
    universal_name: str
    role: BoneSemanticRole
    side: BoneSide
    category: BoneCategory
    confidence: BoneConfidence
    evidence: tuple[BoneEvidenceCode, ...]
    matched_aliases: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "index": self.index,
            "local_name": self.local_name,
            "universal_name": self.universal_name,
            "role": self.role,
            "side": self.side,
            "category": self.category,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "matched_aliases": list(self.matched_aliases),
        }


_DEFORM_VARIANTS: Final[dict[BoneSemanticRole, BoneSemanticRole]] = {
    "shoulder": "shoulder_deform",
    "arm": "arm_deform",
    "elbow": "elbow_deform",
    "wrist": "wrist_deform",
    "finger": "finger_deform",
    "thigh": "thigh_deform",
    "knee": "knee_deform",
    "ankle": "ankle_deform",
    "toe": "toe_deform",
}

_HELPER_VARIANTS: Final[dict[BoneSemanticRole, BoneSemanticRole]] = {
    "shoulder": "shoulder_helper",
    "arm": "arm_helper",
    "elbow": "elbow_helper",
    "wrist": "wrist_helper",
    "finger": "finger_helper",
    "thigh": "thigh_helper",
    "knee": "knee_helper",
    "ankle": "ankle_helper",
    "toe": "toe_helper",
}

_BASE_ROLE_BY_VARIANT: Final[dict[BoneSemanticRole, BoneSemanticRole]] = {
    variant: base
    for variants in (
        _DEFORM_VARIANTS,
        _HELPER_VARIANTS,
    )
    for base, variant in variants.items()
}

_CONTROL_ROLES: Final[frozenset[BoneSemanticRole]] = frozenset(
    {
        "root",
        "view_control",
        "center",
        "groove",
    }
)

_IK_ROLES: Final[frozenset[BoneSemanticRole]] = frozenset(
    {
        "leg_ik_parent",
        "leg_ik",
        "toe_ik",
    }
)

_EVIDENCE_ORDER: Final[tuple[BoneEvidenceCode, ...]] = (
    "local_name_alias",
    "universal_name_alias",
    "local_name_convention",
    "universal_name_convention",
    "side_marker",
    "bone_flags",
    "ik_definition",
    "parent_role",
    "child_role",
    "hierarchy_side",
    "physics_binding",
    "alias_conflict",
    "naming_conflict",
    "category_conflict",
    "side_conflict",
)


def base_bone_semantic_role(
    role: BoneSemanticRole,
) -> BoneSemanticRole:
    """Return the canonical base role for a deform/helper variant."""

    return _BASE_ROLE_BY_VARIANT.get(role, role)


def specialize_bone_semantic_role(
    role: BoneSemanticRole,
    category: BoneCategory,
) -> BoneSemanticRole:
    """Apply a supported deform/helper variant to one base role."""

    base_role = base_bone_semantic_role(role)

    if category == "deform":
        return _DEFORM_VARIANTS.get(base_role, base_role)

    if category == "helper":
        return _HELPER_VARIANTS.get(base_role, base_role)

    return role


def default_bone_category_for_role(
    role: BoneSemanticRole,
) -> BoneCategory:
    """Return the default category implied by one semantic role."""

    if role == "unknown":
        return "unknown"

    if role in _CONTROL_ROLES:
        return "control"

    if role in _IK_ROLES:
        return "ik"

    if role in _HELPER_VARIANTS.values():
        return "helper"

    return "deform"


def order_bone_evidence(
    evidence: Iterable[BoneEvidenceCode],
) -> tuple[BoneEvidenceCode, ...]:
    """Deduplicate evidence and return it in one stable public order."""

    evidence_set = set(evidence)

    return tuple(code for code in _EVIDENCE_ORDER if code in evidence_set)


def _alias_group(
    role: BoneSemanticRole,
    category: BoneCategory,
    aliases: tuple[str, ...],
    *,
    side: BoneSide | None = None,
) -> tuple[BoneSemanticAlias, ...]:
    """Build one compact immutable alias group."""

    return tuple(
        BoneSemanticAlias(
            alias=alias,
            role=role,
            category=category,
            side=side,
        )
        for alias in aliases
    )


DEFAULT_BONE_SEMANTIC_PROFILE: Final[BoneSemanticProfile] = BoneSemanticProfile(
    name="mmd-standard-v1",
    aliases=(
        *_alias_group(
            "root",
            "control",
            (
                "全ての親",
                "root",
                "mother bone",
                "master",
            ),
            side="center",
        ),
        *_alias_group(
            "view_control",
            "control",
            (
                "操作中心",
                "view center",
                "control center",
            ),
            side="center",
        ),
        *_alias_group(
            "center",
            "control",
            (
                "センター",
                "center",
            ),
            side="center",
        ),
        *_alias_group(
            "groove",
            "control",
            (
                "グルーブ",
                "groove",
            ),
            side="center",
        ),
        *_alias_group(
            "waist",
            "deform",
            (
                "腰",
                "waist",
                "hip",
            ),
            side="center",
        ),
        *_alias_group(
            "lower_body",
            "deform",
            (
                "下半身",
                "lower body",
            ),
            side="center",
        ),
        *_alias_group(
            "upper_body_2",
            "deform",
            (
                "上半身2",
                "upper body 2",
                "upper body2",
            ),
            side="center",
        ),
        *_alias_group(
            "upper_body",
            "deform",
            (
                "上半身",
                "upper body",
                "spine",
                "chest",
            ),
            side="center",
        ),
        *_alias_group(
            "neck",
            "deform",
            (
                "首",
                "neck",
            ),
            side="center",
        ),
        *_alias_group(
            "head",
            "deform",
            (
                "頭",
                "head",
            ),
            side="center",
        ),
        *_alias_group(
            "eye",
            "deform",
            (
                "目",
                "eye",
                "eyes",
            ),
        ),
        *_alias_group(
            "shoulder",
            "deform",
            (
                "肩",
                "shoulder",
                "clavicle",
            ),
        ),
        *_alias_group(
            "arm",
            "deform",
            (
                "腕",
                "arm",
                "upper arm",
            ),
        ),
        *_alias_group(
            "elbow",
            "deform",
            (
                "ひじ",
                "肘",
                "elbow",
                "forearm",
                "lower arm",
            ),
        ),
        *_alias_group(
            "wrist",
            "deform",
            (
                "手首",
                "wrist",
                "hand",
            ),
        ),
        *_alias_group(
            "finger",
            "deform",
            (
                "指",
                "finger",
                "thumb",
                "index finger",
                "middle finger",
                "ring finger",
                "little finger",
                "pinky",
            ),
        ),
        *_alias_group(
            "thigh",
            "deform",
            (
                "足",
                "thigh",
                "leg",
                "upper leg",
            ),
        ),
        *_alias_group(
            "knee",
            "deform",
            (
                "ひざ",
                "膝",
                "knee",
                "calf",
                "lower leg",
            ),
        ),
        *_alias_group(
            "ankle",
            "deform",
            (
                "足首",
                "ankle",
                "foot",
            ),
        ),
        *_alias_group(
            "toe",
            "deform",
            (
                "つま先",
                "toe",
            ),
        ),
        *_alias_group(
            "leg_ik_parent",
            "ik",
            (
                "足ik親",
                "leg ik parent",
            ),
        ),
        *_alias_group(
            "leg_ik",
            "ik",
            (
                "足ik",
                "leg ik",
            ),
        ),
        *_alias_group(
            "toe_ik",
            "ik",
            (
                "つま先ik",
                "toe ik",
            ),
        ),
    ),
)


def build_unknown_bone_semantic(
    index: int,
    bone: PmxBone,
) -> BoneSemanticResult:
    """Build an explicit unknown result without modifying scanner data."""

    return BoneSemanticResult(
        index=index,
        local_name=bone.local_name,
        universal_name=bone.universal_name,
        role="unknown",
        side="none",
        category="unknown",
        confidence="unknown",
        evidence=(),
        matched_aliases=(),
    )
