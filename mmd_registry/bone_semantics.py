"""Typed semantic vocabulary for read-only PMX rig analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Literal, TypeAlias

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
    "physics_binding",
    "alias_conflict",
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


DEFAULT_BONE_SEMANTIC_PROFILE: Final[BoneSemanticProfile] = BoneSemanticProfile(
    name="mmd-minimal-v1",
    aliases=(
        BoneSemanticAlias(
            alias="全ての親",
            role="root",
            category="control",
            side="center",
        ),
        BoneSemanticAlias(
            alias="root",
            role="root",
            category="control",
            side="center",
        ),
        BoneSemanticAlias(
            alias="操作中心",
            role="view_control",
            category="control",
            side="center",
        ),
        BoneSemanticAlias(
            alias="view center",
            role="view_control",
            category="control",
            side="center",
        ),
        BoneSemanticAlias(
            alias="センター",
            role="center",
            category="control",
            side="center",
        ),
        BoneSemanticAlias(
            alias="center",
            role="center",
            category="control",
            side="center",
        ),
        BoneSemanticAlias(
            alias="グルーブ",
            role="groove",
            category="control",
            side="center",
        ),
        BoneSemanticAlias(
            alias="groove",
            role="groove",
            category="control",
            side="center",
        ),
        BoneSemanticAlias(
            alias="ひざ",
            role="knee",
            category="deform",
        ),
        BoneSemanticAlias(
            alias="knee",
            role="knee",
            category="deform",
        ),
        BoneSemanticAlias(
            alias="calf",
            role="knee",
            category="deform",
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
