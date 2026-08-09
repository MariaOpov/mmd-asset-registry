"""Immutable declarative PMX edit-plan model."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from mmd_registry.pmx.editing.operations import (
    PmxEditOperation,
    SUPPORTED_OPERATION_TYPES,
    operation_to_dict,
)


PMX_EDIT_PLAN_SCHEMA_VERSION: Final = 1
_LOWERCASE_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True, slots=True)
class PmxEditPlan:
    """One validated-shape sequence of deterministic PMX edit operations."""

    operations: tuple[PmxEditOperation, ...]
    schema_version: int = PMX_EDIT_PLAN_SCHEMA_VERSION
    expected_source_sha256: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.schema_version, int) or isinstance(
            self.schema_version,
            bool,
        ):
            raise TypeError("schema_version must be an integer.")
        if self.schema_version != PMX_EDIT_PLAN_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported edit-plan schema version {self.schema_version}; "
                f"expected {PMX_EDIT_PLAN_SCHEMA_VERSION}."
            )

        if not isinstance(self.operations, tuple):
            raise TypeError("operations must be a tuple.")
        if not self.operations:
            raise ValueError("operations must contain at least one operation.")
        if not all(
            isinstance(operation, SUPPORTED_OPERATION_TYPES)
            for operation in self.operations
        ):
            raise TypeError("operations contains an unsupported operation type.")

        if self.expected_source_sha256 is not None:
            if not isinstance(self.expected_source_sha256, str):
                raise TypeError("expected_source_sha256 must be a string.")
            if _LOWERCASE_SHA256.fullmatch(self.expected_source_sha256) is None:
                raise ValueError(
                    "expected_source_sha256 must be exactly 64 lowercase "
                    "hexadecimal characters."
                )

    def to_dict(self) -> dict[str, object]:
        """Return a stable JSON-compatible plan representation."""

        payload: dict[str, object] = {
            "schema_version": self.schema_version,
        }
        if self.expected_source_sha256 is not None:
            payload["expected_source_sha256"] = self.expected_source_sha256
        payload["operations"] = [
            operation_to_dict(operation) for operation in self.operations
        ]
        return payload
