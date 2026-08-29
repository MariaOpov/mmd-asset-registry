"""Stable authoring service boundary for structural transaction plans."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
import re
from typing import Final

from mmd_registry.pmx.transaction_plan import (
    PmxStructuralTransactionPlan,
    PmxStructuralTransactionPlanError,
    PmxStructuralTransactionPlanExplanation,
    explain_pmx_structural_transaction_plan as _explain_plan,
    load_pmx_structural_transaction_plan as _load_plan,
    parse_pmx_structural_transaction_plan_json as _parse_plan_json,
)
from mmd_registry.services.structural_transaction import (
    PmxStructuralTransactionRequest,
)


_DETAIL_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(r"[a-z][a-z0-9_]*\Z")
_CONTEXT_VALUE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"[A-Za-z0-9_.\[\]-]{1,128}\Z"
)


class PmxStructuralTransactionPlanServiceOperation(StrEnum):
    """Stable CP15 authoring-service operations."""

    PARSE_JSON = "parse_structural_transaction_plan_json"
    LOAD = "load_structural_transaction_plan"
    VALIDATE = "validate_structural_transaction_plan"
    EXPLAIN = "explain_structural_transaction_plan"


class PmxStructuralTransactionPlanServiceDiagnosticCode(StrEnum):
    """Stable coarse-grained CP15 authoring-service failure codes."""

    INVALID_ARGUMENT = "invalid_argument"
    PLAN_INVALID = "transaction_plan_invalid"
    IO_FAILED = "service_io_failed"
    INTERNAL_ERROR = "service_internal_error"


@dataclass(frozen=True, slots=True)
class PmxStructuralTransactionPlanServiceDiagnostic:
    """One deterministic disclosure-safe authoring-service diagnostic."""

    code: PmxStructuralTransactionPlanServiceDiagnosticCode
    operation: PmxStructuralTransactionPlanServiceOperation
    message: str
    details: tuple[tuple[str, str | int | bool | None], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(
            self.code,
            PmxStructuralTransactionPlanServiceDiagnosticCode,
        ):
            raise TypeError(
                "code must be a PmxStructuralTransactionPlanServiceDiagnosticCode."
            )
        if not isinstance(
            self.operation,
            PmxStructuralTransactionPlanServiceOperation,
        ):
            raise TypeError(
                "operation must be a PmxStructuralTransactionPlanServiceOperation."
            )
        if type(self.message) is not str or not self.message:
            raise ValueError("message must be a non-empty string.")
        if type(self.details) is not tuple:
            raise TypeError("details must be a tuple of key/value pairs.")

        seen: set[str] = set()
        for item in self.details:
            if type(item) is not tuple or len(item) != 2:
                raise TypeError("each detail must be one key/value tuple.")
            key, value = item
            if (
                type(key) is not str
                or _DETAIL_KEY_PATTERN.fullmatch(key) is None
            ):
                raise ValueError(
                    "diagnostic detail keys must use lowercase snake_case."
                )
            if key in seen:
                raise ValueError(f"duplicate diagnostic detail key {key!r}.")
            seen.add(key)
            if value is not None and type(value) not in (str, int, bool):
                raise TypeError(
                    "diagnostic detail values must be strings, integers, "
                    "booleans, or None."
                )

    def to_dict(self) -> dict[str, object]:
        """Return one deterministic JSON-ready diagnostic payload."""

        payload: dict[str, object] = {
            "code": self.code.value,
            "operation": self.operation.value,
            "message": self.message,
        }
        if self.details:
            payload["details"] = dict(sorted(self.details))
        return payload


class PmxStructuralTransactionPlanServiceError(RuntimeError):
    """Public authoring-service failure carrying one safe diagnostic."""

    def __init__(
        self,
        diagnostic: PmxStructuralTransactionPlanServiceDiagnostic,
    ) -> None:
        if not isinstance(
            diagnostic,
            PmxStructuralTransactionPlanServiceDiagnostic,
        ):
            raise TypeError(
                "diagnostic must be a PmxStructuralTransactionPlanServiceDiagnostic."
            )
        self.diagnostic = diagnostic
        super().__init__(diagnostic.message)

    def to_dict(self) -> dict[str, object]:
        """Return the wrapped diagnostic as a JSON-ready payload."""

        return self.diagnostic.to_dict()


@dataclass(frozen=True, slots=True)
class PmxStructuralTransactionPlanValidationResult:
    """One immutable validated plan paired with its released request."""

    plan: PmxStructuralTransactionPlan
    request: PmxStructuralTransactionRequest

    def __post_init__(self) -> None:
        if not isinstance(self.plan, PmxStructuralTransactionPlan):
            raise TypeError(
                "plan must be a PmxStructuralTransactionPlan instance."
            )
        if not isinstance(self.request, PmxStructuralTransactionRequest):
            raise TypeError(
                "request must be a PmxStructuralTransactionRequest instance."
            )
        if self.request.operations != self.plan.operations:
            raise ValueError(
                "request operations must exactly match the authored plan."
            )

    @property
    def schema_version(self) -> int:
        """Return the validated authoring schema version."""

        return self.plan.schema_version

    @property
    def operation_count(self) -> int:
        """Return the number of ordered structural operations."""

        return len(self.plan.operations)

    @property
    def expected_source_sha256_declared(self) -> bool:
        """Report only whether a source identity precondition was declared."""

        return self.plan.expected_source_sha256 is not None

    def to_dict(self) -> dict[str, object]:
        """Return deterministic value-free validation evidence."""

        return {
            "status": "valid",
            "schema_version": self.schema_version,
            "operation_count": self.operation_count,
            "expected_source_sha256_declared": (
                self.expected_source_sha256_declared
            ),
        }


def _safe_context_value(value: str | None) -> str | None:
    if value is None:
        return None
    if _CONTEXT_VALUE_PATTERN.fullmatch(value) is None:
        return None
    return value


def _plan_error_details(
    error: PmxStructuralTransactionPlanError,
) -> tuple[tuple[str, str | int | bool | None], ...]:
    details: list[tuple[str, str | int | bool | None]] = []
    if error.operation_index is not None:
        details.append(("operation_index", error.operation_index))
    operation_type = _safe_context_value(error.operation_type)
    if operation_type is not None:
        details.append(("operation_type", operation_type))
    field = _safe_context_value(error.field)
    if field is not None:
        details.append(("field", field))
    return tuple(details)


def _service_error(
    operation: PmxStructuralTransactionPlanServiceOperation,
    error: Exception,
) -> PmxStructuralTransactionPlanServiceError:
    if isinstance(error, PmxStructuralTransactionPlanError):
        diagnostic = PmxStructuralTransactionPlanServiceDiagnostic(
            code=PmxStructuralTransactionPlanServiceDiagnosticCode.PLAN_INVALID,
            operation=operation,
            message="Structural transaction plan is invalid.",
            details=_plan_error_details(error),
        )
    elif isinstance(error, OSError):
        details = (("errno", error.errno),) if type(error.errno) is int else ()
        diagnostic = PmxStructuralTransactionPlanServiceDiagnostic(
            code=PmxStructuralTransactionPlanServiceDiagnosticCode.IO_FAILED,
            operation=operation,
            message="Structural transaction-plan file operation failed.",
            details=details,
        )
    elif isinstance(error, (TypeError, ValueError)):
        diagnostic = PmxStructuralTransactionPlanServiceDiagnostic(
            code=PmxStructuralTransactionPlanServiceDiagnosticCode.INVALID_ARGUMENT,
            operation=operation,
            message="Invalid structural transaction-plan service input.",
        )
    else:
        diagnostic = PmxStructuralTransactionPlanServiceDiagnostic(
            code=PmxStructuralTransactionPlanServiceDiagnosticCode.INTERNAL_ERROR,
            operation=operation,
            message="Unexpected structural transaction-plan service failure.",
        )
    return PmxStructuralTransactionPlanServiceError(diagnostic)


def _validate_plan(
    plan: PmxStructuralTransactionPlan,
) -> PmxStructuralTransactionPlanValidationResult:
    if not isinstance(plan, PmxStructuralTransactionPlan):
        raise TypeError(
            "plan must be a PmxStructuralTransactionPlan instance."
        )
    request = PmxStructuralTransactionRequest(operations=plan.operations)
    return PmxStructuralTransactionPlanValidationResult(
        plan=plan,
        request=request,
    )


def parse_structural_transaction_plan_json(
    text: str,
) -> PmxStructuralTransactionPlanValidationResult:
    """Parse strict JSON and compile exactly one released transaction request."""

    try:
        return _validate_plan(_parse_plan_json(text))
    except Exception as error:
        failure = _service_error(
            PmxStructuralTransactionPlanServiceOperation.PARSE_JSON,
            error,
        )
    raise failure from None


def load_structural_transaction_plan(
    path: str | Path,
) -> PmxStructuralTransactionPlanValidationResult:
    """Load one bounded JSON plan and compile one released transaction request."""

    try:
        return _validate_plan(_load_plan(path))
    except Exception as error:
        failure = _service_error(
            PmxStructuralTransactionPlanServiceOperation.LOAD,
            error,
        )
    raise failure from None


def validate_structural_transaction_plan(
    plan: PmxStructuralTransactionPlan,
) -> PmxStructuralTransactionPlanValidationResult:
    """Validate one typed plan through the released transaction request authority."""

    try:
        return _validate_plan(plan)
    except Exception as error:
        failure = _service_error(
            PmxStructuralTransactionPlanServiceOperation.VALIDATE,
            error,
        )
    raise failure from None


def explain_structural_transaction_plan(
    plan: PmxStructuralTransactionPlan,
) -> PmxStructuralTransactionPlanExplanation:
    """Return the existing deterministic value-free authoring explanation."""

    try:
        return _explain_plan(plan)
    except Exception as error:
        failure = _service_error(
            PmxStructuralTransactionPlanServiceOperation.EXPLAIN,
            error,
        )
    raise failure from None


__all__ = (
    "PmxStructuralTransactionPlanServiceOperation",
    "PmxStructuralTransactionPlanServiceDiagnosticCode",
    "PmxStructuralTransactionPlanServiceDiagnostic",
    "PmxStructuralTransactionPlanServiceError",
    "PmxStructuralTransactionPlanValidationResult",
    "parse_structural_transaction_plan_json",
    "load_structural_transaction_plan",
    "validate_structural_transaction_plan",
    "explain_structural_transaction_plan",
)
