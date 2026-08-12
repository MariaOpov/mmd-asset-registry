"""Pure deterministic explanations for validated PMX edit plans."""

from __future__ import annotations

import json
from dataclasses import dataclass

from mmd_registry.pmx.editing.catalog import (
    PmxEditOperationCatalogEntry,
    get_pmx_edit_operation_catalog,
)
from mmd_registry.pmx.editing.operations import (
    PmxEditFieldRole,
    PmxEditOperation,
    operation_to_dict,
)
from mmd_registry.pmx.editing.plan import PmxEditPlan
from mmd_registry.pmx.editing.validation import validate_pmx_edit_plan


@dataclass(frozen=True, slots=True)
class PmxEditOperationExplanation:
    """One operation's authoring intent without executing the edit."""

    index: int
    operation_type: str
    target: str
    fields: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.index) is not int or self.index < 0:
            raise ValueError("index must be a nonnegative integer.")
        if type(self.operation_type) is not str or not self.operation_type:
            raise ValueError("operation_type must be a non-empty string.")
        if type(self.target) is not str or not self.target:
            raise ValueError("target must be a non-empty string.")
        if type(self.fields) is not tuple or not self.fields:
            raise ValueError("fields must be a non-empty tuple.")
        if any(type(field) is not str or not field for field in self.fields):
            raise ValueError("fields must contain non-empty strings.")
        if len(set(self.fields)) != len(self.fields):
            raise ValueError("fields must be unique.")

    def to_dict(self) -> dict[str, object]:
        """Return one deterministic JSON-ready operation explanation."""

        return {
            "index": self.index,
            "type": self.operation_type,
            "target": self.target,
            "fields": list(self.fields),
        }


@dataclass(frozen=True, slots=True)
class PmxEditPlanExplanation:
    """Immutable explanation of one validated plan's declared intent."""

    schema_version: int
    expected_source_sha256: bool
    operations: tuple[PmxEditOperationExplanation, ...]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version < 1:
            raise ValueError("schema_version must be a positive integer.")
        if type(self.expected_source_sha256) is not bool:
            raise TypeError("expected_source_sha256 must be a boolean.")
        if type(self.operations) is not tuple or not self.operations:
            raise ValueError("operations must be a non-empty tuple.")
        if not all(
            isinstance(operation, PmxEditOperationExplanation)
            for operation in self.operations
        ):
            raise TypeError(
                "operations must contain only PmxEditOperationExplanation values."
            )
        if tuple(operation.index for operation in self.operations) != tuple(
            range(len(self.operations))
        ):
            raise ValueError(
                "operation explanation indexes must be contiguous from zero."
            )

    @property
    def operation_count(self) -> int:
        """Return the number of explained operations."""

        return len(self.operations)

    def to_dict(self) -> dict[str, object]:
        """Return the stable machine-readable explanation payload."""

        return {
            "status": "ok",
            "schema_version": self.schema_version,
            "expected_source_sha256": self.expected_source_sha256,
            "operation_count": self.operation_count,
            "operations": [
                operation.to_dict() for operation in self.operations
            ],
        }


def _catalog_by_operation_type() -> dict[str, PmxEditOperationCatalogEntry]:
    """Return an ephemeral lookup derived from the authoritative catalog."""

    catalog = get_pmx_edit_operation_catalog()
    return {
        entry.operation_type: entry
        for entry in catalog.operations
    }


def _target_identity(
    operation: PmxEditOperation,
    entry: PmxEditOperationCatalogEntry,
    payload: dict[str, object],
) -> str:
    """Describe the target identity available from the plan alone."""

    del operation

    selectors = tuple(
        field
        for field in entry.fields
        if field.role is PmxEditFieldRole.SELECTOR
    )
    if not selectors:
        return entry.target_kind.value
    if len(selectors) != 1:
        raise RuntimeError(
            f"operation {entry.operation_type!r} has an unsupported "
            "multi-selector target shape."
        )

    selector = selectors[0]
    if selector.name not in payload:
        raise RuntimeError(
            f"operation {entry.operation_type!r} is missing selector "
            f"{selector.name!r} after validation."
        )
    selector_value = payload[selector.name]
    if type(selector_value) is not int:
        raise RuntimeError(
            f"operation {entry.operation_type!r} selector "
            f"{selector.name!r} is not an integer after validation."
        )
    return f"{entry.target_kind.value}[{selector_value}]"


def _intended_fields(
    entry: PmxEditOperationCatalogEntry,
    payload: dict[str, object],
) -> tuple[str, ...]:
    """Return intended value-field names in stable catalog order."""

    fields = tuple(
        field.name
        for field in entry.fields
        if field.role is PmxEditFieldRole.VALUE
        and field.name in payload
    )
    if not fields:
        raise RuntimeError(
            f"operation {entry.operation_type!r} has no intended value fields "
            "after validation."
        )
    return fields


def explain_pmx_edit_plan(plan: PmxEditPlan) -> PmxEditPlanExplanation:
    """Explain a validated typed plan without loading or modifying a PMX."""

    if not isinstance(plan, PmxEditPlan):
        raise TypeError("plan must be a PmxEditPlan instance.")

    validate_pmx_edit_plan(plan)
    catalog_by_type = _catalog_by_operation_type()

    explanations: list[PmxEditOperationExplanation] = []
    for index, operation in enumerate(plan.operations):
        payload = operation_to_dict(operation)
        operation_type = payload["op"]
        if type(operation_type) is not str:
            raise RuntimeError(
                "validated operation produced a non-string operation name."
            )

        entry = catalog_by_type.get(operation_type)
        if entry is None:
            raise RuntimeError(
                f"validated operation {operation_type!r} is missing from "
                "the authoring catalog."
            )

        explanations.append(
            PmxEditOperationExplanation(
                index=index,
                operation_type=operation_type,
                target=_target_identity(operation, entry, payload),
                fields=_intended_fields(entry, payload),
            )
        )

    return PmxEditPlanExplanation(
        schema_version=plan.schema_version,
        expected_source_sha256=plan.expected_source_sha256 is not None,
        operations=tuple(explanations),
    )


def render_pmx_edit_plan_explanation_text(
    explanation: PmxEditPlanExplanation,
) -> str:
    """Render a compact deterministic explanation followed by a newline."""

    if not isinstance(explanation, PmxEditPlanExplanation):
        raise TypeError(
            "explanation must be a PmxEditPlanExplanation instance."
        )

    lines = [
        "PMX EDIT PLAN EXPLANATION",
        f"Plan schema: {explanation.schema_version}",
        "Expected source SHA-256: "
        + ("present" if explanation.expected_source_sha256 else "absent"),
        f"Operations: {explanation.operation_count}",
        "Execution: not performed",
    ]

    for operation in explanation.operations:
        lines.extend(
            (
                "",
                f"[{operation.index}] {operation.operation_type}",
                f"    Target: {operation.target}",
                "    Fields:",
            )
        )
        lines.extend(
            f"      - {field}"
            for field in operation.fields
        )

    return "\n".join(lines) + "\n"


def render_pmx_edit_plan_explanation_json(
    explanation: PmxEditPlanExplanation,
    *,
    indent: int | None = 2,
) -> str:
    """Render deterministic Unicode-safe JSON followed by a newline."""

    if not isinstance(explanation, PmxEditPlanExplanation):
        raise TypeError(
            "explanation must be a PmxEditPlanExplanation instance."
        )
    if indent is not None:
        if type(indent) is not int:
            raise TypeError("indent must be an integer or None.")
        if indent < 0:
            raise ValueError("indent cannot be negative.")

    return (
        json.dumps(
            explanation.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            indent=indent,
        )
        + "\n"
    )
