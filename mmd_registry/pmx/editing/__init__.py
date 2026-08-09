"""Typed foundations for safe declarative PMX editing."""

from mmd_registry.pmx.editing.audit import (
    PmxAuditValue,
    PmxEditAudit,
    PmxEditCategory,
    PmxEditChange,
)
from mmd_registry.pmx.editing.engine import PmxEditResult, apply_set_model_info
from mmd_registry.pmx.editing.errors import PmxEditPlanError
from mmd_registry.pmx.editing.operations import (
    PmxEditOperation,
    SetModelInfo,
    SetTexturePath,
    UpdateMaterial,
)
from mmd_registry.pmx.editing.plan import (
    PMX_EDIT_PLAN_SCHEMA_VERSION,
    PmxEditPlan,
)
from mmd_registry.pmx.editing.validation import validate_pmx_edit_plan

__all__ = [
    "PMX_EDIT_PLAN_SCHEMA_VERSION",
    "PmxAuditValue",
    "PmxEditAudit",
    "PmxEditCategory",
    "PmxEditChange",
    "PmxEditOperation",
    "PmxEditPlan",
    "PmxEditPlanError",
    "PmxEditResult",
    "SetModelInfo",
    "SetTexturePath",
    "UpdateMaterial",
    "apply_set_model_info",
    "validate_pmx_edit_plan",
]
