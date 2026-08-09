"""Contextual failures for declarative PMX edit plans."""

from __future__ import annotations


class PmxEditPlanError(ValueError):
    """One validation failure in an immutable PMX edit plan."""

    def __init__(
        self,
        reason: str,
        *,
        operation_index: int | None = None,
        field: str | None = None,
    ) -> None:
        if not isinstance(reason, str) or not reason:
            raise ValueError("reason must be a non-empty string.")
        if operation_index is not None and (
            not isinstance(operation_index, int)
            or isinstance(operation_index, bool)
            or operation_index < 0
        ):
            raise ValueError("operation_index must be a nonnegative integer.")
        if field is not None and (not isinstance(field, str) or not field):
            raise ValueError("field must be a non-empty string when provided.")

        location = "edit plan"
        if operation_index is not None:
            location = f"operations[{operation_index}]"
        if field is not None:
            location = f"{location}.{field}"

        self.reason = reason
        self.operation_index = operation_index
        self.field = field
        super().__init__(f"Invalid PMX edit plan at {location}: {reason}")


class PmxEditVerificationError(RuntimeError):
    """Raised when an edited PMX fails semantic or source verification."""


class PmxEditPathError(ValueError):
    """Raised when edit input/output paths violate safe-write policy."""
