"""Stable structured diagnostics for declarative PMX editing failures."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, TypeAlias

from mmd_registry.pmx.editing.errors import PmxEditPlanError


_CODE_PATTERN: Final[re.Pattern[str]] = re.compile(r"[a-z][a-z0-9_]*\Z")
_OPERATION_TYPE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"[a-z][a-z0-9_]*\Z"
)
_SIMPLE_FIELD_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*(?:\[[0-9]+\])*\Z"
)
_DETAIL_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(r"[a-z][a-z0-9_]*\Z")

PmxEditDiagnosticDetail: TypeAlias = str | int | bool | None


class PmxEditPhase(StrEnum):
    """Stable PMX edit-pipeline phases exposed to automation."""

    PLAN_READ = "plan_read"
    PLAN_DECODE = "plan_decode"
    PLAN_VALIDATE = "plan_validate"
    SOURCE_READ = "source_read"
    SOURCE_PARSE = "source_parse"
    PREFLIGHT = "preflight"
    APPLY = "apply"
    DOCUMENT_VALIDATE = "document_validate"
    SERIALIZE = "serialize"
    REPARSE = "reparse"
    SEMANTIC_VERIFY = "semantic_verify"
    OUTPUT_COMMIT = "output_commit"
    INTERNAL = "internal"


class PmxEditDiagnosticCode(StrEnum):
    """Stable coarse-grained failure codes for the edit pipeline."""

    PLAN_READ_FAILED = "edit_plan_read_failed"
    PLAN_DECODE_FAILED = "edit_plan_decode_failed"
    PLAN_INVALID = "edit_plan_invalid"
    SOURCE_READ_FAILED = "source_read_failed"
    SOURCE_INVALID = "source_invalid"
    PREFLIGHT_FAILED = "edit_preflight_failed"
    APPLY_FAILED = "edit_apply_failed"
    DOCUMENT_INVALID = "edited_document_invalid"
    SERIALIZE_FAILED = "edit_serialize_failed"
    REPARSE_FAILED = "edit_reparse_failed"
    SEMANTIC_VERIFY_FAILED = "edit_verification_failed"
    OUTPUT_COMMIT_FAILED = "output_commit_failed"
    INTERNAL_ERROR = "edit_internal_error"


_DEFAULT_CODE_BY_PHASE: Final[dict[PmxEditPhase, PmxEditDiagnosticCode]] = {
    PmxEditPhase.PLAN_READ: PmxEditDiagnosticCode.PLAN_READ_FAILED,
    PmxEditPhase.PLAN_DECODE: PmxEditDiagnosticCode.PLAN_DECODE_FAILED,
    PmxEditPhase.PLAN_VALIDATE: PmxEditDiagnosticCode.PLAN_INVALID,
    PmxEditPhase.SOURCE_READ: PmxEditDiagnosticCode.SOURCE_READ_FAILED,
    PmxEditPhase.SOURCE_PARSE: PmxEditDiagnosticCode.SOURCE_INVALID,
    PmxEditPhase.PREFLIGHT: PmxEditDiagnosticCode.PREFLIGHT_FAILED,
    PmxEditPhase.APPLY: PmxEditDiagnosticCode.APPLY_FAILED,
    PmxEditPhase.DOCUMENT_VALIDATE: PmxEditDiagnosticCode.DOCUMENT_INVALID,
    PmxEditPhase.SERIALIZE: PmxEditDiagnosticCode.SERIALIZE_FAILED,
    PmxEditPhase.REPARSE: PmxEditDiagnosticCode.REPARSE_FAILED,
    PmxEditPhase.SEMANTIC_VERIFY: PmxEditDiagnosticCode.SEMANTIC_VERIFY_FAILED,
    PmxEditPhase.OUTPUT_COMMIT: PmxEditDiagnosticCode.OUTPUT_COMMIT_FAILED,
    PmxEditPhase.INTERNAL: PmxEditDiagnosticCode.INTERNAL_ERROR,
}


@dataclass(frozen=True, slots=True)
class PmxEditDiagnostic:
    """One immutable, deterministic, automation-safe edit diagnostic."""

    code: PmxEditDiagnosticCode
    phase: PmxEditPhase
    message: str
    operation_index: int | None = None
    operation_type: str | None = None
    path: str | None = None
    details: tuple[tuple[str, PmxEditDiagnosticDetail], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.code, PmxEditDiagnosticCode):
            raise TypeError("code must be a PmxEditDiagnosticCode value.")
        if _CODE_PATTERN.fullmatch(self.code.value) is None:
            raise ValueError("diagnostic code must use lowercase snake_case.")
        if not isinstance(self.phase, PmxEditPhase):
            raise TypeError("phase must be a PmxEditPhase value.")
        if type(self.message) is not str or not self.message:
            raise ValueError("message must be a non-empty string.")
        if self.operation_index is not None:
            if type(self.operation_index) is not int:
                raise TypeError("operation_index must be an integer when provided.")
            if self.operation_index < 0:
                raise ValueError("operation_index cannot be negative.")
        if self.operation_type is not None:
            if type(self.operation_type) is not str:
                raise TypeError("operation_type must be a string when provided.")
            if _OPERATION_TYPE_PATTERN.fullmatch(self.operation_type) is None:
                raise ValueError(
                    "operation_type must use lowercase snake_case when provided."
                )
        if self.path is not None:
            if type(self.path) is not str or not self.path:
                raise ValueError("path must be a non-empty string when provided.")
            if not self.path.startswith("$"):
                raise ValueError("path must be rooted at '$' when provided.")
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
        """Return a deterministic JSON-ready diagnostic payload."""

        payload: dict[str, object] = {
            "code": self.code.value,
            "phase": self.phase.value,
            "message": self.message,
        }
        if self.operation_index is not None:
            payload["operation_index"] = self.operation_index
        if self.operation_type is not None:
            payload["operation_type"] = self.operation_type
        if self.path is not None:
            payload["path"] = self.path
        if self.details:
            payload["details"] = dict(sorted(self.details))
        return payload


def default_diagnostic_code(phase: PmxEditPhase) -> PmxEditDiagnosticCode:
    """Return the stable default failure code for one pipeline phase."""

    if not isinstance(phase, PmxEditPhase):
        raise TypeError("phase must be a PmxEditPhase value.")
    return _DEFAULT_CODE_BY_PHASE[phase]


def build_edit_plan_json_path(
    *,
    operation_index: int | None = None,
    field: str | None = None,
) -> str:
    """Build one deterministic JSON path for edit-plan error context."""

    if operation_index is not None:
        if type(operation_index) is not int:
            raise TypeError("operation_index must be an integer when provided.")
        if operation_index < 0:
            raise ValueError("operation_index cannot be negative.")
    if field is not None and (type(field) is not str or not field):
        raise ValueError("field must be a non-empty string when provided.")

    path = "$"
    if operation_index is not None:
        path += f".operations[{operation_index}]"
    if field is None:
        return path
    if _SIMPLE_FIELD_PATTERN.fullmatch(field) is not None:
        return f"{path}.{field}"
    return f"{path}[{json.dumps(field, ensure_ascii=False)}]"


def diagnostic_from_plan_error(
    error: PmxEditPlanError,
    *,
    phase: PmxEditPhase,
    operation_type: str | None = None,
) -> PmxEditDiagnostic:
    """Convert one plan error using only its stable contextual fields."""

    if not isinstance(error, PmxEditPlanError):
        raise TypeError("error must be a PmxEditPlanError instance.")

    path = None
    if error.operation_index is not None or error.field is not None:
        path = build_edit_plan_json_path(
            operation_index=error.operation_index,
            field=error.field,
        )

    return PmxEditDiagnostic(
        code=default_diagnostic_code(phase),
        phase=phase,
        message=error.reason,
        operation_index=error.operation_index,
        operation_type=operation_type,
        path=path,
    )


def render_pmx_edit_diagnostic_text(diagnostic: PmxEditDiagnostic) -> str:
    """Render one compact deterministic human-readable diagnostic."""

    if not isinstance(diagnostic, PmxEditDiagnostic):
        raise TypeError("diagnostic must be a PmxEditDiagnostic instance.")

    context: list[str] = []
    if diagnostic.operation_index is not None:
        context.append(f"operation={diagnostic.operation_index}")
    if diagnostic.operation_type is not None:
        context.append(f"type={diagnostic.operation_type}")
    if diagnostic.path is not None:
        context.append(f"path={diagnostic.path}")

    prefix = f"{diagnostic.phase.value}/{diagnostic.code.value}"
    if context:
        prefix += " [" + ", ".join(context) + "]"
    return f"{prefix}: {diagnostic.message}\n"


def render_pmx_edit_diagnostic_json(
    diagnostic: PmxEditDiagnostic,
    *,
    indent: int | None = 2,
) -> str:
    """Render one deterministic Unicode-safe JSON diagnostic."""

    if not isinstance(diagnostic, PmxEditDiagnostic):
        raise TypeError("diagnostic must be a PmxEditDiagnostic instance.")
    if indent is not None:
        if type(indent) is not int:
            raise TypeError("indent must be an integer or None.")
        if indent < 0:
            raise ValueError("indent cannot be negative.")
    return (
        json.dumps(
            diagnostic.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            indent=indent,
        )
        + "\n"
    )
