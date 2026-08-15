"""Deterministic read-only extraction of PMX reference relationships.

The CP05 layer traverses an already-typed :class:`PmxDocument` and records
active reference relationships without mutating the document or touching the
filesystem. It deliberately keeps raw invalid/unsupported evidence separate
from public diagnostics, which remain owned by a later checkpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from mmd_registry.pmx.document import (
    PMX_BONE_FLAG_IK,
    PMX_BONE_FLAG_INHERIT_ROTATION,
    PMX_BONE_FLAG_INHERIT_TRANSLATION,
    PMX_BONE_FLAG_TAIL_INDEX,
    PmxBdef1,
    PmxBdef2,
    PmxBdef4,
    PmxBoneMorphOffset,
    PmxDocument,
    PmxFlipMorphOffset,
    PmxGroupMorphOffset,
    PmxImpulseMorphOffset,
    PmxMaterialMorphOffset,
    PmxQdef,
    PmxSdef,
    PmxUvMorphOffset,
    PmxVertexMorphOffset,
)
from mmd_registry.pmx.reference_model import (
    PmxReferenceEdge,
    PmxReferenceNode,
    PmxReferenceSourceLocation,
    PmxReferenceSourceSection,
    PmxReferenceTargetKind,
)


@dataclass(frozen=True, slots=True)
class PmxReferenceTargetCounts:
    """Record counts for the six globally index-addressable target collections."""

    vertex: int
    texture: int
    material: int
    bone: int
    morph: int
    rigid_body: int

    def __post_init__(self) -> None:
        for field_name in (
            "vertex",
            "texture",
            "material",
            "bone",
            "morph",
            "rigid_body",
        ):
            value = getattr(self, field_name)
            if type(value) is not int:
                raise TypeError(f"{field_name} count must be an integer.")
            if value < 0:
                raise ValueError(f"{field_name} count must be nonnegative.")

    def count_for(self, kind: PmxReferenceTargetKind) -> int:
        """Return the target count for one typed collection identity."""

        if not isinstance(kind, PmxReferenceTargetKind):
            raise TypeError("kind must be a PmxReferenceTargetKind value.")
        return getattr(self, kind.value)


@dataclass(frozen=True, slots=True)
class PmxReferenceInvalidTarget:
    """Raw evidence for one active reference whose target index is invalid."""

    relationship_id: str
    source: PmxReferenceSourceLocation
    target_kind: PmxReferenceTargetKind
    raw_index: int
    target_count: int

    def __post_init__(self) -> None:
        if type(self.relationship_id) is not str or not self.relationship_id:
            raise ValueError("relationship_id must be a non-empty string.")
        if not isinstance(self.source, PmxReferenceSourceLocation):
            raise TypeError("source must be a PmxReferenceSourceLocation value.")
        if not isinstance(self.target_kind, PmxReferenceTargetKind):
            raise TypeError("target_kind must be a PmxReferenceTargetKind value.")
        if type(self.raw_index) is not int:
            raise TypeError("raw_index must be an integer.")
        if type(self.target_count) is not int:
            raise TypeError("target_count must be an integer.")
        if self.target_count < 0:
            raise ValueError("target_count must be nonnegative.")


class PmxReferenceUnsupportedStateKind(StrEnum):
    """Neutral extraction-state categories, not public diagnostic codes."""

    ACTIVE_PAYLOAD_MISSING = "active_payload_missing"
    INACTIVE_PAYLOAD_PRESENT = "inactive_payload_present"
    MORPH_OFFSET_TYPE_MISMATCH = "morph_offset_type_mismatch"
    VERSION_CONDITION_MISMATCH = "version_condition_mismatch"
    UV_LAYER_CONDITION_MISMATCH = "uv_layer_condition_mismatch"


@dataclass(frozen=True, slots=True)
class PmxReferenceUnsupportedState:
    """Raw deterministic evidence for a relationship state CP05 cannot emit."""

    kind: PmxReferenceUnsupportedStateKind
    relationship_id: str
    source: PmxReferenceSourceLocation
    observed: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, PmxReferenceUnsupportedStateKind):
            raise TypeError(
                "kind must be a PmxReferenceUnsupportedStateKind value."
            )
        if type(self.relationship_id) is not str or not self.relationship_id:
            raise ValueError("relationship_id must be a non-empty string.")
        if not isinstance(self.source, PmxReferenceSourceLocation):
            raise TypeError("source must be a PmxReferenceSourceLocation value.")
        if type(self.observed) is not str or not self.observed:
            raise ValueError("observed must be a non-empty string.")


@dataclass(frozen=True, slots=True)
class PmxReferenceGraph:
    """Immutable deterministic snapshot extracted from one typed PMX document."""

    target_counts: PmxReferenceTargetCounts
    edges: tuple[PmxReferenceEdge, ...]
    invalid_targets: tuple[PmxReferenceInvalidTarget, ...]
    unsupported_states: tuple[PmxReferenceUnsupportedState, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.target_counts, PmxReferenceTargetCounts):
            raise TypeError("target_counts must be a PmxReferenceTargetCounts value.")
        for field_name, expected_type in (
            ("edges", PmxReferenceEdge),
            ("invalid_targets", PmxReferenceInvalidTarget),
            ("unsupported_states", PmxReferenceUnsupportedState),
        ):
            value = getattr(self, field_name)
            if type(value) is not tuple:
                raise TypeError(f"{field_name} must be a tuple.")
            if not all(isinstance(item, expected_type) for item in value):
                raise TypeError(
                    f"{field_name} must contain only {expected_type.__name__} values."
                )


def _source(
    section: PmxReferenceSourceSection,
    record_index: int,
    path: str,
) -> PmxReferenceSourceLocation:
    return PmxReferenceSourceLocation(
        section=section,
        record_index=record_index,
        path=path,
    )


def _record_reference(
    *,
    relationship_id: str,
    source: PmxReferenceSourceLocation,
    target_kind: PmxReferenceTargetKind,
    raw_index: int,
    target_counts: PmxReferenceTargetCounts,
    allow_sentinel: bool,
    edges: list[PmxReferenceEdge],
    invalid_targets: list[PmxReferenceInvalidTarget],
) -> None:
    """Record one active integer reference without silently normalizing it."""

    if allow_sentinel and raw_index == -1:
        return

    target_count = target_counts.count_for(target_kind)
    if raw_index < 0 or raw_index >= target_count:
        invalid_targets.append(
            PmxReferenceInvalidTarget(
                relationship_id=relationship_id,
                source=source,
                target_kind=target_kind,
                raw_index=raw_index,
                target_count=target_count,
            )
        )
        return

    edges.append(
        PmxReferenceEdge(
            relationship_id=relationship_id,
            source=source,
            target=PmxReferenceNode(
                kind=target_kind,
                index=raw_index,
            ),
        )
    )


def _record_unsupported(
    *,
    kind: PmxReferenceUnsupportedStateKind,
    relationship_id: str,
    source: PmxReferenceSourceLocation,
    observed: str,
    unsupported_states: list[PmxReferenceUnsupportedState],
) -> None:
    unsupported_states.append(
        PmxReferenceUnsupportedState(
            kind=kind,
            relationship_id=relationship_id,
            source=source,
            observed=observed,
        )
    )


def _extract_surface_references(
    document: PmxDocument,
    *,
    target_counts: PmxReferenceTargetCounts,
    edges: list[PmxReferenceEdge],
    invalid_targets: list[PmxReferenceInvalidTarget],
) -> None:
    for index, vertex_index in enumerate(document.surface_indices):
        _record_reference(
            relationship_id="surface.vertex",
            source=_source(
                PmxReferenceSourceSection.SURFACE_INDICES,
                index,
                f"surface_indices[{index}]",
            ),
            target_kind=PmxReferenceTargetKind.VERTEX,
            raw_index=vertex_index,
            target_counts=target_counts,
            allow_sentinel=False,
            edges=edges,
            invalid_targets=invalid_targets,
        )


def _extract_vertex_references(
    document: PmxDocument,
    *,
    target_counts: PmxReferenceTargetCounts,
    edges: list[PmxReferenceEdge],
    invalid_targets: list[PmxReferenceInvalidTarget],
    unsupported_states: list[PmxReferenceUnsupportedState],
) -> None:
    for vertex_index, vertex in enumerate(document.vertices):
        deform = vertex.deform

        if isinstance(deform, PmxBdef1):
            references = (
                (
                    "vertex.deform.bdef1.bone",
                    "deform.bone_index",
                    deform.bone_index,
                ),
            )
        elif isinstance(deform, (PmxBdef2, PmxBdef4, PmxSdef, PmxQdef)):
            if isinstance(deform, PmxQdef) and document.header.version < 2.1:
                for index, _ in enumerate(deform.bone_indices):
                    _record_unsupported(
                        kind=(
                            PmxReferenceUnsupportedStateKind.VERSION_CONDITION_MISMATCH
                        ),
                        relationship_id="vertex.deform.multi.bone",
                        source=_source(
                            PmxReferenceSourceSection.VERTICES,
                            vertex_index,
                            (
                                f"vertices[{vertex_index}].deform."
                                f"bone_indices[{index}]"
                            ),
                        ),
                        observed=f"pmx_version={document.header.version};qdef",
                        unsupported_states=unsupported_states,
                    )
                continue

            references = tuple(
                (
                    "vertex.deform.multi.bone",
                    f"deform.bone_indices[{index}]",
                    bone_index,
                )
                for index, bone_index in enumerate(deform.bone_indices)
            )
        else:
            continue

        for relationship_id, suffix, bone_index in references:
            _record_reference(
                relationship_id=relationship_id,
                source=_source(
                    PmxReferenceSourceSection.VERTICES,
                    vertex_index,
                    f"vertices[{vertex_index}].{suffix}",
                ),
                target_kind=PmxReferenceTargetKind.BONE,
                raw_index=bone_index,
                target_counts=target_counts,
                allow_sentinel=True,
                edges=edges,
                invalid_targets=invalid_targets,
            )


def _extract_material_references(
    document: PmxDocument,
    *,
    target_counts: PmxReferenceTargetCounts,
    edges: list[PmxReferenceEdge],
    invalid_targets: list[PmxReferenceInvalidTarget],
) -> None:
    for material_index, material in enumerate(document.materials):
        for relationship_id, field_name, raw_index in (
            ("material.texture", "texture_index", material.texture_index),
            (
                "material.sphere_texture",
                "sphere_texture_index",
                material.sphere_texture_index,
            ),
        ):
            _record_reference(
                relationship_id=relationship_id,
                source=_source(
                    PmxReferenceSourceSection.MATERIALS,
                    material_index,
                    f"materials[{material_index}].{field_name}",
                ),
                target_kind=PmxReferenceTargetKind.TEXTURE,
                raw_index=raw_index,
                target_counts=target_counts,
                allow_sentinel=True,
                edges=edges,
                invalid_targets=invalid_targets,
            )

        if material.toon_reference_mode == "texture":
            _record_reference(
                relationship_id="material.toon_texture",
                source=_source(
                    PmxReferenceSourceSection.MATERIALS,
                    material_index,
                    f"materials[{material_index}].toon_reference_index",
                ),
                target_kind=PmxReferenceTargetKind.TEXTURE,
                raw_index=material.toon_reference_index,
                target_counts=target_counts,
                allow_sentinel=True,
                edges=edges,
                invalid_targets=invalid_targets,
            )


def _extract_bone_references(
    document: PmxDocument,
    *,
    target_counts: PmxReferenceTargetCounts,
    edges: list[PmxReferenceEdge],
    invalid_targets: list[PmxReferenceInvalidTarget],
    unsupported_states: list[PmxReferenceUnsupportedState],
) -> None:
    inherit_mask = (
        PMX_BONE_FLAG_INHERIT_ROTATION | PMX_BONE_FLAG_INHERIT_TRANSLATION
    )

    for bone_index, bone in enumerate(document.bones):
        _record_reference(
            relationship_id="bone.parent",
            source=_source(
                PmxReferenceSourceSection.BONES,
                bone_index,
                f"bones[{bone_index}].parent_bone_index",
            ),
            target_kind=PmxReferenceTargetKind.BONE,
            raw_index=bone.parent_bone_index,
            target_counts=target_counts,
            allow_sentinel=True,
            edges=edges,
            invalid_targets=invalid_targets,
        )

        tail_active = bool(bone.flags & PMX_BONE_FLAG_TAIL_INDEX)
        tail_source = _source(
            PmxReferenceSourceSection.BONES,
            bone_index,
            f"bones[{bone_index}].tail_bone_index",
        )
        if tail_active:
            if bone.tail_bone_index is None:
                _record_unsupported(
                    kind=PmxReferenceUnsupportedStateKind.ACTIVE_PAYLOAD_MISSING,
                    relationship_id="bone.tail",
                    source=tail_source,
                    observed="tail_index_flag_enabled;tail_bone_index=None",
                    unsupported_states=unsupported_states,
                )
            else:
                _record_reference(
                    relationship_id="bone.tail",
                    source=tail_source,
                    target_kind=PmxReferenceTargetKind.BONE,
                    raw_index=bone.tail_bone_index,
                    target_counts=target_counts,
                    allow_sentinel=True,
                    edges=edges,
                    invalid_targets=invalid_targets,
                )
        elif bone.tail_bone_index is not None:
            _record_unsupported(
                kind=PmxReferenceUnsupportedStateKind.INACTIVE_PAYLOAD_PRESENT,
                relationship_id="bone.tail",
                source=tail_source,
                observed="tail_index_flag_disabled;tail_bone_index_present",
                unsupported_states=unsupported_states,
            )

        inherit_active = bool(bone.flags & inherit_mask)
        inherit_source = _source(
            PmxReferenceSourceSection.BONES,
            bone_index,
            f"bones[{bone_index}].inherit_parent_bone_index",
        )
        if inherit_active:
            if bone.inherit_parent_bone_index is None:
                _record_unsupported(
                    kind=PmxReferenceUnsupportedStateKind.ACTIVE_PAYLOAD_MISSING,
                    relationship_id="bone.inherit_parent",
                    source=inherit_source,
                    observed="inherit_flag_enabled;inherit_parent_bone_index=None",
                    unsupported_states=unsupported_states,
                )
            else:
                _record_reference(
                    relationship_id="bone.inherit_parent",
                    source=inherit_source,
                    target_kind=PmxReferenceTargetKind.BONE,
                    raw_index=bone.inherit_parent_bone_index,
                    target_counts=target_counts,
                    allow_sentinel=True,
                    edges=edges,
                    invalid_targets=invalid_targets,
                )
        elif bone.inherit_parent_bone_index is not None:
            _record_unsupported(
                kind=PmxReferenceUnsupportedStateKind.INACTIVE_PAYLOAD_PRESENT,
                relationship_id="bone.inherit_parent",
                source=inherit_source,
                observed="inherit_flag_disabled;inherit_parent_bone_index_present",
                unsupported_states=unsupported_states,
            )

        ik_active = bool(bone.flags & PMX_BONE_FLAG_IK)
        ik_source = _source(
            PmxReferenceSourceSection.BONES,
            bone_index,
            f"bones[{bone_index}].ik",
        )
        if ik_active:
            if bone.ik is None:
                _record_unsupported(
                    kind=PmxReferenceUnsupportedStateKind.ACTIVE_PAYLOAD_MISSING,
                    relationship_id="bone.ik_target",
                    source=ik_source,
                    observed="ik_flag_enabled;ik=None",
                    unsupported_states=unsupported_states,
                )
                continue

            _record_reference(
                relationship_id="bone.ik_target",
                source=_source(
                    PmxReferenceSourceSection.BONES,
                    bone_index,
                    f"bones[{bone_index}].ik.target_bone_index",
                ),
                target_kind=PmxReferenceTargetKind.BONE,
                raw_index=bone.ik.target_bone_index,
                target_counts=target_counts,
                allow_sentinel=False,
                edges=edges,
                invalid_targets=invalid_targets,
            )
            for link_index, link in enumerate(bone.ik.links):
                _record_reference(
                    relationship_id="bone.ik_link",
                    source=_source(
                        PmxReferenceSourceSection.BONES,
                        bone_index,
                        (
                            f"bones[{bone_index}].ik.links[{link_index}]."
                            "bone_index"
                        ),
                    ),
                    target_kind=PmxReferenceTargetKind.BONE,
                    raw_index=link.bone_index,
                    target_counts=target_counts,
                    allow_sentinel=False,
                    edges=edges,
                    invalid_targets=invalid_targets,
                )
        elif bone.ik is not None:
            _record_unsupported(
                kind=PmxReferenceUnsupportedStateKind.INACTIVE_PAYLOAD_PRESENT,
                relationship_id="bone.ik_target",
                source=ik_source,
                observed="ik_flag_disabled;ik_present",
                unsupported_states=unsupported_states,
            )


def _morph_relationship(
    morph_type: int,
) -> tuple[type[object], str, str, PmxReferenceTargetKind]:
    if morph_type == 0:
        return (
            PmxGroupMorphOffset,
            "morph.group.morph",
            "morph_index",
            PmxReferenceTargetKind.MORPH,
        )
    if morph_type == 1:
        return (
            PmxVertexMorphOffset,
            "morph.vertex.vertex",
            "vertex_index",
            PmxReferenceTargetKind.VERTEX,
        )
    if morph_type == 2:
        return (
            PmxBoneMorphOffset,
            "morph.bone.bone",
            "bone_index",
            PmxReferenceTargetKind.BONE,
        )
    if 3 <= morph_type <= 7:
        return (
            PmxUvMorphOffset,
            "morph.uv.vertex",
            "vertex_index",
            PmxReferenceTargetKind.VERTEX,
        )
    if morph_type == 8:
        return (
            PmxMaterialMorphOffset,
            "morph.material.material",
            "material_index",
            PmxReferenceTargetKind.MATERIAL,
        )
    if morph_type == 9:
        return (
            PmxFlipMorphOffset,
            "morph.flip.morph",
            "morph_index",
            PmxReferenceTargetKind.MORPH,
        )
    return (
        PmxImpulseMorphOffset,
        "morph.impulse.rigid_body",
        "rigid_body_index",
        PmxReferenceTargetKind.RIGID_BODY,
    )


def _extract_morph_references(
    document: PmxDocument,
    *,
    target_counts: PmxReferenceTargetCounts,
    edges: list[PmxReferenceEdge],
    invalid_targets: list[PmxReferenceInvalidTarget],
    unsupported_states: list[PmxReferenceUnsupportedState],
) -> None:
    for morph_index, morph in enumerate(document.morphs):
        (
            expected_type,
            relationship_id,
            target_field,
            target_kind,
        ) = _morph_relationship(morph.morph_type)

        for offset_index, offset in enumerate(morph.offsets):
            source = _source(
                PmxReferenceSourceSection.MORPHS,
                morph_index,
                (
                    f"morphs[{morph_index}].offsets[{offset_index}]."
                    f"{target_field}"
                ),
            )

            if not isinstance(offset, expected_type):
                _record_unsupported(
                    kind=PmxReferenceUnsupportedStateKind.MORPH_OFFSET_TYPE_MISMATCH,
                    relationship_id=relationship_id,
                    source=_source(
                        PmxReferenceSourceSection.MORPHS,
                        morph_index,
                        f"morphs[{morph_index}].offsets[{offset_index}]",
                    ),
                    observed=type(offset).__name__,
                    unsupported_states=unsupported_states,
                )
                continue

            if morph.morph_type in (9, 10) and document.header.version < 2.1:
                _record_unsupported(
                    kind=PmxReferenceUnsupportedStateKind.VERSION_CONDITION_MISMATCH,
                    relationship_id=relationship_id,
                    source=source,
                    observed=f"pmx_version={document.header.version}",
                    unsupported_states=unsupported_states,
                )
                continue

            if 4 <= morph.morph_type <= 7:
                required_layer = morph.morph_type - 3
                if document.header.additional_uv_count < required_layer:
                    _record_unsupported(
                        kind=(
                            PmxReferenceUnsupportedStateKind.UV_LAYER_CONDITION_MISMATCH
                        ),
                        relationship_id=relationship_id,
                        source=source,
                        observed=(
                            f"additional_uv_count="
                            f"{document.header.additional_uv_count};"
                            f"required_layer={required_layer}"
                        ),
                        unsupported_states=unsupported_states,
                    )
                    continue

            raw_index = getattr(offset, target_field)
            _record_reference(
                relationship_id=relationship_id,
                source=source,
                target_kind=target_kind,
                raw_index=raw_index,
                target_counts=target_counts,
                allow_sentinel=(morph.morph_type == 8),
                edges=edges,
                invalid_targets=invalid_targets,
            )


def _extract_display_frame_references(
    document: PmxDocument,
    *,
    target_counts: PmxReferenceTargetCounts,
    edges: list[PmxReferenceEdge],
    invalid_targets: list[PmxReferenceInvalidTarget],
) -> None:
    for frame_index, frame in enumerate(document.display_frames):
        for element_index, element in enumerate(frame.elements):
            if element.target_type == "bone":
                relationship_id = "display_frame.bone"
                target_kind = PmxReferenceTargetKind.BONE
            else:
                relationship_id = "display_frame.morph"
                target_kind = PmxReferenceTargetKind.MORPH

            _record_reference(
                relationship_id=relationship_id,
                source=_source(
                    PmxReferenceSourceSection.DISPLAY_FRAMES,
                    frame_index,
                    (
                        f"display_frames[{frame_index}].elements[{element_index}]."
                        "target_index"
                    ),
                ),
                target_kind=target_kind,
                raw_index=element.target_index,
                target_counts=target_counts,
                allow_sentinel=False,
                edges=edges,
                invalid_targets=invalid_targets,
            )


def _extract_physics_references(
    document: PmxDocument,
    *,
    target_counts: PmxReferenceTargetCounts,
    edges: list[PmxReferenceEdge],
    invalid_targets: list[PmxReferenceInvalidTarget],
    unsupported_states: list[PmxReferenceUnsupportedState],
) -> None:
    for body_index, body in enumerate(document.rigid_bodies):
        _record_reference(
            relationship_id="rigid_body.bone",
            source=_source(
                PmxReferenceSourceSection.RIGID_BODIES,
                body_index,
                f"rigid_bodies[{body_index}].bone_index",
            ),
            target_kind=PmxReferenceTargetKind.BONE,
            raw_index=body.bone_index,
            target_counts=target_counts,
            allow_sentinel=True,
            edges=edges,
            invalid_targets=invalid_targets,
        )

    for joint_index, joint in enumerate(document.joints):
        joint_references = (
            (
                "joint.rigid_body_a",
                "rigid_body_a_index",
                joint.rigid_body_a_index,
            ),
            (
                "joint.rigid_body_b",
                "rigid_body_b_index",
                joint.rigid_body_b_index,
            ),
        )
        if joint.joint_type != 0 and document.header.version < 2.1:
            for relationship_id, field_name, _ in joint_references:
                _record_unsupported(
                    kind=PmxReferenceUnsupportedStateKind.VERSION_CONDITION_MISMATCH,
                    relationship_id=relationship_id,
                    source=_source(
                        PmxReferenceSourceSection.JOINTS,
                        joint_index,
                        f"joints[{joint_index}].{field_name}",
                    ),
                    observed=(
                        f"pmx_version={document.header.version};"
                        f"joint_type={joint.joint_type}"
                    ),
                    unsupported_states=unsupported_states,
                )

        for relationship_id, field_name, raw_index in joint_references:
            _record_reference(
                relationship_id=relationship_id,
                source=_source(
                    PmxReferenceSourceSection.JOINTS,
                    joint_index,
                    f"joints[{joint_index}].{field_name}",
                ),
                target_kind=PmxReferenceTargetKind.RIGID_BODY,
                raw_index=raw_index,
                target_counts=target_counts,
                allow_sentinel=True,
                edges=edges,
                invalid_targets=invalid_targets,
            )

    for body_index, body in enumerate(document.soft_bodies):
        version_supported = document.header.version >= 2.1

        def record_soft_reference(
            relationship_id: str,
            path: str,
            target_kind: PmxReferenceTargetKind,
            raw_index: int,
            allow_sentinel: bool,
        ) -> None:
            source = _source(
                PmxReferenceSourceSection.SOFT_BODIES,
                body_index,
                path,
            )
            if not version_supported:
                _record_unsupported(
                    kind=PmxReferenceUnsupportedStateKind.VERSION_CONDITION_MISMATCH,
                    relationship_id=relationship_id,
                    source=source,
                    observed=f"pmx_version={document.header.version}",
                    unsupported_states=unsupported_states,
                )
                return
            _record_reference(
                relationship_id=relationship_id,
                source=source,
                target_kind=target_kind,
                raw_index=raw_index,
                target_counts=target_counts,
                allow_sentinel=allow_sentinel,
                edges=edges,
                invalid_targets=invalid_targets,
            )

        record_soft_reference(
            "soft_body.material",
            f"soft_bodies[{body_index}].material_index",
            PmxReferenceTargetKind.MATERIAL,
            body.material_index,
            True,
        )
        for anchor_index, anchor in enumerate(body.anchors):
            record_soft_reference(
                "soft_body.anchor.rigid_body",
                (
                    f"soft_bodies[{body_index}].anchors[{anchor_index}]."
                    "rigid_body_index"
                ),
                PmxReferenceTargetKind.RIGID_BODY,
                anchor.rigid_body_index,
                False,
            )
            record_soft_reference(
                "soft_body.anchor.vertex",
                (
                    f"soft_bodies[{body_index}].anchors[{anchor_index}]."
                    "vertex_index"
                ),
                PmxReferenceTargetKind.VERTEX,
                anchor.vertex_index,
                False,
            )
        for pin_index, vertex_index in enumerate(body.pinned_vertex_indices):
            record_soft_reference(
                "soft_body.pin.vertex",
                f"soft_bodies[{body_index}].pinned_vertex_indices[{pin_index}]",
                PmxReferenceTargetKind.VERTEX,
                vertex_index,
                False,
            )


def extract_pmx_reference_graph(document: PmxDocument) -> PmxReferenceGraph:
    """Extract every currently supported active PMX reference deterministically."""

    if not isinstance(document, PmxDocument):
        raise TypeError("document must be a PmxDocument instance.")

    target_counts = PmxReferenceTargetCounts(
        vertex=len(document.vertices),
        texture=len(document.texture_paths),
        material=len(document.materials),
        bone=len(document.bones),
        morph=len(document.morphs),
        rigid_body=len(document.rigid_bodies),
    )
    edges: list[PmxReferenceEdge] = []
    invalid_targets: list[PmxReferenceInvalidTarget] = []
    unsupported_states: list[PmxReferenceUnsupportedState] = []

    _extract_surface_references(
        document,
        target_counts=target_counts,
        edges=edges,
        invalid_targets=invalid_targets,
    )
    _extract_vertex_references(
        document,
        target_counts=target_counts,
        edges=edges,
        invalid_targets=invalid_targets,
        unsupported_states=unsupported_states,
    )
    _extract_material_references(
        document,
        target_counts=target_counts,
        edges=edges,
        invalid_targets=invalid_targets,
    )
    _extract_bone_references(
        document,
        target_counts=target_counts,
        edges=edges,
        invalid_targets=invalid_targets,
        unsupported_states=unsupported_states,
    )
    _extract_morph_references(
        document,
        target_counts=target_counts,
        edges=edges,
        invalid_targets=invalid_targets,
        unsupported_states=unsupported_states,
    )
    _extract_display_frame_references(
        document,
        target_counts=target_counts,
        edges=edges,
        invalid_targets=invalid_targets,
    )
    _extract_physics_references(
        document,
        target_counts=target_counts,
        edges=edges,
        invalid_targets=invalid_targets,
        unsupported_states=unsupported_states,
    )

    return PmxReferenceGraph(
        target_counts=target_counts,
        edges=tuple(edges),
        invalid_targets=tuple(invalid_targets),
        unsupported_states=tuple(unsupported_states),
    )


__all__ = (
    "PmxReferenceGraph",
    "PmxReferenceInvalidTarget",
    "PmxReferenceTargetCounts",
    "PmxReferenceUnsupportedState",
    "PmxReferenceUnsupportedStateKind",
    "extract_pmx_reference_graph",
)
