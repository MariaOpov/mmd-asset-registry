"""Public immutable capability manifest for the supported PMX core."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, get_args

from mmd_registry.pmx.document import (
    PmxDeform,
    PmxMorphType,
    SUPPORTED_PMX_VERSIONS,
    VALID_PMX_INDEX_SIZES,
    VALID_PMX_TEXT_ENCODINGS,
)
from mmd_registry.pmx.editing.catalog import get_pmx_edit_operation_catalog


PmxRoundTripContract = Literal["validated_semantic_roundtrip"]


def _supported_deform_types() -> tuple[int, ...]:
    """Derive supported PMX deform codes from the authoritative document union."""

    deform_codes: list[int] = []
    for deform_type in get_args(PmxDeform):
        code = getattr(deform_type, "deform_type", None)
        if type(code) is not int:
            raise TypeError(
                "PmxDeform members must expose an integer deform_type code."
            )
        deform_codes.append(code)
    return tuple(sorted(deform_codes))


def _supported_morph_types() -> tuple[int, ...]:
    """Derive supported PMX morph codes from the authoritative Literal alias."""

    morph_codes = get_args(PmxMorphType)
    if not morph_codes or any(type(code) is not int for code in morph_codes):
        raise TypeError("PmxMorphType must contain integer Literal values.")
    return tuple(sorted(morph_codes))


@dataclass(frozen=True, slots=True)
class PmxCapabilityManifest:
    """Stable public description of the currently supported PMX core."""

    pmx_versions: tuple[float, ...]
    text_encodings: tuple[str, ...]
    index_sizes: tuple[int, ...]
    deform_types: tuple[int, ...]
    morph_types: tuple[int, ...]
    soft_body_support: bool
    roundtrip_contract: PmxRoundTripContract
    edit_operation_types: tuple[str, ...]
    texture_portability: bool
    private_runtime_required: bool

    def to_dict(self) -> dict[str, object]:
        """Return a deterministic JSON-ready capability representation."""

        return {
            "pmx_versions": list(self.pmx_versions),
            "text_encodings": list(self.text_encodings),
            "index_sizes": list(self.index_sizes),
            "deform_types": list(self.deform_types),
            "morph_types": list(self.morph_types),
            "soft_body_support": self.soft_body_support,
            "roundtrip_contract": self.roundtrip_contract,
            "edit_operation_types": list(self.edit_operation_types),
            "texture_portability": self.texture_portability,
            "private_runtime_required": self.private_runtime_required,
        }


def get_capabilities() -> PmxCapabilityManifest:
    """Return the deterministic public capability manifest."""

    operation_catalog = get_pmx_edit_operation_catalog()
    return PmxCapabilityManifest(
        pmx_versions=tuple(SUPPORTED_PMX_VERSIONS),
        text_encodings=tuple(sorted(VALID_PMX_TEXT_ENCODINGS)),
        index_sizes=tuple(sorted(VALID_PMX_INDEX_SIZES)),
        deform_types=_supported_deform_types(),
        morph_types=_supported_morph_types(),
        soft_body_support=True,
        roundtrip_contract="validated_semantic_roundtrip",
        edit_operation_types=tuple(
            operation.operation_type for operation in operation_catalog.operations
        ),
        texture_portability=True,
        private_runtime_required=False,
    )


def get_pmx_capability_manifest() -> PmxCapabilityManifest:
    """Return the manifest through the retained v0.8 compatibility name."""

    return get_capabilities()


__all__ = (
    "PmxCapabilityManifest",
    "PmxRoundTripContract",
    "get_capabilities",
)
