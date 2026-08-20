"""CP13 morph/display-frame structural reference remapping kernels.

This module is intentionally internal. It rewrites only relationships owned by
CP13:

* group morph -> morph
* vertex morph -> vertex
* bone morph -> bone
* UV morph -> vertex
* material morph -> material
* flip morph -> morph
* display-frame element -> bone or morph

Impulse morph -> rigid body remains CP14-owned and is validated/preserved here
without rewriting its rigid-body reference. No PmxDocument orchestration,
serialization, public mutation API, or automatic repair policy is performed.
"""

from __future__ import annotations

from dataclasses import replace

from mmd_registry.pmx.collection_transform import PmxCollectionTransform
from mmd_registry.pmx.document import (
    PmxBoneMorphOffset,
    PmxDisplayFrame,
    PmxDisplayFrameElement,
    PmxFlipMorphOffset,
    PmxGroupMorphOffset,
    PmxImpulseMorphOffset,
    PmxMaterialMorphOffset,
    PmxMorph,
    PmxUvMorphOffset,
    PmxVertexMorphOffset,
)
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.pmx.structural_reference_shift import (
    PmxCollectionReferenceShiftPlan,
)


class PmxMorphDisplayRemapError(ValueError):
    """Raised when CP13 remapping would create a dangling reference."""


def _require_transform(
    transform: PmxCollectionTransform,
    expected_kind: PmxReferenceTargetKind,
    field_name: str,
) -> PmxCollectionTransform:
    if not isinstance(transform, PmxCollectionTransform):
        raise TypeError(f"{field_name} must be a PmxCollectionTransform value.")
    if transform.kind is not expected_kind:
        raise ValueError(
            f"{field_name} kind must be {expected_kind.value}, got {transform.kind.value}."
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
        raise PmxMorphDisplayRemapError(
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
        raise PmxMorphDisplayRemapError(
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


def _require_additional_uv_count(additional_uv_count: object) -> int:
    if type(additional_uv_count) is not int:
        raise TypeError("additional_uv_count must be an integer.")
    if not 0 <= additional_uv_count <= 4:
        raise ValueError("additional_uv_count must be a value from 0 through 4.")
    return additional_uv_count


_EXPECTED_OFFSET_TYPES: tuple[type[object], ...] = (
    PmxGroupMorphOffset,
    PmxVertexMorphOffset,
    PmxBoneMorphOffset,
    PmxUvMorphOffset,
    PmxUvMorphOffset,
    PmxUvMorphOffset,
    PmxUvMorphOffset,
    PmxUvMorphOffset,
    PmxMaterialMorphOffset,
    PmxFlipMorphOffset,
    PmxImpulseMorphOffset,
)


def _remap_morph_offset(
    morph: PmxMorph,
    offset: object,
    *,
    source_morph_index: int,
    offset_index: int,
    morph_transform: PmxCollectionTransform,
    vertex_transform: PmxCollectionTransform,
    bone_transform: PmxCollectionTransform,
    material_transform: PmxCollectionTransform,
) -> object:
    field_prefix = f"morphs[{source_morph_index}].offsets[{offset_index}]"

    if isinstance(offset, (PmxGroupMorphOffset, PmxFlipMorphOffset)):
        mapped = _remap_required_index(
            offset.morph_index,
            field_name=f"{field_prefix}.morph_index",
            transform=morph_transform,
        )
        return offset if mapped == offset.morph_index else replace(offset, morph_index=mapped)

    if isinstance(offset, (PmxVertexMorphOffset, PmxUvMorphOffset)):
        mapped = _remap_required_index(
            offset.vertex_index,
            field_name=f"{field_prefix}.vertex_index",
            transform=vertex_transform,
        )
        return offset if mapped == offset.vertex_index else replace(offset, vertex_index=mapped)

    if isinstance(offset, PmxBoneMorphOffset):
        mapped = _remap_required_index(
            offset.bone_index,
            field_name=f"{field_prefix}.bone_index",
            transform=bone_transform,
        )
        return offset if mapped == offset.bone_index else replace(offset, bone_index=mapped)

    if isinstance(offset, PmxMaterialMorphOffset):
        mapped = _remap_optional_index(
            offset.material_index,
            field_name=f"{field_prefix}.material_index",
            transform=material_transform,
        )
        return (
            offset
            if mapped == offset.material_index
            else replace(offset, material_index=mapped)
        )

    if isinstance(offset, PmxImpulseMorphOffset):
        return offset

    raise TypeError(f"{field_prefix} must be a supported PMX morph offset.")


def _remap_surviving_morph(
    morph: PmxMorph,
    *,
    source_morph_index: int,
    pmx_version: float,
    additional_uv_count: int,
    morph_transform: PmxCollectionTransform,
    vertex_transform: PmxCollectionTransform,
    bone_transform: PmxCollectionTransform,
    material_transform: PmxCollectionTransform,
) -> PmxMorph:
    if not 0 <= morph.morph_type < len(_EXPECTED_OFFSET_TYPES):
        raise ValueError(
            f"morphs[{source_morph_index}].morph_type must be a value from 0 through 10."
        )
    if morph.morph_type in (9, 10) and pmx_version != 2.1:
        raise ValueError(
            f"morphs[{source_morph_index}] type {morph.morph_type} requires PMX 2.1."
        )
    if 4 <= morph.morph_type <= 7:
        required_layer = morph.morph_type - 3
        if additional_uv_count < required_layer:
            raise ValueError(
                f"morphs[{source_morph_index}] type {morph.morph_type} requires "
                f"additional UV layer {required_layer}."
            )

    expected_type = _EXPECTED_OFFSET_TYPES[morph.morph_type]
    rewritten: list[object] = []
    changed = False
    for offset_index, offset in enumerate(morph.offsets):
        if not isinstance(offset, expected_type):
            raise ValueError(
                f"morphs[{source_morph_index}].offsets[{offset_index}] type "
                f"{morph.morph_type} requires {expected_type.__name__}."
            )
        remapped = _remap_morph_offset(
            morph,
            offset,
            source_morph_index=source_morph_index,
            offset_index=offset_index,
            morph_transform=morph_transform,
            vertex_transform=vertex_transform,
            bone_transform=bone_transform,
            material_transform=material_transform,
        )
        rewritten.append(remapped)
        changed = changed or remapped is not offset

    if not changed:
        return morph
    return replace(morph, offsets=tuple(rewritten))


def transform_morph_collection_references(
    morphs: tuple[PmxMorph, ...],
    morph_transform: PmxCollectionTransform,
    vertex_transform: PmxCollectionTransform,
    bone_transform: PmxCollectionTransform,
    material_transform: PmxCollectionTransform,
    *,
    pmx_version: float,
    additional_uv_count: int,
) -> tuple[PmxMorph, ...]:
    """Return surviving morphs in new order with CP13-owned refs rewritten."""

    if type(morphs) is not tuple:
        raise TypeError("morphs must be a tuple.")
    if not all(isinstance(morph, PmxMorph) for morph in morphs):
        raise TypeError("morphs must contain only PmxMorph records.")

    morph_transform = _require_transform(
        morph_transform, PmxReferenceTargetKind.MORPH, "morph_transform"
    )
    vertex_transform = _require_transform(
        vertex_transform, PmxReferenceTargetKind.VERTEX, "vertex_transform"
    )
    bone_transform = _require_transform(
        bone_transform, PmxReferenceTargetKind.BONE, "bone_transform"
    )
    material_transform = _require_transform(
        material_transform, PmxReferenceTargetKind.MATERIAL, "material_transform"
    )
    version = _require_pmx_version(pmx_version)
    uv_count = _require_additional_uv_count(additional_uv_count)

    if morph_transform.old_size != len(morphs):
        raise ValueError("morph_transform old_size must match the morph collection size.")

    rewritten: list[PmxMorph] = []
    changed = not morph_transform.is_noop
    for old_morph_index in morph_transform.old_indices_in_new_order:
        morph = morphs[old_morph_index]
        remapped = _remap_surviving_morph(
            morph,
            source_morph_index=old_morph_index,
            pmx_version=version,
            additional_uv_count=uv_count,
            morph_transform=morph_transform,
            vertex_transform=vertex_transform,
            bone_transform=bone_transform,
            material_transform=material_transform,
        )
        rewritten.append(remapped)
        changed = changed or remapped is not morph

    if not changed:
        return morphs
    return tuple(rewritten)


def remap_material_morph_references_for_insertion(
    morphs: tuple[PmxMorph, ...],
    material_shift: PmxCollectionReferenceShiftPlan,
    *,
    pmx_version: float,
    additional_uv_count: int,
) -> tuple[PmxMorph, ...]:
    """Rewrite CP13-owned material-morph references through insertion evidence.

    The material collection itself is materialized by the target-specific
    insertion layer. This adapter owns only existing morph -> material
    references and deliberately does not construct ``PmxCollectionTransform``.
    """

    if type(morphs) is not tuple:
        raise TypeError("morphs must be a tuple.")
    if not all(isinstance(morph, PmxMorph) for morph in morphs):
        raise TypeError("morphs must contain only PmxMorph records.")
    if not isinstance(material_shift, PmxCollectionReferenceShiftPlan):
        raise TypeError(
            "material_shift must be a PmxCollectionReferenceShiftPlan value."
        )
    if material_shift.target_kind is not PmxReferenceTargetKind.MATERIAL:
        raise ValueError("material_shift target_kind must be material.")

    version = _require_pmx_version(pmx_version)
    uv_count = _require_additional_uv_count(additional_uv_count)
    rewritten_morphs: list[PmxMorph] = []
    changed = False

    for morph_index, morph in enumerate(morphs):
        if not 0 <= morph.morph_type < len(_EXPECTED_OFFSET_TYPES):
            raise ValueError(
                f"morphs[{morph_index}].morph_type must be a value from 0 through 10."
            )
        if morph.morph_type in (9, 10) and version != 2.1:
            raise ValueError(
                f"morphs[{morph_index}] type {morph.morph_type} requires PMX 2.1."
            )
        if 4 <= morph.morph_type <= 7:
            required_layer = morph.morph_type - 3
            if uv_count < required_layer:
                raise ValueError(
                    f"morphs[{morph_index}] type {morph.morph_type} requires "
                    f"additional UV layer {required_layer}."
                )

        expected_type = _EXPECTED_OFFSET_TYPES[morph.morph_type]
        rewritten_offsets: list[object] = []
        morph_changed = False

        for offset_index, offset in enumerate(morph.offsets):
            if not isinstance(offset, expected_type):
                raise ValueError(
                    f"morphs[{morph_index}].offsets[{offset_index}] type "
                    f"{morph.morph_type} requires {expected_type.__name__}."
                )

            if not isinstance(offset, PmxMaterialMorphOffset):
                rewritten_offsets.append(offset)
                continue

            field_name = (
                f"morphs[{morph_index}].offsets[{offset_index}].material_index"
            )
            material_index = _require_plain_index(offset.material_index, field_name)
            if material_index == -1:
                rewritten_offsets.append(offset)
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
                raise PmxMorphDisplayRemapError(
                    f"{field_name} references removed material index {material_index}; "
                    "removed targets are not converted to the -1 sentinel."
                )
            if mapped == material_index:
                rewritten_offsets.append(offset)
                continue

            rewritten_offsets.append(replace(offset, material_index=mapped))
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


def remap_display_frame_references(
    display_frames: tuple[PmxDisplayFrame, ...],
    bone_transform: PmxCollectionTransform,
    morph_transform: PmxCollectionTransform,
) -> tuple[PmxDisplayFrame, ...]:
    """Rewrite required bone/morph references in ordered display frames."""

    if type(display_frames) is not tuple:
        raise TypeError("display_frames must be a tuple.")
    if not all(isinstance(frame, PmxDisplayFrame) for frame in display_frames):
        raise TypeError("display_frames must contain only PmxDisplayFrame records.")

    bone_transform = _require_transform(
        bone_transform, PmxReferenceTargetKind.BONE, "bone_transform"
    )
    morph_transform = _require_transform(
        morph_transform, PmxReferenceTargetKind.MORPH, "morph_transform"
    )

    rewritten_frames: list[PmxDisplayFrame] = []
    changed = False
    for frame_index, frame in enumerate(display_frames):
        rewritten_elements: list[PmxDisplayFrameElement] = []
        frame_changed = False
        for element_index, element in enumerate(frame.elements):
            if not isinstance(element, PmxDisplayFrameElement):
                raise TypeError(
                    f"display_frames[{frame_index}].elements[{element_index}] "
                    "must be a PmxDisplayFrameElement record."
                )
            if element.target_type == "bone":
                transform = bone_transform
            elif element.target_type == "morph":
                transform = morph_transform
            else:
                raise ValueError(
                    f"display_frames[{frame_index}].elements[{element_index}]."
                    "target_type must be either 'bone' or 'morph'."
                )

            target_index = _remap_required_index(
                element.target_index,
                field_name=(
                    f"display_frames[{frame_index}].elements[{element_index}].target_index"
                ),
                transform=transform,
            )
            if target_index == element.target_index:
                rewritten_elements.append(element)
                continue
            rewritten_elements.append(replace(element, target_index=target_index))
            frame_changed = True

        if frame_changed:
            rewritten_frames.append(replace(frame, elements=tuple(rewritten_elements)))
            changed = True
        else:
            rewritten_frames.append(frame)

    if not changed:
        return display_frames
    return tuple(rewritten_frames)


def _require_reference_shift(
    shift: PmxCollectionReferenceShiftPlan,
    expected_kind: PmxReferenceTargetKind,
    field_name: str,
) -> PmxCollectionReferenceShiftPlan:
    if not isinstance(shift, PmxCollectionReferenceShiftPlan):
        raise TypeError(
            f"{field_name} must be a PmxCollectionReferenceShiftPlan value."
        )
    if shift.target_kind is not expected_kind:
        raise ValueError(
            f"{field_name} target_kind must be {expected_kind.value}."
        )
    return shift


def _shift_required_source_index(
    value: object,
    *,
    field_name: str,
    shift: PmxCollectionReferenceShiftPlan,
) -> int:
    index = _require_plain_index(value, field_name)
    if index < 0:
        raise ValueError(f"{field_name} cannot be negative.")
    if index >= shift.current_count:
        raise ValueError(
            f"{field_name}={index} is outside {shift.target_kind.value} old_size "
            f"{shift.current_count}."
        )
    mapped = shift.remap.target_for(index)
    if mapped is None:
        raise PmxMorphDisplayRemapError(
            f"{field_name} references removed {shift.target_kind.value} index {index}; "
            "insertion shifts cannot remove source records."
        )
    return mapped


def remap_bone_morph_references_for_insertion(
    morphs: tuple[PmxMorph, ...],
    bone_shift: PmxCollectionReferenceShiftPlan,
    *,
    pmx_version: float,
    additional_uv_count: int,
) -> tuple[PmxMorph, ...]:
    """Rewrite existing bone-morph references through additive bone insertion."""

    if type(morphs) is not tuple:
        raise TypeError("morphs must be a tuple.")
    if not all(isinstance(morph, PmxMorph) for morph in morphs):
        raise TypeError("morphs must contain only PmxMorph records.")
    shift = _require_reference_shift(
        bone_shift,
        PmxReferenceTargetKind.BONE,
        "bone_shift",
    )
    version = _require_pmx_version(pmx_version)
    uv_count = _require_additional_uv_count(additional_uv_count)

    rewritten_morphs: list[PmxMorph] = []
    changed = False
    for morph_index, morph in enumerate(morphs):
        if not 0 <= morph.morph_type < len(_EXPECTED_OFFSET_TYPES):
            raise ValueError(
                f"morphs[{morph_index}].morph_type must be a value from 0 through 10."
            )
        if morph.morph_type in (9, 10) and version != 2.1:
            raise ValueError(
                f"morphs[{morph_index}] type {morph.morph_type} requires PMX 2.1."
            )
        if 4 <= morph.morph_type <= 7:
            required_layer = morph.morph_type - 3
            if uv_count < required_layer:
                raise ValueError(
                    f"morphs[{morph_index}] type {morph.morph_type} requires "
                    f"additional UV layer {required_layer}."
                )

        expected_type = _EXPECTED_OFFSET_TYPES[morph.morph_type]
        rewritten_offsets: list[object] = []
        morph_changed = False
        for offset_index, offset in enumerate(morph.offsets):
            if not isinstance(offset, expected_type):
                raise ValueError(
                    f"morphs[{morph_index}].offsets[{offset_index}] type "
                    f"{morph.morph_type} requires {expected_type.__name__}."
                )
            if not isinstance(offset, PmxBoneMorphOffset):
                rewritten_offsets.append(offset)
                continue

            field_name = (
                f"morphs[{morph_index}].offsets[{offset_index}].bone_index"
            )
            bone_index = _shift_required_source_index(
                offset.bone_index,
                field_name=field_name,
                shift=shift,
            )
            if bone_index == offset.bone_index:
                rewritten_offsets.append(offset)
                continue
            rewritten_offsets.append(replace(offset, bone_index=bone_index))
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


def remap_display_frame_bone_references_for_insertion(
    display_frames: tuple[PmxDisplayFrame, ...],
    bone_shift: PmxCollectionReferenceShiftPlan,
) -> tuple[PmxDisplayFrame, ...]:
    """Rewrite only existing display-frame bone targets through insertion evidence."""

    if type(display_frames) is not tuple:
        raise TypeError("display_frames must be a tuple.")
    if not all(isinstance(frame, PmxDisplayFrame) for frame in display_frames):
        raise TypeError("display_frames must contain only PmxDisplayFrame records.")
    shift = _require_reference_shift(
        bone_shift,
        PmxReferenceTargetKind.BONE,
        "bone_shift",
    )

    rewritten_frames: list[PmxDisplayFrame] = []
    changed = False
    for frame_index, frame in enumerate(display_frames):
        rewritten_elements: list[PmxDisplayFrameElement] = []
        frame_changed = False
        for element_index, element in enumerate(frame.elements):
            if not isinstance(element, PmxDisplayFrameElement):
                raise TypeError(
                    f"display_frames[{frame_index}].elements[{element_index}] "
                    "must be a PmxDisplayFrameElement record."
                )
            if element.target_type == "morph":
                rewritten_elements.append(element)
                continue
            if element.target_type != "bone":
                raise ValueError(
                    f"display_frames[{frame_index}].elements[{element_index}]."
                    "target_type must be either 'bone' or 'morph'."
                )

            field_name = (
                f"display_frames[{frame_index}].elements[{element_index}]."
                "target_index"
            )
            target_index = _shift_required_source_index(
                element.target_index,
                field_name=field_name,
                shift=shift,
            )
            if target_index == element.target_index:
                rewritten_elements.append(element)
                continue
            rewritten_elements.append(replace(element, target_index=target_index))
            frame_changed = True

        if frame_changed:
            rewritten_frames.append(
                replace(frame, elements=tuple(rewritten_elements))
            )
            changed = True
        else:
            rewritten_frames.append(frame)

    if not changed:
        return display_frames
    return tuple(rewritten_frames)
