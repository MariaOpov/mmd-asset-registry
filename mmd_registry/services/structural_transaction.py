"""Public immutable request model for bounded structural transactions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from mmd_registry.services import (
    PmxReferenceTargetKind,
    PmxStructuralCollectionEdit,
)
from mmd_registry.services.structural_bone import PmxStructuralBoneInsertion
from mmd_registry.services.structural_material import (
    PmxStructuralMaterialInsertion,
)
from mmd_registry.services.structural_morph import PmxStructuralMorphInsertion
from mmd_registry.services.structural_rigid_body import (
    PmxStructuralRigidBodyInsertion,
)
from mmd_registry.services.structural_texture import PmxStructuralTextureInsertion
from mmd_registry.services.structural_vertex import PmxStructuralVertexInsertion


PmxStructuralTransactionOperation: TypeAlias = (
    PmxStructuralCollectionEdit
    | PmxStructuralTextureInsertion
    | PmxStructuralMaterialInsertion
    | PmxStructuralBoneInsertion
    | PmxStructuralMorphInsertion
    | PmxStructuralRigidBodyInsertion
    | PmxStructuralVertexInsertion
)


_TRANSACTION_OPERATION_TYPES: tuple[type[object], ...] = (
    PmxStructuralCollectionEdit,
    PmxStructuralTextureInsertion,
    PmxStructuralMaterialInsertion,
    PmxStructuralBoneInsertion,
    PmxStructuralMorphInsertion,
    PmxStructuralRigidBodyInsertion,
    PmxStructuralVertexInsertion,
)


@dataclass(frozen=True, slots=True)
class PmxStructuralTransactionRequest:
    """One ordered tuple of bounded structural transaction operations."""

    operations: tuple[PmxStructuralTransactionOperation, ...] = ()

    def __post_init__(self) -> None:
        if type(self.operations) is not tuple:
            raise TypeError("operations must be a tuple.")
        if not all(
            isinstance(operation, _TRANSACTION_OPERATION_TYPES)
            for operation in self.operations
        ):
            raise TypeError(
                "operations must contain only PmxStructuralCollectionEdit "
                "or supported structural insertion values."
            )

        seen_collection_kinds: set[PmxReferenceTargetKind] = set()
        seen_new_ids: set[str] = set()
        for operation in self.operations:
            if isinstance(operation, PmxStructuralCollectionEdit):
                if operation.target_kind in seen_collection_kinds:
                    raise ValueError(
                        "operations cannot repeat one "
                        "PmxStructuralCollectionEdit target_kind."
                    )
                seen_collection_kinds.add(operation.target_kind)
                continue

            new_id = operation.new_id
            if new_id is None:
                continue
            if new_id in seen_new_ids:
                raise ValueError(
                    f"request-local new_id {new_id!r} must be globally unique."
                )
            seen_new_ids.add(new_id)


__all__ = (
    "PmxStructuralTransactionOperation",
    "PmxStructuralTransactionRequest",
)
