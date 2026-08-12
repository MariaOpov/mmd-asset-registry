"""Deterministic authoring catalog for supported PMX edit operations."""

from __future__ import annotations

from dataclasses import dataclass

from mmd_registry.pmx.editing.operations import (
    PmxEditEffectKind,
    PmxEditFieldSpec,
    PmxEditOperationMetadata,
    PmxEditTargetKind,
    SUPPORTED_OPERATION_TYPES,
)


@dataclass(frozen=True, slots=True)
class PmxEditOperationCatalogEntry:
    """One stable authoring description derived from a supported operation."""

    operation_type: str
    purpose: str
    target_kind: PmxEditTargetKind
    effect_kind: PmxEditEffectKind
    fields: tuple[PmxEditFieldSpec, ...]
    constraints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.operation_type) is not str or not self.operation_type:
            raise ValueError("operation_type must be a non-empty string.")
        if type(self.purpose) is not str or not self.purpose:
            raise ValueError("purpose must be a non-empty string.")
        if not isinstance(self.target_kind, PmxEditTargetKind):
            raise TypeError("target_kind must be a PmxEditTargetKind value.")
        if not isinstance(self.effect_kind, PmxEditEffectKind):
            raise TypeError("effect_kind must be a PmxEditEffectKind value.")
        if type(self.fields) is not tuple or not self.fields:
            raise ValueError("fields must be a non-empty tuple.")
        if not all(isinstance(field, PmxEditFieldSpec) for field in self.fields):
            raise TypeError("fields must contain only PmxEditFieldSpec values.")
        if len({field.name for field in self.fields}) != len(self.fields):
            raise ValueError("catalog field names must be unique.")
        if type(self.constraints) is not tuple:
            raise TypeError("constraints must be a tuple.")

    @property
    def required_fields(self) -> tuple[str, ...]:
        """Return required payload fields in stable declaration order."""

        return tuple(field.name for field in self.fields if field.required)

    @property
    def optional_fields(self) -> tuple[str, ...]:
        """Return optional payload fields in stable declaration order."""

        return tuple(field.name for field in self.fields if not field.required)

    def to_dict(self) -> dict[str, object]:
        """Return one deterministic JSON-ready catalog record."""

        return {
            "type": self.operation_type,
            "purpose": self.purpose,
            "target_kind": self.target_kind.value,
            "effect_kind": self.effect_kind.value,
            "required_fields": list(self.required_fields),
            "optional_fields": list(self.optional_fields),
            "fields": [field.to_dict() for field in self.fields],
            "constraints": list(self.constraints),
        }


@dataclass(frozen=True, slots=True)
class PmxEditOperationCatalog:
    """Immutable deterministic catalog of the currently supported operations."""

    operations: tuple[PmxEditOperationCatalogEntry, ...]

    def __post_init__(self) -> None:
        if type(self.operations) is not tuple or not self.operations:
            raise ValueError("operations must be a non-empty tuple.")
        if not all(
            isinstance(operation, PmxEditOperationCatalogEntry)
            for operation in self.operations
        ):
            raise TypeError(
                "operations must contain only PmxEditOperationCatalogEntry values."
            )
        operation_types = tuple(
            operation.operation_type for operation in self.operations
        )
        if len(set(operation_types)) != len(operation_types):
            raise ValueError("catalog operation types must be unique.")

    def to_dict(self) -> dict[str, object]:
        """Return the stable JSON-ready catalog payload."""

        return {
            "operations": [operation.to_dict() for operation in self.operations],
        }


def _entry_from_operation_type(
    operation_type: type[object],
) -> PmxEditOperationCatalogEntry:
    """Build one catalog entry from authoritative operation-class metadata."""

    operation_name = getattr(operation_type, "operation_name", None)
    metadata = getattr(operation_type, "catalog_metadata", None)
    if type(operation_name) is not str or not operation_name:
        raise TypeError(
            "supported operation types must define a non-empty operation_name."
        )
    if not isinstance(metadata, PmxEditOperationMetadata):
        raise TypeError(
            f"supported operation {operation_name!r} must define catalog_metadata."
        )
    return PmxEditOperationCatalogEntry(
        operation_type=operation_name,
        purpose=metadata.purpose,
        target_kind=metadata.target_kind,
        effect_kind=metadata.effect_kind,
        fields=metadata.fields,
        constraints=metadata.constraints,
    )


def get_pmx_edit_operation_catalog() -> PmxEditOperationCatalog:
    """Return the catalog in the authoritative supported-operation order."""

    return PmxEditOperationCatalog(
        operations=tuple(
            _entry_from_operation_type(operation_type)
            for operation_type in SUPPORTED_OPERATION_TYPES
        )
    )
