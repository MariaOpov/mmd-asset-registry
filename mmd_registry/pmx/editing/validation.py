"""Cross-operation validation for declarative PMX edit plans."""

from __future__ import annotations

from mmd_registry.pmx.editing.errors import PmxEditPlanError
from mmd_registry.pmx.editing.operations import operation_targets
from mmd_registry.pmx.editing.plan import PmxEditPlan


def validate_pmx_edit_plan(plan: PmxEditPlan) -> None:
    """Reject conflicting writes before any document transformation."""

    if not isinstance(plan, PmxEditPlan):
        raise TypeError("plan must be a PmxEditPlan instance.")

    first_writes: dict[str, tuple[int, str]] = {}
    for operation_index, operation in enumerate(plan.operations):
        for target in operation_targets(operation):
            first_write = first_writes.get(target.field_path)
            if first_write is not None:
                first_index, first_field = first_write
                raise PmxEditPlanError(
                    (
                        f"duplicate write to {target.field_path}; first written "
                        f"by operations[{first_index}].{first_field}."
                    ),
                    operation_index=operation_index,
                    field=target.payload_field,
                )

            first_writes[target.field_path] = (
                operation_index,
                target.payload_field,
            )
