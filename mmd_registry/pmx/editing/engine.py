"""Pure in-memory transformations for declarative PMX editing."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Final

from mmd_registry.pmx.document import PmxDocument
from mmd_registry.pmx.editing.audit import PmxEditAudit, PmxEditChange
from mmd_registry.pmx.editing.errors import PmxEditPlanError
from mmd_registry.pmx.editing.operations import (
    SetModelInfo,
    SetTexturePath,
    UpdateMaterial,
)
from mmd_registry.pmx.editing.numeric import canonicalize_pmx_float32
from mmd_registry.pmx.editing.path_policy import validate_portable_texture_path
from mmd_registry.pmx.editing.plan import PmxEditPlan
from mmd_registry.pmx.editing.validation import validate_pmx_edit_plan
from mmd_registry.pmx.errors import PmxValidationError
from mmd_registry.pmx.validation import validate_pmx_document


_MATERIAL_EDITABLE_FIELDS = (
    "local_name",
    "universal_name",
    "memo",
    "texture_index",
    "sphere_texture_index",
    "sphere_mode",
    "toon_reference_mode",
    "toon_reference_index",
    "diffuse",
    "specular",
    "specular_strength",
    "ambient",
    "drawing_flags",
    "edge_color",
    "edge_scale",
)

_MATERIAL_FLOAT_VECTOR_FIELDS = (
    "diffuse",
    "specular",
    "ambient",
    "edge_color",
)
_MATERIAL_FLOAT_FIELDS = ("specular_strength", "edge_scale")
_LOWERCASE_SHA256: Final[re.Pattern[str]] = re.compile(r"[0-9a-f]{64}\Z")


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


def _validate_source_sha256(
    plan: PmxEditPlan,
    source_sha256: str | None,
) -> None:
    """Validate an optional actual source digest against the plan contract."""

    if source_sha256 is not None:
        if not isinstance(source_sha256, str):
            raise TypeError("source_sha256 must be a string when provided.")
        if _LOWERCASE_SHA256.fullmatch(source_sha256) is None:
            raise ValueError(
                "source_sha256 must be exactly 64 lowercase hexadecimal "
                "characters."
            )

    expected = plan.expected_source_sha256
    if expected is None:
        return
    if source_sha256 is None:
        raise PmxEditPlanError(
            "actual source SHA-256 is required by this plan.",
            field="expected_source_sha256",
        )
    if source_sha256 != expected:
        raise PmxEditPlanError(
            (
                f"source SHA-256 mismatch; expected {expected}, "
                f"received {source_sha256}."
            ),
            field="expected_source_sha256",
        )


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


def _canonicalize_material_float_updates(
    updates: dict[str, object],
    *,
    operation_index: int,
) -> dict[str, object]:
    """Canonicalize targeted material floats to their stored PMX values."""

    canonical = dict(updates)
    for field_name in _MATERIAL_EDITABLE_FIELDS:
        value = canonical.get(field_name)
        if value is None:
            continue

        if field_name in _MATERIAL_FLOAT_VECTOR_FIELDS:
            components: list[float] = []
            for component_index, component in enumerate(value):
                try:
                    components.append(canonicalize_pmx_float32(component))
                except ValueError as error:
                    raise PmxEditPlanError(
                        str(error),
                        operation_index=operation_index,
                        field=f"{field_name}[{component_index}]",
                    ) from error
            canonical[field_name] = tuple(components)
            continue

        if field_name not in _MATERIAL_FLOAT_FIELDS:
            continue

        try:
            canonical[field_name] = canonicalize_pmx_float32(value)
        except ValueError as error:
            raise PmxEditPlanError(
                str(error),
                operation_index=operation_index,
                field=field_name,
            ) from error

    return canonical


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


def apply_update_material(
    document: PmxDocument,
    operation: UpdateMaterial,
    *,
    operation_index: int = 0,
) -> PmxEditResult:
    """Purely update supported fields of one material."""

    if not isinstance(document, PmxDocument):
        raise TypeError("document must be a PmxDocument instance.")
    if not isinstance(operation, UpdateMaterial):
        raise TypeError("operation must be an UpdateMaterial instance.")
    _validate_operation_index(operation_index)

    if operation.material_index >= len(document.materials):
        raise PmxEditPlanError(
            (
                f"material index {operation.material_index} is out of range; "
                f"document contains {len(document.materials)} materials."
            ),
            operation_index=operation_index,
            field="material_index",
        )

    material = document.materials[operation.material_index]
    requested_updates = {
        field_name: getattr(operation, field_name)
        for field_name in _MATERIAL_EDITABLE_FIELDS
        if getattr(operation, field_name) is not None
    }
    requested_updates = _canonicalize_material_float_updates(
        requested_updates,
        operation_index=operation_index,
    )
    effective_updates = {
        field_name: value
        for field_name, value in requested_updates.items()
        if getattr(material, field_name) != value
    }

    final_toon_mode = requested_updates.get(
        "toon_reference_mode",
        material.toon_reference_mode,
    )
    final_toon_index = requested_updates.get(
        "toon_reference_index",
        material.toon_reference_index,
    )
    if final_toon_mode == "shared" and not 0 <= final_toon_index <= 9:
        field_name = (
            "toon_reference_index"
            if "toon_reference_index" in requested_updates
            else "toon_reference_mode"
        )
        raise PmxEditPlanError(
            "shared toon reference index must be a value from 0 through 9.",
            operation_index=operation_index,
            field=field_name,
        )

    changes = tuple(
        PmxEditChange(
            category="material",
            target_index=operation.material_index,
            target_name=material.local_name,
            field_path=f"materials[{operation.material_index}].{field_name}",
            before=getattr(material, field_name),
            after=effective_updates[field_name],
            operation_index=operation_index,
        )
        for field_name in _MATERIAL_EDITABLE_FIELDS
        if field_name in effective_updates
    )

    edited_document = document
    if effective_updates:
        updated_material = replace(material, **effective_updates)
        materials = (
            *document.materials[: operation.material_index],
            updated_material,
            *document.materials[operation.material_index + 1 :],
        )
        edited_document = replace(document, materials=materials)

    target_fields = {
        ("materials", operation.material_index, field_name): field_name
        for field_name in effective_updates
    }
    if (
        "toon_reference_mode" in effective_updates
        and "toon_reference_index" not in effective_updates
    ):
        target_fields[
            ("materials", operation.material_index, "toon_reference_index")
        ] = "toon_reference_mode"

    _validate_edited_document(
        edited_document,
        operation_index=operation_index,
        target_fields=target_fields,
    )

    return PmxEditResult(
        document=edited_document,
        audit=PmxEditAudit(changes=changes),
    )


def apply_pmx_edit_plan(
    document: PmxDocument,
    plan: PmxEditPlan,
    *,
    source_sha256: str | None = None,
) -> PmxEditResult:
    """Atomically apply a validated plan to an immutable PMX document."""

    if not isinstance(document, PmxDocument):
        raise TypeError("document must be a PmxDocument instance.")
    if not isinstance(plan, PmxEditPlan):
        raise TypeError("plan must be a PmxEditPlan instance.")

    validate_pmx_document(document)
    validate_pmx_edit_plan(plan)
    _validate_source_sha256(plan, source_sha256)

    edited_document = document
    changes: list[PmxEditChange] = []
    for operation_index, operation in enumerate(plan.operations):
        if isinstance(operation, SetModelInfo):
            operation_result = apply_set_model_info(
                edited_document,
                operation,
                operation_index=operation_index,
            )
        elif isinstance(operation, SetTexturePath):
            operation_result = apply_set_texture_path(
                edited_document,
                operation,
                operation_index=operation_index,
            )
        elif isinstance(operation, UpdateMaterial):
            operation_result = apply_update_material(
                edited_document,
                operation,
                operation_index=operation_index,
            )
        else:
            raise TypeError("plan contains an unsupported operation type.")

        edited_document = operation_result.document
        changes.extend(operation_result.audit.changes)

    validate_pmx_document(edited_document)
    return PmxEditResult(
        document=edited_document,
        audit=PmxEditAudit(changes=tuple(changes)),
    )
