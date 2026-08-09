"""Typed reading for the ordered PMX texture-path table."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from mmd_registry.binary_reader import BinaryReader
from mmd_registry.pmx.document import PmxHeader


MAX_PMX_TEXTURE_COUNT: Final[int] = 100_000
MAX_PMX_TEXTURE_PATH_BYTES: Final[int] = 64 * 1024


@dataclass(slots=True)
class PmxTextureReadState:
    """Incremental texture data for legacy scanner projections."""

    texture_count: int | None = None
    texture_paths: tuple[str, ...] = ()


def read_pmx_textures(
    reader: BinaryReader,
    *,
    header: PmxHeader,
    state: PmxTextureReadState | None = None,
) -> tuple[str, ...]:
    """Read the complete ordered PMX texture-path table."""

    if not isinstance(header, PmxHeader):
        raise TypeError("header must be a PmxHeader instance.")

    read_state = state if state is not None else PmxTextureReadState()
    require_even_length = header.encoding == "utf-16-le"

    with reader.context("textures"):
        texture_count = reader.read_bounded_count(
            "texture count",
            max_count=MAX_PMX_TEXTURE_COUNT,
            minimum_item_size=4,
        )

    read_state.texture_count = texture_count
    texture_paths = tuple(
        _read_pmx_texture_path(
            reader,
            record_index=record_index,
            encoding=header.encoding,
            require_even_length=require_even_length,
        )
        for record_index in range(texture_count)
    )
    read_state.texture_paths = texture_paths
    return texture_paths


def _read_pmx_texture_path(
    reader: BinaryReader,
    *,
    record_index: int,
    encoding: str,
    require_even_length: bool,
) -> str:
    """Read one raw PMX texture path without resolving or normalizing it."""

    with reader.context(
        "textures",
        record_index=record_index,
    ):
        return reader.read_length_prefixed_text(
            "texture path",
            encoding=encoding,
            max_length=MAX_PMX_TEXTURE_PATH_BYTES,
            require_even_length=require_even_length,
        )
