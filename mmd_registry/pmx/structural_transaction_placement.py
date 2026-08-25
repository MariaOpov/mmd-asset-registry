"""Internal insertion placement over structural survivor transforms.

This CP11-CP13 layer composes one released ``PmxCollectionTransform`` with
validated CP10 insertion operations. Source anchors follow their named
surviving old records through the transform's final survivor order. The result
is exactly one insertion-capable ``PmxIndexRemap``; no independent transform
and insertion maps are retained.

CP12 blocks deleted insertion anchors and CP13 accepts the released complete
survivor sequence when deletion and reorder coexist. The planner accepts no
PMX payload, does not mutate a document, and performs no materialization or
filesystem I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mmd_registry.pmx.collection_transform import PmxCollectionTransform
from mmd_registry.pmx.index_remap import PmxIndexRemap
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.pmx.structural_capacity import (
    PmxStructuralCapacityAnalysis,
    analyze_structural_capacity,
)
from mmd_registry.pmx.structural_insert_intent import (
    PmxStructuralInsertPositionMode,
)
from mmd_registry.pmx.structural_transaction_insertion import (
    PmxStructuralTransactionInsertionBinding,
    PmxStructuralTransactionInsertionOperation,
)
from mmd_registry.pmx.structural_transaction_reference import (
    PmxStructuralTransactionIdentityBinding,
    PmxStructuralTransactionTargetRemap,
)


def _require_nonnegative_plain_int(value: object, field_name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be an integer.")
    if value < 0:
        raise ValueError(f"{field_name} must be nonnegative.")
    return value


class PmxStructuralTransactionPlacementError(ValueError):
    """Raised when CP11-CP13 cannot derive one safe combined placement."""


def _validate_operations(
    transform: PmxCollectionTransform,
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
        if operation.target_kind is not transform.kind:
            raise ValueError(
                f"operations[{position}] target_kind must match "
                "transform kind."
            )
        if operation.request_ordinal <= previous_ordinal:
            raise ValueError(
                "operations must follow strictly increasing unique "
                "request_ordinal order."
            )
        previous_ordinal = operation.request_ordinal
        operation.position.validate_for_source_size(transform.old_size)
        if operation.position.mode is PmxStructuralInsertPositionMode.INSERT_BEFORE:
            assert operation.position.source_index is not None
            if transform.remap.target_for(operation.position.source_index) is None:
                raise PmxStructuralTransactionPlacementError(
                    "insert_before anchor "
                    f"{transform.kind.value}[{operation.position.source_index}] "
                    "is deleted by the same transaction."
                )

        if operation.new_id is None:
            continue
        if operation.new_id in seen_ids:
            raise ValueError(
                f"request-local new_id {operation.new_id!r} must be "
                "globally unique."
            )
        seen_ids.add(operation.new_id)


def _derive_combined_mapping(
    transform: PmxCollectionTransform,
    operations: tuple[PmxStructuralTransactionInsertionOperation, ...],
) -> tuple[PmxIndexRemap, tuple[int, ...]]:
    anchored_operation_indices: dict[int, list[int]] = {}
    append_operation_indices: list[int] = []

    for operation_index, operation in enumerate(operations):
        if operation.position.mode is PmxStructuralInsertPositionMode.APPEND:
            append_operation_indices.append(operation_index)
            continue

        assert operation.position.source_index is not None
        anchored_operation_indices.setdefault(
            operation.position.source_index,
            [],
        ).append(operation_index)

    targets: list[int | None] = [None] * transform.old_size
    operation_new_indices = [0] * len(operations)
    next_new_index = 0

    for old_index in transform.old_indices_in_new_order:
        for operation_index in anchored_operation_indices.get(old_index, ()):
            operation_new_indices[operation_index] = next_new_index
            next_new_index += 1

        targets[old_index] = next_new_index
        next_new_index += 1

    for operation_index in append_operation_indices:
        operation_new_indices[operation_index] = next_new_index
        next_new_index += 1

    expected_result_count = transform.new_size + len(operations)
    if next_new_index != expected_result_count:
        raise AssertionError(
            "combined placement produced an inconsistent resulting count."
        )

    remap = PmxIndexRemap(
        targets=tuple(targets),
        new_size=expected_result_count,
        new_indices_without_old_source=tuple(sorted(operation_new_indices)),
    )
    return remap, tuple(operation_new_indices)


@dataclass(frozen=True, slots=True)
class PmxStructuralTransactionCollectionPlacement:
    """One immutable, capacity-checked combined target placement."""

    transform: PmxCollectionTransform
    index_width: int
    operations: tuple[PmxStructuralTransactionInsertionOperation, ...] = ()
    capacity: PmxStructuralCapacityAnalysis = field(init=False)
    remap: PmxIndexRemap = field(init=False)
    bindings: tuple[PmxStructuralTransactionInsertionBinding, ...] = field(
        init=False
    )
    identities: tuple[PmxStructuralTransactionIdentityBinding, ...] = field(
        init=False
    )
    target_remap: PmxStructuralTransactionTargetRemap = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.transform, PmxCollectionTransform):
            raise TypeError("transform must be a PmxCollectionTransform value.")
        _validate_operations(self.transform, self.operations)

        capacity = analyze_structural_capacity(
            self.transform.kind,
            current_count=self.transform.new_size,
            insert_count=len(self.operations),
            index_width=self.index_width,
        )
        if not capacity.representable:
            reason = (
                "declared index width cannot represent resulting collection"
                if not capacity.width_representable
                else "resulting collection exceeds PMX signed 32-bit "
                "section-count limit"
            )
            raise PmxStructuralTransactionPlacementError(
                f"cannot plan {self.transform.kind.value} combined placement: "
                f"{reason}."
            )

        remap, new_indices = _derive_combined_mapping(
            self.transform,
            self.operations,
        )
        bindings = tuple(
            PmxStructuralTransactionInsertionBinding(
                request_ordinal=operation.request_ordinal,
                target_kind=operation.target_kind,
                target_insertion_index=operation_index,
                final_index=new_indices[operation_index],
            )
            for operation_index, operation in enumerate(self.operations)
        )
        identities = tuple(
            sorted(
                (
                    PmxStructuralTransactionIdentityBinding(
                        target_kind=operation.target_kind,
                        new_id=operation.new_id,
                        operation_index=operation.request_ordinal,
                        final_index=new_indices[operation_index],
                    )
                    for operation_index, operation in enumerate(self.operations)
                    if operation.new_id is not None
                ),
                key=lambda identity: (
                    identity.final_index,
                    identity.new_id,
                ),
            )
        )

        object.__setattr__(self, "capacity", capacity)
        object.__setattr__(self, "remap", remap)
        object.__setattr__(self, "bindings", bindings)
        object.__setattr__(self, "identities", identities)
        object.__setattr__(
            self,
            "target_remap",
            PmxStructuralTransactionTargetRemap(
                target_kind=self.transform.kind,
                remap=remap,
            ),
        )

    @property
    def target_kind(self) -> PmxReferenceTargetKind:
        """Return the target collection kind."""

        return self.transform.kind

    @property
    def source_count(self) -> int:
        """Return the complete captured source-domain size."""

        return self.transform.old_size

    @property
    def result_count(self) -> int:
        """Return the final survivor-plus-insertion count."""

        return self.remap.new_size

    @property
    def new_indices_in_request_order(self) -> tuple[int, ...]:
        """Return final insertion positions in operation/request order."""

        return tuple(binding.final_index for binding in self.bindings)

    def new_index_for_operation(self, request_ordinal: int) -> int:
        """Return the final index for one global request tuple ordinal."""

        ordinal = _require_nonnegative_plain_int(
            request_ordinal,
            "request_ordinal",
        )
        for binding in self.bindings:
            if binding.request_ordinal == ordinal:
                return binding.final_index
        raise ValueError(
            f"request_ordinal {ordinal} is not an insertion in this placement."
        )


def plan_structural_transaction_collection_placement(
    transform: PmxCollectionTransform,
    *,
    index_width: int,
    operations: tuple[PmxStructuralTransactionInsertionOperation, ...] = (),
) -> PmxStructuralTransactionCollectionPlacement:
    """Compose source-anchored insertions with one CP11-CP13 transform."""

    return PmxStructuralTransactionCollectionPlacement(
        transform=transform,
        index_width=index_width,
        operations=operations,
    )


__all__ = (
    "PmxStructuralTransactionCollectionPlacement",
    "PmxStructuralTransactionPlacementError",
    "plan_structural_transaction_collection_placement",
)
