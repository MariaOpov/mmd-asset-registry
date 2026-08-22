"""Internal final-state reference resolution for structural transactions."""

from __future__ import annotations

from dataclasses import dataclass

from mmd_registry.pmx.index_remap import PmxIndexRemap
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind


def _require_nonnegative_plain_int(value: object, field_name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be an integer.")
    if value < 0:
        raise ValueError(f"{field_name} must be nonnegative.")
    return value


@dataclass(frozen=True, slots=True)
class PmxStructuralTransactionTargetRemap:
    """One internal target kind paired with its authoritative final remap."""

    target_kind: PmxReferenceTargetKind
    remap: PmxIndexRemap

    def __post_init__(self) -> None:
        if not isinstance(self.target_kind, PmxReferenceTargetKind):
            raise TypeError("target_kind must be a PmxReferenceTargetKind value.")
        if not isinstance(self.remap, PmxIndexRemap):
            raise TypeError("remap must be a PmxIndexRemap value.")


@dataclass(frozen=True, slots=True)
class PmxStructuralTransactionIdentityBinding:
    """Bind one validated request-local identity to a planned final index."""

    target_kind: PmxReferenceTargetKind
    new_id: str
    operation_index: int
    final_index: int

    def __post_init__(self) -> None:
        if not isinstance(self.target_kind, PmxReferenceTargetKind):
            raise TypeError("target_kind must be a PmxReferenceTargetKind value.")
        if not isinstance(self.new_id, str):
            raise TypeError("new_id must be a string.")
        _require_nonnegative_plain_int(self.operation_index, "operation_index")
        _require_nonnegative_plain_int(self.final_index, "final_index")


@dataclass(frozen=True, slots=True)
class PmxStructuralTransactionReferenceResolver:
    """Resolve captured-source, local-new and sentinel reference forms."""

    source_counts: tuple[tuple[PmxReferenceTargetKind, int], ...]
    target_remaps: tuple[PmxStructuralTransactionTargetRemap, ...] = ()
    identities: tuple[PmxStructuralTransactionIdentityBinding, ...] = ()

    def __post_init__(self) -> None:
        self._validate_source_counts()
        self._validate_target_remaps()
        self._validate_identities()

    def _validate_source_counts(self) -> None:
        if type(self.source_counts) is not tuple:
            raise TypeError("source_counts must be a tuple.")
        expected_kinds = tuple(PmxReferenceTargetKind)
        if len(self.source_counts) != len(expected_kinds):
            raise ValueError(
                "source_counts must contain all six target kinds "
                "in canonical order."
            )
        for position, entry in enumerate(self.source_counts):
            if type(entry) is not tuple or len(entry) != 2:
                raise TypeError(
                    "source_counts entries must be (PmxReferenceTargetKind, count) "
                    "tuples."
                )
            target_kind, count = entry
            if target_kind is not expected_kinds[position]:
                raise ValueError(
                    "source_counts must contain all six target kinds "
                    "in canonical order."
                )
            _require_nonnegative_plain_int(
                count,
                f"source_counts[{position}] count",
            )

    def _validate_target_remaps(self) -> None:
        if type(self.target_remaps) is not tuple:
            raise TypeError("target_remaps must be a tuple.")
        previous_rank = -1
        for target_remap in self.target_remaps:
            if not isinstance(
                target_remap,
                PmxStructuralTransactionTargetRemap,
            ):
                raise TypeError(
                    "target_remaps must contain only "
                    "PmxStructuralTransactionTargetRemap values."
                )
            rank = tuple(PmxReferenceTargetKind).index(target_remap.target_kind)
            if rank <= previous_rank:
                raise ValueError(
                    "target_remaps must follow canonical target-kind order "
                    "without duplicates."
                )
            previous_rank = rank
            source_count = self._source_count(target_remap.target_kind)
            if target_remap.remap.old_size != source_count:
                raise ValueError(
                    f"{target_remap.target_kind.value} remap old_size must match "
                    "its captured source count."
                )

    def _validate_identities(self) -> None:
        if type(self.identities) is not tuple:
            raise TypeError("identities must be a tuple.")
        seen_ids: set[str] = set()
        seen_operation_indices: set[int] = set()
        seen_final_targets: set[tuple[PmxReferenceTargetKind, int]] = set()
        for identity in self.identities:
            if not isinstance(
                identity,
                PmxStructuralTransactionIdentityBinding,
            ):
                raise TypeError(
                    "identities must contain only "
                    "PmxStructuralTransactionIdentityBinding values."
                )
            if identity.new_id in seen_ids:
                raise ValueError(
                    f"request-local new_id {identity.new_id!r} must be "
                    "globally unique."
                )
            seen_ids.add(identity.new_id)
            if identity.operation_index in seen_operation_indices:
                raise ValueError(
                    "identity operation_index values must be globally unique."
                )
            seen_operation_indices.add(identity.operation_index)

            target_remap = self._target_remap(identity.target_kind)
            if target_remap is None:
                raise ValueError(
                    f"new_id {identity.new_id!r} has no planned "
                    f"{identity.target_kind.value} target remap."
                )
            if (
                identity.final_index
                not in target_remap.remap.new_indices_without_old_source
            ):
                raise ValueError(
                    f"new_id {identity.new_id!r} final_index must be a planned "
                    f"new-only {identity.target_kind.value} index."
                )
            final_target = (identity.target_kind, identity.final_index)
            if final_target in seen_final_targets:
                raise ValueError(
                    "identity bindings cannot reuse one target final index."
                )
            seen_final_targets.add(final_target)

    def _source_count(self, target_kind: PmxReferenceTargetKind) -> int:
        for kind, count in self.source_counts:
            if kind is target_kind:
                return count
        raise AssertionError(f"missing source count for {target_kind.value}")

    def _target_remap(
        self,
        target_kind: PmxReferenceTargetKind,
    ) -> PmxStructuralTransactionTargetRemap | None:
        for target_remap in self.target_remaps:
            if target_remap.target_kind is target_kind:
                return target_remap
        return None

    def resolve_source_reference(
        self,
        target_kind: PmxReferenceTargetKind,
        value: object,
        *,
        allow_sentinel: bool,
        field_name: str,
    ) -> int:
        """Resolve one captured-source or sentinel reference through final state."""

        if not isinstance(target_kind, PmxReferenceTargetKind):
            raise TypeError("target_kind must be a PmxReferenceTargetKind value.")
        if type(allow_sentinel) is not bool:
            raise TypeError("allow_sentinel must be a boolean.")
        if type(field_name) is not str:
            raise TypeError("field_name must be a string.")
        if not field_name:
            raise ValueError("field_name must be a non-empty string.")

        if type(value) is not int:
            raise TypeError(f"{field_name} source reference must be an integer.")
        if value == -1:
            if allow_sentinel:
                return -1
            raise ValueError(f"{field_name} does not allow the -1 sentinel.")

        source_count = self._source_count(target_kind)
        if value < 0 or value >= source_count:
            raise ValueError(
                f"{field_name} must reference the captured source "
                f"{target_kind.value} domain."
            )
        target_remap = self._target_remap(target_kind)
        if target_remap is None:
            return value
        mapped = target_remap.remap.target_for(value)
        if mapped is None:
            raise ValueError(
                f"{field_name} references removed captured-source "
                f"{target_kind.value}[{value}]."
            )
        return mapped

    def resolve_new_reference(
        self,
        target_kind: PmxReferenceTargetKind,
        new_id: object,
        *,
        field_name: str,
    ) -> int:
        """Resolve one validated DTO local ID to its planned final index."""

        if not isinstance(target_kind, PmxReferenceTargetKind):
            raise TypeError("target_kind must be a PmxReferenceTargetKind value.")
        if not isinstance(new_id, str):
            raise TypeError(f"{field_name} new_id must be a string.")
        if type(field_name) is not str:
            raise TypeError("field_name must be a string.")
        if not field_name:
            raise ValueError("field_name must be a non-empty string.")
        for identity in self.identities:
            if identity.new_id != new_id:
                continue
            if identity.target_kind is not target_kind:
                raise ValueError(
                    f"{field_name} new reference targets {target_kind.value} but "
                    f"new_id {new_id!r} belongs to "
                    f"{identity.target_kind.value}."
                )
            return identity.final_index
        raise ValueError(
            f"{field_name} references unknown request-local "
            f"new_id {new_id!r}."
        )


__all__ = (
    "PmxStructuralTransactionIdentityBinding",
    "PmxStructuralTransactionReferenceResolver",
    "PmxStructuralTransactionTargetRemap",
)
