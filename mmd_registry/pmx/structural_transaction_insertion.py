"""Internal multi-insert composition for structural transactions.

This CP10 layer groups already-validated insertion evidence by target kind,
reuses the released shift/capacity authority, and joins its final maps to the
CP08 reference resolver and CP09 dependency evidence. It accepts no collection
transform or PMX payload and performs no document mutation or materialization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType

from mmd_registry.pmx.document import VALID_PMX_INDEX_SIZES
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.pmx.structural_insert_intent import (
    PmxCollectionInsertionIntent,
    PmxStructuralInsertPosition,
)
from mmd_registry.pmx.structural_reference_shift import (
    PmxCollectionReferenceShiftPlan,
    plan_collection_reference_shift,
)
from mmd_registry.pmx.structural_transaction_dependency import (
    PmxStructuralTransactionDependencyEvidence,
    build_structural_transaction_dependency_evidence,
)
from mmd_registry.pmx.structural_transaction_reference import (
    PmxStructuralTransactionIdentityBinding,
    PmxStructuralTransactionReferenceResolver,
    PmxStructuralTransactionTargetRemap,
)


_TARGET_KIND_ORDER = tuple(PmxReferenceTargetKind)
_TARGET_KIND_RANK = MappingProxyType(
    {
        target_kind: rank
        for rank, target_kind in enumerate(_TARGET_KIND_ORDER)
    }
)


def _require_nonnegative_plain_int(value: object, field_name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be an integer.")
    if value < 0:
        raise ValueError(f"{field_name} must be nonnegative.")
    return value


@dataclass(frozen=True, slots=True)
class PmxStructuralTransactionInsertionOperation:
    """One validated insertion's transaction ordinal and placement evidence."""

    request_ordinal: int
    target_kind: PmxReferenceTargetKind
    position: PmxStructuralInsertPosition
    new_id: str | None = None

    def __post_init__(self) -> None:
        _require_nonnegative_plain_int(self.request_ordinal, "request_ordinal")
        if not isinstance(self.target_kind, PmxReferenceTargetKind):
            raise TypeError("target_kind must be a PmxReferenceTargetKind value.")
        if not isinstance(self.position, PmxStructuralInsertPosition):
            raise TypeError("position must be a PmxStructuralInsertPosition value.")
        if self.new_id is not None and not isinstance(self.new_id, str):
            raise TypeError("new_id must be a string or None.")


@dataclass(frozen=True, slots=True)
class PmxStructuralTransactionInsertionBinding:
    """Bind one insertion request ordinal to one deterministic final index."""

    request_ordinal: int
    target_kind: PmxReferenceTargetKind
    target_insertion_index: int
    final_index: int

    def __post_init__(self) -> None:
        _require_nonnegative_plain_int(self.request_ordinal, "request_ordinal")
        if not isinstance(self.target_kind, PmxReferenceTargetKind):
            raise TypeError("target_kind must be a PmxReferenceTargetKind value.")
        _require_nonnegative_plain_int(
            self.target_insertion_index,
            "target_insertion_index",
        )
        _require_nonnegative_plain_int(self.final_index, "final_index")


def _validate_environment(
    entries: tuple[tuple[PmxReferenceTargetKind, int], ...],
    *,
    field_name: str,
    index_widths: bool,
) -> None:
    if type(entries) is not tuple:
        raise TypeError(f"{field_name} must be a tuple.")
    if len(entries) != len(_TARGET_KIND_ORDER):
        raise ValueError(
            f"{field_name} must contain all six target kinds in canonical order."
        )
    for position, entry in enumerate(entries):
        if type(entry) is not tuple or len(entry) != 2:
            raise TypeError(
                f"{field_name} entries must be "
                "(PmxReferenceTargetKind, integer) tuples."
            )
        target_kind, value = entry
        if target_kind is not _TARGET_KIND_ORDER[position]:
            raise ValueError(
                f"{field_name} must contain all six target kinds "
                "in canonical order."
            )
        if index_widths:
            if type(value) is not int:
                raise TypeError(f"{field_name}[{position}] width must be an integer.")
            if value not in VALID_PMX_INDEX_SIZES:
                raise ValueError(
                    f"{field_name}[{position}] width must be one of "
                    f"{sorted(VALID_PMX_INDEX_SIZES)}."
                )
            continue
        _require_nonnegative_plain_int(
            value,
            f"{field_name}[{position}] count",
        )


def _validate_operations(
    operations: tuple[PmxStructuralTransactionInsertionOperation, ...],
) -> None:
    if type(operations) is not tuple:
        raise TypeError("operations must be a tuple.")
    previous_ordinal = -1
    seen_ids: set[str] = set()
    for position, operation in enumerate(operations):
        if not isinstance(
            operation,
            PmxStructuralTransactionInsertionOperation,
        ):
            raise TypeError(
                f"operations[{position}] must be a "
                "PmxStructuralTransactionInsertionOperation value."
            )
        if operation.request_ordinal <= previous_ordinal:
            raise ValueError(
                "operations must follow strictly increasing unique "
                "request_ordinal order."
            )
        previous_ordinal = operation.request_ordinal
        if operation.new_id is None:
            continue
        if operation.new_id in seen_ids:
            raise ValueError(
                f"request-local new_id {operation.new_id!r} must be "
                "globally unique."
            )
        seen_ids.add(operation.new_id)


@dataclass(frozen=True, slots=True)
class PmxStructuralTransactionInsertionPlan:
    """One immutable capacity-checked insertion-only transaction plan."""

    source_counts: tuple[tuple[PmxReferenceTargetKind, int], ...]
    index_widths: tuple[tuple[PmxReferenceTargetKind, int], ...]
    operations: tuple[PmxStructuralTransactionInsertionOperation, ...] = ()
    dependency: PmxStructuralTransactionDependencyEvidence = field(init=False)
    shifts: tuple[PmxCollectionReferenceShiftPlan, ...] = field(init=False)
    bindings: tuple[PmxStructuralTransactionInsertionBinding, ...] = field(
        init=False
    )
    identities: tuple[PmxStructuralTransactionIdentityBinding, ...] = field(
        init=False
    )
    reference_resolver: PmxStructuralTransactionReferenceResolver = field(
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        _validate_environment(
            self.source_counts,
            field_name="source_counts",
            index_widths=False,
        )
        _validate_environment(
            self.index_widths,
            field_name="index_widths",
            index_widths=True,
        )
        _validate_operations(self.operations)

        changed_targets = tuple(
            target_kind
            for target_kind in _TARGET_KIND_ORDER
            if any(
                operation.target_kind is target_kind
                for operation in self.operations
            )
        )
        dependency = build_structural_transaction_dependency_evidence(
            changed_targets
        )

        shifts: list[PmxCollectionReferenceShiftPlan] = []
        bindings_by_ordinal: dict[
            int,
            PmxStructuralTransactionInsertionBinding,
        ] = {}
        for target_kind in changed_targets:
            target_operations = tuple(
                operation
                for operation in self.operations
                if operation.target_kind is target_kind
            )
            insertion = PmxCollectionInsertionIntent(
                target_kind=target_kind,
                positions=tuple(
                    operation.position for operation in target_operations
                ),
            )
            shift = plan_collection_reference_shift(
                insertion,
                current_count=self._environment_value(
                    self.source_counts,
                    target_kind,
                ),
                index_width=self._environment_value(
                    self.index_widths,
                    target_kind,
                ),
            )
            shifts.append(shift)
            for target_insertion_index, operation in enumerate(
                target_operations
            ):
                bindings_by_ordinal[operation.request_ordinal] = (
                    PmxStructuralTransactionInsertionBinding(
                        request_ordinal=operation.request_ordinal,
                        target_kind=target_kind,
                        target_insertion_index=target_insertion_index,
                        final_index=shift.new_index_for_insertion(
                            target_insertion_index
                        ),
                    )
                )

        bindings = tuple(
            bindings_by_ordinal[operation.request_ordinal]
            for operation in self.operations
        )
        operation_by_ordinal = {
            operation.request_ordinal: operation
            for operation in self.operations
        }
        identity_values: list[PmxStructuralTransactionIdentityBinding] = []
        for binding in bindings:
            operation = operation_by_ordinal[binding.request_ordinal]
            if operation.new_id is None:
                continue
            identity_values.append(
                PmxStructuralTransactionIdentityBinding(
                    target_kind=binding.target_kind,
                    new_id=operation.new_id,
                    operation_index=binding.request_ordinal,
                    final_index=binding.final_index,
                )
            )
        identities = tuple(
            sorted(
                identity_values,
                key=lambda identity: (
                    _TARGET_KIND_RANK[identity.target_kind],
                    identity.final_index,
                    identity.new_id,
                ),
            )
        )
        target_remaps = tuple(
            PmxStructuralTransactionTargetRemap(
                target_kind=shift.target_kind,
                remap=shift.remap,
            )
            for shift in shifts
        )
        reference_resolver = PmxStructuralTransactionReferenceResolver(
            source_counts=self.source_counts,
            target_remaps=target_remaps,
            identities=identities,
        )

        object.__setattr__(self, "dependency", dependency)
        object.__setattr__(self, "shifts", tuple(shifts))
        object.__setattr__(self, "bindings", bindings)
        object.__setattr__(self, "identities", identities)
        object.__setattr__(self, "reference_resolver", reference_resolver)

    @staticmethod
    def _environment_value(
        entries: tuple[tuple[PmxReferenceTargetKind, int], ...],
        target_kind: PmxReferenceTargetKind,
    ) -> int:
        for kind, value in entries:
            if kind is target_kind:
                return value
        raise AssertionError(f"missing environment value for {target_kind.value}")

    @property
    def changed_targets(self) -> tuple[PmxReferenceTargetKind, ...]:
        return tuple(shift.target_kind for shift in self.shifts)

    @property
    def total_insert_count(self) -> int:
        return len(self.operations)

    def shift_for(
        self,
        target_kind: PmxReferenceTargetKind,
    ) -> PmxCollectionReferenceShiftPlan | None:
        if not isinstance(target_kind, PmxReferenceTargetKind):
            raise TypeError("target_kind must be a PmxReferenceTargetKind value.")
        for shift in self.shifts:
            if shift.target_kind is target_kind:
                return shift
        return None

    def binding_for_operation(
        self,
        request_ordinal: int,
    ) -> PmxStructuralTransactionInsertionBinding:
        ordinal = _require_nonnegative_plain_int(
            request_ordinal,
            "request_ordinal",
        )
        for binding in self.bindings:
            if binding.request_ordinal == ordinal:
                return binding
        raise ValueError(
            f"request_ordinal {ordinal} is not an insertion in this plan."
        )


def plan_structural_transaction_insertions(
    *,
    source_counts: tuple[tuple[PmxReferenceTargetKind, int], ...],
    index_widths: tuple[tuple[PmxReferenceTargetKind, int], ...],
    operations: tuple[PmxStructuralTransactionInsertionOperation, ...] = (),
) -> PmxStructuralTransactionInsertionPlan:
    """Compose validated insertion evidence without materializing PMX payloads."""

    return PmxStructuralTransactionInsertionPlan(
        source_counts=source_counts,
        index_widths=index_widths,
        operations=operations,
    )


__all__ = (
    "PmxStructuralTransactionInsertionBinding",
    "PmxStructuralTransactionInsertionOperation",
    "PmxStructuralTransactionInsertionPlan",
    "plan_structural_transaction_insertions",
)
