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

PMX_BONE_FLAG_TAIL_INDEX: Final[int] = 0x0001
PMX_BONE_FLAG_ROTATABLE: Final[int] = 0x0002
PMX_BONE_FLAG_TRANSLATABLE: Final[int] = 0x0004
PMX_BONE_FLAG_VISIBLE: Final[int] = 0x0008
PMX_BONE_FLAG_ENABLED: Final[int] = 0x0010
PMX_BONE_FLAG_IK: Final[int] = 0x0020
PMX_BONE_FLAG_LOCAL_APPEND: Final[int] = 0x0080
PMX_BONE_FLAG_INHERIT_ROTATION: Final[int] = 0x0100
PMX_BONE_FLAG_INHERIT_TRANSLATION: Final[int] = 0x0200
PMX_BONE_FLAG_FIXED_AXIS: Final[int] = 0x0400
PMX_BONE_FLAG_LOCAL_AXES: Final[int] = 0x0800
PMX_BONE_FLAG_AFTER_PHYSICS: Final[int] = 0x1000
PMX_BONE_FLAG_EXTERNAL_PARENT: Final[int] = 0x2000

PMX_BONE_FLAG_DEFINITIONS: Final[tuple[tuple[int, str], ...]] = (
    (PMX_BONE_FLAG_TAIL_INDEX, "tail_index"),
    (PMX_BONE_FLAG_ROTATABLE, "rotatable"),
    (PMX_BONE_FLAG_TRANSLATABLE, "translatable"),
    (PMX_BONE_FLAG_VISIBLE, "visible"),
    (PMX_BONE_FLAG_ENABLED, "enabled"),
    (PMX_BONE_FLAG_IK, "ik"),
    (PMX_BONE_FLAG_LOCAL_APPEND, "local_append"),
    (PMX_BONE_FLAG_INHERIT_ROTATION, "inherit_rotation"),
    (PMX_BONE_FLAG_INHERIT_TRANSLATION, "inherit_translation"),
    (PMX_BONE_FLAG_FIXED_AXIS, "fixed_axis"),
    (PMX_BONE_FLAG_LOCAL_AXES, "local_axes"),
    (PMX_BONE_FLAG_AFTER_PHYSICS, "after_physics"),
    (PMX_BONE_FLAG_EXTERNAL_PARENT, "external_parent"),
)


def _is_plain_int(value: object) -> bool:
    """Return whether value is an integer but not a boolean."""

    return isinstance(value, int) and not isinstance(value, bool)


def decode_pmx_bone_flags(flags: int) -> tuple[str, ...]:
    """Return stable names for recognized bits in one PMX bone flag word."""

    if not _is_plain_int(flags):
        raise TypeError("flags must be an integer.")

    if not 0 <= flags <= 0xFFFF:
        raise ValueError("flags must fit in one unsigned 16-bit integer.")

    return tuple(name for bit, name in PMX_BONE_FLAG_DEFINITIONS if flags & bit)


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


PmxBoneTailMode: TypeAlias = Literal["bone", "offset"]


@dataclass(frozen=True, slots=True)
class PmxIkLink:
    """One complete PMX inverse-kinematics link record."""

    bone_index: int
    angle_limits_enabled: bool
    lower_limit: PmxVector3 | None
    upper_limit: PmxVector3 | None

    def __post_init__(self) -> None:
        _validate_integer(self.bone_index, "bone_index")

        if not isinstance(self.angle_limits_enabled, bool):
            raise TypeError("angle_limits_enabled must be a boolean.")

        if self.angle_limits_enabled:
            if self.lower_limit is None or self.upper_limit is None:
                raise ValueError(
                    "enabled IK angle limits require lower and upper vectors."
                )
        elif self.lower_limit is not None or self.upper_limit is not None:
            raise ValueError(
                "disabled IK angle limits cannot retain lower or upper vectors."
            )

        for field_name in ("lower_limit", "upper_limit"):
            value = getattr(self, field_name)

            if value is not None:
                _validate_float_tuple(
                    value,
                    field_name=field_name,
                    length=3,
                )

    def to_dict(self) -> dict[str, object]:
        """Return the stable legacy scanner representation."""

        return {
            "bone_index": self.bone_index,
            "angle_limits_enabled": self.angle_limits_enabled,
            "lower_limit": (
                list(self.lower_limit) if self.lower_limit is not None else None
            ),
            "upper_limit": (
                list(self.upper_limit) if self.upper_limit is not None else None
            ),
        }


@dataclass(frozen=True, slots=True)
class PmxIk:
    """One complete PMX bone inverse-kinematics definition."""

    target_bone_index: int
    loop_count: int
    angle_limit: float
    links: tuple[PmxIkLink, ...]

    def __post_init__(self) -> None:
        _validate_integer(self.target_bone_index, "target_bone_index")
        _validate_integer(self.loop_count, "loop_count")
        _validate_float(self.angle_limit, "angle_limit")

        if not isinstance(self.links, tuple):
            raise TypeError("links must be a tuple.")

        if not all(isinstance(link, PmxIkLink) for link in self.links):
            raise TypeError("links must contain only PmxIkLink records.")

    def to_dict(self) -> dict[str, object]:
        """Return the stable legacy scanner representation."""

        return {
            "target_bone_index": self.target_bone_index,
            "loop_count": self.loop_count,
            "angle_limit": self.angle_limit,
            "link_count": len(self.links),
            "links": [link.to_dict() for link in self.links],
        }


@dataclass(frozen=True, slots=True)
class PmxBone:
    """One complete PMX bone record including all flag-controlled data."""

    local_name: str
    universal_name: str
    position: PmxVector3
    parent_bone_index: int
    transform_layer: int
    flags: int
    flag_names: tuple[str, ...]
    tail_mode: PmxBoneTailMode
    tail_bone_index: int | None
    tail_offset: PmxVector3 | None
    inherit_parent_bone_index: int | None
    inherit_weight: float | None
    fixed_axis: PmxVector3 | None
    local_axis_x: PmxVector3 | None
    local_axis_z: PmxVector3 | None
    external_parent_key: int | None
    ik: PmxIk | None

    def __post_init__(self) -> None:
        for field_name in ("local_name", "universal_name"):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"{field_name} must be a string.")

        _validate_float_tuple(
            self.position,
            field_name="position",
            length=3,
        )

        for field_name in ("parent_bone_index", "transform_layer", "flags"):
            _validate_integer(getattr(self, field_name), field_name)

        if not 0 <= self.flags <= 0xFFFF:
            raise ValueError("flags must fit in one unsigned 16-bit integer.")

        if not isinstance(self.flag_names, tuple):
            raise TypeError("flag_names must be a tuple.")

        if not all(isinstance(name, str) for name in self.flag_names):
            raise TypeError("flag_names must contain only strings.")

        if self.tail_mode not in ("bone", "offset"):
            raise ValueError("tail_mode must be either 'bone' or 'offset'.")

        for field_name in (
            "tail_bone_index",
            "inherit_parent_bone_index",
            "external_parent_key",
        ):
            value = getattr(self, field_name)

            if value is not None:
                _validate_integer(value, field_name)

        for field_name in (
            "tail_offset",
            "fixed_axis",
            "local_axis_x",
            "local_axis_z",
        ):
            value = getattr(self, field_name)

            if value is not None:
                _validate_float_tuple(
                    value,
                    field_name=field_name,
                    length=3,
                )

        if self.inherit_weight is not None:
            _validate_float(self.inherit_weight, "inherit_weight")

        if self.ik is not None and not isinstance(self.ik, PmxIk):
            raise TypeError("ik must be a PmxIk record or None.")

    def to_dict(self) -> dict[str, object]:
        """Return the stable legacy scanner representation."""

        return {
            "local_name": self.local_name,
            "universal_name": self.universal_name,
            "position": list(self.position),
            "parent_bone_index": self.parent_bone_index,
            "transform_layer": self.transform_layer,
            "flags": self.flags,
            "flag_names": list(self.flag_names),
            "tail_mode": self.tail_mode,
            "tail_bone_index": self.tail_bone_index,
            "tail_offset": (
                list(self.tail_offset) if self.tail_offset is not None else None
            ),
            "inherit_parent_bone_index": self.inherit_parent_bone_index,
            "inherit_weight": self.inherit_weight,
            "fixed_axis": (
                list(self.fixed_axis) if self.fixed_axis is not None else None
            ),
            "local_axis_x": (
                list(self.local_axis_x) if self.local_axis_x is not None else None
            ),
            "local_axis_z": (
                list(self.local_axis_z) if self.local_axis_z is not None else None
            ),
            "external_parent_key": self.external_parent_key,
            "ik": self.ik.to_dict() if self.ik is not None else None,
        }


PmxMorphPanel: TypeAlias = Literal[0, 1, 2, 3, 4]
PmxMorphType: TypeAlias = Literal[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
PmxMaterialMorphOperation: TypeAlias = Literal["multiply", "add"]
PmxDisplayFrameTargetType: TypeAlias = Literal["bone", "morph"]


@dataclass(frozen=True, slots=True)
class PmxGroupMorphOffset:
    """One group-morph reference and influence weight."""

    morph_index: int
    weight: float

    def __post_init__(self) -> None:
        _validate_integer(self.morph_index, "morph_index")
        _validate_float(self.weight, "weight")

    def to_dict(self) -> dict[str, object]:
        """Return the stable legacy scanner representation."""

        return {"morph_index": self.morph_index, "weight": self.weight}


@dataclass(frozen=True, slots=True)
class PmxVertexMorphOffset:
    """One vertex-morph displacement."""

    vertex_index: int
    translation: PmxVector3

    def __post_init__(self) -> None:
        _validate_integer(self.vertex_index, "vertex_index")
        _validate_float_tuple(
            self.translation,
            field_name="translation",
            length=3,
        )

    def to_dict(self) -> dict[str, object]:
        """Return the stable legacy scanner representation."""

        return {
            "vertex_index": self.vertex_index,
            "translation": list(self.translation),
        }


@dataclass(frozen=True, slots=True)
class PmxBoneMorphOffset:
    """One bone-morph translation and quaternion rotation."""

    bone_index: int
    translation: PmxVector3
    rotation: PmxVector4

    def __post_init__(self) -> None:
        _validate_integer(self.bone_index, "bone_index")
        _validate_float_tuple(
            self.translation,
            field_name="translation",
            length=3,
        )
        _validate_float_tuple(
            self.rotation,
            field_name="rotation",
            length=4,
        )

    def to_dict(self) -> dict[str, object]:
        """Return the stable legacy scanner representation."""

        return {
            "bone_index": self.bone_index,
            "translation": list(self.translation),
            "rotation": list(self.rotation),
        }


@dataclass(frozen=True, slots=True)
class PmxUvMorphOffset:
    """One base-UV or additional-UV morph displacement."""

    vertex_index: int
    uv_offset: PmxVector4

    def __post_init__(self) -> None:
        _validate_integer(self.vertex_index, "vertex_index")
        _validate_float_tuple(
            self.uv_offset,
            field_name="uv_offset",
            length=4,
        )

    def to_dict(self) -> dict[str, object]:
        """Return the stable legacy scanner representation."""

        return {
            "vertex_index": self.vertex_index,
            "uv_offset": list(self.uv_offset),
        }


@dataclass(frozen=True, slots=True)
class PmxMaterialMorphOffset:
    """One material-morph operation and its color/scalar values."""

    material_index: int
    operation: PmxMaterialMorphOperation
    diffuse: PmxVector4
    specular: PmxVector3
    specular_strength: float
    ambient: PmxVector3
    edge_color: PmxVector4
    edge_scale: float
    texture_tint: PmxVector4
    sphere_tint: PmxVector4
    toon_tint: PmxVector4

    def __post_init__(self) -> None:
        _validate_integer(self.material_index, "material_index")

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
            _validate_float_tuple(
                getattr(self, field_name),
                field_name=field_name,
                length=length,
            )

        _validate_float(self.specular_strength, "specular_strength")
        _validate_float(self.edge_scale, "edge_scale")

    def to_dict(self) -> dict[str, object]:
        """Return the stable legacy scanner representation."""

        return {
            "material_index": self.material_index,
            "operation": self.operation,
            "diffuse": list(self.diffuse),
            "specular": list(self.specular),
            "specular_strength": self.specular_strength,
            "ambient": list(self.ambient),
            "edge_color": list(self.edge_color),
            "edge_scale": self.edge_scale,
            "texture_tint": list(self.texture_tint),
            "sphere_tint": list(self.sphere_tint),
            "toon_tint": list(self.toon_tint),
        }


@dataclass(frozen=True, slots=True)
class PmxFlipMorphOffset:
    """One PMX 2.1 flip-morph reference and influence weight."""

    morph_index: int
    weight: float

    def __post_init__(self) -> None:
        _validate_integer(self.morph_index, "morph_index")
        _validate_float(self.weight, "weight")

    def to_dict(self) -> dict[str, object]:
        """Return the stable legacy scanner representation."""

        return {"morph_index": self.morph_index, "weight": self.weight}


@dataclass(frozen=True, slots=True)
class PmxImpulseMorphOffset:
    """One PMX 2.1 rigid-body impulse morph record."""

    rigid_body_index: int
    local: bool
    velocity: PmxVector3
    angular_torque: PmxVector3

    def __post_init__(self) -> None:
        _validate_integer(self.rigid_body_index, "rigid_body_index")

        if not isinstance(self.local, bool):
            raise TypeError("local must be a boolean.")

        _validate_float_tuple(
            self.velocity,
            field_name="velocity",
            length=3,
        )
        _validate_float_tuple(
            self.angular_torque,
            field_name="angular_torque",
            length=3,
        )

    def to_dict(self) -> dict[str, object]:
        """Return the stable legacy scanner representation."""

        return {
            "rigid_body_index": self.rigid_body_index,
            "local": self.local,
            "velocity": list(self.velocity),
            "angular_torque": list(self.angular_torque),
        }


PmxMorphOffset: TypeAlias = (
    PmxGroupMorphOffset
    | PmxVertexMorphOffset
    | PmxBoneMorphOffset
    | PmxUvMorphOffset
    | PmxMaterialMorphOffset
    | PmxFlipMorphOffset
    | PmxImpulseMorphOffset
)


@dataclass(frozen=True, slots=True)
class PmxMorph:
    """One complete PMX morph record with ordered typed offsets."""

    local_name: str
    universal_name: str
    panel: PmxMorphPanel
    panel_name: str
    morph_type: PmxMorphType
    morph_type_name: str
    offsets: tuple[PmxMorphOffset, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "local_name",
            "universal_name",
            "panel_name",
            "morph_type_name",
        ):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"{field_name} must be a string.")

        _validate_integer(self.panel, "panel")
        if self.panel not in (0, 1, 2, 3, 4):
            raise ValueError("panel must be a value from 0 through 4.")

        _validate_integer(self.morph_type, "morph_type")
        if self.morph_type not in tuple(range(11)):
            raise ValueError("morph_type must be a value from 0 through 10.")

        if not isinstance(self.offsets, tuple):
            raise TypeError("offsets must be a tuple.")

        supported_offset_types = (
            PmxGroupMorphOffset,
            PmxVertexMorphOffset,
            PmxBoneMorphOffset,
            PmxUvMorphOffset,
            PmxMaterialMorphOffset,
            PmxFlipMorphOffset,
            PmxImpulseMorphOffset,
        )
        if not all(isinstance(offset, supported_offset_types) for offset in self.offsets):
            raise TypeError("offsets must contain only supported PMX morph offsets.")

    def to_dict(self) -> dict[str, object]:
        """Return the stable legacy scanner representation."""

        return {
            "local_name": self.local_name,
            "universal_name": self.universal_name,
            "panel": self.panel,
            "panel_name": self.panel_name,
            "morph_type": self.morph_type,
            "morph_type_name": self.morph_type_name,
            "offset_count": len(self.offsets),
            "offsets": [offset.to_dict() for offset in self.offsets],
        }


@dataclass(frozen=True, slots=True)
class PmxDisplayFrameElement:
    """One bone or morph reference inside a PMX display frame."""

    target_type: PmxDisplayFrameTargetType
    target_index: int

    def __post_init__(self) -> None:
        if self.target_type not in ("bone", "morph"):
            raise ValueError("target_type must be either 'bone' or 'morph'.")

        _validate_integer(self.target_index, "target_index")

    def to_dict(self) -> dict[str, object]:
        """Return the stable legacy scanner representation."""

        return {
            "target_type": self.target_type,
            "target_index": self.target_index,
        }


@dataclass(frozen=True, slots=True)
class PmxDisplayFrame:
    """One complete PMX display frame with ordered references."""

    local_name: str
    universal_name: str
    special: bool
    elements: tuple[PmxDisplayFrameElement, ...]

    def __post_init__(self) -> None:
        for field_name in ("local_name", "universal_name"):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"{field_name} must be a string.")

        if not isinstance(self.special, bool):
            raise TypeError("special must be a boolean.")

        if not isinstance(self.elements, tuple):
            raise TypeError("elements must be a tuple.")

        if not all(
            isinstance(element, PmxDisplayFrameElement)
            for element in self.elements
        ):
            raise TypeError(
                "elements must contain only PmxDisplayFrameElement records."
            )

    def to_dict(self) -> dict[str, object]:
        """Return the stable legacy scanner representation."""

        return {
            "local_name": self.local_name,
            "universal_name": self.universal_name,
            "special": self.special,
            "element_count": len(self.elements),
            "elements": [element.to_dict() for element in self.elements],
        }


PmxRigidBodyShape: TypeAlias = Literal[0, 1, 2]
PmxRigidBodyPhysicsMode: TypeAlias = Literal[0, 1, 2]
PmxJointType: TypeAlias = Literal[0, 1, 2, 3, 4, 5]
PmxSoftBodyShape: TypeAlias = Literal[0, 1]
PmxSoftBodyAerodynamicsModel: TypeAlias = Literal[0, 1, 2, 3, 4]


@dataclass(frozen=True, slots=True)
class PmxRigidBody:
    """One complete PMX rigid-body record."""

    local_name: str
    universal_name: str
    bone_index: int
    collision_group: int
    collision_mask: int
    shape: PmxRigidBodyShape
    shape_name: str
    size: PmxVector3
    position: PmxVector3
    rotation: PmxVector3
    mass: float
    linear_damping: float
    angular_damping: float
    restitution: float
    friction: float
    physics_mode: PmxRigidBodyPhysicsMode
    physics_mode_name: str

    def __post_init__(self) -> None:
        for field_name in (
            "local_name",
            "universal_name",
            "shape_name",
            "physics_mode_name",
        ):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"{field_name} must be a string.")

        for field_name in (
            "bone_index",
            "collision_group",
            "collision_mask",
            "shape",
            "physics_mode",
        ):
            _validate_integer(getattr(self, field_name), field_name)

        if not 0 <= self.collision_group <= 15:
            raise ValueError("collision_group must be a value from 0 through 15.")
        if not 0 <= self.collision_mask <= 0xFFFF:
            raise ValueError("collision_mask must fit in one unsigned 16-bit integer.")
        if self.shape not in (0, 1, 2):
            raise ValueError("shape must be a value from 0 through 2.")
        if self.physics_mode not in (0, 1, 2):
            raise ValueError("physics_mode must be a value from 0 through 2.")

        for field_name in ("size", "position", "rotation"):
            _validate_float_tuple(
                getattr(self, field_name),
                field_name=field_name,
                length=3,
            )

        for field_name in (
            "mass",
            "linear_damping",
            "angular_damping",
            "restitution",
            "friction",
        ):
            _validate_float(getattr(self, field_name), field_name)

    def to_dict(self) -> dict[str, object]:
        """Return the stable legacy scanner representation."""

        return {
            "local_name": self.local_name,
            "universal_name": self.universal_name,
            "bone_index": self.bone_index,
            "collision_group": self.collision_group,
            "collision_mask": self.collision_mask,
            "shape": self.shape,
            "shape_name": self.shape_name,
            "size": list(self.size),
            "position": list(self.position),
            "rotation": list(self.rotation),
            "mass": self.mass,
            "linear_damping": self.linear_damping,
            "angular_damping": self.angular_damping,
            "restitution": self.restitution,
            "friction": self.friction,
            "physics_mode": self.physics_mode,
            "physics_mode_name": self.physics_mode_name,
        }


@dataclass(frozen=True, slots=True)
class PmxJoint:
    """One complete PMX joint record."""

    local_name: str
    universal_name: str
    joint_type: PmxJointType
    joint_type_name: str
    rigid_body_a_index: int
    rigid_body_b_index: int
    position: PmxVector3
    rotation: PmxVector3
    translation_limit_minimum: PmxVector3
    translation_limit_maximum: PmxVector3
    rotation_limit_minimum: PmxVector3
    rotation_limit_maximum: PmxVector3
    translation_spring: PmxVector3
    rotation_spring: PmxVector3

    def __post_init__(self) -> None:
        for field_name in ("local_name", "universal_name", "joint_type_name"):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"{field_name} must be a string.")

        for field_name in (
            "joint_type",
            "rigid_body_a_index",
            "rigid_body_b_index",
        ):
            _validate_integer(getattr(self, field_name), field_name)

        if self.joint_type not in (0, 1, 2, 3, 4, 5):
            raise ValueError("joint_type must be a value from 0 through 5.")

        for field_name in (
            "position",
            "rotation",
            "translation_limit_minimum",
            "translation_limit_maximum",
            "rotation_limit_minimum",
            "rotation_limit_maximum",
            "translation_spring",
            "rotation_spring",
        ):
            _validate_float_tuple(
                getattr(self, field_name),
                field_name=field_name,
                length=3,
            )

    def to_dict(self) -> dict[str, object]:
        """Return the stable legacy scanner representation."""

        return {
            "local_name": self.local_name,
            "universal_name": self.universal_name,
            "joint_type": self.joint_type,
            "joint_type_name": self.joint_type_name,
            "rigid_body_a_index": self.rigid_body_a_index,
            "rigid_body_b_index": self.rigid_body_b_index,
            "position": list(self.position),
            "rotation": list(self.rotation),
            "translation_limit_minimum": list(self.translation_limit_minimum),
            "translation_limit_maximum": list(self.translation_limit_maximum),
            "rotation_limit_minimum": list(self.rotation_limit_minimum),
            "rotation_limit_maximum": list(self.rotation_limit_maximum),
            "translation_spring": list(self.translation_spring),
            "rotation_spring": list(self.rotation_spring),
        }


@dataclass(frozen=True, slots=True)
class PmxSoftBodyAnchor:
    """One PMX 2.1 soft-body anchor reference."""

    rigid_body_index: int
    vertex_index: int
    near_mode: bool

    def __post_init__(self) -> None:
        _validate_integer(self.rigid_body_index, "rigid_body_index")
        _validate_integer(self.vertex_index, "vertex_index")
        if not isinstance(self.near_mode, bool):
            raise TypeError("near_mode must be a boolean.")

    def to_dict(self) -> dict[str, object]:
        """Return the stable legacy scanner representation."""

        return {
            "rigid_body_index": self.rigid_body_index,
            "vertex_index": self.vertex_index,
            "near_mode": self.near_mode,
        }


@dataclass(frozen=True, slots=True)
class PmxSoftBodyConfig:
    """Bullet soft-body configuration values stored by PMX 2.1."""

    aerodynamics_model: PmxSoftBodyAerodynamicsModel
    aerodynamics_model_name: str
    velocity_correction_factor: float
    damping_coefficient: float
    drag_coefficient: float
    lift_coefficient: float
    pressure_coefficient: float
    volume_conservation_coefficient: float
    dynamic_friction_coefficient: float
    pose_matching_coefficient: float
    rigid_contact_hardness: float
    kinetic_contact_hardness: float
    soft_contact_hardness: float
    anchor_hardness: float

    def __post_init__(self) -> None:
        _validate_integer(self.aerodynamics_model, "aerodynamics_model")
        if self.aerodynamics_model not in (0, 1, 2, 3, 4):
            raise ValueError("aerodynamics_model must be a value from 0 through 4.")
        if not isinstance(self.aerodynamics_model_name, str):
            raise TypeError("aerodynamics_model_name must be a string.")

        for field_name in (
            "velocity_correction_factor",
            "damping_coefficient",
            "drag_coefficient",
            "lift_coefficient",
            "pressure_coefficient",
            "volume_conservation_coefficient",
            "dynamic_friction_coefficient",
            "pose_matching_coefficient",
            "rigid_contact_hardness",
            "kinetic_contact_hardness",
            "soft_contact_hardness",
            "anchor_hardness",
        ):
            _validate_float(getattr(self, field_name), field_name)

    def to_dict(self) -> dict[str, object]:
        """Return the stable legacy scanner representation."""

        return {
            "aerodynamics_model": self.aerodynamics_model,
            "aerodynamics_model_name": self.aerodynamics_model_name,
            "velocity_correction_factor": self.velocity_correction_factor,
            "damping_coefficient": self.damping_coefficient,
            "drag_coefficient": self.drag_coefficient,
            "lift_coefficient": self.lift_coefficient,
            "pressure_coefficient": self.pressure_coefficient,
            "volume_conservation_coefficient": (
                self.volume_conservation_coefficient
            ),
            "dynamic_friction_coefficient": self.dynamic_friction_coefficient,
            "pose_matching_coefficient": self.pose_matching_coefficient,
            "rigid_contact_hardness": self.rigid_contact_hardness,
            "kinetic_contact_hardness": self.kinetic_contact_hardness,
            "soft_contact_hardness": self.soft_contact_hardness,
            "anchor_hardness": self.anchor_hardness,
        }


@dataclass(frozen=True, slots=True)
class PmxSoftBodyClusterConfig:
    """PMX 2.1 soft-body cluster hardness and split values."""

    soft_rigid_hardness: float
    soft_kinetic_hardness: float
    soft_soft_hardness: float
    soft_rigid_impulse_split: float
    soft_kinetic_impulse_split: float
    soft_soft_impulse_split: float

    def __post_init__(self) -> None:
        for field_name in (
            "soft_rigid_hardness",
            "soft_kinetic_hardness",
            "soft_soft_hardness",
            "soft_rigid_impulse_split",
            "soft_kinetic_impulse_split",
            "soft_soft_impulse_split",
        ):
            _validate_float(getattr(self, field_name), field_name)

    def to_dict(self) -> dict[str, float]:
        """Return the stable legacy scanner representation."""

        return {
            "soft_rigid_hardness": self.soft_rigid_hardness,
            "soft_kinetic_hardness": self.soft_kinetic_hardness,
            "soft_soft_hardness": self.soft_soft_hardness,
            "soft_rigid_impulse_split": self.soft_rigid_impulse_split,
            "soft_kinetic_impulse_split": self.soft_kinetic_impulse_split,
            "soft_soft_impulse_split": self.soft_soft_impulse_split,
        }


@dataclass(frozen=True, slots=True)
class PmxSoftBodyIterationConfig:
    """PMX 2.1 soft-body solver iteration counts."""

    velocity: int
    position: int
    drift: int
    cluster: int

    def __post_init__(self) -> None:
        for field_name in ("velocity", "position", "drift", "cluster"):
            _validate_integer(getattr(self, field_name), field_name)

    def to_dict(self) -> dict[str, int]:
        """Return the stable legacy scanner representation."""

        return {
            "velocity": self.velocity,
            "position": self.position,
            "drift": self.drift,
            "cluster": self.cluster,
        }


@dataclass(frozen=True, slots=True)
class PmxSoftBodyMaterialConfig:
    """PMX 2.1 soft-body material stiffness coefficients."""

    linear_stiffness: float
    area_angular_stiffness: float
    volume_stiffness: float

    def __post_init__(self) -> None:
        for field_name in (
            "linear_stiffness",
            "area_angular_stiffness",
            "volume_stiffness",
        ):
            _validate_float(getattr(self, field_name), field_name)

    def to_dict(self) -> dict[str, float]:
        """Return the stable legacy scanner representation."""

        return {
            "linear_stiffness": self.linear_stiffness,
            "area_angular_stiffness": self.area_angular_stiffness,
            "volume_stiffness": self.volume_stiffness,
        }


@dataclass(frozen=True, slots=True)
class PmxSoftBody:
    """One complete PMX 2.1 soft-body record."""

    local_name: str
    universal_name: str
    shape: PmxSoftBodyShape
    shape_name: str
    material_index: int
    collision_group: int
    collision_mask: int
    flags: int
    flag_names: tuple[str, ...]
    bending_link_distance: int
    cluster_count: int
    total_mass: float
    collision_margin: float
    config: PmxSoftBodyConfig
    cluster_config: PmxSoftBodyClusterConfig
    iteration_config: PmxSoftBodyIterationConfig
    material_config: PmxSoftBodyMaterialConfig
    anchors: tuple[PmxSoftBodyAnchor, ...]
    pinned_vertex_indices: tuple[int, ...]

    def __post_init__(self) -> None:
        for field_name in ("local_name", "universal_name", "shape_name"):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"{field_name} must be a string.")

        for field_name in (
            "shape",
            "material_index",
            "collision_group",
            "collision_mask",
            "flags",
            "bending_link_distance",
            "cluster_count",
        ):
            _validate_integer(getattr(self, field_name), field_name)

        if self.shape not in (0, 1):
            raise ValueError("shape must be 0 or 1.")
        if not 0 <= self.collision_group <= 15:
            raise ValueError("collision_group must be a value from 0 through 15.")
        if not 0 <= self.collision_mask <= 0xFFFF:
            raise ValueError("collision_mask must fit in one unsigned 16-bit integer.")
        if not 0 <= self.flags <= 0xFF:
            raise ValueError("flags must fit in one unsigned byte.")

        if not isinstance(self.flag_names, tuple):
            raise TypeError("flag_names must be a tuple.")
        if not all(isinstance(name, str) for name in self.flag_names):
            raise TypeError("flag_names must contain only strings.")

        _validate_float(self.total_mass, "total_mass")
        _validate_float(self.collision_margin, "collision_margin")

        nested_types = (
            ("config", PmxSoftBodyConfig),
            ("cluster_config", PmxSoftBodyClusterConfig),
            ("iteration_config", PmxSoftBodyIterationConfig),
            ("material_config", PmxSoftBodyMaterialConfig),
        )
        for field_name, expected_type in nested_types:
            if not isinstance(getattr(self, field_name), expected_type):
                raise TypeError(
                    f"{field_name} must be a {expected_type.__name__} record."
                )

        if not isinstance(self.anchors, tuple):
            raise TypeError("anchors must be a tuple.")
        if not all(isinstance(anchor, PmxSoftBodyAnchor) for anchor in self.anchors):
            raise TypeError("anchors must contain only PmxSoftBodyAnchor records.")

        if not isinstance(self.pinned_vertex_indices, tuple):
            raise TypeError("pinned_vertex_indices must be a tuple.")
        for vertex_index in self.pinned_vertex_indices:
            _validate_integer(vertex_index, "pinned vertex index")

    def to_dict(self) -> dict[str, object]:
        """Return the stable legacy scanner representation."""

        return {
            "local_name": self.local_name,
            "universal_name": self.universal_name,
            "shape": self.shape,
            "shape_name": self.shape_name,
            "material_index": self.material_index,
            "collision_group": self.collision_group,
            "collision_mask": self.collision_mask,
            "flags": self.flags,
            "flag_names": list(self.flag_names),
            "bending_link_distance": self.bending_link_distance,
            "cluster_count": self.cluster_count,
            "total_mass": self.total_mass,
            "collision_margin": self.collision_margin,
            "config": self.config.to_dict(),
            "cluster_config": self.cluster_config.to_dict(),
            "iteration_config": self.iteration_config.to_dict(),
            "material_config": self.material_config.to_dict(),
            "anchor_count": len(self.anchors),
            "anchors": [anchor.to_dict() for anchor in self.anchors],
            "pinned_vertex_count": len(self.pinned_vertex_indices),
            "pinned_vertex_indices": list(self.pinned_vertex_indices),
        }


@dataclass(frozen=True, slots=True)
class PmxDocument:
    """One complete immutable PMX document ready for validation or writing."""

    header: PmxHeader
    model_info: PmxModelInfo
    geometry: PmxGeometry
    texture_paths: tuple[str, ...]
    materials: tuple[PmxMaterial, ...]
    bones: tuple[PmxBone, ...]
    morphs: tuple[PmxMorph, ...]
    display_frames: tuple[PmxDisplayFrame, ...]
    rigid_bodies: tuple[PmxRigidBody, ...]
    joints: tuple[PmxJoint, ...]
    soft_bodies: tuple[PmxSoftBody, ...]
    trailing_data: bytes = b""

    def __post_init__(self) -> None:
        if not isinstance(self.header, PmxHeader):
            raise TypeError("header must be a PmxHeader instance.")
        if not isinstance(self.model_info, PmxModelInfo):
            raise TypeError("model_info must be a PmxModelInfo instance.")
        if not isinstance(self.geometry, PmxGeometry):
            raise TypeError("geometry must be a PmxGeometry instance.")

        tuple_fields = (
            ("texture_paths", str),
            ("materials", PmxMaterial),
            ("bones", PmxBone),
            ("morphs", PmxMorph),
            ("display_frames", PmxDisplayFrame),
            ("rigid_bodies", PmxRigidBody),
            ("joints", PmxJoint),
            ("soft_bodies", PmxSoftBody),
        )
        for field_name, expected_type in tuple_fields:
            value = getattr(self, field_name)
            if not isinstance(value, tuple):
                raise TypeError(f"{field_name} must be a tuple.")
            if not all(isinstance(item, expected_type) for item in value):
                raise TypeError(
                    f"{field_name} must contain only "
                    f"{expected_type.__name__} values."
                )

        if not isinstance(self.trailing_data, bytes):
            raise TypeError("trailing_data must be immutable bytes.")

    @property
    def vertices(self) -> tuple[PmxVertex, ...]:
        """Return the ordered PMX vertex records."""

        return self.geometry.vertices

    @property
    def surface_indices(self) -> tuple[int, ...]:
        """Return the ordered PMX triangle indices."""

        return self.geometry.surface_indices
