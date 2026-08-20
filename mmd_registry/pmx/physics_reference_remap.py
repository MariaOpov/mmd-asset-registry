"""CP14 physics-section structural reference remapping kernels.

This module is intentionally internal. It rewrites only relationships owned by
CP14:

* impulse morph -> rigid body
* rigid body -> bone
* joint -> rigid body A / B
* soft body -> material
* soft-body anchor -> rigid body / vertex
* soft-body pin -> vertex

Rigid-body collection transforms operate only on surviving rigid-body records,
so outgoing references from a deleted rigid-body source cannot create false
failures. Morph deletion/reordering remains CP13-owned; callers must pass the
surviving morph collection when remapping impulse references. Joints and soft
bodies are ordered non-target source collections and are not deleted/reordered
here. No PmxDocument orchestration, serialization, public mutation API, or
automatic repair policy is performed.
"""

from __future__ import annotations

from dataclasses import replace

from mmd_registry.pmx.collection_transform import PmxCollectionTransform
from mmd_registry.pmx.document import (
    PmxImpulseMorphOffset,
    PmxJoint,
    PmxMorph,
    PmxRigidBody,
    PmxSoftBody,
    PmxSoftBodyAnchor,
)
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.pmx.structural_reference_shift import (
    PmxCollectionReferenceShiftPlan,
)


class PmxPhysicsReferenceRemapError(ValueError):
    """Raised when CP14 remapping would create a dangling reference."""


def _require_transform(
    transform: PmxCollectionTransform,
    expected_kind: PmxReferenceTargetKind,
    field_name: str,
) -> PmxCollectionTransform:
    if not isinstance(transform, PmxCollectionTransform):
        raise TypeError(f"{field_name} must be a PmxCollectionTransform value.")
    if transform.kind is not expected_kind:
        raise ValueError(
            f"{field_name} kind must be {expected_kind.value}, "
            f"got {transform.kind.value}."
        )
    return transform


def _require_plain_index(value: object, field_name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be an integer.")
    return value


def _remap_required_index(
    value: object,
    *,
    field_name: str,
    transform: PmxCollectionTransform,
) -> int:
    index = _require_plain_index(value, field_name)
    if index < 0:
        raise ValueError(f"{field_name} cannot be negative.")
    if index >= transform.old_size:
        raise ValueError(
            f"{field_name}={index} is outside {transform.kind.value} "
            f"old_size {transform.old_size}."
        )

    mapped = transform.remap.target_for(index)
    if mapped is None:
        raise PmxPhysicsReferenceRemapError(
            f"{field_name} references removed {transform.kind.value} index {index}."
        )
    return mapped


def _remap_optional_index(
    value: object,
    *,
    field_name: str,
    transform: PmxCollectionTransform,
) -> int:
    index = _require_plain_index(value, field_name)
    if index == -1:
        return -1
    if index < -1:
        raise ValueError(f"{field_name} cannot be smaller than -1.")
    if index >= transform.old_size:
        raise ValueError(
            f"{field_name}={index} is outside {transform.kind.value} "
            f"old_size {transform.old_size}."
        )

    mapped = transform.remap.target_for(index)
    if mapped is None:
        raise PmxPhysicsReferenceRemapError(
            f"{field_name} references removed {transform.kind.value} index {index}; "
            "removed targets are not converted to the -1 sentinel."
        )
    return mapped


def _require_pmx_version(pmx_version: object) -> float:
    if type(pmx_version) is not float:
        raise TypeError("pmx_version must be a float.")
    if pmx_version not in (2.0, 2.1):
        raise ValueError("pmx_version must be 2.0 or 2.1.")
    return pmx_version


def remap_impulse_morph_rigid_body_references(
    morphs: tuple[PmxMorph, ...],
    rigid_body_transform: PmxCollectionTransform,
    *,
    pmx_version: float,
) -> tuple[PmxMorph, ...]:
    """Rewrite CP14-owned impulse-morph rigid-body references.

    ``morphs`` must already represent the surviving morph source collection.
    Morph collection deletion/reordering remains owned by CP13.
    """

    if type(morphs) is not tuple:
        raise TypeError("morphs must be a tuple.")
    if not all(isinstance(morph, PmxMorph) for morph in morphs):
        raise TypeError("morphs must contain only PmxMorph records.")
    transform = _require_transform(
        rigid_body_transform,
        PmxReferenceTargetKind.RIGID_BODY,
        "rigid_body_transform",
    )
    version = _require_pmx_version(pmx_version)

    rewritten_morphs: list[PmxMorph] = []
    changed = False

    for morph_index, morph in enumerate(morphs):
        if morph.morph_type != 10:
            rewritten_morphs.append(morph)
            continue
        if version != 2.1:
            raise ValueError(
                f"morphs[{morph_index}] type 10 requires PMX 2.1."
            )

        rewritten_offsets: list[object] = []
        morph_changed = False
        for offset_index, offset in enumerate(morph.offsets):
            if not isinstance(offset, PmxImpulseMorphOffset):
                raise ValueError(
                    f"morphs[{morph_index}].offsets[{offset_index}] type 10 "
                    "requires PmxImpulseMorphOffset."
                )

            rigid_body_index = _remap_required_index(
                offset.rigid_body_index,
                field_name=(
                    f"morphs[{morph_index}].offsets[{offset_index}]."
                    "rigid_body_index"
                ),
                transform=transform,
            )
            if rigid_body_index == offset.rigid_body_index:
                rewritten_offsets.append(offset)
                continue
            rewritten_offsets.append(
                replace(offset, rigid_body_index=rigid_body_index)
            )
            morph_changed = True

        if morph_changed:
            rewritten_morphs.append(
                replace(morph, offsets=tuple(rewritten_offsets))
            )
            changed = True
        else:
            rewritten_morphs.append(morph)

    if not changed:
        return morphs
    return tuple(rewritten_morphs)


def transform_rigid_body_collection_references(
    rigid_bodies: tuple[PmxRigidBody, ...],
    rigid_body_transform: PmxCollectionTransform,
    bone_transform: PmxCollectionTransform,
) -> tuple[PmxRigidBody, ...]:
    """Return surviving rigid bodies in new order with bone refs rewritten."""

    if type(rigid_bodies) is not tuple:
        raise TypeError("rigid_bodies must be a tuple.")
    if not all(isinstance(body, PmxRigidBody) for body in rigid_bodies):
        raise TypeError("rigid_bodies must contain only PmxRigidBody records.")

    source_transform = _require_transform(
        rigid_body_transform,
        PmxReferenceTargetKind.RIGID_BODY,
        "rigid_body_transform",
    )
    bone_transform = _require_transform(
        bone_transform,
        PmxReferenceTargetKind.BONE,
        "bone_transform",
    )

    if source_transform.old_size != len(rigid_bodies):
        raise ValueError(
            "rigid_body_transform old_size must match the rigid-body "
            "collection size."
        )

    rewritten: list[PmxRigidBody] = []
    changed = not source_transform.is_noop

    for old_body_index in source_transform.old_indices_in_new_order:
        body = rigid_bodies[old_body_index]
        bone_index = _remap_optional_index(
            body.bone_index,
            field_name=f"rigid_bodies[{old_body_index}].bone_index",
            transform=bone_transform,
        )
        if bone_index == body.bone_index:
            rewritten.append(body)
            continue
        rewritten.append(replace(body, bone_index=bone_index))
        changed = True

    if not changed:
        return rigid_bodies
    return tuple(rewritten)


def remap_joint_rigid_body_references(
    joints: tuple[PmxJoint, ...],
    rigid_body_transform: PmxCollectionTransform,
    *,
    pmx_version: float,
) -> tuple[PmxJoint, ...]:
    """Rewrite optional joint rigid-body A/B references without reordering."""

    if type(joints) is not tuple:
        raise TypeError("joints must be a tuple.")
    if not all(isinstance(joint, PmxJoint) for joint in joints):
        raise TypeError("joints must contain only PmxJoint records.")

    transform = _require_transform(
        rigid_body_transform,
        PmxReferenceTargetKind.RIGID_BODY,
        "rigid_body_transform",
    )
    version = _require_pmx_version(pmx_version)

    rewritten: list[PmxJoint] = []
    changed = False

    for joint_index, joint in enumerate(joints):
        joint_type = _require_plain_index(
            joint.joint_type,
            f"joints[{joint_index}].joint_type",
        )
        if not 0 <= joint_type <= 5:
            raise ValueError(
                f"joints[{joint_index}].joint_type must be a value from 0 through 5."
            )
        if version == 2.0 and joint_type != 0:
            raise ValueError(
                f"joints[{joint_index}] type {joint_type} requires PMX 2.1."
            )

        rigid_body_a_index = _remap_optional_index(
            joint.rigid_body_a_index,
            field_name=f"joints[{joint_index}].rigid_body_a_index",
            transform=transform,
        )
        rigid_body_b_index = _remap_optional_index(
            joint.rigid_body_b_index,
            field_name=f"joints[{joint_index}].rigid_body_b_index",
            transform=transform,
        )

        if (
            rigid_body_a_index == joint.rigid_body_a_index
            and rigid_body_b_index == joint.rigid_body_b_index
        ):
            rewritten.append(joint)
            continue

        rewritten.append(
            replace(
                joint,
                rigid_body_a_index=rigid_body_a_index,
                rigid_body_b_index=rigid_body_b_index,
            )
        )
        changed = True

    if not changed:
        return joints
    return tuple(rewritten)


def remap_soft_body_material_references_for_insertion(
    soft_bodies: tuple[PmxSoftBody, ...],
    material_shift: PmxCollectionReferenceShiftPlan,
    *,
    pmx_version: float,
) -> tuple[PmxSoftBody, ...]:
    """Rewrite CP14-owned soft-body material references through insertion evidence.

    Rigid-body anchors and pinned-vertex references are intentionally preserved;
    their target collections are unchanged by material-only insertion.
    """

    if type(soft_bodies) is not tuple:
        raise TypeError("soft_bodies must be a tuple.")
    if not all(isinstance(body, PmxSoftBody) for body in soft_bodies):
        raise TypeError("soft_bodies must contain only PmxSoftBody records.")
    if not isinstance(material_shift, PmxCollectionReferenceShiftPlan):
        raise TypeError(
            "material_shift must be a PmxCollectionReferenceShiftPlan value."
        )
    if material_shift.target_kind is not PmxReferenceTargetKind.MATERIAL:
        raise ValueError("material_shift target_kind must be material.")

    version = _require_pmx_version(pmx_version)
    if version == 2.0:
        if soft_bodies:
            raise ValueError("PMX 2.0 cannot contain a soft-body section.")
        return soft_bodies

    rewritten_bodies: list[PmxSoftBody] = []
    changed = False
    for body_index, body in enumerate(soft_bodies):
        field_name = f"soft_bodies[{body_index}].material_index"
        material_index = _require_plain_index(body.material_index, field_name)
        if material_index == -1:
            rewritten_bodies.append(body)
            continue
        if material_index < -1:
            raise ValueError(f"{field_name} cannot be smaller than -1.")
        if material_index >= material_shift.current_count:
            raise ValueError(
                f"{field_name}={material_index} is outside material old_size "
                f"{material_shift.current_count}."
            )

        mapped = material_shift.remap.target_for(material_index)
        if mapped is None:
            raise PmxPhysicsReferenceRemapError(
                f"{field_name} references removed material index {material_index}; "
                "removed targets are not converted to the -1 sentinel."
            )
        if mapped == material_index:
            rewritten_bodies.append(body)
            continue

        rewritten_bodies.append(replace(body, material_index=mapped))
        changed = True

    if not changed:
        return soft_bodies
    return tuple(rewritten_bodies)


def remap_soft_body_references(
    soft_bodies: tuple[PmxSoftBody, ...],
    material_transform: PmxCollectionTransform,
    rigid_body_transform: PmxCollectionTransform,
    vertex_transform: PmxCollectionTransform,
    *,
    pmx_version: float,
) -> tuple[PmxSoftBody, ...]:
    """Rewrite all CP14-owned references in the ordered soft-body section."""

    if type(soft_bodies) is not tuple:
        raise TypeError("soft_bodies must be a tuple.")
    if not all(isinstance(body, PmxSoftBody) for body in soft_bodies):
        raise TypeError("soft_bodies must contain only PmxSoftBody records.")

    material_transform = _require_transform(
        material_transform,
        PmxReferenceTargetKind.MATERIAL,
        "material_transform",
    )
    rigid_body_transform = _require_transform(
        rigid_body_transform,
        PmxReferenceTargetKind.RIGID_BODY,
        "rigid_body_transform",
    )
    vertex_transform = _require_transform(
        vertex_transform,
        PmxReferenceTargetKind.VERTEX,
        "vertex_transform",
    )
    version = _require_pmx_version(pmx_version)

    if version == 2.0:
        if soft_bodies:
            raise ValueError("PMX 2.0 cannot contain a soft-body section.")
        return soft_bodies

    rewritten_bodies: list[PmxSoftBody] = []
    changed = False

    for body_index, body in enumerate(soft_bodies):
        material_index = _remap_optional_index(
            body.material_index,
            field_name=f"soft_bodies[{body_index}].material_index",
            transform=material_transform,
        )

        rewritten_anchors: list[PmxSoftBodyAnchor] = []
        anchors_changed = False
        for anchor_index, anchor in enumerate(body.anchors):
            if not isinstance(anchor, PmxSoftBodyAnchor):
                raise TypeError(
                    f"soft_bodies[{body_index}].anchors[{anchor_index}] "
                    "must be a PmxSoftBodyAnchor record."
                )

            rigid_body_index = _remap_required_index(
                anchor.rigid_body_index,
                field_name=(
                    f"soft_bodies[{body_index}].anchors[{anchor_index}]."
                    "rigid_body_index"
                ),
                transform=rigid_body_transform,
            )
            vertex_index = _remap_required_index(
                anchor.vertex_index,
                field_name=(
                    f"soft_bodies[{body_index}].anchors[{anchor_index}]."
                    "vertex_index"
                ),
                transform=vertex_transform,
            )

            if (
                rigid_body_index == anchor.rigid_body_index
                and vertex_index == anchor.vertex_index
            ):
                rewritten_anchors.append(anchor)
                continue

            rewritten_anchors.append(
                replace(
                    anchor,
                    rigid_body_index=rigid_body_index,
                    vertex_index=vertex_index,
                )
            )
            anchors_changed = True

        pinned_vertex_indices = tuple(
            _remap_required_index(
                vertex_index,
                field_name=(
                    f"soft_bodies[{body_index}]."
                    f"pinned_vertex_indices[{pin_index}]"
                ),
                transform=vertex_transform,
            )
            for pin_index, vertex_index in enumerate(body.pinned_vertex_indices)
        )
        pins_changed = pinned_vertex_indices != body.pinned_vertex_indices

        if (
            material_index == body.material_index
            and not anchors_changed
            and not pins_changed
        ):
            rewritten_bodies.append(body)
            continue

        rewritten_bodies.append(
            replace(
                body,
                material_index=material_index,
                anchors=(
                    tuple(rewritten_anchors)
                    if anchors_changed
                    else body.anchors
                ),
                pinned_vertex_indices=(
                    pinned_vertex_indices
                    if pins_changed
                    else body.pinned_vertex_indices
                ),
            )
        )
        changed = True

    if not changed:
        return soft_bodies
    return tuple(rewritten_bodies)


def remap_rigid_body_bone_references_for_insertion(
    rigid_bodies: tuple[PmxRigidBody, ...],
    bone_shift: PmxCollectionReferenceShiftPlan,
) -> tuple[PmxRigidBody, ...]:
    """Rewrite existing rigid-body -> bone refs through additive bone insertion."""

    if type(rigid_bodies) is not tuple:
        raise TypeError("rigid_bodies must be a tuple.")
    if not all(isinstance(body, PmxRigidBody) for body in rigid_bodies):
        raise TypeError("rigid_bodies must contain only PmxRigidBody records.")
    if not isinstance(bone_shift, PmxCollectionReferenceShiftPlan):
        raise TypeError(
            "bone_shift must be a PmxCollectionReferenceShiftPlan value."
        )
    if bone_shift.target_kind is not PmxReferenceTargetKind.BONE:
        raise ValueError("bone_shift target_kind must be bone.")

    rewritten: list[PmxRigidBody] = []
    changed = False
    for body_index, body in enumerate(rigid_bodies):
        field_name = f"rigid_bodies[{body_index}].bone_index"
        bone_index = _require_plain_index(body.bone_index, field_name)
        if bone_index == -1:
            rewritten.append(body)
            continue
        if bone_index < -1:
            raise ValueError(f"{field_name} cannot be smaller than -1.")
        if bone_index >= bone_shift.current_count:
            raise ValueError(
                f"{field_name}={bone_index} is outside bone old_size "
                f"{bone_shift.current_count}."
            )

        mapped = bone_shift.remap.target_for(bone_index)
        if mapped is None:
            raise PmxPhysicsReferenceRemapError(
                f"{field_name} references removed bone index {bone_index}; "
                "insertion shifts cannot remove source bones."
            )
        if mapped == bone_index:
            rewritten.append(body)
            continue
        rewritten.append(replace(body, bone_index=mapped))
        changed = True

    if not changed:
        return rigid_bodies
    return tuple(rewritten)
