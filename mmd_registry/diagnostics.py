"""Public structured failures for reusable PMX service clients."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, TypeAlias

from mmd_registry.binary_reader import BinaryParseError
from mmd_registry.pmx.editing.errors import (
    PmxEditPathError,
    PmxEditPlanError,
    PmxEditVerificationError,
)
from mmd_registry.pmx.errors import PmxValidationError


_DETAIL_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"[a-z][a-z0-9_]*\Z"
)

_DiagnosticDetail: TypeAlias = str | int | bool | None


class PmxServiceOperation(StrEnum):
    """Current reusable PMX service operations that may report failures."""

    LOAD_DOCUMENT = "load_document"
    INSPECT_DOCUMENT = "inspect_document"
    VALIDATE_DOCUMENT = "validate_document"
    ANALYZE_REFERENCES = "analyze_references"
    ANALYZE_REFERENCE_NODE = "analyze_reference_node"
    PREVIEW_EDIT = "preview_edit"
    APPLY_EDIT = "apply_edit"
    PREVIEW_STRUCTURAL_EDIT = "preview_structural_edit"
    APPLY_STRUCTURAL_EDIT = "apply_structural_edit"


class PmxServiceDiagnosticCode(StrEnum):
    """Stable coarse-grained codes for public PMX service failures."""

    INVALID_ARGUMENT = "invalid_argument"
    IO_FAILED = "service_io_failed"
    SOURCE_INVALID = "source_invalid"
    DOCUMENT_INVALID = "document_invalid"
    EDIT_PLAN_INVALID = "edit_plan_invalid"
    EDIT_PATH_UNSAFE = "edit_path_unsafe"
    EDIT_VERIFICATION_FAILED = "edit_verification_failed"
    STRUCTURAL_PREVIEW_FAILED = "structural_preview_failed"
    STRUCTURAL_PATH_UNSAFE = "structural_path_unsafe"
    STRUCTURAL_VERIFICATION_FAILED = "structural_verification_failed"
    INTERNAL_ERROR = "service_internal_error"


@dataclass(frozen=True, slots=True)
class PmxServiceDiagnostic:
    """One immutable deterministic diagnostic safe for service consumers."""

    code: PmxServiceDiagnosticCode
    operation: PmxServiceOperation
    message: str
    details: tuple[tuple[str, _DiagnosticDetail], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.code, PmxServiceDiagnosticCode):
            raise TypeError("code must be a PmxServiceDiagnosticCode value.")
        if not isinstance(self.operation, PmxServiceOperation):
            raise TypeError("operation must be a PmxServiceOperation value.")
        if type(self.message) is not str or not self.message:
            raise ValueError("message must be a non-empty string.")
        if type(self.details) is not tuple:
            raise TypeError("details must be a tuple of key/value pairs.")

        seen_keys: set[str] = set()
        for item in self.details:
            if type(item) is not tuple or len(item) != 2:
                raise TypeError("each diagnostic detail must be one key/value tuple.")
            key, value = item
            if type(key) is not str or _DETAIL_KEY_PATTERN.fullmatch(key) is None:
                raise ValueError(
                    "diagnostic detail keys must use lowercase snake_case."
                )
            if key in seen_keys:
                raise ValueError(f"duplicate diagnostic detail key {key!r}.")
            seen_keys.add(key)
            if value is not None and type(value) not in (str, int, bool):
                raise TypeError(
                    "diagnostic detail values must be strings, integers, "
                    "booleans, or None."
                )

    def to_dict(self) -> dict[str, object]:
        """Return a deterministic JSON-ready failure payload."""

        payload: dict[str, object] = {
            "code": self.code.value,
            "operation": self.operation.value,
            "message": self.message,
        }
        if self.details:
            payload["details"] = dict(sorted(self.details))
        return payload


class PmxServiceError(RuntimeError):
    """Exception wrapper carrying one safe structured service diagnostic."""

    def __init__(self, diagnostic: PmxServiceDiagnostic) -> None:
        if not isinstance(diagnostic, PmxServiceDiagnostic):
            raise TypeError("diagnostic must be a PmxServiceDiagnostic instance.")
        self.diagnostic = diagnostic
        super().__init__(diagnostic.message)

    def to_dict(self) -> dict[str, object]:
        """Return the wrapped diagnostic as a JSON-ready payload."""

        return self.diagnostic.to_dict()


def _diagnostic(
    operation: PmxServiceOperation,
    code: PmxServiceDiagnosticCode,
    message: str,
    details: tuple[tuple[str, _DiagnosticDetail], ...] = (),
) -> PmxServiceDiagnostic:
    """Build one public diagnostic from already-sanitized fields."""

    return PmxServiceDiagnostic(
        code=code,
        operation=operation,
        message=message,
        details=details,
    )


def diagnostic_from_service_error(
    operation: PmxServiceOperation,
    error: Exception,
) -> PmxServiceDiagnostic:
    """Map an allowlisted failure without exposing exception representation."""

    if not isinstance(operation, PmxServiceOperation):
        raise TypeError("operation must be a PmxServiceOperation value.")
    if not isinstance(error, Exception):
        raise TypeError("error must be an exception instance.")

    if isinstance(error, BinaryParseError):
        details: tuple[tuple[str, _DiagnosticDetail], ...] = (
            ("format_name", error.format_name),
            ("section", error.section),
            ("record_index", error.record_index),
            ("offset", error.offset),
            ("parse_operation", error.operation),
        )
        return _diagnostic(
            operation,
            PmxServiceDiagnosticCode.SOURCE_INVALID,
            "Source PMX data is invalid.",
            details,
        )

    if isinstance(error, PmxValidationError):
        issue = error.issue
        return _diagnostic(
            operation,
            PmxServiceDiagnosticCode.DOCUMENT_INVALID,
            issue.message,
            (
                ("section", issue.section),
                ("record_index", issue.record_index),
                ("field", issue.field),
                ("reason", issue.reason),
            ),
        )

    if isinstance(error, PmxEditPlanError):
        return _diagnostic(
            operation,
            PmxServiceDiagnosticCode.EDIT_PLAN_INVALID,
            error.reason,
            (
                ("operation_index", error.operation_index),
                ("operation_type", error.operation_type),
                ("field", error.field),
            ),
        )

    if isinstance(error, PmxEditPathError):
        return _diagnostic(
            operation,
            PmxServiceDiagnosticCode.EDIT_PATH_UNSAFE,
            "Edit path failed safety validation.",
        )

    if isinstance(error, PmxEditVerificationError):
        return _diagnostic(
            operation,
            PmxServiceDiagnosticCode.EDIT_VERIFICATION_FAILED,
            "PMX edit verification failed.",
        )

    if (
        operation is PmxServiceOperation.PREVIEW_STRUCTURAL_EDIT
        and isinstance(error, ValueError)
    ):
        return _diagnostic(
            operation,
            PmxServiceDiagnosticCode.STRUCTURAL_PREVIEW_FAILED,
            "Structural preview failed reference-safety validation.",
        )

    if operation is PmxServiceOperation.APPLY_STRUCTURAL_EDIT:
        # Keep the structural-output dependency lazy so importing the public
        # diagnostics/service namespaces does not load the writer kernel.
        from mmd_registry.pmx.structural_output import (
            PmxStructuralOutputPathError,
            PmxStructuralOutputVerificationError,
        )

        if isinstance(error, PmxStructuralOutputPathError):
            return _diagnostic(
                operation,
                PmxServiceDiagnosticCode.STRUCTURAL_PATH_UNSAFE,
                "Structural output path failed safety validation.",
            )
        if isinstance(error, PmxStructuralOutputVerificationError):
            return _diagnostic(
                operation,
                PmxServiceDiagnosticCode.STRUCTURAL_VERIFICATION_FAILED,
                "Structural output verification failed.",
            )
        if isinstance(error, ValueError):
            return _diagnostic(
                operation,
                PmxServiceDiagnosticCode.STRUCTURAL_VERIFICATION_FAILED,
                "Structural execution failed reference-safety validation.",
            )

    if isinstance(error, OSError):
        details = (("errno", error.errno),) if type(error.errno) is int else ()
        return _diagnostic(
            operation,
            PmxServiceDiagnosticCode.IO_FAILED,
            "Service file operation failed.",
            details,
        )

    if isinstance(error, (TypeError, ValueError)):
        return _diagnostic(
            operation,
            PmxServiceDiagnosticCode.INVALID_ARGUMENT,
            "Invalid service input.",
        )

    return _diagnostic(
        operation,
        PmxServiceDiagnosticCode.INTERNAL_ERROR,
        "Unexpected internal service failure.",
    )


__all__ = (
    "PmxServiceDiagnostic",
    "PmxServiceDiagnosticCode",
    "PmxServiceError",
    "PmxServiceOperation",
    "diagnostic_from_service_error",
)
