"""Public bounded semantic DTOs for CP15 vertex insertion preview requests."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, TypeAlias


def _is_plain_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _require_plain_int(value: object, field_name: str) -> int:
    if not _is_plain_int(value):
        raise TypeError(f"{field_name} must be an integer.")
    return value


def _require_source_bone_index(value: object, field_name: str) -> int:
    index = _require_plain_int(value, field_name)
    if index < -1:
        raise ValueError(f"{field_name} cannot be smaller than -1.")
    return index


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


def _require_bone_index_tuple(
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
        _require_source_bone_index(item, f"{field_name} value")


@dataclass(frozen=True, slots=True)
class PmxStructuralVertexBdef1:
    """One source-domain BDEF1 payload for an inserted vertex."""

    bone_index: int

    def __post_init__(self) -> None:
        _require_source_bone_index(self.bone_index, "bone_index")


@dataclass(frozen=True, slots=True)
class PmxStructuralVertexBdef2:
    """One source-domain BDEF2 payload for an inserted vertex."""

    bone_indices: tuple[int, int]
    bone_1_weight: float

    def __post_init__(self) -> None:
        _require_bone_index_tuple(
            self.bone_indices,
            field_name="bone_indices",
            length=2,
        )
        _require_finite_float(self.bone_1_weight, "bone_1_weight")


@dataclass(frozen=True, slots=True)
class PmxStructuralVertexBdef4:
    """One source-domain BDEF4 payload for an inserted vertex."""

    bone_indices: tuple[int, int, int, int]
    weights: tuple[float, float, float, float]

    def __post_init__(self) -> None:
        _require_bone_index_tuple(
            self.bone_indices,
            field_name="bone_indices",
            length=4,
        )
        _require_float_tuple(self.weights, field_name="weights", length=4)


@dataclass(frozen=True, slots=True)
class PmxStructuralVertexSdef:
    """One source-domain SDEF payload for an inserted vertex."""

    bone_indices: tuple[int, int]
    bone_1_weight: float
    c: tuple[float, float, float]
    r0: tuple[float, float, float]
    r1: tuple[float, float, float]

    def __post_init__(self) -> None:
        _require_bone_index_tuple(
            self.bone_indices,
            field_name="bone_indices",
            length=2,
        )
        _require_finite_float(self.bone_1_weight, "bone_1_weight")
        for field_name in ("c", "r0", "r1"):
            _require_float_tuple(
                getattr(self, field_name),
                field_name=field_name,
                length=3,
            )


@dataclass(frozen=True, slots=True)
class PmxStructuralVertexQdef:
    """One source-domain QDEF payload; PMX 2.1 is enforced by preview."""

    bone_indices: tuple[int, int, int, int]
    weights: tuple[float, float, float, float]

    def __post_init__(self) -> None:
        _require_bone_index_tuple(
            self.bone_indices,
            field_name="bone_indices",
            length=4,
        )
        _require_float_tuple(self.weights, field_name="weights", length=4)


_PmxStructuralVertexDeform: TypeAlias = (
    PmxStructuralVertexBdef1
    | PmxStructuralVertexBdef2
    | PmxStructuralVertexBdef4
    | PmxStructuralVertexSdef
    | PmxStructuralVertexQdef
)


@dataclass(frozen=True, slots=True)
class PmxStructuralVertexInsertion:
    """One semantic PMX vertex insertion with source-domain bone references."""

    vertex_position: tuple[float, float, float]
    normal: tuple[float, float, float]
    uv: tuple[float, float]
    additional_uvs: tuple[tuple[float, float, float, float], ...]
    deform: _PmxStructuralVertexDeform
    edge_scale: float
    position: Literal["append", "insert_before"] = "append"
    source_index: int | None = None

    def __post_init__(self) -> None:
        _require_float_tuple(
            self.vertex_position,
            field_name="vertex_position",
            length=3,
        )
        _require_float_tuple(self.normal, field_name="normal", length=3)
        _require_float_tuple(self.uv, field_name="uv", length=2)

        if type(self.additional_uvs) is not tuple:
            raise TypeError("additional_uvs must be a tuple.")
        if len(self.additional_uvs) > 4:
            raise ValueError("additional_uvs cannot contain more than 4 vectors.")
        for index, additional_uv in enumerate(self.additional_uvs):
            _require_float_tuple(
                additional_uv,
                field_name=f"additional_uvs[{index}]",
                length=4,
            )

        if not isinstance(
            self.deform,
            (
                PmxStructuralVertexBdef1,
                PmxStructuralVertexBdef2,
                PmxStructuralVertexBdef4,
                PmxStructuralVertexSdef,
                PmxStructuralVertexQdef,
            ),
        ):
            raise TypeError("deform must be a supported structural vertex deform DTO.")
        _require_finite_float(self.edge_scale, "edge_scale")

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
    "PmxStructuralVertexBdef1",
    "PmxStructuralVertexBdef2",
    "PmxStructuralVertexBdef4",
    "PmxStructuralVertexSdef",
    "PmxStructuralVertexQdef",
    "PmxStructuralVertexInsertion",
)
