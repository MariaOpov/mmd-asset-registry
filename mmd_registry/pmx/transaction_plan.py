"""Immutable declarative structural transaction-plan model and vocabulary."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Final, get_args

from mmd_registry.services import (
    PmxReferenceTargetKind,
    PmxStructuralCollectionEdit,
)
from mmd_registry.services.structural_bone import PmxStructuralBoneInsertion
from mmd_registry.services.structural_material import PmxStructuralMaterialInsertion
from mmd_registry.services.structural_morph import PmxStructuralMorphInsertion
from mmd_registry.services.structural_reference import PmxStructuralNewReference
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

_OPERATION_TYPE_BY_DISCRIMINATOR: Final = MappingProxyType(
    {
        operation_type.value: dto_type
        for operation_type, dto_type, _purpose in _OPERATION_TYPE_SPECS
    }
)

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


_TOP_LEVEL_FIELDS: Final[frozenset[str]] = frozenset(
    {"schema_version", "expected_source_sha256", "operations"}
)
_TRANSFORM_COLLECTION_FIELDS: Final[frozenset[str]] = frozenset(
    {"op", "target_kind", "old_indices_in_new_order"}
)
_INSERT_TEXTURE_FIELDS: Final[frozenset[str]] = frozenset(
    {"op", "path", "position", "source_index", "new_id"}
)
_INSERT_MATERIAL_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "op",
        "local_name",
        "universal_name",
        "memo",
        "texture_index",
        "sphere_texture_index",
        "sphere_mode",
        "toon_reference_mode",
        "toon_reference_index",
        "diffuse",
        "specular",
        "specular_strength",
        "ambient",
        "drawing_flags",
        "edge_color",
        "edge_scale",
        "position",
        "source_index",
        "new_id",
    }
)
_NEW_REFERENCE_FIELDS: Final[frozenset[str]] = frozenset(
    {"ref", "target_kind", "new_id"}
)
_COLLECTION_TARGET_KINDS: Final[tuple[str, ...]] = (
    "vertex",
    "texture",
    "material",
    "bone",
    "morph",
    "rigid_body",
)


class PmxStructuralTransactionPlanError(ValueError):
    """One contextual failure in a declarative structural transaction plan."""

    def __init__(
        self,
        reason: str,
        *,
        operation_index: int | None = None,
        operation_type: str | None = None,
        field: str | None = None,
    ) -> None:
        if type(reason) is not str or not reason:
            raise ValueError("reason must be a non-empty string.")
        if operation_index is not None and (
            type(operation_index) is not int or operation_index < 0
        ):
            raise ValueError("operation_index must be a nonnegative integer.")
        if operation_type is not None and (
            type(operation_type) is not str or not operation_type
        ):
            raise ValueError(
                "operation_type must be a non-empty string when provided."
            )
        if field is not None and (type(field) is not str or not field):
            raise ValueError("field must be a non-empty string when provided.")

        location = "transaction plan"
        if operation_index is not None:
            location = f"operations[{operation_index}]"
        if field is not None:
            location = f"{location}.{field}"

        self.reason = reason
        self.operation_index = operation_index
        self.operation_type = operation_type
        self.field = field
        super().__init__(
            f"Invalid structural transaction plan at {location}: {reason}"
        )


class PmxStructuralTransactionPlanDecodeError(PmxStructuralTransactionPlanError):
    """Raised when strict JSON decoding fails before plan construction."""


class _DuplicateJsonMemberError(ValueError):
    def __init__(self, member_name: str) -> None:
        self.member_name = member_name
        super().__init__(member_name)


class _NonstandardJsonConstantError(ValueError):
    def __init__(self, constant: str) -> None:
        self.constant = constant
        super().__init__(constant)


def _strict_json_object(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for name, value in pairs:
        if name in result:
            raise _DuplicateJsonMemberError(name)
        result[name] = value
    return result


def _reject_json_constant(constant: str) -> object:
    raise _NonstandardJsonConstantError(constant)


def _field_error(
    reason: str,
    *,
    field: str,
    operation_index: int | None = None,
    operation_type: str | None = None,
) -> PmxStructuralTransactionPlanError:
    return PmxStructuralTransactionPlanError(
        reason,
        operation_index=operation_index,
        operation_type=operation_type,
        field=field,
    )


def _reject_unknown_fields(
    payload: dict[str, object],
    allowed_fields: frozenset[str],
    *,
    operation_index: int | None = None,
    operation_type: str | None = None,
) -> None:
    unknown_fields = sorted(set(payload) - allowed_fields)
    if unknown_fields:
        field = unknown_fields[0]
        raise _field_error(
            f"unknown field {field!r}.",
            field=field,
            operation_index=operation_index,
            operation_type=operation_type,
        )


def _require_field(
    payload: dict[str, object],
    field: str,
    *,
    operation_index: int | None = None,
    operation_type: str | None = None,
) -> object:
    if field not in payload:
        raise _field_error(
            "field is required.",
            field=field,
            operation_index=operation_index,
            operation_type=operation_type,
        )
    return payload[field]


def _require_string(
    value: object,
    *,
    field: str,
    operation_index: int | None = None,
    operation_type: str | None = None,
) -> str:
    if type(value) is not str:
        raise _field_error(
            "value must be a JSON string.",
            field=field,
            operation_index=operation_index,
            operation_type=operation_type,
        )
    return value


def _require_integer(
    value: object,
    *,
    field: str,
    operation_index: int | None = None,
    operation_type: str | None = None,
) -> int:
    if type(value) is not int:
        raise _field_error(
            "value must be a JSON integer; booleans and floats are invalid.",
            field=field,
            operation_index=operation_index,
            operation_type=operation_type,
        )
    return value


def _require_float(
    value: object,
    *,
    field: str,
    operation_index: int,
    operation_type: str,
) -> float:
    if type(value) is not float:
        raise _field_error(
            "value must be a JSON float; integers are not coerced.",
            field=field,
            operation_index=operation_index,
            operation_type=operation_type,
        )
    if not math.isfinite(value):
        raise _field_error(
            "floating-point value must be finite.",
            field=field,
            operation_index=operation_index,
            operation_type=operation_type,
        )
    return value


def _require_float_vector(
    value: object,
    *,
    field: str,
    length: int,
    operation_index: int,
    operation_type: str,
) -> tuple[float, ...]:
    if type(value) is not list:
        raise _field_error(
            "value must be a JSON array.",
            field=field,
            operation_index=operation_index,
            operation_type=operation_type,
        )
    if len(value) != length:
        raise _field_error(
            f"array must contain exactly {length} values.",
            field=field,
            operation_index=operation_index,
            operation_type=operation_type,
        )
    return tuple(
        _require_float(
            component,
            field=f"{field}[{component_index}]",
            operation_index=operation_index,
            operation_type=operation_type,
        )
        for component_index, component in enumerate(value)
    )


def _parse_optional_new_id(
    payload: dict[str, object],
    *,
    operation_index: int,
    operation_type: str,
) -> str | None:
    if "new_id" not in payload:
        return None
    return _require_string(
        payload["new_id"],
        field="new_id",
        operation_index=operation_index,
        operation_type=operation_type,
    )


def _parse_insertion_position(
    payload: dict[str, object],
    *,
    operation_index: int,
    operation_type: str,
) -> tuple[str, int | None]:
    if "position" in payload:
        position = _require_string(
            payload["position"],
            field="position",
            operation_index=operation_index,
            operation_type=operation_type,
        )
    else:
        position = "append"

    if position not in ("append", "insert_before"):
        raise _field_error(
            "value must be either 'append' or 'insert_before'.",
            field="position",
            operation_index=operation_index,
            operation_type=operation_type,
        )

    if position == "append":
        if "source_index" in payload:
            raise _field_error(
                "field is forbidden when position is 'append'.",
                field="source_index",
                operation_index=operation_index,
                operation_type=operation_type,
            )
        return position, None

    source_index = _require_integer(
        _require_field(
            payload,
            "source_index",
            operation_index=operation_index,
            operation_type=operation_type,
        ),
        field="source_index",
        operation_index=operation_index,
        operation_type=operation_type,
    )
    if source_index < 0:
        raise _field_error(
            "value cannot be negative.",
            field="source_index",
            operation_index=operation_index,
            operation_type=operation_type,
        )
    return position, source_index


def _parse_new_reference(
    value: object,
    *,
    field: str,
    expected_target_kind: str,
    operation_index: int,
    operation_type: str,
) -> PmxStructuralNewReference:
    if type(value) is not dict:
        raise _field_error(
            "value must be an integer or a new-reference JSON object.",
            field=field,
            operation_index=operation_index,
            operation_type=operation_type,
        )

    unknown_fields = sorted(set(value) - _NEW_REFERENCE_FIELDS)
    if unknown_fields:
        unknown = unknown_fields[0]
        raise _field_error(
            f"unknown field {unknown!r}.",
            field=f"{field}.{unknown}",
            operation_index=operation_index,
            operation_type=operation_type,
        )

    ref_value = _require_string(
        _require_field(
            value,
            "ref",
            operation_index=operation_index,
            operation_type=operation_type,
        ),
        field=f"{field}.ref",
        operation_index=operation_index,
        operation_type=operation_type,
    )
    if ref_value != "new":
        raise _field_error(
            "value must equal 'new'.",
            field=f"{field}.ref",
            operation_index=operation_index,
            operation_type=operation_type,
        )

    target_kind = _require_string(
        _require_field(
            value,
            "target_kind",
            operation_index=operation_index,
            operation_type=operation_type,
        ),
        field=f"{field}.target_kind",
        operation_index=operation_index,
        operation_type=operation_type,
    )
    if target_kind != expected_target_kind:
        raise _field_error(
            f"new reference must target {expected_target_kind}.",
            field=f"{field}.target_kind",
            operation_index=operation_index,
            operation_type=operation_type,
        )

    new_id = _require_string(
        _require_field(
            value,
            "new_id",
            operation_index=operation_index,
            operation_type=operation_type,
        ),
        field=f"{field}.new_id",
        operation_index=operation_index,
        operation_type=operation_type,
    )

    try:
        return PmxStructuralNewReference(
            target_kind=target_kind,
            new_id=new_id,
        )
    except (TypeError, ValueError) as error:
        raise _field_error(
            str(error),
            field=f"{field}.new_id",
            operation_index=operation_index,
            operation_type=operation_type,
        ) from error


def _parse_texture_reference(
    value: object,
    *,
    field: str,
    operation_index: int,
    operation_type: str,
) -> int | PmxStructuralNewReference:
    if type(value) is int:
        if value < -1:
            raise _field_error(
                "existing texture reference cannot be smaller than -1.",
                field=field,
                operation_index=operation_index,
                operation_type=operation_type,
            )
        return value
    return _parse_new_reference(
        value,
        field=field,
        expected_target_kind="texture",
        operation_index=operation_index,
        operation_type=operation_type,
    )


def _parse_transform_collection_operation(
    payload: dict[str, object],
    *,
    operation_index: int,
) -> PmxStructuralCollectionEdit:
    operation_type = PmxStructuralTransactionOperationType.TRANSFORM_COLLECTION.value
    _reject_unknown_fields(
        payload,
        _TRANSFORM_COLLECTION_FIELDS,
        operation_index=operation_index,
        operation_type=operation_type,
    )

    target_kind_value = _require_string(
        _require_field(
            payload,
            "target_kind",
            operation_index=operation_index,
            operation_type=operation_type,
        ),
        field="target_kind",
        operation_index=operation_index,
        operation_type=operation_type,
    )
    if target_kind_value not in _COLLECTION_TARGET_KINDS:
        raise _field_error(
            "value must name one supported structural collection.",
            field="target_kind",
            operation_index=operation_index,
            operation_type=operation_type,
        )

    indices_value = _require_field(
        payload,
        "old_indices_in_new_order",
        operation_index=operation_index,
        operation_type=operation_type,
    )
    if type(indices_value) is not list:
        raise _field_error(
            "value must be a JSON array.",
            field="old_indices_in_new_order",
            operation_index=operation_index,
            operation_type=operation_type,
        )

    indices: list[int] = []
    seen: set[int] = set()
    for index, value in enumerate(indices_value):
        parsed = _require_integer(
            value,
            field=f"old_indices_in_new_order[{index}]",
            operation_index=operation_index,
            operation_type=operation_type,
        )
        if parsed < 0:
            raise _field_error(
                "value cannot be negative.",
                field=f"old_indices_in_new_order[{index}]",
                operation_index=operation_index,
                operation_type=operation_type,
            )
        if parsed in seen:
            raise _field_error(
                "source indices must be unique.",
                field=f"old_indices_in_new_order[{index}]",
                operation_index=operation_index,
                operation_type=operation_type,
            )
        seen.add(parsed)
        indices.append(parsed)

    return PmxStructuralCollectionEdit(
        target_kind=PmxReferenceTargetKind(target_kind_value),
        old_indices_in_new_order=tuple(indices),
    )


def _parse_texture_insertion_operation(
    payload: dict[str, object],
    *,
    operation_index: int,
) -> PmxStructuralTextureInsertion:
    operation_type = PmxStructuralTransactionOperationType.INSERT_TEXTURE.value
    _reject_unknown_fields(
        payload,
        _INSERT_TEXTURE_FIELDS,
        operation_index=operation_index,
        operation_type=operation_type,
    )

    path = _require_string(
        _require_field(
            payload,
            "path",
            operation_index=operation_index,
            operation_type=operation_type,
        ),
        field="path",
        operation_index=operation_index,
        operation_type=operation_type,
    )
    position, source_index = _parse_insertion_position(
        payload,
        operation_index=operation_index,
        operation_type=operation_type,
    )
    new_id = _parse_optional_new_id(
        payload,
        operation_index=operation_index,
        operation_type=operation_type,
    )

    try:
        return PmxStructuralTextureInsertion(
            path=path,
            position=position,
            source_index=source_index,
            new_id=new_id,
        )
    except (TypeError, ValueError) as error:
        raise PmxStructuralTransactionPlanError(
            str(error),
            operation_index=operation_index,
            operation_type=operation_type,
        ) from error


def _parse_material_insertion_operation(
    payload: dict[str, object],
    *,
    operation_index: int,
) -> PmxStructuralMaterialInsertion:
    operation_type = PmxStructuralTransactionOperationType.INSERT_MATERIAL.value
    _reject_unknown_fields(
        payload,
        _INSERT_MATERIAL_FIELDS,
        operation_index=operation_index,
        operation_type=operation_type,
    )

    kwargs: dict[str, object] = {
        "local_name": _require_string(
            _require_field(
                payload,
                "local_name",
                operation_index=operation_index,
                operation_type=operation_type,
            ),
            field="local_name",
            operation_index=operation_index,
            operation_type=operation_type,
        )
    }

    for field in ("universal_name", "memo"):
        if field in payload:
            kwargs[field] = _require_string(
                payload[field],
                field=field,
                operation_index=operation_index,
                operation_type=operation_type,
            )

    for field in ("texture_index", "sphere_texture_index"):
        if field in payload:
            kwargs[field] = _parse_texture_reference(
                payload[field],
                field=field,
                operation_index=operation_index,
                operation_type=operation_type,
            )

    if "sphere_mode" in payload:
        sphere_mode = _require_integer(
            payload["sphere_mode"],
            field="sphere_mode",
            operation_index=operation_index,
            operation_type=operation_type,
        )
        if sphere_mode not in (0, 1, 2, 3):
            raise _field_error(
                "value must be from 0 through 3.",
                field="sphere_mode",
                operation_index=operation_index,
                operation_type=operation_type,
            )
        kwargs["sphere_mode"] = sphere_mode

    if "toon_reference_mode" in payload:
        toon_mode = _require_string(
            payload["toon_reference_mode"],
            field="toon_reference_mode",
            operation_index=operation_index,
            operation_type=operation_type,
        )
        if toon_mode not in ("texture", "shared"):
            raise _field_error(
                "value must be either 'texture' or 'shared'.",
                field="toon_reference_mode",
                operation_index=operation_index,
                operation_type=operation_type,
            )
    else:
        toon_mode = "texture"

    if "toon_reference_mode" in payload:
        kwargs["toon_reference_mode"] = toon_mode

    if toon_mode == "shared":
        toon_index = _require_integer(
            _require_field(
                payload,
                "toon_reference_index",
                operation_index=operation_index,
                operation_type=operation_type,
            ),
            field="toon_reference_index",
            operation_index=operation_index,
            operation_type=operation_type,
        )
        if not 0 <= toon_index <= 9:
            raise _field_error(
                "shared toon reference index must be from 0 through 9.",
                field="toon_reference_index",
                operation_index=operation_index,
                operation_type=operation_type,
            )
        kwargs["toon_reference_index"] = toon_index
    elif "toon_reference_index" in payload:
        kwargs["toon_reference_index"] = _parse_texture_reference(
            payload["toon_reference_index"],
            field="toon_reference_index",
            operation_index=operation_index,
            operation_type=operation_type,
        )

    vector_fields = (
        ("diffuse", 4),
        ("specular", 3),
        ("ambient", 3),
        ("edge_color", 4),
    )
    for field, length in vector_fields:
        if field in payload:
            kwargs[field] = _require_float_vector(
                payload[field],
                field=field,
                length=length,
                operation_index=operation_index,
                operation_type=operation_type,
            )

    for field in ("specular_strength", "edge_scale"):
        if field in payload:
            kwargs[field] = _require_float(
                payload[field],
                field=field,
                operation_index=operation_index,
                operation_type=operation_type,
            )

    if "drawing_flags" in payload:
        drawing_flags = _require_integer(
            payload["drawing_flags"],
            field="drawing_flags",
            operation_index=operation_index,
            operation_type=operation_type,
        )
        if not 0 <= drawing_flags <= 0xFF:
            raise _field_error(
                "value must fit in one unsigned byte.",
                field="drawing_flags",
                operation_index=operation_index,
                operation_type=operation_type,
            )
        kwargs["drawing_flags"] = drawing_flags

    position, source_index = _parse_insertion_position(
        payload,
        operation_index=operation_index,
        operation_type=operation_type,
    )
    if "position" in payload:
        kwargs["position"] = position
    if source_index is not None:
        kwargs["source_index"] = source_index

    new_id = _parse_optional_new_id(
        payload,
        operation_index=operation_index,
        operation_type=operation_type,
    )
    if new_id is not None:
        kwargs["new_id"] = new_id

    try:
        return PmxStructuralMaterialInsertion(**kwargs)
    except (TypeError, ValueError) as error:
        raise PmxStructuralTransactionPlanError(
            str(error),
            operation_index=operation_index,
            operation_type=operation_type,
        ) from error


def _parse_transaction_operation(
    payload: object,
    *,
    operation_index: int,
) -> PmxStructuralTransactionOperation:
    if type(payload) is not dict:
        raise PmxStructuralTransactionPlanError(
            "operation must be a JSON object.",
            operation_index=operation_index,
        )

    operation_name = _require_string(
        _require_field(payload, "op", operation_index=operation_index),
        field="op",
        operation_index=operation_index,
    )
    if operation_name == PmxStructuralTransactionOperationType.TRANSFORM_COLLECTION:
        return _parse_transform_collection_operation(
            payload,
            operation_index=operation_index,
        )
    if operation_name == PmxStructuralTransactionOperationType.INSERT_TEXTURE:
        return _parse_texture_insertion_operation(
            payload,
            operation_index=operation_index,
        )
    if operation_name == PmxStructuralTransactionOperationType.INSERT_MATERIAL:
        return _parse_material_insertion_operation(
            payload,
            operation_index=operation_index,
        )

    if operation_name in _OPERATION_TYPE_BY_DISCRIMINATOR:
        raise _field_error(
            (
                f"operation {operation_name!r} is recognized by schema 1 but "
                "is not implemented by this loader stage."
            ),
            field="op",
            operation_index=operation_index,
            operation_type=operation_name,
        )
    raise _field_error(
        f"unsupported operation name {operation_name!r}.",
        field="op",
        operation_index=operation_index,
    )


def _parse_decoded_transaction_plan(
    payload: object,
) -> PmxStructuralTransactionPlan:
    if type(payload) is not dict:
        raise PmxStructuralTransactionPlanError(
            "top-level JSON value must be an object."
        )

    _reject_unknown_fields(payload, _TOP_LEVEL_FIELDS)
    schema_version = _require_integer(
        _require_field(payload, "schema_version"),
        field="schema_version",
    )
    if schema_version != PMX_STRUCTURAL_TRANSACTION_PLAN_SCHEMA_VERSION:
        raise _field_error(
            (
                f"unsupported schema version {schema_version}; expected "
                f"{PMX_STRUCTURAL_TRANSACTION_PLAN_SCHEMA_VERSION}."
            ),
            field="schema_version",
        )

    operations_value = _require_field(payload, "operations")
    if type(operations_value) is not list:
        raise _field_error(
            "value must be a JSON array.",
            field="operations",
        )
    operations = tuple(
        _parse_transaction_operation(operation, operation_index=index)
        for index, operation in enumerate(operations_value)
    )

    expected_source_sha256 = None
    if "expected_source_sha256" in payload:
        expected_source_sha256 = _require_string(
            payload["expected_source_sha256"],
            field="expected_source_sha256",
        )
        if _LOWERCASE_SHA256.fullmatch(expected_source_sha256) is None:
            raise _field_error(
                "value must be exactly 64 lowercase hexadecimal characters.",
                field="expected_source_sha256",
            )

    try:
        return PmxStructuralTransactionPlan(
            operations=operations,
            schema_version=schema_version,
            expected_source_sha256=expected_source_sha256,
        )
    except (TypeError, ValueError) as error:
        raise PmxStructuralTransactionPlanError(str(error)) from error


def parse_pmx_structural_transaction_plan_json(
    text: str,
) -> PmxStructuralTransactionPlan:
    """Parse strict JSON text into an immutable schema-one transaction plan."""

    if type(text) is not str:
        raise TypeError("text must be a string.")
    if not text.strip():
        raise PmxStructuralTransactionPlanDecodeError(
            "invalid JSON at line 1, column 1: document is empty."
        )

    try:
        payload = json.loads(
            text,
            object_pairs_hook=_strict_json_object,
            parse_constant=_reject_json_constant,
        )
    except _DuplicateJsonMemberError as error:
        raise PmxStructuralTransactionPlanDecodeError(
            f"duplicate JSON member {error.member_name!r}."
        ) from error
    except _NonstandardJsonConstantError as error:
        raise PmxStructuralTransactionPlanDecodeError(
            f"numeric constant {error.constant!r} is not valid JSON."
        ) from error
    except json.JSONDecodeError as error:
        raise PmxStructuralTransactionPlanDecodeError(
            (
                f"invalid JSON at line {error.lineno}, column "
                f"{error.colno}: {error.msg}."
            )
        ) from error

    return _parse_decoded_transaction_plan(payload)


def load_pmx_structural_transaction_plan(
    path: str | Path,
) -> PmxStructuralTransactionPlan:
    """Read one UTF-8 JSON file and parse a structural transaction plan."""

    if not isinstance(path, (str, Path)):
        raise TypeError("path must be a string or pathlib.Path.")
    try:
        text = Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise PmxStructuralTransactionPlanDecodeError(
            "transaction-plan file must be valid UTF-8."
        ) from error
    return parse_pmx_structural_transaction_plan_json(text)


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
    "PmxStructuralTransactionPlanError",
    "PmxStructuralTransactionPlanDecodeError",
    "parse_pmx_structural_transaction_plan_json",
    "load_pmx_structural_transaction_plan",
    "PmxStructuralTransactionPlan",
)
