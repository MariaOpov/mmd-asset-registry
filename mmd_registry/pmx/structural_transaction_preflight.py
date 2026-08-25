"""Internal whole-transaction capacity preflight for v0.9.3.

CP15 computes final counts and declared-width capacity evidence for all six PMX
target collections before any transaction materialization.  It never widens an
index field, mutates a document, validates payload records, or performs I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mmd_registry.pmx.collection_transform import (
    PmxCollectionTransform,
    PmxStructuralTransformIntent,
)
from mmd_registry.pmx.document import VALID_PMX_INDEX_SIZES
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.pmx.structural_capacity import (
    PmxStructuralCapacityAnalysis,
    analyze_structural_capacity,
)
from mmd_registry.pmx.structural_transaction_insertion import (
    PmxStructuralTransactionInsertionOperation,
)


_TARGET_KIND_ORDER = tuple(PmxReferenceTargetKind)


def _require_nonnegative_plain_int(value: object, field_name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be an integer.")
    if value < 0:
        raise ValueError(f"{field_name} must be nonnegative.")
    return value


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
                raise TypeError(
                    f"{field_name}[{position}] width must be an integer."
                )
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


class PmxStructuralTransactionCapacityPreflightError(ValueError):
    """Raised after complete six-target capacity analysis finds blockers."""


def _blocker_reason(analysis: PmxStructuralCapacityAnalysis) -> str:
    if not analysis.width_representable and not analysis.count_representable:
        return "declared_index_width_and_section_count"
    if not analysis.width_representable:
        return "declared_index_width"
    if not analysis.count_representable:
        return "section_count"
    raise AssertionError("representable capacity evidence is not a blocker")


@dataclass(frozen=True, slots=True)
class PmxStructuralTransactionCapacityPreflight:
    """Immutable all-target final-count and capacity evidence."""

    source_counts: tuple[tuple[PmxReferenceTargetKind, int], ...]
    index_widths: tuple[tuple[PmxReferenceTargetKind, int], ...]
    transforms: tuple[PmxCollectionTransform, ...] = ()
    operations: tuple[PmxStructuralTransactionInsertionOperation, ...] = ()
    analyses: tuple[PmxStructuralCapacityAnalysis, ...] = field(init=False)

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
        transform_intent = PmxStructuralTransformIntent(self.transforms)
        _validate_operations(self.operations)

        for transform in transform_intent.transforms:
            expected_count = self._environment_value(
                self.source_counts,
                transform.kind,
            )
            if transform.old_size != expected_count:
                raise ValueError(
                    f"{transform.kind.value} transform old_size must match "
                    "its captured source count."
                )

        analyses = tuple(
            analyze_structural_capacity(
                target_kind,
                current_count=self._survivor_count(
                    target_kind,
                    transform_intent,
                ),
                insert_count=sum(
                    operation.target_kind is target_kind
                    for operation in self.operations
                ),
                index_width=self._environment_value(
                    self.index_widths,
                    target_kind,
                ),
            )
            for target_kind in _TARGET_KIND_ORDER
        )
        blockers = tuple(
            analysis for analysis in analyses if not analysis.representable
        )
        if blockers:
            rendered = "; ".join(
                f"{analysis.target_kind.value}("
                f"final_count={analysis.result_count},"
                f"declared_width={analysis.index_width},"
                f"effective_max_count={analysis.effective_max_count},"
                f"reason={_blocker_reason(analysis)})"
                for analysis in blockers
            )
            raise PmxStructuralTransactionCapacityPreflightError(
                "whole-transaction capacity preflight failed without "
                f"automatic width expansion: {rendered}."
            )

        object.__setattr__(self, "analyses", analyses)

    @staticmethod
    def _environment_value(
        entries: tuple[tuple[PmxReferenceTargetKind, int], ...],
        target_kind: PmxReferenceTargetKind,
    ) -> int:
        for kind, value in entries:
            if kind is target_kind:
                return value
        raise AssertionError(f"missing environment value for {target_kind.value}")

    def _survivor_count(
        self,
        target_kind: PmxReferenceTargetKind,
        transform_intent: PmxStructuralTransformIntent,
    ) -> int:
        transform = transform_intent.transform_for(target_kind)
        if transform is not None:
            return transform.new_size
        return self._environment_value(self.source_counts, target_kind)

    @property
    def final_counts(
        self,
    ) -> tuple[tuple[PmxReferenceTargetKind, int], ...]:
        """Return all six final counts in canonical target order."""

        return tuple(
            (analysis.target_kind, analysis.result_count)
            for analysis in self.analyses
        )

    @property
    def all_representable(self) -> bool:
        """Whether every declared target width and count limit is satisfied."""

        return all(analysis.representable for analysis in self.analyses)

    def analysis_for(
        self,
        target_kind: PmxReferenceTargetKind,
    ) -> PmxStructuralCapacityAnalysis:
        """Return one target's immutable capacity evidence."""

        if not isinstance(target_kind, PmxReferenceTargetKind):
            raise TypeError("target_kind must be a PmxReferenceTargetKind value.")
        for analysis in self.analyses:
            if analysis.target_kind is target_kind:
                return analysis
        raise AssertionError(f"missing capacity analysis for {target_kind.value}")


def preflight_structural_transaction_capacity(
    *,
    source_counts: tuple[tuple[PmxReferenceTargetKind, int], ...],
    index_widths: tuple[tuple[PmxReferenceTargetKind, int], ...],
    transforms: tuple[PmxCollectionTransform, ...] = (),
    operations: tuple[PmxStructuralTransactionInsertionOperation, ...] = (),
) -> PmxStructuralTransactionCapacityPreflight:
    """Prove all six final counts without changing declared index widths."""

    return PmxStructuralTransactionCapacityPreflight(
        source_counts=source_counts,
        index_widths=index_widths,
        transforms=transforms,
        operations=operations,
    )


__all__ = (
    "PmxStructuralTransactionCapacityPreflight",
    "PmxStructuralTransactionCapacityPreflightError",
    "preflight_structural_transaction_capacity",
)
