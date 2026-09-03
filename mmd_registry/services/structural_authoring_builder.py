"""Typed builder boundary for human-friendly structural authoring."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TypeAlias

from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.pmx.transaction_plan import (
    PmxStructuralTransactionPlan,
    render_pmx_structural_transaction_plan_json,
)
from mmd_registry.services import PmxStructuralCollectionEdit
from mmd_registry.services.structural_authoring_selector import (
    PmxStructuralAuthoringSelectorResolution,
)
from mmd_registry.services.structural_bone import PmxStructuralBoneInsertion
from mmd_registry.services.structural_material import PmxStructuralMaterialInsertion
from mmd_registry.services.structural_morph import PmxStructuralMorphInsertion
from mmd_registry.services.structural_rigid_body import (
    PmxStructuralRigidBodyInsertion,
)
from mmd_registry.services.structural_texture import PmxStructuralTextureInsertion
from mmd_registry.services.structural_vertex import PmxStructuralVertexInsertion


PmxStructuralAuthoringInsertion: TypeAlias = (
    PmxStructuralTextureInsertion
    | PmxStructuralMaterialInsertion
    | PmxStructuralBoneInsertion
    | PmxStructuralMorphInsertion
    | PmxStructuralRigidBodyInsertion
    | PmxStructuralVertexInsertion
)
PmxStructuralAuthoringOperation: TypeAlias = (
    PmxStructuralCollectionEdit | PmxStructuralAuthoringInsertion
)


class PmxStructuralAuthoringBuilderServiceOperation(StrEnum):
    """Stable builder service operations."""

    COMPILE_INSERT_BEFORE = "compile_structural_authoring_insert_before"
    BUILD_PLAN = "build_structural_authoring_plan"
    RENDER_PLAN = "render_structural_authoring_plan"


class PmxStructuralAuthoringBuilderServiceDiagnosticCode(StrEnum):
    """Stable disclosure-safe builder failure categories."""

    INVALID_ARGUMENT = "invalid_argument"
    TARGET_KIND_MISMATCH = "target_kind_mismatch"
    PLAN_INVALID = "structural_authoring_plan_invalid"
    INTERNAL_ERROR = "structural_authoring_builder_internal_error"


@dataclass(frozen=True, slots=True)
class PmxStructuralAuthoringBuilderServiceDiagnostic:
    """One bounded builder diagnostic without authored values."""

    code: PmxStructuralAuthoringBuilderServiceDiagnosticCode
    operation: PmxStructuralAuthoringBuilderServiceOperation
    message: str

    def __post_init__(self) -> None:
        if not isinstance(
            self.code,
            PmxStructuralAuthoringBuilderServiceDiagnosticCode,
        ):
            raise TypeError("invalid builder diagnostic code.")
        if not isinstance(
            self.operation,
            PmxStructuralAuthoringBuilderServiceOperation,
        ):
            raise TypeError("invalid builder diagnostic operation.")
        if type(self.message) is not str or not self.message:
            raise ValueError("builder diagnostic message must be non-empty.")

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code.value,
            "operation": self.operation.value,
            "message": self.message,
        }


class PmxStructuralAuthoringBuilderServiceError(RuntimeError):
    """Structured fail-closed builder failure."""

    def __init__(
        self,
        diagnostic: PmxStructuralAuthoringBuilderServiceDiagnostic,
    ) -> None:
        if not isinstance(
            diagnostic,
            PmxStructuralAuthoringBuilderServiceDiagnostic,
        ):
            raise TypeError("diagnostic must be a builder service diagnostic.")
        self.diagnostic = diagnostic
        super().__init__(diagnostic.message)

    def to_dict(self) -> dict[str, object]:
        return self.diagnostic.to_dict()


def _diagnostic(
    code: PmxStructuralAuthoringBuilderServiceDiagnosticCode,
    operation: PmxStructuralAuthoringBuilderServiceOperation,
    message: str,
) -> PmxStructuralAuthoringBuilderServiceDiagnostic:
    return PmxStructuralAuthoringBuilderServiceDiagnostic(
        code=code,
        operation=operation,
        message=message,
    )


def _insertion_target_kind(
    insertion: PmxStructuralAuthoringInsertion,
) -> PmxReferenceTargetKind:
    if isinstance(insertion, PmxStructuralTextureInsertion):
        return PmxReferenceTargetKind.TEXTURE
    if isinstance(insertion, PmxStructuralMaterialInsertion):
        return PmxReferenceTargetKind.MATERIAL
    if isinstance(insertion, PmxStructuralBoneInsertion):
        return PmxReferenceTargetKind.BONE
    if isinstance(insertion, PmxStructuralMorphInsertion):
        return PmxReferenceTargetKind.MORPH
    if isinstance(insertion, PmxStructuralRigidBodyInsertion):
        return PmxReferenceTargetKind.RIGID_BODY
    if isinstance(insertion, PmxStructuralVertexInsertion):
        return PmxReferenceTargetKind.VERTEX
    raise TypeError("insertion must be a released structural insertion DTO.")


def compile_structural_authoring_insert_before(
    insertion: PmxStructuralAuthoringInsertion,
    resolution: PmxStructuralAuthoringSelectorResolution,
) -> PmxStructuralAuthoringInsertion:
    """Compile one resolved exact selector into a released insertion DTO."""

    operation = (
        PmxStructuralAuthoringBuilderServiceOperation.COMPILE_INSERT_BEFORE
    )
    try:
        target_kind = _insertion_target_kind(insertion)
        if not isinstance(
            resolution,
            PmxStructuralAuthoringSelectorResolution,
        ):
            raise TypeError(
                "resolution must be a selector resolution instance."
            )
        if insertion.position != "append" or insertion.source_index is not None:
            raise ValueError(
                "builder placement requires an unanchored append insertion."
            )
        if resolution.target_kind is not target_kind:
            raise PmxStructuralAuthoringBuilderServiceError(
                _diagnostic(
                    (
                        PmxStructuralAuthoringBuilderServiceDiagnosticCode
                        .TARGET_KIND_MISMATCH
                    ),
                    operation,
                    "Selector resolution target does not match insertion target.",
                )
            )
        return replace(
            insertion,
            position="insert_before",
            source_index=resolution.source_index,
        )
    except PmxStructuralAuthoringBuilderServiceError:
        raise
    except (TypeError, ValueError):
        failure = PmxStructuralAuthoringBuilderServiceError(
            _diagnostic(
                PmxStructuralAuthoringBuilderServiceDiagnosticCode.INVALID_ARGUMENT,
                operation,
                "Invalid structural authoring insertion placement input.",
            )
        )
    except Exception:
        failure = PmxStructuralAuthoringBuilderServiceError(
            _diagnostic(
                PmxStructuralAuthoringBuilderServiceDiagnosticCode.INTERNAL_ERROR,
                operation,
                "Unexpected structural authoring builder failure.",
            )
        )
    raise failure from None


def build_structural_authoring_plan(
    operations: tuple[PmxStructuralAuthoringOperation, ...],
    *,
    expected_source_sha256: str | None = None,
) -> PmxStructuralTransactionPlan:
    """Build exactly one existing schema-one transaction plan."""

    operation = PmxStructuralAuthoringBuilderServiceOperation.BUILD_PLAN
    try:
        if type(operations) is not tuple:
            raise TypeError("operations must be a tuple.")
        allowed_types = (
            PmxStructuralCollectionEdit,
            PmxStructuralTextureInsertion,
            PmxStructuralMaterialInsertion,
            PmxStructuralBoneInsertion,
            PmxStructuralMorphInsertion,
            PmxStructuralRigidBodyInsertion,
            PmxStructuralVertexInsertion,
        )
        if not all(isinstance(item, allowed_types) for item in operations):
            raise TypeError(
                "operations must contain only released structural operation DTOs."
            )
        return PmxStructuralTransactionPlan(
            operations=operations,
            expected_source_sha256=expected_source_sha256,
        )
    except (TypeError, ValueError):
        failure = PmxStructuralAuthoringBuilderServiceError(
            _diagnostic(
                PmxStructuralAuthoringBuilderServiceDiagnosticCode.PLAN_INVALID,
                operation,
                "Structural authoring plan is invalid.",
            )
        )
    except Exception:
        failure = PmxStructuralAuthoringBuilderServiceError(
            _diagnostic(
                PmxStructuralAuthoringBuilderServiceDiagnosticCode.INTERNAL_ERROR,
                operation,
                "Unexpected structural authoring builder failure.",
            )
        )
    raise failure from None


def render_structural_authoring_plan(
    plan: PmxStructuralTransactionPlan,
) -> str:
    """Delegate rendering to the existing canonical schema-one renderer."""

    operation = PmxStructuralAuthoringBuilderServiceOperation.RENDER_PLAN
    try:
        if not isinstance(plan, PmxStructuralTransactionPlan):
            raise TypeError(
                "plan must be a PmxStructuralTransactionPlan instance."
            )
        return render_pmx_structural_transaction_plan_json(plan)
    except TypeError:
        failure = PmxStructuralAuthoringBuilderServiceError(
            _diagnostic(
                PmxStructuralAuthoringBuilderServiceDiagnosticCode.INVALID_ARGUMENT,
                operation,
                "Invalid structural authoring render input.",
            )
        )
    except Exception:
        failure = PmxStructuralAuthoringBuilderServiceError(
            _diagnostic(
                PmxStructuralAuthoringBuilderServiceDiagnosticCode.INTERNAL_ERROR,
                operation,
                "Unexpected structural authoring builder failure.",
            )
        )
    raise failure from None


__all__ = (
    "PmxStructuralAuthoringInsertion",
    "PmxStructuralAuthoringOperation",
    "PmxStructuralAuthoringBuilderServiceOperation",
    "PmxStructuralAuthoringBuilderServiceDiagnosticCode",
    "PmxStructuralAuthoringBuilderServiceDiagnostic",
    "PmxStructuralAuthoringBuilderServiceError",
    "compile_structural_authoring_insert_before",
    "build_structural_authoring_plan",
    "render_structural_authoring_plan",
)
