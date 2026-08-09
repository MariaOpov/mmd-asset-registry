"""Deterministic in-memory dry-run previews for PMX edit plans."""

from __future__ import annotations

import hashlib
import io
import json
import re
from dataclasses import dataclass
from typing import Final

from mmd_registry.pmx import load_pmx, serialize_pmx
from mmd_registry.pmx.document import PmxDocument
from mmd_registry.pmx.editing.audit import PmxAuditValue, PmxEditAudit
from mmd_registry.pmx.editing.engine import apply_pmx_edit_plan
from mmd_registry.pmx.editing.errors import PmxEditVerificationError
from mmd_registry.pmx.editing.plan import PmxEditPlan


PMX_EDIT_PREVIEW_SCHEMA_VERSION: Final[int] = 1
_LOWERCASE_SHA256: Final[re.Pattern[str]] = re.compile(r"[0-9a-f]{64}\Z")


def _validate_sha256(value: object, field_name: str) -> None:
    """Require one exact lowercase SHA-256 digest."""

    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    if _LOWERCASE_SHA256.fullmatch(value) is None:
        raise ValueError(
            f"{field_name} must be exactly 64 lowercase hexadecimal characters."
        )


@dataclass(frozen=True, slots=True)
class PmxEditPreview:
    """One verified dry-run document and its stable report metadata."""

    document: PmxDocument
    audit: PmxEditAudit
    source_sha256: str
    source_size_bytes: int
    plan_sha256: str
    plan_schema_version: int
    operation_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.document, PmxDocument):
            raise TypeError("document must be a PmxDocument instance.")
        if not isinstance(self.audit, PmxEditAudit):
            raise TypeError("audit must be a PmxEditAudit instance.")
        _validate_sha256(self.source_sha256, "source_sha256")
        _validate_sha256(self.plan_sha256, "plan_sha256")
        for field_name in (
            "source_size_bytes",
            "plan_schema_version",
            "operation_count",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"{field_name} must be an integer.")
        if self.source_size_bytes < 0:
            raise ValueError("source_size_bytes cannot be negative.")
        if self.plan_schema_version < 1:
            raise ValueError("plan_schema_version must be positive.")
        if self.operation_count < 1:
            raise ValueError("operation_count must be positive.")

    @property
    def status(self) -> str:
        """Return the stable dry-run outcome name."""

        return "no_changes" if self.audit.changed_fields == 0 else "changes_pending"

    def to_dict(self) -> dict[str, object]:
        """Return one deterministic GUI-friendly JSON report payload."""

        return {
            "preview_schema_version": PMX_EDIT_PREVIEW_SCHEMA_VERSION,
            "status": self.status,
            "dry_run": True,
            "source": {
                "sha256": self.source_sha256,
                "size_bytes": self.source_size_bytes,
            },
            "plan": {
                "sha256": self.plan_sha256,
                "schema_version": self.plan_schema_version,
                "operation_count": self.operation_count,
            },
            "output": {
                "written": False,
                "sha256": None,
            },
            "verification": {
                "semantic": "passed",
                "input_unchanged": True,
            },
            "audit": self.audit.to_dict(),
        }


def calculate_pmx_edit_plan_sha256(plan: PmxEditPlan) -> str:
    """Hash the canonical UTF-8 JSON representation of one typed plan."""

    if not isinstance(plan, PmxEditPlan):
        raise TypeError("plan must be a PmxEditPlan instance.")
    canonical_json = json.dumps(
        plan.to_dict(),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def dry_run_pmx_edit(
    source_bytes: bytes,
    plan: PmxEditPlan,
) -> PmxEditPreview:
    """Parse, apply, serialize, and semantically verify without filesystem I/O."""

    if type(source_bytes) is not bytes:
        raise TypeError("source_bytes must be bytes.")
    if not isinstance(plan, PmxEditPlan):
        raise TypeError("plan must be a PmxEditPlan instance.")

    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    source_document = load_pmx(io.BytesIO(source_bytes))
    result = apply_pmx_edit_plan(
        source_document,
        plan,
        source_sha256=source_sha256,
    )

    serialized_document = serialize_pmx(result.document)
    reparsed_document = load_pmx(io.BytesIO(serialized_document))
    if reparsed_document != result.document:
        raise PmxEditVerificationError(
            "serialized PMX does not match the intended edited document."
        )
    if hashlib.sha256(source_bytes).hexdigest() != source_sha256:
        raise PmxEditVerificationError(
            "source bytes changed during the in-memory dry run."
        )

    return PmxEditPreview(
        document=result.document,
        audit=result.audit,
        source_sha256=source_sha256,
        source_size_bytes=len(source_bytes),
        plan_sha256=calculate_pmx_edit_plan_sha256(plan),
        plan_schema_version=plan.schema_version,
        operation_count=len(plan.operations),
    )


def _render_audit_value(value: PmxAuditValue) -> str:
    """Render one typed audit value without unstable ``repr`` output."""

    json_value: object = list(value) if isinstance(value, tuple) else value
    return json.dumps(
        json_value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )


def _changed_count(count: int, singular: str, plural: str) -> str:
    """Render one stable category-count phrase."""

    unit = singular if count == 1 else plural
    return f"{count} {unit} changed"


def render_pmx_edit_preview_text(
    preview: PmxEditPreview,
    *,
    include_changes: bool = True,
) -> str:
    """Render a compact Unicode-safe text preview."""

    if not isinstance(preview, PmxEditPreview):
        raise TypeError("preview must be a PmxEditPreview instance.")
    if not isinstance(include_changes, bool):
        raise TypeError("include_changes must be a boolean.")

    audit = preview.audit
    status = (
        "no changes"
        if audit.changed_fields == 0
        else f"{audit.changed_fields} fields changed"
    )
    lines = [
        "PMX EDIT PREVIEW",
        f"Status: {status}",
        "Model: "
        + _changed_count(audit.category_count("model"), "field", "fields"),
        "Textures: "
        + _changed_count(audit.category_count("texture"), "path", "paths"),
        "Materials: "
        + _changed_count(audit.category_count("material"), "field", "fields"),
        f"Source SHA-256: {preview.source_sha256}",
        f"Plan SHA-256: {preview.plan_sha256}",
        "Semantic verification: passed",
        "Source unchanged: yes",
        "Output written: no (dry-run)",
    ]
    if include_changes and audit.changes:
        lines.extend(("", "Changes:"))
        lines.extend(
            (
                f"- {change.field_path}: "
                f"{_render_audit_value(change.before)} -> "
                f"{_render_audit_value(change.after)}"
            )
            for change in audit.changes
        )
    return "\n".join(lines) + "\n"


def render_pmx_edit_preview_json(
    preview: PmxEditPreview,
    *,
    indent: int | None = 2,
) -> str:
    """Render one stable Unicode-safe JSON preview followed by a newline."""

    if not isinstance(preview, PmxEditPreview):
        raise TypeError("preview must be a PmxEditPreview instance.")
    if indent is not None:
        if not isinstance(indent, int) or isinstance(indent, bool):
            raise TypeError("indent must be an integer or None.")
        if indent < 0:
            raise ValueError("indent cannot be negative.")
    return (
        json.dumps(
            preview.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            indent=indent,
        )
        + "\n"
    )
