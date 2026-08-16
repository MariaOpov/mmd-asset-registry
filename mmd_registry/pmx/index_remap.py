"""Immutable old-index to new-index/removed mapping primitives.

Checkpoint 09 is intentionally section-agnostic and internal.  It models index
identity changes only; it does not mutate a PmxDocument, rewrite references,
apply deletion policy, serialize PMX data, or expose a public execution API.

``None`` is the explicit removed-target state.  It is deliberately distinct
from PMX field sentinels such as ``-1``.

``new_indices_without_old_source`` makes the representation compatible with a
future insertion-capable layer without authorizing insertion in v0.9.0.
Current structural proposals must decide separately whether such indices are
allowed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias


PmxIndexRemapTarget: TypeAlias = int | None


def _require_nonnegative_plain_int(value: object, field_name: str) -> int:
    """Return one exact nonnegative integer, rejecting booleans."""

    if type(value) is not int:
        raise TypeError(f"{field_name} must be an integer.")
    if value < 0:
        raise ValueError(f"{field_name} must be nonnegative.")
    return value


@dataclass(frozen=True, slots=True)
class PmxIndexRemap:
    """One complete deterministic mapping from an old index domain.

    ``targets[old_index]`` is either the corresponding new index or ``None``
    when that old record is removed.

    The old domain is always complete because its size is exactly
    ``len(targets)``.  The union of mapped new indices and
    ``new_indices_without_old_source`` must densely cover
    ``range(new_size)`` exactly once.
    """

    targets: tuple[PmxIndexRemapTarget, ...]
    new_size: int
    new_indices_without_old_source: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if type(self.targets) is not tuple:
            raise TypeError("targets must be a tuple.")

        _require_nonnegative_plain_int(self.new_size, "new_size")

        mapped_new_indices: set[int] = set()
        for old_index, target in enumerate(self.targets):
            if target is None:
                continue
            if type(target) is not int:
                raise TypeError(
                    f"targets[{old_index}] must be an integer or None."
                )
            if target < 0:
                raise ValueError(
                    f"targets[{old_index}] cannot be negative; use None for removal."
                )
            if target >= self.new_size:
                raise ValueError(
                    f"targets[{old_index}]={target} is outside new_size "
                    f"{self.new_size}."
                )
            if target in mapped_new_indices:
                raise ValueError(f"new index {target} is mapped more than once.")
            mapped_new_indices.add(target)

        if type(self.new_indices_without_old_source) is not tuple:
            raise TypeError("new_indices_without_old_source must be a tuple.")

        previous: int | None = None
        new_only_indices: set[int] = set()
        for position, new_index in enumerate(self.new_indices_without_old_source):
            if type(new_index) is not int:
                raise TypeError(
                    "new_indices_without_old_source "
                    f"[{position}] must be an integer."
                )
            if new_index < 0:
                raise ValueError(
                    "new_indices_without_old_source cannot contain "
                    "negative indices."
                )
            if new_index >= self.new_size:
                raise ValueError(
                    f"new-only index {new_index} is outside new_size "
                    f"{self.new_size}."
                )
            if previous is not None and new_index <= previous:
                raise ValueError(
                    "new_indices_without_old_source must be strictly increasing."
                )
            if new_index in mapped_new_indices:
                raise ValueError(
                    f"new index {new_index} cannot be both mapped and new-only."
                )
            new_only_indices.add(new_index)
            previous = new_index

        covered_count = len(mapped_new_indices) + len(new_only_indices)
        if covered_count != self.new_size:
            raise ValueError(
                "mapped and new-only indices must densely cover "
                "the complete new index range."
            )

    @classmethod
    def identity(cls, size: int) -> "PmxIndexRemap":
        """Return the identity mapping for one collection size."""

        validated_size = _require_nonnegative_plain_int(size, "size")
        return cls(
            targets=tuple(range(validated_size)),
            new_size=validated_size,
        )

    @property
    def old_size(self) -> int:
        """Return the size of the complete old index domain."""

        return len(self.targets)

    @property
    def removed_old_indices(self) -> tuple[int, ...]:
        """Return removed old indices in deterministic old-index order."""

        return tuple(
            old_index
            for old_index, target in enumerate(self.targets)
            if target is None
        )

    @property
    def has_new_indices_without_old_source(self) -> bool:
        """Whether the new range contains positions not sourced from old data."""

        return bool(self.new_indices_without_old_source)

    @property
    def is_identity(self) -> bool:
        """Whether every old index maps to itself with no added new position."""

        return (
            not self.new_indices_without_old_source
            and self.old_size == self.new_size
            and all(
                target == old_index
                for old_index, target in enumerate(self.targets)
            )
        )

    def target_for(self, old_index: int) -> PmxIndexRemapTarget:
        """Return the mapped new index or ``None`` for one old index."""

        validated_index = _require_nonnegative_plain_int(old_index, "old_index")
        if validated_index >= self.old_size:
            raise ValueError(
                f"old_index {validated_index} is outside old_size "
                f"{self.old_size}."
            )
        return self.targets[validated_index]


__all__ = (
    "PmxIndexRemap",
    "PmxIndexRemapTarget",
)
