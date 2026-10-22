"""v0.9.5.11 immutable, read-only, source-bound Smart Morph descriptors.

This private module carries no PMX reader, writer, planning or apply authority.
All semantic candidate traces originate in the released Smart Part detector.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from mmd_registry._smart_part_confidence import _candidate_trace_identity_key
from mmd_registry.smart_part_detection import (
    _SmartPartCandidateTrace,
    _candidate_trace_sort_key,
)
from mmd_registry.smart_parts import SmartPartEvidence, SmartPartEvidenceKind, SmartPartKind


class SmartMorphCapabilityStatus(str, Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    BLOCKED = "blocked"


_STATUS_REASON: dict[str, SmartMorphCapabilityStatus] = {
    "source_evidence_mismatch": SmartMorphCapabilityStatus.BLOCKED,
    "same_source_exact_conflict": SmartMorphCapabilityStatus.BLOCKED,
    "multiple_exact_morph_candidates": SmartMorphCapabilityStatus.BLOCKED,
    "no_exact_morph_evidence": SmartMorphCapabilityStatus.UNSUPPORTED,
    "morph_type_out_of_scope": SmartMorphCapabilityStatus.UNSUPPORTED,
    "empty_morph_offsets": SmartMorphCapabilityStatus.UNSUPPORTED,
    "exact_morph_evidence": SmartMorphCapabilityStatus.SUPPORTED,
}


@dataclass(frozen=True, slots=True)
class SmartMorphIdentity:
    source_index: int
    local_name: str
    universal_name: str
    panel: int
    panel_name: str
    morph_type: int
    morph_type_name: str
    offset_count: int

    def __post_init__(self) -> None:
        if type(self.source_index) is not int or self.source_index < 0:
            raise ValueError("source_index must be a nonnegative integer.")
        if type(self.panel) is not int or self.panel not in range(5):
            raise ValueError("panel must be a PMX panel number 0..4.")
        if type(self.morph_type) is not int or self.morph_type not in range(11):
            raise ValueError("morph_type must be a PMX morph code 0..10.")
        if type(self.offset_count) is not int or self.offset_count < 0:
            raise ValueError("offset_count must be a nonnegative integer.")
        for field in ("local_name", "universal_name", "panel_name", "morph_type_name"):
            if type(getattr(self, field)) is not str:
                raise TypeError(f"{field} must be a string.")


@dataclass(frozen=True, slots=True)
class SmartMorphCandidateEvidence:
    """An exact pre-filter source trace, including a competing kind if blocked."""

    kind: SmartPartKind
    evidence: SmartPartEvidence
    source_field: str
    source_value: str
    comparison_value: str
    normalized_value: str
    matched_alias: str
    match_rule: str
    derivation: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.kind, SmartPartKind):
            raise TypeError("kind must be SmartPartKind.")
        if not isinstance(self.evidence, SmartPartEvidence):
            raise TypeError("evidence must be SmartPartEvidence.")
        if self.evidence.source_kind is not SmartPartEvidenceKind.MORPH:
            raise ValueError("only direct MORPH traces may be carried.")
        if self.source_field not in ("local_name", "universal_name"):
            raise ValueError("source_field must be a morph name field.")
        for field in ("source_value", "comparison_value", "normalized_value", "matched_alias"):
            if type(getattr(self, field)) is not str:
                raise TypeError(f"{field} must be a string.")
        if self.match_rule != "exact_alias":
            raise ValueError("match_rule must come from exact alias detection.")
        if type(self.derivation) is not tuple or any(
            type(item) is not tuple or len(item) != 2 or
            any(type(component) is not str for component in item)
            for item in self.derivation
        ):
            raise TypeError("derivation must be a tuple of two-string tuples.")


def _canonical_candidate_traces(
    traces: tuple[_SmartPartCandidateTrace, ...],
) -> tuple[_SmartPartCandidateTrace, ...]:
    """Deduplicate by frozen full trace identity and sort by detector authority."""

    if type(traces) is not tuple:
        raise TypeError("traces must be an exact tuple.")
    if any(not isinstance(t, _SmartPartCandidateTrace) for t in traces):
        raise TypeError("traces must be detector candidate trace records.")
    identities: dict[tuple[object, ...], _SmartPartCandidateTrace] = {}
    for trace in traces:
        identities.setdefault(_candidate_trace_identity_key(trace), trace)
    return tuple(sorted(identities.values(), key=_candidate_trace_sort_key))


def _project_traces(
    traces: tuple[_SmartPartCandidateTrace, ...],
) -> tuple[SmartMorphCandidateEvidence, ...]:
    return tuple(
        SmartMorphCandidateEvidence(
            kind=t.kind,
            evidence=t.evidence,
            source_field=t.source_field,
            source_value=t.source_value,
            comparison_value=t.comparison_value,
            normalized_value=t.normalized_value,
            matched_alias=t.matched_alias,
            match_rule=t.match_rule,
            derivation=t.derivation,
        )
        for t in _canonical_candidate_traces(traces)
    )


@dataclass(frozen=True, slots=True)
class SmartMorphCapability:
    part_kind: SmartPartKind
    capability_kind: str
    status: SmartMorphCapabilityStatus
    reason: str
    candidate_indices: tuple[int, ...]
    evidence: tuple[SmartMorphCandidateEvidence, ...]

    def __post_init__(self) -> None:
        required_kind = {"smile": SmartPartKind.FACE, "blink": SmartPartKind.EYES}
        if self.capability_kind not in required_kind:
            raise ValueError("only frozen smile and blink slots are supported.")
        if self.part_kind is not required_kind[self.capability_kind]:
            raise ValueError("slot and SmartPartKind do not match.")
        if not isinstance(self.status, SmartMorphCapabilityStatus):
            raise TypeError("status must be a SmartMorphCapabilityStatus.")
        if _STATUS_REASON.get(self.reason) is not self.status:
            raise ValueError("status and canonical reason do not agree.")
        if type(self.candidate_indices) is not tuple or any(
            type(x) is not int or x < 0 for x in self.candidate_indices
        ):
            raise TypeError("candidate_indices must be nonnegative integer tuple.")
        if self.candidate_indices != tuple(sorted(set(self.candidate_indices))):
            raise ValueError("candidate_indices must be sorted and unique.")
        if type(self.evidence) is not tuple or any(
            not isinstance(e, SmartMorphCandidateEvidence) for e in self.evidence
        ):
            raise TypeError("evidence must be a tuple of exact candidate explanations.")
        if self.reason == "no_exact_morph_evidence" and (self.candidate_indices or self.evidence):
            raise ValueError("no-evidence status cannot carry candidates.")
        if self.status is SmartMorphCapabilityStatus.SUPPORTED and len(self.candidate_indices) != 1:
            raise ValueError("supported capability must have one source index.")

    @property
    def supported(self) -> bool:
        """Descriptive structural support; NOT authorization to edit or animate."""
        return self.status is SmartMorphCapabilityStatus.SUPPORTED

    @property
    def blocked(self) -> bool:
        return self.status is SmartMorphCapabilityStatus.BLOCKED


@dataclass(frozen=True, slots=True)
class SmartMorphInspection:
    source_sha256: str
    morphs: tuple[SmartMorphIdentity, ...]
    capabilities: tuple[SmartMorphCapability, ...]

    def __post_init__(self) -> None:
        if type(self.source_sha256) is not str or len(self.source_sha256) != 64 or any(
            ch not in "0123456789abcdef" for ch in self.source_sha256
        ):
            raise ValueError("source_sha256 must be 64 lowercase hex characters.")
        if type(self.morphs) is not tuple or any(not isinstance(m, SmartMorphIdentity) for m in self.morphs):
            raise TypeError("morphs must be immutable morph identities.")
        if tuple(m.source_index for m in self.morphs) != tuple(range(len(self.morphs))):
            raise ValueError("morph inventory must have consecutive ascending source indices.")
        if type(self.capabilities) is not tuple or len(self.capabilities) != 2:
            raise ValueError("capabilities must contain exactly two slots.")
        if tuple(c.capability_kind for c in self.capabilities) != ("smile", "blink"):
            raise ValueError("capability slot order must be smile, blink.")
