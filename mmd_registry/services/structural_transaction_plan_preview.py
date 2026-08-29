"""Source-bound preview service for authored structural transaction plans."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import hashlib
import io
from pathlib import Path
import re
from typing import Final, Literal, TypeAlias

from mmd_registry.diagnostics import (
    PmxServiceDiagnosticCode,
    PmxServiceError,
)
from mmd_registry.pmx.document import PmxDocument
from mmd_registry.services.structural_transaction import (
    PmxStructuralTransactionPreviewResult,
    preview_structural_transaction,
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


class PmxStructuralTransactionPlanPreviewServiceOperation(StrEnum):
    """Stable CP17 preview-service operations."""

    PREVIEW = "preview_structural_transaction_plan"


class PmxStructuralTransactionPlanPreviewServiceDiagnosticCode(StrEnum):
    """Stable coarse-grained CP17 preview-service failure codes."""

    INVALID_ARGUMENT = "invalid_argument"
    SOURCE_IO_FAILED = "service_io_failed"
    SOURCE_INVALID = "source_invalid"
    SOURCE_IDENTITY_MISMATCH = "source_identity_mismatch"
    PREVIEW_FAILED = "structural_preview_failed"
    INTERNAL_ERROR = "service_internal_error"


@dataclass(frozen=True, slots=True)
class PmxStructuralTransactionPlanPreviewServiceDiagnostic:
    """One deterministic disclosure-safe CP17 preview diagnostic."""

    code: PmxStructuralTransactionPlanPreviewServiceDiagnosticCode
    operation: PmxStructuralTransactionPlanPreviewServiceOperation
    message: str
    details: tuple[tuple[str, _DiagnosticDetail], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(
            self.code,
            PmxStructuralTransactionPlanPreviewServiceDiagnosticCode,
        ):
            raise TypeError(
                "code must be a "
                "PmxStructuralTransactionPlanPreviewServiceDiagnosticCode."
            )
        if not isinstance(
            self.operation,
            PmxStructuralTransactionPlanPreviewServiceOperation,
        ):
            raise TypeError(
                "operation must be a "
                "PmxStructuralTransactionPlanPreviewServiceOperation."
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


class PmxStructuralTransactionPlanPreviewServiceError(RuntimeError):
    """Public CP17 failure carrying one disclosure-safe diagnostic."""

    def __init__(
        self,
        diagnostic: PmxStructuralTransactionPlanPreviewServiceDiagnostic,
    ) -> None:
        if not isinstance(
            diagnostic,
            PmxStructuralTransactionPlanPreviewServiceDiagnostic,
        ):
            raise TypeError(
                "diagnostic must be a "
                "PmxStructuralTransactionPlanPreviewServiceDiagnostic."
            )
        self.diagnostic = diagnostic
        super().__init__(diagnostic.message)

    def to_dict(self) -> dict[str, object]:
        """Return the wrapped diagnostic as a JSON-ready payload."""

        return self.diagnostic.to_dict()


@dataclass(frozen=True, slots=True)
class PmxStructuralTransactionPlanPreviewResult:
    """One source-bound wrapper around the released transaction preview."""

    _preview: PmxStructuralTransactionPreviewResult = field(repr=False)
    expected_source_sha256_declared: bool
    source_identity_status: _SourceIdentityStatus

    def __post_init__(self) -> None:
        if not isinstance(
            self._preview,
            PmxStructuralTransactionPreviewResult,
        ):
            raise TypeError(
                "_preview must be a PmxStructuralTransactionPreviewResult."
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
        """Return the released transaction preview status."""

        return self._preview.status

    @property
    def document(self) -> PmxDocument:
        """Return the released certified intended document."""

        return self._preview.document

    @property
    def plan_sha256(self) -> str:
        """Return the released semantic transaction-plan digest."""

        return self._preview.plan_sha256

    def to_dict(self) -> dict[str, object]:
        """Return source-identity status plus exact released preview evidence."""

        return {
            "source_identity": {
                "algorithm": "sha256",
                "expected_source_sha256_declared": (
                    self.expected_source_sha256_declared
                ),
                "status": self.source_identity_status,
            },
            **self._preview.to_dict(),
        }


class _SourceIdentityMismatch(ValueError):
    """Internal marker for one captured raw-source identity mismatch."""


def _capture_source_snapshot(source: str | Path) -> bytes:
    if not isinstance(source, (str, Path)):
        raise TypeError("source must be a string or Path.")
    with Path(source).open("rb") as file:
        snapshot = file.read()
    if type(snapshot) is not bytes:
        raise TypeError("source snapshot must be bytes.")
    return snapshot


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
) -> PmxStructuralTransactionPlanPreviewServiceError:
    operation = PmxStructuralTransactionPlanPreviewServiceOperation.PREVIEW

    if isinstance(error, _SourceIdentityMismatch):
        diagnostic = PmxStructuralTransactionPlanPreviewServiceDiagnostic(
            code=(
                PmxStructuralTransactionPlanPreviewServiceDiagnosticCode
                .SOURCE_IDENTITY_MISMATCH
            ),
            operation=operation,
            message="Captured source SHA-256 does not match the authored plan.",
            details=(
                ("expected_source_sha256_declared", True),
                ("preview_performed", False),
                ("source_parsed", False),
                ("source_snapshot_captured", True),
            ),
        )
    elif isinstance(error, OSError):
        details = (("errno", error.errno),) if type(error.errno) is int else ()
        diagnostic = PmxStructuralTransactionPlanPreviewServiceDiagnostic(
            code=(
                PmxStructuralTransactionPlanPreviewServiceDiagnosticCode
                .SOURCE_IO_FAILED
            ),
            operation=operation,
            message="Structural transaction preview source read failed.",
            details=details,
        )
    elif isinstance(error, PmxServiceError):
        code = error.diagnostic.code
        if code in (
            PmxServiceDiagnosticCode.SOURCE_INVALID,
            PmxServiceDiagnosticCode.DOCUMENT_INVALID,
        ):
            local_code = (
                PmxStructuralTransactionPlanPreviewServiceDiagnosticCode
                .SOURCE_INVALID
            )
            message = "Structural transaction preview source is invalid."
        elif code is PmxServiceDiagnosticCode.STRUCTURAL_PREVIEW_FAILED:
            local_code = (
                PmxStructuralTransactionPlanPreviewServiceDiagnosticCode
                .PREVIEW_FAILED
            )
            message = "Structural transaction preview was blocked."
        elif code is PmxServiceDiagnosticCode.INVALID_ARGUMENT:
            local_code = (
                PmxStructuralTransactionPlanPreviewServiceDiagnosticCode
                .INVALID_ARGUMENT
            )
            message = "Invalid structural transaction plan preview input."
        elif code is PmxServiceDiagnosticCode.IO_FAILED:
            local_code = (
                PmxStructuralTransactionPlanPreviewServiceDiagnosticCode
                .SOURCE_IO_FAILED
            )
            message = "Structural transaction preview source read failed."
        else:
            local_code = (
                PmxStructuralTransactionPlanPreviewServiceDiagnosticCode
                .INTERNAL_ERROR
            )
            message = "Unexpected structural transaction plan preview failure."
        diagnostic = PmxStructuralTransactionPlanPreviewServiceDiagnostic(
            code=local_code,
            operation=operation,
            message=message,
            details=_underlying_details(error),
        )
    elif isinstance(error, (TypeError, ValueError)):
        diagnostic = PmxStructuralTransactionPlanPreviewServiceDiagnostic(
            code=(
                PmxStructuralTransactionPlanPreviewServiceDiagnosticCode
                .INVALID_ARGUMENT
            ),
            operation=operation,
            message="Invalid structural transaction plan preview input.",
        )
    else:
        diagnostic = PmxStructuralTransactionPlanPreviewServiceDiagnostic(
            code=(
                PmxStructuralTransactionPlanPreviewServiceDiagnosticCode
                .INTERNAL_ERROR
            ),
            operation=operation,
            message="Unexpected structural transaction plan preview failure.",
        )
    return PmxStructuralTransactionPlanPreviewServiceError(diagnostic)


def preview_structural_transaction_plan(
    source: str | Path,
    validated_plan: PmxStructuralTransactionPlanValidationResult,
) -> PmxStructuralTransactionPlanPreviewResult:
    """Preview one validated authored plan against one captured raw PMX snapshot."""

    try:
        if not isinstance(
            validated_plan,
            PmxStructuralTransactionPlanValidationResult,
        ):
            raise TypeError(
                "validated_plan must be a "
                "PmxStructuralTransactionPlanValidationResult."
            )

        snapshot = _capture_source_snapshot(source)
        expected_sha256 = validated_plan.plan.expected_source_sha256
        source_identity_status: _SourceIdentityStatus = "not_declared"
        if expected_sha256 is not None:
            actual_sha256 = hashlib.sha256(snapshot).hexdigest()
            if actual_sha256 != expected_sha256:
                raise _SourceIdentityMismatch
            source_identity_status = "matched"

        import mmd_registry.services as service_root

        document = service_root.load_document(io.BytesIO(snapshot))
        preview = preview_structural_transaction(
            document,
            validated_plan.request,
        )
        return PmxStructuralTransactionPlanPreviewResult(
            _preview=preview,
            expected_source_sha256_declared=expected_sha256 is not None,
            source_identity_status=source_identity_status,
        )
    except Exception as error:
        failure = _service_error(error)
    raise failure from None


__all__ = (
    "PmxStructuralTransactionPlanPreviewServiceOperation",
    "PmxStructuralTransactionPlanPreviewServiceDiagnosticCode",
    "PmxStructuralTransactionPlanPreviewServiceDiagnostic",
    "PmxStructuralTransactionPlanPreviewServiceError",
    "PmxStructuralTransactionPlanPreviewResult",
    "preview_structural_transaction_plan",
)
