"""Internal immutable position intent for safe structural insertion planning.

This layer deliberately models only *where* records are proposed for insertion.
It does not own inserted PMX payloads, mutate a PmxDocument, build a
PmxCollectionTransform, serialize bytes, resize index widths, or expose a public
mutation authority.

Positions are expressed in the captured source index domain:

* ``append`` means after the complete source collection.
* ``insert_before(source_index)`` means immediately before one existing source
  record.

Payload DTOs and materialization are introduced by later target-specific layers.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from mmd_registry.pmx.reference_model import PmxReferenceTargetKind


def _require_nonnegative_plain_int(value: object, field_name: str) -> int:
    """Return one exact nonnegative integer, rejecting booleans."""

    if type(value) is not int:
        raise TypeError(f"{field_name} must be an integer.")
    if value < 0:
        raise ValueError(f"{field_name} must be nonnegative.")
    return value


_TARGET_KIND_ORDER: tuple[PmxReferenceTargetKind, ...] = tuple(PmxReferenceTargetKind)


def _target_kind_rank(target_kind: PmxReferenceTargetKind) -> int:
    return _TARGET_KIND_ORDER.index(target_kind)


class PmxStructuralInsertPositionMode(str, Enum):
    """Closed insertion-position vocabulary."""

    APPEND = "append"
    INSERT_BEFORE = "insert_before"


@dataclass(frozen=True, slots=True)
class PmxStructuralInsertPosition:
    """One immutable insertion position in the captured source domain."""

    mode: PmxStructuralInsertPositionMode
    source_index: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.mode, PmxStructuralInsertPositionMode):
            raise TypeError("mode must be a PmxStructuralInsertPositionMode value.")

        if self.mode is PmxStructuralInsertPositionMode.APPEND:
            if self.source_index is not None:
                raise ValueError("append position cannot define source_index.")
            return

        if self.source_index is None:
            raise ValueError("insert_before position requires source_index.")
        _require_nonnegative_plain_int(self.source_index, "source_index")

    @classmethod
    def append(cls) -> "PmxStructuralInsertPosition":
        """Return an explicit append position."""

        return cls(mode=PmxStructuralInsertPositionMode.APPEND)

    @classmethod
    def insert_before(cls, source_index: int) -> "PmxStructuralInsertPosition":
        """Return an explicit source-domain insert-before position."""

        return cls(
            mode=PmxStructuralInsertPositionMode.INSERT_BEFORE,
            source_index=source_index,
        )

    def validate_for_source_size(self, current_count: int) -> None:
        """Validate this position against one captured source collection size."""

        count = _require_nonnegative_plain_int(current_count, "current_count")
        if self.mode is PmxStructuralInsertPositionMode.INSERT_BEFORE:
            assert self.source_index is not None
            if self.source_index >= count:
                raise ValueError(
                    "insert_before source_index must be less than current_count."
                )

    def to_dict(self) -> dict[str, object]:
        """Return deterministic JSON-ready position evidence."""

        return {
            "mode": self.mode.value,
            "source_index": self.source_index,
        }


@dataclass(frozen=True, slots=True)
class PmxCollectionInsertionIntent:
    """Insertion positions for exactly one PMX reference target kind.

    The tuple order is authoritative. Multiple positions at the same source
    anchor and multiple appends therefore retain caller order without mutable
    state or implicit sorting.
    """

    target_kind: PmxReferenceTargetKind
    positions: tuple[PmxStructuralInsertPosition, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.target_kind, PmxReferenceTargetKind):
            raise TypeError("target_kind must be a PmxReferenceTargetKind value.")
        if type(self.positions) is not tuple:
            raise TypeError("positions must be a tuple.")
        if not self.positions:
            raise ValueError("positions must contain at least one insertion position.")
        if not all(
            isinstance(position, PmxStructuralInsertPosition)
            for position in self.positions
        ):
            raise TypeError(
                "positions must contain only PmxStructuralInsertPosition values."
            )

    @property
    def insert_count(self) -> int:
        """Return the number of proposed inserted records."""

        return len(self.positions)

    def validate_for_source_size(self, current_count: int) -> None:
        """Validate every source-domain position without changing request order."""

        count = _require_nonnegative_plain_int(current_count, "current_count")
        for position in self.positions:
            position.validate_for_source_size(count)

    def to_dict(self) -> dict[str, object]:
        """Return deterministic JSON-ready collection insertion evidence."""

        return {
            "target_kind": self.target_kind.value,
            "insert_count": self.insert_count,
            "positions": [position.to_dict() for position in self.positions],
        }


@dataclass(frozen=True, slots=True)
class PmxStructuralInsertionIntent:
    """Canonical coordinated position intent for zero or more target kinds.

    Collection intents must be unique by target kind and supplied in
    ``PmxReferenceTargetKind`` declaration order. This mirrors the deterministic
    ordering contract of the existing structural transform intent while keeping
    insertion payloads and legacy collection transforms separate.
    """

    collection_insertions: tuple[PmxCollectionInsertionIntent, ...] = ()

    def __post_init__(self) -> None:
        if type(self.collection_insertions) is not tuple:
            raise TypeError("collection_insertions must be a tuple.")
        if not all(
            isinstance(insertion, PmxCollectionInsertionIntent)
            for insertion in self.collection_insertions
        ):
            raise TypeError(
                "collection_insertions must contain only "
                "PmxCollectionInsertionIntent values."
            )

        target_kinds = tuple(
            insertion.target_kind for insertion in self.collection_insertions
        )
        if len(set(target_kinds)) != len(target_kinds):
            raise ValueError(
                "collection_insertions cannot repeat one target_kind."
            )

        ranks = tuple(_target_kind_rank(kind) for kind in target_kinds)
        if ranks != tuple(sorted(ranks)):
            raise ValueError(
                "collection_insertions must follow PmxReferenceTargetKind order."
            )

    @property
    def total_insert_count(self) -> int:
        """Return the total number of proposed inserted records."""

        return sum(
            insertion.insert_count for insertion in self.collection_insertions
        )

    def insertion_for(
        self,
        target_kind: PmxReferenceTargetKind,
    ) -> PmxCollectionInsertionIntent | None:
        """Return one target-kind insertion intent, if present."""

        if not isinstance(target_kind, PmxReferenceTargetKind):
            raise TypeError("target_kind must be a PmxReferenceTargetKind value.")
        for insertion in self.collection_insertions:
            if insertion.target_kind is target_kind:
                return insertion
        return None

    def to_dict(self) -> dict[str, object]:
        """Return deterministic JSON-ready coordinated position evidence."""

        return {
            "collection_insertions": [
                insertion.to_dict() for insertion in self.collection_insertions
            ],
            "total_insert_count": self.total_insert_count,
        }


__all__ = (
    "PmxStructuralInsertPositionMode",
    "PmxStructuralInsertPosition",
    "PmxCollectionInsertionIntent",
    "PmxStructuralInsertionIntent",
)
