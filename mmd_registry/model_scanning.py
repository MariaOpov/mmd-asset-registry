"""Safe structural metadata scanning for PMX and PMD model files."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Literal

from mmd_registry.binary_reader import (
    BinaryParseError,
    BinaryReader,
)
from mmd_registry.pmx.document import (
    PMX_BONE_FLAG_AFTER_PHYSICS,
    PMX_BONE_FLAG_ENABLED,
    PMX_BONE_FLAG_EXTERNAL_PARENT,
    PMX_BONE_FLAG_FIXED_AXIS,
    PMX_BONE_FLAG_IK,
    PMX_BONE_FLAG_INHERIT_ROTATION,
    PMX_BONE_FLAG_INHERIT_TRANSLATION,
    PMX_BONE_FLAG_LOCAL_APPEND,
    PMX_BONE_FLAG_LOCAL_AXES,
    PMX_BONE_FLAG_ROTATABLE,
    PMX_BONE_FLAG_TAIL_INDEX,
    PMX_BONE_FLAG_TRANSLATABLE,
    PMX_BONE_FLAG_VISIBLE,
    PmxBone,
    PmxHeader,
    PmxIk,
    PmxIkLink,
    PmxIndexSizes,
    PmxMaterial,
    PmxModelInfo,
)
from mmd_registry.pmx.errors import raise_pmx_error as _raise_pmx_error
from mmd_registry.pmx.sections.bones import (
    MAX_PMX_BONE_COUNT,
    MAX_PMX_IK_LINK_COUNT,
    MAX_PMX_IK_LOOP_COUNT,
    MAX_PMX_TOTAL_IK_LINK_COUNT,
    PmxBoneReadState,
    read_pmx_bones,
    validate_pmx_bone_index as _validate_pmx_bone_index,
)
from mmd_registry.pmx.sections.geometry import (
    MAX_PMX_SURFACE_INDEX_COUNT,
    PmxGeometryReadState,
    read_pmx_geometry,
)
from mmd_registry.pmx.sections.header import (
    MAX_PMX_NAME_BYTES,
    PmxHeaderReadState,
    read_pmx_header_body,
    read_pmx_magic,
    validate_pmx_magic,
)
from mmd_registry.pmx.sections.materials import (
    MAX_PMX_MATERIAL_COUNT,
    PmxMaterialReadState,
    read_pmx_materials,
)
from mmd_registry.pmx.sections.textures import (
    MAX_PMX_TEXTURE_COUNT,
    PmxTextureReadState,
    read_pmx_textures,
)


MAX_PMX_MORPH_COUNT: Final[int] = 200_000
MAX_PMX_MORPH_OFFSET_COUNT: Final[int] = 2_000_000
MAX_PMX_TOTAL_MORPH_OFFSET_COUNT: Final[int] = 5_000_000
MAX_PMX_DISPLAY_FRAME_COUNT: Final[int] = 100_000
MAX_PMX_DISPLAY_FRAME_ELEMENT_COUNT: Final[int] = 1_000_000
MAX_PMX_TOTAL_DISPLAY_FRAME_ELEMENT_COUNT: Final[int] = 5_000_000
MAX_PMX_RIGID_BODY_COUNT: Final[int] = 200_000
MAX_PMX_JOINT_COUNT: Final[int] = 200_000
MAX_PMX_SOFT_BODY_COUNT: Final[int] = 100_000
MAX_PMX_SOFT_BODY_ANCHOR_COUNT: Final[int] = 500_000
MAX_PMX_TOTAL_SOFT_BODY_ANCHOR_COUNT: Final[int] = 1_000_000
MAX_PMX_SOFT_BODY_PIN_COUNT: Final[int] = 500_000
MAX_PMX_TOTAL_SOFT_BODY_PIN_COUNT: Final[int] = 1_000_000
MAX_PMX_SOFT_BODY_PARAMETER_COUNT: Final[int] = 1_000_000

ScanStatus = Literal["ok", "warning", "error"]


@dataclass(frozen=True, slots=True)
class PmxGroupMorphOffset:
    """One group-morph reference and influence weight."""

    morph_index: int
    weight: float

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "morph_index": self.morph_index,
            "weight": self.weight,
        }


@dataclass(frozen=True, slots=True)
class PmxVertexMorphOffset:
    """One vertex-morph displacement."""

    vertex_index: int
    translation: tuple[float, float, float]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "vertex_index": self.vertex_index,
            "translation": list(self.translation),
        }


@dataclass(frozen=True, slots=True)
class PmxBoneMorphOffset:
    """One bone-morph translation and quaternion rotation."""

    bone_index: int
    translation: tuple[float, float, float]
    rotation: tuple[float, float, float, float]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "bone_index": self.bone_index,
            "translation": list(self.translation),
            "rotation": list(self.rotation),
        }


@dataclass(frozen=True, slots=True)
class PmxUvMorphOffset:
    """One base-UV or additional-UV morph displacement."""

    vertex_index: int
    uv_offset: tuple[float, float, float, float]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "vertex_index": self.vertex_index,
            "uv_offset": list(self.uv_offset),
        }


@dataclass(frozen=True, slots=True)
class PmxMaterialMorphOffset:
    """One material-morph operation and its color/scalar values."""

    material_index: int
    operation: Literal["multiply", "add"]
    diffuse: tuple[float, float, float, float]
    specular: tuple[float, float, float]
    specular_strength: float
    ambient: tuple[float, float, float]
    edge_color: tuple[float, float, float, float]
    edge_scale: float
    texture_tint: tuple[float, float, float, float]
    sphere_tint: tuple[float, float, float, float]
    toon_tint: tuple[float, float, float, float]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

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

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "morph_index": self.morph_index,
            "weight": self.weight,
        }


@dataclass(frozen=True, slots=True)
class PmxImpulseMorphOffset:
    """One PMX 2.1 rigid-body impulse morph record."""

    rigid_body_index: int
    local: bool
    velocity: tuple[float, float, float]
    angular_torque: tuple[float, float, float]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "rigid_body_index": self.rigid_body_index,
            "local": self.local,
            "velocity": list(self.velocity),
            "angular_torque": list(self.angular_torque),
        }


PmxMorphOffset = (
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
    """Structural metadata extracted from one PMX morph record."""

    local_name: str
    universal_name: str
    panel: int
    panel_name: str
    morph_type: int
    morph_type_name: str
    offsets: tuple[PmxMorphOffset, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

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

    target_type: Literal["bone", "morph"]
    target_index: int

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "target_type": self.target_type,
            "target_index": self.target_index,
        }


@dataclass(frozen=True, slots=True)
class PmxDisplayFrame:
    """Structural metadata extracted from one PMX display frame."""

    local_name: str
    universal_name: str
    special: bool
    elements: tuple[PmxDisplayFrameElement, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "local_name": self.local_name,
            "universal_name": self.universal_name,
            "special": self.special,
            "element_count": len(self.elements),
            "elements": [element.to_dict() for element in self.elements],
        }


@dataclass(frozen=True, slots=True)
class PmxRigidBody:
    """Structural metadata extracted from one PMX rigid body."""

    local_name: str
    universal_name: str
    bone_index: int
    collision_group: int
    collision_mask: int
    shape: int
    shape_name: str
    size: tuple[float, float, float]
    position: tuple[float, float, float]
    rotation: tuple[float, float, float]
    mass: float
    linear_damping: float
    angular_damping: float
    restitution: float
    friction: float
    physics_mode: int
    physics_mode_name: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

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
    """Structural metadata extracted from one PMX joint."""

    local_name: str
    universal_name: str
    joint_type: int
    joint_type_name: str
    rigid_body_a_index: int
    rigid_body_b_index: int
    position: tuple[float, float, float]
    rotation: tuple[float, float, float]
    translation_limit_minimum: tuple[float, float, float]
    translation_limit_maximum: tuple[float, float, float]
    rotation_limit_minimum: tuple[float, float, float]
    rotation_limit_maximum: tuple[float, float, float]
    translation_spring: tuple[float, float, float]
    rotation_spring: tuple[float, float, float]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

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

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "rigid_body_index": self.rigid_body_index,
            "vertex_index": self.vertex_index,
            "near_mode": self.near_mode,
        }


@dataclass(frozen=True, slots=True)
class PmxSoftBodyConfig:
    """Bullet soft-body configuration values stored by PMX 2.1."""

    aerodynamics_model: int
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

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "aerodynamics_model": self.aerodynamics_model,
            "aerodynamics_model_name": self.aerodynamics_model_name,
            "velocity_correction_factor": (self.velocity_correction_factor),
            "damping_coefficient": self.damping_coefficient,
            "drag_coefficient": self.drag_coefficient,
            "lift_coefficient": self.lift_coefficient,
            "pressure_coefficient": self.pressure_coefficient,
            "volume_conservation_coefficient": (self.volume_conservation_coefficient),
            "dynamic_friction_coefficient": (self.dynamic_friction_coefficient),
            "pose_matching_coefficient": (self.pose_matching_coefficient),
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

    def to_dict(self) -> dict[str, float]:
        """Return a JSON-serializable representation."""

        return {
            "soft_rigid_hardness": self.soft_rigid_hardness,
            "soft_kinetic_hardness": self.soft_kinetic_hardness,
            "soft_soft_hardness": self.soft_soft_hardness,
            "soft_rigid_impulse_split": (self.soft_rigid_impulse_split),
            "soft_kinetic_impulse_split": (self.soft_kinetic_impulse_split),
            "soft_soft_impulse_split": self.soft_soft_impulse_split,
        }


@dataclass(frozen=True, slots=True)
class PmxSoftBodyIterationConfig:
    """PMX 2.1 soft-body solver iteration counts."""

    velocity: int
    position: int
    drift: int
    cluster: int

    def to_dict(self) -> dict[str, int]:
        """Return a JSON-serializable representation."""

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

    def to_dict(self) -> dict[str, float]:
        """Return a JSON-serializable representation."""

        return {
            "linear_stiffness": self.linear_stiffness,
            "area_angular_stiffness": self.area_angular_stiffness,
            "volume_stiffness": self.volume_stiffness,
        }


@dataclass(frozen=True, slots=True)
class PmxSoftBody:
    """Structural metadata extracted from one PMX 2.1 soft body."""

    local_name: str
    universal_name: str
    shape: int
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

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

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
class PmxSectionSummary:
    """Aggregate counts for a completely scanned PMX structure."""

    vertex_count: int
    surface_index_count: int
    triangle_count: int
    texture_count: int
    material_count: int
    bone_count: int
    ik_count: int
    ik_link_count: int
    morph_count: int
    morph_offset_count: int
    display_frame_count: int
    display_frame_element_count: int
    rigid_body_count: int
    joint_count: int
    soft_body_count: int
    soft_body_anchor_count: int
    pinned_vertex_count: int

    def to_dict(self) -> dict[str, int]:
        """Return a JSON-serializable representation."""

        return {
            "vertex_count": self.vertex_count,
            "surface_index_count": self.surface_index_count,
            "triangle_count": self.triangle_count,
            "texture_count": self.texture_count,
            "material_count": self.material_count,
            "bone_count": self.bone_count,
            "ik_count": self.ik_count,
            "ik_link_count": self.ik_link_count,
            "morph_count": self.morph_count,
            "morph_offset_count": self.morph_offset_count,
            "display_frame_count": self.display_frame_count,
            "display_frame_element_count": (self.display_frame_element_count),
            "rigid_body_count": self.rigid_body_count,
            "joint_count": self.joint_count,
            "soft_body_count": self.soft_body_count,
            "soft_body_anchor_count": self.soft_body_anchor_count,
            "pinned_vertex_count": self.pinned_vertex_count,
        }


@dataclass(frozen=True, slots=True)
class PmxDependencySummary:
    """Texture dependency references collected from PMX materials."""

    declared_texture_path_count: int
    material_texture_reference_count: int
    sphere_texture_reference_count: int
    toon_texture_reference_count: int
    total_texture_reference_count: int
    referenced_texture_indices: tuple[int, ...]
    referenced_texture_paths: tuple[str, ...]
    unreferenced_texture_indices: tuple[int, ...]
    unreferenced_texture_paths: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "declared_texture_path_count": (self.declared_texture_path_count),
            "material_texture_reference_count": (self.material_texture_reference_count),
            "sphere_texture_reference_count": (self.sphere_texture_reference_count),
            "toon_texture_reference_count": (self.toon_texture_reference_count),
            "total_texture_reference_count": (self.total_texture_reference_count),
            "referenced_texture_indices": list(self.referenced_texture_indices),
            "referenced_texture_paths": list(self.referenced_texture_paths),
            "unreferenced_texture_indices": list(self.unreferenced_texture_indices),
            "unreferenced_texture_paths": list(self.unreferenced_texture_paths),
        }


@dataclass(slots=True)
class PmxHeaderScanResult:
    """Result of scanning PMX header and structural sections."""

    detected_format: Literal["pmx"] | None = None
    magic: str | None = None
    version: float | None = None
    encoding: str | None = None
    global_count: int | None = None
    additional_uv_count: int | None = None
    index_sizes: PmxIndexSizes | None = None
    model_info: PmxModelInfo | None = None
    vertex_count: int | None = None
    surface_index_count: int | None = None
    triangle_count: int | None = None
    texture_count: int | None = None
    texture_paths: list[str] = field(default_factory=list)
    material_count: int | None = None
    materials: list[PmxMaterial] = field(default_factory=list)
    bone_count: int | None = None
    bones: list[PmxBone] = field(default_factory=list)
    morph_count: int | None = None
    morphs: list[PmxMorph] = field(default_factory=list)
    display_frame_count: int | None = None
    display_frames: list[PmxDisplayFrame] = field(default_factory=list)
    rigid_body_count: int | None = None
    rigid_bodies: list[PmxRigidBody] = field(default_factory=list)
    joint_count: int | None = None
    joints: list[PmxJoint] = field(default_factory=list)
    soft_body_count: int | None = None
    soft_bodies: list[PmxSoftBody] = field(default_factory=list)
    file_size: int | None = None
    bytes_consumed: int = 0
    scan_complete: bool = False
    trailing_byte_count: int | None = None
    section_summary: PmxSectionSummary | None = None
    dependency_summary: PmxDependencySummary | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def status(self) -> ScanStatus:
        """Return the overall scan status."""

        if self.errors:
            return "error"

        if self.warnings:
            return "warning"

        return "ok"

    @property
    def bytes_remaining(self) -> int | None:
        """Return unread bytes, or ``None`` when file size is unavailable."""

        if self.file_size is None:
            return None

        return max(self.file_size - self.bytes_consumed, 0)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "status": self.status,
            "detected_format": self.detected_format,
            "magic": self.magic,
            "version": self.version,
            "encoding": self.encoding,
            "global_count": self.global_count,
            "additional_uv_count": self.additional_uv_count,
            "index_sizes": (
                self.index_sizes.to_dict() if self.index_sizes is not None else None
            ),
            "model_info": (
                self.model_info.to_dict() if self.model_info is not None else None
            ),
            "vertex_count": self.vertex_count,
            "surface_index_count": self.surface_index_count,
            "triangle_count": self.triangle_count,
            "texture_count": self.texture_count,
            "texture_paths": list(self.texture_paths),
            "material_count": self.material_count,
            "materials": [material.to_dict() for material in self.materials],
            "bone_count": self.bone_count,
            "bones": [bone.to_dict() for bone in self.bones],
            "morph_count": self.morph_count,
            "morphs": [morph.to_dict() for morph in self.morphs],
            "display_frame_count": self.display_frame_count,
            "display_frames": [
                display_frame.to_dict() for display_frame in self.display_frames
            ],
            "rigid_body_count": self.rigid_body_count,
            "rigid_bodies": [rigid_body.to_dict() for rigid_body in self.rigid_bodies],
            "joint_count": self.joint_count,
            "joints": [joint.to_dict() for joint in self.joints],
            "soft_body_count": self.soft_body_count,
            "soft_bodies": [soft_body.to_dict() for soft_body in self.soft_bodies],
            "file_size": self.file_size,
            "bytes_consumed": self.bytes_consumed,
            "bytes_remaining": self.bytes_remaining,
            "scan_complete": self.scan_complete,
            "trailing_byte_count": self.trailing_byte_count,
            "section_summary": (
                self.section_summary.to_dict()
                if self.section_summary is not None
                else None
            ),
            "dependency_summary": (
                self.dependency_summary.to_dict()
                if self.dependency_summary is not None
                else None
            ),
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def _scan_pmx_geometry(
    reader: BinaryReader,
    result: PmxHeaderScanResult,
    *,
    header: PmxHeader,
) -> None:
    """Read geometry while preserving the legacy count projection."""

    geometry_state = PmxGeometryReadState()

    try:
        read_pmx_geometry(
            reader,
            header=header,
            state=geometry_state,
        )
    finally:
        result.vertex_count = geometry_state.vertex_count
        result.surface_index_count = geometry_state.surface_index_count
        result.triangle_count = geometry_state.triangle_count


def _scan_pmx_textures(
    reader: BinaryReader,
    result: PmxHeaderScanResult,
    *,
    header: PmxHeader,
) -> None:
    """Read texture paths while preserving the legacy list projection."""

    texture_state = PmxTextureReadState()

    try:
        read_pmx_textures(
            reader,
            header=header,
            state=texture_state,
        )
    finally:
        result.texture_count = texture_state.texture_count
        result.texture_paths = list(texture_state.texture_paths)


def _scan_pmx_materials(
    reader: BinaryReader,
    result: PmxHeaderScanResult,
    *,
    header: PmxHeader,
) -> None:
    """Read materials while preserving the legacy list projection."""

    if result.texture_count is None:
        _raise_pmx_error(
            section="materials",
            offset=reader.offset,
            operation="starting material scan",
            reason="PMX texture count is unavailable.",
        )

    if result.surface_index_count is None:
        _raise_pmx_error(
            section="materials",
            offset=reader.offset,
            operation="starting material scan",
            reason="PMX surface index count is unavailable.",
        )

    material_state = PmxMaterialReadState()

    try:
        read_pmx_materials(
            reader,
            header=header,
            texture_count=result.texture_count,
            surface_index_count=result.surface_index_count,
            state=material_state,
        )
    finally:
        result.material_count = material_state.material_count
        result.materials = list(material_state.materials)


def _read_pmx_int32(
    reader: BinaryReader,
    label: str,
) -> int:
    """Read one little-endian signed 32-bit PMX integer."""

    return int.from_bytes(
        reader.read_exact(4, label),
        byteorder="little",
        signed=True,
    )


def _read_pmx_uint16(
    reader: BinaryReader,
    label: str,
) -> int:
    """Read one little-endian unsigned 16-bit PMX integer."""

    return int.from_bytes(
        reader.read_exact(2, label),
        byteorder="little",
        signed=False,
    )


def _read_pmx_vec3(
    reader: BinaryReader,
    label: str,
) -> tuple[float, float, float]:
    """Read one PMX vec3 as three little-endian floats."""

    return (
        reader.read_float32(f"{label} x"),
        reader.read_float32(f"{label} y"),
        reader.read_float32(f"{label} z"),
    )


def _scan_pmx_bones(
    reader: BinaryReader,
    result: PmxHeaderScanResult,
    *,
    header: PmxHeader,
) -> None:
    """Read bones while preserving the legacy list projection."""

    bone_state = PmxBoneReadState()

    try:
        read_pmx_bones(
            reader,
            header=header,
            state=bone_state,
        )
    finally:
        result.bone_count = bone_state.bone_count
        result.bones = list(bone_state.bones)


def _read_pmx_vec4(
    reader: BinaryReader,
    label: str,
) -> tuple[float, float, float, float]:
    """Read one PMX vec4 as four little-endian floats."""

    return (
        reader.read_float32(f"{label} x"),
        reader.read_float32(f"{label} y"),
        reader.read_float32(f"{label} z"),
        reader.read_float32(f"{label} w"),
    )


def _decode_pmx_morph_panel(
    panel: int,
    *,
    offset: int,
    record_index: int,
) -> str:
    """Validate and decode one PMX morph panel value."""

    panel_names = {
        0: "system",
        1: "eyebrow",
        2: "eye",
        3: "mouth",
        4: "other",
    }

    try:
        return panel_names[panel]
    except KeyError:
        _raise_pmx_error(
            section="morphs",
            record_index=record_index,
            offset=offset,
            operation="validating morph panel",
            reason=(f"invalid panel {panel}; expected a value from 0 through 4."),
        )


def _decode_pmx_morph_type(
    morph_type: int,
    *,
    version: float,
    additional_uv_count: int,
    offset: int,
    record_index: int,
) -> str:
    """Validate and decode one PMX morph type."""

    morph_type_names = {
        0: "group",
        1: "vertex",
        2: "bone",
        3: "uv",
        4: "additional_uv_1",
        5: "additional_uv_2",
        6: "additional_uv_3",
        7: "additional_uv_4",
        8: "material",
        9: "flip",
        10: "impulse",
    }

    if morph_type not in morph_type_names:
        _raise_pmx_error(
            section="morphs",
            record_index=record_index,
            offset=offset,
            operation="validating morph type",
            reason=(
                f"invalid morph type {morph_type}; expected a value from 0 through 10."
            ),
        )

    if morph_type in {9, 10} and version < 2.1:
        _raise_pmx_error(
            section="morphs",
            record_index=record_index,
            offset=offset,
            operation="validating morph type",
            reason=(
                f"morph type {morph_type} "
                f"({morph_type_names[morph_type]}) requires PMX 2.1."
            ),
        )

    if 4 <= morph_type <= 7:
        required_uv_count = morph_type - 3
        if additional_uv_count < required_uv_count:
            _raise_pmx_error(
                section="morphs",
                record_index=record_index,
                offset=offset,
                operation="validating additional UV morph type",
                reason=(
                    f"morph type {morph_type} requires additional UV "
                    f"layer {required_uv_count}, but the model declares "
                    f"{additional_uv_count} additional UV layers."
                ),
            )

    return morph_type_names[morph_type]


def _minimum_pmx_morph_size() -> int:
    """Return the smallest possible PMX morph-record size."""

    text_length_fields = 8
    panel_size = 1
    type_size = 1
    offset_count_size = 4
    return text_length_fields + panel_size + type_size + offset_count_size


def _minimum_pmx_morph_offset_size(
    morph_type: int,
    *,
    index_sizes: PmxIndexSizes,
) -> int:
    """Return the smallest fixed size for one morph offset."""

    if morph_type in {0, 9}:
        return index_sizes.morph + 4

    if morph_type == 1:
        return index_sizes.vertex + 12

    if morph_type == 2:
        return index_sizes.bone + 28

    if 3 <= morph_type <= 7:
        return index_sizes.vertex + 16

    if morph_type == 8:
        return index_sizes.material + 113

    if morph_type == 10:
        return index_sizes.rigid_body + 25

    raise ValueError(f"Unsupported PMX morph type: {morph_type}")


def _validate_pmx_index_range(
    value: int,
    *,
    count: int,
    section: str,
    record_index: int,
    label: str,
    offset: int,
    allow_sentinel: bool,
) -> None:
    """Validate an index for a PMX section whose count is known."""

    minimum_value = -1 if allow_sentinel else 0

    if value < minimum_value or value >= count:
        if count == 0:
            expected = (
                "expected only -1 because no records are declared"
                if allow_sentinel
                else "no valid index exists"
            )
        elif allow_sentinel:
            expected = f"expected -1 or a value from 0 through {count - 1}"
        else:
            expected = f"expected a value from 0 through {count - 1}"

        _raise_pmx_error(
            section=section,
            record_index=record_index,
            offset=offset,
            operation=f"validating {label}",
            reason=(f"index {value} is invalid for record count {count}; {expected}."),
        )


def _read_pmx_group_morph_offset(
    reader: BinaryReader,
    *,
    result: PmxHeaderScanResult,
    morph_count: int,
    section: str,
    offset_index: int,
) -> PmxGroupMorphOffset:
    """Read one PMX group-morph offset."""

    assert result.index_sizes is not None
    reference_offset = reader.offset
    morph_index = reader.read_index(
        result.index_sizes.morph,
        signed=True,
        label="group morph index",
    )
    _validate_pmx_index_range(
        morph_index,
        count=morph_count,
        section=section,
        record_index=offset_index,
        label="group morph index",
        offset=reference_offset,
        allow_sentinel=False,
    )
    weight = reader.read_float32("group morph weight")
    return PmxGroupMorphOffset(
        morph_index=morph_index,
        weight=weight,
    )


def _read_pmx_vertex_morph_offset(
    reader: BinaryReader,
    *,
    result: PmxHeaderScanResult,
    section: str,
    offset_index: int,
) -> PmxVertexMorphOffset:
    """Read one PMX vertex-morph offset."""

    assert result.index_sizes is not None
    assert result.vertex_count is not None
    reference_offset = reader.offset
    vertex_index = reader.read_index(
        result.index_sizes.vertex,
        signed=False,
        label="vertex morph vertex index",
    )
    _validate_pmx_index_range(
        vertex_index,
        count=result.vertex_count,
        section=section,
        record_index=offset_index,
        label="vertex morph vertex index",
        offset=reference_offset,
        allow_sentinel=False,
    )
    translation = _read_pmx_vec3(
        reader,
        "vertex morph translation",
    )
    return PmxVertexMorphOffset(
        vertex_index=vertex_index,
        translation=translation,
    )


def _read_pmx_bone_morph_offset(
    reader: BinaryReader,
    *,
    result: PmxHeaderScanResult,
    section: str,
    offset_index: int,
) -> PmxBoneMorphOffset:
    """Read one PMX bone-morph offset."""

    assert result.index_sizes is not None
    assert result.bone_count is not None
    reference_offset = reader.offset
    bone_index = reader.read_index(
        result.index_sizes.bone,
        signed=True,
        label="bone morph bone index",
    )
    _validate_pmx_index_range(
        bone_index,
        count=result.bone_count,
        section=section,
        record_index=offset_index,
        label="bone morph bone index",
        offset=reference_offset,
        allow_sentinel=False,
    )
    translation = _read_pmx_vec3(
        reader,
        "bone morph translation",
    )
    rotation = _read_pmx_vec4(
        reader,
        "bone morph rotation",
    )
    return PmxBoneMorphOffset(
        bone_index=bone_index,
        translation=translation,
        rotation=rotation,
    )


def _read_pmx_uv_morph_offset(
    reader: BinaryReader,
    *,
    result: PmxHeaderScanResult,
    section: str,
    offset_index: int,
) -> PmxUvMorphOffset:
    """Read one base-UV or additional-UV morph offset."""

    assert result.index_sizes is not None
    assert result.vertex_count is not None
    reference_offset = reader.offset
    vertex_index = reader.read_index(
        result.index_sizes.vertex,
        signed=False,
        label="UV morph vertex index",
    )
    _validate_pmx_index_range(
        vertex_index,
        count=result.vertex_count,
        section=section,
        record_index=offset_index,
        label="UV morph vertex index",
        offset=reference_offset,
        allow_sentinel=False,
    )
    uv_offset = _read_pmx_vec4(
        reader,
        "UV morph offset",
    )
    return PmxUvMorphOffset(
        vertex_index=vertex_index,
        uv_offset=uv_offset,
    )


def _read_pmx_material_morph_offset(
    reader: BinaryReader,
    *,
    result: PmxHeaderScanResult,
    section: str,
    offset_index: int,
) -> PmxMaterialMorphOffset:
    """Read one PMX material-morph offset."""

    assert result.index_sizes is not None
    assert result.material_count is not None
    reference_offset = reader.offset
    material_index = reader.read_index(
        result.index_sizes.material,
        signed=True,
        label="material morph material index",
    )
    _validate_pmx_index_range(
        material_index,
        count=result.material_count,
        section=section,
        record_index=offset_index,
        label="material morph material index",
        offset=reference_offset,
        allow_sentinel=True,
    )

    operation_offset = reader.offset
    operation_value = reader.read_uint8("material morph operation")
    if operation_value == 0:
        operation: Literal["multiply", "add"] = "multiply"
    elif operation_value == 1:
        operation = "add"
    else:
        _raise_pmx_error(
            section=section,
            record_index=offset_index,
            offset=operation_offset,
            operation="validating material morph operation",
            reason=(f"invalid operation {operation_value}; expected 0 or 1."),
        )

    return PmxMaterialMorphOffset(
        material_index=material_index,
        operation=operation,
        diffuse=_read_pmx_vec4(reader, "material morph diffuse"),
        specular=_read_pmx_vec3(reader, "material morph specular"),
        specular_strength=reader.read_float32("material morph specular strength"),
        ambient=_read_pmx_vec3(reader, "material morph ambient"),
        edge_color=_read_pmx_vec4(reader, "material morph edge color"),
        edge_scale=reader.read_float32("material morph edge scale"),
        texture_tint=_read_pmx_vec4(
            reader,
            "material morph texture tint",
        ),
        sphere_tint=_read_pmx_vec4(
            reader,
            "material morph sphere tint",
        ),
        toon_tint=_read_pmx_vec4(
            reader,
            "material morph toon tint",
        ),
    )


def _read_pmx_flip_morph_offset(
    reader: BinaryReader,
    *,
    result: PmxHeaderScanResult,
    morph_count: int,
    section: str,
    offset_index: int,
) -> PmxFlipMorphOffset:
    """Read one PMX 2.1 flip-morph offset."""

    assert result.index_sizes is not None
    reference_offset = reader.offset
    morph_index = reader.read_index(
        result.index_sizes.morph,
        signed=True,
        label="flip morph index",
    )
    _validate_pmx_index_range(
        morph_index,
        count=morph_count,
        section=section,
        record_index=offset_index,
        label="flip morph index",
        offset=reference_offset,
        allow_sentinel=False,
    )
    weight = reader.read_float32("flip morph weight")
    return PmxFlipMorphOffset(
        morph_index=morph_index,
        weight=weight,
    )


def _read_pmx_impulse_morph_offset(
    reader: BinaryReader,
    *,
    result: PmxHeaderScanResult,
    section: str,
    offset_index: int,
) -> PmxImpulseMorphOffset:
    """Read one PMX 2.1 impulse-morph offset.

    The rigid-body section appears later in a PMX file, so its upper
    index bound is validated when rigid-body scanning is implemented.
    Negative indices are invalid and rejected here.
    """

    assert result.index_sizes is not None
    reference_offset = reader.offset
    rigid_body_index = reader.read_index(
        result.index_sizes.rigid_body,
        signed=True,
        label="impulse morph rigid-body index",
    )
    if rigid_body_index < 0:
        _raise_pmx_error(
            section=section,
            record_index=offset_index,
            offset=reference_offset,
            operation="validating impulse morph rigid-body index",
            reason=(f"index {rigid_body_index} cannot be negative."),
        )

    local_flag_offset = reader.offset
    local_flag = reader.read_uint8("impulse morph local flag")
    if local_flag not in {0, 1}:
        _raise_pmx_error(
            section=section,
            record_index=offset_index,
            offset=local_flag_offset,
            operation="validating impulse morph local flag",
            reason=(f"invalid flag {local_flag}; expected 0 or 1."),
        )

    return PmxImpulseMorphOffset(
        rigid_body_index=rigid_body_index,
        local=(local_flag == 1),
        velocity=_read_pmx_vec3(
            reader,
            "impulse morph velocity",
        ),
        angular_torque=_read_pmx_vec3(
            reader,
            "impulse morph angular torque",
        ),
    )


def _read_pmx_morph_offset(
    reader: BinaryReader,
    result: PmxHeaderScanResult,
    *,
    morph_type: int,
    morph_count: int,
    morph_record_index: int,
    offset_index: int,
) -> PmxMorphOffset:
    """Read one type-specific PMX morph offset."""

    section = f"morphs[{morph_record_index}].offsets"

    with reader.context(
        section,
        record_index=offset_index,
    ):
        if morph_type == 0:
            return _read_pmx_group_morph_offset(
                reader,
                result=result,
                morph_count=morph_count,
                section=section,
                offset_index=offset_index,
            )

        if morph_type == 1:
            return _read_pmx_vertex_morph_offset(
                reader,
                result=result,
                section=section,
                offset_index=offset_index,
            )

        if morph_type == 2:
            return _read_pmx_bone_morph_offset(
                reader,
                result=result,
                section=section,
                offset_index=offset_index,
            )

        if 3 <= morph_type <= 7:
            return _read_pmx_uv_morph_offset(
                reader,
                result=result,
                section=section,
                offset_index=offset_index,
            )

        if morph_type == 8:
            return _read_pmx_material_morph_offset(
                reader,
                result=result,
                section=section,
                offset_index=offset_index,
            )

        if morph_type == 9:
            return _read_pmx_flip_morph_offset(
                reader,
                result=result,
                morph_count=morph_count,
                section=section,
                offset_index=offset_index,
            )

        if morph_type == 10:
            return _read_pmx_impulse_morph_offset(
                reader,
                result=result,
                section=section,
                offset_index=offset_index,
            )

    raise AssertionError(f"Unhandled PMX morph type: {morph_type}")


def _read_pmx_morph(
    reader: BinaryReader,
    result: PmxHeaderScanResult,
    *,
    record_index: int,
    morph_count: int,
) -> PmxMorph:
    """Read one PMX morph and its bounded offset records."""

    if result.encoding is None:
        _raise_pmx_error(
            section="morphs",
            record_index=record_index,
            offset=reader.offset,
            operation="reading morph",
            reason="PMX text encoding is unavailable.",
        )

    if result.index_sizes is None:
        _raise_pmx_error(
            section="morphs",
            record_index=record_index,
            offset=reader.offset,
            operation="reading morph",
            reason="PMX index sizes are unavailable.",
        )

    if result.version is None or result.additional_uv_count is None:
        _raise_pmx_error(
            section="morphs",
            record_index=record_index,
            offset=reader.offset,
            operation="reading morph",
            reason="PMX header metadata is unavailable.",
        )

    require_even_length = result.encoding == "utf-16-le"

    with reader.context(
        "morphs",
        record_index=record_index,
    ):
        local_name = reader.read_length_prefixed_text(
            "local morph name",
            encoding=result.encoding,
            max_length=MAX_PMX_NAME_BYTES,
            require_even_length=require_even_length,
        )
        universal_name = reader.read_length_prefixed_text(
            "universal morph name",
            encoding=result.encoding,
            max_length=MAX_PMX_NAME_BYTES,
            require_even_length=require_even_length,
        )

        panel_offset = reader.offset
        panel = reader.read_uint8("morph panel")
        panel_name = _decode_pmx_morph_panel(
            panel,
            offset=panel_offset,
            record_index=record_index,
        )

        type_offset = reader.offset
        morph_type = reader.read_uint8("morph type")
        morph_type_name = _decode_pmx_morph_type(
            morph_type,
            version=result.version,
            additional_uv_count=result.additional_uv_count,
            offset=type_offset,
            record_index=record_index,
        )

        minimum_offset_size = _minimum_pmx_morph_offset_size(
            morph_type,
            index_sizes=result.index_sizes,
        )
        offset_count = reader.read_bounded_count(
            "morph offset count",
            max_count=MAX_PMX_MORPH_OFFSET_COUNT,
            minimum_item_size=minimum_offset_size,
        )

    offsets = tuple(
        _read_pmx_morph_offset(
            reader,
            result,
            morph_type=morph_type,
            morph_count=morph_count,
            morph_record_index=record_index,
            offset_index=offset_index,
        )
        for offset_index in range(offset_count)
    )

    return PmxMorph(
        local_name=local_name,
        universal_name=universal_name,
        panel=panel,
        panel_name=panel_name,
        morph_type=morph_type,
        morph_type_name=morph_type_name,
        offsets=offsets,
    )


def _scan_pmx_morphs(
    reader: BinaryReader,
    result: PmxHeaderScanResult,
) -> None:
    """Read PMX morphs and validate all currently resolvable references."""

    if result.index_sizes is None:
        _raise_pmx_error(
            section="morphs",
            offset=reader.offset,
            operation="starting morph scan",
            reason="PMX index sizes are unavailable.",
        )

    with reader.context("morphs"):
        morph_count = reader.read_bounded_count(
            "morph count",
            max_count=MAX_PMX_MORPH_COUNT,
            minimum_item_size=_minimum_pmx_morph_size(),
        )

    result.morph_count = morph_count
    morphs: list[PmxMorph] = []
    total_offset_count = 0

    for record_index in range(morph_count):
        morph = _read_pmx_morph(
            reader,
            result,
            record_index=record_index,
            morph_count=morph_count,
        )
        morphs.append(morph)
        total_offset_count += len(morph.offsets)

        if total_offset_count > MAX_PMX_TOTAL_MORPH_OFFSET_COUNT:
            _raise_pmx_error(
                section="morphs",
                record_index=record_index,
                offset=reader.offset,
                operation="validating total morph offset count",
                reason=(
                    f"cumulative morph offset count "
                    f"{total_offset_count} exceeds the safety limit "
                    f"of {MAX_PMX_TOTAL_MORPH_OFFSET_COUNT}."
                ),
            )

    result.morphs = morphs


def _minimum_pmx_display_frame_size() -> int:
    """Return the smallest possible PMX display-frame record size."""

    text_length_fields = 8
    special_flag_size = 1
    element_count_size = 4

    return text_length_fields + special_flag_size + element_count_size


def _minimum_pmx_display_frame_element_size(
    index_sizes: PmxIndexSizes,
) -> int:
    """Return the smallest possible PMX display-frame element size."""

    target_type_size = 1
    target_index_size = min(
        index_sizes.bone,
        index_sizes.morph,
    )

    return target_type_size + target_index_size


def _validate_pmx_display_frame_target_index(
    value: int,
    *,
    target_type: Literal["bone", "morph"],
    target_count: int,
    frame_record_index: int,
    element_index: int,
    offset: int,
) -> None:
    """Validate one display-frame bone or morph reference."""

    if value < 0 or value >= target_count:
        if target_count == 0:
            expected = f"no valid {target_type} index exists"
        else:
            expected = f"expected a value from 0 through {target_count - 1}"

        _raise_pmx_error(
            section=(f"display_frames[{frame_record_index}].elements"),
            record_index=element_index,
            offset=offset,
            operation=(f"validating display-frame {target_type} index"),
            reason=(
                f"index {value} is invalid for {target_type} count "
                f"{target_count}; {expected}."
            ),
        )


def _read_pmx_display_frame_element(
    reader: BinaryReader,
    result: PmxHeaderScanResult,
    *,
    frame_record_index: int,
    element_index: int,
) -> PmxDisplayFrameElement:
    """Read and validate one PMX display-frame element."""

    if result.index_sizes is None:
        _raise_pmx_error(
            section=(f"display_frames[{frame_record_index}].elements"),
            record_index=element_index,
            offset=reader.offset,
            operation="reading display-frame element",
            reason="PMX index sizes are unavailable.",
        )

    if result.bone_count is None:
        _raise_pmx_error(
            section=(f"display_frames[{frame_record_index}].elements"),
            record_index=element_index,
            offset=reader.offset,
            operation="reading display-frame element",
            reason="PMX bone count is unavailable.",
        )

    if result.morph_count is None:
        _raise_pmx_error(
            section=(f"display_frames[{frame_record_index}].elements"),
            record_index=element_index,
            offset=reader.offset,
            operation="reading display-frame element",
            reason="PMX morph count is unavailable.",
        )

    section = f"display_frames[{frame_record_index}].elements"

    with reader.context(
        section,
        record_index=element_index,
    ):
        target_type_offset = reader.offset
        target_type_value = reader.read_uint8("display-frame element target type")

        if target_type_value == 0:
            target_type: Literal["bone", "morph"] = "bone"
            target_count = result.bone_count
            target_index_size = result.index_sizes.bone
        elif target_type_value == 1:
            target_type = "morph"
            target_count = result.morph_count
            target_index_size = result.index_sizes.morph
        else:
            _raise_pmx_error(
                section=section,
                record_index=element_index,
                offset=target_type_offset,
                operation=("validating display-frame element target type"),
                reason=(
                    f"invalid target type {target_type_value}; "
                    "expected 0 for bone or 1 for morph."
                ),
            )

        target_index_offset = reader.offset
        target_index = reader.read_index(
            target_index_size,
            signed=True,
            label=(f"display-frame {target_type} index"),
        )

    _validate_pmx_display_frame_target_index(
        target_index,
        target_type=target_type,
        target_count=target_count,
        frame_record_index=frame_record_index,
        element_index=element_index,
        offset=target_index_offset,
    )

    return PmxDisplayFrameElement(
        target_type=target_type,
        target_index=target_index,
    )


def _read_pmx_display_frame(
    reader: BinaryReader,
    result: PmxHeaderScanResult,
    *,
    record_index: int,
) -> PmxDisplayFrame:
    """Read one PMX display-frame record."""

    if result.encoding is None:
        _raise_pmx_error(
            section="display_frames",
            record_index=record_index,
            offset=reader.offset,
            operation="reading display frame",
            reason="PMX text encoding is unavailable.",
        )

    if result.index_sizes is None:
        _raise_pmx_error(
            section="display_frames",
            record_index=record_index,
            offset=reader.offset,
            operation="reading display frame",
            reason="PMX index sizes are unavailable.",
        )

    require_even_length = result.encoding == "utf-16-le"

    with reader.context(
        "display_frames",
        record_index=record_index,
    ):
        local_name = reader.read_length_prefixed_text(
            "local display-frame name",
            encoding=result.encoding,
            max_length=MAX_PMX_NAME_BYTES,
            require_even_length=require_even_length,
        )
        universal_name = reader.read_length_prefixed_text(
            "universal display-frame name",
            encoding=result.encoding,
            max_length=MAX_PMX_NAME_BYTES,
            require_even_length=require_even_length,
        )

        special_flag_offset = reader.offset
        special_flag = reader.read_uint8("display-frame special flag")

        if special_flag not in {0, 1}:
            _raise_pmx_error(
                section="display_frames",
                record_index=record_index,
                offset=special_flag_offset,
                operation="validating display-frame special flag",
                reason=(f"invalid special flag {special_flag}; expected 0 or 1."),
            )

        element_count = reader.read_bounded_count(
            "display-frame element count",
            max_count=MAX_PMX_DISPLAY_FRAME_ELEMENT_COUNT,
            minimum_item_size=(
                _minimum_pmx_display_frame_element_size(result.index_sizes)
            ),
        )

    elements = tuple(
        _read_pmx_display_frame_element(
            reader,
            result,
            frame_record_index=record_index,
            element_index=element_index,
        )
        for element_index in range(element_count)
    )

    return PmxDisplayFrame(
        local_name=local_name,
        universal_name=universal_name,
        special=bool(special_flag),
        elements=elements,
    )


def _scan_pmx_display_frames(
    reader: BinaryReader,
    result: PmxHeaderScanResult,
) -> None:
    """Read PMX display frames and validate bone/morph references."""

    if result.index_sizes is None:
        _raise_pmx_error(
            section="display_frames",
            offset=reader.offset,
            operation="starting display-frame scan",
            reason="PMX index sizes are unavailable.",
        )

    with reader.context("display_frames"):
        display_frame_count = reader.read_bounded_count(
            "display-frame count",
            max_count=MAX_PMX_DISPLAY_FRAME_COUNT,
            minimum_item_size=_minimum_pmx_display_frame_size(),
        )

    result.display_frame_count = display_frame_count
    display_frames: list[PmxDisplayFrame] = []
    total_element_count = 0

    for record_index in range(display_frame_count):
        display_frame = _read_pmx_display_frame(
            reader,
            result,
            record_index=record_index,
        )
        display_frames.append(display_frame)
        total_element_count += len(display_frame.elements)

        if total_element_count > MAX_PMX_TOTAL_DISPLAY_FRAME_ELEMENT_COUNT:
            _raise_pmx_error(
                section="display_frames",
                record_index=record_index,
                offset=reader.offset,
                operation=("validating total display-frame element count"),
                reason=(
                    f"cumulative display-frame element count "
                    f"{total_element_count} exceeds the safety "
                    "limit of "
                    f"{MAX_PMX_TOTAL_DISPLAY_FRAME_ELEMENT_COUNT}."
                ),
            )

    result.display_frames = display_frames


def _minimum_pmx_rigid_body_size(
    index_sizes: PmxIndexSizes,
) -> int:
    """Return the fixed minimum size of one PMX rigid-body record."""

    text_length_fields = 8
    bone_index_size = index_sizes.bone
    collision_group_size = 1
    collision_mask_size = 2
    shape_size = 1
    vector_fields_size = 36
    physical_scalar_fields_size = 20
    physics_mode_size = 1

    return (
        text_length_fields
        + bone_index_size
        + collision_group_size
        + collision_mask_size
        + shape_size
        + vector_fields_size
        + physical_scalar_fields_size
        + physics_mode_size
    )


def _validate_pmx_finite_scalar(
    value: float,
    *,
    section: str,
    record_index: int,
    label: str,
    offset: int,
    nonnegative: bool,
) -> None:
    """Validate one finite PMX rigid-body scalar."""

    if not math.isfinite(value):
        _raise_pmx_error(
            section=section,
            record_index=record_index,
            offset=offset,
            operation=f"validating {label}",
            reason=f"{label} must be finite.",
        )

    if nonnegative and value < 0.0:
        _raise_pmx_error(
            section=section,
            record_index=record_index,
            offset=offset,
            operation=f"validating {label}",
            reason=f"{label} cannot be negative: {value}.",
        )


def _validate_pmx_finite_vec3(
    value: tuple[float, float, float],
    *,
    section: str,
    record_index: int,
    label: str,
    offset: int,
    nonnegative: bool,
) -> None:
    """Validate one finite PMX rigid-body vec3."""

    component_names = ("x", "y", "z")

    for component_index, component in enumerate(value):
        component_label = f"{label} {component_names[component_index]}"
        _validate_pmx_finite_scalar(
            component,
            section=section,
            record_index=record_index,
            label=component_label,
            offset=offset + component_index * 4,
            nonnegative=nonnegative,
        )


def _decode_pmx_rigid_body_shape(
    value: int,
    *,
    record_index: int,
    offset: int,
) -> str:
    """Validate and decode one PMX rigid-body shape value."""

    shape_names = {
        0: "sphere",
        1: "box",
        2: "capsule",
    }

    try:
        return shape_names[value]
    except KeyError:
        _raise_pmx_error(
            section="rigid_bodies",
            record_index=record_index,
            offset=offset,
            operation="validating rigid-body shape",
            reason=(
                f"invalid rigid-body shape {value}; expected "
                "0 for sphere, 1 for box, or 2 for capsule."
            ),
        )


def _decode_pmx_rigid_body_physics_mode(
    value: int,
    *,
    record_index: int,
    offset: int,
) -> str:
    """Validate and decode one PMX rigid-body physics mode."""

    mode_names = {
        0: "bone_follow",
        1: "physics",
        2: "physics_with_bone_alignment",
    }

    try:
        return mode_names[value]
    except KeyError:
        _raise_pmx_error(
            section="rigid_bodies",
            record_index=record_index,
            offset=offset,
            operation="validating rigid-body physics mode",
            reason=(
                f"invalid physics mode {value}; expected a value from 0 through 2."
            ),
        )


def _read_pmx_rigid_body(
    reader: BinaryReader,
    result: PmxHeaderScanResult,
    *,
    record_index: int,
) -> PmxRigidBody:
    """Read and validate one PMX rigid-body record."""

    if result.encoding is None:
        _raise_pmx_error(
            section="rigid_bodies",
            record_index=record_index,
            offset=reader.offset,
            operation="reading rigid body",
            reason="PMX text encoding is unavailable.",
        )

    if result.index_sizes is None or result.bone_count is None:
        _raise_pmx_error(
            section="rigid_bodies",
            record_index=record_index,
            offset=reader.offset,
            operation="reading rigid body",
            reason="PMX index sizes or bone count are unavailable.",
        )

    require_even_length = result.encoding == "utf-16-le"

    with reader.context("rigid_bodies", record_index=record_index):
        local_name = reader.read_length_prefixed_text(
            "local rigid-body name",
            encoding=result.encoding,
            max_length=MAX_PMX_NAME_BYTES,
            require_even_length=require_even_length,
        )
        universal_name = reader.read_length_prefixed_text(
            "universal rigid-body name",
            encoding=result.encoding,
            max_length=MAX_PMX_NAME_BYTES,
            require_even_length=require_even_length,
        )

        bone_index_offset = reader.offset
        bone_index = reader.read_index(
            result.index_sizes.bone,
            signed=True,
            label="rigid-body bone index",
        )
        _validate_pmx_bone_index(
            bone_index,
            bone_count=result.bone_count,
            section="rigid_bodies",
            record_index=record_index,
            label="rigid-body bone index",
            offset=bone_index_offset,
            allow_sentinel=True,
        )

        collision_group_offset = reader.offset
        collision_group = reader.read_uint8("rigid-body collision group")
        if collision_group > 15:
            _raise_pmx_error(
                section="rigid_bodies",
                record_index=record_index,
                offset=collision_group_offset,
                operation="validating rigid-body collision group",
                reason=(
                    f"collision group {collision_group} is invalid; "
                    "expected a value from 0 through 15."
                ),
            )

        collision_mask = _read_pmx_uint16(
            reader,
            "rigid-body collision mask",
        )

        shape_offset = reader.offset
        shape = reader.read_uint8("rigid-body shape")
        shape_name = _decode_pmx_rigid_body_shape(
            shape,
            record_index=record_index,
            offset=shape_offset,
        )

        size_offset = reader.offset
        size = _read_pmx_vec3(reader, "rigid-body size")
        _validate_pmx_finite_vec3(
            size,
            section="rigid_bodies",
            record_index=record_index,
            label="rigid-body size",
            offset=size_offset,
            nonnegative=True,
        )

        position_offset = reader.offset
        position = _read_pmx_vec3(reader, "rigid-body position")
        _validate_pmx_finite_vec3(
            position,
            section="rigid_bodies",
            record_index=record_index,
            label="rigid-body position",
            offset=position_offset,
            nonnegative=False,
        )

        rotation_offset = reader.offset
        rotation = _read_pmx_vec3(reader, "rigid-body rotation")
        _validate_pmx_finite_vec3(
            rotation,
            section="rigid_bodies",
            record_index=record_index,
            label="rigid-body rotation",
            offset=rotation_offset,
            nonnegative=False,
        )

        scalar_fields: list[tuple[str, float, int]] = []
        for scalar_label in (
            "rigid-body mass",
            "rigid-body linear damping",
            "rigid-body angular damping",
            "rigid-body restitution",
            "rigid-body friction",
        ):
            scalar_offset = reader.offset
            scalar_value = reader.read_float32(scalar_label)
            _validate_pmx_finite_scalar(
                scalar_value,
                section="rigid_bodies",
                record_index=record_index,
                label=scalar_label,
                offset=scalar_offset,
                nonnegative=True,
            )
            scalar_fields.append((scalar_label, scalar_value, scalar_offset))

        physics_mode_offset = reader.offset
        physics_mode = reader.read_uint8("rigid-body physics mode")
        physics_mode_name = _decode_pmx_rigid_body_physics_mode(
            physics_mode,
            record_index=record_index,
            offset=physics_mode_offset,
        )

    return PmxRigidBody(
        local_name=local_name,
        universal_name=universal_name,
        bone_index=bone_index,
        collision_group=collision_group,
        collision_mask=collision_mask,
        shape=shape,
        shape_name=shape_name,
        size=size,
        position=position,
        rotation=rotation,
        mass=scalar_fields[0][1],
        linear_damping=scalar_fields[1][1],
        angular_damping=scalar_fields[2][1],
        restitution=scalar_fields[3][1],
        friction=scalar_fields[4][1],
        physics_mode=physics_mode,
        physics_mode_name=physics_mode_name,
    )


def _validate_pmx_impulse_rigid_body_references(
    result: PmxHeaderScanResult,
    *,
    offset: int,
) -> None:
    """Validate impulse-morph references after rigid bodies are known."""

    if result.rigid_body_count is None:
        _raise_pmx_error(
            section="rigid_bodies",
            offset=offset,
            operation="validating impulse morph references",
            reason="PMX rigid-body count is unavailable.",
        )

    for morph_index, morph in enumerate(result.morphs):
        for offset_index, morph_offset in enumerate(morph.offsets):
            if not isinstance(morph_offset, PmxImpulseMorphOffset):
                continue

            _validate_pmx_index_range(
                morph_offset.rigid_body_index,
                count=result.rigid_body_count,
                section=f"morphs[{morph_index}].offsets",
                record_index=offset_index,
                label="impulse morph rigid-body index",
                offset=offset,
                allow_sentinel=False,
            )


def _scan_pmx_rigid_bodies(
    reader: BinaryReader,
    result: PmxHeaderScanResult,
) -> None:
    """Read PMX rigid bodies and resolve impulse-morph references."""

    if result.index_sizes is None:
        _raise_pmx_error(
            section="rigid_bodies",
            offset=reader.offset,
            operation="starting rigid-body scan",
            reason="PMX index sizes are unavailable.",
        )

    count_offset = reader.offset
    with reader.context("rigid_bodies"):
        rigid_body_count = reader.read_bounded_count(
            "rigid-body count",
            max_count=MAX_PMX_RIGID_BODY_COUNT,
            minimum_item_size=_minimum_pmx_rigid_body_size(result.index_sizes),
        )

    result.rigid_body_count = rigid_body_count
    result.rigid_bodies = [
        _read_pmx_rigid_body(
            reader,
            result,
            record_index=record_index,
        )
        for record_index in range(rigid_body_count)
    ]

    _validate_pmx_impulse_rigid_body_references(
        result,
        offset=count_offset,
    )


def _minimum_pmx_joint_size(
    index_sizes: PmxIndexSizes,
) -> int:
    """Return the fixed minimum size of one PMX joint record."""

    text_length_fields = 8
    joint_type_size = 1
    rigid_body_indices_size = index_sizes.rigid_body * 2
    vector_fields_size = 8 * 12

    return (
        text_length_fields
        + joint_type_size
        + rigid_body_indices_size
        + vector_fields_size
    )


def _decode_pmx_joint_type(
    value: int,
    *,
    version: float,
    record_index: int,
    offset: int,
) -> str:
    """Validate and decode one PMX joint type."""

    type_names = {
        0: "spring_6dof",
        1: "6dof",
        2: "point_to_point",
        3: "cone_twist",
        4: "slider",
        5: "hinge",
    }

    try:
        type_name = type_names[value]
    except KeyError:
        _raise_pmx_error(
            section="joints",
            record_index=record_index,
            offset=offset,
            operation="validating joint type",
            reason=(f"invalid joint type {value}; expected a value from 0 through 5."),
        )

    if version == 2.0 and value != 0:
        _raise_pmx_error(
            section="joints",
            record_index=record_index,
            offset=offset,
            operation="validating joint type",
            reason=(
                f"joint type {value} ({type_name}) requires PMX 2.1; "
                "PMX 2.0 supports only type 0 (spring_6dof)."
            ),
        )

    return type_name


def _validate_pmx_joint_limit_pair(
    minimum: tuple[float, float, float],
    maximum: tuple[float, float, float],
    *,
    record_index: int,
    label: str,
    minimum_offset: int,
) -> None:
    """Validate component-wise PMX joint lower and upper limits."""

    component_names = ("x", "y", "z")

    for component_index, (minimum_value, maximum_value) in enumerate(
        zip(minimum, maximum)
    ):
        if minimum_value <= maximum_value:
            continue

        component_name = component_names[component_index]
        _raise_pmx_error(
            section="joints",
            record_index=record_index,
            offset=minimum_offset + component_index * 4,
            operation=f"validating {label} limits",
            reason=(
                f"{label} minimum {component_name} value "
                f"{minimum_value} exceeds maximum {component_name} "
                f"value {maximum_value}."
            ),
        )


def _read_pmx_joint(
    reader: BinaryReader,
    result: PmxHeaderScanResult,
    *,
    record_index: int,
) -> PmxJoint:
    """Read and validate one PMX joint record."""

    if result.encoding is None or result.version is None:
        _raise_pmx_error(
            section="joints",
            record_index=record_index,
            offset=reader.offset,
            operation="reading joint",
            reason="PMX text encoding or version is unavailable.",
        )

    if result.index_sizes is None or result.rigid_body_count is None:
        _raise_pmx_error(
            section="joints",
            record_index=record_index,
            offset=reader.offset,
            operation="reading joint",
            reason="PMX index sizes or rigid-body count are unavailable.",
        )

    require_even_length = result.encoding == "utf-16-le"

    with reader.context("joints", record_index=record_index):
        local_name = reader.read_length_prefixed_text(
            "local joint name",
            encoding=result.encoding,
            max_length=MAX_PMX_NAME_BYTES,
            require_even_length=require_even_length,
        )
        universal_name = reader.read_length_prefixed_text(
            "universal joint name",
            encoding=result.encoding,
            max_length=MAX_PMX_NAME_BYTES,
            require_even_length=require_even_length,
        )

        joint_type_offset = reader.offset
        joint_type = reader.read_uint8("joint type")
        joint_type_name = _decode_pmx_joint_type(
            joint_type,
            version=result.version,
            record_index=record_index,
            offset=joint_type_offset,
        )

        rigid_body_a_offset = reader.offset
        rigid_body_a_index = reader.read_index(
            result.index_sizes.rigid_body,
            signed=True,
            label="joint rigid-body A index",
        )
        _validate_pmx_index_range(
            rigid_body_a_index,
            count=result.rigid_body_count,
            section="joints",
            record_index=record_index,
            label="joint rigid-body A index",
            offset=rigid_body_a_offset,
            allow_sentinel=True,
        )

        rigid_body_b_offset = reader.offset
        rigid_body_b_index = reader.read_index(
            result.index_sizes.rigid_body,
            signed=True,
            label="joint rigid-body B index",
        )
        _validate_pmx_index_range(
            rigid_body_b_index,
            count=result.rigid_body_count,
            section="joints",
            record_index=record_index,
            label="joint rigid-body B index",
            offset=rigid_body_b_offset,
            allow_sentinel=True,
        )

        vector_fields: list[tuple[str, tuple[float, float, float], int]] = []
        for vector_label in (
            "joint position",
            "joint rotation",
            "joint translation limit minimum",
            "joint translation limit maximum",
            "joint rotation limit minimum",
            "joint rotation limit maximum",
            "joint translation spring",
            "joint rotation spring",
        ):
            vector_offset = reader.offset
            vector_value = _read_pmx_vec3(reader, vector_label)
            _validate_pmx_finite_vec3(
                vector_value,
                section="joints",
                record_index=record_index,
                label=vector_label,
                offset=vector_offset,
                nonnegative=False,
            )
            vector_fields.append((vector_label, vector_value, vector_offset))

    _validate_pmx_joint_limit_pair(
        vector_fields[2][1],
        vector_fields[3][1],
        record_index=record_index,
        label="joint translation limit",
        minimum_offset=vector_fields[2][2],
    )
    _validate_pmx_joint_limit_pair(
        vector_fields[4][1],
        vector_fields[5][1],
        record_index=record_index,
        label="joint rotation limit",
        minimum_offset=vector_fields[4][2],
    )

    return PmxJoint(
        local_name=local_name,
        universal_name=universal_name,
        joint_type=joint_type,
        joint_type_name=joint_type_name,
        rigid_body_a_index=rigid_body_a_index,
        rigid_body_b_index=rigid_body_b_index,
        position=vector_fields[0][1],
        rotation=vector_fields[1][1],
        translation_limit_minimum=vector_fields[2][1],
        translation_limit_maximum=vector_fields[3][1],
        rotation_limit_minimum=vector_fields[4][1],
        rotation_limit_maximum=vector_fields[5][1],
        translation_spring=vector_fields[6][1],
        rotation_spring=vector_fields[7][1],
    )


def _scan_pmx_joints(
    reader: BinaryReader,
    result: PmxHeaderScanResult,
) -> None:
    """Read and validate the PMX joint section."""

    if result.index_sizes is None:
        _raise_pmx_error(
            section="joints",
            offset=reader.offset,
            operation="starting joint scan",
            reason="PMX index sizes are unavailable.",
        )

    with reader.context("joints"):
        joint_count = reader.read_bounded_count(
            "joint count",
            max_count=MAX_PMX_JOINT_COUNT,
            minimum_item_size=_minimum_pmx_joint_size(result.index_sizes),
        )

    result.joint_count = joint_count
    result.joints = [
        _read_pmx_joint(
            reader,
            result,
            record_index=record_index,
        )
        for record_index in range(joint_count)
    ]


def _minimum_pmx_soft_body_size(
    index_sizes: PmxIndexSizes,
) -> int:
    """Return the fixed minimum size of one PMX 2.1 soft body."""

    text_length_fields = 8
    shape_size = 1
    material_index_size = index_sizes.material
    collision_fields_size = 4
    integer_parameter_size = 8
    mass_and_margin_size = 8
    aerodynamics_model_size = 4
    config_float_size = 12 * 4
    cluster_float_size = 6 * 4
    iteration_size = 4 * 4
    material_config_size = 3 * 4
    anchor_and_pin_count_size = 8

    return (
        text_length_fields
        + shape_size
        + material_index_size
        + collision_fields_size
        + integer_parameter_size
        + mass_and_margin_size
        + aerodynamics_model_size
        + config_float_size
        + cluster_float_size
        + iteration_size
        + material_config_size
        + anchor_and_pin_count_size
    )


def _decode_pmx_soft_body_shape(
    value: int,
    *,
    record_index: int,
    offset: int,
) -> str:
    """Validate and decode one PMX 2.1 soft-body shape."""

    shape_names = {
        0: "tri_mesh",
        1: "rope",
    }

    try:
        return shape_names[value]
    except KeyError:
        _raise_pmx_error(
            section="soft_bodies",
            record_index=record_index,
            offset=offset,
            operation="validating soft-body shape",
            reason=(f"invalid soft-body shape {value}; expected 0 or 1."),
        )


def _decode_pmx_soft_body_flags(
    value: int,
    *,
    record_index: int,
    offset: int,
) -> tuple[str, ...]:
    """Validate and decode PMX 2.1 soft-body flag bits."""

    known_mask = 0x07
    unknown_bits = value & ~known_mask
    if unknown_bits:
        _raise_pmx_error(
            section="soft_bodies",
            record_index=record_index,
            offset=offset,
            operation="validating soft-body flags",
            reason=(f"soft-body flags contain unknown bits 0x{unknown_bits:02x}."),
        )

    definitions = (
        (0x01, "generate_bending_links"),
        (0x02, "generate_clusters"),
        (0x04, "randomize_constraints"),
    )
    return tuple(name for bit, name in definitions if value & bit)


def _decode_pmx_soft_body_aerodynamics_model(
    value: int,
    *,
    record_index: int,
    offset: int,
) -> str:
    """Validate and decode a PMX 2.1 aerodynamics model."""

    model_names = {
        0: "vertex_point",
        1: "vertex_two_sided",
        2: "vertex_one_sided",
        3: "face_two_sided",
        4: "face_one_sided",
    }

    try:
        return model_names[value]
    except KeyError:
        _raise_pmx_error(
            section="soft_bodies",
            record_index=record_index,
            offset=offset,
            operation="validating soft-body aerodynamics model",
            reason=(
                f"invalid soft-body aerodynamics model {value}; "
                "expected a value from 0 through 4."
            ),
        )


def _read_pmx_soft_body_float(
    reader: BinaryReader,
    *,
    record_index: int,
    label: str,
    nonnegative: bool,
) -> float:
    """Read and validate one soft-body float field."""

    offset = reader.offset
    value = reader.read_float32(label)
    _validate_pmx_finite_scalar(
        value,
        section="soft_bodies",
        record_index=record_index,
        label=label,
        offset=offset,
        nonnegative=nonnegative,
    )
    return value


def _read_pmx_soft_body_parameter_count(
    reader: BinaryReader,
    *,
    record_index: int,
    label: str,
) -> int:
    """Read one bounded nonnegative PMX soft-body integer parameter."""

    offset = reader.offset
    value = _read_pmx_int32(reader, label)

    if value < 0:
        _raise_pmx_error(
            section="soft_bodies",
            record_index=record_index,
            offset=offset,
            operation=f"validating {label}",
            reason=f"{label} cannot be negative: {value}.",
        )

    if value > MAX_PMX_SOFT_BODY_PARAMETER_COUNT:
        _raise_pmx_error(
            section="soft_bodies",
            record_index=record_index,
            offset=offset,
            operation=f"validating {label}",
            reason=(
                f"{label} {value} exceeds the safety limit of "
                f"{MAX_PMX_SOFT_BODY_PARAMETER_COUNT}."
            ),
        )

    return value


def _read_pmx_soft_body_anchor(
    reader: BinaryReader,
    result: PmxHeaderScanResult,
    *,
    soft_body_index: int,
    anchor_index: int,
) -> PmxSoftBodyAnchor:
    """Read and validate one PMX 2.1 soft-body anchor."""

    if (
        result.index_sizes is None
        or result.rigid_body_count is None
        or result.vertex_count is None
    ):
        _raise_pmx_error(
            section="soft_bodies",
            record_index=soft_body_index,
            offset=reader.offset,
            operation="reading soft-body anchor",
            reason="PMX index sizes or referenced counts are unavailable.",
        )

    with reader.context(
        f"soft_bodies[{soft_body_index}].anchors",
        record_index=anchor_index,
    ):
        rigid_body_offset = reader.offset
        rigid_body_index = reader.read_index(
            result.index_sizes.rigid_body,
            signed=True,
            label="soft-body anchor rigid-body index",
        )
        _validate_pmx_index_range(
            rigid_body_index,
            count=result.rigid_body_count,
            section=f"soft_bodies[{soft_body_index}].anchors",
            record_index=anchor_index,
            label="soft-body anchor rigid-body index",
            offset=rigid_body_offset,
            allow_sentinel=False,
        )

        vertex_offset = reader.offset
        vertex_index = reader.read_index(
            result.index_sizes.vertex,
            signed=False,
            label="soft-body anchor vertex index",
        )
        _validate_pmx_index_range(
            vertex_index,
            count=result.vertex_count,
            section=f"soft_bodies[{soft_body_index}].anchors",
            record_index=anchor_index,
            label="soft-body anchor vertex index",
            offset=vertex_offset,
            allow_sentinel=False,
        )

        near_mode_offset = reader.offset
        near_mode_value = reader.read_uint8("soft-body anchor near-mode flag")
        if near_mode_value not in (0, 1):
            _raise_pmx_error(
                section=f"soft_bodies[{soft_body_index}].anchors",
                record_index=anchor_index,
                offset=near_mode_offset,
                operation="validating soft-body anchor near-mode flag",
                reason=(
                    f"invalid soft-body anchor near-mode flag "
                    f"{near_mode_value}; expected 0 or 1."
                ),
            )

    return PmxSoftBodyAnchor(
        rigid_body_index=rigid_body_index,
        vertex_index=vertex_index,
        near_mode=bool(near_mode_value),
    )


def _read_pmx_soft_body(
    reader: BinaryReader,
    result: PmxHeaderScanResult,
    *,
    record_index: int,
) -> PmxSoftBody:
    """Read and validate one PMX 2.1 soft-body record."""

    if result.encoding is None or result.index_sizes is None:
        _raise_pmx_error(
            section="soft_bodies",
            record_index=record_index,
            offset=reader.offset,
            operation="reading soft body",
            reason="PMX encoding or index sizes are unavailable.",
        )

    if (
        result.material_count is None
        or result.rigid_body_count is None
        or result.vertex_count is None
    ):
        _raise_pmx_error(
            section="soft_bodies",
            record_index=record_index,
            offset=reader.offset,
            operation="reading soft body",
            reason="PMX referenced section counts are unavailable.",
        )

    require_even_length = result.encoding == "utf-16-le"

    with reader.context("soft_bodies", record_index=record_index):
        local_name = reader.read_length_prefixed_text(
            "local soft-body name",
            encoding=result.encoding,
            max_length=MAX_PMX_NAME_BYTES,
            require_even_length=require_even_length,
        )
        universal_name = reader.read_length_prefixed_text(
            "universal soft-body name",
            encoding=result.encoding,
            max_length=MAX_PMX_NAME_BYTES,
            require_even_length=require_even_length,
        )

        shape_offset = reader.offset
        shape = reader.read_uint8("soft-body shape")
        shape_name = _decode_pmx_soft_body_shape(
            shape,
            record_index=record_index,
            offset=shape_offset,
        )

        material_offset = reader.offset
        material_index = reader.read_index(
            result.index_sizes.material,
            signed=True,
            label="soft-body material index",
        )
        _validate_pmx_index_range(
            material_index,
            count=result.material_count,
            section="soft_bodies",
            record_index=record_index,
            label="soft-body material index",
            offset=material_offset,
            allow_sentinel=True,
        )

        collision_group_offset = reader.offset
        collision_group = reader.read_uint8("soft-body collision group")
        if collision_group > 15:
            _raise_pmx_error(
                section="soft_bodies",
                record_index=record_index,
                offset=collision_group_offset,
                operation="validating soft-body collision group",
                reason=(
                    f"soft-body collision group {collision_group} is "
                    "outside the supported range 0 through 15."
                ),
            )

        collision_mask = _read_pmx_uint16(
            reader,
            "soft-body collision mask",
        )

        flags_offset = reader.offset
        flags = reader.read_uint8("soft-body flags")
        flag_names = _decode_pmx_soft_body_flags(
            flags,
            record_index=record_index,
            offset=flags_offset,
        )

        bending_link_distance = _read_pmx_soft_body_parameter_count(
            reader,
            record_index=record_index,
            label="soft-body bending-link distance",
        )
        cluster_count = _read_pmx_soft_body_parameter_count(
            reader,
            record_index=record_index,
            label="soft-body cluster count",
        )

        total_mass = _read_pmx_soft_body_float(
            reader,
            record_index=record_index,
            label="soft-body total mass",
            nonnegative=True,
        )
        collision_margin = _read_pmx_soft_body_float(
            reader,
            record_index=record_index,
            label="soft-body collision margin",
            nonnegative=True,
        )

        aerodynamics_offset = reader.offset
        aerodynamics_model = _read_pmx_int32(
            reader,
            "soft-body aerodynamics model",
        )
        aerodynamics_model_name = _decode_pmx_soft_body_aerodynamics_model(
            aerodynamics_model,
            record_index=record_index,
            offset=aerodynamics_offset,
        )

        config_labels = (
            "soft-body velocity correction factor",
            "soft-body damping coefficient",
            "soft-body drag coefficient",
            "soft-body lift coefficient",
            "soft-body pressure coefficient",
            "soft-body volume conservation coefficient",
            "soft-body dynamic friction coefficient",
            "soft-body pose matching coefficient",
            "soft-body rigid contact hardness",
            "soft-body kinetic contact hardness",
            "soft-body soft contact hardness",
            "soft-body anchor hardness",
        )
        config_values = tuple(
            _read_pmx_soft_body_float(
                reader,
                record_index=record_index,
                label=label,
                nonnegative=False,
            )
            for label in config_labels
        )

        cluster_labels = (
            "soft-body soft-rigid cluster hardness",
            "soft-body soft-kinetic cluster hardness",
            "soft-body soft-soft cluster hardness",
            "soft-body soft-rigid impulse split",
            "soft-body soft-kinetic impulse split",
            "soft-body soft-soft impulse split",
        )
        cluster_values = tuple(
            _read_pmx_soft_body_float(
                reader,
                record_index=record_index,
                label=label,
                nonnegative=False,
            )
            for label in cluster_labels
        )

        iteration_values = tuple(
            _read_pmx_soft_body_parameter_count(
                reader,
                record_index=record_index,
                label=label,
            )
            for label in (
                "soft-body velocity iteration count",
                "soft-body position iteration count",
                "soft-body drift iteration count",
                "soft-body cluster iteration count",
            )
        )

        material_values = tuple(
            _read_pmx_soft_body_float(
                reader,
                record_index=record_index,
                label=label,
                nonnegative=False,
            )
            for label in (
                "soft-body linear stiffness",
                "soft-body area-angular stiffness",
                "soft-body volume stiffness",
            )
        )

        anchor_count = reader.read_bounded_count(
            "soft-body anchor count",
            max_count=MAX_PMX_SOFT_BODY_ANCHOR_COUNT,
            minimum_item_size=(
                result.index_sizes.rigid_body + result.index_sizes.vertex + 1
            ),
        )

        anchors = tuple(
            _read_pmx_soft_body_anchor(
                reader,
                result,
                soft_body_index=record_index,
                anchor_index=anchor_index,
            )
            for anchor_index in range(anchor_count)
        )

        pinned_vertex_count = reader.read_bounded_count(
            "soft-body pinned-vertex count",
            max_count=MAX_PMX_SOFT_BODY_PIN_COUNT,
            minimum_item_size=result.index_sizes.vertex,
        )

        pinned_vertex_indices: list[int] = []
        for pin_index in range(pinned_vertex_count):
            with reader.context(
                f"soft_bodies[{record_index}].pinned_vertices",
                record_index=pin_index,
            ):
                pin_offset = reader.offset
                vertex_index = reader.read_index(
                    result.index_sizes.vertex,
                    signed=False,
                    label="soft-body pinned vertex index",
                )
                _validate_pmx_index_range(
                    vertex_index,
                    count=result.vertex_count,
                    section=(f"soft_bodies[{record_index}].pinned_vertices"),
                    record_index=pin_index,
                    label="soft-body pinned vertex index",
                    offset=pin_offset,
                    allow_sentinel=False,
                )
                pinned_vertex_indices.append(vertex_index)

    return PmxSoftBody(
        local_name=local_name,
        universal_name=universal_name,
        shape=shape,
        shape_name=shape_name,
        material_index=material_index,
        collision_group=collision_group,
        collision_mask=collision_mask,
        flags=flags,
        flag_names=flag_names,
        bending_link_distance=bending_link_distance,
        cluster_count=cluster_count,
        total_mass=total_mass,
        collision_margin=collision_margin,
        config=PmxSoftBodyConfig(
            aerodynamics_model=aerodynamics_model,
            aerodynamics_model_name=aerodynamics_model_name,
            velocity_correction_factor=config_values[0],
            damping_coefficient=config_values[1],
            drag_coefficient=config_values[2],
            lift_coefficient=config_values[3],
            pressure_coefficient=config_values[4],
            volume_conservation_coefficient=config_values[5],
            dynamic_friction_coefficient=config_values[6],
            pose_matching_coefficient=config_values[7],
            rigid_contact_hardness=config_values[8],
            kinetic_contact_hardness=config_values[9],
            soft_contact_hardness=config_values[10],
            anchor_hardness=config_values[11],
        ),
        cluster_config=PmxSoftBodyClusterConfig(
            soft_rigid_hardness=cluster_values[0],
            soft_kinetic_hardness=cluster_values[1],
            soft_soft_hardness=cluster_values[2],
            soft_rigid_impulse_split=cluster_values[3],
            soft_kinetic_impulse_split=cluster_values[4],
            soft_soft_impulse_split=cluster_values[5],
        ),
        iteration_config=PmxSoftBodyIterationConfig(
            velocity=iteration_values[0],
            position=iteration_values[1],
            drift=iteration_values[2],
            cluster=iteration_values[3],
        ),
        material_config=PmxSoftBodyMaterialConfig(
            linear_stiffness=material_values[0],
            area_angular_stiffness=material_values[1],
            volume_stiffness=material_values[2],
        ),
        anchors=anchors,
        pinned_vertex_indices=tuple(pinned_vertex_indices),
    )


def _scan_pmx_soft_bodies(
    reader: BinaryReader,
    result: PmxHeaderScanResult,
) -> None:
    """Read and validate the optional PMX 2.1 soft-body section."""

    if result.version is None or result.index_sizes is None:
        _raise_pmx_error(
            section="soft_bodies",
            offset=reader.offset,
            operation="starting soft-body scan",
            reason="PMX version or index sizes are unavailable.",
        )

    if result.version == 2.0:
        result.soft_body_count = 0
        result.soft_bodies = []
        return

    with reader.context("soft_bodies"):
        count_offset = reader.offset
        soft_body_count = reader.read_bounded_count(
            "soft-body count",
            max_count=MAX_PMX_SOFT_BODY_COUNT,
            minimum_item_size=_minimum_pmx_soft_body_size(result.index_sizes),
        )

    result.soft_body_count = soft_body_count
    soft_bodies: list[PmxSoftBody] = []
    total_anchor_count = 0
    total_pin_count = 0

    for record_index in range(soft_body_count):
        soft_body = _read_pmx_soft_body(
            reader,
            result,
            record_index=record_index,
        )
        total_anchor_count += len(soft_body.anchors)
        total_pin_count += len(soft_body.pinned_vertex_indices)

        if total_anchor_count > MAX_PMX_TOTAL_SOFT_BODY_ANCHOR_COUNT:
            _raise_pmx_error(
                section="soft_bodies",
                record_index=record_index,
                offset=count_offset,
                operation="validating total soft-body anchor count",
                reason=(
                    f"soft bodies declare {total_anchor_count} total "
                    "anchors, exceeding the safety limit of "
                    f"{MAX_PMX_TOTAL_SOFT_BODY_ANCHOR_COUNT}."
                ),
            )

        if total_pin_count > MAX_PMX_TOTAL_SOFT_BODY_PIN_COUNT:
            _raise_pmx_error(
                section="soft_bodies",
                record_index=record_index,
                offset=count_offset,
                operation="validating total soft-body pinned-vertex count",
                reason=(
                    f"soft bodies declare {total_pin_count} total pinned "
                    "vertices, exceeding the safety limit of "
                    f"{MAX_PMX_TOTAL_SOFT_BODY_PIN_COUNT}."
                ),
            )

        soft_bodies.append(soft_body)

    result.soft_body_count = soft_body_count
    result.soft_bodies = soft_bodies


def _build_pmx_section_summary(
    result: PmxHeaderScanResult,
) -> PmxSectionSummary:
    """Build aggregate section counts after a complete PMX scan."""

    required_counts = {
        "vertex_count": result.vertex_count,
        "surface_index_count": result.surface_index_count,
        "triangle_count": result.triangle_count,
        "texture_count": result.texture_count,
        "material_count": result.material_count,
        "bone_count": result.bone_count,
        "morph_count": result.morph_count,
        "display_frame_count": result.display_frame_count,
        "rigid_body_count": result.rigid_body_count,
        "joint_count": result.joint_count,
        "soft_body_count": result.soft_body_count,
    }
    missing = [name for name, value in required_counts.items() if value is None]
    if missing:
        raise AssertionError(
            "Cannot summarize an incomplete PMX scan; missing: " + ", ".join(missing)
        )

    return PmxSectionSummary(
        vertex_count=required_counts["vertex_count"],
        surface_index_count=required_counts["surface_index_count"],
        triangle_count=required_counts["triangle_count"],
        texture_count=required_counts["texture_count"],
        material_count=required_counts["material_count"],
        bone_count=required_counts["bone_count"],
        ik_count=sum(1 for bone in result.bones if bone.ik is not None),
        ik_link_count=sum(
            len(bone.ik.links) for bone in result.bones if bone.ik is not None
        ),
        morph_count=required_counts["morph_count"],
        morph_offset_count=sum(len(morph.offsets) for morph in result.morphs),
        display_frame_count=required_counts["display_frame_count"],
        display_frame_element_count=sum(
            len(display_frame.elements) for display_frame in result.display_frames
        ),
        rigid_body_count=required_counts["rigid_body_count"],
        joint_count=required_counts["joint_count"],
        soft_body_count=required_counts["soft_body_count"],
        soft_body_anchor_count=sum(
            len(soft_body.anchors) for soft_body in result.soft_bodies
        ),
        pinned_vertex_count=sum(
            len(soft_body.pinned_vertex_indices) for soft_body in result.soft_bodies
        ),
    )


def _build_pmx_dependency_summary(
    result: PmxHeaderScanResult,
) -> PmxDependencySummary:
    """Summarize material references to declared PMX texture paths."""

    material_reference_count = sum(
        material.texture_index >= 0 for material in result.materials
    )
    sphere_reference_count = sum(
        material.sphere_texture_index >= 0 for material in result.materials
    )
    toon_reference_count = sum(
        material.toon_reference_mode == "texture" and material.toon_reference_index >= 0
        for material in result.materials
    )

    referenced_indices = sorted(
        {
            index
            for material in result.materials
            for index in (
                material.texture_index,
                material.sphere_texture_index,
                (
                    material.toon_reference_index
                    if material.toon_reference_mode == "texture"
                    else -1
                ),
            )
            if index >= 0
        }
    )
    referenced_index_set = set(referenced_indices)
    unreferenced_indices = [
        index
        for index in range(len(result.texture_paths))
        if index not in referenced_index_set
    ]

    return PmxDependencySummary(
        declared_texture_path_count=len(result.texture_paths),
        material_texture_reference_count=material_reference_count,
        sphere_texture_reference_count=sphere_reference_count,
        toon_texture_reference_count=toon_reference_count,
        total_texture_reference_count=(
            material_reference_count + sphere_reference_count + toon_reference_count
        ),
        referenced_texture_indices=tuple(referenced_indices),
        referenced_texture_paths=tuple(
            result.texture_paths[index] for index in referenced_indices
        ),
        unreferenced_texture_indices=tuple(unreferenced_indices),
        unreferenced_texture_paths=tuple(
            result.texture_paths[index] for index in unreferenced_indices
        ),
    )


def _finalize_pmx_structure_scan(
    reader: BinaryReader,
    result: PmxHeaderScanResult,
) -> None:
    """Finalize byte accounting and summaries after all PMX sections."""

    trailing_byte_count = reader.remaining
    section_summary = _build_pmx_section_summary(result)
    dependency_summary = _build_pmx_dependency_summary(result)

    result.trailing_byte_count = trailing_byte_count
    result.section_summary = section_summary
    result.dependency_summary = dependency_summary
    result.scan_complete = True

    if trailing_byte_count:
        result.warnings.append(
            "PMX file contains "
            f"{trailing_byte_count} trailing byte(s) after "
            "the final structural section."
        )


def _scan_pmx_header(
    reader: BinaryReader,
    result: PmxHeaderScanResult,
) -> PmxHeader:
    """Scan PMX signature, globals, index sizes, and model information."""

    magic, magic_offset = read_pmx_magic(reader)

    result.magic = magic.decode(
        "ascii",
        errors="replace",
    )
    validate_pmx_magic(
        magic,
        offset=magic_offset,
    )

    result.detected_format = "pmx"
    header_state = PmxHeaderReadState()

    try:
        header_data = read_pmx_header_body(
            reader,
            magic=magic,
            state=header_state,
        )
    finally:
        result.version = header_state.version
        result.encoding = header_state.encoding
        result.global_count = header_state.global_count
        result.additional_uv_count = header_state.additional_uv_count
        result.index_sizes = header_state.index_sizes
        result.model_info = header_state.model_info

    result.warnings.extend(header_data.warnings)
    return header_data.header


def scan_pmx_header(
    file_path: str | Path,
) -> PmxHeaderScanResult:
    """Safely scan the PMX header and complete model-information block.

    This function intentionally stops before the vertex section.
    """

    path = Path(file_path)
    result = PmxHeaderScanResult()

    try:
        with path.open("rb") as file:
            reader = BinaryReader(
                file,
                format_name="PMX",
            )
            result.file_size = reader.size

            try:
                _scan_pmx_header(
                    reader,
                    result,
                )
            except BinaryParseError as error:
                result.errors.append(str(error))
            finally:
                result.bytes_consumed = reader.offset

    except OSError as error:
        result.errors.append(f"Unable to read PMX model file: {error}.")

    return result


def scan_pmx_structure(
    file_path: str | Path,
) -> PmxHeaderScanResult:
    """Scan all structural sections defined by PMX 2.0 and 2.1."""

    path = Path(file_path)
    result = PmxHeaderScanResult()

    try:
        with path.open("rb") as file:
            reader = BinaryReader(
                file,
                format_name="PMX",
            )
            result.file_size = reader.size

            try:
                header = _scan_pmx_header(
                    reader,
                    result,
                )
                _scan_pmx_geometry(
                    reader,
                    result,
                    header=header,
                )
                _scan_pmx_textures(
                    reader,
                    result,
                    header=header,
                )
                _scan_pmx_materials(
                    reader,
                    result,
                    header=header,
                )
                _scan_pmx_bones(
                    reader,
                    result,
                    header=header,
                )
                _scan_pmx_morphs(
                    reader,
                    result,
                )
                _scan_pmx_display_frames(
                    reader,
                    result,
                )
                _scan_pmx_rigid_bodies(
                    reader,
                    result,
                )
                _scan_pmx_joints(
                    reader,
                    result,
                )
                _scan_pmx_soft_bodies(
                    reader,
                    result,
                )
                _finalize_pmx_structure_scan(
                    reader,
                    result,
                )
            except BinaryParseError as error:
                result.errors.append(str(error))
            finally:
                result.bytes_consumed = reader.offset

    except OSError as error:
        result.errors.append(f"Unable to read PMX model file: {error}.")

    return result
