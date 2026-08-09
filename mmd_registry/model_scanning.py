"""Safe structural metadata scanning for PMX and PMD model files."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

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
    PmxBoneMorphOffset,
    PmxDisplayFrame,
    PmxDisplayFrameElement,
    PmxFlipMorphOffset,
    PmxGroupMorphOffset,
    PmxHeader,
    PmxIk,
    PmxIkLink,
    PmxImpulseMorphOffset,
    PmxIndexSizes,
    PmxJoint,
    PmxMaterial,
    PmxMaterialMorphOffset,
    PmxModelInfo,
    PmxMorph,
    PmxMorphOffset,
    PmxRigidBody,
    PmxSoftBody,
    PmxSoftBodyAnchor,
    PmxSoftBodyClusterConfig,
    PmxSoftBodyConfig,
    PmxSoftBodyIterationConfig,
    PmxSoftBodyMaterialConfig,
    PmxUvMorphOffset,
    PmxVertexMorphOffset,
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
from mmd_registry.pmx.sections.display_frames import (
    MAX_PMX_DISPLAY_FRAME_COUNT,
    MAX_PMX_DISPLAY_FRAME_ELEMENT_COUNT,
    MAX_PMX_TOTAL_DISPLAY_FRAME_ELEMENT_COUNT,
    PmxDisplayFrameReadState,
    read_pmx_display_frames,
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
from mmd_registry.pmx.sections.joints import (
    MAX_PMX_JOINT_COUNT,
    PmxJointReadState,
    read_pmx_joints,
)
from mmd_registry.pmx.sections.morphs import (
    MAX_PMX_MORPH_COUNT,
    MAX_PMX_MORPH_OFFSET_COUNT,
    MAX_PMX_TOTAL_MORPH_OFFSET_COUNT,
    PmxMorphReadState,
    read_pmx_morphs,
)
from mmd_registry.pmx.sections.rigid_bodies import (
    MAX_PMX_RIGID_BODY_COUNT,
    PmxRigidBodyReadState,
    read_pmx_rigid_bodies,
)
from mmd_registry.pmx.sections.soft_bodies import (
    MAX_PMX_SOFT_BODY_ANCHOR_COUNT,
    MAX_PMX_SOFT_BODY_COUNT,
    MAX_PMX_SOFT_BODY_PARAMETER_COUNT,
    MAX_PMX_SOFT_BODY_PIN_COUNT,
    MAX_PMX_TOTAL_SOFT_BODY_ANCHOR_COUNT,
    MAX_PMX_TOTAL_SOFT_BODY_PIN_COUNT,
    PmxSoftBodyReadState,
    read_pmx_soft_bodies,
)
from mmd_registry.pmx.sections.textures import (
    MAX_PMX_TEXTURE_COUNT,
    PmxTextureReadState,
    read_pmx_textures,
)


ScanStatus = Literal["ok", "warning", "error"]


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


def _scan_pmx_morphs(
    reader: BinaryReader,
    result: PmxHeaderScanResult,
    *,
    header: PmxHeader,
) -> None:
    """Read morphs while preserving the legacy list projection."""

    if result.vertex_count is None:
        _raise_pmx_error(
            section="morphs",
            offset=reader.offset,
            operation="starting morph scan",
            reason="PMX vertex count is unavailable.",
        )
    if result.bone_count is None:
        _raise_pmx_error(
            section="morphs",
            offset=reader.offset,
            operation="starting morph scan",
            reason="PMX bone count is unavailable.",
        )
    if result.material_count is None:
        _raise_pmx_error(
            section="morphs",
            offset=reader.offset,
            operation="starting morph scan",
            reason="PMX material count is unavailable.",
        )

    morph_state = PmxMorphReadState()

    try:
        read_pmx_morphs(
            reader,
            header=header,
            vertex_count=result.vertex_count,
            bone_count=result.bone_count,
            material_count=result.material_count,
            state=morph_state,
            max_total_offset_count=MAX_PMX_TOTAL_MORPH_OFFSET_COUNT,
        )
    finally:
        result.morph_count = morph_state.morph_count
        result.morphs = list(morph_state.morphs)


def _scan_pmx_display_frames(
    reader: BinaryReader,
    result: PmxHeaderScanResult,
    *,
    header: PmxHeader,
) -> None:
    """Read display frames while preserving the legacy list projection."""

    if result.bone_count is None:
        _raise_pmx_error(
            section="display_frames",
            offset=reader.offset,
            operation="starting display-frame scan",
            reason="PMX bone count is unavailable.",
        )
    if result.morph_count is None:
        _raise_pmx_error(
            section="display_frames",
            offset=reader.offset,
            operation="starting display-frame scan",
            reason="PMX morph count is unavailable.",
        )

    frame_state = PmxDisplayFrameReadState()

    try:
        read_pmx_display_frames(
            reader,
            header=header,
            bone_count=result.bone_count,
            morph_count=result.morph_count,
            state=frame_state,
            max_total_element_count=(
                MAX_PMX_TOTAL_DISPLAY_FRAME_ELEMENT_COUNT
            ),
        )
    finally:
        result.display_frame_count = frame_state.display_frame_count
        result.display_frames = list(frame_state.display_frames)


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
    *,
    header: PmxHeader,
) -> None:
    """Read rigid bodies and resolve impulse-morph references."""

    if result.bone_count is None:
        _raise_pmx_error(
            section="rigid_bodies",
            offset=reader.offset,
            operation="starting rigid-body scan",
            reason="PMX bone count is unavailable.",
        )

    count_offset = reader.offset
    rigid_body_state = PmxRigidBodyReadState()

    try:
        read_pmx_rigid_bodies(
            reader,
            header=header,
            bone_count=result.bone_count,
            state=rigid_body_state,
        )
    finally:
        result.rigid_body_count = rigid_body_state.rigid_body_count
        result.rigid_bodies = list(rigid_body_state.rigid_bodies)

    _validate_pmx_impulse_rigid_body_references(
        result,
        offset=count_offset,
    )


def _scan_pmx_joints(
    reader: BinaryReader,
    result: PmxHeaderScanResult,
    *,
    header: PmxHeader,
) -> None:
    """Read joints while preserving the legacy list projection."""

    if result.rigid_body_count is None:
        _raise_pmx_error(
            section="joints",
            offset=reader.offset,
            operation="starting joint scan",
            reason="PMX rigid-body count is unavailable.",
        )

    joint_state = PmxJointReadState()

    try:
        read_pmx_joints(
            reader,
            header=header,
            rigid_body_count=result.rigid_body_count,
            state=joint_state,
        )
    finally:
        result.joint_count = joint_state.joint_count
        result.joints = list(joint_state.joints)


def _scan_pmx_soft_bodies(
    reader: BinaryReader,
    result: PmxHeaderScanResult,
    *,
    header: PmxHeader,
) -> None:
    """Read soft bodies while preserving the legacy list projection."""

    if result.material_count is None:
        _raise_pmx_error(
            section="soft_bodies",
            offset=reader.offset,
            operation="starting soft-body scan",
            reason="PMX material count is unavailable.",
        )
    if result.rigid_body_count is None:
        _raise_pmx_error(
            section="soft_bodies",
            offset=reader.offset,
            operation="starting soft-body scan",
            reason="PMX rigid-body count is unavailable.",
        )
    if result.vertex_count is None:
        _raise_pmx_error(
            section="soft_bodies",
            offset=reader.offset,
            operation="starting soft-body scan",
            reason="PMX vertex count is unavailable.",
        )

    soft_body_state = PmxSoftBodyReadState()

    try:
        read_pmx_soft_bodies(
            reader,
            header=header,
            material_count=result.material_count,
            rigid_body_count=result.rigid_body_count,
            vertex_count=result.vertex_count,
            state=soft_body_state,
            max_total_anchor_count=(
                MAX_PMX_TOTAL_SOFT_BODY_ANCHOR_COUNT
            ),
            max_total_pin_count=MAX_PMX_TOTAL_SOFT_BODY_PIN_COUNT,
        )
    finally:
        result.soft_body_count = soft_body_state.soft_body_count
        result.soft_bodies = list(soft_body_state.soft_bodies)


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
                    header=header,
                )
                _scan_pmx_display_frames(
                    reader,
                    result,
                    header=header,
                )
                _scan_pmx_rigid_bodies(
                    reader,
                    result,
                    header=header,
                )
                _scan_pmx_joints(
                    reader,
                    result,
                    header=header,
                )
                _scan_pmx_soft_bodies(
                    reader,
                    result,
                    header=header,
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
