"""Private v0.9.5.4 confidence/ambiguity assessment foundation.

This module groups shared deterministic semantic candidate traces by exact PMX
source identity. It intentionally derives no HIGH/MEDIUM/LOW state yet and
exports no public API. Matching authority remains in smart_part_detection.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from mmd_registry.smart_part_detection import (
    SmartPartDetectionEntry,
    _SmartPartCandidateTrace,
    _match_smart_part_candidate_traces,
)
from mmd_registry.smart_parts import (
    SmartPartEvidenceKind,
    SmartPartKind,
)


@dataclass(frozen=True, slots=True)
class _SmartPartCandidateAssociation:
    """All exact Smart Part candidates belonging to one PMX source entity."""

    source_kind: SmartPartEvidenceKind
    source_index: int
    candidates: tuple[SmartPartKind, ...]
    traces: tuple[_SmartPartCandidateTrace, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source_kind, SmartPartEvidenceKind):
            raise TypeError("source_kind must be a SmartPartEvidenceKind value.")
        if type(self.source_index) is not int:
            raise TypeError("source_index must be an integer.")
        if self.source_index < 0:
            raise ValueError("source_index must be nonnegative.")
        if type(self.candidates) is not tuple or not self.candidates:
            raise ValueError("candidates must be a non-empty tuple.")
        if not all(isinstance(kind, SmartPartKind) for kind in self.candidates):
            raise TypeError("candidates must contain only SmartPartKind values.")
        canonical_candidates = tuple(
            kind for kind in SmartPartKind if kind in set(self.candidates)
        )
        if self.candidates != canonical_candidates:
            raise ValueError(
                "candidates must be unique and follow SmartPartKind declaration order."
            )
        if type(self.traces) is not tuple or not self.traces:
            raise ValueError("traces must be a non-empty tuple.")
        if not all(isinstance(trace, _SmartPartCandidateTrace) for trace in self.traces):
            raise TypeError("traces must contain only shared candidate traces.")
        for trace in self.traces:
            if trace.evidence.source_kind is not self.source_kind:
                raise ValueError("trace source_kind must match the association.")
            if trace.evidence.source_index != self.source_index:
                raise ValueError("trace source_index must match the association.")
            if trace.kind not in self.candidates:
                raise ValueError("trace kind must be present in candidates.")


def _association_sort_key(
    association: _SmartPartCandidateAssociation,
) -> tuple[int, int]:
    return (
        tuple(SmartPartEvidenceKind).index(association.source_kind),
        association.source_index,
    )


def _collect_smart_part_candidate_associations(
    entries: tuple[SmartPartDetectionEntry, ...],
) -> tuple[_SmartPartCandidateAssociation, ...]:
    """Group shared exact candidate traces by (source_kind, source_index)."""

    traces = _match_smart_part_candidate_traces(entries)
    grouped: dict[
        tuple[SmartPartEvidenceKind, int],
        list[_SmartPartCandidateTrace],
    ] = {}
    for trace in traces:
        key = (trace.evidence.source_kind, trace.evidence.source_index)
        grouped.setdefault(key, []).append(trace)

    associations = tuple(
        _SmartPartCandidateAssociation(
            source_kind=source_kind,
            source_index=source_index,
            candidates=tuple(
                kind
                for kind in SmartPartKind
                if any(trace.kind is kind for trace in source_traces)
            ),
            traces=_deduplicate_candidate_traces(tuple(source_traces)),
        )
        for (source_kind, source_index), source_traces in grouped.items()
    )
    return tuple(sorted(associations, key=_association_sort_key))


_SmartPartSourceIdentity = tuple[SmartPartEvidenceKind, int]

_DIRECT_NAMED_SOURCE_KINDS: tuple[SmartPartEvidenceKind, ...] = (
    SmartPartEvidenceKind.MATERIAL,
    SmartPartEvidenceKind.BONE,
    SmartPartEvidenceKind.MORPH,
)
_DERIVED_SOURCE_KINDS: tuple[SmartPartEvidenceKind, ...] = (
    SmartPartEvidenceKind.TEXTURE,
)


def _source_identity_sort_key(
    key: _SmartPartSourceIdentity,
) -> tuple[int, int]:
    source_kind, source_index = key
    return (tuple(SmartPartEvidenceKind).index(source_kind), source_index)


def _candidate_trace_identity_key(
    trace: _SmartPartCandidateTrace,
) -> tuple[object, ...]:
    if not isinstance(trace, _SmartPartCandidateTrace):
        raise TypeError("trace must be a shared candidate trace.")
    return (
        trace.kind,
        trace.evidence.source_kind,
        trace.evidence.source_index,
        trace.evidence.reason,
        trace.source_field,
        trace.source_value,
        trace.comparison_value,
        trace.normalized_value,
        trace.matched_alias,
        trace.match_rule,
        trace.derivation,
    )


def _deduplicate_candidate_traces(
    traces: tuple[_SmartPartCandidateTrace, ...],
) -> tuple[_SmartPartCandidateTrace, ...]:
    if type(traces) is not tuple:
        raise TypeError("traces must be a tuple.")
    if not all(isinstance(trace, _SmartPartCandidateTrace) for trace in traces):
        raise TypeError("traces must contain only shared candidate traces.")

    first_by_identity: dict[tuple[object, ...], _SmartPartCandidateTrace] = {}
    for trace in traces:
        first_by_identity.setdefault(_candidate_trace_identity_key(trace), trace)
    return tuple(first_by_identity.values())


@dataclass(frozen=True, slots=True)
class _SmartPartIndependentSupport:
    """Canonical independent source support for one resolved Smart Part kind."""

    kind: SmartPartKind
    direct_source_keys: tuple[_SmartPartSourceIdentity, ...]
    derived_source_keys: tuple[_SmartPartSourceIdentity, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.kind, SmartPartKind):
            raise TypeError("kind must be a SmartPartKind value.")
        for field_name in ("direct_source_keys", "derived_source_keys"):
            keys = getattr(self, field_name)
            if type(keys) is not tuple:
                raise TypeError(f"{field_name} must be a tuple.")
            for key in keys:
                if type(key) is not tuple or len(key) != 2:
                    raise TypeError(f"{field_name} must contain source identity tuples.")
                source_kind, source_index = key
                if not isinstance(source_kind, SmartPartEvidenceKind):
                    raise TypeError("source identity kind must be SmartPartEvidenceKind.")
                if type(source_index) is not int or source_index < 0:
                    raise ValueError("source identity index must be nonnegative int.")
            canonical = tuple(sorted(set(keys), key=_source_identity_sort_key))
            if keys != canonical:
                raise ValueError(f"{field_name} must be unique and canonical.")

        if not self.direct_source_keys and not self.derived_source_keys:
            raise ValueError("independent support must contain at least one source.")
        if any(
            source_kind not in _DIRECT_NAMED_SOURCE_KINDS
            for source_kind, _ in self.direct_source_keys
        ):
            raise ValueError("direct_source_keys contains a non-direct source kind.")
        if any(
            source_kind not in _DERIVED_SOURCE_KINDS
            for source_kind, _ in self.derived_source_keys
        ):
            raise ValueError("derived_source_keys contains a non-derived source kind.")


def _collect_smart_part_independent_support(
    entries: tuple[SmartPartDetectionEntry, ...],
) -> tuple[_SmartPartIndependentSupport, ...]:
    """Return resolved source identities without counting duplicate evidence rows."""

    associations = _collect_smart_part_candidate_associations(entries)
    direct_by_kind: dict[SmartPartKind, set[_SmartPartSourceIdentity]] = {}
    derived_by_kind: dict[SmartPartKind, set[_SmartPartSourceIdentity]] = {}

    for association in associations:
        if len(association.candidates) != 1:
            # Same-source exact conflicts remain ambiguity input, never resolved support.
            continue
        kind = association.candidates[0]
        key = (association.source_kind, association.source_index)
        if association.source_kind in _DIRECT_NAMED_SOURCE_KINDS:
            direct_by_kind.setdefault(kind, set()).add(key)
        elif association.source_kind in _DERIVED_SOURCE_KINDS:
            derived_by_kind.setdefault(kind, set()).add(key)

    return tuple(
        _SmartPartIndependentSupport(
            kind=kind,
            direct_source_keys=tuple(
                sorted(direct_by_kind.get(kind, set()), key=_source_identity_sort_key)
            ),
            derived_source_keys=tuple(
                sorted(derived_by_kind.get(kind, set()), key=_source_identity_sort_key)
            ),
        )
        for kind in SmartPartKind
        if direct_by_kind.get(kind) or derived_by_kind.get(kind)
    )

_REASON_HIGH = "multiple_independent_direct_exact_sources"
_REASON_MEDIUM = "single_direct_exact_source"
_REASON_LOW = "derived_texture_only"


class _SmartPartResolvedConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True, slots=True)
class _SmartPartResolvedAssessment:
    confidence: _SmartPartResolvedConfidence
    support: _SmartPartIndependentSupport
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.confidence, _SmartPartResolvedConfidence):
            raise TypeError("confidence must be a _SmartPartResolvedConfidence value.")
        if not isinstance(self.support, _SmartPartIndependentSupport):
            raise TypeError("support must be a _SmartPartIndependentSupport value.")
        if type(self.reason) is not str:
            raise TypeError("reason must be a string.")

        direct_count = len(self.support.direct_source_keys)
        derived_count = len(self.support.derived_source_keys)

        if self.confidence is _SmartPartResolvedConfidence.HIGH:
            if self.reason != _REASON_HIGH:
                raise ValueError("HIGH must use the frozen HIGH machine reason.")
            if direct_count < 2:
                raise ValueError("HIGH requires at least two independent direct sources.")
        elif self.confidence is _SmartPartResolvedConfidence.MEDIUM:
            if self.reason != _REASON_MEDIUM:
                raise ValueError("MEDIUM must use the frozen MEDIUM machine reason.")
            if direct_count != 1:
                raise ValueError("MEDIUM requires exactly one independent direct source.")
        elif self.confidence is _SmartPartResolvedConfidence.LOW:
            if self.reason != _REASON_LOW:
                raise ValueError("LOW must use the frozen LOW machine reason.")
            if direct_count != 0 or derived_count < 1:
                raise ValueError(
                    "LOW requires derived texture support and zero direct sources."
                )


def _derive_resolved_confidence(
    support: _SmartPartIndependentSupport,
) -> _SmartPartResolvedAssessment:
    if not isinstance(support, _SmartPartIndependentSupport):
        raise TypeError("support must be a _SmartPartIndependentSupport value.")

    direct_count = len(support.direct_source_keys)
    if direct_count >= 2:
        return _SmartPartResolvedAssessment(
            confidence=_SmartPartResolvedConfidence.HIGH,
            support=support,
            reason=_REASON_HIGH,
        )
    if direct_count == 1:
        return _SmartPartResolvedAssessment(
            confidence=_SmartPartResolvedConfidence.MEDIUM,
            support=support,
            reason=_REASON_MEDIUM,
        )
    return _SmartPartResolvedAssessment(
        confidence=_SmartPartResolvedConfidence.LOW,
        support=support,
        reason=_REASON_LOW,
    )


def _derive_smart_part_resolved_assessments(
    entries: tuple[SmartPartDetectionEntry, ...],
) -> tuple[_SmartPartResolvedAssessment, ...]:
    return tuple(
        _derive_resolved_confidence(support)
        for support in _collect_smart_part_independent_support(entries)
    )

_REASON_AMBIGUOUS = "same_source_exact_conflict"


@dataclass(frozen=True, slots=True)
class _SmartPartAmbiguityCandidate:
    kind: SmartPartKind
    traces: tuple[_SmartPartCandidateTrace, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.kind, SmartPartKind):
            raise TypeError("kind must be a SmartPartKind value.")
        if type(self.traces) is not tuple or not self.traces:
            raise ValueError("traces must be a non-empty tuple.")
        if not all(isinstance(trace, _SmartPartCandidateTrace) for trace in self.traces):
            raise TypeError("traces must contain only shared candidate traces.")
        if any(trace.kind is not self.kind for trace in self.traces):
            raise ValueError("all traces must belong to the candidate kind.")

        deduplicated = _deduplicate_candidate_traces(self.traces)
        if self.traces != deduplicated:
            raise ValueError("candidate traces must be exact-duplicate-free.")

        source_keys = {
            (trace.evidence.source_kind, trace.evidence.source_index)
            for trace in self.traces
        }
        if len(source_keys) != 1:
            raise ValueError("candidate traces must belong to one source association.")


@dataclass(frozen=True, slots=True)
class _SmartPartAmbiguityAssessment:
    source_kind: SmartPartEvidenceKind
    source_index: int
    candidates: tuple[_SmartPartAmbiguityCandidate, ...]
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.source_kind, SmartPartEvidenceKind):
            raise TypeError("source_kind must be a SmartPartEvidenceKind value.")
        if type(self.source_index) is not int or self.source_index < 0:
            raise ValueError("source_index must be a nonnegative integer.")
        if type(self.candidates) is not tuple or len(self.candidates) < 2:
            raise ValueError("ambiguity requires at least two candidates.")
        if not all(
            isinstance(candidate, _SmartPartAmbiguityCandidate)
            for candidate in self.candidates
        ):
            raise TypeError("candidates must contain ambiguity candidate values.")

        kinds = tuple(candidate.kind for candidate in self.candidates)
        canonical_kinds = tuple(kind for kind in SmartPartKind if kind in set(kinds))
        if kinds != canonical_kinds:
            raise ValueError(
                "ambiguity candidates must be unique and use SmartPartKind order."
            )

        for candidate in self.candidates:
            for trace in candidate.traces:
                if trace.evidence.source_kind is not self.source_kind:
                    raise ValueError("candidate source_kind must match assessment.")
                if trace.evidence.source_index != self.source_index:
                    raise ValueError("candidate source_index must match assessment.")

        if self.reason != _REASON_AMBIGUOUS:
            raise ValueError("ambiguity must use the frozen machine reason.")


def _collect_smart_part_ambiguity_assessments(
    entries: tuple[SmartPartDetectionEntry, ...],
) -> tuple[_SmartPartAmbiguityAssessment, ...]:
    associations = _collect_smart_part_candidate_associations(entries)
    assessments: list[_SmartPartAmbiguityAssessment] = []

    for association in associations:
        if len(association.candidates) < 2:
            continue

        candidates = tuple(
            _SmartPartAmbiguityCandidate(
                kind=kind,
                traces=_deduplicate_candidate_traces(
                    tuple(
                        trace
                        for trace in association.traces
                        if trace.kind is kind
                    )
                ),
            )
            for kind in association.candidates
        )
        assessments.append(
            _SmartPartAmbiguityAssessment(
                source_kind=association.source_kind,
                source_index=association.source_index,
                candidates=candidates,
                reason=_REASON_AMBIGUOUS,
            )
        )

    return tuple(assessments)


__all__: tuple[str, ...] = ()
