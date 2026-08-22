"""Certified in-memory PMX bone insertion preview for v0.9.2 CP11.

This internal target-specific layer accepts only typed semantic bone payloads,
validates source-domain references and reader/index capacity before planning,
reuses the CP06 insertion reference-shift evidence, delegates every existing
bone-reference owner to its established remap module, and materializes new
flag-consistent ``PmxBone`` records without serialization or filesystem I/O.

CP11 is preview-only. New-to-new bone references, mixed target insertion,
automatic index-width resizing, raw section payloads, and public writer
authority remain out of scope.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
from dataclasses import dataclass, field, replace
from typing import Final

from mmd_registry.pmx.bone_reference_remap import (
    remap_bone_references_for_insertion,
    remap_vertex_deform_bone_references_for_insertion,
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
    PmxDocument,
    PmxIk,
    PmxIkLink,
    decode_pmx_bone_flags,
)
from mmd_registry.pmx.morph_display_remap import (
    remap_bone_morph_references_for_insertion,
    remap_display_frame_bone_references_for_insertion,
)
from mmd_registry.pmx.physics_reference_remap import (
    remap_rigid_body_bone_references_for_insertion,
)
from mmd_registry.pmx.reference_diagnostics import (
    PmxReferenceDiagnostic,
    diagnose_reference_graph,
)
from mmd_registry.pmx.reference_graph import (
    PmxReferenceGraph,
    extract_pmx_reference_graph,
)
from mmd_registry.pmx.reference_model import (
    PmxReferenceNode,
    PmxReferenceTargetKind,
)
from mmd_registry.pmx.reference_queries import _analyze_reference_impacts
from mmd_registry.pmx.sections.bones import (
    MAX_PMX_BONE_COUNT,
    MAX_PMX_IK_LINK_COUNT,
    MAX_PMX_IK_LOOP_COUNT,
    MAX_PMX_TOTAL_IK_LINK_COUNT,
)
from mmd_registry.pmx.sections.header import MAX_PMX_NAME_BYTES
from mmd_registry.pmx.structural_insert_intent import (
    PmxCollectionInsertionIntent,
    PmxStructuralInsertPosition,
)
from mmd_registry.pmx.structural_invariants import PmxStructuralInvariantCertificate
from mmd_registry.pmx.structural_preview import PmxStructuralReferenceImpactAudit
from mmd_registry.pmx.structural_reference_shift import (
    PmxCollectionReferenceShiftPlan,
    plan_collection_reference_shift,
)


PMX_BONE_INSERTION_PREVIEW_SCHEMA_VERSION: Final[int] = 1
_INT32_MIN: Final[int] = -(1 << 31)
_INT32_MAX: Final[int] = (1 << 31) - 1


class PmxStructuralBoneInsertionError(ValueError):
    """Raised when a bone insertion cannot be certified under the CP11 contract."""


def _is_plain_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _require_plain_int(value: object, field_name: str) -> int:
    if not _is_plain_int(value):
        raise TypeError(f"{field_name} must be an integer.")
    return value


def _require_int32(value: object, field_name: str) -> int:
    integer = _require_plain_int(value, field_name)
    if not _INT32_MIN <= integer <= _INT32_MAX:
        raise PmxStructuralBoneInsertionError(
            f"{field_name} must fit in a signed 32-bit integer."
        )
    return integer


def _require_finite_float(value: object, field_name: str) -> None:
    if not isinstance(value, float):
        raise TypeError(f"{field_name} must be a float.")
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite.")


def _require_float_tuple(
    value: object,
    *,
    field_name: str,
    length: int,
) -> None:
    if type(value) is not tuple:
        raise TypeError(f"{field_name} must be a tuple.")
    if len(value) != length:
        raise ValueError(f"{field_name} must contain exactly {length} values.")
    for item in value:
        _require_finite_float(item, f"{field_name} value")


def _canonical_pmx_float32(value: float, field_name: str) -> float:
    _require_finite_float(value, field_name)
    try:
        encoded = struct.pack("<f", value)
    except (OverflowError, struct.error):
        raise PmxStructuralBoneInsertionError(
            f"{field_name} must be representable as a finite PMX float32 value."
        ) from None
    canonical = struct.unpack("<f", encoded)[0]
    if not math.isfinite(canonical):
        raise PmxStructuralBoneInsertionError(
            f"{field_name} must be representable as a finite PMX float32 value."
        )
    return canonical


def _canonical_pmx_float_tuple(
    value: tuple[float, ...],
    *,
    field_name: str,
) -> tuple[float, ...]:
    return tuple(
        _canonical_pmx_float32(item, f"{field_name} value") for item in value
    )


@dataclass(frozen=True, slots=True)
class PmxBoneIkLinkInsertionPayload:
    """Internal source-domain IK link payload."""

    bone_index: int
    lower_limit: tuple[float, float, float] | None
    upper_limit: tuple[float, float, float] | None

    def __post_init__(self) -> None:
        bone_index = _require_plain_int(self.bone_index, "bone_index")
        if bone_index < 0:
            raise ValueError("bone_index cannot be negative.")
        if (self.lower_limit is None) != (self.upper_limit is None):
            raise ValueError(
                "IK link lower_limit and upper_limit must either both be present "
                "or both be None."
            )
        if self.lower_limit is not None:
            _require_float_tuple(
                self.lower_limit,
                field_name="lower_limit",
                length=3,
            )
            assert self.upper_limit is not None
            _require_float_tuple(
                self.upper_limit,
                field_name="upper_limit",
                length=3,
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "bone_index": self.bone_index,
            "lower_limit": (
                list(self.lower_limit) if self.lower_limit is not None else None
            ),
            "upper_limit": (
                list(self.upper_limit) if self.upper_limit is not None else None
            ),
        }


@dataclass(frozen=True, slots=True)
class PmxBoneIkInsertionPayload:
    """Internal source-domain IK payload."""

    target_bone_index: int
    loop_count: int
    angle_limit: float
    links: tuple[PmxBoneIkLinkInsertionPayload, ...]

    def __post_init__(self) -> None:
        target = _require_plain_int(self.target_bone_index, "target_bone_index")
        if target < 0:
            raise ValueError("target_bone_index cannot be negative.")
        loop_count = _require_plain_int(self.loop_count, "loop_count")
        if loop_count < 0:
            raise ValueError("loop_count cannot be negative.")
        _require_finite_float(self.angle_limit, "angle_limit")
        if type(self.links) is not tuple:
            raise TypeError("links must be a tuple.")
        if not all(
            isinstance(link, PmxBoneIkLinkInsertionPayload) for link in self.links
        ):
            raise TypeError(
                "links must contain only PmxBoneIkLinkInsertionPayload values."
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "target_bone_index": self.target_bone_index,
            "loop_count": self.loop_count,
            "angle_limit": self.angle_limit,
            "links": [link.to_dict() for link in self.links],
        }


@dataclass(frozen=True, slots=True)
class PmxBoneInsertionPayload:
    """Internal semantic bone payload paired with one CP05 insertion position."""

    local_name: str
    universal_name: str
    bone_position: tuple[float, float, float]
    parent_bone_index: int
    transform_layer: int
    rotatable: bool
    translatable: bool
    visible: bool
    enabled: bool
    local_append: bool
    after_physics: bool
    tail_offset: tuple[float, float, float] | None
    tail_bone_index: int | None
    inherit_rotation: bool
    inherit_translation: bool
    inherit_parent_bone_index: int | None
    inherit_weight: float | None
    fixed_axis: tuple[float, float, float] | None
    local_axis_x: tuple[float, float, float] | None
    local_axis_z: tuple[float, float, float] | None
    external_parent_key: int | None
    ik: PmxBoneIkInsertionPayload | None
    position: PmxStructuralInsertPosition

    def __post_init__(self) -> None:
        for field_name in ("local_name", "universal_name"):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"{field_name} must be a string.")

        _require_float_tuple(
            self.bone_position,
            field_name="bone_position",
            length=3,
        )
        parent = _require_plain_int(self.parent_bone_index, "parent_bone_index")
        if parent < -1:
            raise ValueError("parent_bone_index cannot be smaller than -1.")
        _require_int32(self.transform_layer, "transform_layer")

        for field_name in (
            "rotatable",
            "translatable",
            "visible",
            "enabled",
            "local_append",
            "after_physics",
            "inherit_rotation",
            "inherit_translation",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be a boolean.")

        if (self.tail_offset is None) == (self.tail_bone_index is None):
            raise ValueError(
                "exactly one of tail_offset or tail_bone_index must be present."
            )
        if self.tail_offset is not None:
            _require_float_tuple(
                self.tail_offset,
                field_name="tail_offset",
                length=3,
            )
        else:
            assert self.tail_bone_index is not None
            tail_index = _require_plain_int(self.tail_bone_index, "tail_bone_index")
            if tail_index < -1:
                raise ValueError("tail_bone_index cannot be smaller than -1.")

        has_inherit = self.inherit_rotation or self.inherit_translation
        if has_inherit:
            if self.inherit_parent_bone_index is None or self.inherit_weight is None:
                raise ValueError(
                    "inherit flags require inherit_parent_bone_index and inherit_weight."
                )
            inherit_parent = _require_plain_int(
                self.inherit_parent_bone_index,
                "inherit_parent_bone_index",
            )
            if inherit_parent < -1:
                raise ValueError(
                    "inherit_parent_bone_index cannot be smaller than -1."
                )
            _require_finite_float(self.inherit_weight, "inherit_weight")
        elif (
            self.inherit_parent_bone_index is not None
            or self.inherit_weight is not None
        ):
            raise ValueError(
                "inherit_parent_bone_index and inherit_weight require an inherit flag."
            )

        if self.fixed_axis is not None:
            _require_float_tuple(
                self.fixed_axis,
                field_name="fixed_axis",
                length=3,
            )
        if (self.local_axis_x is None) != (self.local_axis_z is None):
            raise ValueError(
                "local_axis_x and local_axis_z must either both be present or both be None."
            )
        if self.local_axis_x is not None:
            _require_float_tuple(
                self.local_axis_x,
                field_name="local_axis_x",
                length=3,
            )
            assert self.local_axis_z is not None
            _require_float_tuple(
                self.local_axis_z,
                field_name="local_axis_z",
                length=3,
            )

        if self.external_parent_key is not None:
            _require_int32(self.external_parent_key, "external_parent_key")
        if self.ik is not None and not isinstance(self.ik, PmxBoneIkInsertionPayload):
            raise TypeError("ik must be a PmxBoneIkInsertionPayload value or None.")
        if not isinstance(self.position, PmxStructuralInsertPosition):
            raise TypeError("position must be a PmxStructuralInsertPosition value.")

    def _derived_flags(self) -> int:
        flags = 0
        if self.tail_bone_index is not None:
            flags |= PMX_BONE_FLAG_TAIL_INDEX
        if self.rotatable:
            flags |= PMX_BONE_FLAG_ROTATABLE
        if self.translatable:
            flags |= PMX_BONE_FLAG_TRANSLATABLE
        if self.visible:
            flags |= PMX_BONE_FLAG_VISIBLE
        if self.enabled:
            flags |= PMX_BONE_FLAG_ENABLED
        if self.ik is not None:
            flags |= PMX_BONE_FLAG_IK
        if self.local_append:
            flags |= PMX_BONE_FLAG_LOCAL_APPEND
        if self.inherit_rotation:
            flags |= PMX_BONE_FLAG_INHERIT_ROTATION
        if self.inherit_translation:
            flags |= PMX_BONE_FLAG_INHERIT_TRANSLATION
        if self.fixed_axis is not None:
            flags |= PMX_BONE_FLAG_FIXED_AXIS
        if self.local_axis_x is not None:
            flags |= PMX_BONE_FLAG_LOCAL_AXES
        if self.after_physics:
            flags |= PMX_BONE_FLAG_AFTER_PHYSICS
        if self.external_parent_key is not None:
            flags |= PMX_BONE_FLAG_EXTERNAL_PARENT
        return flags

    def to_dict(self) -> dict[str, object]:
        return {
            "local_name": self.local_name,
            "universal_name": self.universal_name,
            "bone_position": list(self.bone_position),
            "parent_bone_index": self.parent_bone_index,
            "transform_layer": self.transform_layer,
            "rotatable": self.rotatable,
            "translatable": self.translatable,
            "visible": self.visible,
            "enabled": self.enabled,
            "local_append": self.local_append,
            "after_physics": self.after_physics,
            "tail_offset": (
                list(self.tail_offset) if self.tail_offset is not None else None
            ),
            "tail_bone_index": self.tail_bone_index,
            "inherit_rotation": self.inherit_rotation,
            "inherit_translation": self.inherit_translation,
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
            "position": self.position.to_dict(),
        }

    def to_bone(self, shift: PmxCollectionReferenceShiftPlan) -> PmxBone:
        if not isinstance(shift, PmxCollectionReferenceShiftPlan):
            raise TypeError("shift must be a PmxCollectionReferenceShiftPlan value.")
        if shift.target_kind is not PmxReferenceTargetKind.BONE:
            raise ValueError("shift target_kind must be bone.")

        flags = self._derived_flags()
        tail_bone_index = (
            _map_optional_source_bone_reference(
                self.tail_bone_index,
                field_name="tail_bone_index",
                shift=shift,
            )
            if self.tail_bone_index is not None
            else None
        )
        inherit_parent = (
            _map_optional_source_bone_reference(
                self.inherit_parent_bone_index,
                field_name="inherit_parent_bone_index",
                shift=shift,
            )
            if self.inherit_parent_bone_index is not None
            else None
        )

        ik = None
        if self.ik is not None:
            links = tuple(
                PmxIkLink(
                    bone_index=_map_required_source_bone_reference(
                        link.bone_index,
                        field_name=f"ik.links[{link_index}].bone_index",
                        shift=shift,
                    ),
                    angle_limits_enabled=link.lower_limit is not None,
                    lower_limit=(
                        _canonical_pmx_float_tuple(
                            link.lower_limit,
                            field_name=f"ik.links[{link_index}].lower_limit",
                        )
                        if link.lower_limit is not None
                        else None
                    ),
                    upper_limit=(
                        _canonical_pmx_float_tuple(
                            link.upper_limit,
                            field_name=f"ik.links[{link_index}].upper_limit",
                        )
                        if link.upper_limit is not None
                        else None
                    ),
                )
                for link_index, link in enumerate(self.ik.links)
            )
            ik = PmxIk(
                target_bone_index=_map_required_source_bone_reference(
                    self.ik.target_bone_index,
                    field_name="ik.target_bone_index",
                    shift=shift,
                ),
                loop_count=self.ik.loop_count,
                angle_limit=_canonical_pmx_float32(
                    self.ik.angle_limit,
                    "ik.angle_limit",
                ),
                links=links,
            )

        return PmxBone(
            local_name=self.local_name,
            universal_name=self.universal_name,
            position=_canonical_pmx_float_tuple(
                self.bone_position,
                field_name="bone_position",
            ),
            parent_bone_index=_map_optional_source_bone_reference(
                self.parent_bone_index,
                field_name="parent_bone_index",
                shift=shift,
            ),
            transform_layer=self.transform_layer,
            flags=flags,
            flag_names=decode_pmx_bone_flags(flags),
            tail_mode="bone" if self.tail_bone_index is not None else "offset",
            tail_bone_index=tail_bone_index,
            tail_offset=(
                _canonical_pmx_float_tuple(
                    self.tail_offset,
                    field_name="tail_offset",
                )
                if self.tail_offset is not None
                else None
            ),
            inherit_parent_bone_index=inherit_parent,
            inherit_weight=(
                _canonical_pmx_float32(
                    self.inherit_weight,
                    "inherit_weight",
                )
                if self.inherit_weight is not None
                else None
            ),
            fixed_axis=(
                _canonical_pmx_float_tuple(
                    self.fixed_axis,
                    field_name="fixed_axis",
                )
                if self.fixed_axis is not None
                else None
            ),
            local_axis_x=(
                _canonical_pmx_float_tuple(
                    self.local_axis_x,
                    field_name="local_axis_x",
                )
                if self.local_axis_x is not None
                else None
            ),
            local_axis_z=(
                _canonical_pmx_float_tuple(
                    self.local_axis_z,
                    field_name="local_axis_z",
                )
                if self.local_axis_z is not None
                else None
            ),
            external_parent_key=self.external_parent_key,
            ik=ik,
        )


def _target_counts_to_dict(graph: PmxReferenceGraph) -> dict[str, int]:
    counts = graph.target_counts
    return {
        "vertex": counts.vertex,
        "texture": counts.texture,
        "material": counts.material,
        "bone": counts.bone,
        "morph": counts.morph,
        "rigid_body": counts.rigid_body,
    }


def _validate_text_for_source(
    text: str,
    *,
    encoding: str,
    label: str,
) -> None:
    try:
        encoded = text.encode(encoding, errors="strict")
    except UnicodeEncodeError:
        raise PmxStructuralBoneInsertionError(
            f"{label} cannot be encoded using the source PMX text encoding."
        ) from None
    if len(encoded) > MAX_PMX_NAME_BYTES:
        raise PmxStructuralBoneInsertionError(
            f"encoded {label} exceeds the PMX bone parser safety limit."
        )


def _validate_optional_source_bone_reference(
    value: int,
    *,
    bone_count: int,
    field_name: str,
) -> None:
    if value == -1:
        return
    if value < -1 or value >= bone_count:
        raise PmxStructuralBoneInsertionError(
            f"{field_name} must reference an existing source bone or use -1."
        )


def _validate_required_source_bone_reference(
    value: int,
    *,
    bone_count: int,
    field_name: str,
) -> None:
    if value < 0 or value >= bone_count:
        raise PmxStructuralBoneInsertionError(
            f"{field_name} must reference an existing source bone."
        )


def _map_optional_source_bone_reference(
    value: int | None,
    *,
    field_name: str,
    shift: PmxCollectionReferenceShiftPlan,
) -> int:
    if value is None:
        raise TypeError(f"{field_name} cannot be None.")
    if value == -1:
        return -1
    if value < -1 or value >= shift.current_count:
        raise PmxStructuralBoneInsertionError(
            f"{field_name} is outside the source bone domain."
        )
    mapped = shift.remap.target_for(value)
    if mapped is None:
        raise AssertionError("bone insertion shift cannot remove source bones.")
    return mapped


def _map_required_source_bone_reference(
    value: int,
    *,
    field_name: str,
    shift: PmxCollectionReferenceShiftPlan,
) -> int:
    if value < 0 or value >= shift.current_count:
        raise PmxStructuralBoneInsertionError(
            f"{field_name} is outside the source bone domain."
        )
    mapped = shift.remap.target_for(value)
    if mapped is None:
        raise AssertionError("bone insertion shift cannot remove source bones.")
    return mapped


def _validate_float32_payload(insertion: PmxBoneInsertionPayload) -> None:
    _canonical_pmx_float_tuple(
        insertion.bone_position,
        field_name="bone_position",
    )
    if insertion.tail_offset is not None:
        _canonical_pmx_float_tuple(
            insertion.tail_offset,
            field_name="tail_offset",
        )
    if insertion.inherit_weight is not None:
        _canonical_pmx_float32(
            insertion.inherit_weight,
            "inherit_weight",
        )
    for field_name in ("fixed_axis", "local_axis_x", "local_axis_z"):
        value = getattr(insertion, field_name)
        if value is not None:
            _canonical_pmx_float_tuple(value, field_name=field_name)

    if insertion.ik is None:
        return
    _canonical_pmx_float32(insertion.ik.angle_limit, "ik.angle_limit")
    for link_index, link in enumerate(insertion.ik.links):
        if link.lower_limit is not None:
            _canonical_pmx_float_tuple(
                link.lower_limit,
                field_name=f"ik.links[{link_index}].lower_limit",
            )
            assert link.upper_limit is not None
            _canonical_pmx_float_tuple(
                link.upper_limit,
                field_name=f"ik.links[{link_index}].upper_limit",
            )


def _validate_payload_for_source(
    document: PmxDocument,
    insertion: PmxBoneInsertionPayload,
) -> None:
    _validate_text_for_source(
        insertion.local_name,
        encoding=document.header.encoding,
        label="bone local name",
    )
    _validate_text_for_source(
        insertion.universal_name,
        encoding=document.header.encoding,
        label="bone universal name",
    )

    bone_count = len(document.bones)
    _validate_optional_source_bone_reference(
        insertion.parent_bone_index,
        bone_count=bone_count,
        field_name="parent_bone_index",
    )
    if insertion.tail_bone_index is not None:
        _validate_optional_source_bone_reference(
            insertion.tail_bone_index,
            bone_count=bone_count,
            field_name="tail_bone_index",
        )
    if insertion.inherit_parent_bone_index is not None:
        _validate_optional_source_bone_reference(
            insertion.inherit_parent_bone_index,
            bone_count=bone_count,
            field_name="inherit_parent_bone_index",
        )

    _require_int32(insertion.transform_layer, "transform_layer")
    if insertion.external_parent_key is not None:
        _require_int32(insertion.external_parent_key, "external_parent_key")

    if insertion.ik is not None:
        _validate_required_source_bone_reference(
            insertion.ik.target_bone_index,
            bone_count=bone_count,
            field_name="ik.target_bone_index",
        )
        if insertion.ik.loop_count > MAX_PMX_IK_LOOP_COUNT:
            raise PmxStructuralBoneInsertionError(
                "IK loop_count exceeds the PMX bone parser safety limit."
            )
        if len(insertion.ik.links) > MAX_PMX_IK_LINK_COUNT:
            raise PmxStructuralBoneInsertionError(
                "IK link count exceeds the PMX bone parser safety limit."
            )
        for link_index, link in enumerate(insertion.ik.links):
            _validate_required_source_bone_reference(
                link.bone_index,
                bone_count=bone_count,
                field_name=f"ik.links[{link_index}].bone_index",
            )

    _validate_float32_payload(insertion)


def _require_reader_safe_counts(
    document: PmxDocument,
    insertions: tuple[PmxBoneInsertionPayload, ...],
) -> int:
    result_count = len(document.bones) + len(insertions)
    if result_count > MAX_PMX_BONE_COUNT:
        raise PmxStructuralBoneInsertionError(
            "resulting bone count exceeds the PMX bone parser safety limit."
        )

    total_ik_links = sum(
        len(bone.ik.links) for bone in document.bones if bone.ik is not None
    )
    total_ik_links += sum(
        len(insertion.ik.links)
        for insertion in insertions
        if insertion.ik is not None
    )
    if total_ik_links > MAX_PMX_TOTAL_IK_LINK_COUNT:
        raise PmxStructuralBoneInsertionError(
            "resulting cumulative IK link count exceeds the PMX bone parser "
            "safety limit."
        )
    return result_count


def _build_bone_shift_plan(
    document: PmxDocument,
    insertions: tuple[PmxBoneInsertionPayload, ...],
) -> PmxCollectionReferenceShiftPlan:
    expected_result_count = _require_reader_safe_counts(document, insertions)

    for insertion in insertions:
        _validate_payload_for_source(document, insertion)

    position_intent = PmxCollectionInsertionIntent(
        target_kind=PmxReferenceTargetKind.BONE,
        positions=tuple(insertion.position for insertion in insertions),
    )
    shift = plan_collection_reference_shift(
        position_intent,
        current_count=len(document.bones),
        index_width=document.header.index_sizes.bone,
    )
    if shift.result_count != expected_result_count:
        raise AssertionError(
            "bone reference-shift result count disagrees with the reader-safe "
            "result count."
        )
    return shift


def _materialize_bones(
    source_bones: tuple[PmxBone, ...],
    rewritten_source_bones: tuple[PmxBone, ...],
    insertions: tuple[PmxBoneInsertionPayload, ...],
    shift: PmxCollectionReferenceShiftPlan,
) -> tuple[PmxBone, ...]:
    if len(source_bones) != len(rewritten_source_bones):
        raise ValueError("rewritten source bone count must match source bone count.")
    if shift.current_count != len(source_bones):
        raise ValueError("bone shift current_count does not match source bone count.")
    if shift.insert_count != len(insertions):
        raise ValueError(
            "bone shift insert_count does not match bone insertion payload count."
        )

    slots: list[PmxBone | None] = [None] * shift.result_count
    for old_index, new_index in enumerate(shift.remap.targets):
        if new_index is None:
            raise AssertionError("bone insertion shift cannot remove source bones.")
        if slots[new_index] is not None:
            raise AssertionError("bone insertion shift assigned a duplicate old slot.")
        slots[new_index] = rewritten_source_bones[old_index]

    for request_index, insertion in enumerate(insertions):
        new_index = shift.new_index_for_insertion(request_index)
        if slots[new_index] is not None:
            raise AssertionError("bone insertion payload overlaps an old bone slot.")
        slots[new_index] = insertion.to_bone(shift)

    if any(value is None for value in slots):
        raise AssertionError("bone insertion materialization left an unfilled slot.")
    return tuple(value for value in slots if value is not None)


def _calculate_intent_sha256(
    insertions: tuple[PmxBoneInsertionPayload, ...],
    shift: PmxCollectionReferenceShiftPlan,
) -> str:
    canonical = {
        "bone_insertions": [insertion.to_dict() for insertion in insertions],
        "reference_shift": shift.to_dict(),
    }
    payload = json.dumps(
        canonical,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _payload_sha256(insertion: PmxBoneInsertionPayload) -> str:
    payload = json.dumps(
        insertion.to_dict(),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _reference_impact_audits(
    source_graph: PmxReferenceGraph,
    shift: PmxCollectionReferenceShiftPlan,
) -> tuple[PmxStructuralReferenceImpactAudit, ...]:
    specs = tuple(
        (
            PmxReferenceNode(
                kind=PmxReferenceTargetKind.BONE,
                index=old_index,
            ),
            new_index,
        )
        for old_index, new_index in enumerate(shift.remap.targets)
        if new_index is not None and new_index != old_index
    )
    impacts = _analyze_reference_impacts(
        source_graph,
        tuple(node for node, _new_index in specs),
    )
    return tuple(
        PmxStructuralReferenceImpactAudit(
            node=node,
            new_index=new_index,
            impact=impact,
        )
        for (node, new_index), impact in zip(specs, impacts, strict=True)
    )


@dataclass(frozen=True, slots=True)
class PmxBoneInsertionPreview:
    """Deterministic certified preview for one or more semantic bone insertions."""

    source_document: PmxDocument
    insertions: tuple[PmxBoneInsertionPayload, ...]
    shift: PmxCollectionReferenceShiftPlan = field(init=False)
    certificate: PmxStructuralInvariantCertificate = field(init=False)
    reference_impacts: tuple[PmxStructuralReferenceImpactAudit, ...] = field(init=False)
    source_reference_diagnostics: tuple[PmxReferenceDiagnostic, ...] = field(init=False)
    intent_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.source_document, PmxDocument):
            raise TypeError("source_document must be a PmxDocument instance.")
        if type(self.insertions) is not tuple:
            raise TypeError("insertions must be a tuple.")
        if not self.insertions:
            raise ValueError("bone insertion preview requires at least one insertion.")
        if not all(
            isinstance(insertion, PmxBoneInsertionPayload)
            for insertion in self.insertions
        ):
            raise TypeError(
                "insertions must contain only PmxBoneInsertionPayload values."
            )

        shift = _build_bone_shift_plan(self.source_document, self.insertions)

        vertices = remap_vertex_deform_bone_references_for_insertion(
            self.source_document.vertices,
            shift,
            pmx_version=self.source_document.header.version,
        )
        rewritten_source_bones = remap_bone_references_for_insertion(
            self.source_document.bones,
            shift,
        )
        bones = _materialize_bones(
            self.source_document.bones,
            rewritten_source_bones,
            self.insertions,
            shift,
        )
        morphs = remap_bone_morph_references_for_insertion(
            self.source_document.morphs,
            shift,
            pmx_version=self.source_document.header.version,
            additional_uv_count=self.source_document.header.additional_uv_count,
        )
        display_frames = remap_display_frame_bone_references_for_insertion(
            self.source_document.display_frames,
            shift,
        )
        rigid_bodies = remap_rigid_body_bone_references_for_insertion(
            self.source_document.rigid_bodies,
            shift,
        )

        geometry = (
            self.source_document.geometry
            if vertices is self.source_document.vertices
            else replace(self.source_document.geometry, vertices=vertices)
        )
        intended_document = replace(
            self.source_document,
            geometry=geometry,
            bones=bones,
            morphs=morphs,
            display_frames=display_frames,
            rigid_bodies=rigid_bodies,
        )
        certificate = PmxStructuralInvariantCertificate(document=intended_document)

        source_graph = extract_pmx_reference_graph(self.source_document)
        source_diagnostics = diagnose_reference_graph(source_graph)
        reference_impacts = _reference_impact_audits(source_graph, shift)

        object.__setattr__(self, "shift", shift)
        object.__setattr__(self, "certificate", certificate)
        object.__setattr__(self, "reference_impacts", reference_impacts)
        object.__setattr__(
            self,
            "source_reference_diagnostics",
            source_diagnostics,
        )
        object.__setattr__(
            self,
            "intent_sha256",
            _calculate_intent_sha256(self.insertions, shift),
        )

    @property
    def status(self) -> str:
        return "changes_pending"

    def to_dict(self) -> dict[str, object]:
        source_graph = extract_pmx_reference_graph(self.source_document)
        direct_reference_edge_count = sum(
            len(item.impact.inbound_edges) + len(item.impact.outbound_edges)
            for item in self.reference_impacts
        )
        return {
            "preview_schema_version": PMX_BONE_INSERTION_PREVIEW_SCHEMA_VERSION,
            "status": self.status,
            "dry_run": True,
            "source": {
                "target_counts": _target_counts_to_dict(source_graph),
                "reference_edge_count": len(source_graph.edges),
                "reference_diagnostic_count": len(
                    self.source_reference_diagnostics
                ),
            },
            "intent": {
                "sha256": self.intent_sha256,
                "changed_kinds": ["bone"],
                "collection_count": 1,
                "insert_count": self.shift.insert_count,
            },
            "output": {
                "written": False,
                "target_counts": _target_counts_to_dict(
                    self.certificate.reference_graph
                ),
                "reference_edge_count": self.certificate.edge_count,
                "reference_diagnostic_count": 0,
            },
            "verification": {
                "invariants": "passed",
                "reference_model": "passed",
                "serialization": "not_performed",
            },
            "audit": {
                "summary": {
                    "changed_kinds": ["bone"],
                    "changed_collection_count": 1,
                    "changed_node_count": len(self.reference_impacts),
                    "removed_record_count": 0,
                    "reindexed_record_count": len(self.reference_impacts),
                    "inserted_record_count": self.shift.insert_count,
                    "direct_reference_edge_count": direct_reference_edge_count,
                    "direct_reference_impact_complete": all(
                        item.impact.is_complete for item in self.reference_impacts
                    ),
                    "source_reference_diagnostic_count": len(
                        self.source_reference_diagnostics
                    ),
                },
                "bone_insertion": {
                    **self.shift.to_dict(),
                    "payloads": [
                        {
                            "request_index": request_index,
                            "new_index": self.shift.new_index_for_insertion(
                                request_index
                            ),
                            "payload_sha256": _payload_sha256(insertion),
                            "has_ik": insertion.ik is not None,
                            "ik_link_count": (
                                len(insertion.ik.links)
                                if insertion.ik is not None
                                else 0
                            ),
                        }
                        for request_index, insertion in enumerate(self.insertions)
                    ],
                },
                "reference_impacts": [
                    item.to_dict() for item in self.reference_impacts
                ],
                "source_reference_diagnostics": [
                    item.to_dict() for item in self.source_reference_diagnostics
                ],
            },
        }


def preview_pmx_bone_insertions(
    document: PmxDocument,
    insertions: tuple[PmxBoneInsertionPayload, ...],
) -> PmxBoneInsertionPreview:
    """Return one certified in-memory bone insertion preview without I/O."""

    return PmxBoneInsertionPreview(
        source_document=document,
        insertions=insertions,
    )


__all__ = (
    "PmxStructuralBoneInsertionError",
    "PmxBoneIkLinkInsertionPayload",
    "PmxBoneIkInsertionPayload",
    "PmxBoneInsertionPayload",
    "PmxBoneInsertionPreview",
    "preview_pmx_bone_insertions",
)
