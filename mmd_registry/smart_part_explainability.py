"""Immutable deterministic explanations for Smart Part detection evidence.

This module is a read-only projection over the single private deterministic
match-trace authority owned by :mod:`mmd_registry.smart_part_detection`.
It has no independent semantic matching authority.
"""

from __future__ import annotations

from dataclasses import dataclass

from mmd_registry.smart_part_detection import (
    SmartPartDetectionEntry,
    _SmartPartMatchTrace,
    _match_smart_part_traces,
)
from mmd_registry.smart_parts import (
    SmartPartEvidence,
    SmartPartKind,
)


@dataclass(frozen=True, slots=True)
class SmartPartEvidenceExplanation:
    """Explain one canonical detector evidence record."""

    evidence: SmartPartEvidence
    source_field: str
    source_value: str
    comparison_value: str
    normalized_value: str
    matched_alias: str
    match_rule: str
    derivation: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.evidence, SmartPartEvidence):
            raise TypeError("evidence must be a SmartPartEvidence value.")
        for field_name in (
            "source_field",
            "source_value",
            "comparison_value",
            "normalized_value",
            "matched_alias",
            "match_rule",
        ):
            if type(getattr(self, field_name)) is not str:
                raise TypeError(f"{field_name} must be a string.")
        if not self.source_field:
            raise ValueError("source_field must be non-empty.")
        if not self.normalized_value:
            raise ValueError("normalized_value must be non-empty.")
        if not self.matched_alias:
            raise ValueError("matched_alias must be non-empty.")
        if self.match_rule != "exact_alias":
            raise ValueError("match_rule must be 'exact_alias'.")
        if type(self.derivation) is not tuple:
            raise TypeError("derivation must be a tuple.")
        for item in self.derivation:
            if (
                type(item) is not tuple
                or len(item) != 2
                or type(item[0]) is not str
                or type(item[1]) is not str
            ):
                raise TypeError(
                    "derivation must contain only string/string tuples."
                )


@dataclass(frozen=True, slots=True)
class SmartPartExplanation:
    """Explain all canonical detector evidence for one Smart Part kind."""

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


def _explanation_from_trace(
    trace: _SmartPartMatchTrace,
) -> SmartPartEvidenceExplanation:
    return SmartPartEvidenceExplanation(
        evidence=trace.evidence,
        source_field=trace.source_field,
        source_value=trace.source_value,
        comparison_value=trace.comparison_value,
        normalized_value=trace.normalized_value,
        matched_alias=trace.matched_alias,
        match_rule=trace.match_rule,
        derivation=trace.derivation,
    )


def explain_smart_parts(
    entries: tuple[SmartPartDetectionEntry, ...],
) -> tuple[SmartPartExplanation, ...]:
    """Return canonical explanations projected from shared detector traces."""

    traces = _match_smart_part_traces(entries)

    first_trace_by_kind_and_evidence: dict[
        tuple[SmartPartKind, SmartPartEvidence],
        _SmartPartMatchTrace,
    ] = {}
    for trace in traces:
        key = (trace.kind, trace.evidence)
        first_trace_by_kind_and_evidence.setdefault(key, trace)

    return tuple(
        SmartPartExplanation(
            kind=kind,
            evidence=tuple(
                _explanation_from_trace(trace)
                for (
                    trace_kind,
                    _,
                ), trace in first_trace_by_kind_and_evidence.items()
                if trace_kind is kind
            ),
        )
        for kind in SmartPartKind
        if any(
            trace_kind is kind
            for trace_kind, _ in first_trace_by_kind_and_evidence
        )
    )


__all__ = (
    "SmartPartEvidenceExplanation",
    "SmartPartExplanation",
    "explain_smart_parts",
)
