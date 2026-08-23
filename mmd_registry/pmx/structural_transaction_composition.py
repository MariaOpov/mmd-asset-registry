"""Internal mixed-target composition for structural transactions.

CP14 joins the released six-target transform and insertion primitives into one
deterministic immutable planning value.  It reuses CP11-CP13 placement, CP08
final-state reference resolution, and CP09 dependency evidence.  This layer
does not translate public DTO payloads, perform CP15 whole-plan preflight,
materialize a PMX document, or perform filesystem I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mmd_registry.pmx.collection_transform import (
    PmxCollectionTransform,
    PmxStructuralTransformIntent,
)
from mmd_registry.pmx.document import VALID_PMX_INDEX_SIZES
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.pmx.structural_transaction_dependency import (
    PmxStructuralTransactionDependencyEvidence,
    build_structural_transaction_dependency_evidence,
)
from mmd_registry.pmx.structural_transaction_insertion import (
    PmxStructuralTransactionInsertionBinding,
    PmxStructuralTransactionInsertionOperation,
)
from mmd_registry.pmx.structural_transaction_placement import (
    PmxStructuralTransactionCollectionPlacement,
    plan_structural_transaction_collection_placement,
)
from mmd_registry.pmx.structural_transaction_reference import (
    PmxStructuralTransactionIdentityBinding,
    PmxStructuralTransactionReferenceResolver,
)


_TARGET_KIND_ORDER = tuple(PmxReferenceTargetKind)
_TARGET_KIND_RANK = {
    target_kind: rank for rank, target_kind in enumerate(_TARGET_KIND_ORDER)
}


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


@dataclass(frozen=True, slots=True)
class PmxStructuralTransactionComposition:
    """One immutable deterministic composition across PMX target kinds."""

    source_counts: tuple[tuple[PmxReferenceTargetKind, int], ...]
    index_widths: tuple[tuple[PmxReferenceTargetKind, int], ...]
    transforms: tuple[PmxCollectionTransform, ...] = ()
    operations: tuple[PmxStructuralTransactionInsertionOperation, ...] = ()
    dependency: PmxStructuralTransactionDependencyEvidence = field(init=False)
    placements: tuple[PmxStructuralTransactionCollectionPlacement, ...] = field(
        init=False
    )
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

        placements: list[PmxStructuralTransactionCollectionPlacement] = []
        for target_kind in _TARGET_KIND_ORDER:
            transform = transform_intent.transform_for(target_kind)
            target_operations = tuple(
                operation
                for operation in self.operations
                if operation.target_kind is target_kind
            )
            if transform is None and not target_operations:
                continue
            if transform is None:
                transform = PmxCollectionTransform.identity(
                    target_kind,
                    self._environment_value(self.source_counts, target_kind),
                )
            placements.append(
                plan_structural_transaction_collection_placement(
                    transform,
                    index_width=self._environment_value(
                        self.index_widths,
                        target_kind,
                    ),
                    operations=target_operations,
                )
            )

        changed_targets = tuple(
            placement.target_kind
            for placement in placements
            if placement.operations or not placement.transform.is_noop
        )
        dependency = build_structural_transaction_dependency_evidence(
            changed_targets
        )

        bindings_by_ordinal = {
            binding.request_ordinal: binding
            for placement in placements
            for binding in placement.bindings
        }
        bindings = tuple(
            bindings_by_ordinal[operation.request_ordinal]
            for operation in self.operations
        )
        identities = tuple(
            sorted(
                (
                    identity
                    for placement in placements
                    for identity in placement.identities
                ),
                key=lambda identity: (
                    _TARGET_KIND_RANK[identity.target_kind],
                    identity.final_index,
                    identity.new_id,
                ),
            )
        )
        reference_resolver = PmxStructuralTransactionReferenceResolver(
            source_counts=self.source_counts,
            target_remaps=tuple(
                placement.target_remap
                for placement in placements
                if placement.target_kind in changed_targets
            ),
            identities=identities,
        )

        object.__setattr__(self, "dependency", dependency)
        object.__setattr__(self, "placements", tuple(placements))
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
        """Return semantically changed target kinds in canonical order."""

        return self.dependency.nodes

    @property
    def total_insert_count(self) -> int:
        """Return the number of normalized insertion operations."""

        return len(self.operations)

    def placement_for(
        self,
        target_kind: PmxReferenceTargetKind,
    ) -> PmxStructuralTransactionCollectionPlacement | None:
        """Return one target placement, or ``None`` when it is uninvolved."""

        if not isinstance(target_kind, PmxReferenceTargetKind):
            raise TypeError("target_kind must be a PmxReferenceTargetKind value.")
        for placement in self.placements:
            if placement.target_kind is target_kind:
                return placement
        return None

    def binding_for_operation(
        self,
        request_ordinal: int,
    ) -> PmxStructuralTransactionInsertionBinding:
        """Return one global request-ordinal insertion binding."""

        ordinal = _require_nonnegative_plain_int(
            request_ordinal,
            "request_ordinal",
        )
        for binding in self.bindings:
            if binding.request_ordinal == ordinal:
                return binding
        raise ValueError(
            f"request_ordinal {ordinal} is not an insertion in this composition."
        )


def compose_structural_transaction(
    *,
    source_counts: tuple[tuple[PmxReferenceTargetKind, int], ...],
    index_widths: tuple[tuple[PmxReferenceTargetKind, int], ...],
    transforms: tuple[PmxCollectionTransform, ...] = (),
    operations: tuple[PmxStructuralTransactionInsertionOperation, ...] = (),
) -> PmxStructuralTransactionComposition:
    """Compose supported target primitives without materializing payloads."""

    return PmxStructuralTransactionComposition(
        source_counts=source_counts,
        index_widths=index_widths,
        transforms=transforms,
        operations=operations,
    )


__all__ = (
    "PmxStructuralTransactionComposition",
    "compose_structural_transaction",
)
