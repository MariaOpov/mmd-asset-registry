"""Stable structured diagnostics for extracted PMX reference evidence.

CP07 converts immutable CP05 raw evidence into deterministic diagnostics.
It does not traverse a model document, expose a service API, mutate data,
recommend corrective actions, change reference indices, or touch the filesystem.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from mmd_registry.pmx.reference_graph import (
    PmxReferenceGraph,
    PmxReferenceInvalidTarget,
    PmxReferenceUnsupportedState,
    PmxReferenceUnsupportedStateKind,
)
from mmd_registry.pmx.reference_model import (
    PmxReferenceSourceLocation,
    PmxReferenceTargetKind,
)


class PmxReferenceDiagnosticCode(StrEnum):
    """Stable CP07 codes for reference-analysis evidence."""

    INVALID_TARGET = "invalid_target"
    ACTIVE_PAYLOAD_MISSING = "active_payload_missing"
    INACTIVE_PAYLOAD_PRESENT = "inactive_payload_present"
    MORPH_OFFSET_TYPE_MISMATCH = "morph_offset_type_mismatch"
    VERSION_CONDITION_MISMATCH = "version_condition_mismatch"
    UV_LAYER_CONDITION_MISMATCH = "uv_layer_condition_mismatch"


_MESSAGES = {
    PmxReferenceDiagnosticCode.INVALID_TARGET:
        "Reference target index is invalid.",
    PmxReferenceDiagnosticCode.ACTIVE_PAYLOAD_MISSING:
        "Active reference payload is missing.",
    PmxReferenceDiagnosticCode.INACTIVE_PAYLOAD_PRESENT:
        "Inactive reference payload is present.",
    PmxReferenceDiagnosticCode.MORPH_OFFSET_TYPE_MISMATCH:
        "Morph offset type does not match the reference relationship.",
    PmxReferenceDiagnosticCode.VERSION_CONDITION_MISMATCH:
        "Reference relationship is not supported by the PMX version.",
    PmxReferenceDiagnosticCode.UV_LAYER_CONDITION_MISMATCH:
        "UV reference relationship exceeds available additional UV layers.",
}

_UNSUPPORTED_CODE_MAP = {
    PmxReferenceUnsupportedStateKind.ACTIVE_PAYLOAD_MISSING:
        PmxReferenceDiagnosticCode.ACTIVE_PAYLOAD_MISSING,
    PmxReferenceUnsupportedStateKind.INACTIVE_PAYLOAD_PRESENT:
        PmxReferenceDiagnosticCode.INACTIVE_PAYLOAD_PRESENT,
    PmxReferenceUnsupportedStateKind.MORPH_OFFSET_TYPE_MISMATCH:
        PmxReferenceDiagnosticCode.MORPH_OFFSET_TYPE_MISMATCH,
    PmxReferenceUnsupportedStateKind.VERSION_CONDITION_MISMATCH:
        PmxReferenceDiagnosticCode.VERSION_CONDITION_MISMATCH,
    PmxReferenceUnsupportedStateKind.UV_LAYER_CONDITION_MISMATCH:
        PmxReferenceDiagnosticCode.UV_LAYER_CONDITION_MISMATCH,
}


@dataclass(frozen=True, slots=True)
class PmxReferenceDiagnostic:
    """One immutable deterministic diagnostic derived from CP05 evidence."""

    code: PmxReferenceDiagnosticCode
    message: str
    relationship_id: str
    source: PmxReferenceSourceLocation
    target_kind: PmxReferenceTargetKind | None = None
    raw_index: int | None = None
    target_count: int | None = None
    observed: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, PmxReferenceDiagnosticCode):
            raise TypeError("code must be a PmxReferenceDiagnosticCode value.")
        if type(self.message) is not str or not self.message:
            raise ValueError("message must be a non-empty string.")
        if self.message != _MESSAGES[self.code]:
            raise ValueError("message must match the stable diagnostic code message.")
        if type(self.relationship_id) is not str or not self.relationship_id:
            raise ValueError("relationship_id must be a non-empty string.")
        if not isinstance(self.source, PmxReferenceSourceLocation):
            raise TypeError("source must be a PmxReferenceSourceLocation value.")

        invalid_target = self.code is PmxReferenceDiagnosticCode.INVALID_TARGET
        if invalid_target:
            if not isinstance(self.target_kind, PmxReferenceTargetKind):
                raise TypeError("invalid-target diagnostics require target_kind.")
            if type(self.raw_index) is not int:
                raise TypeError("invalid-target diagnostics require integer raw_index.")
            if type(self.target_count) is not int:
                raise TypeError("invalid-target diagnostics require integer target_count.")
            if self.target_count < 0:
                raise ValueError("target_count must be nonnegative.")
            if self.observed is not None:
                raise ValueError("invalid-target diagnostics cannot carry observed.")
        else:
            if self.target_kind is not None:
                raise ValueError("unsupported-state diagnostics cannot carry target_kind.")
            if self.raw_index is not None or self.target_count is not None:
                raise ValueError(
                    "unsupported-state diagnostics cannot carry target index details."
                )
            if type(self.observed) is not str or not self.observed:
                raise ValueError(
                    "unsupported-state diagnostics require non-empty observed."
                )

    def to_dict(self) -> dict[str, object]:
        """Return a deterministic JSON-ready diagnostic payload."""

        payload: dict[str, object] = {
            "code": self.code.value,
            "message": self.message,
            "relationship_id": self.relationship_id,
            "source": {
                "section": self.source.section.value,
                "record_index": self.source.record_index,
                "path": self.source.path,
            },
        }
        if self.code is PmxReferenceDiagnosticCode.INVALID_TARGET:
            assert self.target_kind is not None
            assert self.raw_index is not None
            assert self.target_count is not None
            payload["target"] = {
                "kind": self.target_kind.value,
                "raw_index": self.raw_index,
                "target_count": self.target_count,
            }
        else:
            assert self.observed is not None
            payload["observed"] = self.observed
        return payload


def _diagnostic_from_invalid_target(
    evidence: PmxReferenceInvalidTarget,
) -> PmxReferenceDiagnostic:
    return PmxReferenceDiagnostic(
        code=PmxReferenceDiagnosticCode.INVALID_TARGET,
        message=_MESSAGES[PmxReferenceDiagnosticCode.INVALID_TARGET],
        relationship_id=evidence.relationship_id,
        source=evidence.source,
        target_kind=evidence.target_kind,
        raw_index=evidence.raw_index,
        target_count=evidence.target_count,
    )


def _diagnostic_from_unsupported_state(
    evidence: PmxReferenceUnsupportedState,
) -> PmxReferenceDiagnostic:
    code = _UNSUPPORTED_CODE_MAP[evidence.kind]
    return PmxReferenceDiagnostic(
        code=code,
        message=_MESSAGES[code],
        relationship_id=evidence.relationship_id,
        source=evidence.source,
        observed=evidence.observed,
    )


def diagnose_reference_graph(
    graph: PmxReferenceGraph,
) -> tuple[PmxReferenceDiagnostic, ...]:
    """Convert all CP05 raw evidence into stable structured diagnostics.

    Ordering is deliberately category-stable: invalid-target evidence first in
    its CP05 extraction order, followed by unsupported-state evidence in its
    CP05 extraction order. No evidence is dropped, merged, normalized, or
    deduplicated.
    """

    if not isinstance(graph, PmxReferenceGraph):
        raise TypeError("graph must be a PmxReferenceGraph value.")

    invalid = tuple(
        _diagnostic_from_invalid_target(item)
        for item in graph.invalid_targets
    )
    unsupported = tuple(
        _diagnostic_from_unsupported_state(item)
        for item in graph.unsupported_states
    )
    return invalid + unsupported


__all__ = (
    "PmxReferenceDiagnostic",
    "PmxReferenceDiagnosticCode",
    "diagnose_reference_graph",
)
