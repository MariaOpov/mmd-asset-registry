"""Rich read-only diff projection from certified structural preview evidence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.services.structural_transaction_plan_preview import (
    PmxStructuralTransactionPlanPreviewResult,
)


class PmxStructuralAuthoringDiffServiceOperation(StrEnum):
    """Stable rich-diff service operations."""

    BUILD_DIFF = "build_structural_authoring_diff"


class PmxStructuralAuthoringDiffServiceDiagnosticCode(StrEnum):
    """Stable disclosure-safe rich-diff failure categories."""

    INVALID_ARGUMENT = "invalid_argument"
    EVIDENCE_INVALID = "certified_preview_evidence_invalid"
    INTERNAL_ERROR = "structural_authoring_diff_internal_error"


@dataclass(frozen=True, slots=True)
class PmxStructuralAuthoringDiffServiceDiagnostic:
    """One bounded rich-diff diagnostic without source or authored values."""

    code: PmxStructuralAuthoringDiffServiceDiagnosticCode
    operation: PmxStructuralAuthoringDiffServiceOperation
    message: str

    def __post_init__(self) -> None:
        if not isinstance(
            self.code,
            PmxStructuralAuthoringDiffServiceDiagnosticCode,
        ):
            raise TypeError("invalid structural authoring diff diagnostic code.")
        if not isinstance(
            self.operation,
            PmxStructuralAuthoringDiffServiceOperation,
        ):
            raise TypeError("invalid structural authoring diff operation.")
        if type(self.message) is not str or not self.message:
            raise ValueError("structural authoring diff message must be non-empty.")

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code.value,
            "operation": self.operation.value,
            "message": self.message,
        }


class PmxStructuralAuthoringDiffServiceError(RuntimeError):
    """Structured fail-closed rich-diff service failure."""

    def __init__(
        self,
        diagnostic: PmxStructuralAuthoringDiffServiceDiagnostic,
    ) -> None:
        if not isinstance(
            diagnostic,
            PmxStructuralAuthoringDiffServiceDiagnostic,
        ):
            raise TypeError("diagnostic must be a structural authoring diff diagnostic.")
        self.diagnostic = diagnostic
        super().__init__(diagnostic.message)

    def to_dict(self) -> dict[str, object]:
        return self.diagnostic.to_dict()


@dataclass(frozen=True, slots=True)
class PmxStructuralAuthoringDiffInsertion:
    """One certified insertion placement projected from preview evidence."""

    request_ordinal: int
    final_index: int

    def __post_init__(self) -> None:
        for field_name in ("request_ordinal", "final_index"):
            value = getattr(self, field_name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{field_name} must be a nonnegative integer.")

    def to_dict(self) -> dict[str, object]:
        return {
            "request_ordinal": self.request_ordinal,
            "final_index": self.final_index,
        }


@dataclass(frozen=True, slots=True)
class PmxStructuralAuthoringDiffCollection:
    """One target-kind diff derived only from certified preview evidence."""

    target_kind: PmxReferenceTargetKind
    captured_count: int
    final_count: int
    changed: bool
    explicit_transform: bool
    deleted_old_indices: tuple[int, ...]
    reordered: bool
    insertions: tuple[PmxStructuralAuthoringDiffInsertion, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.target_kind, PmxReferenceTargetKind):
            raise TypeError("target_kind must be PmxReferenceTargetKind.")
        for field_name in ("captured_count", "final_count"):
            value = getattr(self, field_name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{field_name} must be a nonnegative integer.")
        for field_name in ("changed", "explicit_transform", "reordered"):
            if type(getattr(self, field_name)) is not bool:
                raise TypeError(f"{field_name} must be a boolean.")
        if type(self.deleted_old_indices) is not tuple:
            raise TypeError("deleted_old_indices must be a tuple.")
        previous = -1
        for source_index in self.deleted_old_indices:
            if type(source_index) is not int or source_index < 0:
                raise ValueError("deleted source indices must be nonnegative integers.")
            if source_index <= previous:
                raise ValueError(
                    "deleted source indices must be strictly increasing."
                )
            previous = source_index
        if type(self.insertions) is not tuple or not all(
            isinstance(item, PmxStructuralAuthoringDiffInsertion)
            for item in self.insertions
        ):
            raise TypeError(
                "insertions must contain only PmxStructuralAuthoringDiffInsertion."
            )

    @property
    def count_delta(self) -> int:
        return self.final_count - self.captured_count

    @property
    def inserted_count(self) -> int:
        return len(self.insertions)

    @property
    def deleted_count(self) -> int:
        return len(self.deleted_old_indices)

    def to_dict(self) -> dict[str, object]:
        return {
            "target_kind": self.target_kind.value,
            "captured_count": self.captured_count,
            "final_count": self.final_count,
            "count_delta": self.count_delta,
            "changed": self.changed,
            "explicit_transform": self.explicit_transform,
            "deleted_old_indices": list(self.deleted_old_indices),
            "reordered": self.reordered,
            "insertions": [item.to_dict() for item in self.insertions],
        }


@dataclass(frozen=True, slots=True)
class PmxStructuralAuthoringDiff:
    """Deterministic human-facing projection of one certified preview."""

    status: str
    expected_source_sha256_declared: bool
    source_identity_status: str
    plan_sha256: str
    changed_targets: tuple[PmxReferenceTargetKind, ...]
    collections: tuple[PmxStructuralAuthoringDiffCollection, ...]
    inserted_count: int
    deleted_count: int
    reordered_target_count: int
    resolved_local_reference_count: int
    remapped_existing_reference_count: int
    dependency_materialization_order: tuple[PmxReferenceTargetKind, ...]
    capacity_all_representable: bool

    def __post_init__(self) -> None:
        if self.status not in ("no_changes", "changes_pending"):
            raise ValueError("status must be no_changes or changes_pending.")
        if type(self.expected_source_sha256_declared) is not bool:
            raise TypeError("expected_source_sha256_declared must be a boolean.")
        if self.source_identity_status not in ("matched", "not_declared"):
            raise ValueError(
                "source_identity_status must be matched or not_declared."
            )
        if type(self.plan_sha256) is not str or len(self.plan_sha256) != 64:
            raise ValueError("plan_sha256 must be a 64-character string.")
        if type(self.changed_targets) is not tuple or not all(
            isinstance(item, PmxReferenceTargetKind)
            for item in self.changed_targets
        ):
            raise TypeError("changed_targets must be target-kind values.")
        if type(self.collections) is not tuple or not all(
            isinstance(item, PmxStructuralAuthoringDiffCollection)
            for item in self.collections
        ):
            raise TypeError(
                "collections must contain structural authoring diff collections."
            )
        if tuple(item.target_kind for item in self.collections) != tuple(
            PmxReferenceTargetKind
        ):
            raise ValueError(
                "collections must cover every target kind in canonical order."
            )
        for field_name in (
            "inserted_count",
            "deleted_count",
            "reordered_target_count",
            "resolved_local_reference_count",
            "remapped_existing_reference_count",
        ):
            value = getattr(self, field_name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{field_name} must be a nonnegative integer.")
        if type(self.dependency_materialization_order) is not tuple or not all(
            isinstance(item, PmxReferenceTargetKind)
            for item in self.dependency_materialization_order
        ):
            raise TypeError(
                "dependency_materialization_order must contain target kinds."
            )
        if type(self.capacity_all_representable) is not bool:
            raise TypeError("capacity_all_representable must be a boolean.")

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "source_identity": {
                "expected_source_sha256_declared": (
                    self.expected_source_sha256_declared
                ),
                "status": self.source_identity_status,
            },
            "plan_sha256": self.plan_sha256,
            "changed_targets": [item.value for item in self.changed_targets],
            "collections": [item.to_dict() for item in self.collections],
            "totals": {
                "inserted": self.inserted_count,
                "deleted": self.deleted_count,
                "reordered_targets": self.reordered_target_count,
                "resolved_local_references": self.resolved_local_reference_count,
                "remapped_existing_references": (
                    self.remapped_existing_reference_count
                ),
            },
            "dependency_materialization_order": [
                item.value for item in self.dependency_materialization_order
            ],
            "capacity_all_representable": self.capacity_all_representable,
        }


def _diagnostic(
    code: PmxStructuralAuthoringDiffServiceDiagnosticCode,
    message: str,
) -> PmxStructuralAuthoringDiffServiceDiagnostic:
    return PmxStructuralAuthoringDiffServiceDiagnostic(
        code=code,
        operation=PmxStructuralAuthoringDiffServiceOperation.BUILD_DIFF,
        message=message,
    )


def _require_dict(value: object) -> dict[str, object]:
    if type(value) is not dict:
        raise ValueError("certified preview evidence object is invalid.")
    return value


def _require_list(value: object) -> list[object]:
    if type(value) is not list:
        raise ValueError("certified preview evidence array is invalid.")
    return value


def _require_nonnegative_int(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("certified preview evidence integer is invalid.")
    return value


def _require_bool(value: object) -> bool:
    if type(value) is not bool:
        raise ValueError("certified preview evidence boolean is invalid.")
    return value


def _parse_kind_list(value: object) -> tuple[PmxReferenceTargetKind, ...]:
    items = _require_list(value)
    kinds = tuple(PmxReferenceTargetKind(item) for item in items)
    if len(set(kinds)) != len(kinds):
        raise ValueError("certified preview target-kind list has duplicates.")
    return kinds


def _parse_effects(
    value: object,
) -> dict[PmxReferenceTargetKind, dict[str, object]]:
    effects: dict[PmxReferenceTargetKind, dict[str, object]] = {}
    for item in _require_list(value):
        payload = _require_dict(item)
        target_kind = PmxReferenceTargetKind(payload["target_kind"])
        if target_kind in effects:
            raise ValueError("certified preview collection effect is duplicated.")
        effects[target_kind] = payload
    return effects


def _parse_insertions(
    value: object,
) -> tuple[PmxStructuralAuthoringDiffInsertion, ...]:
    result: list[PmxStructuralAuthoringDiffInsertion] = []
    for item in _require_list(value):
        payload = _require_dict(item)
        result.append(
            PmxStructuralAuthoringDiffInsertion(
                request_ordinal=_require_nonnegative_int(
                    payload["request_ordinal"]
                ),
                final_index=_require_nonnegative_int(payload["final_index"]),
            )
        )
    return tuple(result)


def _parse_deleted_indices(value: object) -> tuple[int, ...]:
    result = tuple(_require_nonnegative_int(item) for item in _require_list(value))
    if tuple(sorted(set(result))) != result:
        raise ValueError(
            "certified preview deleted indices must be unique source order."
        )
    return result


def build_structural_authoring_diff(
    preview: PmxStructuralTransactionPlanPreviewResult,
) -> PmxStructuralAuthoringDiff:
    """Project one certified preview into deterministic rich diff evidence."""

    try:
        if not isinstance(
            preview,
            PmxStructuralTransactionPlanPreviewResult,
        ):
            raise TypeError(
                "preview must be PmxStructuralTransactionPlanPreviewResult."
            )

        payload = _require_dict(preview.to_dict())
        effects = _require_dict(payload["effects"])
        counts = _require_dict(payload["counts"])
        captured = _require_dict(counts["captured"])
        final = _require_dict(counts["final"])
        references = _require_dict(payload["references"])
        dependencies = _require_dict(payload["dependencies"])
        capacity = _require_dict(payload["capacity"])

        changed_targets = _parse_kind_list(effects["changed_targets"])
        effect_by_kind = _parse_effects(effects["collections"])

        collections: list[PmxStructuralAuthoringDiffCollection] = []
        changed_set = set(changed_targets)
        for target_kind in PmxReferenceTargetKind:
            kind = target_kind.value
            source_count = _require_nonnegative_int(captured[kind])
            final_count = _require_nonnegative_int(final[kind])
            effect = effect_by_kind.get(target_kind)
            if effect is None:
                collection = PmxStructuralAuthoringDiffCollection(
                    target_kind=target_kind,
                    captured_count=source_count,
                    final_count=final_count,
                    changed=target_kind in changed_set,
                    explicit_transform=False,
                    deleted_old_indices=(),
                    reordered=False,
                    insertions=(),
                )
            else:
                collection = PmxStructuralAuthoringDiffCollection(
                    target_kind=target_kind,
                    captured_count=source_count,
                    final_count=final_count,
                    changed=target_kind in changed_set,
                    explicit_transform=_require_bool(
                        effect["explicit_transform"]
                    ),
                    deleted_old_indices=_parse_deleted_indices(
                        effect["deleted_old_indices"]
                    ),
                    reordered=_require_bool(effect["reordered"]),
                    insertions=_parse_insertions(effect["insertions"]),
                )
            collections.append(collection)

        inserted_count = _require_nonnegative_int(effects["inserted_count"])
        deleted_count = _require_nonnegative_int(effects["deleted_count"])
        reordered_target_count = _require_nonnegative_int(
            effects["reordered_target_count"]
        )
        if sum(item.inserted_count for item in collections) != inserted_count:
            raise ValueError("certified preview insertion totals disagree.")
        if sum(item.deleted_count for item in collections) != deleted_count:
            raise ValueError("certified preview deletion totals disagree.")
        if sum(item.reordered for item in collections) != reordered_target_count:
            raise ValueError("certified preview reorder totals disagree.")

        resolved_local = _require_list(references["resolved_local"])
        remapped_existing = _require_list(references["remapped_existing"])
        materialization_order = _parse_kind_list(
            dependencies["materialization_order"]
        )

        return PmxStructuralAuthoringDiff(
            status=preview.status,
            expected_source_sha256_declared=(
                preview.expected_source_sha256_declared
            ),
            source_identity_status=preview.source_identity_status,
            plan_sha256=preview.plan_sha256,
            changed_targets=changed_targets,
            collections=tuple(collections),
            inserted_count=inserted_count,
            deleted_count=deleted_count,
            reordered_target_count=reordered_target_count,
            resolved_local_reference_count=len(resolved_local),
            remapped_existing_reference_count=len(remapped_existing),
            dependency_materialization_order=materialization_order,
            capacity_all_representable=_require_bool(
                capacity["all_representable"]
            ),
        )
    except PmxStructuralAuthoringDiffServiceError:
        raise
    except TypeError:
        failure = PmxStructuralAuthoringDiffServiceError(
            _diagnostic(
                PmxStructuralAuthoringDiffServiceDiagnosticCode.INVALID_ARGUMENT,
                "Invalid structural authoring diff input.",
            )
        )
    except (KeyError, ValueError):
        failure = PmxStructuralAuthoringDiffServiceError(
            _diagnostic(
                PmxStructuralAuthoringDiffServiceDiagnosticCode.EVIDENCE_INVALID,
                "Certified structural preview evidence is invalid.",
            )
        )
    except Exception:
        failure = PmxStructuralAuthoringDiffServiceError(
            _diagnostic(
                PmxStructuralAuthoringDiffServiceDiagnosticCode.INTERNAL_ERROR,
                "Unexpected structural authoring diff failure.",
            )
        )
    raise failure from None


__all__ = (
    "PmxStructuralAuthoringDiffServiceOperation",
    "PmxStructuralAuthoringDiffServiceDiagnosticCode",
    "PmxStructuralAuthoringDiffServiceDiagnostic",
    "PmxStructuralAuthoringDiffServiceError",
    "PmxStructuralAuthoringDiffInsertion",
    "PmxStructuralAuthoringDiffCollection",
    "PmxStructuralAuthoringDiff",
    "build_structural_authoring_diff",
)
