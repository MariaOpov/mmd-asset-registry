"""Source-bound apply service for authored structural transaction plans."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
import re
from typing import Final, Literal, TypeAlias

from mmd_registry.diagnostics import (
    PmxServiceDiagnosticCode,
    PmxServiceError,
)
from mmd_registry.services import PmxStructuralExecutionResult
from mmd_registry.services.structural_transaction import (
    _execution_service_error,
    _transaction_failure_provenance,
    _write_structural_transaction_with_stage_callback,
)
from mmd_registry.services.structural_transaction_plan import (
    PmxStructuralTransactionPlanValidationResult,
)


_DiagnosticDetail: TypeAlias = str | int | bool | None
_SourceIdentityStatus: TypeAlias = Literal["matched", "not_declared"]

_DETAIL_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"[a-z][a-z0-9_]*\Z"
)
_SAFE_UNDERLYING_DETAIL_KEYS: Final[frozenset[str]] = frozenset(
    {
        "destination_published",
        "errno",
        "format_name",
        "new_id",
        "offset",
        "operation_index",
        "parse_operation",
        "provenance",
        "record_index",
        "relationship_id",
        "section",
        "source_bytes_read",
        "source_modified",
        "stage",
        "target_kind",
    }
)


class PmxStructuralTransactionPlanApplyServiceOperation(StrEnum):
    """Stable CP18 apply-service operations."""

    APPLY = "apply_structural_transaction_plan"


class PmxStructuralTransactionPlanApplyServiceDiagnosticCode(StrEnum):
    """Stable coarse-grained CP18 apply-service failure codes."""

    INVALID_ARGUMENT = "invalid_argument"
    IO_FAILED = "service_io_failed"
    SOURCE_INVALID = "source_invalid"
    SOURCE_IDENTITY_MISMATCH = "source_identity_mismatch"
    OUTPUT_PATH_UNSAFE = "output_path_unsafe"
    EXECUTION_FAILED = "structural_execution_failed"
    INTERNAL_ERROR = "service_internal_error"


@dataclass(frozen=True, slots=True)
class PmxStructuralTransactionPlanApplyServiceDiagnostic:
    """One deterministic disclosure-safe CP18 apply diagnostic."""

    code: PmxStructuralTransactionPlanApplyServiceDiagnosticCode
    operation: PmxStructuralTransactionPlanApplyServiceOperation
    message: str
    details: tuple[tuple[str, _DiagnosticDetail], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(
            self.code,
            PmxStructuralTransactionPlanApplyServiceDiagnosticCode,
        ):
            raise TypeError(
                "code must be a "
                "PmxStructuralTransactionPlanApplyServiceDiagnosticCode."
            )
        if not isinstance(
            self.operation,
            PmxStructuralTransactionPlanApplyServiceOperation,
        ):
            raise TypeError(
                "operation must be a "
                "PmxStructuralTransactionPlanApplyServiceOperation."
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


class PmxStructuralTransactionPlanApplyServiceError(RuntimeError):
    """Public CP18 failure carrying one disclosure-safe diagnostic."""

    def __init__(
        self,
        diagnostic: PmxStructuralTransactionPlanApplyServiceDiagnostic,
    ) -> None:
        if not isinstance(
            diagnostic,
            PmxStructuralTransactionPlanApplyServiceDiagnostic,
        ):
            raise TypeError(
                "diagnostic must be a "
                "PmxStructuralTransactionPlanApplyServiceDiagnostic."
            )
        self.diagnostic = diagnostic
        super().__init__(diagnostic.message)

    def to_dict(self) -> dict[str, object]:
        """Return the wrapped diagnostic as a JSON-ready payload."""

        return self.diagnostic.to_dict()


@dataclass(frozen=True, slots=True)
class PmxStructuralTransactionPlanApplyResult:
    """Bounded CP18 wrapper around one committed released execution result."""

    _execution: PmxStructuralExecutionResult = field(repr=False)
    expected_source_sha256_declared: bool
    source_identity_status: _SourceIdentityStatus

    def __post_init__(self) -> None:
        if not isinstance(self._execution, PmxStructuralExecutionResult):
            raise TypeError(
                "_execution must be a PmxStructuralExecutionResult."
            )
        if type(self.expected_source_sha256_declared) is not bool:
            raise TypeError(
                "expected_source_sha256_declared must be a boolean."
            )
        if self.source_identity_status not in ("matched", "not_declared"):
            raise ValueError(
                "source_identity_status must be 'matched' or 'not_declared'."
            )
        if (
            self.expected_source_sha256_declared
            and self.source_identity_status != "matched"
        ):
            raise ValueError(
                "declared source identity must have matched status."
            )
        if (
            not self.expected_source_sha256_declared
            and self.source_identity_status != "not_declared"
        ):
            raise ValueError(
                "undeclared source identity must have not_declared status."
            )

    @property
    def status(self) -> str:
        """Return the released structural execution status."""

        return self._execution.status

    @property
    def output_size_bytes(self) -> int:
        """Return the committed output size without exposing a filesystem path."""

        return self._execution.output_size_bytes

    def to_dict(self) -> dict[str, object]:
        """Return committed evidence with raw source identity and paths removed."""

        report = self._execution.to_dict()
        report.pop("source", None)

        plan = report.get("plan")
        if not isinstance(plan, dict):
            raise RuntimeError("execution plan evidence must be a dictionary.")
        bounded_plan = dict(plan)
        plan_source = bounded_plan.get("source")
        if not isinstance(plan_source, dict):
            raise RuntimeError(
                "execution plan source evidence must be a dictionary."
            )
        bounded_plan_source = dict(plan_source)
        bounded_plan_source.pop("semantic_sha256", None)
        bounded_plan["source"] = bounded_plan_source
        report["plan"] = bounded_plan

        output = report.get("output")
        if not isinstance(output, dict):
            raise RuntimeError("execution output evidence must be a dictionary.")
        bounded_output = dict(output)
        bounded_output.pop("path", None)
        bounded_output.pop("sha256", None)
        report["output"] = bounded_output

        return {
            "source_identity": {
                "algorithm": "sha256",
                "expected_source_sha256_declared": (
                    self.expected_source_sha256_declared
                ),
                "status": self.source_identity_status,
            },
            **report,
        }


class _SourceIdentityMismatch(ValueError):
    """Internal marker for one captured raw-source identity mismatch."""


def _underlying_details(
    error: PmxServiceError,
) -> tuple[tuple[str, _DiagnosticDetail], ...]:
    details: list[tuple[str, _DiagnosticDetail]] = [
        ("cause_code", error.diagnostic.code.value),
        ("cause_operation", error.diagnostic.operation.value),
    ]
    for key, value in error.diagnostic.details:
        if (
            key in _SAFE_UNDERLYING_DETAIL_KEYS
            and (value is None or type(value) in (str, int, bool))
        ):
            details.append((key, value))
    return tuple(details)


def _service_error(
    error: Exception,
) -> PmxStructuralTransactionPlanApplyServiceError:
    operation = PmxStructuralTransactionPlanApplyServiceOperation.APPLY

    if isinstance(error, _SourceIdentityMismatch):
        diagnostic = PmxStructuralTransactionPlanApplyServiceDiagnostic(
            code=(
                PmxStructuralTransactionPlanApplyServiceDiagnosticCode
                .SOURCE_IDENTITY_MISMATCH
            ),
            operation=operation,
            message="Captured source SHA-256 does not match the authored plan.",
            details=(
                ("destination_published", False),
                ("expected_source_sha256_declared", True),
                ("source_parsed", False),
                ("source_snapshot_captured", True),
            ),
        )
    elif isinstance(error, PmxServiceError):
        code = error.diagnostic.code
        if code is PmxServiceDiagnosticCode.INVALID_ARGUMENT:
            local_code = (
                PmxStructuralTransactionPlanApplyServiceDiagnosticCode
                .INVALID_ARGUMENT
            )
            message = "Invalid structural transaction plan apply input."
        elif code in (
            PmxServiceDiagnosticCode.SOURCE_INVALID,
            PmxServiceDiagnosticCode.DOCUMENT_INVALID,
        ):
            local_code = (
                PmxStructuralTransactionPlanApplyServiceDiagnosticCode
                .SOURCE_INVALID
            )
            message = "Structural transaction apply source is invalid."
        elif code is PmxServiceDiagnosticCode.STRUCTURAL_PATH_UNSAFE:
            local_code = (
                PmxStructuralTransactionPlanApplyServiceDiagnosticCode
                .OUTPUT_PATH_UNSAFE
            )
            message = "Structural transaction output path is unsafe."
        elif code in (
            PmxServiceDiagnosticCode.STRUCTURAL_VERIFICATION_FAILED,
            PmxServiceDiagnosticCode.STRUCTURAL_PREVIEW_FAILED,
        ):
            local_code = (
                PmxStructuralTransactionPlanApplyServiceDiagnosticCode
                .EXECUTION_FAILED
            )
            message = "Structural transaction execution was blocked."
        elif code is PmxServiceDiagnosticCode.IO_FAILED:
            local_code = (
                PmxStructuralTransactionPlanApplyServiceDiagnosticCode
                .IO_FAILED
            )
            message = "Structural transaction filesystem operation failed."
        else:
            local_code = (
                PmxStructuralTransactionPlanApplyServiceDiagnosticCode
                .INTERNAL_ERROR
            )
            message = "Unexpected structural transaction plan apply failure."
        diagnostic = PmxStructuralTransactionPlanApplyServiceDiagnostic(
            code=local_code,
            operation=operation,
            message=message,
            details=_underlying_details(error),
        )
    else:
        diagnostic = PmxStructuralTransactionPlanApplyServiceDiagnostic(
            code=(
                PmxStructuralTransactionPlanApplyServiceDiagnosticCode
                .INTERNAL_ERROR
            ),
            operation=operation,
            message="Unexpected structural transaction plan apply failure.",
        )

    return PmxStructuralTransactionPlanApplyServiceError(diagnostic)


def apply_structural_transaction_plan(
    source: str | Path,
    output: str | Path,
    validated_plan: PmxStructuralTransactionPlanValidationResult,
    *,
    overwrite: bool = False,
) -> PmxStructuralTransactionPlanApplyResult:
    """Apply one validated authored plan through the released atomic authority."""

    failure_stage = "service_validation"
    source_bytes_read = False

    def record_stage(stage: str) -> None:
        nonlocal failure_stage, source_bytes_read
        _transaction_failure_provenance(stage)
        failure_stage = stage
        if stage == "source_parse":
            source_bytes_read = True

    try:
        if not isinstance(
            validated_plan,
            PmxStructuralTransactionPlanValidationResult,
        ):
            raise TypeError(
                "validated_plan must be a "
                "PmxStructuralTransactionPlanValidationResult."
            )
        if not isinstance(overwrite, bool):
            raise TypeError("overwrite must be a boolean.")

        expected_sha256 = validated_plan.plan.expected_source_sha256

        def validate_source_sha256(actual_sha256: str) -> None:
            if actual_sha256 != expected_sha256:
                raise _SourceIdentityMismatch

        validator = (
            validate_source_sha256
            if expected_sha256 is not None
            else None
        )

        raw_result = _write_structural_transaction_with_stage_callback(
            source,
            output,
            validated_plan.request,
            overwrite=overwrite,
            stage_callback=record_stage,
            _source_sha256_validator=validator,
        )
        execution = PmxStructuralExecutionResult(raw_result)
        return PmxStructuralTransactionPlanApplyResult(
            _execution=execution,
            expected_source_sha256_declared=expected_sha256 is not None,
            source_identity_status=(
                "matched" if expected_sha256 is not None else "not_declared"
            ),
        )
    except _SourceIdentityMismatch as error:
        failure = _service_error(error)
    except Exception as error:
        translated = _execution_service_error(
            error,
            failure_stage,
            source_bytes_read=source_bytes_read,
        )
        failure = _service_error(translated)
    raise failure from None


__all__ = (
    "PmxStructuralTransactionPlanApplyServiceOperation",
    "PmxStructuralTransactionPlanApplyServiceDiagnosticCode",
    "PmxStructuralTransactionPlanApplyServiceDiagnostic",
    "PmxStructuralTransactionPlanApplyServiceError",
    "PmxStructuralTransactionPlanApplyResult",
    "apply_structural_transaction_plan",
)
