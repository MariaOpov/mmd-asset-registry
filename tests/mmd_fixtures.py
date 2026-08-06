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
