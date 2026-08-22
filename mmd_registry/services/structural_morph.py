"""Public bounded semantic DTOs for CP13/CP14 morph insertion requests."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, TypeAlias

from mmd_registry.services.structural_reference import (
    PmxStructuralNewReference,
    _require_optional_new_id,
)


_PmxStructuralCrossReference: TypeAlias = int | PmxStructuralNewReference


PmxStructuralMorphPanel: TypeAlias = Literal[
    "system",
    "eyebrow",
    "eye",
    "mouth",
    "other",
]
PmxStructuralMorphType: TypeAlias = Literal[
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
]
PmxStructuralMaterialMorphOperation: TypeAlias = Literal["multiply", "add"]


def _is_plain_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _require_nonnegative_index(value: object, field_name: str) -> None:
    if not _is_plain_int(value):
        raise TypeError(f"{field_name} must be an integer.")
    if value < 0:
        raise ValueError(f"{field_name} cannot be negative.")


def _require_optional_index(value: object, field_name: str) -> None:
    if not _is_plain_int(value):
        raise TypeError(f"{field_name} must be an integer.")
    if value < -1:
        raise ValueError(f"{field_name} cannot be smaller than -1.")



def _require_cross_reference(
    value: object,
    field_name: str,
    *,
    target_kind: str,
    allow_sentinel: bool = False,
) -> None:
    if isinstance(value, PmxStructuralNewReference):
        if value.target_kind != target_kind:
            raise ValueError(
                f"{field_name} new reference must target {target_kind}."
            )
        return
    if allow_sentinel:
        _require_optional_index(value, field_name)
    else:
        _require_nonnegative_index(value, field_name)

def _require_finite_float(value: object, field_name: str) -> None:
    if not isinstance(value, float):
        raise TypeError(f"{field_name} must be a float.")
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite.")


def _require_float_tuple(
    value: object,
    *,
    field_name: str,
    length: int,
) -> None:
    if type(value) is not tuple:
        raise TypeError(f"{field_name} must be a tuple.")
    if len(value) != length:
        raise ValueError(f"{field_name} must contain exactly {length} values.")
    for item in value:
        _require_finite_float(item, f"{field_name} value")


@dataclass(frozen=True, slots=True)
class PmxStructuralMorphGroupOffset:
    """One source-domain group-morph target and influence weight."""

    morph_index: int
    weight: float

    def __post_init__(self) -> None:
        _require_nonnegative_index(self.morph_index, "morph_index")
        _require_finite_float(self.weight, "weight")


@dataclass(frozen=True, slots=True)
class PmxStructuralMorphVertexOffset:
    """One existing vertex target and displacement."""

    vertex_index: _PmxStructuralCrossReference
    translation: tuple[float, float, float]

    def __post_init__(self) -> None:
        _require_cross_reference(
            self.vertex_index,
            "vertex_index",
            target_kind="vertex",
        )
        _require_float_tuple(
            self.translation,
            field_name="translation",
            length=3,
        )


@dataclass(frozen=True, slots=True)
class PmxStructuralMorphBoneOffset:
    """One existing bone target and translation/quaternion payload."""

    bone_index: _PmxStructuralCrossReference
    translation: tuple[float, float, float]
    rotation: tuple[float, float, float, float]

    def __post_init__(self) -> None:
        _require_cross_reference(
            self.bone_index,
            "bone_index",
            target_kind="bone",
        )
        _require_float_tuple(
            self.translation,
            field_name="translation",
            length=3,
        )
        _require_float_tuple(
            self.rotation,
            field_name="rotation",
            length=4,
        )


@dataclass(frozen=True, slots=True)
class PmxStructuralMorphUvOffset:
    """One existing vertex target and base/additional-UV displacement."""

    vertex_index: _PmxStructuralCrossReference
    uv_offset: tuple[float, float, float, float]

    def __post_init__(self) -> None:
        _require_cross_reference(
            self.vertex_index,
            "vertex_index",
            target_kind="vertex",
        )
        _require_float_tuple(
            self.uv_offset,
            field_name="uv_offset",
            length=4,
        )


@dataclass(frozen=True, slots=True)
class PmxStructuralMorphMaterialOffset:
    """One material-morph operation against one source material or all materials."""

    material_index: _PmxStructuralCrossReference
    operation: PmxStructuralMaterialMorphOperation
    diffuse: tuple[float, float, float, float]
    specular: tuple[float, float, float]
    specular_strength: float
    ambient: tuple[float, float, float]
    edge_color: tuple[float, float, float, float]
    edge_scale: float
    texture_tint: tuple[float, float, float, float]
    sphere_tint: tuple[float, float, float, float]
    toon_tint: tuple[float, float, float, float]

    def __post_init__(self) -> None:
        _require_cross_reference(
            self.material_index,
            "material_index",
            target_kind="material",
            allow_sentinel=True,
        )
        if self.operation not in ("multiply", "add"):
            raise ValueError("operation must be either 'multiply' or 'add'.")
        for field_name, length in (
            ("diffuse", 4),
            ("specular", 3),
            ("ambient", 3),
            ("edge_color", 4),
            ("texture_tint", 4),
            ("sphere_tint", 4),
            ("toon_tint", 4),
        ):
            _require_float_tuple(
                getattr(self, field_name),
                field_name=field_name,
                length=length,
            )
        _require_finite_float(self.specular_strength, "specular_strength")
        _require_finite_float(self.edge_scale, "edge_scale")


@dataclass(frozen=True, slots=True)
class PmxStructuralMorphFlipOffset:
    """One PMX 2.1 source-domain flip-morph target and influence weight."""

    morph_index: int
    weight: float

    def __post_init__(self) -> None:
        _require_nonnegative_index(self.morph_index, "morph_index")
        _require_finite_float(self.weight, "weight")


@dataclass(frozen=True, slots=True)
class PmxStructuralMorphImpulseOffset:
    """One PMX 2.1 impulse against an existing source rigid body."""

    rigid_body_index: _PmxStructuralCrossReference
    local: bool
    velocity: tuple[float, float, float]
    angular_torque: tuple[float, float, float]

    def __post_init__(self) -> None:
        _require_cross_reference(
            self.rigid_body_index,
            "rigid_body_index",
            target_kind="rigid_body",
        )
        if not isinstance(self.local, bool):
            raise TypeError("local must be a boolean.")
        _require_float_tuple(self.velocity, field_name="velocity", length=3)
        _require_float_tuple(
            self.angular_torque,
            field_name="angular_torque",
            length=3,
        )


PmxStructuralMorphOffset: TypeAlias = (
    PmxStructuralMorphGroupOffset
    | PmxStructuralMorphVertexOffset
    | PmxStructuralMorphBoneOffset
    | PmxStructuralMorphUvOffset
    | PmxStructuralMorphMaterialOffset
    | PmxStructuralMorphFlipOffset
    | PmxStructuralMorphImpulseOffset
)


_MORPH_TYPES: tuple[str, ...] = (
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
_EXPECTED_OFFSET_TYPES: tuple[type[object], ...] = (
    PmxStructuralMorphGroupOffset,
    PmxStructuralMorphVertexOffset,
    PmxStructuralMorphBoneOffset,
    PmxStructuralMorphUvOffset,
    PmxStructuralMorphUvOffset,
    PmxStructuralMorphUvOffset,
    PmxStructuralMorphUvOffset,
    PmxStructuralMorphUvOffset,
    PmxStructuralMorphMaterialOffset,
    PmxStructuralMorphFlipOffset,
    PmxStructuralMorphImpulseOffset,
)


@dataclass(frozen=True, slots=True)
class PmxStructuralMorphInsertion:
    """One semantic PMX morph insertion with bounded source-domain references."""

    local_name: str
    morph_type: PmxStructuralMorphType
    universal_name: str = ""
    panel: PmxStructuralMorphPanel = "other"
    offsets: tuple[PmxStructuralMorphOffset, ...] = ()
    position: Literal["append", "insert_before"] = "append"
    source_index: int | None = None
    new_id: str | None = None

    def __post_init__(self) -> None:
        _require_optional_new_id(self.new_id)
        for field_name in ("local_name", "universal_name"):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"{field_name} must be a string.")

        if self.panel not in ("system", "eyebrow", "eye", "mouth", "other"):
            raise ValueError(
                "panel must be system, eyebrow, eye, mouth, or other."
            )
        if self.morph_type not in _MORPH_TYPES:
            raise ValueError(
                "morph_type must be one of the CP13/CP14 semantic morph types."
            )

        if type(self.offsets) is not tuple:
            raise TypeError("offsets must be a tuple.")
        expected = _EXPECTED_OFFSET_TYPES[_MORPH_TYPES.index(self.morph_type)]
        if not all(isinstance(offset, expected) for offset in self.offsets):
            raise TypeError(
                f"{self.morph_type} morph offsets must contain only "
                f"{expected.__name__} values."
            )

        if not isinstance(self.position, str):
            raise TypeError("position must be a string.")
        if self.position not in ("append", "insert_before"):
            raise ValueError("position must be either 'append' or 'insert_before'.")

        if self.position == "append":
            if self.source_index is not None:
                raise ValueError("append insertion cannot define source_index.")
            return

        if type(self.source_index) is not int:
            raise TypeError("insert_before source_index must be an integer.")
        if self.source_index < 0:
            raise ValueError("insert_before source_index cannot be negative.")


__all__ = (
    "PmxStructuralMorphGroupOffset",
    "PmxStructuralMorphVertexOffset",
    "PmxStructuralMorphBoneOffset",
    "PmxStructuralMorphUvOffset",
    "PmxStructuralMorphMaterialOffset",
    "PmxStructuralMorphFlipOffset",
    "PmxStructuralMorphImpulseOffset",
    "PmxStructuralMorphInsertion",
)
