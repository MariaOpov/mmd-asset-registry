"""Programmatic PMX/PMD header fixtures for unit tests."""

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
