"""Immutable core types for a complete in-memory PMX document.

This module starts with the header and model-information types shared by all
PMX sections. Section records and the top-level ``PmxDocument`` are introduced
incrementally before any writer is exposed, so no public API can mistake a
header-only object for a complete model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Final, Literal, TypeAlias


PmxVersion: TypeAlias = Literal[2.0, 2.1]
PmxTextEncoding: TypeAlias = Literal["utf-16-le", "utf-8"]

SUPPORTED_PMX_VERSIONS: Final[tuple[float, ...]] = (2.0, 2.1)
VALID_PMX_TEXT_ENCODINGS: Final[frozenset[str]] = frozenset(
    {"utf-16-le", "utf-8"}
)
VALID_PMX_INDEX_SIZES: Final[frozenset[int]] = frozenset({1, 2, 4})
MIN_PMX_GLOBAL_COUNT: Final[int] = 8
MAX_PMX_GLOBAL_COUNT: Final[int] = 64
MIN_PMX_ADDITIONAL_UV_COUNT: Final[int] = 0
MAX_PMX_ADDITIONAL_UV_COUNT: Final[int] = 4


def _is_plain_int(value: object) -> bool:
    """Return whether value is an integer but not a boolean."""

    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True, slots=True)
class PmxIndexSizes:
    """Index widths declared by the six standard PMX global fields."""

    vertex: int
    texture: int
    material: int
    bone: int
    morph: int
    rigid_body: int

    def __post_init__(self) -> None:
        for field_name in (
            "vertex",
            "texture",
            "material",
            "bone",
            "morph",
            "rigid_body",
        ):
            value = getattr(self, field_name)

            if not _is_plain_int(value) or value not in VALID_PMX_INDEX_SIZES:
                raise ValueError(
                    f"{field_name} index size must be one of "
                    f"{sorted(VALID_PMX_INDEX_SIZES)}; got {value!r}."
                )

    def to_dict(self) -> dict[str, int]:
        """Return the stable legacy-compatible JSON representation."""

        return {
            "vertex": self.vertex,
            "texture": self.texture,
            "material": self.material,
            "bone": self.bone,
            "morph": self.morph,
            "rigid_body": self.rigid_body,
        }


@dataclass(frozen=True, slots=True)
class PmxHeader:
    """Byte-relevant PMX header settings required for safe serialization."""

    version: PmxVersion
    encoding: PmxTextEncoding
    additional_uv_count: int
    index_sizes: PmxIndexSizes
    extra_global_data: bytes = b""

    def __post_init__(self) -> None:
        if not isinstance(self.version, float) or isinstance(self.version, bool):
            raise TypeError("PMX version must be a float.")

        if self.version not in SUPPORTED_PMX_VERSIONS:
            raise ValueError(
                f"Unsupported PMX version {self.version!r}; expected 2.0 or 2.1."
            )

        if self.encoding not in VALID_PMX_TEXT_ENCODINGS:
            raise ValueError(
                f"Unsupported PMX text encoding {self.encoding!r}; "
                "expected 'utf-16-le' or 'utf-8'."
            )

        if not _is_plain_int(self.additional_uv_count):
            raise TypeError("additional_uv_count must be an integer.")

        if not (
            MIN_PMX_ADDITIONAL_UV_COUNT
            <= self.additional_uv_count
            <= MAX_PMX_ADDITIONAL_UV_COUNT
        ):
            raise ValueError(
                "additional_uv_count must be between 0 and 4; "
                f"got {self.additional_uv_count}."
            )

        if not isinstance(self.index_sizes, PmxIndexSizes):
            raise TypeError("index_sizes must be a PmxIndexSizes instance.")

        if not isinstance(self.extra_global_data, bytes):
            raise TypeError("extra_global_data must be immutable bytes.")

        if self.global_count > MAX_PMX_GLOBAL_COUNT:
            raise ValueError(
                f"PMX global count {self.global_count} exceeds the supported "
                f"maximum of {MAX_PMX_GLOBAL_COUNT}."
            )

    @property
    def encoding_flag(self) -> int:
        """Return the PMX global encoding flag used on disk."""

        return 0 if self.encoding == "utf-16-le" else 1

    @property
    def global_count(self) -> int:
        """Return the complete PMX global-setting byte count."""

        return MIN_PMX_GLOBAL_COUNT + len(self.extra_global_data)


@dataclass(frozen=True, slots=True)
class PmxModelInfo:
    """The four PMX model-information text fields without normalization."""

    local_name: str
    universal_name: str
    local_comments: str
    universal_comments: str

    def __post_init__(self) -> None:
        for field_name in (
            "local_name",
            "universal_name",
            "local_comments",
            "universal_comments",
        ):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"{field_name} must be a string.")

    def to_dict(self) -> dict[str, str]:
        """Return the stable legacy-compatible JSON representation."""

        return {
            "local_name": self.local_name,
            "universal_name": self.universal_name,
            "local_comments": self.local_comments,
            "universal_comments": self.universal_comments,
        }


PmxVector2: TypeAlias = tuple[float, float]
PmxVector3: TypeAlias = tuple[float, float, float]
PmxVector4: TypeAlias = tuple[float, float, float, float]
PmxSphereMode: TypeAlias = Literal[0, 1, 2, 3]
PmxToonReferenceMode: TypeAlias = Literal["texture", "shared"]


def _validate_float(value: object, field_name: str) -> None:
    """Require one explicit float without imposing semantic bounds."""

    if not isinstance(value, float):
        raise TypeError(f"{field_name} must be a float.")


def _validate_integer(value: object, field_name: str) -> None:
    """Require one explicit integer without accepting booleans."""

    if not _is_plain_int(value):
        raise TypeError(f"{field_name} must be an integer.")


def _validate_float_tuple(
    value: object,
    *,
    field_name: str,
    length: int,
) -> None:
    """Require one immutable fixed-length tuple of explicit floats."""

    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be a tuple.")

    if len(value) != length:
        raise ValueError(f"{field_name} must contain exactly {length} values.")

    for item in value:
        _validate_float(item, f"{field_name} value")


def _validate_integer_tuple(
    value: object,
    *,
    field_name: str,
    length: int,
) -> None:
    """Require one immutable fixed-length tuple of explicit integers."""

    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be a tuple.")

    if len(value) != length:
        raise ValueError(f"{field_name} must contain exactly {length} values.")

    for item in value:
        _validate_integer(item, f"{field_name} value")


@dataclass(frozen=True, slots=True)
class PmxBdef1:
    """One-bone PMX vertex deformation."""

    deform_type: ClassVar[Literal[0]] = 0
    bone_index: int

    def __post_init__(self) -> None:
        _validate_integer(self.bone_index, "bone_index")


@dataclass(frozen=True, slots=True)
class PmxBdef2:
    """Two-bone PMX vertex deformation."""

    deform_type: ClassVar[Literal[1]] = 1
    bone_indices: tuple[int, int]
    bone_1_weight: float

    def __post_init__(self) -> None:
        _validate_integer_tuple(
            self.bone_indices,
            field_name="bone_indices",
            length=2,
        )
        _validate_float(self.bone_1_weight, "bone_1_weight")


@dataclass(frozen=True, slots=True)
class PmxBdef4:
    """Four-bone linear PMX vertex deformation."""

    deform_type: ClassVar[Literal[2]] = 2
    bone_indices: tuple[int, int, int, int]
    weights: PmxVector4

    def __post_init__(self) -> None:
        _validate_integer_tuple(
            self.bone_indices,
            field_name="bone_indices",
            length=4,
        )
        _validate_float_tuple(
            self.weights,
            field_name="weights",
            length=4,
        )


@dataclass(frozen=True, slots=True)
class PmxSdef:
    """Spherical PMX vertex deformation with C, R0, and R1 vectors."""

    deform_type: ClassVar[Literal[3]] = 3
    bone_indices: tuple[int, int]
    bone_1_weight: float
    c: PmxVector3
    r0: PmxVector3
    r1: PmxVector3

    def __post_init__(self) -> None:
        _validate_integer_tuple(
            self.bone_indices,
            field_name="bone_indices",
            length=2,
        )
        _validate_float(self.bone_1_weight, "bone_1_weight")

        for field_name in ("c", "r0", "r1"):
            _validate_float_tuple(
                getattr(self, field_name),
                field_name=field_name,
                length=3,
            )


@dataclass(frozen=True, slots=True)
class PmxQdef:
    """Four-bone dual-quaternion PMX 2.1 vertex deformation."""

    deform_type: ClassVar[Literal[4]] = 4
    bone_indices: tuple[int, int, int, int]
    weights: PmxVector4

    def __post_init__(self) -> None:
        _validate_integer_tuple(
            self.bone_indices,
            field_name="bone_indices",
            length=4,
        )
        _validate_float_tuple(
            self.weights,
            field_name="weights",
            length=4,
        )


PmxDeform: TypeAlias = PmxBdef1 | PmxBdef2 | PmxBdef4 | PmxSdef | PmxQdef


@dataclass(frozen=True, slots=True)
class PmxVertex:
    """One complete PMX vertex record required for serialization."""

    position: PmxVector3
    normal: PmxVector3
    uv: PmxVector2
    additional_uvs: tuple[PmxVector4, ...]
    deform: PmxDeform
    edge_scale: float

    def __post_init__(self) -> None:
        _validate_float_tuple(
            self.position,
            field_name="position",
            length=3,
        )
        _validate_float_tuple(
            self.normal,
            field_name="normal",
            length=3,
        )
        _validate_float_tuple(
            self.uv,
            field_name="uv",
            length=2,
        )

        if not isinstance(self.additional_uvs, tuple):
            raise TypeError("additional_uvs must be a tuple.")

        if len(self.additional_uvs) > MAX_PMX_ADDITIONAL_UV_COUNT:
            raise ValueError("additional_uvs cannot contain more than 4 vectors.")

        for additional_uv in self.additional_uvs:
            _validate_float_tuple(
                additional_uv,
                field_name="additional_uv",
                length=4,
            )

        if not isinstance(
            self.deform,
            (PmxBdef1, PmxBdef2, PmxBdef4, PmxSdef, PmxQdef),
        ):
            raise TypeError("deform must be a supported PMX deform record.")

        _validate_float(self.edge_scale, "edge_scale")


@dataclass(frozen=True, slots=True)
class PmxGeometry:
    """Complete ordered PMX vertex and surface-index sections."""

    vertices: tuple[PmxVertex, ...]
    surface_indices: tuple[int, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.vertices, tuple):
            raise TypeError("vertices must be a tuple.")

        if not all(isinstance(vertex, PmxVertex) for vertex in self.vertices):
            raise TypeError("vertices must contain only PmxVertex records.")

        if not isinstance(self.surface_indices, tuple):
            raise TypeError("surface_indices must be a tuple.")

        for surface_index in self.surface_indices:
            _validate_integer(surface_index, "surface index")

            if surface_index < 0:
                raise ValueError("surface indices cannot be negative.")

        if len(self.surface_indices) % 3 != 0:
            raise ValueError("surface index count must be divisible by 3.")

    @property
    def triangle_count(self) -> int:
        """Return the number of triangles represented by surface indices."""

        return len(self.surface_indices) // 3


@dataclass(frozen=True, slots=True)
class PmxMaterial:
    """One complete PMX material record required for serialization."""

    local_name: str
    universal_name: str
    texture_index: int
    sphere_texture_index: int
    sphere_mode: PmxSphereMode
    toon_reference_mode: PmxToonReferenceMode
    toon_reference_index: int
    memo: str
    surface_index_count: int
    diffuse: PmxVector4 = (1.0, 1.0, 1.0, 1.0)
    specular: PmxVector3 = (0.0, 0.0, 0.0)
    specular_strength: float = 0.0
    ambient: PmxVector3 = (0.5, 0.5, 0.5)
    drawing_flags: int = 0
    edge_color: PmxVector4 = (0.0, 0.0, 0.0, 1.0)
    edge_scale: float = 1.0

    def __post_init__(self) -> None:
        for field_name in ("local_name", "universal_name", "memo"):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"{field_name} must be a string.")

        _validate_float_tuple(
            self.diffuse,
            field_name="diffuse",
            length=4,
        )
        _validate_float_tuple(
            self.specular,
            field_name="specular",
            length=3,
        )
        _validate_float(self.specular_strength, "specular_strength")
        _validate_float_tuple(
            self.ambient,
            field_name="ambient",
            length=3,
        )

        _validate_integer(self.drawing_flags, "drawing_flags")

        if not 0 <= self.drawing_flags <= 0xFF:
            raise ValueError("drawing_flags must fit in one unsigned byte.")

        _validate_float_tuple(
            self.edge_color,
            field_name="edge_color",
            length=4,
        )
        _validate_float(self.edge_scale, "edge_scale")

        for field_name in ("texture_index", "sphere_texture_index"):
            value = getattr(self, field_name)
            _validate_integer(value, field_name)

            if value < -1:
                raise ValueError(f"{field_name} cannot be smaller than -1.")

        _validate_integer(self.sphere_mode, "sphere_mode")

        if self.sphere_mode not in (0, 1, 2, 3):
            raise ValueError("sphere_mode must be a value from 0 through 3.")

        if self.toon_reference_mode not in ("texture", "shared"):
            raise ValueError(
                "toon_reference_mode must be either 'texture' or 'shared'."
            )

        _validate_integer(self.toon_reference_index, "toon_reference_index")

        if self.toon_reference_mode == "texture":
            if self.toon_reference_index < -1:
                raise ValueError("toon texture index cannot be smaller than -1.")
        elif not 0 <= self.toon_reference_index <= 9:
            raise ValueError("shared toon index must be a value from 0 through 9.")

        _validate_integer(self.surface_index_count, "surface_index_count")

        if self.surface_index_count < 0:
            raise ValueError("surface_index_count cannot be negative.")

        if self.surface_index_count % 3 != 0:
            raise ValueError("surface_index_count must be divisible by 3.")

    def to_dict(self) -> dict[str, object]:
        """Return the stable legacy scanner representation."""

        return {
            "local_name": self.local_name,
            "universal_name": self.universal_name,
            "texture_index": self.texture_index,
            "sphere_texture_index": self.sphere_texture_index,
            "sphere_mode": self.sphere_mode,
            "toon_reference_mode": self.toon_reference_mode,
            "toon_reference_index": self.toon_reference_index,
            "memo": self.memo,
            "surface_index_count": self.surface_index_count,
        }
