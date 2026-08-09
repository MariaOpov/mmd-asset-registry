"""Immutable deterministic audit records for PMX edit previews."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, TypeAlias


PmxEditCategory: TypeAlias = Literal["model", "texture", "material"]
PmxAuditValue: TypeAlias = str | int | float | tuple[float, ...]


def _is_plain_int(value: object) -> bool:
    """Return whether a value is an integer but not a boolean."""

    return isinstance(value, int) and not isinstance(value, bool)


def _validate_audit_value(value: object, field_name: str) -> None:
    """Require one supported typed before/after audit value."""

    if isinstance(value, bool):
        raise TypeError(f"{field_name} cannot be a boolean.")
    if isinstance(value, (str, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{field_name} must be finite.")
        return
    if isinstance(value, tuple) and all(
        isinstance(item, float) and math.isfinite(item) for item in value
    ):
        return
    raise TypeError(
        f"{field_name} must be a string, integer, float, or tuple of floats."
    )


def _audit_value_to_json(value: PmxAuditValue) -> object:
    """Convert one immutable audit value to stable JSON-compatible data."""

    if isinstance(value, tuple):
        return list(value)
    return value


@dataclass(frozen=True, slots=True)
class PmxEditChange:
    """One effective typed field change produced by one operation."""

    category: PmxEditCategory
    target_index: int | None
    target_name: str | None
    field_path: str
    before: PmxAuditValue
    after: PmxAuditValue
    operation_index: int

    def __post_init__(self) -> None:
        if self.category not in ("model", "texture", "material"):
            raise ValueError(
                "category must be 'model', 'texture', or 'material'."
            )

        if self.category == "model":
            if self.target_index is not None:
                raise ValueError("model changes cannot have a target_index.")
        else:
            if not _is_plain_int(self.target_index):
                raise TypeError(
                    "texture and material target_index must be an integer."
                )
            if self.target_index < 0:
                raise ValueError("target_index cannot be negative.")

        if self.target_name is not None and not isinstance(self.target_name, str):
            raise TypeError("target_name must be a string when provided.")
        if not isinstance(self.field_path, str) or not self.field_path:
            raise ValueError("field_path must be a non-empty string.")
        if not _is_plain_int(self.operation_index):
            raise TypeError("operation_index must be an integer.")
        if self.operation_index < 0:
            raise ValueError("operation_index cannot be negative.")

        _validate_audit_value(self.before, "before")
        _validate_audit_value(self.after, "after")
        if self.before == self.after:
            raise ValueError("audit changes must contain different values.")

    def to_dict(self) -> dict[str, object]:
        """Return the stable JSON-compatible change representation."""

        return {
            "category": self.category,
            "target_index": self.target_index,
            "target_name": self.target_name,
            "field_path": self.field_path,
            "before": _audit_value_to_json(self.before),
            "after": _audit_value_to_json(self.after),
            "operation_index": self.operation_index,
        }


@dataclass(frozen=True, slots=True)
class PmxEditAudit:
    """Stable ordered collection of effective PMX field changes."""

    changes: tuple[PmxEditChange, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.changes, tuple):
            raise TypeError("changes must be a tuple.")
        if not all(isinstance(change, PmxEditChange) for change in self.changes):
            raise TypeError("changes must contain only PmxEditChange records.")

        previous_operation_index = -1
        field_paths: set[str] = set()
        for change in self.changes:
            if change.operation_index < previous_operation_index:
                raise ValueError(
                    "changes must be ordered by nondecreasing operation_index."
                )
            if change.field_path in field_paths:
                raise ValueError(
                    f"changes contains duplicate field path {change.field_path}."
                )
            previous_operation_index = change.operation_index
            field_paths.add(change.field_path)

    @property
    def changed_fields(self) -> int:
        """Return the number of effective field changes."""

        return len(self.changes)

    def category_count(self, category: PmxEditCategory) -> int:
        """Return the effective field count for one edit category."""

        if category not in ("model", "texture", "material"):
            raise ValueError(
                "category must be 'model', 'texture', or 'material'."
            )
        return sum(change.category == category for change in self.changes)

    def to_dict(self) -> dict[str, object]:
        """Return a deterministic JSON-compatible audit representation."""

        return {
            "summary": {
                "changed_fields": self.changed_fields,
                "model_fields": self.category_count("model"),
                "texture_fields": self.category_count("texture"),
                "material_fields": self.category_count("material"),
            },
            "changes": [change.to_dict() for change in self.changes],
        }
