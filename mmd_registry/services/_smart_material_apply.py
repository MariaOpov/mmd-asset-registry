"""Private v0.9.5.8 Smart Material confirmed-apply integration boundary."""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

import mmd_registry.services as services
from mmd_registry.pmx import load_pmx, validate_pmx_document
from mmd_registry.pmx.editing import (
    PMX_EDIT_PLAN_SCHEMA_VERSION,
    PMX_EDIT_PREVIEW_SCHEMA_VERSION,
    calculate_pmx_edit_plan_sha256,
)


@dataclass(frozen=True, slots=True)
class SmartMaterialApplyConfirmation:
    """Explicit immutable confirmation bound to exact preview/source/plan identity."""

    preview_schema_version: int
    source_sha256: str
    plan_sha256: str


class SmartMaterialApplyError(RuntimeError):
    """Private Smart-specific confirmed-apply boundary failure."""

    def __init__(self, reason: str, message: str) -> None:
        if not isinstance(reason, str) or not reason:
            raise ValueError("reason must be a non-empty string.")
        if not isinstance(message, str) or not message:
            raise ValueError("message must be a non-empty string.")
        self.reason = reason
        super().__init__(message)


def apply_smart_material_color_draft(
    source_path: object,
    destination_path: object,
    draft: object,
    preview: object,
    *,
    confirmation: object = None,
) -> object:
    """Apply one explicitly confirmed Smart Material draft through existing authority."""

    if confirmation is None:
        raise SmartMaterialApplyError(
            "confirmation_required",
            "Explicit Smart Material apply confirmation is required.",
        )

    if type(confirmation) is not SmartMaterialApplyConfirmation:
        raise TypeError(
            "confirmation must be exactly SmartMaterialApplyConfirmation."
        )

    expected_preview_schema_version = PMX_EDIT_PREVIEW_SCHEMA_VERSION
    expected_source_sha256 = getattr(preview, "source_sha256", None)
    expected_plan_sha256 = calculate_pmx_edit_plan_sha256(draft)
    expected_preview_plan_sha256 = getattr(preview, "plan_sha256", None)
    expected_draft_plan_schema_version = getattr(draft, "schema_version", None)
    expected_preview_plan_schema_version = getattr(
        preview,
        "plan_schema_version",
        None,
    )
    expected_operation_count = len(getattr(draft, "operations", ()))
    expected_preview_operation_count = getattr(preview, "operation_count", None)

    if (
        getattr(confirmation, "preview_schema_version", None)
        != expected_preview_schema_version
        or getattr(confirmation, "source_sha256", None)
        != expected_source_sha256
        or getattr(confirmation, "plan_sha256", None)
        != expected_plan_sha256
        or expected_preview_plan_sha256 != expected_plan_sha256
        or expected_draft_plan_schema_version != PMX_EDIT_PLAN_SCHEMA_VERSION
        or expected_preview_plan_schema_version != PMX_EDIT_PLAN_SCHEMA_VERSION
        or expected_preview_operation_count != expected_operation_count
    ):
        raise SmartMaterialApplyError(
            "confirmation_mismatch",
            "Smart Material apply confirmation does not match the approved identity.",
        )

    current_source_bytes = Path(source_path).read_bytes()
    current_source_sha256 = hashlib.sha256(current_source_bytes).hexdigest()
    expected_draft_source_sha256 = getattr(draft, "expected_source_sha256", None)

    if (
        current_source_sha256 != expected_source_sha256
        or current_source_sha256 != expected_draft_source_sha256
        or current_source_sha256
        != getattr(confirmation, "source_sha256", None)
    ):
        raise SmartMaterialApplyError(
            "source_evidence_mismatch",
            "Current source content no longer matches the approved Smart Material evidence.",
        )

    verification_preview = services.preview_edit(current_source_bytes, draft)
    if verification_preview != preview:
        raise SmartMaterialApplyError(
            "preview_apply_mismatch",
            "Current Smart Material preview no longer matches the approved preview.",
        )

    result = services.apply_edit(
        source_path,
        destination_path,
        draft,
        overwrite=False,
    )

    if getattr(result, "preview", None) != preview:
        raise SmartMaterialApplyError(
            "preview_apply_mismatch",
            "Applied Smart Material result does not match the approved preview.",
        )

    destination_bytes = Path(destination_path).read_bytes()
    destination_sha256 = hashlib.sha256(destination_bytes).hexdigest()
    if destination_sha256 != getattr(result, "output_sha256", None):
        raise SmartMaterialApplyError(
            "post_write_certification_failed",
            "Published Smart Material output failed SHA-256 certification.",
        )

    try:
        reparsed_document = load_pmx(io.BytesIO(destination_bytes))
    except Exception as error:
        raise SmartMaterialApplyError(
            "post_write_certification_failed",
            "Published Smart Material output failed PMX reparse certification.",
        ) from error

    if reparsed_document != getattr(preview, "document", None):
        raise SmartMaterialApplyError(
            "post_write_certification_failed",
            "Published Smart Material output does not match the approved preview document.",
        )

    try:
        validate_pmx_document(reparsed_document)
    except Exception as error:
        raise SmartMaterialApplyError(
            "post_write_certification_failed",
            "Published Smart Material output failed PMX validation certification.",
        ) from error

    post_write_source_bytes = Path(source_path).read_bytes()
    post_write_source_sha256 = hashlib.sha256(post_write_source_bytes).hexdigest()
    if post_write_source_sha256 != expected_source_sha256:
        raise SmartMaterialApplyError(
            "post_write_certification_failed",
            "Source content changed during Smart Material apply publication.",
        )

    return result
