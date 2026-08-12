"""Safe deterministic starter templates for PMX edit-plan authoring."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Final

from mmd_registry.pmx.editing.catalog import (
    PmxEditOperationCatalogEntry,
    get_pmx_edit_operation_catalog,
)
from mmd_registry.pmx.editing.operations import (
    PmxEditFieldRole,
    PmxEditFieldSpec,
)
from mmd_registry.pmx.editing.plan import PMX_EDIT_PLAN_SCHEMA_VERSION


PMX_EDIT_PLAN_TEMPLATE_FORMAT_VERSION: Final[int] = 1
PMX_EDIT_PLAN_TEMPLATE_MARKER: Final[str] = "_template"
PMX_EDIT_PLAN_TEMPLATE_PLACEHOLDER: Final[str] = "$placeholder"

_TEMPLATE_INSTRUCTIONS: Final[tuple[str, ...]] = (
    "This is an intentionally incomplete authoring template, not an executable edit plan.",
    'Replace every {"$placeholder": ...} object with a concrete JSON value.',
    'Remove the top-level "_template" member before using the document as an edit plan.',
    "Unicode JSON values are supported (for example, モデル名).",
)


@dataclass(frozen=True, slots=True)
class PmxEditPlanTemplateOperation:
    """One intentionally incomplete operation starter."""

    operation_type: str
    placeholder_fields: tuple[PmxEditFieldSpec, ...]

    def __post_init__(self) -> None:
        if type(self.operation_type) is not str or not self.operation_type:
            raise ValueError("operation_type must be a non-empty string.")
        if type(self.placeholder_fields) is not tuple or not self.placeholder_fields:
            raise ValueError("placeholder_fields must be a non-empty tuple.")
        if not all(
            isinstance(field, PmxEditFieldSpec)
            for field in self.placeholder_fields
        ):
            raise TypeError(
                "placeholder_fields must contain only PmxEditFieldSpec values."
            )
        field_names = tuple(field.name for field in self.placeholder_fields)
        if len(set(field_names)) != len(field_names):
            raise ValueError("placeholder field names must be unique.")

    @property
    def placeholder_field_names(self) -> tuple[str, ...]:
        """Return placeholder field names in stable catalog order."""

        return tuple(field.name for field in self.placeholder_fields)

    def to_dict(self) -> dict[str, object]:
        """Return one deterministic, deliberately non-executable operation."""

        payload: dict[str, object] = {"op": self.operation_type}
        for field in self.placeholder_fields:
            payload[field.name] = {
                PMX_EDIT_PLAN_TEMPLATE_PLACEHOLDER: field.to_dict(),
            }
        return payload


@dataclass(frozen=True, slots=True)
class PmxEditPlanTemplate:
    """One immutable plan-shaped authoring template."""

    supported_operation_types: tuple[str, ...]
    operation: PmxEditPlanTemplateOperation | None = None
    template_format_version: int = PMX_EDIT_PLAN_TEMPLATE_FORMAT_VERSION
    plan_schema_version: int = PMX_EDIT_PLAN_SCHEMA_VERSION
    executable: bool = False

    def __post_init__(self) -> None:
        if type(self.supported_operation_types) is not tuple:
            raise TypeError("supported_operation_types must be a tuple.")
        if not self.supported_operation_types:
            raise ValueError("supported_operation_types cannot be empty.")
        if any(
            type(operation_type) is not str or not operation_type
            for operation_type in self.supported_operation_types
        ):
            raise ValueError(
                "supported_operation_types must contain non-empty strings."
            )
        if len(set(self.supported_operation_types)) != len(
            self.supported_operation_types
        ):
            raise ValueError("supported_operation_types must be unique.")
        if self.operation is not None:
            if not isinstance(self.operation, PmxEditPlanTemplateOperation):
                raise TypeError(
                    "operation must be a PmxEditPlanTemplateOperation or None."
                )
            if self.operation.operation_type not in self.supported_operation_types:
                raise ValueError(
                    "template operation must be one of the supported operation types."
                )
        if (
            type(self.template_format_version) is not int
            or self.template_format_version
            != PMX_EDIT_PLAN_TEMPLATE_FORMAT_VERSION
        ):
            raise ValueError(
                "template_format_version must match the current template format."
            )
        if (
            type(self.plan_schema_version) is not int
            or self.plan_schema_version != PMX_EDIT_PLAN_SCHEMA_VERSION
        ):
            raise ValueError(
                "plan_schema_version must match the current edit-plan schema."
            )
        if type(self.executable) is not bool or self.executable:
            raise ValueError("safe authoring templates must be non-executable.")

    @property
    def operation_type(self) -> str | None:
        """Return the selected starter operation type, if any."""

        if self.operation is None:
            return None
        return self.operation.operation_type

    def to_dict(self) -> dict[str, object]:
        """Return a stable JSON-ready authoring template."""

        marker: dict[str, object] = {
            "format_version": self.template_format_version,
            "executable": self.executable,
            "operation_type": self.operation_type,
            "supported_operation_types": list(self.supported_operation_types),
            "instructions": list(_TEMPLATE_INSTRUCTIONS),
        }
        operations: list[dict[str, object]] = []
        if self.operation is not None:
            marker["starter_fields"] = list(
                self.operation.placeholder_field_names
            )
            operations.append(self.operation.to_dict())

        return {
            PMX_EDIT_PLAN_TEMPLATE_MARKER: marker,
            "schema_version": self.plan_schema_version,
            "operations": operations,
        }


def _select_starter_fields(
    entry: PmxEditOperationCatalogEntry,
) -> tuple[PmxEditFieldSpec, ...]:
    """Choose safe placeholders without inventing executable values."""

    required_fields = tuple(field for field in entry.fields if field.required)
    selected_names = {field.name for field in required_fields}
    has_required_value = any(
        field.role is PmxEditFieldRole.VALUE
        for field in required_fields
    )

    if not has_required_value:
        starter_value = next(
            (
                field
                for field in entry.fields
                if not field.required and field.role is PmxEditFieldRole.VALUE
            ),
            None,
        )
        if starter_value is not None:
            selected_names.add(starter_value.name)

    selected_fields = tuple(
        field for field in entry.fields if field.name in selected_names
    )
    if not selected_fields:
        raise RuntimeError(
            f"supported operation {entry.operation_type!r} has no safe "
            "placeholder field for template generation."
        )
    return selected_fields


def get_pmx_edit_plan_template(
    operation_type: str | None = None,
) -> PmxEditPlanTemplate:
    """Build a plan skeleton or one operation-specific starter template."""

    if operation_type is not None and type(operation_type) is not str:
        raise TypeError("operation_type must be a string or None.")
    if operation_type == "":
        raise ValueError("operation_type cannot be empty.")

    catalog = get_pmx_edit_operation_catalog()
    supported_operation_types = tuple(
        entry.operation_type for entry in catalog.operations
    )

    if operation_type is None:
        return PmxEditPlanTemplate(
            supported_operation_types=supported_operation_types,
        )

    entry = next(
        (
            candidate
            for candidate in catalog.operations
            if candidate.operation_type == operation_type
        ),
        None,
    )
    if entry is None:
        supported = ", ".join(supported_operation_types)
        raise ValueError(
            f"unsupported operation type {operation_type!r}; "
            f"supported operation types: {supported}."
        )

    return PmxEditPlanTemplate(
        supported_operation_types=supported_operation_types,
        operation=PmxEditPlanTemplateOperation(
            operation_type=entry.operation_type,
            placeholder_fields=_select_starter_fields(entry),
        ),
    )


def render_pmx_edit_plan_template_json(
    template: PmxEditPlanTemplate,
    *,
    indent: int | None = 2,
) -> str:
    """Render stable Unicode-safe template JSON followed by a newline."""

    if not isinstance(template, PmxEditPlanTemplate):
        raise TypeError("template must be a PmxEditPlanTemplate instance.")
    if indent is not None:
        if type(indent) is not int:
            raise TypeError("indent must be an integer or None.")
        if indent < 0:
            raise ValueError("indent cannot be negative.")
    return (
        json.dumps(
            template.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            indent=indent,
        )
        + "\n"
    )
