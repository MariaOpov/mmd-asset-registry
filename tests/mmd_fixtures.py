"""Programmatic PMX/PMD binary fixtures for unit tests."""

from __future__ import annotations

import struct


def build_minimal_pmx_header(
    model_name: str = "Test PMX Model",
    *,
    encoding_flag: int = 1,
    version: float = 2.0,
) -> bytes:
    """Build a minimal PMX header through its first model-name field."""

    if encoding_flag == 0:
        name_data = model_name.encode("utf-16-le")
    else:
        name_data = model_name.encode("utf-8")

    globals_data = bytes(
        [
            encoding_flag,
            0,
            1,
            1,
            1,
            1,
            1,
            1,
        ]
    )

    return b"".join(
        [
            b"PMX ",
            struct.pack("<f", version),
            struct.pack("<B", len(globals_data)),
            globals_data,
            struct.pack("<i", len(name_data)),
            name_data,
        ]
    )


def build_minimal_pmd_header(
    model_name: str = "Test PMD Model",
    *,
    version: float = 1.0,
) -> bytes:
    """Build a minimal PMD header through its fixed model-name field."""

    name_data = model_name.encode("cp932")

    if len(name_data) > 20:
        raise ValueError("PMD fixture model name must fit in 20 bytes.")

    return b"".join(
        [
            b"Pmd",
            struct.pack("<f", version),
            name_data.ljust(20, b"\x00"),
        ]
    )


def _encode_pmx_text(
    value: str,
    encoding_flag: int,
) -> bytes:
    """Encode one PMX length-prefixed text field."""

    if encoding_flag == 0:
        data = value.encode("utf-16-le")
    else:
        data = value.encode("utf-8")

    return struct.pack("<i", len(data)) + data


def build_pmx_model_info(
    local_name: str = "Test PMX Model",
    universal_name: str = "Test PMX Model",
    local_comments: str = "",
    universal_comments: str = "",
    *,
    encoding_flag: int = 1,
    version: float = 2.0,
    additional_uv_count: int = 0,
    vertex_index_size: int = 1,
    texture_index_size: int = 1,
    material_index_size: int = 1,
    bone_index_size: int = 1,
    morph_index_size: int = 1,
    rigid_body_index_size: int = 1,
    extra_globals: bytes = b"",
    globals_override: bytes | None = None,
) -> bytes:
    """Build a PMX file through all four model-information fields."""

    if globals_override is None:
        globals_data = (
            bytes(
                [
                    encoding_flag,
                    additional_uv_count,
                    vertex_index_size,
                    texture_index_size,
                    material_index_size,
                    bone_index_size,
                    morph_index_size,
                    rigid_body_index_size,
                ]
            )
            + extra_globals
        )
    else:
        globals_data = globals_override

    if len(globals_data) > 255:
        raise ValueError("PMX fixture globals must fit in one unsigned byte.")

    return b"".join(
        [
            b"PMX ",
            struct.pack("<f", version),
            struct.pack("<B", len(globals_data)),
            globals_data,
            _encode_pmx_text(
                local_name,
                encoding_flag,
            ),
            _encode_pmx_text(
                universal_name,
                encoding_flag,
            ),
            _encode_pmx_text(
                local_comments,
                encoding_flag,
            ),
            _encode_pmx_text(
                universal_comments,
                encoding_flag,
            ),
        ]
    )


def _pack_pmx_index(
    value: int,
    *,
    size: int,
    signed: bool,
) -> bytes:
    """Pack one PMX index using a declared width."""

    format_codes = {
        (1, False): "<B",
        (1, True): "<b",
        (2, False): "<H",
        (2, True): "<h",
        (4, False): "<I",
        (4, True): "<i",
    }

    try:
        format_code = format_codes[(size, signed)]
    except KeyError as error:
        raise ValueError("PMX fixture index size must be 1, 2, or 4.") from error

    return struct.pack(
        format_code,
        value,
    )


def build_pmx_vertex(
    *,
    deform_type: int = 0,
    additional_uv_count: int = 0,
    bone_index_size: int = 1,
) -> bytes:
    """Build one small PMX vertex record."""

    parts = [
        struct.pack(
            "<8f",
            0.0,
            0.0,
            0.0,
            0.0,
            1.0,
            0.0,
            0.0,
            0.0,
        ),
        b"\x00" * (additional_uv_count * 16),
        struct.pack(
            "<B",
            deform_type,
        ),
    ]

    bone_index = _pack_pmx_index(
        0,
        size=bone_index_size,
        signed=True,
    )

    if deform_type == 0:
        parts.append(bone_index)

    elif deform_type == 1:
        parts.extend(
            [
                bone_index * 2,
                struct.pack("<f", 0.5),
            ]
        )

    elif deform_type in {2, 4}:
        parts.extend(
            [
                bone_index * 4,
                struct.pack(
                    "<4f",
                    0.25,
                    0.25,
                    0.25,
                    0.25,
                ),
            ]
        )

    elif deform_type == 3:
        parts.extend(
            [
                bone_index * 2,
                struct.pack("<f", 0.5),
                struct.pack(
                    "<9f",
                    *([0.0] * 9),
                ),
            ]
        )

    parts.append(struct.pack("<f", 1.0))

    return b"".join(parts)


def build_pmx_material(
    *,
    local_name: str = "Material",
    universal_name: str = "Material",
    texture_index: int = -1,
    sphere_texture_index: int = -1,
    sphere_mode: int = 0,
    toon_reference_mode: int = 1,
    toon_reference_index: int = 0,
    memo: str = "",
    surface_index_count: int = 0,
    encoding_flag: int = 1,
    texture_index_size: int = 1,
) -> bytes:
    """Build one PMX material record for structural scanner tests."""

    parts = [
        _encode_pmx_text(
            local_name,
            encoding_flag,
        ),
        _encode_pmx_text(
            universal_name,
            encoding_flag,
        ),
        struct.pack(
            "<4f",
            1.0,
            1.0,
            1.0,
            1.0,
        ),
        struct.pack(
            "<3f",
            0.0,
            0.0,
            0.0,
        ),
        struct.pack("<f", 0.0),
        struct.pack(
            "<3f",
            0.5,
            0.5,
            0.5,
        ),
        struct.pack("<B", 0),
        struct.pack(
            "<4f",
            0.0,
            0.0,
            0.0,
            1.0,
        ),
        struct.pack("<f", 1.0),
        _pack_pmx_index(
            texture_index,
            size=texture_index_size,
            signed=True,
        ),
        _pack_pmx_index(
            sphere_texture_index,
            size=texture_index_size,
            signed=True,
        ),
        struct.pack("<B", sphere_mode),
        struct.pack("<B", toon_reference_mode),
    ]

    if toon_reference_mode == 0:
        parts.append(
            _pack_pmx_index(
                toon_reference_index,
                size=texture_index_size,
                signed=True,
            )
        )
    else:
        parts.append(
            struct.pack(
                "<B",
                toon_reference_index,
            )
        )

    parts.extend(
        [
            _encode_pmx_text(
                memo,
                encoding_flag,
            ),
            struct.pack(
                "<i",
                surface_index_count,
            ),
        ]
    )

    return b"".join(parts)


def build_pmx_ik_link(
    *,
    bone_index: int = 0,
    angle_limit_flag: int = 0,
    lower_limit: tuple[float, float, float] = (
        -0.5,
        -0.5,
        -0.5,
    ),
    upper_limit: tuple[float, float, float] = (
        0.5,
        0.5,
        0.5,
    ),
    bone_index_size: int = 1,
) -> bytes:
    """Build one PMX IK-link record."""

    parts = [
        _pack_pmx_index(
            bone_index,
            size=bone_index_size,
            signed=True,
        ),
        struct.pack("<B", angle_limit_flag),
    ]

    if angle_limit_flag == 1:
        parts.extend(
            [
                struct.pack("<3f", *lower_limit),
                struct.pack("<3f", *upper_limit),
            ]
        )

    return b"".join(parts)


def build_pmx_bone(
    *,
    local_name: str = "Bone",
    universal_name: str = "Bone",
    position: tuple[float, float, float] = (
        0.0,
        0.0,
        0.0,
    ),
    parent_bone_index: int = -1,
    transform_layer: int = 0,
    tail_bone_index: int | None = None,
    tail_offset: tuple[float, float, float] = (
        0.0,
        1.0,
        0.0,
    ),
    inherit_rotation: bool = False,
    inherit_translation: bool = False,
    inherit_parent_bone_index: int = -1,
    inherit_weight: float = 0.0,
    fixed_axis: tuple[float, float, float] | None = None,
    local_axes: tuple[
        tuple[float, float, float],
        tuple[float, float, float],
    ]
    | None = None,
    external_parent_key: int | None = None,
    ik_target_bone_index: int | None = None,
    ik_loop_count: int = 1,
    ik_angle_limit: float = 0.5,
    ik_links: tuple[bytes, ...] = (),
    ik_link_count_override: int | None = None,
    extra_flags: int = 0,
    flags_override: int | None = None,
    encoding_flag: int = 1,
    bone_index_size: int = 1,
) -> bytes:
    """Build one PMX bone record with flag-controlled fields."""

    if flags_override is None:
        flags = extra_flags

        if tail_bone_index is not None:
            flags |= 0x0001
        if inherit_rotation:
            flags |= 0x0100
        if inherit_translation:
            flags |= 0x0200
        if fixed_axis is not None:
            flags |= 0x0400
        if local_axes is not None:
            flags |= 0x0800
        if external_parent_key is not None:
            flags |= 0x2000
        if ik_target_bone_index is not None:
            flags |= 0x0020
    else:
        flags = flags_override

    parts = [
        _encode_pmx_text(
            local_name,
            encoding_flag,
        ),
        _encode_pmx_text(
            universal_name,
            encoding_flag,
        ),
        struct.pack("<3f", *position),
        _pack_pmx_index(
            parent_bone_index,
            size=bone_index_size,
            signed=True,
        ),
        struct.pack("<i", transform_layer),
        struct.pack("<H", flags),
    ]

    if flags & 0x0001:
        parts.append(
            _pack_pmx_index(
                (-1 if tail_bone_index is None else tail_bone_index),
                size=bone_index_size,
                signed=True,
            )
        )
    else:
        parts.append(struct.pack("<3f", *tail_offset))

    if flags & (0x0100 | 0x0200):
        parts.extend(
            [
                _pack_pmx_index(
                    inherit_parent_bone_index,
                    size=bone_index_size,
                    signed=True,
                ),
                struct.pack("<f", inherit_weight),
            ]
        )

    if flags & 0x0400:
        axis = (1.0, 0.0, 0.0) if fixed_axis is None else fixed_axis
        parts.append(struct.pack("<3f", *axis))

    if flags & 0x0800:
        axes = (
            (
                (1.0, 0.0, 0.0),
                (0.0, 0.0, 1.0),
            )
            if local_axes is None
            else local_axes
        )
        parts.extend(
            [
                struct.pack("<3f", *axes[0]),
                struct.pack("<3f", *axes[1]),
            ]
        )

    if flags & 0x2000:
        parts.append(
            struct.pack(
                "<i",
                (0 if external_parent_key is None else external_parent_key),
            )
        )

    if flags & 0x0020:
        parts.extend(
            [
                _pack_pmx_index(
                    (-1 if ik_target_bone_index is None else ik_target_bone_index),
                    size=bone_index_size,
                    signed=True,
                ),
                struct.pack("<i", ik_loop_count),
                struct.pack("<f", ik_angle_limit),
                struct.pack(
                    "<i",
                    (
                        len(ik_links)
                        if ik_link_count_override is None
                        else ik_link_count_override
                    ),
                ),
                b"".join(ik_links),
            ]
        )

    return b"".join(parts)


def build_pmx_group_morph_offset(
    *,
    morph_index: int = 0,
    weight: float = 1.0,
    morph_index_size: int = 1,
) -> bytes:
    """Build one PMX group-morph offset."""

    return b"".join(
        [
            _pack_pmx_index(
                morph_index,
                size=morph_index_size,
                signed=True,
            ),
            struct.pack("<f", weight),
        ]
    )


def build_pmx_vertex_morph_offset(
    *,
    vertex_index: int = 0,
    translation: tuple[float, float, float] = (
        0.1,
        0.2,
        0.3,
    ),
    vertex_index_size: int = 1,
) -> bytes:
    """Build one PMX vertex-morph offset."""

    return b"".join(
        [
            _pack_pmx_index(
                vertex_index,
                size=vertex_index_size,
                signed=False,
            ),
            struct.pack("<3f", *translation),
        ]
    )


def build_pmx_bone_morph_offset(
    *,
    bone_index: int = 0,
    translation: tuple[float, float, float] = (
        0.1,
        0.2,
        0.3,
    ),
    rotation: tuple[float, float, float, float] = (
        0.0,
        0.0,
        0.0,
        1.0,
    ),
    bone_index_size: int = 1,
) -> bytes:
    """Build one PMX bone-morph offset."""

    return b"".join(
        [
            _pack_pmx_index(
                bone_index,
                size=bone_index_size,
                signed=True,
            ),
            struct.pack("<3f", *translation),
            struct.pack("<4f", *rotation),
        ]
    )


def build_pmx_uv_morph_offset(
    *,
    vertex_index: int = 0,
    uv_offset: tuple[float, float, float, float] = (
        0.1,
        0.2,
        0.3,
        0.4,
    ),
    vertex_index_size: int = 1,
) -> bytes:
    """Build one PMX UV-morph offset."""

    return b"".join(
        [
            _pack_pmx_index(
                vertex_index,
                size=vertex_index_size,
                signed=False,
            ),
            struct.pack("<4f", *uv_offset),
        ]
    )


def build_pmx_material_morph_offset(
    *,
    material_index: int = 0,
    operation: int = 1,
    diffuse: tuple[float, float, float, float] = (
        1.0,
        1.0,
        1.0,
        1.0,
    ),
    specular: tuple[float, float, float] = (
        0.0,
        0.0,
        0.0,
    ),
    specular_strength: float = 0.0,
    ambient: tuple[float, float, float] = (
        0.0,
        0.0,
        0.0,
    ),
    edge_color: tuple[float, float, float, float] = (
        0.0,
        0.0,
        0.0,
        0.0,
    ),
    edge_scale: float = 0.0,
    texture_tint: tuple[float, float, float, float] = (
        0.0,
        0.0,
        0.0,
        0.0,
    ),
    sphere_tint: tuple[float, float, float, float] = (
        0.0,
        0.0,
        0.0,
        0.0,
    ),
    toon_tint: tuple[float, float, float, float] = (
        0.0,
        0.0,
        0.0,
        0.0,
    ),
    material_index_size: int = 1,
) -> bytes:
    """Build one PMX material-morph offset."""

    return b"".join(
        [
            _pack_pmx_index(
                material_index,
                size=material_index_size,
                signed=True,
            ),
            struct.pack("<B", operation),
            struct.pack("<4f", *diffuse),
            struct.pack("<3f", *specular),
            struct.pack("<f", specular_strength),
            struct.pack("<3f", *ambient),
            struct.pack("<4f", *edge_color),
            struct.pack("<f", edge_scale),
            struct.pack("<4f", *texture_tint),
            struct.pack("<4f", *sphere_tint),
            struct.pack("<4f", *toon_tint),
        ]
    )


def build_pmx_flip_morph_offset(
    *,
    morph_index: int = 0,
    weight: float = 1.0,
    morph_index_size: int = 1,
) -> bytes:
    """Build one PMX 2.1 flip-morph offset."""

    return build_pmx_group_morph_offset(
        morph_index=morph_index,
        weight=weight,
        morph_index_size=morph_index_size,
    )


def build_pmx_impulse_morph_offset(
    *,
    rigid_body_index: int = 0,
    local_flag: int = 0,
    velocity: tuple[float, float, float] = (
        1.0,
        2.0,
        3.0,
    ),
    angular_torque: tuple[float, float, float] = (
        4.0,
        5.0,
        6.0,
    ),
    rigid_body_index_size: int = 1,
) -> bytes:
    """Build one PMX 2.1 impulse-morph offset."""

    return b"".join(
        [
            _pack_pmx_index(
                rigid_body_index,
                size=rigid_body_index_size,
                signed=True,
            ),
            struct.pack("<B", local_flag),
            struct.pack("<3f", *velocity),
            struct.pack("<3f", *angular_torque),
        ]
    )


def build_pmx_morph(
    *,
    local_name: str = "Morph",
    universal_name: str = "Morph",
    panel: int = 4,
    morph_type: int = 1,
    offsets: tuple[bytes, ...] = (),
    encoding_flag: int = 1,
    offset_count_override: int | None = None,
) -> bytes:
    """Build one PMX morph record from prebuilt offsets."""

    offset_count = (
        len(offsets) if offset_count_override is None else offset_count_override
    )

    return b"".join(
        [
            _encode_pmx_text(local_name, encoding_flag),
            _encode_pmx_text(universal_name, encoding_flag),
            struct.pack("<B", panel),
            struct.pack("<B", morph_type),
            struct.pack("<i", offset_count),
            b"".join(offsets),
        ]
    )


def build_pmx_display_frame_element(
    *,
    target_type: int = 0,
    target_index: int = 0,
    bone_index_size: int = 1,
    morph_index_size: int = 1,
) -> bytes:
    """Build one PMX display-frame bone or morph element."""

    if target_type == 0:
        index_size = bone_index_size
    elif target_type == 1:
        index_size = morph_index_size
    else:
        index_size = min(
            bone_index_size,
            morph_index_size,
        )

    return b"".join(
        [
            struct.pack("<B", target_type),
            _pack_pmx_index(
                target_index,
                size=index_size,
                signed=True,
            ),
        ]
    )


def build_pmx_display_frame(
    *,
    local_name: str = "Display Frame",
    universal_name: str = "Display Frame",
    special_flag: int = 0,
    elements: tuple[bytes, ...] = (),
    encoding_flag: int = 1,
    element_count_override: int | None = None,
) -> bytes:
    """Build one PMX display-frame record."""

    element_count = (
        len(elements) if element_count_override is None else element_count_override
    )

    return b"".join(
        [
            _encode_pmx_text(local_name, encoding_flag),
            _encode_pmx_text(universal_name, encoding_flag),
            struct.pack("<B", special_flag),
            struct.pack("<i", element_count),
            b"".join(elements),
        ]
    )


def build_pmx_rigid_body(
    *,
    local_name: str = "Rigid Body",
    universal_name: str = "Rigid Body",
    bone_index: int = -1,
    collision_group: int = 0,
    collision_mask: int = 0xFFFF,
    shape: int = 0,
    size: tuple[float, float, float] = (1.0, 1.0, 1.0),
    position: tuple[float, float, float] = (0.0, 0.0, 0.0),
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    mass: float = 1.0,
    linear_damping: float = 0.5,
    angular_damping: float = 0.5,
    restitution: float = 0.0,
    friction: float = 0.5,
    physics_mode: int = 0,
    encoding_flag: int = 1,
    bone_index_size: int = 1,
) -> bytes:
    """Build one PMX rigid-body record."""

    return b"".join(
        [
            _encode_pmx_text(local_name, encoding_flag),
            _encode_pmx_text(universal_name, encoding_flag),
            _pack_pmx_index(
                bone_index,
                size=bone_index_size,
                signed=True,
            ),
            struct.pack("<B", collision_group),
            struct.pack("<H", collision_mask),
            struct.pack("<B", shape),
            struct.pack("<3f", *size),
            struct.pack("<3f", *position),
            struct.pack("<3f", *rotation),
            struct.pack("<f", mass),
            struct.pack("<f", linear_damping),
            struct.pack("<f", angular_damping),
            struct.pack("<f", restitution),
            struct.pack("<f", friction),
            struct.pack("<B", physics_mode),
        ]
    )


def build_pmx_joint(
    *,
    local_name: str = "Joint",
    universal_name: str = "Joint",
    joint_type: int = 0,
    rigid_body_a_index: int = -1,
    rigid_body_b_index: int = -1,
    position: tuple[float, float, float] = (0.0, 0.0, 0.0),
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    translation_limit_minimum: tuple[float, float, float] = (
        -1.0,
        -1.0,
        -1.0,
    ),
    translation_limit_maximum: tuple[float, float, float] = (
        1.0,
        1.0,
        1.0,
    ),
    rotation_limit_minimum: tuple[float, float, float] = (
        -0.5,
        -0.5,
        -0.5,
    ),
    rotation_limit_maximum: tuple[float, float, float] = (
        0.5,
        0.5,
        0.5,
    ),
    translation_spring: tuple[float, float, float] = (
        0.0,
        0.0,
        0.0,
    ),
    rotation_spring: tuple[float, float, float] = (
        0.0,
        0.0,
        0.0,
    ),
    encoding_flag: int = 1,
    rigid_body_index_size: int = 1,
) -> bytes:
    """Build one PMX joint record."""

    return b"".join(
        [
            _encode_pmx_text(local_name, encoding_flag),
            _encode_pmx_text(universal_name, encoding_flag),
            struct.pack("<B", joint_type),
            _pack_pmx_index(
                rigid_body_a_index,
                size=rigid_body_index_size,
                signed=True,
            ),
            _pack_pmx_index(
                rigid_body_b_index,
                size=rigid_body_index_size,
                signed=True,
            ),
            struct.pack("<3f", *position),
            struct.pack("<3f", *rotation),
            struct.pack("<3f", *translation_limit_minimum),
            struct.pack("<3f", *translation_limit_maximum),
            struct.pack("<3f", *rotation_limit_minimum),
            struct.pack("<3f", *rotation_limit_maximum),
            struct.pack("<3f", *translation_spring),
            struct.pack("<3f", *rotation_spring),
        ]
    )


def build_pmx_soft_body_anchor(
    *,
    rigid_body_index: int = 0,
    vertex_index: int = 0,
    near_mode: int = 0,
    rigid_body_index_size: int = 1,
    vertex_index_size: int = 1,
) -> bytes:
    """Build one PMX 2.1 soft-body anchor record."""

    return b"".join(
        [
            _pack_pmx_index(
                rigid_body_index,
                size=rigid_body_index_size,
                signed=True,
            ),
            _pack_pmx_index(
                vertex_index,
                size=vertex_index_size,
                signed=False,
            ),
            struct.pack("<B", near_mode),
        ]
    )


def build_pmx_soft_body(
    *,
    local_name: str = "Soft Body",
    universal_name: str = "Soft Body",
    shape: int = 0,
    material_index: int = 0,
    collision_group: int = 0,
    collision_mask: int = 0xFFFF,
    flags: int = 0,
    bending_link_distance: int = 0,
    cluster_count: int = 0,
    total_mass: float = 1.0,
    collision_margin: float = 0.05,
    aerodynamics_model: int = 0,
    config: tuple[float, ...] = (
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.1,
        1.0,
        0.7,
    ),
    cluster_config: tuple[float, ...] = (
        1.0,
        0.1,
        1.0,
        0.5,
        0.5,
        0.5,
    ),
    iteration_config: tuple[int, int, int, int] = (0, 1, 0, 0),
    material_config: tuple[float, float, float] = (1.0, 1.0, 1.0),
    anchors: tuple[bytes, ...] = (),
    pinned_vertex_indices: tuple[int, ...] = (),
    encoding_flag: int = 1,
    material_index_size: int = 1,
    vertex_index_size: int = 1,
    anchor_count_override: int | None = None,
    pinned_vertex_count_override: int | None = None,
) -> bytes:
    """Build one PMX 2.1 soft-body record."""

    if len(config) != 12:
        raise ValueError("soft-body config must contain 12 floats")
    if len(cluster_config) != 6:
        raise ValueError("soft-body cluster config must contain 6 floats")

    anchor_count = (
        len(anchors) if anchor_count_override is None else anchor_count_override
    )
    pinned_vertex_count = (
        len(pinned_vertex_indices)
        if pinned_vertex_count_override is None
        else pinned_vertex_count_override
    )

    return b"".join(
        [
            _encode_pmx_text(local_name, encoding_flag),
            _encode_pmx_text(universal_name, encoding_flag),
            struct.pack("<B", shape),
            _pack_pmx_index(
                material_index,
                size=material_index_size,
                signed=True,
            ),
            struct.pack("<B", collision_group),
            struct.pack("<H", collision_mask),
            struct.pack("<B", flags),
            struct.pack("<i", bending_link_distance),
            struct.pack("<i", cluster_count),
            struct.pack("<f", total_mass),
            struct.pack("<f", collision_margin),
            struct.pack("<i", aerodynamics_model),
            struct.pack("<12f", *config),
            struct.pack("<6f", *cluster_config),
            struct.pack("<4i", *iteration_config),
            struct.pack("<3f", *material_config),
            struct.pack("<i", anchor_count),
            b"".join(anchors),
            struct.pack("<i", pinned_vertex_count),
            b"".join(
                _pack_pmx_index(
                    vertex_index,
                    size=vertex_index_size,
                    signed=False,
                )
                for vertex_index in pinned_vertex_indices
            ),
        ]
    )


def build_pmx_structure(
    *,
    deform_types: tuple[int, ...] = (0,),
    surface_indices: tuple[int, ...] = (
        0,
        0,
        0,
    ),
    version: float = 2.0,
    encoding_flag: int = 1,
    additional_uv_count: int = 0,
    vertex_index_size: int = 1,
    texture_index_size: int = 1,
    material_index_size: int = 1,
    bone_index_size: int = 1,
    morph_index_size: int = 1,
    rigid_body_index_size: int = 1,
    vertex_count_override: int | None = None,
    surface_index_count_override: int | None = None,
    texture_paths: tuple[str, ...] = (),
    texture_count_override: int | None = None,
    materials: tuple[bytes, ...] | None = None,
    material_count_override: int | None = None,
    bones: tuple[bytes, ...] = (),
    bone_count_override: int | None = None,
    morphs: tuple[bytes, ...] = (),
    morph_count_override: int | None = None,
    display_frames: tuple[bytes, ...] = (),
    display_frame_count_override: int | None = None,
    rigid_bodies: tuple[bytes, ...] = (),
    rigid_body_count_override: int | None = None,
    joints: tuple[bytes, ...] = (),
    joint_count_override: int | None = None,
    soft_bodies: tuple[bytes, ...] = (),
    soft_body_count_override: int | None = None,
) -> bytes:
    """Build a PMX fixture through the optional soft-body section."""

    header = build_pmx_model_info(
        version=version,
        encoding_flag=encoding_flag,
        additional_uv_count=additional_uv_count,
        vertex_index_size=vertex_index_size,
        texture_index_size=texture_index_size,
        material_index_size=material_index_size,
        bone_index_size=bone_index_size,
        morph_index_size=morph_index_size,
        rigid_body_index_size=rigid_body_index_size,
    )

    vertex_count = (
        len(deform_types) if vertex_count_override is None else vertex_count_override
    )

    surface_index_count = (
        len(surface_indices)
        if surface_index_count_override is None
        else surface_index_count_override
    )

    vertex_data = b"".join(
        build_pmx_vertex(
            deform_type=deform_type,
            additional_uv_count=additional_uv_count,
            bone_index_size=bone_index_size,
        )
        for deform_type in deform_types
    )

    surface_data = b"".join(
        _pack_pmx_index(
            index,
            size=vertex_index_size,
            signed=False,
        )
        for index in surface_indices
    )

    texture_count = (
        len(texture_paths) if texture_count_override is None else texture_count_override
    )
    texture_data = b"".join(
        _encode_pmx_text(
            texture_path,
            encoding_flag,
        )
        for texture_path in texture_paths
    )

    if materials is None:
        if surface_index_count:
            material_records = (
                build_pmx_material(
                    surface_index_count=(surface_index_count),
                    encoding_flag=encoding_flag,
                    texture_index_size=(texture_index_size),
                ),
            )
        else:
            material_records = ()
    else:
        material_records = materials

    material_count = (
        len(material_records)
        if material_count_override is None
        else material_count_override
    )
    material_data = b"".join(material_records)

    bone_count = len(bones) if bone_count_override is None else bone_count_override
    bone_data = b"".join(bones)

    morph_count = len(morphs) if morph_count_override is None else morph_count_override
    morph_data = b"".join(morphs)

    display_frame_count = (
        len(display_frames)
        if display_frame_count_override is None
        else display_frame_count_override
    )
    display_frame_data = b"".join(display_frames)

    rigid_body_count = (
        len(rigid_bodies)
        if rigid_body_count_override is None
        else rigid_body_count_override
    )
    rigid_body_data = b"".join(rigid_bodies)

    joint_count = len(joints) if joint_count_override is None else joint_count_override
    joint_data = b"".join(joints)

    soft_body_count = (
        len(soft_bodies)
        if soft_body_count_override is None
        else soft_body_count_override
    )
    soft_body_data = b"".join(soft_bodies)
    soft_body_section = (
        struct.pack("<i", soft_body_count) + soft_body_data if version == 2.1 else b""
    )

    return b"".join(
        [
            header,
            struct.pack(
                "<i",
                vertex_count,
            ),
            vertex_data,
            struct.pack(
                "<i",
                surface_index_count,
            ),
            surface_data,
            struct.pack(
                "<i",
                texture_count,
            ),
            texture_data,
            struct.pack(
                "<i",
                material_count,
            ),
            material_data,
            struct.pack(
                "<i",
                bone_count,
            ),
            bone_data,
            struct.pack(
                "<i",
                morph_count,
            ),
            morph_data,
            struct.pack(
                "<i",
                display_frame_count,
            ),
            display_frame_data,
            struct.pack(
                "<i",
                rigid_body_count,
            ),
            rigid_body_data,
            struct.pack(
                "<i",
                joint_count,
            ),
            joint_data,
            soft_body_section,
        ]
    )
