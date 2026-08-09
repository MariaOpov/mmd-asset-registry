"""Deterministic PMX serialization independent from CLI and UI layers."""

from __future__ import annotations

import os
import struct
import tempfile
from pathlib import Path

from mmd_registry.pmx.document import (
    PMX_BONE_FLAG_EXTERNAL_PARENT,
    PMX_BONE_FLAG_FIXED_AXIS,
    PMX_BONE_FLAG_IK,
    PMX_BONE_FLAG_INHERIT_ROTATION,
    PMX_BONE_FLAG_INHERIT_TRANSLATION,
    PMX_BONE_FLAG_LOCAL_AXES,
    PMX_BONE_FLAG_TAIL_INDEX,
    PmxBdef1,
    PmxBdef2,
    PmxBdef4,
    PmxBone,
    PmxBoneMorphOffset,
    PmxDisplayFrame,
    PmxDocument,
    PmxFlipMorphOffset,
    PmxGroupMorphOffset,
    PmxImpulseMorphOffset,
    PmxJoint,
    PmxMaterial,
    PmxMaterialMorphOffset,
    PmxMorph,
    PmxQdef,
    PmxRigidBody,
    PmxSdef,
    PmxSoftBody,
    PmxUvMorphOffset,
    PmxVertex,
    PmxVertexMorphOffset,
)
from mmd_registry.pmx.validation import validate_pmx_document


class _PmxBuffer:
    """Append-only little-endian PMX byte builder."""

    def __init__(self, document: PmxDocument) -> None:
        self.document = document
        self.parts: list[bytes] = []

    def pack(self, format_string: str, *values: object) -> None:
        """Append one little-endian struct payload."""

        self.parts.append(struct.pack("<" + format_string, *values))

    def raw(self, value: bytes) -> None:
        """Append immutable raw bytes."""

        self.parts.append(value)

    def count(self, value: int) -> None:
        """Append one signed 32-bit PMX count."""

        self.pack("i", value)

    def index(self, value: int, *, size: int, signed: bool) -> None:
        """Append one PMX variable-width index."""

        self.parts.append(
            value.to_bytes(size, byteorder="little", signed=signed)
        )

    def text(self, value: str) -> None:
        """Append one PMX length-prefixed text field."""

        encoded = value.encode(self.document.header.encoding, errors="strict")
        self.count(len(encoded))
        self.raw(encoded)

    def floats(self, values: tuple[float, ...]) -> None:
        """Append one fixed tuple of little-endian float32 values."""

        self.pack(f"{len(values)}f", *values)

    def finish(self) -> bytes:
        """Return the complete immutable byte sequence."""

        return b"".join(self.parts)


def _write_header(buffer: _PmxBuffer) -> None:
    """Write the PMX signature, globals, and model information."""

    document = buffer.document
    header = document.header
    index_sizes = header.index_sizes

    buffer.raw(b"PMX ")
    buffer.pack("f", header.version)
    buffer.pack("B", header.global_count)
    buffer.raw(
        bytes(
            (
                header.encoding_flag,
                header.additional_uv_count,
                index_sizes.vertex,
                index_sizes.texture,
                index_sizes.material,
                index_sizes.bone,
                index_sizes.morph,
                index_sizes.rigid_body,
            )
        )
    )
    buffer.raw(header.extra_global_data)

    model_info = document.model_info
    for value in (
        model_info.local_name,
        model_info.universal_name,
        model_info.local_comments,
        model_info.universal_comments,
    ):
        buffer.text(value)


def _write_deform(buffer: _PmxBuffer, vertex: PmxVertex) -> None:
    """Write one type-specific PMX vertex deform payload."""

    deform = vertex.deform
    bone_index_size = buffer.document.header.index_sizes.bone
    buffer.pack("B", deform.deform_type)

    if isinstance(deform, PmxBdef1):
        buffer.index(deform.bone_index, size=bone_index_size, signed=True)
        return

    if isinstance(deform, (PmxBdef2, PmxSdef)):
        for bone_index in deform.bone_indices:
            buffer.index(bone_index, size=bone_index_size, signed=True)
        buffer.pack("f", deform.bone_1_weight)
        if isinstance(deform, PmxSdef):
            buffer.floats(deform.c)
            buffer.floats(deform.r0)
            buffer.floats(deform.r1)
        return

    if isinstance(deform, (PmxBdef4, PmxQdef)):
        for bone_index in deform.bone_indices:
            buffer.index(bone_index, size=bone_index_size, signed=True)
        buffer.floats(deform.weights)
        return

    raise AssertionError(f"Unsupported PMX deform: {type(deform).__name__}")


def _write_geometry(buffer: _PmxBuffer) -> None:
    """Write complete vertex and triangle-index sections."""

    document = buffer.document
    buffer.count(len(document.vertices))
    for vertex in document.vertices:
        buffer.floats(vertex.position)
        buffer.floats(vertex.normal)
        buffer.floats(vertex.uv)
        for additional_uv in vertex.additional_uvs:
            buffer.floats(additional_uv)
        _write_deform(buffer, vertex)
        buffer.pack("f", vertex.edge_scale)

    buffer.count(len(document.surface_indices))
    for vertex_index in document.surface_indices:
        buffer.index(
            vertex_index,
            size=document.header.index_sizes.vertex,
            signed=False,
        )


def _write_textures(buffer: _PmxBuffer) -> None:
    """Write the ordered texture-path table."""

    buffer.count(len(buffer.document.texture_paths))
    for texture_path in buffer.document.texture_paths:
        buffer.text(texture_path)


def _write_material(buffer: _PmxBuffer, material: PmxMaterial) -> None:
    """Write one complete PMX material record."""

    texture_index_size = buffer.document.header.index_sizes.texture
    buffer.text(material.local_name)
    buffer.text(material.universal_name)
    buffer.floats(material.diffuse)
    buffer.floats(material.specular)
    buffer.pack("f", material.specular_strength)
    buffer.floats(material.ambient)
    buffer.pack("B", material.drawing_flags)
    buffer.floats(material.edge_color)
    buffer.pack("f", material.edge_scale)
    buffer.index(material.texture_index, size=texture_index_size, signed=True)
    buffer.index(
        material.sphere_texture_index,
        size=texture_index_size,
        signed=True,
    )
    buffer.pack("B", material.sphere_mode)

    if material.toon_reference_mode == "texture":
        buffer.pack("B", 0)
        buffer.index(
            material.toon_reference_index,
            size=texture_index_size,
            signed=True,
        )
    else:
        buffer.pack("B", 1)
        buffer.pack("B", material.toon_reference_index)

    buffer.text(material.memo)
    buffer.count(material.surface_index_count)


def _write_materials(buffer: _PmxBuffer) -> None:
    """Write the complete ordered PMX material section."""

    buffer.count(len(buffer.document.materials))
    for material in buffer.document.materials:
        _write_material(buffer, material)


def _write_ik(buffer: _PmxBuffer, bone: PmxBone) -> None:
    """Write one flag-enabled PMX inverse-kinematics payload."""

    assert bone.ik is not None
    bone_index_size = buffer.document.header.index_sizes.bone
    buffer.index(
        bone.ik.target_bone_index,
        size=bone_index_size,
        signed=True,
    )
    buffer.pack("i", bone.ik.loop_count)
    buffer.pack("f", bone.ik.angle_limit)
    buffer.count(len(bone.ik.links))
    for link in bone.ik.links:
        buffer.index(link.bone_index, size=bone_index_size, signed=True)
        buffer.pack("B", int(link.angle_limits_enabled))
        if link.angle_limits_enabled:
            assert link.lower_limit is not None
            assert link.upper_limit is not None
            buffer.floats(link.lower_limit)
            buffer.floats(link.upper_limit)


def _write_bone(buffer: _PmxBuffer, bone: PmxBone) -> None:
    """Write one complete flag-controlled PMX bone record."""

    bone_index_size = buffer.document.header.index_sizes.bone
    buffer.text(bone.local_name)
    buffer.text(bone.universal_name)
    buffer.floats(bone.position)
    buffer.index(bone.parent_bone_index, size=bone_index_size, signed=True)
    buffer.pack("i", bone.transform_layer)
    buffer.pack("H", bone.flags)

    if bone.flags & PMX_BONE_FLAG_TAIL_INDEX:
        assert bone.tail_bone_index is not None
        buffer.index(bone.tail_bone_index, size=bone_index_size, signed=True)
    else:
        assert bone.tail_offset is not None
        buffer.floats(bone.tail_offset)

    if bone.flags & (
        PMX_BONE_FLAG_INHERIT_ROTATION | PMX_BONE_FLAG_INHERIT_TRANSLATION
    ):
        assert bone.inherit_parent_bone_index is not None
        assert bone.inherit_weight is not None
        buffer.index(
            bone.inherit_parent_bone_index,
            size=bone_index_size,
            signed=True,
        )
        buffer.pack("f", bone.inherit_weight)

    if bone.flags & PMX_BONE_FLAG_FIXED_AXIS:
        assert bone.fixed_axis is not None
        buffer.floats(bone.fixed_axis)

    if bone.flags & PMX_BONE_FLAG_LOCAL_AXES:
        assert bone.local_axis_x is not None
        assert bone.local_axis_z is not None
        buffer.floats(bone.local_axis_x)
        buffer.floats(bone.local_axis_z)

    if bone.flags & PMX_BONE_FLAG_EXTERNAL_PARENT:
        assert bone.external_parent_key is not None
        buffer.pack("i", bone.external_parent_key)

    if bone.flags & PMX_BONE_FLAG_IK:
        _write_ik(buffer, bone)


def _write_bones(buffer: _PmxBuffer) -> None:
    """Write the complete ordered PMX bone section."""

    buffer.count(len(buffer.document.bones))
    for bone in buffer.document.bones:
        _write_bone(buffer, bone)


def _write_morph_offset(
    buffer: _PmxBuffer,
    morph: PmxMorph,
    offset: object,
) -> None:
    """Write one already-validated type-specific morph offset."""

    sizes = buffer.document.header.index_sizes
    if isinstance(offset, (PmxGroupMorphOffset, PmxFlipMorphOffset)):
        buffer.index(offset.morph_index, size=sizes.morph, signed=True)
        buffer.pack("f", offset.weight)
    elif isinstance(offset, PmxVertexMorphOffset):
        buffer.index(offset.vertex_index, size=sizes.vertex, signed=False)
        buffer.floats(offset.translation)
    elif isinstance(offset, PmxBoneMorphOffset):
        buffer.index(offset.bone_index, size=sizes.bone, signed=True)
        buffer.floats(offset.translation)
        buffer.floats(offset.rotation)
    elif isinstance(offset, PmxUvMorphOffset):
        buffer.index(offset.vertex_index, size=sizes.vertex, signed=False)
        buffer.floats(offset.uv_offset)
    elif isinstance(offset, PmxMaterialMorphOffset):
        buffer.index(offset.material_index, size=sizes.material, signed=True)
        buffer.pack("B", 0 if offset.operation == "multiply" else 1)
        buffer.floats(offset.diffuse)
        buffer.floats(offset.specular)
        buffer.pack("f", offset.specular_strength)
        buffer.floats(offset.ambient)
        buffer.floats(offset.edge_color)
        buffer.pack("f", offset.edge_scale)
        buffer.floats(offset.texture_tint)
        buffer.floats(offset.sphere_tint)
        buffer.floats(offset.toon_tint)
    elif isinstance(offset, PmxImpulseMorphOffset):
        buffer.index(
            offset.rigid_body_index,
            size=sizes.rigid_body,
            signed=True,
        )
        buffer.pack("B", int(offset.local))
        buffer.floats(offset.velocity)
        buffer.floats(offset.angular_torque)
    else:
        raise AssertionError(
            f"Unsupported offset for morph type {morph.morph_type}: "
            f"{type(offset).__name__}"
        )


def _write_morphs(buffer: _PmxBuffer) -> None:
    """Write the complete ordered PMX morph section."""

    buffer.count(len(buffer.document.morphs))
    for morph in buffer.document.morphs:
        buffer.text(morph.local_name)
        buffer.text(morph.universal_name)
        buffer.pack("B", morph.panel)
        buffer.pack("B", morph.morph_type)
        buffer.count(len(morph.offsets))
        for offset in morph.offsets:
            _write_morph_offset(buffer, morph, offset)


def _write_display_frame(buffer: _PmxBuffer, frame: PmxDisplayFrame) -> None:
    """Write one complete PMX display-frame record."""

    sizes = buffer.document.header.index_sizes
    buffer.text(frame.local_name)
    buffer.text(frame.universal_name)
    buffer.pack("B", int(frame.special))
    buffer.count(len(frame.elements))
    for element in frame.elements:
        if element.target_type == "bone":
            buffer.pack("B", 0)
            buffer.index(element.target_index, size=sizes.bone, signed=True)
        else:
            buffer.pack("B", 1)
            buffer.index(element.target_index, size=sizes.morph, signed=True)


def _write_display_frames(buffer: _PmxBuffer) -> None:
    """Write the complete ordered PMX display-frame section."""

    buffer.count(len(buffer.document.display_frames))
    for frame in buffer.document.display_frames:
        _write_display_frame(buffer, frame)


def _write_rigid_body(buffer: _PmxBuffer, body: PmxRigidBody) -> None:
    """Write one complete PMX rigid-body record."""

    bone_index_size = buffer.document.header.index_sizes.bone
    buffer.text(body.local_name)
    buffer.text(body.universal_name)
    buffer.index(body.bone_index, size=bone_index_size, signed=True)
    buffer.pack("B", body.collision_group)
    buffer.pack("H", body.collision_mask)
    buffer.pack("B", body.shape)
    buffer.floats(body.size)
    buffer.floats(body.position)
    buffer.floats(body.rotation)
    for value in (
        body.mass,
        body.linear_damping,
        body.angular_damping,
        body.restitution,
        body.friction,
    ):
        buffer.pack("f", value)
    buffer.pack("B", body.physics_mode)


def _write_rigid_bodies(buffer: _PmxBuffer) -> None:
    """Write the complete ordered PMX rigid-body section."""

    buffer.count(len(buffer.document.rigid_bodies))
    for body in buffer.document.rigid_bodies:
        _write_rigid_body(buffer, body)


def _write_joint(buffer: _PmxBuffer, joint: PmxJoint) -> None:
    """Write one complete PMX joint record."""

    rigid_body_index_size = buffer.document.header.index_sizes.rigid_body
    buffer.text(joint.local_name)
    buffer.text(joint.universal_name)
    buffer.pack("B", joint.joint_type)
    buffer.index(
        joint.rigid_body_a_index,
        size=rigid_body_index_size,
        signed=True,
    )
    buffer.index(
        joint.rigid_body_b_index,
        size=rigid_body_index_size,
        signed=True,
    )
    for value in (
        joint.position,
        joint.rotation,
        joint.translation_limit_minimum,
        joint.translation_limit_maximum,
        joint.rotation_limit_minimum,
        joint.rotation_limit_maximum,
        joint.translation_spring,
        joint.rotation_spring,
    ):
        buffer.floats(value)


def _write_joints(buffer: _PmxBuffer) -> None:
    """Write the complete ordered PMX joint section."""

    buffer.count(len(buffer.document.joints))
    for joint in buffer.document.joints:
        _write_joint(buffer, joint)


def _write_soft_body(buffer: _PmxBuffer, body: PmxSoftBody) -> None:
    """Write one complete PMX 2.1 soft-body record."""

    sizes = buffer.document.header.index_sizes
    buffer.text(body.local_name)
    buffer.text(body.universal_name)
    buffer.pack("B", body.shape)
    buffer.index(body.material_index, size=sizes.material, signed=True)
    buffer.pack("B", body.collision_group)
    buffer.pack("H", body.collision_mask)
    buffer.pack("B", body.flags)
    buffer.pack("i", body.bending_link_distance)
    buffer.pack("i", body.cluster_count)
    buffer.pack("f", body.total_mass)
    buffer.pack("f", body.collision_margin)

    config = body.config
    buffer.pack("i", config.aerodynamics_model)
    buffer.floats(
        (
            config.velocity_correction_factor,
            config.damping_coefficient,
            config.drag_coefficient,
            config.lift_coefficient,
            config.pressure_coefficient,
            config.volume_conservation_coefficient,
            config.dynamic_friction_coefficient,
            config.pose_matching_coefficient,
            config.rigid_contact_hardness,
            config.kinetic_contact_hardness,
            config.soft_contact_hardness,
            config.anchor_hardness,
        )
    )

    cluster = body.cluster_config
    buffer.floats(
        (
            cluster.soft_rigid_hardness,
            cluster.soft_kinetic_hardness,
            cluster.soft_soft_hardness,
            cluster.soft_rigid_impulse_split,
            cluster.soft_kinetic_impulse_split,
            cluster.soft_soft_impulse_split,
        )
    )
    iteration = body.iteration_config
    buffer.pack(
        "4i",
        iteration.velocity,
        iteration.position,
        iteration.drift,
        iteration.cluster,
    )
    material = body.material_config
    buffer.floats(
        (
            material.linear_stiffness,
            material.area_angular_stiffness,
            material.volume_stiffness,
        )
    )

    buffer.count(len(body.anchors))
    for anchor in body.anchors:
        buffer.index(
            anchor.rigid_body_index,
            size=sizes.rigid_body,
            signed=True,
        )
        buffer.index(anchor.vertex_index, size=sizes.vertex, signed=False)
        buffer.pack("B", int(anchor.near_mode))

    buffer.count(len(body.pinned_vertex_indices))
    for vertex_index in body.pinned_vertex_indices:
        buffer.index(vertex_index, size=sizes.vertex, signed=False)


def _write_soft_bodies(buffer: _PmxBuffer) -> None:
    """Write the optional complete PMX 2.1 soft-body section."""

    if buffer.document.header.version == 2.0:
        return

    buffer.count(len(buffer.document.soft_bodies))
    for body in buffer.document.soft_bodies:
        _write_soft_body(buffer, body)


def serialize_pmx(document: PmxDocument) -> bytes:
    """Validate and deterministically serialize one complete PMX document."""

    validate_pmx_document(document)
    buffer = _PmxBuffer(document)
    _write_header(buffer)
    _write_geometry(buffer)
    _write_textures(buffer)
    _write_materials(buffer)
    _write_bones(buffer)
    _write_morphs(buffer)
    _write_display_frames(buffer)
    _write_rigid_bodies(buffer)
    _write_joints(buffer)
    _write_soft_bodies(buffer)
    buffer.raw(document.trailing_data)
    return buffer.finish()


def write_pmx(
    document: PmxDocument,
    destination: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Safely write a validated PMX document to one filesystem path."""

    data = serialize_pmx(document)
    path = Path(destination)

    if not overwrite:
        with path.open("xb") as file:
            file.write(data)
        return path

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            temporary_path = Path(file.name)
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    return path
