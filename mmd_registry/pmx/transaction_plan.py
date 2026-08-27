"""Immutable declarative structural transaction-plan model."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from mmd_registry.services.structural_transaction import (
    PmxStructuralTransactionOperation,
    PmxStructuralTransactionRequest,
)


PMX_STRUCTURAL_TRANSACTION_PLAN_SCHEMA_VERSION: Final = 1
_LOWERCASE_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True, slots=True)
class PmxStructuralTransactionPlan:
    """One immutable user-authored structural transaction plan."""

    operations: tuple[PmxStructuralTransactionOperation, ...]
    schema_version: int = PMX_STRUCTURAL_TRANSACTION_PLAN_SCHEMA_VERSION
    expected_source_sha256: str | None = None

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int:
            raise TypeError("schema_version must be an integer.")
        if self.schema_version != PMX_STRUCTURAL_TRANSACTION_PLAN_SCHEMA_VERSION:
            raise ValueError(
                "Unsupported structural transaction-plan schema version "
                f"{self.schema_version}; expected "
                f"{PMX_STRUCTURAL_TRANSACTION_PLAN_SCHEMA_VERSION}."
            )

        if type(self.operations) is not tuple:
            raise TypeError("operations must be a tuple.")

        # Reuse the released v0.9.3 request authority for operation-shape,
        # duplicate collection-target, and request-local new_id validation.
        PmxStructuralTransactionRequest(operations=self.operations)

        if self.expected_source_sha256 is not None:
            if not isinstance(self.expected_source_sha256, str):
                raise TypeError("expected_source_sha256 must be a string.")
            if _LOWERCASE_SHA256.fullmatch(self.expected_source_sha256) is None:
                raise ValueError(
                    "expected_source_sha256 must be exactly 64 lowercase "
                    "hexadecimal characters."
                )


__all__ = (
    "PMX_STRUCTURAL_TRANSACTION_PLAN_SCHEMA_VERSION",
    "PmxStructuralTransactionPlan",
)
