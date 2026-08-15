"""Typed side-effect-controlled service boundary for reusable PMX clients."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from mmd_registry.capabilities import (
    PmxCapabilityManifest,
    get_capabilities,
)
from mmd_registry.diagnostics import (
    PmxServiceError,
    PmxServiceOperation,
    diagnostic_from_service_error,
)
from mmd_registry.pmx.document import PmxDocument
from mmd_registry.pmx.editing.output import PmxEditWriteResult, write_pmx_edit
from mmd_registry.pmx.editing.plan import PmxEditPlan
from mmd_registry.pmx.editing.preview import PmxEditPreview, dry_run_pmx_edit
from mmd_registry.pmx.errors import PmxValidationError, PmxValidationIssue
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.validation import validate_pmx_document


@dataclass(frozen=True, slots=True)
class PmxDocumentMetadata:
    """Immutable model metadata exposed without leaking a CLI representation."""

    version: float
    encoding: str
    local_name: str
    universal_name: str
    local_comments: str
    universal_comments: str

    def __post_init__(self) -> None:
        if not isinstance(self.version, float):
            raise TypeError("version must be a float.")
        for field_name in (
            "encoding",
            "local_name",
            "universal_name",
            "local_comments",
            "universal_comments",
        ):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"{field_name} must be a string.")


@dataclass(frozen=True, slots=True)
class PmxDocumentValidationResult:
    """Immutable deterministic semantic-validation outcome."""

    issues: tuple[PmxValidationIssue, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.issues, tuple):
            raise TypeError("issues must be a tuple.")
        if not all(isinstance(issue, PmxValidationIssue) for issue in self.issues):
            raise TypeError("issues must contain only PmxValidationIssue values.")

    @property
    def is_valid(self) -> bool:
        """Return whether semantic validation found no issue."""

        return not self.issues


def load_document(source: str | Path | BinaryIO) -> PmxDocument:
    """Load one typed PMX document or raise one structured service failure."""

    try:
        return load_pmx(source)
    except Exception as error:
        failure = PmxServiceError(
            diagnostic_from_service_error(
                PmxServiceOperation.LOAD_DOCUMENT,
                error,
            )
        )
    raise failure from None


def inspect_document(document: PmxDocument) -> PmxDocumentMetadata:
    """Return immutable metadata or raise one structured service failure."""

    try:
        if not isinstance(document, PmxDocument):
            raise TypeError("document must be a PmxDocument instance.")
        model_info = document.model_info
        return PmxDocumentMetadata(
            version=document.header.version,
            encoding=document.header.encoding,
            local_name=model_info.local_name,
            universal_name=model_info.universal_name,
            local_comments=model_info.local_comments,
            universal_comments=model_info.universal_comments,
        )
    except Exception as error:
        failure = PmxServiceError(
            diagnostic_from_service_error(
                PmxServiceOperation.INSPECT_DOCUMENT,
                error,
            )
        )
    raise failure from None


def validate_document(document: PmxDocument) -> PmxDocumentValidationResult:
    """Return one structured deterministic result instead of terminal output."""

    if not isinstance(document, PmxDocument):
        raise TypeError("document must be a PmxDocument instance.")
    try:
        validate_pmx_document(document)
    except PmxValidationError as error:
        return PmxDocumentValidationResult(issues=(error.issue,))
    return PmxDocumentValidationResult()


def preview_edit(source_bytes: bytes, plan: PmxEditPlan) -> PmxEditPreview:
    """Run the existing verified in-memory edit preview pipeline."""

    return dry_run_pmx_edit(source_bytes, plan)


def apply_edit(
    input_path: str | Path,
    output_path: str | Path,
    plan: PmxEditPlan,
    *,
    overwrite: bool = False,
) -> PmxEditWriteResult:
    """Apply one plan through the existing safe distinct-output pipeline."""

    return write_pmx_edit(
        input_path,
        output_path,
        plan,
        overwrite=overwrite,
    )


__all__ = (
    "PmxDocumentMetadata",
    "PmxDocumentValidationResult",
    "apply_edit",
    "get_capabilities",
    "inspect_document",
    "load_document",
    "preview_edit",
    "validate_document",
)
