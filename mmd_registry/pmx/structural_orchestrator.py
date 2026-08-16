"""CP15 deterministic document-level structural transform orchestration.

This module coordinates the internal CP09-CP14 structural primitives across one
immutable ``PmxDocument``.  It does not define new relationship ownership,
serialize bytes, resize PMX index widths, perform full PMX validation, expose a
public mutation service, or repair dangling references.

Key ordering rules:

* material-owned surface segments are deleted/reordered before surviving
  surface references are remapped through the vertex transform;
* deleted vertex sources are removed before vertex-deform bone references are
  remapped;
* deleted morph sources are removed by CP13 before CP14 rewrites surviving
  impulse-morph rigid-body references;
* deleted rigid-body sources are removed inside the CP14 collection kernel;
* every relationship is remapped from the original old-index domain exactly
  once.

Absent target transforms are explicit identity transforms over the source
document's current collection sizes.  A non-noop structural transform fails
closed when ``PmxDocument.trailing_data`` is non-empty because those opaque
bytes may contain unreviewed references.  ``header.extra_global_data`` remains
opaque header data and is preserved unchanged.
"""

from __future__ import annotations

from dataclasses import replace

from mmd_registry.pmx.bone_reference_remap import (
    remap_vertex_deform_bone_references,
    transform_bone_collection_references,
)
from mmd_registry.pmx.collection_transform import (
    PmxCollectionTransform,
    PmxStructuralTransformIntent,
)
from mmd_registry.pmx.document import PmxDocument, PmxGeometry
from mmd_registry.pmx.geometry_material_remap import (
    PmxMaterialSurfacePartitionTransform,
    remap_material_texture_references,
    remap_surface_vertex_references,
    transform_material_surface_partition,
)
from mmd_registry.pmx.morph_display_remap import (
    remap_display_frame_references,
    transform_morph_collection_references,
)
from mmd_registry.pmx.physics_reference_remap import (
    remap_impulse_morph_rigid_body_references,
    remap_joint_rigid_body_references,
    remap_soft_body_references,
    transform_rigid_body_collection_references,
)
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind


class PmxStructuralTransformError(ValueError):
    """Raised when one coordinated document transform is unsafe to execute."""


def _target_collection_size(
    document: PmxDocument,
    kind: PmxReferenceTargetKind,
) -> int:
    if kind is PmxReferenceTargetKind.VERTEX:
        return len(document.vertices)
    if kind is PmxReferenceTargetKind.TEXTURE:
        return len(document.texture_paths)
    if kind is PmxReferenceTargetKind.MATERIAL:
        return len(document.materials)
    if kind is PmxReferenceTargetKind.BONE:
        return len(document.bones)
    if kind is PmxReferenceTargetKind.MORPH:
        return len(document.morphs)
    if kind is PmxReferenceTargetKind.RIGID_BODY:
        return len(document.rigid_bodies)
    raise AssertionError(f"unhandled target kind {kind!r}")


def _resolve_transforms(
    document: PmxDocument,
    intent: PmxStructuralTransformIntent,
) -> dict[PmxReferenceTargetKind, PmxCollectionTransform]:
    resolved: dict[PmxReferenceTargetKind, PmxCollectionTransform] = {}
    for kind in PmxReferenceTargetKind:
        old_size = _target_collection_size(document, kind)
        transform = intent.transform_for(kind)
        if transform is None:
            transform = PmxCollectionTransform.identity(kind, old_size)
        elif transform.old_size != old_size:
            raise PmxStructuralTransformError(
                f"{kind.value} transform old_size {transform.old_size} does not "
                f"match source collection size {old_size}."
            )
        resolved[kind] = transform
    return resolved


def _surviving_records(
    records: tuple[object, ...],
    transform: PmxCollectionTransform,
) -> tuple[object, ...]:
    if transform.is_noop:
        return records
    return tuple(records[index] for index in transform.old_indices_in_new_order)


def _require_output_size(
    values: tuple[object, ...],
    transform: PmxCollectionTransform,
) -> None:
    if len(values) != transform.new_size:
        raise AssertionError(
            f"{transform.kind.value} transform produced {len(values)} records; "
            f"expected {transform.new_size}."
        )


def transform_pmx_document(
    document: PmxDocument,
    intent: PmxStructuralTransformIntent,
) -> PmxDocument:
    """Apply one coordinated internal structural transform immutably.

    Full semantic PMX validation remains the responsibility of the existing
    validator and the later CP16 complete invariant gate.
    """

    if not isinstance(document, PmxDocument):
        raise TypeError("document must be a PmxDocument instance.")
    if not isinstance(intent, PmxStructuralTransformIntent):
        raise TypeError("intent must be a PmxStructuralTransformIntent value.")

    transforms = _resolve_transforms(document, intent)

    if intent.is_noop:
        return document

    if document.trailing_data:
        raise PmxStructuralTransformError(
            "structural transforms are not allowed while trailing_data is "
            "non-empty because its reference semantics are opaque."
        )

    vertex_transform = transforms[PmxReferenceTargetKind.VERTEX]
    texture_transform = transforms[PmxReferenceTargetKind.TEXTURE]
    material_transform = transforms[PmxReferenceTargetKind.MATERIAL]
    bone_transform = transforms[PmxReferenceTargetKind.BONE]
    morph_transform = transforms[PmxReferenceTargetKind.MORPH]
    rigid_body_transform = transforms[PmxReferenceTargetKind.RIGID_BODY]

    # CP11: remove/reorder material-owned surface segments first so references
    # from deleted material sources cannot create false vertex-remap failures.
    partition = transform_material_surface_partition(
        document.materials,
        document.surface_indices,
        PmxMaterialSurfacePartitionTransform(material_transform),
    )
    surface_indices = remap_surface_vertex_references(
        partition.surface_indices,
        vertex_transform,
    )
    materials = remap_material_texture_references(
        partition.materials,
        texture_transform,
    )

    # Delete/reorder vertex sources before CP12 rewrites their outgoing bone refs.
    surviving_vertices = _surviving_records(
        document.vertices,
        vertex_transform,
    )
    vertices = remap_vertex_deform_bone_references(
        surviving_vertices,
        bone_transform,
        pmx_version=document.header.version,
    )

    texture_paths = tuple(
        document.texture_paths[index]
        for index in texture_transform.old_indices_in_new_order
    )

    bones = transform_bone_collection_references(
        document.bones,
        bone_transform,
    )

    # CP13 owns morph source deletion/reorder and all non-impulse morph refs.
    morphs = transform_morph_collection_references(
        document.morphs,
        morph_transform,
        vertex_transform,
        bone_transform,
        material_transform,
        pmx_version=document.header.version,
        additional_uv_count=document.header.additional_uv_count,
    )

    # CP14 must receive only surviving CP13 morph sources.
    morphs = remap_impulse_morph_rigid_body_references(
        morphs,
        rigid_body_transform,
        pmx_version=document.header.version,
    )

    display_frames = remap_display_frame_references(
        document.display_frames,
        bone_transform,
        morph_transform,
    )

    rigid_bodies = transform_rigid_body_collection_references(
        document.rigid_bodies,
        rigid_body_transform,
        bone_transform,
    )

    joints = remap_joint_rigid_body_references(
        document.joints,
        rigid_body_transform,
        pmx_version=document.header.version,
    )

    soft_bodies = remap_soft_body_references(
        document.soft_bodies,
        material_transform,
        rigid_body_transform,
        vertex_transform,
        pmx_version=document.header.version,
    )

    _require_output_size(vertices, vertex_transform)
    _require_output_size(texture_paths, texture_transform)
    _require_output_size(materials, material_transform)
    _require_output_size(bones, bone_transform)
    _require_output_size(morphs, morph_transform)
    _require_output_size(rigid_bodies, rigid_body_transform)

    geometry = (
        document.geometry
        if vertices is document.vertices and surface_indices is document.surface_indices
        else replace(
            document.geometry,
            vertices=vertices,
            surface_indices=surface_indices,
        )
    )
    if not isinstance(geometry, PmxGeometry):
        raise AssertionError("geometry rebuild did not produce a PmxGeometry value.")

    return replace(
        document,
        geometry=geometry,
        texture_paths=texture_paths,
        materials=materials,
        bones=bones,
        morphs=morphs,
        display_frames=display_frames,
        rigid_bodies=rigid_bodies,
        joints=joints,
        soft_bodies=soft_bodies,
    )
