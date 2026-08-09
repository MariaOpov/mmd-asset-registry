"""Immutable core types for a complete in-memory PMX document.

This module starts with the header and model-information types shared by all
PMX sections. Section records and the top-level ``PmxDocument`` are introduced
incrementally before any writer is exposed, so no public API can mistake a
header-only object for a complete model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal, TypeAlias


PmxVersion: TypeAlias = Literal[2.0, 2.1]
PmxTextEncoding: TypeAlias = Literal["utf-16-le", "utf-8"]

SUPPORTED_PMX_VERSIONS: Final[tuple[float, ...]] = (2.0, 2.1)
VALID_PMX_TEXT_ENCODINGS: Final[frozenset[str]] = frozenset(
    {"utf-16-le", "utf-8"}
)
VALID_PMX_INDEX_SIZES: Final[frozenset[int]] = frozenset({1, 2, 4})
MIN_PMX_GLOBAL_COUNT: Final[int] = 8
MAX_PMX_GLOBAL_COUNT: Final[int] = 64
MIN_PMX_ADDITIONAL_UV_COUNT: Final[int] = 0
MAX_PMX_ADDITIONAL_UV_COUNT: Final[int] = 4


def _is_plain_int(value: object) -> bool:
    """Return whether value is an integer but not a boolean."""

    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True, slots=True)
class PmxIndexSizes:
    """Index widths declared by the six standard PMX global fields."""

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

            if not _is_plain_int(value) or value not in VALID_PMX_INDEX_SIZES:
                raise ValueError(
                    f"{field_name} index size must be one of "
                    f"{sorted(VALID_PMX_INDEX_SIZES)}; got {value!r}."
                )


@dataclass(frozen=True, slots=True)
class PmxHeader:
    """Byte-relevant PMX header settings required for safe serialization."""

    version: PmxVersion
    encoding: PmxTextEncoding
    additional_uv_count: int
    index_sizes: PmxIndexSizes
    extra_global_data: bytes = b""

    def __post_init__(self) -> None:
        if not isinstance(self.version, float) or isinstance(self.version, bool):
            raise TypeError("PMX version must be a float.")

        if self.version not in SUPPORTED_PMX_VERSIONS:
            raise ValueError(
                f"Unsupported PMX version {self.version!r}; expected 2.0 or 2.1."
            )

        if self.encoding not in VALID_PMX_TEXT_ENCODINGS:
            raise ValueError(
                f"Unsupported PMX text encoding {self.encoding!r}; "
                "expected 'utf-16-le' or 'utf-8'."
            )

        if not _is_plain_int(self.additional_uv_count):
            raise TypeError("additional_uv_count must be an integer.")

        if not (
            MIN_PMX_ADDITIONAL_UV_COUNT
            <= self.additional_uv_count
            <= MAX_PMX_ADDITIONAL_UV_COUNT
        ):
            raise ValueError(
                "additional_uv_count must be between 0 and 4; "
                f"got {self.additional_uv_count}."
            )

        if not isinstance(self.index_sizes, PmxIndexSizes):
            raise TypeError("index_sizes must be a PmxIndexSizes instance.")

        if not isinstance(self.extra_global_data, bytes):
            raise TypeError("extra_global_data must be immutable bytes.")

        if self.global_count > MAX_PMX_GLOBAL_COUNT:
            raise ValueError(
                f"PMX global count {self.global_count} exceeds the supported "
                f"maximum of {MAX_PMX_GLOBAL_COUNT}."
            )

    @property
    def encoding_flag(self) -> int:
        """Return the PMX global encoding flag used on disk."""

        return 0 if self.encoding == "utf-16-le" else 1

    @property
    def global_count(self) -> int:
        """Return the complete PMX global-setting byte count."""

        return MIN_PMX_GLOBAL_COUNT + len(self.extra_global_data)


@dataclass(frozen=True, slots=True)
class PmxModelInfo:
    """The four PMX model-information text fields without normalization."""

    local_name: str
    universal_name: str
    local_comments: str
    universal_comments: str

    def __post_init__(self) -> None:
        for field_name in (
            "local_name",
            "universal_name",
            "local_comments",
            "universal_comments",
        ):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"{field_name} must be a string.")
