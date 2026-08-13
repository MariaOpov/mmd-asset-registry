"""Deterministic PMX compatibility profiles for v0.8.4 regression tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from tests.mmd_fixtures import build_pmx_bone, build_pmx_structure


PmxFixtureKind = Literal["empty", "unicode_bone", "qdef_additional_uv"]

_VALID_VERSIONS: Final[frozenset[float]] = frozenset({2.0, 2.1})
_VALID_ENCODING_FLAGS: Final[frozenset[int]] = frozenset({0, 1})
_VALID_INDEX_SIZES: Final[frozenset[int]] = frozenset({1, 2, 4})
_VALID_FIXTURE_KINDS: Final[frozenset[str]] = frozenset(
    {"empty", "unicode_bone", "qdef_additional_uv"}
)


def _is_plain_int(value: object) -> bool:
    """Return whether value is an integer but not a boolean."""

    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True, slots=True)
class PmxCompatibilityProfile:
    """One small generated PMX configuration with explicit capabilities."""

    profile_id: str
    version: float
    encoding_flag: int
    additional_uv_count: int
    index_sizes: tuple[int, int, int, int, int, int]
    fixture_kind: PmxFixtureKind
    capabilities: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.profile_id, str) or not self.profile_id.strip():
            raise ValueError("profile_id must be a non-empty string.")
        if self.profile_id != self.profile_id.strip():
            raise ValueError("profile_id cannot contain surrounding whitespace.")

        if not isinstance(self.version, float) or isinstance(self.version, bool):
            raise TypeError("version must be a float.")
        if self.version not in _VALID_VERSIONS:
            raise ValueError("version must be 2.0 or 2.1.")

        if (
            not _is_plain_int(self.encoding_flag)
            or self.encoding_flag not in _VALID_ENCODING_FLAGS
        ):
            raise ValueError("encoding_flag must be 0 or 1.")

        if (
            not _is_plain_int(self.additional_uv_count)
            or not 0 <= self.additional_uv_count <= 4
        ):
            raise ValueError("additional_uv_count must be from 0 through 4.")

        if not isinstance(self.index_sizes, tuple) or len(self.index_sizes) != 6:
            raise ValueError("index_sizes must contain exactly six values.")
        if any(
            not _is_plain_int(size) or size not in _VALID_INDEX_SIZES
            for size in self.index_sizes
        ):
            raise ValueError("every index size must be 1, 2, or 4.")

        if self.fixture_kind not in _VALID_FIXTURE_KINDS:
            raise ValueError(f"unsupported fixture_kind: {self.fixture_kind!r}.")

        if not isinstance(self.capabilities, tuple) or not self.capabilities:
            raise ValueError("capabilities must be a non-empty tuple.")
        if any(
            not isinstance(capability, str) or not capability.strip()
            for capability in self.capabilities
        ):
            raise ValueError("capabilities must contain non-empty strings.")
        if len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError("capabilities cannot contain duplicates.")

    @property
    def encoding(self) -> str:
        """Return the PMX text encoding selected by the profile."""

        return "utf-16-le" if self.encoding_flag == 0 else "utf-8"

    @property
    def dimension_key(
        self,
    ) -> tuple[
        float,
        int,
        int,
        tuple[int, int, int, int, int, int],
        PmxFixtureKind,
    ]:
        """Return the stable dimensions used to detect accidental duplicates."""

        return (
            self.version,
            self.encoding_flag,
            self.additional_uv_count,
            self.index_sizes,
            self.fixture_kind,
        )


PMX_COMPATIBILITY_PROFILES: Final[tuple[PmxCompatibilityProfile, ...]] = (
    PmxCompatibilityProfile(
        profile_id="minimal-pmx20-utf16",
        version=2.0,
        encoding_flag=0,
        additional_uv_count=0,
        index_sizes=(1, 1, 1, 1, 1, 1),
        fixture_kind="empty",
        capabilities=("zero-count-sections", "utf-16-le"),
    ),
    PmxCompatibilityProfile(
        profile_id="minimal-pmx20-utf8",
        version=2.0,
        encoding_flag=1,
        additional_uv_count=0,
        index_sizes=(2, 2, 2, 2, 2, 2),
        fixture_kind="empty",
        capabilities=("zero-count-sections", "utf-8"),
    ),
    PmxCompatibilityProfile(
        profile_id="mixed-index-pmx21",
        version=2.1,
        encoding_flag=1,
        additional_uv_count=0,
        index_sizes=(1, 2, 4, 1, 2, 4),
        fixture_kind="empty",
        capabilities=("mixed-index-widths", "zero-count-sections"),
    ),
    PmxCompatibilityProfile(
        profile_id="unicode-bone-pmx21-utf16",
        version=2.1,
        encoding_flag=0,
        additional_uv_count=0,
        index_sizes=(2, 1, 4, 2, 1, 4),
        fixture_kind="unicode_bone",
        capabilities=("unicode-text", "bone-tail-offset"),
    ),
    PmxCompatibilityProfile(
        profile_id="additional-uv4-qdef-pmx21",
        version=2.1,
        encoding_flag=1,
        additional_uv_count=4,
        index_sizes=(4, 2, 1, 4, 2, 1),
        fixture_kind="qdef_additional_uv",
        capabilities=("additional-uv-4", "qdef", "bone-reference"),
    ),
)


def build_compatibility_fixture(profile: PmxCompatibilityProfile) -> bytes:
    """Build deterministic PMX bytes for one compatibility profile."""

    if not isinstance(profile, PmxCompatibilityProfile):
        raise TypeError("profile must be a PmxCompatibilityProfile instance.")

    (
        vertex_index_size,
        texture_index_size,
        material_index_size,
        bone_index_size,
        morph_index_size,
        rigid_body_index_size,
    ) = profile.index_sizes

    common_arguments = {
        "version": profile.version,
        "encoding_flag": profile.encoding_flag,
        "additional_uv_count": profile.additional_uv_count,
        "vertex_index_size": vertex_index_size,
        "texture_index_size": texture_index_size,
        "material_index_size": material_index_size,
        "bone_index_size": bone_index_size,
        "morph_index_size": morph_index_size,
        "rigid_body_index_size": rigid_body_index_size,
        "surface_indices": (),
        "materials": (),
    }

    if profile.fixture_kind == "empty":
        return build_pmx_structure(
            deform_types=(),
            **common_arguments,
        )

    if profile.fixture_kind == "unicode_bone":
        bone = build_pmx_bone(
            local_name="センター",
            universal_name="Center",
            tail_offset=(0.0, 1.0, 0.0),
            encoding_flag=profile.encoding_flag,
            bone_index_size=bone_index_size,
        )
        return build_pmx_structure(
            deform_types=(),
            bones=(bone,),
            **common_arguments,
        )

    if profile.fixture_kind == "qdef_additional_uv":
        bone = build_pmx_bone(
            local_name="Root",
            universal_name="Root",
            encoding_flag=profile.encoding_flag,
            bone_index_size=bone_index_size,
        )
        return build_pmx_structure(
            deform_types=(4,),
            bones=(bone,),
            **common_arguments,
        )

    raise AssertionError(f"Unhandled fixture kind: {profile.fixture_kind}")
