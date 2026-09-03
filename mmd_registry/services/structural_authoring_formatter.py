"""Canonical formatter boundary for structural authoring plan JSON."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from mmd_registry.pmx.transaction_plan import (
    PmxStructuralTransactionPlanDecodeError,
    PmxStructuralTransactionPlanError,
    parse_pmx_structural_transaction_plan_json,
    render_pmx_structural_transaction_plan_json,
)


class PmxStructuralAuthoringFormatterServiceOperation(StrEnum):
    """Stable formatter service operations."""

    NORMALIZE_JSON = "normalize_structural_authoring_plan_json"


class PmxStructuralAuthoringFormatterServiceDiagnosticCode(StrEnum):
    """Stable disclosure-safe formatter failure categories."""

    INVALID_ARGUMENT = "invalid_argument"
    PLAN_INVALID = "structural_authoring_plan_invalid"
    INTERNAL_ERROR = "structural_authoring_formatter_internal_error"


@dataclass(frozen=True, slots=True)
class PmxStructuralAuthoringFormatterServiceDiagnostic:
    """One bounded formatter diagnostic without authored values."""

    code: PmxStructuralAuthoringFormatterServiceDiagnosticCode
    operation: PmxStructuralAuthoringFormatterServiceOperation
    message: str

    def __post_init__(self) -> None:
        if not isinstance(
            self.code,
            PmxStructuralAuthoringFormatterServiceDiagnosticCode,
        ):
            raise TypeError("invalid structural authoring formatter code.")
        if not isinstance(
            self.operation,
            PmxStructuralAuthoringFormatterServiceOperation,
        ):
            raise TypeError("invalid structural authoring formatter operation.")
        if type(self.message) is not str or not self.message:
            raise ValueError("formatter diagnostic message must be non-empty.")

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code.value,
            "operation": self.operation.value,
            "message": self.message,
        }


class PmxStructuralAuthoringFormatterServiceError(RuntimeError):
    """Structured fail-closed formatter service failure."""

    def __init__(
        self,
        diagnostic: PmxStructuralAuthoringFormatterServiceDiagnostic,
    ) -> None:
        if not isinstance(
            diagnostic,
            PmxStructuralAuthoringFormatterServiceDiagnostic,
        ):
            raise TypeError("diagnostic must be a formatter service diagnostic.")
        self.diagnostic = diagnostic
        super().__init__(diagnostic.message)

    def to_dict(self) -> dict[str, object]:
        return self.diagnostic.to_dict()


def _diagnostic(
    code: PmxStructuralAuthoringFormatterServiceDiagnosticCode,
    message: str,
) -> PmxStructuralAuthoringFormatterServiceDiagnostic:
    return PmxStructuralAuthoringFormatterServiceDiagnostic(
        code=code,
        operation=PmxStructuralAuthoringFormatterServiceOperation.NORMALIZE_JSON,
        message=message,
    )


def normalize_structural_authoring_plan_json(text: str) -> str:
    """Normalize strict JSON only through the released parser and renderer."""

    try:
        if type(text) is not str:
            raise TypeError("text must be a string.")
        plan = parse_pmx_structural_transaction_plan_json(text)
        return render_pmx_structural_transaction_plan_json(plan)
    except TypeError:
        failure = PmxStructuralAuthoringFormatterServiceError(
            _diagnostic(
                PmxStructuralAuthoringFormatterServiceDiagnosticCode.INVALID_ARGUMENT,
                "Invalid structural authoring formatter input.",
            )
        )
    except (PmxStructuralTransactionPlanDecodeError, PmxStructuralTransactionPlanError):
        failure = PmxStructuralAuthoringFormatterServiceError(
            _diagnostic(
                PmxStructuralAuthoringFormatterServiceDiagnosticCode.PLAN_INVALID,
                "Structural authoring plan JSON is invalid.",
            )
        )
    except Exception:
        failure = PmxStructuralAuthoringFormatterServiceError(
            _diagnostic(
                PmxStructuralAuthoringFormatterServiceDiagnosticCode.INTERNAL_ERROR,
                "Unexpected structural authoring formatter failure.",
            )
        )
    raise failure from None


__all__ = (
    "PmxStructuralAuthoringFormatterServiceOperation",
    "PmxStructuralAuthoringFormatterServiceDiagnosticCode",
    "PmxStructuralAuthoringFormatterServiceDiagnostic",
    "PmxStructuralAuthoringFormatterServiceError",
    "normalize_structural_authoring_plan_json",
)
