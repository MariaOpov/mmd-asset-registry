"""CP11 section-aware geometry/material structural remapping kernels.

This module is intentionally internal.  It consumes the immutable CP09/CP10
mapping models and rewrites only relationships owned by CP11:

* surface indices -> vertex
* material main texture -> texture
* material sphere texture -> texture
* material individual toon texture -> texture

Material collection transforms are coordinated with the contiguous surface
segments currently owned by each material.  No PmxDocument orchestration,
serialization, public mutation API, or cross-section bone/morph/physics remap
is performed here.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from mmd_registry.pmx.collection_transform import PmxCollectionTransform
from mmd_registry.pmx.document import PmxMaterial
from mmd_registry.pmx.index_remap import PmxIndexRemap
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.pmx.structural_reference_shift import (
    PmxCollectionReferenceShiftPlan,
)


class PmxReferenceRemapError(ValueError):
    """Raised when a structural remap would create a dangling CP11 reference."""


def _require_collection_transform(
    transform: PmxCollectionTransform,
    expected_kind: PmxReferenceTargetKind,
) -> PmxCollectionTransform:
    if not isinstance(transform, PmxCollectionTransform):
        raise TypeError("transform must be a PmxCollectionTransform value.")
    if transform.kind is not expected_kind:
        raise ValueError(
            f"transform kind must be {expected_kind.value}, got {transform.kind.value}."
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
        raise PmxReferenceRemapError(
            f"{field_name} references removed {transform.kind.value} index {index}."
        )
    return mapped


def _remap_optional_index_from_remap(
    value: object,
    *,
    field_name: str,
    remap: PmxIndexRemap,
    target_kind: PmxReferenceTargetKind,
) -> int:
    if not isinstance(remap, PmxIndexRemap):
        raise TypeError("remap must be a PmxIndexRemap value.")
    if not isinstance(target_kind, PmxReferenceTargetKind):
        raise TypeError("target_kind must be a PmxReferenceTargetKind value.")

    index = _require_plain_index(value, field_name)
    if index == -1:
        return -1
    if index < -1:
        raise ValueError(f"{field_name} cannot be smaller than -1.")
    if index >= remap.old_size:
        raise ValueError(
            f"{field_name}={index} is outside {target_kind.value} "
            f"old_size {remap.old_size}."
        )

    mapped = remap.target_for(index)
    if mapped is None:
        raise PmxReferenceRemapError(
            f"{field_name} references removed {target_kind.value} index {index}; "
            "removed targets are not converted to the -1 sentinel."
        )
    return mapped


def remap_surface_vertex_references(
    surface_indices: tuple[int, ...],
    vertex_transform: PmxCollectionTransform,
) -> tuple[int, ...]:
    """Return surface indices rewritten through one vertex collection transform."""

    if type(surface_indices) is not tuple:
        raise TypeError("surface_indices must be a tuple.")
    _require_collection_transform(
        vertex_transform,
        PmxReferenceTargetKind.VERTEX,
    )
    if len(surface_indices) % 3 != 0:
        raise ValueError("surface index count must be divisible by 3.")

    rewritten: list[int] = []
    changed = False
    for position, vertex_index in enumerate(surface_indices):
        mapped = _remap_required_index(
            vertex_index,
            field_name=f"surface_indices[{position}]",
            transform=vertex_transform,
        )
        rewritten.append(mapped)
        changed = changed or mapped != vertex_index

    if not changed:
        return surface_indices
    return tuple(rewritten)


def remap_surface_vertex_references_for_insertion(
    surface_indices: tuple[int, ...],
    vertex_shift: PmxCollectionReferenceShiftPlan,
) -> tuple[int, ...]:
    """Rewrite surface vertex refs through additive vertex insertion evidence."""

    if type(surface_indices) is not tuple:
        raise TypeError("surface_indices must be a tuple.")
    if not isinstance(vertex_shift, PmxCollectionReferenceShiftPlan):
        raise TypeError(
            "vertex_shift must be a PmxCollectionReferenceShiftPlan value."
        )
    if vertex_shift.target_kind is not PmxReferenceTargetKind.VERTEX:
        raise ValueError("vertex_shift target_kind must be vertex.")
    if len(surface_indices) % 3 != 0:
        raise ValueError("surface index count must be divisible by 3.")

    rewritten: list[int] = []
    changed = False
    for position, vertex_index in enumerate(surface_indices):
        index = _require_plain_index(
            vertex_index,
            f"surface_indices[{position}]",
        )
        if index < 0:
            raise ValueError(f"surface_indices[{position}] cannot be negative.")
        if index >= vertex_shift.current_count:
            raise ValueError(
                f"surface_indices[{position}]={index} is outside vertex old_size "
                f"{vertex_shift.current_count}."
            )
        mapped = vertex_shift.remap.target_for(index)
        if mapped is None:
            raise PmxReferenceRemapError(
                f"surface_indices[{position}] references removed vertex index "
                f"{index}; insertion shifts cannot remove source records."
            )
        rewritten.append(mapped)
        changed = changed or mapped != index

    if not changed:
        return surface_indices
    return tuple(rewritten)


def _remap_material_texture_references_from_remap(
    materials: tuple[PmxMaterial, ...],
    texture_remap: PmxIndexRemap,
) -> tuple[PmxMaterial, ...]:
    """Rewrite material texture references through one validated texture remap."""

    if type(materials) is not tuple:
        raise TypeError("materials must be a tuple.")
    if not all(isinstance(material, PmxMaterial) for material in materials):
        raise TypeError("materials must contain only PmxMaterial records.")
    if not isinstance(texture_remap, PmxIndexRemap):
        raise TypeError("texture_remap must be a PmxIndexRemap value.")

    rewritten: list[PmxMaterial] = []
    changed = False

    for material_index, material in enumerate(materials):
        texture_index = _remap_optional_index_from_remap(
            material.texture_index,
            field_name=f"materials[{material_index}].texture_index",
            remap=texture_remap,
            target_kind=PmxReferenceTargetKind.TEXTURE,
        )
        sphere_texture_index = _remap_optional_index_from_remap(
            material.sphere_texture_index,
            field_name=f"materials[{material_index}].sphere_texture_index",
            remap=texture_remap,
            target_kind=PmxReferenceTargetKind.TEXTURE,
        )

        toon_reference_index = material.toon_reference_index
        if material.toon_reference_mode == "texture":
            toon_reference_index = _remap_optional_index_from_remap(
                material.toon_reference_index,
                field_name=f"materials[{material_index}].toon_reference_index",
                remap=texture_remap,
                target_kind=PmxReferenceTargetKind.TEXTURE,
            )
        elif material.toon_reference_mode != "shared":
            raise ValueError(
                f"materials[{material_index}].toon_reference_mode must be "
                "either 'texture' or 'shared'."
            )

        if (
            texture_index == material.texture_index
            and sphere_texture_index == material.sphere_texture_index
            and toon_reference_index == material.toon_reference_index
        ):
            rewritten.append(material)
            continue

        rewritten.append(
            replace(
                material,
                texture_index=texture_index,
                sphere_texture_index=sphere_texture_index,
                toon_reference_index=toon_reference_index,
            )
        )
        changed = True

    if not changed:
        return materials
    return tuple(rewritten)


def remap_material_texture_references(
    materials: tuple[PmxMaterial, ...],
    texture_transform: PmxCollectionTransform,
) -> tuple[PmxMaterial, ...]:
    """Rewrite CP11-owned material texture references through a legacy transform."""

    _require_collection_transform(
        texture_transform,
        PmxReferenceTargetKind.TEXTURE,
    )
    return _remap_material_texture_references_from_remap(
        materials,
        texture_transform.remap,
    )


def remap_material_texture_references_for_insertion(
    materials: tuple[PmxMaterial, ...],
    texture_shift: PmxCollectionReferenceShiftPlan,
) -> tuple[PmxMaterial, ...]:
    """Rewrite material texture references through insertion shift evidence."""

    if not isinstance(texture_shift, PmxCollectionReferenceShiftPlan):
        raise TypeError(
            "texture_shift must be a PmxCollectionReferenceShiftPlan value."
        )
    if texture_shift.target_kind is not PmxReferenceTargetKind.TEXTURE:
        raise ValueError("texture_shift target_kind must be texture.")

    return _remap_material_texture_references_from_remap(
        materials,
        texture_shift.remap,
    )


@dataclass(frozen=True, slots=True)
class PmxMaterialSurfacePartitionTransform:
    """Explicitly move/delete each material together with its owned surface segment.

    The CP10 material remap remains the sole mapping authority.  This wrapper
    adds only the CP11 section semantic that a material's current contiguous
    surface segment travels with that material when it is reordered and is
    removed with it when it is deleted.
    """

    material_transform: PmxCollectionTransform

    def __post_init__(self) -> None:
        _require_collection_transform(
            self.material_transform,
            PmxReferenceTargetKind.MATERIAL,
        )


@dataclass(frozen=True, slots=True)
class PmxMaterialSurfacePartitionResult:
    """Immutable result of one material/surface partition transform."""

    materials: tuple[PmxMaterial, ...]
    surface_indices: tuple[int, ...]

    def __post_init__(self) -> None:
        if type(self.materials) is not tuple:
            raise TypeError("materials must be a tuple.")
        if not all(isinstance(material, PmxMaterial) for material in self.materials):
            raise TypeError("materials must contain only PmxMaterial records.")
        if type(self.surface_indices) is not tuple:
            raise TypeError("surface_indices must be a tuple.")


def transform_material_surface_partition(
    materials: tuple[PmxMaterial, ...],
    surface_indices: tuple[int, ...],
    proposal: PmxMaterialSurfacePartitionTransform,
) -> PmxMaterialSurfacePartitionResult:
    """Apply an explicit material transform to materials and owned surface segments."""

    if type(materials) is not tuple:
        raise TypeError("materials must be a tuple.")
    if not all(isinstance(material, PmxMaterial) for material in materials):
        raise TypeError("materials must contain only PmxMaterial records.")
    if type(surface_indices) is not tuple:
        raise TypeError("surface_indices must be a tuple.")
    for position, vertex_index in enumerate(surface_indices):
        index = _require_plain_index(
            vertex_index,
            f"surface_indices[{position}]",
        )
        if index < 0:
            raise ValueError(f"surface_indices[{position}] cannot be negative.")
    if len(surface_indices) % 3 != 0:
        raise ValueError("surface index count must be divisible by 3.")
    if not isinstance(proposal, PmxMaterialSurfacePartitionTransform):
        raise TypeError(
            "proposal must be a PmxMaterialSurfacePartitionTransform value."
        )

    transform = proposal.material_transform
    if transform.old_size != len(materials):
        raise ValueError(
            "material transform old_size must match the material collection size."
        )

    segments: list[tuple[int, ...]] = []
    offset = 0
    for material_index, material in enumerate(materials):
        count = material.surface_index_count
        end = offset + count
        if end > len(surface_indices):
            raise ValueError(
                f"materials[{material_index}] surface segment exceeds the "
                "surface index stream."
            )
        segments.append(surface_indices[offset:end])
        offset = end

    if offset != len(surface_indices):
        raise ValueError(
            f"materials cover {offset} surface indices but geometry contains "
            f"{len(surface_indices)}."
        )

    old_indices_in_new_order = transform.old_indices_in_new_order
    new_materials = tuple(materials[index] for index in old_indices_in_new_order)

    rewritten_surface_indices: list[int] = []
    for old_material_index in old_indices_in_new_order:
        rewritten_surface_indices.extend(segments[old_material_index])

    new_surface_indices = tuple(rewritten_surface_indices)

    if transform.is_noop:
        new_materials = materials
        new_surface_indices = surface_indices

    expected_surface_count = sum(
        material.surface_index_count for material in new_materials
    )
    if expected_surface_count != len(new_surface_indices):
        raise AssertionError(
            "material/surface partition transform produced inconsistent coverage."
        )

    return PmxMaterialSurfacePartitionResult(
        materials=new_materials,
        surface_indices=new_surface_indices,
    )
