"""Immutable structural collection-transform intent models.

Checkpoint 10 remains an internal, non-executing kernel layer.  A collection
transform is typed by one globally index-addressable PMX target collection and
uses the validated CP09 ``PmxIndexRemap`` as its single source of truth.

The model describes keep/delete/reorder/no-op intent only.  It does not mutate
``PmxDocument``, rewrite references, choose deletion policy, serialize output,
or expose arbitrary public execution.

CP09 can represent future new indices without old sources.  CP10 deliberately
rejects those insertion-capable mappings for v0.9.0 rather than silently
reinterpreting them.
"""

from __future__ import annotations

from dataclasses import dataclass

from mmd_registry.pmx.index_remap import PmxIndexRemap
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind


_TARGET_KIND_ORDER: tuple[PmxReferenceTargetKind, ...] = tuple(PmxReferenceTargetKind)


def _target_kind_position(kind: PmxReferenceTargetKind) -> int:
    """Return canonical target-kind position without mutable lookup state."""

    return _TARGET_KIND_ORDER.index(kind)


@dataclass(frozen=True, slots=True)
class PmxCollectionTransform:
    """One typed keep/delete/reorder/no-op collection proposal.

    ``remap`` is the sole stored mapping authority.  New collection order,
    removals, and transform effects are derived from it deterministically.
    """

    kind: PmxReferenceTargetKind
    remap: PmxIndexRemap

    def __post_init__(self) -> None:
        if not isinstance(self.kind, PmxReferenceTargetKind):
            raise TypeError("kind must be a PmxReferenceTargetKind value.")
        if not isinstance(self.remap, PmxIndexRemap):
            raise TypeError("remap must be a PmxIndexRemap value.")
        if self.remap.has_new_indices_without_old_source:
            raise ValueError(
                "v0.9.0 collection transforms do not authorize new indices "
                "without old sources."
            )

    @classmethod
    def identity(
        cls,
        kind: PmxReferenceTargetKind,
        size: int,
    ) -> "PmxCollectionTransform":
        """Return one typed identity/no-op collection proposal."""

        return cls(kind=kind, remap=PmxIndexRemap.identity(size))

    @property
    def old_size(self) -> int:
        """Return the old collection size."""

        return self.remap.old_size

    @property
    def new_size(self) -> int:
        """Return the proposed new collection size."""

        return self.remap.new_size

    @property
    def removed_old_indices(self) -> tuple[int, ...]:
        """Return removed old records in deterministic old-index order."""

        return self.remap.removed_old_indices

    @property
    def old_indices_in_new_order(self) -> tuple[int, ...]:
        """Return surviving old indices ordered by their proposed new indices."""

        ordered: list[int | None] = [None] * self.new_size
        for old_index, new_index in enumerate(self.remap.targets):
            if new_index is not None:
                ordered[new_index] = old_index

        if any(old_index is None for old_index in ordered):
            raise AssertionError(
                "validated CP09 remap unexpectedly left an unowned new index."
            )
        return tuple(old_index for old_index in ordered if old_index is not None)

    @property
    def has_deletions(self) -> bool:
        """Whether at least one old record is removed."""

        return bool(self.removed_old_indices)

    @property
    def has_reorder(self) -> bool:
        """Whether surviving records change relative order."""

        order = self.old_indices_in_new_order
        return order != tuple(sorted(order))

    @property
    def is_noop(self) -> bool:
        """Whether the proposal preserves every old record at the same index."""

        return self.remap.is_identity


@dataclass(frozen=True, slots=True)
class PmxStructuralTransformIntent:
    """Canonical coordinated intent for zero or more indexed collections.

    Collection transforms must be unique by target kind and supplied in the
    declaration order of ``PmxReferenceTargetKind``.  Requiring canonical
    order keeps equality, hashing, and later audit output deterministic without
    silently normalizing caller input.
    """

    transforms: tuple[PmxCollectionTransform, ...] = ()

    def __post_init__(self) -> None:
        if type(self.transforms) is not tuple:
            raise TypeError("transforms must be a tuple.")
        if not all(
            isinstance(transform, PmxCollectionTransform)
            for transform in self.transforms
        ):
            raise TypeError(
                "transforms must contain only PmxCollectionTransform values."
            )

        kinds = tuple(transform.kind for transform in self.transforms)
        if len(kinds) != len(set(kinds)):
            raise ValueError("transforms cannot contain duplicate target kinds.")

        canonical = tuple(
            sorted(
                self.transforms,
                key=lambda transform: _target_kind_position(transform.kind),
            )
        )
        if self.transforms != canonical:
            raise ValueError(
                "transforms must follow canonical PmxReferenceTargetKind order."
            )

    @property
    def is_noop(self) -> bool:
        """Whether every coordinated collection proposal is a no-op."""

        return all(transform.is_noop for transform in self.transforms)

    @property
    def changed_kinds(self) -> tuple[PmxReferenceTargetKind, ...]:
        """Return changed target kinds in canonical deterministic order."""

        return tuple(
            transform.kind
            for transform in self.transforms
            if not transform.is_noop
        )

    def transform_for(
        self,
        kind: PmxReferenceTargetKind,
    ) -> PmxCollectionTransform | None:
        """Return the transform for one target kind, or ``None`` if absent."""

        if not isinstance(kind, PmxReferenceTargetKind):
            raise TypeError("kind must be a PmxReferenceTargetKind value.")
        for transform in self.transforms:
            if transform.kind is kind:
                return transform
        return None


__all__ = (
    "PmxCollectionTransform",
    "PmxStructuralTransformIntent",
)
