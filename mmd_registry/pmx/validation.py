"""Cross-section validation for complete PMX documents before writing."""

from __future__ import annotations

import math
from dataclasses import fields, is_dataclass
from typing import Iterable

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
from mmd_registry.pmx.errors import PmxValidationError


MIN_INT32 = -(2**31)
MAX_INT32 = 2**31 - 1


def _fail(
    section: str,
    field: str,
    reason: str,
    *,
    record_index: int | None = None,
) -> None:
    """Raise one stable contextual validation error."""

    raise PmxValidationError(
        section=section,
        record_index=record_index,
        field=field,
        reason=reason,
    )


def _validate_count(
    value: int,
    *,
    section: str,
    field: str,
    record_index: int | None = None,
) -> None:
    """Require a count representable by the PMX signed 32-bit count field."""

    if not 0 <= value <= MAX_INT32:
        _fail(
            section,
            field,
            f"count {value} cannot be represented as a signed 32-bit integer.",
            record_index=record_index,
        )


def _validate_int32(
    value: int,
    *,
    section: str,
    field: str,
    record_index: int | None = None,
) -> None:
    """Require one signed 32-bit integer field."""

    if not MIN_INT32 <= value <= MAX_INT32:
        _fail(
            section,
            field,
            f"value {value} cannot be represented as a signed 32-bit integer.",
            record_index=record_index,
        )


def _validate_nonnegative_int32(
    value: int,
    *,
    section: str,
    field: str,
    record_index: int | None = None,
) -> None:
    """Require one nonnegative signed 32-bit integer field."""

    _validate_int32(
        value,
        section=section,
        field=field,
        record_index=record_index,
    )
    if value < 0:
        _fail(
            section,
            field,
            f"value {value} cannot be negative.",
            record_index=record_index,
        )


def _validate_nonnegative_float(
    value: float,
    *,
    section: str,
    field: str,
    record_index: int,
) -> None:
    """Require one finite value already checked by the document-tree pass."""

    if value < 0.0:
        _fail(
            section,
            field,
            f"value {value} cannot be negative.",
            record_index=record_index,
        )


def _validate_index_capacity(
    count: int,
    *,
    size: int,
    signed: bool,
    section: str,
) -> None:
    """Require a declared index width capable of naming every record."""

    maximum = (1 << (size * 8 - (1 if signed else 0))) - 1
    if count and count - 1 > maximum:
        _fail(
            "header",
            f"index_sizes.{section}",
            (
                f"{size}-byte index cannot address {count} {section} records; "
                f"maximum addressable count is {maximum + 1}."
            ),
        )


def _validate_reference(
    value: int,
    *,
    count: int,
    section: str,
    field: str,
    record_index: int,
    allow_sentinel: bool,
) -> None:
    """Validate one reference to a counted PMX section."""

    minimum = -1 if allow_sentinel else 0
    if value < minimum or value >= count:
        expected = (
            f"-1 or 0 through {count - 1}"
            if allow_sentinel and count
            else "-1"
            if allow_sentinel
            else f"0 through {count - 1}"
            if count
            else "no value"
        )
        _fail(
            section,
            field,
            f"index {value} is invalid; expected {expected}.",
            record_index=record_index,
        )


def _validate_text(
    value: str,
    *,
    encoding: str,
    section: str,
    field: str,
    record_index: int | None = None,
) -> None:
    """Require text encodable into one PMX length-prefixed field."""

    try:
        encoded = value.encode(encoding, errors="strict")
    except UnicodeEncodeError as error:
        _fail(
            section,
            field,
            f"text cannot be encoded as {encoding}: {error}.",
            record_index=record_index,
        )

    if len(encoded) > MAX_INT32:
        _fail(
            section,
            field,
            "encoded text exceeds the signed 32-bit PMX length limit.",
            record_index=record_index,
        )


def _validate_finite_tree(value: object, path: str = "") -> None:
    """Reject non-finite floats anywhere in the immutable document tree."""

    if isinstance(value, float):
        if not math.isfinite(value):
            _fail("document", path, "floating-point value must be finite.")
        return

    if isinstance(value, tuple):
        for index, item in enumerate(value):
            item_path = f"{path}[{index}]"
            _validate_finite_tree(item, item_path)
        return

    if is_dataclass(value):
        for item in fields(value):
            item_path = f"{path}.{item.name}" if path else item.name
            _validate_finite_tree(
                getattr(value, item.name),
                item_path,
            )


def _iter_document_text(
    document: PmxDocument,
) -> Iterable[tuple[str, int | None, str, str]]:
    """Yield section, record index, field name, and every stored text value."""

    for field_name in (
        "local_name",
        "universal_name",
        "local_comments",
        "universal_comments",
    ):
        yield "model_info", None, field_name, getattr(document.model_info, field_name)

    for index, texture_path in enumerate(document.texture_paths):
        yield "textures", index, "path", texture_path

    for section, records in (
        ("materials", document.materials),
        ("bones", document.bones),
        ("morphs", document.morphs),
        ("display_frames", document.display_frames),
        ("rigid_bodies", document.rigid_bodies),
        ("joints", document.joints),
        ("soft_bodies", document.soft_bodies),
    ):
        for index, record in enumerate(records):
            yield section, index, "local_name", record.local_name
            yield section, index, "universal_name", record.universal_name
            if section == "materials":
                yield section, index, "memo", record.memo


def _validate_geometry(document: PmxDocument) -> None:
    """Validate geometry counts, deforms, and references."""

    vertex_count = len(document.vertices)
    bone_count = len(document.bones)
    _validate_count(vertex_count, section="vertices", field="count")
    _validate_count(
        len(document.surface_indices),
        section="surface_indices",
        field="count",
    )

    for index, vertex in enumerate(document.vertices):
        if len(vertex.additional_uvs) != document.header.additional_uv_count:
            _fail(
                "vertices",
                "additional_uvs",
                (
                    f"contains {len(vertex.additional_uvs)} vectors but header "
                    f"declares {document.header.additional_uv_count}."
                ),
                record_index=index,
            )

        deform = vertex.deform
        if isinstance(deform, PmxBdef1):
            bone_indices = (deform.bone_index,)
        elif isinstance(deform, (PmxBdef2, PmxSdef)):
            bone_indices = deform.bone_indices
        elif isinstance(deform, (PmxBdef4, PmxQdef)):
            bone_indices = deform.bone_indices
        else:
            _fail(
                "vertices",
                "deform",
                "unsupported deform record.",
                record_index=index,
            )

        if isinstance(deform, PmxQdef) and document.header.version < 2.1:
            _fail(
                "vertices",
                "deform",
                "QDEF requires PMX 2.1.",
                record_index=index,
            )

        for bone_index_index, bone_index in enumerate(bone_indices):
            _validate_reference(
                bone_index,
                count=bone_count,
                section="vertices",
                field=f"deform.bone_indices[{bone_index_index}]",
                record_index=index,
                allow_sentinel=True,
            )

    for index, vertex_index in enumerate(document.surface_indices):
        _validate_reference(
            vertex_index,
            count=vertex_count,
            section="surface_indices",
            field="vertex_index",
            record_index=index,
            allow_sentinel=False,
        )


def _validate_materials(document: PmxDocument) -> None:
    """Validate material references and exact surface coverage."""

    texture_count = len(document.texture_paths)
    surface_count = len(document.surface_indices)
    total_material_surfaces = 0

    for index, material in enumerate(document.materials):
        for field_name in ("texture_index", "sphere_texture_index"):
            _validate_reference(
                getattr(material, field_name),
                count=texture_count,
                section="materials",
                field=field_name,
                record_index=index,
                allow_sentinel=True,
            )

        if material.toon_reference_mode == "texture":
            _validate_reference(
                material.toon_reference_index,
                count=texture_count,
                section="materials",
                field="toon_reference_index",
                record_index=index,
                allow_sentinel=True,
            )

        _validate_count(
            material.surface_index_count,
            section="materials",
            field="surface_index_count",
            record_index=index,
        )
        if material.surface_index_count % 3:
            _fail(
                "materials",
                "surface_index_count",
                "value must be divisible by 3.",
                record_index=index,
            )
        total_material_surfaces += material.surface_index_count

    if total_material_surfaces != surface_count:
        _fail(
            "materials",
            "surface_index_count",
            (
                f"materials cover {total_material_surfaces} indices but geometry "
                f"contains {surface_count}."
            ),
        )


def _validate_bones(document: PmxDocument) -> None:
    """Validate bone references and flag-controlled payload consistency."""

    bone_count = len(document.bones)
    inherit_mask = (
        PMX_BONE_FLAG_INHERIT_ROTATION | PMX_BONE_FLAG_INHERIT_TRANSLATION
    )

    for index, bone in enumerate(document.bones):
        _validate_reference(
            bone.parent_bone_index,
            count=bone_count,
            section="bones",
            field="parent_bone_index",
            record_index=index,
            allow_sentinel=True,
        )
        _validate_int32(
            bone.transform_layer,
            section="bones",
            field="transform_layer",
            record_index=index,
        )

        tail_uses_index = bool(bone.flags & PMX_BONE_FLAG_TAIL_INDEX)
        if tail_uses_index:
            if bone.tail_mode != "bone" or bone.tail_bone_index is None:
                _fail(
                    "bones",
                    "tail_bone_index",
                    "tail-index flag requires a bone tail reference.",
                    record_index=index,
                )
            if bone.tail_offset is not None:
                _fail(
                    "bones",
                    "tail_offset",
                    "tail-index flag cannot retain a tail offset.",
                    record_index=index,
                )
            _validate_reference(
                bone.tail_bone_index,
                count=bone_count,
                section="bones",
                field="tail_bone_index",
                record_index=index,
                allow_sentinel=True,
            )
        elif bone.tail_mode != "offset" or bone.tail_offset is None:
            _fail(
                "bones",
                "tail_offset",
                "offset-tail mode requires a tail vector.",
                record_index=index,
            )
        elif bone.tail_bone_index is not None:
            _fail(
                "bones",
                "tail_bone_index",
                "offset-tail mode cannot retain a bone reference.",
                record_index=index,
            )

        has_inherit = bool(bone.flags & inherit_mask)
        if has_inherit:
            if bone.inherit_parent_bone_index is None or bone.inherit_weight is None:
                _fail(
                    "bones",
                    "inherit_parent_bone_index",
                    "inherit flags require parent index and weight.",
                    record_index=index,
                )
            _validate_reference(
                bone.inherit_parent_bone_index,
                count=bone_count,
                section="bones",
                field="inherit_parent_bone_index",
                record_index=index,
                allow_sentinel=True,
            )
        elif (
            bone.inherit_parent_bone_index is not None
            or bone.inherit_weight is not None
        ):
            _fail(
                "bones",
                "inherit_parent_bone_index",
                "inherit payload requires an inherit flag.",
                record_index=index,
            )

        optional_flag_fields = (
            (PMX_BONE_FLAG_FIXED_AXIS, "fixed_axis", (bone.fixed_axis,)),
            (
                PMX_BONE_FLAG_LOCAL_AXES,
                "local_axes",
                (bone.local_axis_x, bone.local_axis_z),
            ),
            (
                PMX_BONE_FLAG_EXTERNAL_PARENT,
                "external_parent_key",
                (bone.external_parent_key,),
            ),
            (PMX_BONE_FLAG_IK, "ik", (bone.ik,)),
        )
        for flag, field_name, values in optional_flag_fields:
            enabled = bool(bone.flags & flag)
            if enabled and any(value is None for value in values):
                _fail(
                    "bones",
                    field_name,
                    "enabled flag requires its payload.",
                    record_index=index,
                )
            if not enabled and any(value is not None for value in values):
                _fail(
                    "bones",
                    field_name,
                    "payload requires its corresponding flag.",
                    record_index=index,
                )

        if bone.external_parent_key is not None:
            _validate_int32(
                bone.external_parent_key,
                section="bones",
                field="external_parent_key",
                record_index=index,
            )

        if bone.ik is not None:
            _validate_reference(
                bone.ik.target_bone_index,
                count=bone_count,
                section="bones",
                field="ik.target_bone_index",
                record_index=index,
                allow_sentinel=False,
            )
            _validate_nonnegative_int32(
                bone.ik.loop_count,
                section="bones",
                field="ik.loop_count",
                record_index=index,
            )
            _validate_count(
                len(bone.ik.links),
                section="bones",
                field="ik.links",
                record_index=index,
            )
            for link_index, link in enumerate(bone.ik.links):
                _validate_reference(
                    link.bone_index,
                    count=bone_count,
                    section="bones",
                    field=f"ik.links[{link_index}].bone_index",
                    record_index=index,
                    allow_sentinel=False,
                )


def _validate_morphs(document: PmxDocument) -> None:
    """Validate morph variants, versions, and cross-section references."""

    expected_types = {
        0: PmxGroupMorphOffset,
        1: PmxVertexMorphOffset,
        2: PmxBoneMorphOffset,
        3: PmxUvMorphOffset,
        4: PmxUvMorphOffset,
        5: PmxUvMorphOffset,
        6: PmxUvMorphOffset,
        7: PmxUvMorphOffset,
        8: PmxMaterialMorphOffset,
        9: PmxFlipMorphOffset,
        10: PmxImpulseMorphOffset,
    }
    counts = {
        "vertex": len(document.vertices),
        "bone": len(document.bones),
        "material": len(document.materials),
        "morph": len(document.morphs),
        "rigid_body": len(document.rigid_bodies),
    }

    for index, morph in enumerate(document.morphs):
        if morph.morph_type in (9, 10) and document.header.version < 2.1:
            _fail(
                "morphs",
                "morph_type",
                f"type {morph.morph_type} requires PMX 2.1.",
                record_index=index,
            )
        if 4 <= morph.morph_type <= 7:
            required_layer = morph.morph_type - 3
            if document.header.additional_uv_count < required_layer:
                _fail(
                    "morphs",
                    "morph_type",
                    f"type requires additional UV layer {required_layer}.",
                    record_index=index,
                )

        _validate_count(
            len(morph.offsets),
            section="morphs",
            field="offsets",
            record_index=index,
        )
        expected_type = expected_types[morph.morph_type]
        for offset_index, offset in enumerate(morph.offsets):
            field = f"offsets[{offset_index}]"
            if not isinstance(offset, expected_type):
                _fail(
                    "morphs",
                    field,
                    f"type {morph.morph_type} requires {expected_type.__name__}.",
                    record_index=index,
                )

            if isinstance(offset, (PmxGroupMorphOffset, PmxFlipMorphOffset)):
                target_value, target_count, allow_sentinel = (
                    offset.morph_index,
                    counts["morph"],
                    False,
                )
            elif isinstance(offset, (PmxVertexMorphOffset, PmxUvMorphOffset)):
                target_value, target_count, allow_sentinel = (
                    offset.vertex_index,
                    counts["vertex"],
                    False,
                )
            elif isinstance(offset, PmxBoneMorphOffset):
                target_value, target_count, allow_sentinel = (
                    offset.bone_index,
                    counts["bone"],
                    False,
                )
            elif isinstance(offset, PmxMaterialMorphOffset):
                target_value, target_count, allow_sentinel = (
                    offset.material_index,
                    counts["material"],
                    True,
                )
            else:
                target_value, target_count, allow_sentinel = (
                    offset.rigid_body_index,
                    counts["rigid_body"],
                    False,
                )

            _validate_reference(
                target_value,
                count=target_count,
                section="morphs",
                field=field,
                record_index=index,
                allow_sentinel=allow_sentinel,
            )


def _validate_display_and_physics(document: PmxDocument) -> None:
    """Validate display-frame and physics cross-section references."""

    bone_count = len(document.bones)
    morph_count = len(document.morphs)
    rigid_body_count = len(document.rigid_bodies)
    material_count = len(document.materials)
    vertex_count = len(document.vertices)

    for index, frame in enumerate(document.display_frames):
        _validate_count(
            len(frame.elements),
            section="display_frames",
            field="elements",
            record_index=index,
        )
        for element_index, element in enumerate(frame.elements):
            _validate_reference(
                element.target_index,
                count=(bone_count if element.target_type == "bone" else morph_count),
                section="display_frames",
                field=f"elements[{element_index}].target_index",
                record_index=index,
                allow_sentinel=False,
            )

    for index, body in enumerate(document.rigid_bodies):
        _validate_reference(
            body.bone_index,
            count=bone_count,
            section="rigid_bodies",
            field="bone_index",
            record_index=index,
            allow_sentinel=True,
        )
        for component_index, component in enumerate(body.size):
            _validate_nonnegative_float(
                component,
                section="rigid_bodies",
                field=f"size[{component_index}]",
                record_index=index,
            )
        for field_name in (
            "mass",
            "linear_damping",
            "angular_damping",
            "restitution",
            "friction",
        ):
            _validate_nonnegative_float(
                getattr(body, field_name),
                section="rigid_bodies",
                field=field_name,
                record_index=index,
            )

    for index, joint in enumerate(document.joints):
        if joint.joint_type != 0 and document.header.version < 2.1:
            _fail(
                "joints",
                "joint_type",
                f"type {joint.joint_type} requires PMX 2.1.",
                record_index=index,
            )
        for field_name in ("rigid_body_a_index", "rigid_body_b_index"):
            _validate_reference(
                getattr(joint, field_name),
                count=rigid_body_count,
                section="joints",
                field=field_name,
                record_index=index,
                allow_sentinel=True,
            )

    if document.header.version == 2.0 and document.soft_bodies:
        _fail(
            "soft_bodies",
            "count",
            "PMX 2.0 cannot contain a soft-body section.",
        )

    for index, body in enumerate(document.soft_bodies):
        if body.flags & ~0x07:
            _fail(
                "soft_bodies",
                "flags",
                f"unknown flag bits 0x{body.flags & ~0x07:02x}.",
                record_index=index,
            )
        _validate_reference(
            body.material_index,
            count=material_count,
            section="soft_bodies",
            field="material_index",
            record_index=index,
            allow_sentinel=True,
        )
        for field_name in ("bending_link_distance", "cluster_count"):
            _validate_nonnegative_int32(
                getattr(body, field_name),
                section="soft_bodies",
                field=field_name,
                record_index=index,
            )
        for field_name in ("total_mass", "collision_margin"):
            _validate_nonnegative_float(
                getattr(body, field_name),
                section="soft_bodies",
                field=field_name,
                record_index=index,
            )
        for config_field in ("velocity", "position", "drift", "cluster"):
            _validate_nonnegative_int32(
                getattr(body.iteration_config, config_field),
                section="soft_bodies",
                field=f"iteration_config.{config_field}",
                record_index=index,
            )
        _validate_count(
            len(body.anchors),
            section="soft_bodies",
            field="anchors",
            record_index=index,
        )
        _validate_count(
            len(body.pinned_vertex_indices),
            section="soft_bodies",
            field="pinned_vertex_indices",
            record_index=index,
        )
        for anchor_index, anchor in enumerate(body.anchors):
            _validate_reference(
                anchor.rigid_body_index,
                count=rigid_body_count,
                section="soft_bodies",
                field=f"anchors[{anchor_index}].rigid_body_index",
                record_index=index,
                allow_sentinel=False,
            )
            _validate_reference(
                anchor.vertex_index,
                count=vertex_count,
                section="soft_bodies",
                field=f"anchors[{anchor_index}].vertex_index",
                record_index=index,
                allow_sentinel=False,
            )
        for pin_index, vertex_index in enumerate(body.pinned_vertex_indices):
            _validate_reference(
                vertex_index,
                count=vertex_count,
                section="soft_bodies",
                field=f"pinned_vertex_indices[{pin_index}]",
                record_index=index,
                allow_sentinel=False,
            )


def validate_pmx_document(document: PmxDocument) -> None:
    """Validate all invariants required for deterministic PMX serialization."""

    if not isinstance(document, PmxDocument):
        raise TypeError("document must be a PmxDocument instance.")

    counts = (
        ("vertices", len(document.vertices)),
        ("surface_indices", len(document.surface_indices)),
        ("texture", len(document.texture_paths)),
        ("material", len(document.materials)),
        ("bone", len(document.bones)),
        ("morph", len(document.morphs)),
        ("display_frames", len(document.display_frames)),
        ("rigid_body", len(document.rigid_bodies)),
        ("joints", len(document.joints)),
        ("soft_bodies", len(document.soft_bodies)),
    )
    for section, count in counts:
        _validate_count(count, section=section, field="count")

    index_sizes = document.header.index_sizes
    for section, count, size, signed in (
        ("vertex", len(document.vertices), index_sizes.vertex, False),
        ("texture", len(document.texture_paths), index_sizes.texture, True),
        ("material", len(document.materials), index_sizes.material, True),
        ("bone", len(document.bones), index_sizes.bone, True),
        ("morph", len(document.morphs), index_sizes.morph, True),
        ("rigid_body", len(document.rigid_bodies), index_sizes.rigid_body, True),
    ):
        _validate_index_capacity(
            count,
            size=size,
            signed=signed,
            section=section,
        )

    for section, record_index, field_name, text in _iter_document_text(document):
        _validate_text(
            text,
            encoding=document.header.encoding,
            section=section,
            field=field_name,
            record_index=record_index,
        )

    _validate_finite_tree(document)
    _validate_geometry(document)
    _validate_materials(document)
    _validate_bones(document)
    _validate_morphs(document)
    _validate_display_and_physics(document)
