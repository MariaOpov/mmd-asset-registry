"""Immutable read-only domain primitives for Smart PMX semantic parts.

This module defines representation only. It performs no semantic detection,
source loading, PMX mutation, transaction-plan generation, preview, or apply.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SmartPartKind(str, Enum):
    """Initial semantic model-part vocabulary for Smart PMX authoring."""

    EYES = "eyes"
    HAIR = "hair"
    FACE = "face"
    SKIN = "skin"
    CHEST = "chest"
    UPPER_BODY = "upper_body"
    LOWER_BODY = "lower_body"
    ARMS = "arms"
    HANDS = "hands"
    LEGS = "legs"
    FEET = "feet"
    CLOTHING = "clothing"
    SHOES = "shoes"
    ACCESSORIES = "accessories"
    MATERIALS = "materials"


class SmartPartEvidenceKind(str, Enum):
    """PMX source-entity families that may support Smart Part evidence."""

    VERTEX = "vertex"
    TEXTURE = "texture"
    MATERIAL = "material"
    BONE = "bone"
    MORPH = "morph"
    RIGID_BODY = "rigid_body"


@dataclass(frozen=True, slots=True)
class SmartPartEvidence:
    """One exact source-bound semantic reason supporting a Smart Part."""

    source_kind: SmartPartEvidenceKind
    source_index: int
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.source_kind, SmartPartEvidenceKind):
            raise TypeError("source_kind must be a SmartPartEvidenceKind value.")
        if type(self.source_index) is not int:
            raise TypeError("source_index must be an integer.")
        if self.source_index < 0:
            raise ValueError("source_index must be nonnegative.")
        if type(self.reason) is not str:
            raise TypeError("reason must be a string.")
        if not self.reason.strip():
            raise ValueError("reason must contain non-whitespace text.")


def _smart_part_evidence_sort_key(
    evidence: SmartPartEvidence,
) -> tuple[str, int, str]:
    return (
        evidence.source_kind.value,
        evidence.source_index,
        evidence.reason,
    )


@dataclass(frozen=True, slots=True)
class SmartPart:
    """One semantic model part supported by deterministic PMX source evidence."""

    kind: SmartPartKind
    evidence: tuple[SmartPartEvidence, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.kind, SmartPartKind):
            raise TypeError("kind must be a SmartPartKind value.")
        if type(self.evidence) is not tuple:
            raise TypeError("evidence must be a tuple.")
        if not self.evidence:
            raise ValueError("evidence must contain at least one item.")
        if not all(isinstance(item, SmartPartEvidence) for item in self.evidence):
            raise TypeError("evidence must contain only SmartPartEvidence values.")
        if len(set(self.evidence)) != len(self.evidence):
            raise ValueError("evidence must not contain exact duplicates.")

        canonical_evidence = tuple(
            sorted(self.evidence, key=_smart_part_evidence_sort_key)
        )
        object.__setattr__(self, "evidence", canonical_evidence)


__all__ = (
    "SmartPartKind",
    "SmartPartEvidenceKind",
    "SmartPartEvidence",
    "SmartPart",
)
