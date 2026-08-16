"""Immutable identity primitives for PMX reference analysis.

This module is intentionally internal during the v0.9.0 foundation work.
It defines identity and edge values only: no document traversal, graph
extraction, diagnostics, mutation, remapping, or filesystem behavior.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final


_RELATIONSHIP_ID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\Z"
)
_CONCRETE_SOURCE_PATH_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"[a-z][a-z0-9_]*\[\d+\]"
    r"(?:\.[a-z][a-z0-9_]*(?:\[\d+\])?)*\Z"
)


class PmxReferenceTargetKind(StrEnum):
    """The six globally index-addressable PMX target collections."""

    VERTEX = "vertex"
    TEXTURE = "texture"
    MATERIAL = "material"
    BONE = "bone"
    MORPH = "morph"
    RIGID_BODY = "rigid_body"


class PmxReferenceSourceSection(StrEnum):
    """Typed source sections that currently own supported references."""

    SURFACE_INDICES = "surface_indices"
    VERTICES = "vertices"
    MATERIALS = "materials"
    BONES = "bones"
    MORPHS = "morphs"
    DISPLAY_FRAMES = "display_frames"
    RIGID_BODIES = "rigid_bodies"
    JOINTS = "joints"
    SOFT_BODIES = "soft_bodies"


@dataclass(frozen=True, slots=True)
class PmxReferenceNode:
    """Identity of one record in a globally index-addressable target collection."""

    kind: PmxReferenceTargetKind
    index: int

    def __post_init__(self) -> None:
        if not isinstance(self.kind, PmxReferenceTargetKind):
            raise TypeError("kind must be a PmxReferenceTargetKind value.")
        if type(self.index) is not int:
            raise TypeError("index must be an integer.")
        if self.index < 0:
            raise ValueError("index must be nonnegative.")


@dataclass(frozen=True, slots=True)
class PmxReferenceSourceLocation:
    """Concrete source record/path context for one extracted reference."""

    section: PmxReferenceSourceSection
    record_index: int
    path: str

    def __post_init__(self) -> None:
        if not isinstance(self.section, PmxReferenceSourceSection):
            raise TypeError("section must be a PmxReferenceSourceSection value.")
        if type(self.record_index) is not int:
            raise TypeError("record_index must be an integer.")
        if self.record_index < 0:
            raise ValueError("record_index must be nonnegative.")
        if type(self.path) is not str or not self.path:
            raise ValueError("path must be a non-empty string.")
        if _CONCRETE_SOURCE_PATH_PATTERN.fullmatch(self.path) is None:
            raise ValueError(
                "path must be one concrete lowercase PMX source path without wildcards."
            )
        expected_prefix = f"{self.section.value}[{self.record_index}]"
        if not (
            self.path == expected_prefix
            or self.path.startswith(expected_prefix + ".")
        ):
            raise ValueError(
                "path must identify the declared source section and record_index."
            )


@dataclass(frozen=True, slots=True)
class PmxReferenceEdge:
    """One active reference from a concrete PMX source location to a target node."""

    relationship_id: str
    source: PmxReferenceSourceLocation
    target: PmxReferenceNode

    def __post_init__(self) -> None:
        if (
            type(self.relationship_id) is not str
            or _RELATIONSHIP_ID_PATTERN.fullmatch(self.relationship_id) is None
        ):
            raise ValueError(
                "relationship_id must be a dotted lowercase stable identifier."
            )
        if not isinstance(self.source, PmxReferenceSourceLocation):
            raise TypeError("source must be a PmxReferenceSourceLocation value.")
        if not isinstance(self.target, PmxReferenceNode):
            raise TypeError("target must be a PmxReferenceNode value.")


__all__ = (
    "PmxReferenceEdge",
    "PmxReferenceNode",
    "PmxReferenceSourceLocation",
    "PmxReferenceSourceSection",
    "PmxReferenceTargetKind",
)
