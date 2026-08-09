"""Pure in-memory transformations for declarative PMX editing."""

from __future__ import annotations

from dataclasses import dataclass, replace

from mmd_registry.pmx.document import PmxDocument
from mmd_registry.pmx.editing.audit import PmxEditAudit, PmxEditChange
from mmd_registry.pmx.editing.errors import PmxEditPlanError
from mmd_registry.pmx.editing.operations import SetModelInfo
from mmd_registry.pmx.errors import PmxValidationError
from mmd_registry.pmx.validation import validate_pmx_document


def _is_plain_int(value: object) -> bool:
    """Return whether a value is an integer but not a boolean."""

    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True, slots=True)
class PmxEditResult:
    """One immutable edited document and its effective-change audit."""

    document: PmxDocument
    audit: PmxEditAudit

    def __post_init__(self) -> None:
        if not isinstance(self.document, PmxDocument):
            raise TypeError("document must be a PmxDocument instance.")
        if not isinstance(self.audit, PmxEditAudit):
            raise TypeError("audit must be a PmxEditAudit instance.")


def apply_set_model_info(
    document: PmxDocument,
    operation: SetModelInfo,
    *,
    operation_index: int = 0,
) -> PmxEditResult:
    """Purely apply one model-information operation and validate the result."""

    if not isinstance(document, PmxDocument):
        raise TypeError("document must be a PmxDocument instance.")
    if not isinstance(operation, SetModelInfo):
        raise TypeError("operation must be a SetModelInfo instance.")
    if not _is_plain_int(operation_index):
        raise TypeError("operation_index must be an integer.")
    if operation_index < 0:
        raise ValueError("operation_index cannot be negative.")

    updates: dict[str, str] = {}
    changes: list[PmxEditChange] = []
    for target in operation.targets():
        before = getattr(document.model_info, target.payload_field)
        after = getattr(operation, target.payload_field)
        if not isinstance(after, str):
            raise TypeError(
                f"{target.payload_field} must be a string when targeted."
            )

        if before == after:
            continue

        updates[target.payload_field] = after
        changes.append(
            PmxEditChange(
                category="model",
                target_index=None,
                target_name=document.model_info.local_name,
                field_path=target.field_path,
                before=before,
                after=after,
                operation_index=operation_index,
            )
        )

    edited_document = document
    if updates:
        edited_document = replace(
            document,
            model_info=replace(document.model_info, **updates),
        )

    try:
        validate_pmx_document(edited_document)
    except PmxValidationError as error:
        if error.section == "model_info" and error.field in updates:
            raise PmxEditPlanError(
                error.reason,
                operation_index=operation_index,
                field=error.field,
            ) from error
        raise

    return PmxEditResult(
        document=edited_document,
        audit=PmxEditAudit(changes=tuple(changes)),
    )
