"""Certified PMX morph insertion preview and execution intent for v0.9.2 CP13.

This target-specific internal layer accepts only typed semantic morph payloads for
CP13-owned morph types 0 through 9. It validates source-domain references,
reader/count/index capacity, PMX version/additional-UV requirements, and exact
binary32 representability before planning. Existing group/flip morph references
and display-frame morph targets are remapped through the insertion shift plan.

Impulse morph insertion (type 10) remains CP14-owned. New-to-new morph
references, mixed target insertion, automatic index-width resizing, raw PmxMorph
inputs, normalization/repair, and direct filesystem publication are out of scope.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
from dataclasses import dataclass, field, replace
from typing import Final, TypeAlias

from mmd_registry.pmx.document import (
    PmxBoneMorphOffset,
    PmxDocument,
    PmxFlipMorphOffset,
    PmxGroupMorphOffset,
    PmxMaterialMorphOffset,
    PmxMorph,
    PmxUvMorphOffset,
    PmxVertexMorphOffset,
)
from mmd_registry.pmx.morph_display_remap import (
    remap_display_frame_morph_references_for_insertion,
    remap_morph_references_for_insertion,
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
from mmd_registry.pmx.sections.header import MAX_PMX_NAME_BYTES
from mmd_registry.pmx.sections.morphs import (
    MAX_PMX_MORPH_COUNT,
    MAX_PMX_MORPH_OFFSET_COUNT,
    MAX_PMX_TOTAL_MORPH_OFFSET_COUNT,
)
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


PMX_MORPH_INSERTION_PREVIEW_SCHEMA_VERSION: Final[int] = 1

_PANEL_NAMES: Final[tuple[str, ...]] = (
    "system",
    "eyebrow",
    "eye",
    "mouth",
    "other",
)
_MORPH_TYPE_NAMES: Final[tuple[str, ...]] = (
    "group",
    "vertex",
    "bone",
    "uv",
    "additional_uv_1",
    "additional_uv_2",
    "additional_uv_3",
    "additional_uv_4",
    "material",
    "flip",
)


class PmxStructuralMorphInsertionError(ValueError):
    """Raised when a CP13 morph insertion cannot be safely certified."""


def _is_plain_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _require_plain_int(value: object, field_name: str) -> int:
    if not _is_plain_int(value):
        raise TypeError(f"{field_name} must be an integer.")
    return value


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
        raise PmxStructuralMorphInsertionError(
            f"{field_name} must be representable as a finite PMX float32 value."
        ) from None
    canonical = struct.unpack("<f", encoded)[0]
    if not math.isfinite(canonical):
        raise PmxStructuralMorphInsertionError(
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
class PmxGroupMorphInsertionOffsetPayload:
    morph_index: int
    weight: float

    def __post_init__(self) -> None:
        index = _require_plain_int(self.morph_index, "morph_index")
        if index < 0:
            raise ValueError("morph_index cannot be negative.")
        _require_finite_float(self.weight, "weight")

    def to_dict(self) -> dict[str, object]:
        return {"morph_index": self.morph_index, "weight": self.weight}


@dataclass(frozen=True, slots=True)
class PmxVertexMorphInsertionOffsetPayload:
    vertex_index: int
    translation: tuple[float, float, float]

    def __post_init__(self) -> None:
        index = _require_plain_int(self.vertex_index, "vertex_index")
        if index < 0:
            raise ValueError("vertex_index cannot be negative.")
        _require_float_tuple(
            self.translation,
            field_name="translation",
            length=3,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "vertex_index": self.vertex_index,
            "translation": list(self.translation),
        }


@dataclass(frozen=True, slots=True)
class PmxBoneMorphInsertionOffsetPayload:
    bone_index: int
    translation: tuple[float, float, float]
    rotation: tuple[float, float, float, float]

    def __post_init__(self) -> None:
        index = _require_plain_int(self.bone_index, "bone_index")
        if index < 0:
            raise ValueError("bone_index cannot be negative.")
        _require_float_tuple(
            self.translation,
            field_name="translation",
            length=3,
        )
        _require_float_tuple(
            self.rotation,
            field_name="rotation",
            length=4,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "bone_index": self.bone_index,
            "translation": list(self.translation),
            "rotation": list(self.rotation),
        }


@dataclass(frozen=True, slots=True)
class PmxUvMorphInsertionOffsetPayload:
    vertex_index: int
    uv_offset: tuple[float, float, float, float]

    def __post_init__(self) -> None:
        index = _require_plain_int(self.vertex_index, "vertex_index")
        if index < 0:
            raise ValueError("vertex_index cannot be negative.")
        _require_float_tuple(
            self.uv_offset,
            field_name="uv_offset",
            length=4,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "vertex_index": self.vertex_index,
            "uv_offset": list(self.uv_offset),
        }


@dataclass(frozen=True, slots=True)
class PmxMaterialMorphInsertionOffsetPayload:
    material_index: int
    operation: str
    diffuse: tuple[float, float, float, float]
    specular: tuple[float, float, float]
    specular_strength: float
    ambient: tuple[float, float, float]
    edge_color: tuple[float, float, float, float]
    edge_scale: float
    texture_tint: tuple[float, float, float, float]
    sphere_tint: tuple[float, float, float, float]
    toon_tint: tuple[float, float, float, float]

    def __post_init__(self) -> None:
        index = _require_plain_int(self.material_index, "material_index")
        if index < -1:
            raise ValueError("material_index cannot be smaller than -1.")
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
            _require_float_tuple(
                getattr(self, field_name),
                field_name=field_name,
                length=length,
            )
        _require_finite_float(self.specular_strength, "specular_strength")
        _require_finite_float(self.edge_scale, "edge_scale")

    def to_dict(self) -> dict[str, object]:
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
class PmxFlipMorphInsertionOffsetPayload:
    morph_index: int
    weight: float

    def __post_init__(self) -> None:
        index = _require_plain_int(self.morph_index, "morph_index")
        if index < 0:
            raise ValueError("morph_index cannot be negative.")
        _require_finite_float(self.weight, "weight")

    def to_dict(self) -> dict[str, object]:
        return {"morph_index": self.morph_index, "weight": self.weight}


PmxMorphInsertionOffsetPayload: TypeAlias = (
    PmxGroupMorphInsertionOffsetPayload
    | PmxVertexMorphInsertionOffsetPayload
    | PmxBoneMorphInsertionOffsetPayload
    | PmxUvMorphInsertionOffsetPayload
    | PmxMaterialMorphInsertionOffsetPayload
    | PmxFlipMorphInsertionOffsetPayload
)

_EXPECTED_PAYLOAD_TYPES: Final[tuple[type[object], ...]] = (
    PmxGroupMorphInsertionOffsetPayload,
    PmxVertexMorphInsertionOffsetPayload,
    PmxBoneMorphInsertionOffsetPayload,
    PmxUvMorphInsertionOffsetPayload,
    PmxUvMorphInsertionOffsetPayload,
    PmxUvMorphInsertionOffsetPayload,
    PmxUvMorphInsertionOffsetPayload,
    PmxUvMorphInsertionOffsetPayload,
    PmxMaterialMorphInsertionOffsetPayload,
    PmxFlipMorphInsertionOffsetPayload,
)


@dataclass(frozen=True, slots=True)
class PmxMorphInsertionPayload:
    """Internal semantic morph payload paired with one CP05 insertion position."""

    local_name: str
    universal_name: str
    panel: int
    morph_type: int
    offsets: tuple[PmxMorphInsertionOffsetPayload, ...]
    position: PmxStructuralInsertPosition

    def __post_init__(self) -> None:
        for field_name in ("local_name", "universal_name"):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"{field_name} must be a string.")

        panel = _require_plain_int(self.panel, "panel")
        if not 0 <= panel < len(_PANEL_NAMES):
            raise ValueError("panel must be a value from 0 through 4.")

        morph_type = _require_plain_int(self.morph_type, "morph_type")
        if not 0 <= morph_type < len(_MORPH_TYPE_NAMES):
            raise PmxStructuralMorphInsertionError(
                "CP13 morph insertion supports only morph types 0 through 9; "
                "impulse morph insertion remains CP14-owned."
            )

        if type(self.offsets) is not tuple:
            raise TypeError("offsets must be a tuple.")
        expected = _EXPECTED_PAYLOAD_TYPES[morph_type]
        if not all(isinstance(offset, expected) for offset in self.offsets):
            raise TypeError(
                f"morph type {morph_type} offsets must contain only "
                f"{expected.__name__} values."
            )

        if not isinstance(self.position, PmxStructuralInsertPosition):
            raise TypeError("position must be a PmxStructuralInsertPosition value.")

    def to_dict(self) -> dict[str, object]:
        return {
            "local_name": self.local_name,
            "universal_name": self.universal_name,
            "panel": self.panel,
            "morph_type": self.morph_type,
            "offsets": [offset.to_dict() for offset in self.offsets],
            "position": self.position.to_dict(),
        }

    def to_morph(self, shift: PmxCollectionReferenceShiftPlan) -> PmxMorph:
        if not isinstance(shift, PmxCollectionReferenceShiftPlan):
            raise TypeError("shift must be a PmxCollectionReferenceShiftPlan value.")
        if shift.target_kind is not PmxReferenceTargetKind.MORPH:
            raise ValueError("shift target_kind must be morph.")

        materialized: list[object] = []
        for offset_index, offset in enumerate(self.offsets):
            field_prefix = f"offsets[{offset_index}]"
            if isinstance(offset, PmxGroupMorphInsertionOffsetPayload):
                materialized.append(
                    PmxGroupMorphOffset(
                        morph_index=_map_required_source_morph_reference(
                            offset.morph_index,
                            field_name=f"{field_prefix}.morph_index",
                            shift=shift,
                        ),
                        weight=_canonical_pmx_float32(
                            offset.weight,
                            f"{field_prefix}.weight",
                        ),
                    )
                )
            elif isinstance(offset, PmxVertexMorphInsertionOffsetPayload):
                materialized.append(
                    PmxVertexMorphOffset(
                        vertex_index=offset.vertex_index,
                        translation=_canonical_pmx_float_tuple(
                            offset.translation,
                            field_name=f"{field_prefix}.translation",
                        ),
                    )
                )
            elif isinstance(offset, PmxBoneMorphInsertionOffsetPayload):
                materialized.append(
                    PmxBoneMorphOffset(
                        bone_index=offset.bone_index,
                        translation=_canonical_pmx_float_tuple(
                            offset.translation,
                            field_name=f"{field_prefix}.translation",
                        ),
                        rotation=_canonical_pmx_float_tuple(
                            offset.rotation,
                            field_name=f"{field_prefix}.rotation",
                        ),
                    )
                )
            elif isinstance(offset, PmxUvMorphInsertionOffsetPayload):
                materialized.append(
                    PmxUvMorphOffset(
                        vertex_index=offset.vertex_index,
                        uv_offset=_canonical_pmx_float_tuple(
                            offset.uv_offset,
                            field_name=f"{field_prefix}.uv_offset",
                        ),
                    )
                )
            elif isinstance(offset, PmxMaterialMorphInsertionOffsetPayload):
                materialized.append(
                    PmxMaterialMorphOffset(
                        material_index=offset.material_index,
                        operation=offset.operation,
                        diffuse=_canonical_pmx_float_tuple(
                            offset.diffuse,
                            field_name=f"{field_prefix}.diffuse",
                        ),
                        specular=_canonical_pmx_float_tuple(
                            offset.specular,
                            field_name=f"{field_prefix}.specular",
                        ),
                        specular_strength=_canonical_pmx_float32(
                            offset.specular_strength,
                            f"{field_prefix}.specular_strength",
                        ),
                        ambient=_canonical_pmx_float_tuple(
                            offset.ambient,
                            field_name=f"{field_prefix}.ambient",
                        ),
                        edge_color=_canonical_pmx_float_tuple(
                            offset.edge_color,
                            field_name=f"{field_prefix}.edge_color",
                        ),
                        edge_scale=_canonical_pmx_float32(
                            offset.edge_scale,
                            f"{field_prefix}.edge_scale",
                        ),
                        texture_tint=_canonical_pmx_float_tuple(
                            offset.texture_tint,
                            field_name=f"{field_prefix}.texture_tint",
                        ),
                        sphere_tint=_canonical_pmx_float_tuple(
                            offset.sphere_tint,
                            field_name=f"{field_prefix}.sphere_tint",
                        ),
                        toon_tint=_canonical_pmx_float_tuple(
                            offset.toon_tint,
                            field_name=f"{field_prefix}.toon_tint",
                        ),
                    )
                )
            elif isinstance(offset, PmxFlipMorphInsertionOffsetPayload):
                materialized.append(
                    PmxFlipMorphOffset(
                        morph_index=_map_required_source_morph_reference(
                            offset.morph_index,
                            field_name=f"{field_prefix}.morph_index",
                            shift=shift,
                        ),
                        weight=_canonical_pmx_float32(
                            offset.weight,
                            f"{field_prefix}.weight",
                        ),
                    )
                )
            else:
                raise AssertionError("unsupported CP13 morph insertion offset payload.")

        return PmxMorph(
            local_name=self.local_name,
            universal_name=self.universal_name,
            panel=self.panel,
            panel_name=_PANEL_NAMES[self.panel],
            morph_type=self.morph_type,
            morph_type_name=_MORPH_TYPE_NAMES[self.morph_type],
            offsets=tuple(materialized),
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
        raise PmxStructuralMorphInsertionError(
            f"{label} cannot be encoded using the source PMX text encoding."
        ) from None
    if len(encoded) > MAX_PMX_NAME_BYTES:
        raise PmxStructuralMorphInsertionError(
            f"encoded {label} exceeds the PMX morph parser safety limit."
        )


def _validate_required_source_reference(
    value: int,
    *,
    count: int,
    field_name: str,
    target_label: str,
) -> None:
    if value < 0 or value >= count:
        raise PmxStructuralMorphInsertionError(
            f"{field_name} must reference an existing source {target_label}."
        )


def _validate_optional_source_material_reference(
    value: int,
    *,
    material_count: int,
    field_name: str,
) -> None:
    if value == -1:
        return
    if value < -1 or value >= material_count:
        raise PmxStructuralMorphInsertionError(
            f"{field_name} must reference an existing source material or use -1."
        )


def _map_required_source_morph_reference(
    value: int,
    *,
    field_name: str,
    shift: PmxCollectionReferenceShiftPlan,
) -> int:
    if value < 0 or value >= shift.current_count:
        raise PmxStructuralMorphInsertionError(
            f"{field_name} must reference an existing source morph."
        )
    mapped = shift.remap.target_for(value)
    if mapped is None:
        raise AssertionError("morph insertion shift cannot remove source morphs.")
    return mapped


def _validate_float32_offset(
    offset: PmxMorphInsertionOffsetPayload,
    *,
    offset_index: int,
) -> None:
    prefix = f"offsets[{offset_index}]"
    if isinstance(offset, (PmxGroupMorphInsertionOffsetPayload, PmxFlipMorphInsertionOffsetPayload)):
        _canonical_pmx_float32(offset.weight, f"{prefix}.weight")
        return
    if isinstance(offset, PmxVertexMorphInsertionOffsetPayload):
        _canonical_pmx_float_tuple(
            offset.translation,
            field_name=f"{prefix}.translation",
        )
        return
    if isinstance(offset, PmxBoneMorphInsertionOffsetPayload):
        _canonical_pmx_float_tuple(
            offset.translation,
            field_name=f"{prefix}.translation",
        )
        _canonical_pmx_float_tuple(
            offset.rotation,
            field_name=f"{prefix}.rotation",
        )
        return
    if isinstance(offset, PmxUvMorphInsertionOffsetPayload):
        _canonical_pmx_float_tuple(
            offset.uv_offset,
            field_name=f"{prefix}.uv_offset",
        )
        return
    if isinstance(offset, PmxMaterialMorphInsertionOffsetPayload):
        for field_name in (
            "diffuse",
            "specular",
            "ambient",
            "edge_color",
            "texture_tint",
            "sphere_tint",
            "toon_tint",
        ):
            _canonical_pmx_float_tuple(
                getattr(offset, field_name),
                field_name=f"{prefix}.{field_name}",
            )
        _canonical_pmx_float32(
            offset.specular_strength,
            f"{prefix}.specular_strength",
        )
        _canonical_pmx_float32(offset.edge_scale, f"{prefix}.edge_scale")
        return
    raise AssertionError("unsupported CP13 morph insertion offset payload.")


def _validate_payload_for_source(
    document: PmxDocument,
    insertion: PmxMorphInsertionPayload,
) -> None:
    _validate_text_for_source(
        insertion.local_name,
        encoding=document.header.encoding,
        label="local_name",
    )
    _validate_text_for_source(
        insertion.universal_name,
        encoding=document.header.encoding,
        label="universal_name",
    )

    if insertion.morph_type == 9 and document.header.version != 2.1:
        raise PmxStructuralMorphInsertionError(
            "flip morph insertion requires PMX 2.1."
        )
    if 4 <= insertion.morph_type <= 7:
        required_layer = insertion.morph_type - 3
        if document.header.additional_uv_count < required_layer:
            raise PmxStructuralMorphInsertionError(
                f"morph type {insertion.morph_type} requires additional UV "
                f"layer {required_layer}."
            )

    if len(insertion.offsets) > MAX_PMX_MORPH_OFFSET_COUNT:
        raise PmxStructuralMorphInsertionError(
            "morph offset count exceeds the PMX morph parser safety limit."
        )

    for offset_index, offset in enumerate(insertion.offsets):
        prefix = f"offsets[{offset_index}]"
        if isinstance(
            offset,
            (PmxGroupMorphInsertionOffsetPayload, PmxFlipMorphInsertionOffsetPayload),
        ):
            _validate_required_source_reference(
                offset.morph_index,
                count=len(document.morphs),
                field_name=f"{prefix}.morph_index",
                target_label="morph",
            )
        elif isinstance(offset, PmxVertexMorphInsertionOffsetPayload):
            _validate_required_source_reference(
                offset.vertex_index,
                count=len(document.vertices),
                field_name=f"{prefix}.vertex_index",
                target_label="vertex",
            )
        elif isinstance(offset, PmxBoneMorphInsertionOffsetPayload):
            _validate_required_source_reference(
                offset.bone_index,
                count=len(document.bones),
                field_name=f"{prefix}.bone_index",
                target_label="bone",
            )
        elif isinstance(offset, PmxUvMorphInsertionOffsetPayload):
            _validate_required_source_reference(
                offset.vertex_index,
                count=len(document.vertices),
                field_name=f"{prefix}.vertex_index",
                target_label="vertex",
            )
        elif isinstance(offset, PmxMaterialMorphInsertionOffsetPayload):
            _validate_optional_source_material_reference(
                offset.material_index,
                material_count=len(document.materials),
                field_name=f"{prefix}.material_index",
            )
        else:
            raise AssertionError("unsupported CP13 morph insertion offset payload.")
        _validate_float32_offset(offset, offset_index=offset_index)


def _require_reader_safe_counts(
    document: PmxDocument,
    insertions: tuple[PmxMorphInsertionPayload, ...],
) -> int:
    result_count = len(document.morphs) + len(insertions)
    if result_count > MAX_PMX_MORPH_COUNT:
        raise PmxStructuralMorphInsertionError(
            "resulting morph count exceeds the PMX morph parser safety limit."
        )

    inserted_offset_count = sum(len(insertion.offsets) for insertion in insertions)
    total_offset_count = sum(len(morph.offsets) for morph in document.morphs)
    total_offset_count += inserted_offset_count
    if total_offset_count > MAX_PMX_TOTAL_MORPH_OFFSET_COUNT:
        raise PmxStructuralMorphInsertionError(
            "resulting cumulative morph offset count exceeds the PMX morph "
            "parser safety limit."
        )
    return result_count


def _build_morph_shift_plan(
    document: PmxDocument,
    insertions: tuple[PmxMorphInsertionPayload, ...],
) -> PmxCollectionReferenceShiftPlan:
    expected_result_count = _require_reader_safe_counts(document, insertions)
    for insertion in insertions:
        _validate_payload_for_source(document, insertion)

    position_intent = PmxCollectionInsertionIntent(
        target_kind=PmxReferenceTargetKind.MORPH,
        positions=tuple(insertion.position for insertion in insertions),
    )
    shift = plan_collection_reference_shift(
        position_intent,
        current_count=len(document.morphs),
        index_width=document.header.index_sizes.morph,
    )
    if shift.result_count != expected_result_count:
        raise AssertionError(
            "morph reference-shift result count disagrees with the reader-safe "
            "result count."
        )
    return shift


def _materialize_morphs(
    source_morphs: tuple[PmxMorph, ...],
    rewritten_source_morphs: tuple[PmxMorph, ...],
    insertions: tuple[PmxMorphInsertionPayload, ...],
    shift: PmxCollectionReferenceShiftPlan,
) -> tuple[PmxMorph, ...]:
    if len(source_morphs) != len(rewritten_source_morphs):
        raise ValueError("rewritten source morph count must match source morph count.")
    if shift.current_count != len(source_morphs):
        raise ValueError("morph shift current_count does not match source morph count.")
    if shift.insert_count != len(insertions):
        raise ValueError(
            "morph shift insert_count does not match morph insertion payload count."
        )

    slots: list[PmxMorph | None] = [None] * shift.result_count
    for old_index, new_index in enumerate(shift.remap.targets):
        if new_index is None:
            raise AssertionError("morph insertion shift cannot remove source morphs.")
        if slots[new_index] is not None:
            raise AssertionError("morph insertion shift assigned a duplicate old slot.")
        slots[new_index] = rewritten_source_morphs[old_index]

    for request_index, insertion in enumerate(insertions):
        new_index = shift.new_index_for_insertion(request_index)
        if slots[new_index] is not None:
            raise AssertionError("morph insertion payload overlaps an old morph slot.")
        slots[new_index] = insertion.to_morph(shift)

    if any(value is None for value in slots):
        raise AssertionError("morph insertion materialization left an unfilled slot.")
    return tuple(value for value in slots if value is not None)


def _calculate_intent_sha256(
    insertions: tuple[PmxMorphInsertionPayload, ...],
    shift: PmxCollectionReferenceShiftPlan,
) -> str:
    canonical = {
        "morph_insertions": [insertion.to_dict() for insertion in insertions],
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


def _payload_sha256(insertion: PmxMorphInsertionPayload) -> str:
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
                kind=PmxReferenceTargetKind.MORPH,
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
class PmxMorphInsertionPreview:
    """Deterministic certified preview for one or more semantic morph insertions."""

    source_document: PmxDocument
    insertions: tuple[PmxMorphInsertionPayload, ...]
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
            raise ValueError("morph insertion preview requires at least one insertion.")
        if not all(
            isinstance(insertion, PmxMorphInsertionPayload)
            for insertion in self.insertions
        ):
            raise TypeError(
                "insertions must contain only PmxMorphInsertionPayload values."
            )

        shift = _build_morph_shift_plan(self.source_document, self.insertions)
        rewritten_source_morphs = remap_morph_references_for_insertion(
            self.source_document.morphs,
            shift,
            pmx_version=self.source_document.header.version,
            additional_uv_count=self.source_document.header.additional_uv_count,
        )
        morphs = _materialize_morphs(
            self.source_document.morphs,
            rewritten_source_morphs,
            self.insertions,
            shift,
        )
        display_frames = remap_display_frame_morph_references_for_insertion(
            self.source_document.display_frames,
            shift,
        )
        intended_document = replace(
            self.source_document,
            morphs=morphs,
            display_frames=display_frames,
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
            "preview_schema_version": PMX_MORPH_INSERTION_PREVIEW_SCHEMA_VERSION,
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
                "changed_kinds": ["morph"],
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
                    "changed_kinds": ["morph"],
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
                "morph_insertion": {
                    **self.shift.to_dict(),
                    "payloads": [
                        {
                            "request_index": request_index,
                            "new_index": self.shift.new_index_for_insertion(
                                request_index
                            ),
                            "payload_sha256": _payload_sha256(insertion),
                            "panel": _PANEL_NAMES[insertion.panel],
                            "morph_type": _MORPH_TYPE_NAMES[
                                insertion.morph_type
                            ],
                            "offset_count": len(insertion.offsets),
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


def preview_pmx_morph_insertions(
    document: PmxDocument,
    insertions: tuple[PmxMorphInsertionPayload, ...],
) -> PmxMorphInsertionPreview:
    """Return one certified in-memory CP13 morph insertion preview without I/O."""

    return PmxMorphInsertionPreview(
        source_document=document,
        insertions=insertions,
    )


__all__ = (
    "PmxStructuralMorphInsertionError",
    "PmxGroupMorphInsertionOffsetPayload",
    "PmxVertexMorphInsertionOffsetPayload",
    "PmxBoneMorphInsertionOffsetPayload",
    "PmxUvMorphInsertionOffsetPayload",
    "PmxMaterialMorphInsertionOffsetPayload",
    "PmxFlipMorphInsertionOffsetPayload",
    "PmxMorphInsertionPayload",
    "PmxMorphInsertionPreview",
    "preview_pmx_morph_insertions",
)
