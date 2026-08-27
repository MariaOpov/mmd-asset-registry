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
from mmd_registry.services.structural_bone import (
    PmxStructuralBoneIk,
    PmxStructuralBoneIkLink,
    PmxStructuralBoneInsertion,
)
from mmd_registry.services.structural_material import PmxStructuralMaterialInsertion
from mmd_registry.services.structural_morph import (
    PmxStructuralMorphBoneOffset,
    PmxStructuralMorphFlipOffset,
    PmxStructuralMorphGroupOffset,
    PmxStructuralMorphImpulseOffset,
    PmxStructuralMorphInsertion,
    PmxStructuralMorphMaterialOffset,
    PmxStructuralMorphUvOffset,
    PmxStructuralMorphVertexOffset,
)
from mmd_registry.services.structural_reference import PmxStructuralNewReference
from mmd_registry.services.structural_rigid_body import (
    PmxStructuralRigidBodyInsertion,
)
from mmd_registry.services.structural_texture import PmxStructuralTextureInsertion
from mmd_registry.services.structural_transaction import (
    PmxStructuralTransactionOperation,
    PmxStructuralTransactionRequest,
)
from mmd_registry.services.structural_vertex import (
    PmxStructuralVertexBdef1,
    PmxStructuralVertexBdef2,
    PmxStructuralVertexBdef4,
    PmxStructuralVertexInsertion,
    PmxStructuralVertexQdef,
    PmxStructuralVertexSdef,
)


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
_INSERT_BONE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "op",
        "local_name",
        "universal_name",
        "bone_position",
        "parent_bone_index",
        "transform_layer",
        "rotatable",
        "translatable",
        "visible",
        "enabled",
        "local_append",
        "after_physics",
        "tail_offset",
        "tail_bone_index",
        "inherit_rotation",
        "inherit_translation",
        "inherit_parent_bone_index",
        "inherit_weight",
        "fixed_axis",
        "local_axis_x",
        "local_axis_z",
        "external_parent_key",
        "ik",
        "position",
        "source_index",
        "new_id",
    }
)
_BONE_IK_FIELDS: Final[frozenset[str]] = frozenset(
    {"target_bone_index", "loop_count", "angle_limit", "links"}
)
_BONE_IK_LINK_FIELDS: Final[frozenset[str]] = frozenset(
    {"bone_index", "lower_limit", "upper_limit"}
)
_INSERT_VERTEX_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "op",
        "vertex_position",
        "normal",
        "uv",
        "additional_uvs",
        "deform",
        "edge_scale",
        "position",
        "source_index",
        "new_id",
    }
)
_VERTEX_DEFORM_FIELDS_BY_TYPE: Final = MappingProxyType(
    {
        "bdef1": frozenset({"type", "bone_index"}),
        "bdef2": frozenset({"type", "bone_indices", "bone_1_weight"}),
        "bdef4": frozenset({"type", "bone_indices", "weights"}),
        "sdef": frozenset(
            {"type", "bone_indices", "bone_1_weight", "c", "r0", "r1"}
        ),
        "qdef": frozenset({"type", "bone_indices", "weights"}),
    }
)
_INSERT_MORPH_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "op",
        "local_name",
        "morph_type",
        "universal_name",
        "panel",
        "offsets",
        "position",
        "source_index",
        "new_id",
    }
)
_MORPH_TYPES: Final[tuple[str, ...]] = (
    "group",
    "vertex",
    "bone",
    "uv",
    "additional_uv_1",
    "additional_uv_2",
    "additional_uv_3",
    "additional_uv_4",
    "material",
    "flip",
    "impulse",
)
_MORPH_PANELS: Final[tuple[str, ...]] = (
    "system",
    "eyebrow",
    "eye",
    "mouth",
    "other",
)
_MORPH_OFFSET_FIELDS_BY_TYPE: Final = MappingProxyType(
    {
        "group": frozenset({"type", "morph_index", "weight"}),
        "vertex": frozenset({"type", "vertex_index", "translation"}),
        "bone": frozenset({"type", "bone_index", "translation", "rotation"}),
        "uv": frozenset({"type", "vertex_index", "uv_offset"}),
        "material": frozenset(
            {
                "type",
                "material_index",
                "operation",
                "diffuse",
                "specular",
                "specular_strength",
                "ambient",
                "edge_color",
                "edge_scale",
                "texture_tint",
                "sphere_tint",
                "toon_tint",
            }
        ),
        "flip": frozenset({"type", "morph_index", "weight"}),
        "impulse": frozenset(
            {"type", "rigid_body_index", "local", "velocity", "angular_torque"}
        ),
    }
)
_MORPH_OFFSET_TYPE_BY_MORPH_TYPE: Final = MappingProxyType(
    {
        "group": "group",
        "vertex": "vertex",
        "bone": "bone",
        "uv": "uv",
        "additional_uv_1": "uv",
        "additional_uv_2": "uv",
        "additional_uv_3": "uv",
        "additional_uv_4": "uv",
        "material": "material",
        "flip": "flip",
        "impulse": "impulse",
    }
)
_INSERT_RIGID_BODY_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "op",
        "local_name",
        "universal_name",
        "bone_index",
        "collision_group",
        "collision_mask",
        "shape",
        "size",
        "body_position",
        "rotation",
        "mass",
        "linear_damping",
        "angular_damping",
        "restitution",
        "friction",
        "physics_mode",
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
_INT32_MIN: Final[int] = -(1 << 31)
_INT32_MAX: Final[int] = (1 << 31) - 1


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


def _require_boolean(
    value: object,
    *,
    field: str,
    operation_index: int,
    operation_type: str,
) -> bool:
    if type(value) is not bool:
        raise _field_error(
            "value must be a JSON boolean.",
            field=field,
            operation_index=operation_index,
            operation_type=operation_type,
        )
    return value


def _require_int32(
    value: object,
    *,
    field: str,
    operation_index: int,
    operation_type: str,
) -> int:
    integer = _require_integer(
        value,
        field=field,
        operation_index=operation_index,
        operation_type=operation_type,
    )
    if not _INT32_MIN <= integer <= _INT32_MAX:
        raise _field_error(
            "value must fit in a signed 32-bit integer.",
            field=field,
            operation_index=operation_index,
            operation_type=operation_type,
        )
    return integer


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


def _parse_optional_float_vector(
    value: object,
    *,
    field: str,
    length: int,
    operation_index: int,
    operation_type: str,
) -> tuple[float, ...] | None:
    if value is None:
        return None
    return _require_float_vector(
        value,
        field=field,
        length=length,
        operation_index=operation_index,
        operation_type=operation_type,
    )


def _parse_bone_reference(
    value: object,
    *,
    field: str,
    allow_sentinel: bool,
    operation_index: int,
    operation_type: str,
) -> int:
    index = _require_integer(
        value,
        field=field,
        operation_index=operation_index,
        operation_type=operation_type,
    )
    minimum = -1 if allow_sentinel else 0
    if index < minimum:
        message = (
            "captured-source bone reference cannot be smaller than -1."
            if allow_sentinel
            else "captured-source bone reference cannot be negative."
        )
        raise _field_error(
            message,
            field=field,
            operation_index=operation_index,
            operation_type=operation_type,
        )
    return index


def _parse_bone_ik_link(
    payload: object,
    *,
    operation_index: int,
    operation_type: str,
    link_index: int,
) -> PmxStructuralBoneIkLink:
    field_prefix = f"ik.links[{link_index}]"
    if type(payload) is not dict:
        raise _field_error(
            "value must be a JSON object.",
            field=field_prefix,
            operation_index=operation_index,
            operation_type=operation_type,
        )

    unknown_fields = sorted(set(payload) - _BONE_IK_LINK_FIELDS)
    if unknown_fields:
        unknown = unknown_fields[0]
        raise _field_error(
            f"unknown field {unknown!r}.",
            field=f"{field_prefix}.{unknown}",
            operation_index=operation_index,
            operation_type=operation_type,
        )

    bone_index = _parse_bone_reference(
        _require_field(
            payload,
            "bone_index",
            operation_index=operation_index,
            operation_type=operation_type,
        ),
        field=f"{field_prefix}.bone_index",
        allow_sentinel=False,
        operation_index=operation_index,
        operation_type=operation_type,
    )

    lower = None
    upper = None
    if "lower_limit" in payload:
        lower = _parse_optional_float_vector(
            payload["lower_limit"],
            field=f"{field_prefix}.lower_limit",
            length=3,
            operation_index=operation_index,
            operation_type=operation_type,
        )
    if "upper_limit" in payload:
        upper = _parse_optional_float_vector(
            payload["upper_limit"],
            field=f"{field_prefix}.upper_limit",
            length=3,
            operation_index=operation_index,
            operation_type=operation_type,
        )

    try:
        return PmxStructuralBoneIkLink(
            bone_index=bone_index,
            lower_limit=lower,
            upper_limit=upper,
        )
    except (TypeError, ValueError) as error:
        raise PmxStructuralTransactionPlanError(
            str(error),
            operation_index=operation_index,
            operation_type=operation_type,
        ) from error


def _parse_bone_ik(
    payload: object,
    *,
    operation_index: int,
    operation_type: str,
) -> PmxStructuralBoneIk | None:
    if payload is None:
        return None
    if type(payload) is not dict:
        raise _field_error(
            "value must be a JSON object or null.",
            field="ik",
            operation_index=operation_index,
            operation_type=operation_type,
        )

    unknown_fields = sorted(set(payload) - _BONE_IK_FIELDS)
    if unknown_fields:
        unknown = unknown_fields[0]
        raise _field_error(
            f"unknown field {unknown!r}.",
            field=f"ik.{unknown}",
            operation_index=operation_index,
            operation_type=operation_type,
        )

    kwargs: dict[str, object] = {
        "target_bone_index": _parse_bone_reference(
            _require_field(
                payload,
                "target_bone_index",
                operation_index=operation_index,
                operation_type=operation_type,
            ),
            field="ik.target_bone_index",
            allow_sentinel=False,
            operation_index=operation_index,
            operation_type=operation_type,
        )
    }

    if "loop_count" in payload:
        loop_count = _require_integer(
            payload["loop_count"],
            field="ik.loop_count",
            operation_index=operation_index,
            operation_type=operation_type,
        )
        if not 0 <= loop_count <= _INT32_MAX:
            raise _field_error(
                "value must fit in a nonnegative signed 32-bit integer.",
                field="ik.loop_count",
                operation_index=operation_index,
                operation_type=operation_type,
            )
        kwargs["loop_count"] = loop_count

    if "angle_limit" in payload:
        kwargs["angle_limit"] = _require_float(
            payload["angle_limit"],
            field="ik.angle_limit",
            operation_index=operation_index,
            operation_type=operation_type,
        )

    if "links" in payload:
        links_value = payload["links"]
        if type(links_value) is not list:
            raise _field_error(
                "value must be a JSON array.",
                field="ik.links",
                operation_index=operation_index,
                operation_type=operation_type,
            )
        kwargs["links"] = tuple(
            _parse_bone_ik_link(
                link,
                operation_index=operation_index,
                operation_type=operation_type,
                link_index=link_index,
            )
            for link_index, link in enumerate(links_value)
        )

    try:
        return PmxStructuralBoneIk(**kwargs)
    except (TypeError, ValueError) as error:
        raise PmxStructuralTransactionPlanError(
            str(error),
            operation_index=operation_index,
            operation_type=operation_type,
        ) from error


def _parse_bone_insertion_operation(
    payload: dict[str, object],
    *,
    operation_index: int,
) -> PmxStructuralBoneInsertion:
    operation_type = PmxStructuralTransactionOperationType.INSERT_BONE.value
    _reject_unknown_fields(
        payload,
        _INSERT_BONE_FIELDS,
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

    if "universal_name" in payload:
        kwargs["universal_name"] = _require_string(
            payload["universal_name"],
            field="universal_name",
            operation_index=operation_index,
            operation_type=operation_type,
        )

    if "bone_position" in payload:
        kwargs["bone_position"] = _require_float_vector(
            payload["bone_position"],
            field="bone_position",
            length=3,
            operation_index=operation_index,
            operation_type=operation_type,
        )

    if "parent_bone_index" in payload:
        kwargs["parent_bone_index"] = _parse_bone_reference(
            payload["parent_bone_index"],
            field="parent_bone_index",
            allow_sentinel=True,
            operation_index=operation_index,
            operation_type=operation_type,
        )

    if "transform_layer" in payload:
        kwargs["transform_layer"] = _require_int32(
            payload["transform_layer"],
            field="transform_layer",
            operation_index=operation_index,
            operation_type=operation_type,
        )

    for field in (
        "rotatable",
        "translatable",
        "visible",
        "enabled",
        "local_append",
        "after_physics",
        "inherit_rotation",
        "inherit_translation",
    ):
        if field in payload:
            kwargs[field] = _require_boolean(
                payload[field],
                field=field,
                operation_index=operation_index,
                operation_type=operation_type,
            )

    tail_offset_authored = "tail_offset" in payload
    tail_index_authored = "tail_bone_index" in payload
    if tail_offset_authored:
        kwargs["tail_offset"] = _parse_optional_float_vector(
            payload["tail_offset"],
            field="tail_offset",
            length=3,
            operation_index=operation_index,
            operation_type=operation_type,
        )
    if tail_index_authored:
        tail_value = payload["tail_bone_index"]
        kwargs["tail_bone_index"] = (
            None
            if tail_value is None
            else _parse_bone_reference(
                tail_value,
                field="tail_bone_index",
                allow_sentinel=True,
                operation_index=operation_index,
                operation_type=operation_type,
            )
        )
        if not tail_offset_authored:
            kwargs["tail_offset"] = None

    if "inherit_parent_bone_index" in payload:
        inherit_parent = payload["inherit_parent_bone_index"]
        kwargs["inherit_parent_bone_index"] = (
            None
            if inherit_parent is None
            else _parse_bone_reference(
                inherit_parent,
                field="inherit_parent_bone_index",
                allow_sentinel=True,
                operation_index=operation_index,
                operation_type=operation_type,
            )
        )

    if "inherit_weight" in payload:
        inherit_weight = payload["inherit_weight"]
        kwargs["inherit_weight"] = (
            None
            if inherit_weight is None
            else _require_float(
                inherit_weight,
                field="inherit_weight",
                operation_index=operation_index,
                operation_type=operation_type,
            )
        )

    for field in ("fixed_axis", "local_axis_x", "local_axis_z"):
        if field in payload:
            kwargs[field] = _parse_optional_float_vector(
                payload[field],
                field=field,
                length=3,
                operation_index=operation_index,
                operation_type=operation_type,
            )

    if "external_parent_key" in payload:
        external_parent_key = payload["external_parent_key"]
        kwargs["external_parent_key"] = (
            None
            if external_parent_key is None
            else _require_int32(
                external_parent_key,
                field="external_parent_key",
                operation_index=operation_index,
                operation_type=operation_type,
            )
        )

    if "ik" in payload:
        kwargs["ik"] = _parse_bone_ik(
            payload["ik"],
            operation_index=operation_index,
            operation_type=operation_type,
        )

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
        return PmxStructuralBoneInsertion(**kwargs)
    except (TypeError, ValueError) as error:
        raise PmxStructuralTransactionPlanError(
            str(error),
            operation_index=operation_index,
            operation_type=operation_type,
        ) from error


def _parse_vertex_bone_reference(
    value: object,
    *,
    field: str,
    operation_index: int,
    operation_type: str,
) -> int | PmxStructuralNewReference:
    if type(value) is int:
        if value < -1:
            raise _field_error(
                "captured-source bone reference cannot be smaller than -1.",
                field=field,
                operation_index=operation_index,
                operation_type=operation_type,
            )
        return value
    return _parse_new_reference(
        value,
        field=field,
        expected_target_kind="bone",
        operation_index=operation_index,
        operation_type=operation_type,
    )


def _parse_vertex_bone_reference_array(
    value: object,
    *,
    field: str,
    length: int,
    operation_index: int,
    operation_type: str,
) -> tuple[int | PmxStructuralNewReference, ...]:
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
        _parse_vertex_bone_reference(
            item,
            field=f"{field}[{index}]",
            operation_index=operation_index,
            operation_type=operation_type,
        )
        for index, item in enumerate(value)
    )


def _parse_vertex_deform(
    payload: object,
    *,
    operation_index: int,
    operation_type: str,
) -> object:
    if type(payload) is not dict:
        raise _field_error(
            "value must be a JSON object.",
            field="deform",
            operation_index=operation_index,
            operation_type=operation_type,
        )

    deform_type = _require_string(
        _require_field(
            payload,
            "type",
            operation_index=operation_index,
            operation_type=operation_type,
        ),
        field="deform.type",
        operation_index=operation_index,
        operation_type=operation_type,
    )
    allowed_fields = _VERTEX_DEFORM_FIELDS_BY_TYPE.get(deform_type)
    if allowed_fields is None:
        raise _field_error(
            f"unsupported vertex deform type {deform_type!r}.",
            field="deform.type",
            operation_index=operation_index,
            operation_type=operation_type,
        )

    unknown_fields = sorted(set(payload) - allowed_fields)
    if unknown_fields:
        unknown = unknown_fields[0]
        raise _field_error(
            f"unknown field {unknown!r}.",
            field=f"deform.{unknown}",
            operation_index=operation_index,
            operation_type=operation_type,
        )

    try:
        if deform_type == "bdef1":
            return PmxStructuralVertexBdef1(
                bone_index=_parse_vertex_bone_reference(
                    _require_field(
                        payload,
                        "bone_index",
                        operation_index=operation_index,
                        operation_type=operation_type,
                    ),
                    field="deform.bone_index",
                    operation_index=operation_index,
                    operation_type=operation_type,
                )
            )

        if deform_type == "bdef2":
            return PmxStructuralVertexBdef2(
                bone_indices=_parse_vertex_bone_reference_array(
                    _require_field(
                        payload,
                        "bone_indices",
                        operation_index=operation_index,
                        operation_type=operation_type,
                    ),
                    field="deform.bone_indices",
                    length=2,
                    operation_index=operation_index,
                    operation_type=operation_type,
                ),
                bone_1_weight=_require_float(
                    _require_field(
                        payload,
                        "bone_1_weight",
                        operation_index=operation_index,
                        operation_type=operation_type,
                    ),
                    field="deform.bone_1_weight",
                    operation_index=operation_index,
                    operation_type=operation_type,
                ),
            )

        if deform_type == "bdef4":
            return PmxStructuralVertexBdef4(
                bone_indices=_parse_vertex_bone_reference_array(
                    _require_field(
                        payload,
                        "bone_indices",
                        operation_index=operation_index,
                        operation_type=operation_type,
                    ),
                    field="deform.bone_indices",
                    length=4,
                    operation_index=operation_index,
                    operation_type=operation_type,
                ),
                weights=_require_float_vector(
                    _require_field(
                        payload,
                        "weights",
                        operation_index=operation_index,
                        operation_type=operation_type,
                    ),
                    field="deform.weights",
                    length=4,
                    operation_index=operation_index,
                    operation_type=operation_type,
                ),
            )

        if deform_type == "sdef":
            return PmxStructuralVertexSdef(
                bone_indices=_parse_vertex_bone_reference_array(
                    _require_field(
                        payload,
                        "bone_indices",
                        operation_index=operation_index,
                        operation_type=operation_type,
                    ),
                    field="deform.bone_indices",
                    length=2,
                    operation_index=operation_index,
                    operation_type=operation_type,
                ),
                bone_1_weight=_require_float(
                    _require_field(
                        payload,
                        "bone_1_weight",
                        operation_index=operation_index,
                        operation_type=operation_type,
                    ),
                    field="deform.bone_1_weight",
                    operation_index=operation_index,
                    operation_type=operation_type,
                ),
                c=_require_float_vector(
                    _require_field(
                        payload,
                        "c",
                        operation_index=operation_index,
                        operation_type=operation_type,
                    ),
                    field="deform.c",
                    length=3,
                    operation_index=operation_index,
                    operation_type=operation_type,
                ),
                r0=_require_float_vector(
                    _require_field(
                        payload,
                        "r0",
                        operation_index=operation_index,
                        operation_type=operation_type,
                    ),
                    field="deform.r0",
                    length=3,
                    operation_index=operation_index,
                    operation_type=operation_type,
                ),
                r1=_require_float_vector(
                    _require_field(
                        payload,
                        "r1",
                        operation_index=operation_index,
                        operation_type=operation_type,
                    ),
                    field="deform.r1",
                    length=3,
                    operation_index=operation_index,
                    operation_type=operation_type,
                ),
            )

        assert deform_type == "qdef"
        return PmxStructuralVertexQdef(
            bone_indices=_parse_vertex_bone_reference_array(
                _require_field(
                    payload,
                    "bone_indices",
                    operation_index=operation_index,
                    operation_type=operation_type,
                ),
                field="deform.bone_indices",
                length=4,
                operation_index=operation_index,
                operation_type=operation_type,
            ),
            weights=_require_float_vector(
                _require_field(
                    payload,
                    "weights",
                    operation_index=operation_index,
                    operation_type=operation_type,
                ),
                field="deform.weights",
                length=4,
                operation_index=operation_index,
                operation_type=operation_type,
            ),
        )
    except (TypeError, ValueError) as error:
        if isinstance(error, PmxStructuralTransactionPlanError):
            raise
        raise PmxStructuralTransactionPlanError(
            str(error),
            operation_index=operation_index,
            operation_type=operation_type,
        ) from error


def _parse_vertex_insertion_operation(
    payload: dict[str, object],
    *,
    operation_index: int,
) -> PmxStructuralVertexInsertion:
    operation_type = PmxStructuralTransactionOperationType.INSERT_VERTEX.value
    _reject_unknown_fields(
        payload,
        _INSERT_VERTEX_FIELDS,
        operation_index=operation_index,
        operation_type=operation_type,
    )

    vertex_position = _require_float_vector(
        _require_field(
            payload,
            "vertex_position",
            operation_index=operation_index,
            operation_type=operation_type,
        ),
        field="vertex_position",
        length=3,
        operation_index=operation_index,
        operation_type=operation_type,
    )
    normal = _require_float_vector(
        _require_field(
            payload,
            "normal",
            operation_index=operation_index,
            operation_type=operation_type,
        ),
        field="normal",
        length=3,
        operation_index=operation_index,
        operation_type=operation_type,
    )
    uv = _require_float_vector(
        _require_field(
            payload,
            "uv",
            operation_index=operation_index,
            operation_type=operation_type,
        ),
        field="uv",
        length=2,
        operation_index=operation_index,
        operation_type=operation_type,
    )

    additional_uvs_value = _require_field(
        payload,
        "additional_uvs",
        operation_index=operation_index,
        operation_type=operation_type,
    )
    if type(additional_uvs_value) is not list:
        raise _field_error(
            "value must be a JSON array.",
            field="additional_uvs",
            operation_index=operation_index,
            operation_type=operation_type,
        )
    if len(additional_uvs_value) > 4:
        raise _field_error(
            "array cannot contain more than 4 vectors.",
            field="additional_uvs",
            operation_index=operation_index,
            operation_type=operation_type,
        )
    additional_uvs = tuple(
        _require_float_vector(
            additional_uv,
            field=f"additional_uvs[{index}]",
            length=4,
            operation_index=operation_index,
            operation_type=operation_type,
        )
        for index, additional_uv in enumerate(additional_uvs_value)
    )

    deform = _parse_vertex_deform(
        _require_field(
            payload,
            "deform",
            operation_index=operation_index,
            operation_type=operation_type,
        ),
        operation_index=operation_index,
        operation_type=operation_type,
    )
    edge_scale = _require_float(
        _require_field(
            payload,
            "edge_scale",
            operation_index=operation_index,
            operation_type=operation_type,
        ),
        field="edge_scale",
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
        return PmxStructuralVertexInsertion(
            vertex_position=vertex_position,
            normal=normal,
            uv=uv,
            additional_uvs=additional_uvs,
            deform=deform,
            edge_scale=edge_scale,
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


def _parse_cross_target_reference(
    value: object,
    *,
    field: str,
    expected_target_kind: str,
    allow_sentinel: bool,
    operation_index: int,
    operation_type: str,
) -> int | PmxStructuralNewReference:
    if type(value) is int:
        minimum = -1 if allow_sentinel else 0
        if value < minimum:
            message = (
                f"captured-source {expected_target_kind} reference "
                "cannot be smaller than -1."
                if allow_sentinel
                else f"captured-source {expected_target_kind} reference "
                "cannot be negative."
            )
            raise _field_error(
                message,
                field=field,
                operation_index=operation_index,
                operation_type=operation_type,
            )
        return value
    return _parse_new_reference(
        value,
        field=field,
        expected_target_kind=expected_target_kind,
        operation_index=operation_index,
        operation_type=operation_type,
    )


def _parse_nonnegative_source_index(
    value: object,
    *,
    field: str,
    operation_index: int,
    operation_type: str,
) -> int:
    index = _require_integer(
        value,
        field=field,
        operation_index=operation_index,
        operation_type=operation_type,
    )
    if index < 0:
        raise _field_error(
            "captured-source index cannot be negative.",
            field=field,
            operation_index=operation_index,
            operation_type=operation_type,
        )
    return index


def _parse_morph_offset(
    payload: object,
    *,
    morph_type: str,
    offset_index: int,
    operation_index: int,
    operation_type: str,
) -> object:
    field_prefix = f"offsets[{offset_index}]"
    if type(payload) is not dict:
        raise _field_error(
            "value must be a JSON object.",
            field=field_prefix,
            operation_index=operation_index,
            operation_type=operation_type,
        )

    offset_type = _require_string(
        _require_field(
            payload,
            "type",
            operation_index=operation_index,
            operation_type=operation_type,
        ),
        field=f"{field_prefix}.type",
        operation_index=operation_index,
        operation_type=operation_type,
    )
    allowed_fields = _MORPH_OFFSET_FIELDS_BY_TYPE.get(offset_type)
    if allowed_fields is None:
        raise _field_error(
            f"unsupported morph offset type {offset_type!r}.",
            field=f"{field_prefix}.type",
            operation_index=operation_index,
            operation_type=operation_type,
        )

    expected_offset_type = _MORPH_OFFSET_TYPE_BY_MORPH_TYPE[morph_type]
    if offset_type != expected_offset_type:
        raise _field_error(
            (
                f"offset type {offset_type!r} does not match "
                f"morph_type {morph_type!r}."
            ),
            field=f"{field_prefix}.type",
            operation_index=operation_index,
            operation_type=operation_type,
        )

    unknown_fields = sorted(set(payload) - allowed_fields)
    if unknown_fields:
        unknown = unknown_fields[0]
        raise _field_error(
            f"unknown field {unknown!r}.",
            field=f"{field_prefix}.{unknown}",
            operation_index=operation_index,
            operation_type=operation_type,
        )

    try:
        if offset_type == "group":
            return PmxStructuralMorphGroupOffset(
                morph_index=_parse_nonnegative_source_index(
                    _require_field(
                        payload,
                        "morph_index",
                        operation_index=operation_index,
                        operation_type=operation_type,
                    ),
                    field=f"{field_prefix}.morph_index",
                    operation_index=operation_index,
                    operation_type=operation_type,
                ),
                weight=_require_float(
                    _require_field(
                        payload,
                        "weight",
                        operation_index=operation_index,
                        operation_type=operation_type,
                    ),
                    field=f"{field_prefix}.weight",
                    operation_index=operation_index,
                    operation_type=operation_type,
                ),
            )

        if offset_type == "vertex":
            return PmxStructuralMorphVertexOffset(
                vertex_index=_parse_cross_target_reference(
                    _require_field(
                        payload,
                        "vertex_index",
                        operation_index=operation_index,
                        operation_type=operation_type,
                    ),
                    field=f"{field_prefix}.vertex_index",
                    expected_target_kind="vertex",
                    allow_sentinel=False,
                    operation_index=operation_index,
                    operation_type=operation_type,
                ),
                translation=_require_float_vector(
                    _require_field(
                        payload,
                        "translation",
                        operation_index=operation_index,
                        operation_type=operation_type,
                    ),
                    field=f"{field_prefix}.translation",
                    length=3,
                    operation_index=operation_index,
                    operation_type=operation_type,
                ),
            )

        if offset_type == "bone":
            return PmxStructuralMorphBoneOffset(
                bone_index=_parse_cross_target_reference(
                    _require_field(
                        payload,
                        "bone_index",
                        operation_index=operation_index,
                        operation_type=operation_type,
                    ),
                    field=f"{field_prefix}.bone_index",
                    expected_target_kind="bone",
                    allow_sentinel=False,
                    operation_index=operation_index,
                    operation_type=operation_type,
                ),
                translation=_require_float_vector(
                    _require_field(
                        payload,
                        "translation",
                        operation_index=operation_index,
                        operation_type=operation_type,
                    ),
                    field=f"{field_prefix}.translation",
                    length=3,
                    operation_index=operation_index,
                    operation_type=operation_type,
                ),
                rotation=_require_float_vector(
                    _require_field(
                        payload,
                        "rotation",
                        operation_index=operation_index,
                        operation_type=operation_type,
                    ),
                    field=f"{field_prefix}.rotation",
                    length=4,
                    operation_index=operation_index,
                    operation_type=operation_type,
                ),
            )

        if offset_type == "uv":
            return PmxStructuralMorphUvOffset(
                vertex_index=_parse_cross_target_reference(
                    _require_field(
                        payload,
                        "vertex_index",
                        operation_index=operation_index,
                        operation_type=operation_type,
                    ),
                    field=f"{field_prefix}.vertex_index",
                    expected_target_kind="vertex",
                    allow_sentinel=False,
                    operation_index=operation_index,
                    operation_type=operation_type,
                ),
                uv_offset=_require_float_vector(
                    _require_field(
                        payload,
                        "uv_offset",
                        operation_index=operation_index,
                        operation_type=operation_type,
                    ),
                    field=f"{field_prefix}.uv_offset",
                    length=4,
                    operation_index=operation_index,
                    operation_type=operation_type,
                ),
            )

        if offset_type == "material":
            material_operation = _require_string(
                _require_field(
                    payload,
                    "operation",
                    operation_index=operation_index,
                    operation_type=operation_type,
                ),
                field=f"{field_prefix}.operation",
                operation_index=operation_index,
                operation_type=operation_type,
            )
            if material_operation not in ("multiply", "add"):
                raise _field_error(
                    "value must be either 'multiply' or 'add'.",
                    field=f"{field_prefix}.operation",
                    operation_index=operation_index,
                    operation_type=operation_type,
                )
            return PmxStructuralMorphMaterialOffset(
                material_index=_parse_cross_target_reference(
                    _require_field(
                        payload,
                        "material_index",
                        operation_index=operation_index,
                        operation_type=operation_type,
                    ),
                    field=f"{field_prefix}.material_index",
                    expected_target_kind="material",
                    allow_sentinel=True,
                    operation_index=operation_index,
                    operation_type=operation_type,
                ),
                operation=material_operation,
                diffuse=_require_float_vector(
                    _require_field(
                        payload,
                        "diffuse",
                        operation_index=operation_index,
                        operation_type=operation_type,
                    ),
                    field=f"{field_prefix}.diffuse",
                    length=4,
                    operation_index=operation_index,
                    operation_type=operation_type,
                ),
                specular=_require_float_vector(
                    _require_field(
                        payload,
                        "specular",
                        operation_index=operation_index,
                        operation_type=operation_type,
                    ),
                    field=f"{field_prefix}.specular",
                    length=3,
                    operation_index=operation_index,
                    operation_type=operation_type,
                ),
                specular_strength=_require_float(
                    _require_field(
                        payload,
                        "specular_strength",
                        operation_index=operation_index,
                        operation_type=operation_type,
                    ),
                    field=f"{field_prefix}.specular_strength",
                    operation_index=operation_index,
                    operation_type=operation_type,
                ),
                ambient=_require_float_vector(
                    _require_field(
                        payload,
                        "ambient",
                        operation_index=operation_index,
                        operation_type=operation_type,
                    ),
                    field=f"{field_prefix}.ambient",
                    length=3,
                    operation_index=operation_index,
                    operation_type=operation_type,
                ),
                edge_color=_require_float_vector(
                    _require_field(
                        payload,
                        "edge_color",
                        operation_index=operation_index,
                        operation_type=operation_type,
                    ),
                    field=f"{field_prefix}.edge_color",
                    length=4,
                    operation_index=operation_index,
                    operation_type=operation_type,
                ),
                edge_scale=_require_float(
                    _require_field(
                        payload,
                        "edge_scale",
                        operation_index=operation_index,
                        operation_type=operation_type,
                    ),
                    field=f"{field_prefix}.edge_scale",
                    operation_index=operation_index,
                    operation_type=operation_type,
                ),
                texture_tint=_require_float_vector(
                    _require_field(
                        payload,
                        "texture_tint",
                        operation_index=operation_index,
                        operation_type=operation_type,
                    ),
                    field=f"{field_prefix}.texture_tint",
                    length=4,
                    operation_index=operation_index,
                    operation_type=operation_type,
                ),
                sphere_tint=_require_float_vector(
                    _require_field(
                        payload,
                        "sphere_tint",
                        operation_index=operation_index,
                        operation_type=operation_type,
                    ),
                    field=f"{field_prefix}.sphere_tint",
                    length=4,
                    operation_index=operation_index,
                    operation_type=operation_type,
                ),
                toon_tint=_require_float_vector(
                    _require_field(
                        payload,
                        "toon_tint",
                        operation_index=operation_index,
                        operation_type=operation_type,
                    ),
                    field=f"{field_prefix}.toon_tint",
                    length=4,
                    operation_index=operation_index,
                    operation_type=operation_type,
                ),
            )

        if offset_type == "flip":
            return PmxStructuralMorphFlipOffset(
                morph_index=_parse_nonnegative_source_index(
                    _require_field(
                        payload,
                        "morph_index",
                        operation_index=operation_index,
                        operation_type=operation_type,
                    ),
                    field=f"{field_prefix}.morph_index",
                    operation_index=operation_index,
                    operation_type=operation_type,
                ),
                weight=_require_float(
                    _require_field(
                        payload,
                        "weight",
                        operation_index=operation_index,
                        operation_type=operation_type,
                    ),
                    field=f"{field_prefix}.weight",
                    operation_index=operation_index,
                    operation_type=operation_type,
                ),
            )

        assert offset_type == "impulse"
        return PmxStructuralMorphImpulseOffset(
            rigid_body_index=_parse_cross_target_reference(
                _require_field(
                    payload,
                    "rigid_body_index",
                    operation_index=operation_index,
                    operation_type=operation_type,
                ),
                field=f"{field_prefix}.rigid_body_index",
                expected_target_kind="rigid_body",
                allow_sentinel=False,
                operation_index=operation_index,
                operation_type=operation_type,
            ),
            local=_require_boolean(
                _require_field(
                    payload,
                    "local",
                    operation_index=operation_index,
                    operation_type=operation_type,
                ),
                field=f"{field_prefix}.local",
                operation_index=operation_index,
                operation_type=operation_type,
            ),
            velocity=_require_float_vector(
                _require_field(
                    payload,
                    "velocity",
                    operation_index=operation_index,
                    operation_type=operation_type,
                ),
                field=f"{field_prefix}.velocity",
                length=3,
                operation_index=operation_index,
                operation_type=operation_type,
            ),
            angular_torque=_require_float_vector(
                _require_field(
                    payload,
                    "angular_torque",
                    operation_index=operation_index,
                    operation_type=operation_type,
                ),
                field=f"{field_prefix}.angular_torque",
                length=3,
                operation_index=operation_index,
                operation_type=operation_type,
            ),
        )
    except (TypeError, ValueError) as error:
        if isinstance(error, PmxStructuralTransactionPlanError):
            raise
        raise PmxStructuralTransactionPlanError(
            str(error),
            operation_index=operation_index,
            operation_type=operation_type,
        ) from error


def _parse_morph_insertion_operation(
    payload: dict[str, object],
    *,
    operation_index: int,
) -> PmxStructuralMorphInsertion:
    operation_type = PmxStructuralTransactionOperationType.INSERT_MORPH.value
    _reject_unknown_fields(
        payload,
        _INSERT_MORPH_FIELDS,
        operation_index=operation_index,
        operation_type=operation_type,
    )

    local_name = _require_string(
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
    morph_type = _require_string(
        _require_field(
            payload,
            "morph_type",
            operation_index=operation_index,
            operation_type=operation_type,
        ),
        field="morph_type",
        operation_index=operation_index,
        operation_type=operation_type,
    )
    if morph_type not in _MORPH_TYPES:
        raise _field_error(
            f"unsupported morph_type {morph_type!r}.",
            field="morph_type",
            operation_index=operation_index,
            operation_type=operation_type,
        )

    kwargs: dict[str, object] = {
        "local_name": local_name,
        "morph_type": morph_type,
    }

    if "universal_name" in payload:
        kwargs["universal_name"] = _require_string(
            payload["universal_name"],
            field="universal_name",
            operation_index=operation_index,
            operation_type=operation_type,
        )

    if "panel" in payload:
        panel = _require_string(
            payload["panel"],
            field="panel",
            operation_index=operation_index,
            operation_type=operation_type,
        )
        if panel not in _MORPH_PANELS:
            raise _field_error(
                "value must be system, eyebrow, eye, mouth, or other.",
                field="panel",
                operation_index=operation_index,
                operation_type=operation_type,
            )
        kwargs["panel"] = panel

    if "offsets" in payload:
        offsets_value = payload["offsets"]
        if type(offsets_value) is not list:
            raise _field_error(
                "value must be a JSON array.",
                field="offsets",
                operation_index=operation_index,
                operation_type=operation_type,
            )
        kwargs["offsets"] = tuple(
            _parse_morph_offset(
                offset,
                morph_type=morph_type,
                offset_index=offset_index,
                operation_index=operation_index,
                operation_type=operation_type,
            )
            for offset_index, offset in enumerate(offsets_value)
        )

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
        return PmxStructuralMorphInsertion(**kwargs)
    except (TypeError, ValueError) as error:
        raise PmxStructuralTransactionPlanError(
            str(error),
            operation_index=operation_index,
            operation_type=operation_type,
        ) from error


def _parse_rigid_body_insertion_operation(
    payload: dict[str, object],
    *,
    operation_index: int,
) -> PmxStructuralRigidBodyInsertion:
    operation_type = PmxStructuralTransactionOperationType.INSERT_RIGID_BODY.value
    _reject_unknown_fields(
        payload,
        _INSERT_RIGID_BODY_FIELDS,
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

    if "universal_name" in payload:
        kwargs["universal_name"] = _require_string(
            payload["universal_name"],
            field="universal_name",
            operation_index=operation_index,
            operation_type=operation_type,
        )

    if "bone_index" in payload:
        kwargs["bone_index"] = _parse_cross_target_reference(
            payload["bone_index"],
            field="bone_index",
            expected_target_kind="bone",
            allow_sentinel=True,
            operation_index=operation_index,
            operation_type=operation_type,
        )

    if "collision_group" in payload:
        collision_group = _require_integer(
            payload["collision_group"],
            field="collision_group",
            operation_index=operation_index,
            operation_type=operation_type,
        )
        if not 0 <= collision_group <= 15:
            raise _field_error(
                "value must be from 0 through 15.",
                field="collision_group",
                operation_index=operation_index,
                operation_type=operation_type,
            )
        kwargs["collision_group"] = collision_group

    if "collision_mask" in payload:
        collision_mask = _require_integer(
            payload["collision_mask"],
            field="collision_mask",
            operation_index=operation_index,
            operation_type=operation_type,
        )
        if not 0 <= collision_mask <= 0xFFFF:
            raise _field_error(
                "value must fit in an unsigned 16-bit integer.",
                field="collision_mask",
                operation_index=operation_index,
                operation_type=operation_type,
            )
        kwargs["collision_mask"] = collision_mask

    if "shape" in payload:
        shape = _require_string(
            payload["shape"],
            field="shape",
            operation_index=operation_index,
            operation_type=operation_type,
        )
        if shape not in ("sphere", "box", "capsule"):
            raise _field_error(
                "value must be sphere, box, or capsule.",
                field="shape",
                operation_index=operation_index,
                operation_type=operation_type,
            )
        kwargs["shape"] = shape

    for field in ("size", "body_position", "rotation"):
        if field in payload:
            vector = _require_float_vector(
                payload[field],
                field=field,
                length=3,
                operation_index=operation_index,
                operation_type=operation_type,
            )
            if field == "size" and any(value < 0.0 for value in vector):
                raise _field_error(
                    "values cannot be negative.",
                    field=field,
                    operation_index=operation_index,
                    operation_type=operation_type,
                )
            kwargs[field] = vector

    for field in (
        "mass",
        "linear_damping",
        "angular_damping",
        "restitution",
        "friction",
    ):
        if field in payload:
            value = _require_float(
                payload[field],
                field=field,
                operation_index=operation_index,
                operation_type=operation_type,
            )
            if value < 0.0:
                raise _field_error(
                    "value cannot be negative.",
                    field=field,
                    operation_index=operation_index,
                    operation_type=operation_type,
                )
            kwargs[field] = value

    if "physics_mode" in payload:
        physics_mode = _require_string(
            payload["physics_mode"],
            field="physics_mode",
            operation_index=operation_index,
            operation_type=operation_type,
        )
        if physics_mode not in (
            "bone_follow",
            "physics",
            "physics_with_bone_alignment",
        ):
            raise _field_error(
                (
                    "value must be bone_follow, physics, or "
                    "physics_with_bone_alignment."
                ),
                field="physics_mode",
                operation_index=operation_index,
                operation_type=operation_type,
            )
        kwargs["physics_mode"] = physics_mode

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
        return PmxStructuralRigidBodyInsertion(**kwargs)
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
    if operation_name == PmxStructuralTransactionOperationType.INSERT_BONE:
        return _parse_bone_insertion_operation(
            payload,
            operation_index=operation_index,
        )
    if operation_name == PmxStructuralTransactionOperationType.INSERT_MORPH:
        return _parse_morph_insertion_operation(
            payload,
            operation_index=operation_index,
        )
    if operation_name == PmxStructuralTransactionOperationType.INSERT_RIGID_BODY:
        return _parse_rigid_body_insertion_operation(
            payload,
            operation_index=operation_index,
        )
    if operation_name == PmxStructuralTransactionOperationType.INSERT_VERTEX:
        return _parse_vertex_insertion_operation(
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


def _canonical_json_float(value: float) -> float:
    """Collapse semantically equal signed zero to one canonical JSON float."""

    return 0.0 if value == 0.0 else value


def _render_float_vector(value: tuple[float, ...]) -> list[float]:
    return [_canonical_json_float(item) for item in value]


def _render_new_reference(value: PmxStructuralNewReference) -> dict[str, object]:
    return {
        "ref": "new",
        "target_kind": value.target_kind,
        "new_id": value.new_id,
    }


def _render_reference(
    value: int | PmxStructuralNewReference,
) -> int | dict[str, object]:
    if type(value) is int:
        return value
    if isinstance(value, PmxStructuralNewReference):
        return _render_new_reference(value)
    raise TypeError(
        "validated transaction plan exposed an unsupported reference value."
    )


def _append_insertion_metadata(
    payload: dict[str, object],
    *,
    position: str,
    source_index: int | None,
    new_id: str | None,
) -> None:
    if position != "append":
        payload["position"] = position
        assert source_index is not None
        payload["source_index"] = source_index
    if new_id is not None:
        payload["new_id"] = new_id


def _render_bone_ik_link(
    link: PmxStructuralBoneIkLink,
) -> dict[str, object]:
    payload: dict[str, object] = {"bone_index": link.bone_index}
    if link.lower_limit is not None:
        assert link.upper_limit is not None
        payload["lower_limit"] = _render_float_vector(link.lower_limit)
        payload["upper_limit"] = _render_float_vector(link.upper_limit)
    return payload


def _render_bone_ik(ik: PmxStructuralBoneIk) -> dict[str, object]:
    payload: dict[str, object] = {"target_bone_index": ik.target_bone_index}
    if ik.loop_count != 1:
        payload["loop_count"] = ik.loop_count
    if ik.angle_limit != 0.0:
        payload["angle_limit"] = _canonical_json_float(ik.angle_limit)
    if ik.links:
        payload["links"] = [_render_bone_ik_link(link) for link in ik.links]
    return payload


def _render_vertex_deform(
    deform: object,
) -> dict[str, object]:
    if isinstance(deform, PmxStructuralVertexBdef1):
        return {
            "type": "bdef1",
            "bone_index": _render_reference(deform.bone_index),
        }
    if isinstance(deform, PmxStructuralVertexBdef2):
        return {
            "type": "bdef2",
            "bone_indices": [
                _render_reference(value) for value in deform.bone_indices
            ],
            "bone_1_weight": _canonical_json_float(deform.bone_1_weight),
        }
    if isinstance(deform, PmxStructuralVertexBdef4):
        return {
            "type": "bdef4",
            "bone_indices": [
                _render_reference(value) for value in deform.bone_indices
            ],
            "weights": _render_float_vector(deform.weights),
        }
    if isinstance(deform, PmxStructuralVertexSdef):
        return {
            "type": "sdef",
            "bone_indices": [
                _render_reference(value) for value in deform.bone_indices
            ],
            "bone_1_weight": _canonical_json_float(deform.bone_1_weight),
            "c": _render_float_vector(deform.c),
            "r0": _render_float_vector(deform.r0),
            "r1": _render_float_vector(deform.r1),
        }
    if isinstance(deform, PmxStructuralVertexQdef):
        return {
            "type": "qdef",
            "bone_indices": [
                _render_reference(value) for value in deform.bone_indices
            ],
            "weights": _render_float_vector(deform.weights),
        }
    raise TypeError(
        "validated transaction plan exposed an unsupported vertex deform."
    )


def _render_morph_offset(
    offset: object,
) -> dict[str, object]:
    if isinstance(offset, PmxStructuralMorphGroupOffset):
        return {
            "type": "group",
            "morph_index": offset.morph_index,
            "weight": _canonical_json_float(offset.weight),
        }
    if isinstance(offset, PmxStructuralMorphVertexOffset):
        return {
            "type": "vertex",
            "vertex_index": _render_reference(offset.vertex_index),
            "translation": _render_float_vector(offset.translation),
        }
    if isinstance(offset, PmxStructuralMorphBoneOffset):
        return {
            "type": "bone",
            "bone_index": _render_reference(offset.bone_index),
            "translation": _render_float_vector(offset.translation),
            "rotation": _render_float_vector(offset.rotation),
        }
    if isinstance(offset, PmxStructuralMorphUvOffset):
        return {
            "type": "uv",
            "vertex_index": _render_reference(offset.vertex_index),
            "uv_offset": _render_float_vector(offset.uv_offset),
        }
    if isinstance(offset, PmxStructuralMorphMaterialOffset):
        return {
            "type": "material",
            "material_index": _render_reference(offset.material_index),
            "operation": offset.operation,
            "diffuse": _render_float_vector(offset.diffuse),
            "specular": _render_float_vector(offset.specular),
            "specular_strength": _canonical_json_float(offset.specular_strength),
            "ambient": _render_float_vector(offset.ambient),
            "edge_color": _render_float_vector(offset.edge_color),
            "edge_scale": _canonical_json_float(offset.edge_scale),
            "texture_tint": _render_float_vector(offset.texture_tint),
            "sphere_tint": _render_float_vector(offset.sphere_tint),
            "toon_tint": _render_float_vector(offset.toon_tint),
        }
    if isinstance(offset, PmxStructuralMorphFlipOffset):
        return {
            "type": "flip",
            "morph_index": offset.morph_index,
            "weight": _canonical_json_float(offset.weight),
        }
    if isinstance(offset, PmxStructuralMorphImpulseOffset):
        return {
            "type": "impulse",
            "rigid_body_index": _render_reference(offset.rigid_body_index),
            "local": offset.local,
            "velocity": _render_float_vector(offset.velocity),
            "angular_torque": _render_float_vector(offset.angular_torque),
        }
    raise TypeError(
        "validated transaction plan exposed an unsupported morph offset."
    )


def _render_transaction_operation(
    operation: PmxStructuralTransactionOperation,
) -> dict[str, object]:
    if isinstance(operation, PmxStructuralCollectionEdit):
        return {
            "op": PmxStructuralTransactionOperationType.TRANSFORM_COLLECTION.value,
            "target_kind": operation.target_kind.value,
            "old_indices_in_new_order": list(operation.old_indices_in_new_order),
        }

    if isinstance(operation, PmxStructuralTextureInsertion):
        payload: dict[str, object] = {
            "op": PmxStructuralTransactionOperationType.INSERT_TEXTURE.value,
            "path": operation.path,
        }
        _append_insertion_metadata(
            payload,
            position=operation.position,
            source_index=operation.source_index,
            new_id=operation.new_id,
        )
        return payload

    if isinstance(operation, PmxStructuralMaterialInsertion):
        payload = {
            "op": PmxStructuralTransactionOperationType.INSERT_MATERIAL.value,
            "local_name": operation.local_name,
        }
        if operation.universal_name != "":
            payload["universal_name"] = operation.universal_name
        if operation.memo != "":
            payload["memo"] = operation.memo
        if operation.texture_index != -1:
            payload["texture_index"] = _render_reference(operation.texture_index)
        if operation.sphere_texture_index != -1:
            payload["sphere_texture_index"] = _render_reference(
                operation.sphere_texture_index
            )
        if operation.sphere_mode != 0:
            payload["sphere_mode"] = operation.sphere_mode
        if operation.toon_reference_mode != "texture":
            payload["toon_reference_mode"] = operation.toon_reference_mode
        if operation.toon_reference_index != -1:
            payload["toon_reference_index"] = _render_reference(
                operation.toon_reference_index
            )
        if operation.diffuse != (1.0, 1.0, 1.0, 1.0):
            payload["diffuse"] = _render_float_vector(operation.diffuse)
        if operation.specular != (0.0, 0.0, 0.0):
            payload["specular"] = _render_float_vector(operation.specular)
        if operation.specular_strength != 0.0:
            payload["specular_strength"] = _canonical_json_float(
                operation.specular_strength
            )
        if operation.ambient != (0.5, 0.5, 0.5):
            payload["ambient"] = _render_float_vector(operation.ambient)
        if operation.drawing_flags != 0:
            payload["drawing_flags"] = operation.drawing_flags
        if operation.edge_color != (0.0, 0.0, 0.0, 1.0):
            payload["edge_color"] = _render_float_vector(operation.edge_color)
        if operation.edge_scale != 1.0:
            payload["edge_scale"] = _canonical_json_float(operation.edge_scale)
        _append_insertion_metadata(
            payload,
            position=operation.position,
            source_index=operation.source_index,
            new_id=operation.new_id,
        )
        return payload

    if isinstance(operation, PmxStructuralBoneInsertion):
        payload = {
            "op": PmxStructuralTransactionOperationType.INSERT_BONE.value,
            "local_name": operation.local_name,
        }
        if operation.universal_name != "":
            payload["universal_name"] = operation.universal_name
        if operation.bone_position != (0.0, 0.0, 0.0):
            payload["bone_position"] = _render_float_vector(operation.bone_position)
        if operation.parent_bone_index != -1:
            payload["parent_bone_index"] = operation.parent_bone_index
        if operation.transform_layer != 0:
            payload["transform_layer"] = operation.transform_layer
        for field in (
            "rotatable",
            "translatable",
            "visible",
            "enabled",
            "local_append",
            "after_physics",
        ):
            if getattr(operation, field):
                payload[field] = True

        if operation.tail_bone_index is not None:
            payload["tail_bone_index"] = operation.tail_bone_index
        elif operation.tail_offset != (0.0, 0.0, 0.0):
            assert operation.tail_offset is not None
            payload["tail_offset"] = _render_float_vector(operation.tail_offset)

        if operation.inherit_rotation:
            payload["inherit_rotation"] = True
        if operation.inherit_translation:
            payload["inherit_translation"] = True
        if operation.inherit_rotation or operation.inherit_translation:
            assert operation.inherit_parent_bone_index is not None
            assert operation.inherit_weight is not None
            payload["inherit_parent_bone_index"] = (
                operation.inherit_parent_bone_index
            )
            payload["inherit_weight"] = _canonical_json_float(
                operation.inherit_weight
            )

        if operation.fixed_axis is not None:
            payload["fixed_axis"] = _render_float_vector(operation.fixed_axis)
        if operation.local_axis_x is not None:
            assert operation.local_axis_z is not None
            payload["local_axis_x"] = _render_float_vector(operation.local_axis_x)
            payload["local_axis_z"] = _render_float_vector(operation.local_axis_z)
        if operation.external_parent_key is not None:
            payload["external_parent_key"] = operation.external_parent_key
        if operation.ik is not None:
            payload["ik"] = _render_bone_ik(operation.ik)

        _append_insertion_metadata(
            payload,
            position=operation.position,
            source_index=operation.source_index,
            new_id=operation.new_id,
        )
        return payload

    if isinstance(operation, PmxStructuralMorphInsertion):
        payload = {
            "op": PmxStructuralTransactionOperationType.INSERT_MORPH.value,
            "local_name": operation.local_name,
            "morph_type": operation.morph_type,
        }
        if operation.universal_name != "":
            payload["universal_name"] = operation.universal_name
        if operation.panel != "other":
            payload["panel"] = operation.panel
        if operation.offsets:
            payload["offsets"] = [
                _render_morph_offset(offset) for offset in operation.offsets
            ]
        _append_insertion_metadata(
            payload,
            position=operation.position,
            source_index=operation.source_index,
            new_id=operation.new_id,
        )
        return payload

    if isinstance(operation, PmxStructuralRigidBodyInsertion):
        payload = {
            "op": PmxStructuralTransactionOperationType.INSERT_RIGID_BODY.value,
            "local_name": operation.local_name,
        }
        if operation.universal_name != "":
            payload["universal_name"] = operation.universal_name
        if operation.bone_index != -1:
            payload["bone_index"] = _render_reference(operation.bone_index)
        if operation.collision_group != 0:
            payload["collision_group"] = operation.collision_group
        if operation.collision_mask != 0xFFFF:
            payload["collision_mask"] = operation.collision_mask
        if operation.shape != "sphere":
            payload["shape"] = operation.shape
        if operation.size != (1.0, 1.0, 1.0):
            payload["size"] = _render_float_vector(operation.size)
        if operation.body_position != (0.0, 0.0, 0.0):
            payload["body_position"] = _render_float_vector(operation.body_position)
        if operation.rotation != (0.0, 0.0, 0.0):
            payload["rotation"] = _render_float_vector(operation.rotation)
        if operation.mass != 1.0:
            payload["mass"] = _canonical_json_float(operation.mass)
        if operation.linear_damping != 0.5:
            payload["linear_damping"] = _canonical_json_float(
                operation.linear_damping
            )
        if operation.angular_damping != 0.5:
            payload["angular_damping"] = _canonical_json_float(
                operation.angular_damping
            )
        if operation.restitution != 0.0:
            payload["restitution"] = _canonical_json_float(operation.restitution)
        if operation.friction != 0.5:
            payload["friction"] = _canonical_json_float(operation.friction)
        if operation.physics_mode != "bone_follow":
            payload["physics_mode"] = operation.physics_mode
        _append_insertion_metadata(
            payload,
            position=operation.position,
            source_index=operation.source_index,
            new_id=operation.new_id,
        )
        return payload

    if isinstance(operation, PmxStructuralVertexInsertion):
        payload = {
            "op": PmxStructuralTransactionOperationType.INSERT_VERTEX.value,
            "vertex_position": _render_float_vector(operation.vertex_position),
            "normal": _render_float_vector(operation.normal),
            "uv": _render_float_vector(operation.uv),
            "additional_uvs": [
                _render_float_vector(vector) for vector in operation.additional_uvs
            ],
            "deform": _render_vertex_deform(operation.deform),
            "edge_scale": _canonical_json_float(operation.edge_scale),
        }
        _append_insertion_metadata(
            payload,
            position=operation.position,
            source_index=operation.source_index,
            new_id=operation.new_id,
        )
        return payload

    raise TypeError(
        "validated transaction plan exposed an unsupported operation type."
    )


def render_pmx_structural_transaction_plan_json(
    plan: PmxStructuralTransactionPlan,
) -> str:
    """Render one immutable plan to canonical deterministic schema-one JSON."""

    if not isinstance(plan, PmxStructuralTransactionPlan):
        raise TypeError("plan must be a PmxStructuralTransactionPlan instance.")

    payload: dict[str, object] = {
        "schema_version": plan.schema_version,
    }
    if plan.expected_source_sha256 is not None:
        payload["expected_source_sha256"] = plan.expected_source_sha256
    payload["operations"] = [
        _render_transaction_operation(operation) for operation in plan.operations
    ]

    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        + "\n"
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
    "render_pmx_structural_transaction_plan_json",
    "PmxStructuralTransactionPlan",
)
