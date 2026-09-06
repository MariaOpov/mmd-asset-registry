"""Public deterministic confidence and ambiguity assessments for Smart Parts.

This module is a read-only presentation projection over the private v0.9.5.4
candidate/association confidence authority. It performs no independent lexical
matching, fuzzy matching, probability inference, mutation, transaction planning,
preview, apply, writing, remapping, or CLI work.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import mmd_registry._smart_part_confidence as _private
import mmd_registry.smart_part_detection as _detection
from mmd_registry.smart_part_detection import SmartPartDetectionEntry
from mmd_registry.smart_part_explainability import SmartPartEvidenceExplanation
from mmd_registry.smart_parts import SmartPartKind


class SmartPartConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    AMBIGUOUS = "ambiguous"


def _evidence_sort_key(
    item: SmartPartEvidenceExplanation,
) -> tuple[
    str,
    int,
    str,
    str,
    str,
    str,
    str,
    str,
    tuple[tuple[str, str], ...],
]:
    return (
        item.evidence.source_kind.value,
        item.evidence.source_index,
        item.evidence.reason,
        item.source_field,
        item.source_value,
        item.comparison_value,
        item.normalized_value,
        item.matched_alias,
        item.derivation,
    )


@dataclass(frozen=True, slots=True)
class SmartPartConfidenceCandidate:
    kind: SmartPartKind
    evidence: tuple[SmartPartEvidenceExplanation, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.kind, SmartPartKind):
            raise TypeError("kind must be a SmartPartKind value.")
        if type(self.evidence) is not tuple:
            raise TypeError("evidence must be a tuple.")
        if not self.evidence:
            raise ValueError("evidence must be non-empty.")
        if not all(
            isinstance(item, SmartPartEvidenceExplanation)
            for item in self.evidence
        ):
            raise TypeError(
                "evidence must contain only SmartPartEvidenceExplanation values."
            )
        if len(self.evidence) != len(set(self.evidence)):
            raise ValueError("evidence must be exact-duplicate-free.")
        if self.evidence != tuple(sorted(self.evidence, key=_evidence_sort_key)):
            raise ValueError("evidence must use shared candidate-trace canonical order.")
        if any(
            not item.evidence.reason.endswith(f":{self.kind.value}")
            for item in self.evidence
        ):
            raise ValueError("candidate evidence must belong to candidate kind.")


@dataclass(frozen=True, slots=True)
class SmartPartConfidenceAssessment:
    confidence: SmartPartConfidence
    candidates: tuple[SmartPartConfidenceCandidate, ...]
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.confidence, SmartPartConfidence):
            raise TypeError("confidence must be a SmartPartConfidence value.")
        if type(self.candidates) is not tuple or not self.candidates:
            raise ValueError("candidates must be a non-empty tuple.")
        if not all(
            isinstance(candidate, SmartPartConfidenceCandidate)
            for candidate in self.candidates
        ):
            raise TypeError(
                "candidates must contain only SmartPartConfidenceCandidate values."
            )
        kinds = tuple(candidate.kind for candidate in self.candidates)
        canonical_kinds = tuple(kind for kind in SmartPartKind if kind in set(kinds))
        if kinds != canonical_kinds:
            raise ValueError(
                "candidate kinds must be unique and use SmartPartKind order."
            )
        if type(self.reason) is not str:
            raise TypeError("reason must be a string.")

        if self.confidence is SmartPartConfidence.AMBIGUOUS:
            if len(self.candidates) < 2:
                raise ValueError("AMBIGUOUS requires at least two candidates.")
            if self.reason != "same_source_exact_conflict":
                raise ValueError("AMBIGUOUS must use the frozen machine reason.")
            return

        if len(self.candidates) != 1:
            raise ValueError("resolved assessments must contain exactly one candidate.")

        expected_reason = {
            SmartPartConfidence.HIGH:
                "multiple_independent_direct_exact_sources",
            SmartPartConfidence.MEDIUM:
                "single_direct_exact_source",
            SmartPartConfidence.LOW:
                "derived_texture_only",
        }[self.confidence]
        if self.reason != expected_reason:
            raise ValueError("resolved confidence must use its frozen machine reason.")


def _explanation_from_candidate_trace(
    trace: object,
) -> SmartPartEvidenceExplanation:
    return SmartPartEvidenceExplanation(
        evidence=trace.evidence,  # type: ignore[attr-defined]
        source_field=trace.source_field,  # type: ignore[attr-defined]
        source_value=trace.source_value,  # type: ignore[attr-defined]
        comparison_value=trace.comparison_value,  # type: ignore[attr-defined]
        normalized_value=trace.normalized_value,  # type: ignore[attr-defined]
        matched_alias=trace.matched_alias,  # type: ignore[attr-defined]
        match_rule=trace.match_rule,  # type: ignore[attr-defined]
        derivation=trace.derivation,  # type: ignore[attr-defined]
    )


def _candidate_from_traces(
    kind: SmartPartKind,
    traces: tuple[object, ...],
) -> SmartPartConfidenceCandidate:
    canonical = _private._deduplicate_candidate_traces(  # type: ignore[arg-type]
        tuple(sorted(traces, key=_detection._candidate_trace_sort_key))
    )
    return SmartPartConfidenceCandidate(
        kind=kind,
        evidence=tuple(
            _explanation_from_candidate_trace(trace)
            for trace in canonical
        ),
    )


def _resolved_candidate(
    kind: SmartPartKind,
    associations: tuple[object, ...],
) -> SmartPartConfidenceCandidate:
    traces = tuple(
        trace
        for association in associations
        if len(association.candidates) == 1  # type: ignore[attr-defined]
        and association.candidates[0] is kind  # type: ignore[attr-defined]
        for trace in association.traces  # type: ignore[attr-defined]
    )
    return _candidate_from_traces(kind, traces)


def assess_smart_parts(
    entries: tuple[SmartPartDetectionEntry, ...],
) -> tuple[SmartPartConfidenceAssessment, ...]:
    """Return deterministic resolved and ambiguous Smart Part assessments."""

    associations = _private._collect_smart_part_candidate_associations(entries)
    resolved = _private._derive_smart_part_resolved_assessments(entries)
    ambiguous = _private._collect_smart_part_ambiguity_assessments(entries)

    resolved_assessments = tuple(
        SmartPartConfidenceAssessment(
            confidence=SmartPartConfidence(item.confidence.value),
            candidates=(
                _resolved_candidate(item.support.kind, associations),
            ),
            reason=item.reason,
        )
        for item in resolved
    )

    ambiguous_assessments = tuple(
        SmartPartConfidenceAssessment(
            confidence=SmartPartConfidence.AMBIGUOUS,
            candidates=tuple(
                _candidate_from_traces(candidate.kind, candidate.traces)
                for candidate in item.candidates
            ),
            reason=item.reason,
        )
        for item in ambiguous
    )

    return resolved_assessments + ambiguous_assessments


__all__ = (
    "SmartPartConfidence",
    "SmartPartConfidenceCandidate",
    "SmartPartConfidenceAssessment",
    "assess_smart_parts",
)
