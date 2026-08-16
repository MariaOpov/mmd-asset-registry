"""CP12 section-aware vertex-deform and bone/IK reference remapping kernels.

This module is intentionally internal. It consumes the immutable CP09/CP10
mapping models and rewrites only relationships owned by CP12:

* vertex deform -> bone
* bone parent -> bone
* active bone tail -> bone
* active bone inherit parent -> bone
* active IK target -> bone
* active IK links -> bone

Bone collection transforms operate only on surviving bone records, so outgoing
references from a deleted source record cannot create false failures. No
PmxDocument orchestration, morph/display/physics remap, serialization, public
mutation API, or automatic repair policy is performed here.
"""

from __future__ import annotations

from dataclasses import replace

from mmd_registry.pmx.collection_transform import PmxCollectionTransform
from mmd_registry.pmx.document import (
    PMX_BONE_FLAG_IK,
    PMX_BONE_FLAG_INHERIT_ROTATION,
    PMX_BONE_FLAG_INHERIT_TRANSLATION,
    PMX_BONE_FLAG_TAIL_INDEX,
    PmxBdef1,
    PmxBdef2,
    PmxBdef4,
    PmxBone,
    PmxIk,
    PmxIkLink,
    PmxQdef,
    PmxSdef,
    PmxVertex,
)
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind


class PmxBoneReferenceRemapError(ValueError):
    """Raised when CP12 remapping would create a dangling bone reference."""


def _require_bone_transform(transform: PmxCollectionTransform) -> PmxCollectionTransform:
    if not isinstance(transform, PmxCollectionTransform):
        raise TypeError("bone_transform must be a PmxCollectionTransform value.")
    if transform.kind is not PmxReferenceTargetKind.BONE:
        raise ValueError(
            f"bone_transform kind must be bone, got {transform.kind.value}."
        )
    return transform


def _require_plain_index(value: object, field_name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be an integer.")
    return value


def _remap_optional_bone_index(
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
            f"{field_name}={index} is outside bone old_size {transform.old_size}."
        )

    mapped = transform.remap.target_for(index)
    if mapped is None:
        raise PmxBoneReferenceRemapError(
            f"{field_name} references removed bone index {index}; "
            "removed targets are not converted to the -1 sentinel."
        )
    return mapped


def _remap_required_bone_index(
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
            f"{field_name}={index} is outside bone old_size {transform.old_size}."
        )

    mapped = transform.remap.target_for(index)
    if mapped is None:
        raise PmxBoneReferenceRemapError(
            f"{field_name} references removed bone index {index}."
        )
    return mapped


def _require_pmx_version(pmx_version: object) -> float:
    if type(pmx_version) is not float:
        raise TypeError("pmx_version must be a float.")
    if pmx_version not in (2.0, 2.1):
        raise ValueError("pmx_version must be 2.0 or 2.1.")
    return pmx_version


def _remap_deform(
    deform: object,
    *,
    vertex_index: int,
    pmx_version: float,
    transform: PmxCollectionTransform,
) -> object:
    if isinstance(deform, PmxBdef1):
        mapped = _remap_optional_bone_index(
            deform.bone_index,
            field_name=f"vertices[{vertex_index}].deform.bone_index",
            transform=transform,
        )
        return deform if mapped == deform.bone_index else replace(deform, bone_index=mapped)

    if isinstance(deform, (PmxBdef2, PmxBdef4, PmxSdef, PmxQdef)):
        if isinstance(deform, PmxQdef) and pmx_version != 2.1:
            raise ValueError(
                f"vertices[{vertex_index}].deform QDEF requires PMX 2.1."
            )
        mapped_indices = tuple(
            _remap_optional_bone_index(
                bone_index,
                field_name=(
                    f"vertices[{vertex_index}].deform.bone_indices[{position}]"
                ),
                transform=transform,
            )
            for position, bone_index in enumerate(deform.bone_indices)
        )
        return (
            deform
            if mapped_indices == deform.bone_indices
            else replace(deform, bone_indices=mapped_indices)
        )

    raise TypeError(
        f"vertices[{vertex_index}].deform must be a supported PMX deform record."
    )


def remap_vertex_deform_bone_references(
    vertices: tuple[PmxVertex, ...],
    bone_transform: PmxCollectionTransform,
    *,
    pmx_version: float,
) -> tuple[PmxVertex, ...]:
    """Rewrite CP12-owned vertex-deform bone references without reordering vertices."""

    if type(vertices) is not tuple:
        raise TypeError("vertices must be a tuple.")
    if not all(isinstance(vertex, PmxVertex) for vertex in vertices):
        raise TypeError("vertices must contain only PmxVertex records.")
    transform = _require_bone_transform(bone_transform)
    version = _require_pmx_version(pmx_version)

    rewritten: list[PmxVertex] = []
    changed = False
    for vertex_index, vertex in enumerate(vertices):
        deform = _remap_deform(
            vertex.deform,
            vertex_index=vertex_index,
            pmx_version=version,
            transform=transform,
        )
        if deform is vertex.deform:
            rewritten.append(vertex)
            continue
        rewritten.append(replace(vertex, deform=deform))
        changed = True

    if not changed:
        return vertices
    return tuple(rewritten)


def _remap_active_ik(
    ik: PmxIk,
    *,
    source_bone_index: int,
    transform: PmxCollectionTransform,
) -> PmxIk:
    target_bone_index = _remap_required_bone_index(
        ik.target_bone_index,
        field_name=f"bones[{source_bone_index}].ik.target_bone_index",
        transform=transform,
    )

    links: list[PmxIkLink] = []
    links_changed = False
    for link_index, link in enumerate(ik.links):
        bone_index = _remap_required_bone_index(
            link.bone_index,
            field_name=(
                f"bones[{source_bone_index}].ik.links[{link_index}].bone_index"
            ),
            transform=transform,
        )
        if bone_index == link.bone_index:
            links.append(link)
            continue
        links.append(replace(link, bone_index=bone_index))
        links_changed = True

    if target_bone_index == ik.target_bone_index and not links_changed:
        return ik
    return replace(
        ik,
        target_bone_index=target_bone_index,
        links=tuple(links) if links_changed else ik.links,
    )


def _remap_surviving_bone(
    bone: PmxBone,
    *,
    source_bone_index: int,
    transform: PmxCollectionTransform,
) -> PmxBone:
    parent_bone_index = _remap_optional_bone_index(
        bone.parent_bone_index,
        field_name=f"bones[{source_bone_index}].parent_bone_index",
        transform=transform,
    )

    tail_bone_index = bone.tail_bone_index
    tail_uses_index = bool(bone.flags & PMX_BONE_FLAG_TAIL_INDEX)
    if tail_uses_index:
        if bone.tail_mode != "bone" or tail_bone_index is None:
            raise ValueError(
                f"bones[{source_bone_index}] tail-index flag requires a bone tail reference."
            )
        if bone.tail_offset is not None:
            raise ValueError(
                f"bones[{source_bone_index}] tail-index flag cannot retain a tail offset."
            )
        tail_bone_index = _remap_optional_bone_index(
            tail_bone_index,
            field_name=f"bones[{source_bone_index}].tail_bone_index",
            transform=transform,
        )
    else:
        if bone.tail_mode != "offset" or bone.tail_offset is None:
            raise ValueError(
                f"bones[{source_bone_index}] offset-tail mode requires a tail vector."
            )
        if tail_bone_index is not None:
            raise ValueError(
                f"bones[{source_bone_index}] offset-tail mode cannot retain a bone reference."
            )

    inherit_mask = PMX_BONE_FLAG_INHERIT_ROTATION | PMX_BONE_FLAG_INHERIT_TRANSLATION
    inherit_parent_bone_index = bone.inherit_parent_bone_index
    has_inherit = bool(bone.flags & inherit_mask)
    if has_inherit:
        if inherit_parent_bone_index is None or bone.inherit_weight is None:
            raise ValueError(
                f"bones[{source_bone_index}] inherit flags require parent index and weight."
            )
        inherit_parent_bone_index = _remap_optional_bone_index(
            inherit_parent_bone_index,
            field_name=f"bones[{source_bone_index}].inherit_parent_bone_index",
            transform=transform,
        )
    elif inherit_parent_bone_index is not None or bone.inherit_weight is not None:
        raise ValueError(
            f"bones[{source_bone_index}] inherit payload requires an inherit flag."
        )

    ik = bone.ik
    has_ik = bool(bone.flags & PMX_BONE_FLAG_IK)
    if has_ik:
        if ik is None:
            raise ValueError(f"bones[{source_bone_index}] IK flag requires IK payload.")
        ik = _remap_active_ik(
            ik,
            source_bone_index=source_bone_index,
            transform=transform,
        )
    elif ik is not None:
        raise ValueError(
            f"bones[{source_bone_index}] IK payload requires the IK flag."
        )

    if (
        parent_bone_index == bone.parent_bone_index
        and tail_bone_index == bone.tail_bone_index
        and inherit_parent_bone_index == bone.inherit_parent_bone_index
        and ik is bone.ik
    ):
        return bone

    return replace(
        bone,
        parent_bone_index=parent_bone_index,
        tail_bone_index=tail_bone_index,
        inherit_parent_bone_index=inherit_parent_bone_index,
        ik=ik,
    )


def transform_bone_collection_references(
    bones: tuple[PmxBone, ...],
    bone_transform: PmxCollectionTransform,
) -> tuple[PmxBone, ...]:
    """Return surviving bones in new order with all CP12-owned refs rewritten."""

    if type(bones) is not tuple:
        raise TypeError("bones must be a tuple.")
    if not all(isinstance(bone, PmxBone) for bone in bones):
        raise TypeError("bones must contain only PmxBone records.")
    transform = _require_bone_transform(bone_transform)
    if transform.old_size != len(bones):
        raise ValueError("bone_transform old_size must match the bone collection size.")

    rewritten: list[PmxBone] = []
    changed = not transform.is_noop
    for old_bone_index in transform.old_indices_in_new_order:
        bone = bones[old_bone_index]
        remapped = _remap_surviving_bone(
            bone,
            source_bone_index=old_bone_index,
            transform=transform,
        )
        rewritten.append(remapped)
        changed = changed or remapped is not bone

    if not changed:
        return bones
    return tuple(rewritten)
