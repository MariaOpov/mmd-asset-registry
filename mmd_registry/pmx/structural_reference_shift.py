"""Internal deterministic reference-shift planning for structural insertion.

This module converts one validated source-domain collection insertion intent into
an insertion-capable :class:`PmxIndexRemap` without constructing a legacy
``PmxCollectionTransform``. The legacy transform remains delete/reorder/no-op
only and continues to reject new indices without old sources.

The planner also records new indices in original insertion-request order. That
evidence is distinct from ``PmxIndexRemap.new_indices_without_old_source``,
which must remain strictly increasing for dense-range validation.

No PMX payload is accepted or materialized here.
"""

from __future__ import annotations

from dataclasses import dataclass

from mmd_registry.pmx.index_remap import PmxIndexRemap
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.pmx.structural_capacity import (
    PmxStructuralCapacityAnalysis,
    analyze_structural_capacity,
)
from mmd_registry.pmx.structural_insert_intent import (
    PmxCollectionInsertionIntent,
    PmxStructuralInsertPositionMode,
)


def _require_nonnegative_plain_int(value: object, field_name: str) -> int:
    """Return one exact nonnegative integer, rejecting booleans."""

    if type(value) is not int:
        raise TypeError(f"{field_name} must be an integer.")
    if value < 0:
        raise ValueError(f"{field_name} must be nonnegative.")
    return value


class PmxStructuralReferenceShiftError(ValueError):
    """Raised when one insertion shift plan cannot be safely constructed."""


@dataclass(frozen=True, slots=True)
class PmxCollectionReferenceShiftPlan:
    """Immutable successful shift evidence for one target collection."""

    insertion: PmxCollectionInsertionIntent
    current_count: int
    index_width: int
    capacity: PmxStructuralCapacityAnalysis
    remap: PmxIndexRemap
    new_indices_in_request_order: tuple[int, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.insertion, PmxCollectionInsertionIntent):
            raise TypeError("insertion must be a PmxCollectionInsertionIntent value.")
        _require_nonnegative_plain_int(self.current_count, "current_count")
        _require_nonnegative_plain_int(self.index_width, "index_width")
        if not isinstance(self.capacity, PmxStructuralCapacityAnalysis):
            raise TypeError("capacity must be a PmxStructuralCapacityAnalysis value.")
        if not isinstance(self.remap, PmxIndexRemap):
            raise TypeError("remap must be a PmxIndexRemap value.")
        if type(self.new_indices_in_request_order) is not tuple:
            raise TypeError("new_indices_in_request_order must be a tuple.")
        if any(
            type(new_index) is not int
            for new_index in self.new_indices_in_request_order
        ):
            raise TypeError(
                "new_indices_in_request_order must contain only integer indices."
            )

        if self.capacity.target_kind is not self.insertion.target_kind:
            raise ValueError("capacity target_kind does not match insertion target_kind.")
        if self.capacity.current_count != self.current_count:
            raise ValueError("capacity current_count does not match plan current_count.")
        if self.capacity.insert_count != self.insertion.insert_count:
            raise ValueError("capacity insert_count does not match insertion intent.")
        if self.capacity.index_width != self.index_width:
            raise ValueError("capacity index_width does not match plan index_width.")
        if not self.capacity.representable:
            raise ValueError("successful shift plan requires representable capacity.")

        if self.remap.old_size != self.current_count:
            raise ValueError("remap old_size does not match plan current_count.")
        if self.remap.new_size != self.capacity.result_count:
            raise ValueError("remap new_size does not match capacity result_count.")

        if len(self.new_indices_in_request_order) != self.insertion.insert_count:
            raise ValueError(
                "new_indices_in_request_order length does not match insert_count."
            )
        if len(set(self.new_indices_in_request_order)) != len(
            self.new_indices_in_request_order
        ):
            raise ValueError("new_indices_in_request_order cannot contain duplicates.")
        if any(
            new_index < 0 or new_index >= self.remap.new_size
            for new_index in self.new_indices_in_request_order
        ):
            raise ValueError(
                "new_indices_in_request_order contains an index outside new_size."
            )

        if tuple(sorted(self.new_indices_in_request_order)) != (
            self.remap.new_indices_without_old_source
        ):
            raise ValueError(
                "request-order insertion indices do not match remap new-only positions."
            )

        self.insertion.validate_for_source_size(self.current_count)
        expected_targets, expected_request_indices = _derive_reference_shift_mapping(
            self.insertion,
            self.current_count,
        )
        if self.remap.targets != expected_targets:
            raise ValueError(
                "remap targets do not match source-domain insertion shift semantics."
            )
        if self.new_indices_in_request_order != expected_request_indices:
            raise ValueError(
                "request-order insertion indices do not match insertion positions."
            )

    @property
    def target_kind(self) -> PmxReferenceTargetKind:
        """Return the insertion target kind."""

        return self.insertion.target_kind

    @property
    def insert_count(self) -> int:
        """Return the number of inserted records represented by this plan."""

        return self.insertion.insert_count

    @property
    def result_count(self) -> int:
        """Return the resulting collection size."""

        return self.capacity.result_count

    def new_index_for_insertion(self, insertion_index: int) -> int:
        """Return the new index assigned to one insertion request ordinal."""

        index = _require_nonnegative_plain_int(insertion_index, "insertion_index")
        if index >= self.insert_count:
            raise ValueError(
                f"insertion_index {index} is outside insert_count {self.insert_count}."
            )
        return self.new_indices_in_request_order[index]

    def to_dict(self) -> dict[str, object]:
        """Return deterministic JSON-ready shift evidence."""

        return {
            "target_kind": self.target_kind.value,
            "current_count": self.current_count,
            "insert_count": self.insert_count,
            "result_count": self.result_count,
            "index_width": self.index_width,
            "capacity": self.capacity.to_dict(),
            "remap": {
                "targets": list(self.remap.targets),
                "new_size": self.remap.new_size,
                "new_indices_without_old_source": list(
                    self.remap.new_indices_without_old_source
                ),
            },
            "new_indices_in_request_order": list(
                self.new_indices_in_request_order
            ),
        }


def _derive_reference_shift_mapping(
    insertion: PmxCollectionInsertionIntent,
    current_count: int,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Derive old targets and insertion placements from source-domain positions."""

    anchored_request_indices: dict[int, list[int]] = {}
    append_request_indices: list[int] = []

    for request_index, position in enumerate(insertion.positions):
        if position.mode is PmxStructuralInsertPositionMode.APPEND:
            append_request_indices.append(request_index)
            continue

        assert position.source_index is not None
        anchored_request_indices.setdefault(position.source_index, []).append(
            request_index
        )

    targets = [0] * current_count
    request_new_indices = [0] * insertion.insert_count
    next_new_index = 0

    for old_index in range(current_count):
        for request_index in anchored_request_indices.get(old_index, ()):
            request_new_indices[request_index] = next_new_index
            next_new_index += 1

        targets[old_index] = next_new_index
        next_new_index += 1

    for request_index in append_request_indices:
        request_new_indices[request_index] = next_new_index
        next_new_index += 1

    expected_result_count = current_count + insertion.insert_count
    if next_new_index != expected_result_count:
        raise AssertionError(
            "reference-shift derivation produced an inconsistent resulting count."
        )

    return tuple(targets), tuple(request_new_indices)


def plan_collection_reference_shift(
    insertion: PmxCollectionInsertionIntent,
    *,
    current_count: int,
    index_width: int,
) -> PmxCollectionReferenceShiftPlan:
    """Build one capacity-checked insertion shift plan.

    Source-domain anchors are validated before planning. Capacity is evaluated
    before allocating the old-domain remap so obviously impossible counts fail
    closed without constructing a large mapping.

    Final structural order is derived as follows:

    * before each old source index, emit all insertion requests anchored there
      in original request order;
    * emit the surviving old record;
    * after the complete old source domain, emit append requests in original
      request order.

    The resulting ``PmxIndexRemap`` remains the old-index to new-index identity
    authority. ``new_indices_in_request_order`` is additional placement evidence
    for later payload materialization; it is not a second old-index mapping.
    """

    if not isinstance(insertion, PmxCollectionInsertionIntent):
        raise TypeError("insertion must be a PmxCollectionInsertionIntent value.")

    count = _require_nonnegative_plain_int(current_count, "current_count")
    insertion.validate_for_source_size(count)

    capacity = analyze_structural_capacity(
        insertion.target_kind,
        current_count=count,
        insert_count=insertion.insert_count,
        index_width=index_width,
    )
    if not capacity.representable:
        reason = (
            "declared index width cannot represent resulting collection"
            if not capacity.width_representable
            else "resulting collection exceeds PMX signed 32-bit section-count limit"
        )
        raise PmxStructuralReferenceShiftError(
            f"cannot plan {insertion.target_kind.value} insertion shift: {reason}."
        )

    targets, new_indices_in_request_order = _derive_reference_shift_mapping(
        insertion,
        count,
    )
    remap = PmxIndexRemap(
        targets=targets,
        new_size=capacity.result_count,
        new_indices_without_old_source=tuple(
            sorted(new_indices_in_request_order)
        ),
    )

    return PmxCollectionReferenceShiftPlan(
        insertion=insertion,
        current_count=count,
        index_width=capacity.index_width,
        capacity=capacity,
        remap=remap,
        new_indices_in_request_order=new_indices_in_request_order,
    )


__all__ = (
    "PmxStructuralReferenceShiftError",
    "PmxCollectionReferenceShiftPlan",
    "plan_collection_reference_shift",
)
