"""Immutable declarative structural transaction-plan model and vocabulary."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, get_args

from mmd_registry.services import PmxStructuralCollectionEdit
from mmd_registry.services.structural_bone import PmxStructuralBoneInsertion
from mmd_registry.services.structural_material import PmxStructuralMaterialInsertion
from mmd_registry.services.structural_morph import PmxStructuralMorphInsertion
from mmd_registry.services.structural_rigid_body import PmxStructuralRigidBodyInsertion
from mmd_registry.services.structural_texture import PmxStructuralTextureInsertion
from mmd_registry.services.structural_transaction import (
    PmxStructuralTransactionOperation,
    PmxStructuralTransactionRequest,
)
from mmd_registry.services.structural_vertex import PmxStructuralVertexInsertion


PMX_STRUCTURAL_TRANSACTION_PLAN_SCHEMA_VERSION: Final = 1
_LOWERCASE_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class PmxStructuralTransactionOperationType(StrEnum):
    """Stable schema-one top-level ``op`` discriminator vocabulary."""

    TRANSFORM_COLLECTION = "transform_collection"
    INSERT_TEXTURE = "insert_texture"
    INSERT_MATERIAL = "insert_material"
    INSERT_BONE = "insert_bone"
    INSERT_MORPH = "insert_morph"
    INSERT_RIGID_BODY = "insert_rigid_body"
    INSERT_VERTEX = "insert_vertex"


@dataclass(frozen=True, slots=True)
class PmxStructuralTransactionOperationCatalogEntry:
    """One immutable JSON-facing top-level operation description."""

    operation_type: PmxStructuralTransactionOperationType
    purpose: str

    def __post_init__(self) -> None:
        if not isinstance(
            self.operation_type,
            PmxStructuralTransactionOperationType,
        ):
            raise TypeError(
                "operation_type must be a "
                "PmxStructuralTransactionOperationType value."
            )
        if type(self.purpose) is not str or not self.purpose:
            raise ValueError("purpose must be a non-empty string.")

    def to_dict(self) -> dict[str, str]:
        """Return a deterministic JSON-safe catalog entry."""

        return {
            "op": self.operation_type.value,
            "purpose": self.purpose,
        }


@dataclass(frozen=True, slots=True)
class PmxStructuralTransactionOperationCatalog:
    """Immutable catalog of schema-one transaction operation discriminators."""

    operations: tuple[PmxStructuralTransactionOperationCatalogEntry, ...]

    def __post_init__(self) -> None:
        if type(self.operations) is not tuple or not self.operations:
            raise ValueError("operations must be a non-empty tuple.")
        if not all(
            isinstance(
                operation,
                PmxStructuralTransactionOperationCatalogEntry,
            )
            for operation in self.operations
        ):
            raise TypeError(
                "operations must contain only "
                "PmxStructuralTransactionOperationCatalogEntry values."
            )
        discriminators = tuple(
            operation.operation_type for operation in self.operations
        )
        if len(set(discriminators)) != len(discriminators):
            raise ValueError("catalog operation discriminators must be unique.")

    def to_dict(self) -> dict[str, object]:
        """Return the deterministic JSON-ready catalog payload."""

        return {
            "schema_version": PMX_STRUCTURAL_TRANSACTION_PLAN_SCHEMA_VERSION,
            "operations": [operation.to_dict() for operation in self.operations],
        }


_OPERATION_TYPE_SPECS: Final = (
    (
        PmxStructuralTransactionOperationType.TRANSFORM_COLLECTION,
        PmxStructuralCollectionEdit,
        "Reorder or delete members of one supported PMX collection.",
    ),
    (
        PmxStructuralTransactionOperationType.INSERT_TEXTURE,
        PmxStructuralTextureInsertion,
        "Insert one texture path using a source-domain placement.",
    ),
    (
        PmxStructuralTransactionOperationType.INSERT_MATERIAL,
        PmxStructuralMaterialInsertion,
        "Insert one material using the released structural material DTO.",
    ),
    (
        PmxStructuralTransactionOperationType.INSERT_BONE,
        PmxStructuralBoneInsertion,
        "Insert one bone using the released structural bone and IK DTOs.",
    ),
    (
        PmxStructuralTransactionOperationType.INSERT_MORPH,
        PmxStructuralMorphInsertion,
        "Insert one morph using the released structural morph DTOs.",
    ),
    (
        PmxStructuralTransactionOperationType.INSERT_RIGID_BODY,
        PmxStructuralRigidBodyInsertion,
        "Insert one rigid body using the released structural rigid-body DTO.",
    ),
    (
        PmxStructuralTransactionOperationType.INSERT_VERTEX,
        PmxStructuralVertexInsertion,
        "Insert one vertex using the released structural deform DTOs.",
    ),
)

_OPERATION_TYPE_BY_DISCRIMINATOR: Final = {
    operation_type.value: dto_type
    for operation_type, dto_type, _purpose in _OPERATION_TYPE_SPECS
}

if tuple(dto_type for _op, dto_type, _purpose in _OPERATION_TYPE_SPECS) != get_args(
    PmxStructuralTransactionOperation
):
    raise RuntimeError(
        "transaction-plan discriminator catalog is out of sync with the "
        "released structural transaction operation union."
    )


def get_pmx_structural_transaction_operation_catalog(
) -> PmxStructuralTransactionOperationCatalog:
    """Return the schema-one operation catalog in frozen discriminator order."""

    return PmxStructuralTransactionOperationCatalog(
        operations=tuple(
            PmxStructuralTransactionOperationCatalogEntry(
                operation_type=operation_type,
                purpose=purpose,
            )
            for operation_type, _dto_type, purpose in _OPERATION_TYPE_SPECS
        )
    )


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
    "PmxStructuralTransactionOperationType",
    "PmxStructuralTransactionOperationCatalogEntry",
    "PmxStructuralTransactionOperationCatalog",
    "get_pmx_structural_transaction_operation_catalog",
    "PmxStructuralTransactionPlan",
)
