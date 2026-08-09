"""Immutable typed operations for declarative PMX editing."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import ClassVar, Final, Literal, TypeAlias


MODEL_INFO_FIELDS: Final[tuple[str, ...]] = (
    "local_name",
    "universal_name",
    "local_comments",
    "universal_comments",
)

MATERIAL_FIELDS: Final[tuple[str, ...]] = (
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
)


def _is_plain_int(value: object) -> bool:
    """Return whether a value is an integer but not a boolean."""

    return isinstance(value, int) and not isinstance(value, bool)


def _validate_nonnegative_index(value: object, field_name: str) -> None:
    """Require one explicit nonnegative record index."""

    if not _is_plain_int(value):
        raise TypeError(f"{field_name} must be an integer.")
    if value < 0:
        raise ValueError(f"{field_name} cannot be negative.")


def _validate_optional_string(value: object, field_name: str) -> None:
    """Require an optional string without coercion."""

    if value is not None and not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string when provided.")


def _validate_optional_reference(value: object, field_name: str) -> None:
    """Require an optional PMX reference index with the -1 sentinel."""

    if value is None:
        return
    if not _is_plain_int(value):
        raise TypeError(f"{field_name} must be an integer when provided.")
    if value < -1:
        raise ValueError(f"{field_name} cannot be smaller than -1.")


def _validate_optional_float(value: object, field_name: str) -> None:
    """Require an optional finite explicit float."""

    if value is None:
        return
    if not isinstance(value, float):
        raise TypeError(f"{field_name} must be a float when provided.")
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite.")


def _validate_optional_float_tuple(
    value: object,
    *,
    field_name: str,
    length: int,
) -> None:
    """Require an optional immutable vector of finite explicit floats."""

    if value is None:
        return
    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be a tuple when provided.")
    if len(value) != length:
        raise ValueError(f"{field_name} must contain exactly {length} values.")
    for item in value:
        _validate_optional_float(item, f"{field_name} value")


def _value_to_json(value: object) -> object:
    """Convert one immutable operation value to a JSON-compatible value."""

    if isinstance(value, tuple):
        return list(value)
    return value


@dataclass(frozen=True, slots=True)
class PmxEditTarget:
    """One field targeted by an operation and its payload field name."""

    field_path: str
    payload_field: str


@dataclass(frozen=True, slots=True)
class SetModelInfo:
    """Replace one or more existing PMX model-information fields."""

    operation_name: ClassVar[Literal["set_model_info"]] = "set_model_info"

    local_name: str | None = None
    universal_name: str | None = None
    local_comments: str | None = None
    universal_comments: str | None = None

    def __post_init__(self) -> None:
        for field_name in MODEL_INFO_FIELDS:
            _validate_optional_string(getattr(self, field_name), field_name)

        if not any(getattr(self, name) is not None for name in MODEL_INFO_FIELDS):
            raise ValueError("set_model_info must update at least one field.")

    def targets(self) -> tuple[PmxEditTarget, ...]:
        """Return declared targets in stable field order."""

        return tuple(
            PmxEditTarget(
                field_path=f"model_info.{field_name}",
                payload_field=field_name,
            )
            for field_name in MODEL_INFO_FIELDS
            if getattr(self, field_name) is not None
        )

    def to_dict(self) -> dict[str, object]:
        """Return a stable JSON-compatible operation representation."""

        payload: dict[str, object] = {"op": self.operation_name}
        for field_name in MODEL_INFO_FIELDS:
            value = getattr(self, field_name)
            if value is not None:
                payload[field_name] = value
        return payload


@dataclass(frozen=True, slots=True)
class SetTexturePath:
    """Replace one existing texture path by its zero-based index."""

    operation_name: ClassVar[Literal["set_texture_path"]] = "set_texture_path"

    texture_index: int
    path: str

    def __post_init__(self) -> None:
        _validate_nonnegative_index(self.texture_index, "texture_index")
        if not isinstance(self.path, str):
            raise TypeError("path must be a string.")

    def targets(self) -> tuple[PmxEditTarget, ...]:
        """Return the single declared texture target."""

        return (
            PmxEditTarget(
                field_path=f"textures[{self.texture_index}].path",
                payload_field="path",
            ),
        )

    def to_dict(self) -> dict[str, object]:
        """Return a stable JSON-compatible operation representation."""

        return {
            "op": self.operation_name,
            "texture_index": self.texture_index,
            "path": self.path,
        }


@dataclass(frozen=True, slots=True)
class UpdateMaterial:
    """Replace supported fields of one existing material record."""

    operation_name: ClassVar[Literal["update_material"]] = "update_material"

    material_index: int
    local_name: str | None = None
    universal_name: str | None = None
    memo: str | None = None
    texture_index: int | None = None
    sphere_texture_index: int | None = None
    sphere_mode: int | None = None
    toon_reference_mode: Literal["texture", "shared"] | None = None
    toon_reference_index: int | None = None
    diffuse: tuple[float, float, float, float] | None = None
    specular: tuple[float, float, float] | None = None
    specular_strength: float | None = None
    ambient: tuple[float, float, float] | None = None
    drawing_flags: int | None = None
    edge_color: tuple[float, float, float, float] | None = None
    edge_scale: float | None = None

    def __post_init__(self) -> None:
        _validate_nonnegative_index(self.material_index, "material_index")

        for field_name in ("local_name", "universal_name", "memo"):
            _validate_optional_string(getattr(self, field_name), field_name)

        for field_name in (
            "texture_index",
            "sphere_texture_index",
            "toon_reference_index",
        ):
            _validate_optional_reference(getattr(self, field_name), field_name)

        if self.sphere_mode is not None:
            if not _is_plain_int(self.sphere_mode):
                raise TypeError("sphere_mode must be an integer when provided.")
            if self.sphere_mode not in (0, 1, 2, 3):
                raise ValueError("sphere_mode must be a value from 0 through 3.")

        if self.toon_reference_mode is not None and self.toon_reference_mode not in (
            "texture",
            "shared",
        ):
            raise ValueError(
                "toon_reference_mode must be either 'texture' or 'shared'."
            )

        if (
            self.toon_reference_mode == "shared"
            and self.toon_reference_index is not None
            and not 0 <= self.toon_reference_index <= 9
        ):
            raise ValueError(
                "shared toon_reference_index must be a value from 0 through 9."
            )

        _validate_optional_float_tuple(
            self.diffuse,
            field_name="diffuse",
            length=4,
        )
        _validate_optional_float_tuple(
            self.specular,
            field_name="specular",
            length=3,
        )
        _validate_optional_float(
            self.specular_strength,
            "specular_strength",
        )
        _validate_optional_float_tuple(
            self.ambient,
            field_name="ambient",
            length=3,
        )
        _validate_optional_float_tuple(
            self.edge_color,
            field_name="edge_color",
            length=4,
        )
        _validate_optional_float(self.edge_scale, "edge_scale")

        if self.drawing_flags is not None:
            if not _is_plain_int(self.drawing_flags):
                raise TypeError("drawing_flags must be an integer when provided.")
            if not 0 <= self.drawing_flags <= 0xFF:
                raise ValueError("drawing_flags must fit in one unsigned byte.")

        if not any(getattr(self, name) is not None for name in MATERIAL_FIELDS):
            raise ValueError("update_material must update at least one field.")

    def targets(self) -> tuple[PmxEditTarget, ...]:
        """Return declared material targets in stable field order."""

        return tuple(
            PmxEditTarget(
                field_path=f"materials[{self.material_index}].{field_name}",
                payload_field=field_name,
            )
            for field_name in MATERIAL_FIELDS
            if getattr(self, field_name) is not None
        )

    def to_dict(self) -> dict[str, object]:
        """Return a stable JSON-compatible operation representation."""

        payload: dict[str, object] = {
            "op": self.operation_name,
            "material_index": self.material_index,
        }
        for field_name in MATERIAL_FIELDS:
            value = getattr(self, field_name)
            if value is not None:
                payload[field_name] = _value_to_json(value)
        return payload


PmxEditOperation: TypeAlias = SetModelInfo | SetTexturePath | UpdateMaterial
SUPPORTED_OPERATION_TYPES: Final[tuple[type[object], ...]] = (
    SetModelInfo,
    SetTexturePath,
    UpdateMaterial,
)


def operation_targets(
    operation: PmxEditOperation,
) -> tuple[PmxEditTarget, ...]:
    """Return stable target descriptors for one supported operation."""

    if not isinstance(operation, SUPPORTED_OPERATION_TYPES):
        raise TypeError(
            "operation must be SetModelInfo, SetTexturePath, or UpdateMaterial."
        )
    return operation.targets()


def operation_to_dict(operation: PmxEditOperation) -> dict[str, object]:
    """Return the stable representation of one supported operation."""

    if not isinstance(operation, SUPPORTED_OPERATION_TYPES):
        raise TypeError(
            "operation must be SetModelInfo, SetTexturePath, or UpdateMaterial."
        )
    return operation.to_dict()
