"""Strict UTF-8 JSON loading for declarative PMX edit plans."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Final

from mmd_registry.pmx.editing.errors import PmxEditPlanError
from mmd_registry.pmx.editing.operations import (
    MATERIAL_FIELDS,
    MODEL_INFO_FIELDS,
    PmxEditOperation,
    SetModelInfo,
    SetTexturePath,
    UpdateMaterial,
)
from mmd_registry.pmx.editing.plan import (
    PMX_EDIT_PLAN_SCHEMA_VERSION,
    PmxEditPlan,
)
from mmd_registry.pmx.editing.validation import validate_pmx_edit_plan


_TOP_LEVEL_FIELDS: Final[frozenset[str]] = frozenset(
    {"schema_version", "expected_source_sha256", "operations"}
)
_MODEL_INFO_JSON_FIELDS: Final[frozenset[str]] = frozenset(
    {"op", *MODEL_INFO_FIELDS}
)
_TEXTURE_PATH_JSON_FIELDS: Final[frozenset[str]] = frozenset(
    {"op", "texture_index", "path"}
)
_MATERIAL_JSON_FIELDS: Final[frozenset[str]] = frozenset(
    {"op", "material_index", *MATERIAL_FIELDS}
)
_MATERIAL_STRING_FIELDS: Final[tuple[str, ...]] = (
    "local_name",
    "universal_name",
    "memo",
)
_MATERIAL_REFERENCE_FIELDS: Final[tuple[str, ...]] = (
    "texture_index",
    "sphere_texture_index",
    "toon_reference_index",
)
_MATERIAL_VECTOR_FIELDS: Final[dict[str, int]] = {
    "diffuse": 4,
    "specular": 3,
    "ambient": 3,
    "edge_color": 4,
}
_MATERIAL_FLOAT_FIELDS: Final[tuple[str, ...]] = (
    "specular_strength",
    "edge_scale",
)
_LOWERCASE_HEX_DIGITS: Final[frozenset[str]] = frozenset("0123456789abcdef")


class _DuplicateJsonMemberError(ValueError):
    """Internal signal for a repeated member in one JSON object."""

    def __init__(self, member_name: str) -> None:
        self.member_name = member_name
        super().__init__(member_name)


class _NonstandardJsonConstantError(ValueError):
    """Internal signal for NaN or Infinity accepted by Python's decoder."""

    def __init__(self, constant: str) -> None:
        self.constant = constant
        super().__init__(constant)


def _strict_json_object(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    """Build one JSON object while rejecting duplicate member names."""

    result: dict[str, object] = {}
    for name, value in pairs:
        if name in result:
            raise _DuplicateJsonMemberError(name)
        result[name] = value
    return result


def _reject_json_constant(constant: str) -> object:
    """Reject non-standard numeric constants accepted by ``json.loads``."""

    raise _NonstandardJsonConstantError(constant)


def _field_error(
    reason: str,
    *,
    field: str,
    operation_index: int | None = None,
) -> PmxEditPlanError:
    """Build one consistently contextual field error."""

    return PmxEditPlanError(
        reason,
        operation_index=operation_index,
        field=field,
    )


def _reject_unknown_fields(
    payload: dict[str, object],
    allowed_fields: frozenset[str],
    *,
    operation_index: int | None = None,
) -> None:
    """Reject the first unknown member in deterministic lexical order."""

    unknown_fields = sorted(set(payload) - allowed_fields)
    if unknown_fields:
        field = unknown_fields[0]
        raise _field_error(
            f"unknown field {field!r}.",
            field=field,
            operation_index=operation_index,
        )


def _require_field(
    payload: dict[str, object],
    field: str,
    *,
    operation_index: int | None = None,
) -> object:
    """Return one required JSON member with stable missing-field context."""

    if field not in payload:
        raise _field_error(
            "field is required.",
            field=field,
            operation_index=operation_index,
        )
    return payload[field]


def _require_string(
    value: object,
    *,
    field: str,
    operation_index: int | None = None,
) -> str:
    """Require one exact JSON string without coercion."""

    if type(value) is not str:
        raise _field_error(
            "value must be a JSON string.",
            field=field,
            operation_index=operation_index,
        )
    return value


def _require_integer(
    value: object,
    *,
    field: str,
    operation_index: int | None = None,
) -> int:
    """Require one exact JSON integer, excluding booleans and floats."""

    if type(value) is not int:
        raise _field_error(
            "value must be a JSON integer; booleans and floats are invalid.",
            field=field,
            operation_index=operation_index,
        )
    return value


def _require_float(
    value: object,
    *,
    field: str,
    operation_index: int,
) -> float:
    """Require one exact finite JSON floating-point value."""

    if type(value) is not float:
        raise _field_error(
            "value must be a JSON float; integers are not coerced.",
            field=field,
            operation_index=operation_index,
        )
    if not math.isfinite(value):
        raise _field_error(
            "floating-point value must be finite.",
            field=field,
            operation_index=operation_index,
        )
    return value


def _require_vector(
    value: object,
    *,
    field: str,
    length: int,
    operation_index: int,
) -> tuple[float, ...]:
    """Require one exact-length JSON array containing only finite floats."""

    if type(value) is not list:
        raise _field_error(
            "value must be a JSON array.",
            field=field,
            operation_index=operation_index,
        )
    if len(value) != length:
        raise _field_error(
            f"array must contain exactly {length} values.",
            field=field,
            operation_index=operation_index,
        )

    return tuple(
        _require_float(
            component,
            field=f"{field}[{component_index}]",
            operation_index=operation_index,
        )
        for component_index, component in enumerate(value)
    )


def _parse_model_info_operation(
    payload: dict[str, object],
    *,
    operation_index: int,
) -> SetModelInfo:
    """Parse one strict set-model-info operation."""

    _reject_unknown_fields(
        payload,
        _MODEL_INFO_JSON_FIELDS,
        operation_index=operation_index,
    )
    updates = {
        field: _require_string(
            payload[field],
            field=field,
            operation_index=operation_index,
        )
        for field in MODEL_INFO_FIELDS
        if field in payload
    }
    if not updates:
        raise PmxEditPlanError(
            "set_model_info must update at least one field.",
            operation_index=operation_index,
        )
    return SetModelInfo(**updates)


def _parse_texture_path_operation(
    payload: dict[str, object],
    *,
    operation_index: int,
) -> SetTexturePath:
    """Parse one strict indexed texture-path operation."""

    _reject_unknown_fields(
        payload,
        _TEXTURE_PATH_JSON_FIELDS,
        operation_index=operation_index,
    )
    texture_index = _require_integer(
        _require_field(
            payload,
            "texture_index",
            operation_index=operation_index,
        ),
        field="texture_index",
        operation_index=operation_index,
    )
    if texture_index < 0:
        raise _field_error(
            "value cannot be negative.",
            field="texture_index",
            operation_index=operation_index,
        )
    path = _require_string(
        _require_field(payload, "path", operation_index=operation_index),
        field="path",
        operation_index=operation_index,
    )
    return SetTexturePath(texture_index=texture_index, path=path)


def _parse_material_operation(
    payload: dict[str, object],
    *,
    operation_index: int,
) -> UpdateMaterial:
    """Parse one strict indexed material-update operation."""

    _reject_unknown_fields(
        payload,
        _MATERIAL_JSON_FIELDS,
        operation_index=operation_index,
    )
    material_index = _require_integer(
        _require_field(
            payload,
            "material_index",
            operation_index=operation_index,
        ),
        field="material_index",
        operation_index=operation_index,
    )
    if material_index < 0:
        raise _field_error(
            "value cannot be negative.",
            field="material_index",
            operation_index=operation_index,
        )

    updates: dict[str, object] = {}
    for field in _MATERIAL_STRING_FIELDS:
        if field in payload:
            updates[field] = _require_string(
                payload[field],
                field=field,
                operation_index=operation_index,
            )

    for field in _MATERIAL_REFERENCE_FIELDS:
        if field not in payload:
            continue
        value = _require_integer(
            payload[field],
            field=field,
            operation_index=operation_index,
        )
        if value < -1:
            raise _field_error(
                "reference index cannot be smaller than -1.",
                field=field,
                operation_index=operation_index,
            )
        updates[field] = value

    if "sphere_mode" in payload:
        sphere_mode = _require_integer(
            payload["sphere_mode"],
            field="sphere_mode",
            operation_index=operation_index,
        )
        if sphere_mode not in (0, 1, 2, 3):
            raise _field_error(
                "value must be from 0 through 3.",
                field="sphere_mode",
                operation_index=operation_index,
            )
        updates["sphere_mode"] = sphere_mode

    if "toon_reference_mode" in payload:
        toon_mode = _require_string(
            payload["toon_reference_mode"],
            field="toon_reference_mode",
            operation_index=operation_index,
        )
        if toon_mode not in ("texture", "shared"):
            raise _field_error(
                "value must be either 'texture' or 'shared'.",
                field="toon_reference_mode",
                operation_index=operation_index,
            )
        updates["toon_reference_mode"] = toon_mode

    for field, length in _MATERIAL_VECTOR_FIELDS.items():
        if field in payload:
            updates[field] = _require_vector(
                payload[field],
                field=field,
                length=length,
                operation_index=operation_index,
            )

    for field in _MATERIAL_FLOAT_FIELDS:
        if field in payload:
            updates[field] = _require_float(
                payload[field],
                field=field,
                operation_index=operation_index,
            )

    if "drawing_flags" in payload:
        drawing_flags = _require_integer(
            payload["drawing_flags"],
            field="drawing_flags",
            operation_index=operation_index,
        )
        if not 0 <= drawing_flags <= 0xFF:
            raise _field_error(
                "value must fit in one unsigned byte.",
                field="drawing_flags",
                operation_index=operation_index,
            )
        updates["drawing_flags"] = drawing_flags

    if not updates:
        raise PmxEditPlanError(
            "update_material must update at least one field.",
            operation_index=operation_index,
        )

    toon_mode = updates.get("toon_reference_mode")
    toon_index = updates.get("toon_reference_index")
    if toon_mode == "shared" and toon_index is not None and toon_index > 9:
        raise _field_error(
            "shared toon reference index must be from 0 through 9.",
            field="toon_reference_index",
            operation_index=operation_index,
        )

    return UpdateMaterial(material_index=material_index, **updates)


def _parse_operation(
    payload: object,
    *,
    operation_index: int,
) -> PmxEditOperation:
    """Parse one exact operation object and dispatch by its name."""

    if type(payload) is not dict:
        raise PmxEditPlanError(
            "operation must be a JSON object.",
            operation_index=operation_index,
        )

    operation_name = _require_string(
        _require_field(payload, "op", operation_index=operation_index),
        field="op",
        operation_index=operation_index,
    )
    if operation_name == "set_model_info":
        return _parse_model_info_operation(
            payload,
            operation_index=operation_index,
        )
    if operation_name == "set_texture_path":
        return _parse_texture_path_operation(
            payload,
            operation_index=operation_index,
        )
    if operation_name == "update_material":
        return _parse_material_operation(
            payload,
            operation_index=operation_index,
        )
    raise _field_error(
        f"unsupported operation name {operation_name!r}.",
        field="op",
        operation_index=operation_index,
    )


def _parse_decoded_plan(payload: object) -> PmxEditPlan:
    """Convert one decoded strict-JSON value into an immutable plan."""

    if type(payload) is not dict:
        raise PmxEditPlanError("top-level JSON value must be an object.")

    _reject_unknown_fields(payload, _TOP_LEVEL_FIELDS)
    schema_version = _require_integer(
        _require_field(payload, "schema_version"),
        field="schema_version",
    )
    if schema_version != PMX_EDIT_PLAN_SCHEMA_VERSION:
        raise _field_error(
            (
                f"unsupported schema version {schema_version}; expected "
                f"{PMX_EDIT_PLAN_SCHEMA_VERSION}."
            ),
            field="schema_version",
        )

    operations_value = _require_field(payload, "operations")
    if type(operations_value) is not list:
        raise _field_error(
            "value must be a JSON array.",
            field="operations",
        )
    if not operations_value:
        raise _field_error(
            "array must contain at least one operation.",
            field="operations",
        )
    operations = tuple(
        _parse_operation(operation, operation_index=index)
        for index, operation in enumerate(operations_value)
    )

    expected_source_sha256 = None
    if "expected_source_sha256" in payload:
        expected_source_sha256 = _require_string(
            payload["expected_source_sha256"],
            field="expected_source_sha256",
        )
        if (
            len(expected_source_sha256) != 64
            or not set(expected_source_sha256) <= _LOWERCASE_HEX_DIGITS
        ):
            raise _field_error(
                (
                    "value must be exactly 64 lowercase hexadecimal "
                    "characters."
                ),
                field="expected_source_sha256",
            )

    plan = PmxEditPlan(
        operations=operations,
        schema_version=schema_version,
        expected_source_sha256=expected_source_sha256,
    )
    validate_pmx_edit_plan(plan)
    return plan


def parse_pmx_edit_plan_json(text: str) -> PmxEditPlan:
    """Parse one strict JSON string into a validated immutable edit plan."""

    if type(text) is not str:
        raise TypeError("text must be a string.")
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_strict_json_object,
            parse_constant=_reject_json_constant,
        )
    except _DuplicateJsonMemberError as error:
        raise PmxEditPlanError(
            f"duplicate JSON member {error.member_name!r}."
        ) from error
    except _NonstandardJsonConstantError as error:
        raise PmxEditPlanError(
            f"numeric constant {error.constant!r} is not valid JSON."
        ) from error
    except json.JSONDecodeError as error:
        raise PmxEditPlanError(
            (
                f"invalid JSON at line {error.lineno}, column "
                f"{error.colno}: {error.msg}."
            )
        ) from error

    return _parse_decoded_plan(payload)


def load_pmx_edit_plan(path: str | Path) -> PmxEditPlan:
    """Read one UTF-8 JSON file and return its validated immutable plan."""

    if not isinstance(path, (str, Path)):
        raise TypeError("path must be a string or pathlib.Path.")
    plan_path = Path(path)
    try:
        text = plan_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise PmxEditPlanError(
            "edit-plan file must contain valid UTF-8 text."
        ) from error
    return parse_pmx_edit_plan_json(text)
