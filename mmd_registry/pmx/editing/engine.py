"""Pure in-memory transformations for declarative PMX editing."""

from __future__ import annotations

from dataclasses import dataclass, replace

from mmd_registry.pmx.document import PmxDocument
from mmd_registry.pmx.editing.audit import PmxEditAudit, PmxEditChange
from mmd_registry.pmx.editing.errors import PmxEditPlanError
from mmd_registry.pmx.editing.operations import SetModelInfo, SetTexturePath
from mmd_registry.pmx.editing.path_policy import validate_portable_texture_path
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


def _validate_operation_index(operation_index: object) -> None:
    """Require one explicit nonnegative plan-operation index."""

    if not _is_plain_int(operation_index):
        raise TypeError("operation_index must be an integer.")
    if operation_index < 0:
        raise ValueError("operation_index cannot be negative.")


def _validate_edited_document(
    document: PmxDocument,
    *,
    operation_index: int,
    target_fields: dict[tuple[str, int | None, str], str],
) -> None:
    """Validate a candidate and add operation context to targeted failures."""

    try:
        validate_pmx_document(document)
    except PmxValidationError as error:
        payload_field = target_fields.get(
            (error.section, error.record_index, error.field)
        )
        if payload_field is not None:
            raise PmxEditPlanError(
                error.reason,
                operation_index=operation_index,
                field=payload_field,
            ) from error
        raise


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
    _validate_operation_index(operation_index)

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

    _validate_edited_document(
        edited_document,
        operation_index=operation_index,
        target_fields={
            ("model_info", None, field_name): field_name
            for field_name in updates
        },
    )

    return PmxEditResult(
        document=edited_document,
        audit=PmxEditAudit(changes=tuple(changes)),
    )


def apply_set_texture_path(
    document: PmxDocument,
    operation: SetTexturePath,
    *,
    operation_index: int = 0,
) -> PmxEditResult:
    """Purely replace one indexed texture path and validate the result."""

    if not isinstance(document, PmxDocument):
        raise TypeError("document must be a PmxDocument instance.")
    if not isinstance(operation, SetTexturePath):
        raise TypeError("operation must be a SetTexturePath instance.")
    _validate_operation_index(operation_index)

    if operation.texture_index >= len(document.texture_paths):
        raise PmxEditPlanError(
            (
                f"texture index {operation.texture_index} is out of range; "
                f"document contains {len(document.texture_paths)} textures."
            ),
            operation_index=operation_index,
            field="texture_index",
        )

    try:
        validate_portable_texture_path(operation.path)
    except (TypeError, ValueError) as error:
        raise PmxEditPlanError(
            str(error),
            operation_index=operation_index,
            field="path",
        ) from error

    before = document.texture_paths[operation.texture_index]
    if before == operation.path:
        edited_document = document
        changes: tuple[PmxEditChange, ...] = ()
    else:
        texture_paths = (
            *document.texture_paths[: operation.texture_index],
            operation.path,
            *document.texture_paths[operation.texture_index + 1 :],
        )
        edited_document = replace(document, texture_paths=texture_paths)
        changes = (
            PmxEditChange(
                category="texture",
                target_index=operation.texture_index,
                target_name=before,
                field_path=f"textures[{operation.texture_index}].path",
                before=before,
                after=operation.path,
                operation_index=operation_index,
            ),
        )

    _validate_edited_document(
        edited_document,
        operation_index=operation_index,
        target_fields={
            ("textures", operation.texture_index, "path"): "path",
        },
    )

    return PmxEditResult(
        document=edited_document,
        audit=PmxEditAudit(changes=changes),
    )
