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
) -> bytes:
    """Build a PMX fixture through the material section."""

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
        ]
    )
