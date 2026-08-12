"""Typed foundations for safe declarative PMX editing."""

from mmd_registry.pmx.editing.audit import (
    PmxAuditValue,
    PmxEditAudit,
    PmxEditCategory,
    PmxEditChange,
)
from mmd_registry.pmx.editing.diagnostics import (
    PmxEditDiagnostic,
    PmxEditDiagnosticCode,
    PmxEditPhase,
    build_edit_plan_json_path,
    default_diagnostic_code,
    diagnostic_from_plan_error,
    render_pmx_edit_diagnostic_json,
    render_pmx_edit_diagnostic_text,
)
from mmd_registry.pmx.editing.engine import (
    PmxEditResult,
    apply_pmx_edit_plan,
    apply_set_model_info,
    apply_set_texture_path,
    apply_update_material,
)
from mmd_registry.pmx.editing.errors import (
    PmxEditPathError,
    PmxEditPlanDecodeError,
    PmxEditPlanError,
    PmxEditVerificationError,
)
from mmd_registry.pmx.editing.json_loader import (
    load_pmx_edit_plan,
    parse_pmx_edit_plan_json,
)
from mmd_registry.pmx.editing.operations import (
    PmxEditOperation,
    SetModelInfo,
    SetTexturePath,
    UpdateMaterial,
)
from mmd_registry.pmx.editing.numeric import canonicalize_pmx_float32
from mmd_registry.pmx.editing.plan import (
    PMX_EDIT_PLAN_SCHEMA_VERSION,
    PmxEditPlan,
)
from mmd_registry.pmx.editing.path_policy import validate_portable_texture_path
from mmd_registry.pmx.editing.preview import (
    PMX_EDIT_PREVIEW_SCHEMA_VERSION,
    PmxEditPreview,
    calculate_pmx_edit_plan_sha256,
    dry_run_pmx_edit,
    render_pmx_edit_preview_json,
    render_pmx_edit_preview_text,
)
from mmd_registry.pmx.editing.output import (
    PmxEditWriteResult,
    render_pmx_edit_write_json,
    render_pmx_edit_write_text,
    write_pmx_edit,
)
from mmd_registry.pmx.editing.validation import validate_pmx_edit_plan

__all__ = [
    "PMX_EDIT_PLAN_SCHEMA_VERSION",
    "PMX_EDIT_PREVIEW_SCHEMA_VERSION",
    "PmxAuditValue",
    "PmxEditAudit",
    "PmxEditCategory",
    "PmxEditChange",
    "PmxEditDiagnostic",
    "PmxEditDiagnosticCode",
    "PmxEditOperation",
    "PmxEditPathError",
    "PmxEditPhase",
    "PmxEditPlan",
    "PmxEditPlanDecodeError",
    "PmxEditPlanError",
    "PmxEditPreview",
    "PmxEditResult",
    "PmxEditVerificationError",
    "PmxEditWriteResult",
    "SetModelInfo",
    "SetTexturePath",
    "UpdateMaterial",
    "apply_pmx_edit_plan",
    "apply_set_model_info",
    "apply_set_texture_path",
    "apply_update_material",
    "build_edit_plan_json_path",
    "canonicalize_pmx_float32",
    "calculate_pmx_edit_plan_sha256",
    "default_diagnostic_code",
    "diagnostic_from_plan_error",
    "dry_run_pmx_edit",
    "load_pmx_edit_plan",
    "parse_pmx_edit_plan_json",
    "render_pmx_edit_diagnostic_json",
    "render_pmx_edit_diagnostic_text",
    "render_pmx_edit_preview_json",
    "render_pmx_edit_preview_text",
    "render_pmx_edit_write_json",
    "render_pmx_edit_write_text",
    "validate_portable_texture_path",
    "validate_pmx_edit_plan",
    "write_pmx_edit",
]
