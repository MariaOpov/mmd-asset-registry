"""Exact deterministic source selectors for structural authoring."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final, TypeAlias

from mmd_registry.pmx.document import PmxDocument
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind


PMX_STRUCTURAL_AUTHORING_SELECTOR_MAX_CANDIDATES: Final[int] = 100


class PmxStructuralAuthoringSelectorField(StrEnum):
    """Explicit source identity fields supported by exact resolution."""

    SOURCE_INDEX = "source_index"
    LOCAL_NAME = "local_name"
    UNIVERSAL_NAME = "universal_name"
    PATH = "path"


class PmxStructuralAuthoringSelectorOutcome(StrEnum):
    """Deterministic selector outcomes."""

    RESOLVED = "resolved"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"


SelectorValue: TypeAlias = int | str


def _allowed_fields(
    target_kind: PmxReferenceTargetKind,
) -> tuple[PmxStructuralAuthoringSelectorField, ...]:
    if target_kind is PmxReferenceTargetKind.VERTEX:
        return (PmxStructuralAuthoringSelectorField.SOURCE_INDEX,)
    if target_kind is PmxReferenceTargetKind.TEXTURE:
        return (
            PmxStructuralAuthoringSelectorField.SOURCE_INDEX,
            PmxStructuralAuthoringSelectorField.PATH,
        )
    return (
        PmxStructuralAuthoringSelectorField.SOURCE_INDEX,
        PmxStructuralAuthoringSelectorField.LOCAL_NAME,
        PmxStructuralAuthoringSelectorField.UNIVERSAL_NAME,
    )


@dataclass(frozen=True, slots=True)
class PmxStructuralAuthoringSelector:
    """One explicit exact selector that never performs implicit fallback."""

    target_kind: PmxReferenceTargetKind
    field: PmxStructuralAuthoringSelectorField
    value: SelectorValue

    def __post_init__(self) -> None:
        if not isinstance(self.target_kind, PmxReferenceTargetKind):
            raise TypeError("target_kind must be PmxReferenceTargetKind.")
        if not isinstance(self.field, PmxStructuralAuthoringSelectorField):
            raise TypeError(
                "field must be PmxStructuralAuthoringSelectorField."
            )
        if self.field not in _allowed_fields(self.target_kind):
            raise ValueError(
                "selector field is not supported for the target kind."
            )

        if self.field is PmxStructuralAuthoringSelectorField.SOURCE_INDEX:
            if type(self.value) is not int:
                raise TypeError("source_index selector value must be an integer.")
            if self.value < 0:
                raise ValueError("source_index selector value cannot be negative.")
            return

        if type(self.value) is not str:
            raise TypeError("text selector value must be a string.")
        if self.value == "":
            raise ValueError("text selector value cannot be empty.")


@dataclass(frozen=True, slots=True)
class PmxStructuralAuthoringSelectorResolution:
    """One exact selector compiled to a captured-source index."""

    target_kind: PmxReferenceTargetKind
    source_index: int
    matched_by: PmxStructuralAuthoringSelectorField
    outcome: PmxStructuralAuthoringSelectorOutcome = (
        PmxStructuralAuthoringSelectorOutcome.RESOLVED
    )

    def __post_init__(self) -> None:
        if not isinstance(self.target_kind, PmxReferenceTargetKind):
            raise TypeError("target_kind must be PmxReferenceTargetKind.")
        if type(self.source_index) is not int or self.source_index < 0:
            raise ValueError("source_index must be a nonnegative integer.")
        if not isinstance(
            self.matched_by,
            PmxStructuralAuthoringSelectorField,
        ):
            raise TypeError(
                "matched_by must be PmxStructuralAuthoringSelectorField."
            )
        if (
            self.outcome
            is not PmxStructuralAuthoringSelectorOutcome.RESOLVED
        ):
            raise ValueError("resolution outcome must be resolved.")

    def to_dict(self) -> dict[str, object]:
        return {
            "outcome": self.outcome.value,
            "target_kind": self.target_kind.value,
            "source_index": self.source_index,
            "matched_by": self.matched_by.value,
        }


class PmxStructuralAuthoringSelectorServiceOperation(StrEnum):
    """Reusable exact selector service operations."""

    RESOLVE = "resolve_structural_authoring_selector"


class PmxStructuralAuthoringSelectorServiceDiagnosticCode(StrEnum):
    """Stable selector service failure categories."""

    INVALID_ARGUMENT = "invalid_argument"
    NOT_FOUND = "selector_not_found"
    AMBIGUOUS = "selector_ambiguous"
    INTERNAL_ERROR = "selector_internal_error"


@dataclass(frozen=True, slots=True)
class PmxStructuralAuthoringSelectorServiceDiagnostic:
    """Bounded privacy-safe selector diagnostic."""

    code: PmxStructuralAuthoringSelectorServiceDiagnosticCode
    operation: PmxStructuralAuthoringSelectorServiceOperation
    message: str
    target_kind: PmxReferenceTargetKind | None = None
    matched_by: PmxStructuralAuthoringSelectorField | None = None
    candidate_count: int | None = None
    candidate_source_indices: tuple[int, ...] = ()
    candidates_truncated: bool = False

    def __post_init__(self) -> None:
        if not isinstance(
            self.code,
            PmxStructuralAuthoringSelectorServiceDiagnosticCode,
        ):
            raise TypeError("invalid selector diagnostic code.")
        if not isinstance(
            self.operation,
            PmxStructuralAuthoringSelectorServiceOperation,
        ):
            raise TypeError("invalid selector diagnostic operation.")
        if type(self.message) is not str or not self.message:
            raise ValueError("selector diagnostic message must be non-empty.")

        if self.target_kind is not None and not isinstance(
            self.target_kind,
            PmxReferenceTargetKind,
        ):
            raise TypeError("target_kind diagnostic detail is invalid.")
        if self.matched_by is not None and not isinstance(
            self.matched_by,
            PmxStructuralAuthoringSelectorField,
        ):
            raise TypeError("matched_by diagnostic detail is invalid.")
        if self.candidate_count is not None:
            if type(self.candidate_count) is not int or self.candidate_count < 0:
                raise ValueError(
                    "candidate_count must be a nonnegative integer or None."
                )
        if type(self.candidate_source_indices) is not tuple:
            raise TypeError("candidate_source_indices must be a tuple.")
        if len(self.candidate_source_indices) > (
            PMX_STRUCTURAL_AUTHORING_SELECTOR_MAX_CANDIDATES
        ):
            raise ValueError("candidate_source_indices exceeds the public bound.")
        previous = -1
        for source_index in self.candidate_source_indices:
            if type(source_index) is not int or source_index < 0:
                raise ValueError(
                    "candidate source indices must be nonnegative integers."
                )
            if source_index <= previous:
                raise ValueError(
                    "candidate source indices must be strictly increasing."
                )
            previous = source_index
        if type(self.candidates_truncated) is not bool:
            raise TypeError("candidates_truncated must be a boolean.")

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "code": self.code.value,
            "operation": self.operation.value,
            "message": self.message,
        }
        details: dict[str, object] = {}
        if self.target_kind is not None:
            details["target_kind"] = self.target_kind.value
        if self.matched_by is not None:
            details["matched_by"] = self.matched_by.value
        if self.candidate_count is not None:
            details["candidate_count"] = self.candidate_count
        if self.candidate_source_indices:
            details["candidate_source_indices"] = list(
                self.candidate_source_indices
            )
        if self.candidates_truncated:
            details["candidates_truncated"] = True
        if details:
            payload["details"] = details
        return payload


class PmxStructuralAuthoringSelectorServiceError(RuntimeError):
    """Structured fail-closed selector service failure."""

    def __init__(
        self,
        diagnostic: PmxStructuralAuthoringSelectorServiceDiagnostic,
    ) -> None:
        if not isinstance(
            diagnostic,
            PmxStructuralAuthoringSelectorServiceDiagnostic,
        ):
            raise TypeError(
                "diagnostic must be a selector service diagnostic."
            )
        self.diagnostic = diagnostic
        super().__init__(diagnostic.message)

    def to_dict(self) -> dict[str, object]:
        return self.diagnostic.to_dict()


def _collection(
    document: PmxDocument,
    target_kind: PmxReferenceTargetKind,
) -> tuple[object, ...]:
    if target_kind is PmxReferenceTargetKind.VERTEX:
        return document.vertices
    if target_kind is PmxReferenceTargetKind.TEXTURE:
        return document.texture_paths
    if target_kind is PmxReferenceTargetKind.MATERIAL:
        return document.materials
    if target_kind is PmxReferenceTargetKind.BONE:
        return document.bones
    if target_kind is PmxReferenceTargetKind.MORPH:
        return document.morphs
    return document.rigid_bodies


def _matching_source_indices(
    document: PmxDocument,
    selector: PmxStructuralAuthoringSelector,
) -> tuple[int, ...]:
    collection = _collection(document, selector.target_kind)

    if selector.field is PmxStructuralAuthoringSelectorField.SOURCE_INDEX:
        source_index = selector.value
        if type(source_index) is not int:
            raise TypeError("validated source_index selector is not integer.")
        if source_index >= len(collection):
            return ()
        return (source_index,)

    value = selector.value
    if type(value) is not str:
        raise TypeError("validated text selector is not a string.")

    matches: list[int] = []
    for source_index, item in enumerate(collection):
        if selector.field is PmxStructuralAuthoringSelectorField.PATH:
            candidate = item
        elif (
            selector.field
            is PmxStructuralAuthoringSelectorField.LOCAL_NAME
        ):
            candidate = getattr(item, "local_name")
        else:
            candidate = getattr(item, "universal_name")
        if candidate == value:
            matches.append(source_index)
    return tuple(matches)


def _selector_diagnostic(
    code: PmxStructuralAuthoringSelectorServiceDiagnosticCode,
    message: str,
    *,
    selector: PmxStructuralAuthoringSelector | None = None,
    matches: tuple[int, ...] = (),
) -> PmxStructuralAuthoringSelectorServiceDiagnostic:
    target_kind = selector.target_kind if selector is not None else None
    matched_by = selector.field if selector is not None else None

    if code is PmxStructuralAuthoringSelectorServiceDiagnosticCode.AMBIGUOUS:
        bounded = matches[
            :PMX_STRUCTURAL_AUTHORING_SELECTOR_MAX_CANDIDATES
        ]
        return PmxStructuralAuthoringSelectorServiceDiagnostic(
            code=code,
            operation=PmxStructuralAuthoringSelectorServiceOperation.RESOLVE,
            message=message,
            target_kind=target_kind,
            matched_by=matched_by,
            candidate_count=len(matches),
            candidate_source_indices=bounded,
            candidates_truncated=len(matches) > len(bounded),
        )

    return PmxStructuralAuthoringSelectorServiceDiagnostic(
        code=code,
        operation=PmxStructuralAuthoringSelectorServiceOperation.RESOLVE,
        message=message,
        target_kind=target_kind,
        matched_by=matched_by,
    )


def resolve_structural_authoring_selector(
    document: PmxDocument,
    selector: PmxStructuralAuthoringSelector,
) -> PmxStructuralAuthoringSelectorResolution:
    """Resolve one explicit exact selector to one source index or fail closed."""

    try:
        if not isinstance(document, PmxDocument):
            raise TypeError("document must be a PmxDocument instance.")
        if not isinstance(selector, PmxStructuralAuthoringSelector):
            raise TypeError(
                "selector must be a PmxStructuralAuthoringSelector instance."
            )

        matches = _matching_source_indices(document, selector)
        if not matches:
            raise PmxStructuralAuthoringSelectorServiceError(
                _selector_diagnostic(
                    PmxStructuralAuthoringSelectorServiceDiagnosticCode.NOT_FOUND,
                    "Structural authoring selector did not match any source entity.",
                    selector=selector,
                )
            )
        if len(matches) != 1:
            raise PmxStructuralAuthoringSelectorServiceError(
                _selector_diagnostic(
                    PmxStructuralAuthoringSelectorServiceDiagnosticCode.AMBIGUOUS,
                    "Structural authoring selector matched multiple source entities.",
                    selector=selector,
                    matches=matches,
                )
            )

        return PmxStructuralAuthoringSelectorResolution(
            target_kind=selector.target_kind,
            source_index=matches[0],
            matched_by=selector.field,
        )
    except PmxStructuralAuthoringSelectorServiceError:
        raise
    except (TypeError, ValueError):
        failure = PmxStructuralAuthoringSelectorServiceError(
            _selector_diagnostic(
                PmxStructuralAuthoringSelectorServiceDiagnosticCode.INVALID_ARGUMENT,
                "Invalid structural authoring selector input.",
                selector=(
                    selector
                    if isinstance(selector, PmxStructuralAuthoringSelector)
                    else None
                ),
            )
        )
    except Exception:
        failure = PmxStructuralAuthoringSelectorServiceError(
            _selector_diagnostic(
                PmxStructuralAuthoringSelectorServiceDiagnosticCode.INTERNAL_ERROR,
                "Unexpected structural authoring selector failure.",
                selector=(
                    selector
                    if isinstance(selector, PmxStructuralAuthoringSelector)
                    else None
                ),
            )
        )
    raise failure from None


__all__ = (
    "PMX_STRUCTURAL_AUTHORING_SELECTOR_MAX_CANDIDATES",
    "PmxStructuralAuthoringSelectorField",
    "PmxStructuralAuthoringSelectorOutcome",
    "PmxStructuralAuthoringSelector",
    "PmxStructuralAuthoringSelectorResolution",
    "PmxStructuralAuthoringSelectorServiceOperation",
    "PmxStructuralAuthoringSelectorServiceDiagnosticCode",
    "PmxStructuralAuthoringSelectorServiceDiagnostic",
    "PmxStructuralAuthoringSelectorServiceError",
    "resolve_structural_authoring_selector",
)
