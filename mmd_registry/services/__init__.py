"""Typed side-effect-controlled service boundary for reusable PMX clients."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import BinaryIO

from mmd_registry.capabilities import (
    PmxCapabilityManifest,
    get_capabilities,
)
from mmd_registry.diagnostics import (
    PmxServiceDiagnostic as _PmxServiceDiagnostic,
    PmxServiceError,
    PmxServiceOperation,
    diagnostic_from_service_error,
)
from mmd_registry.services.structural_bone import (
    PmxStructuralBoneInsertion as _PmxStructuralBoneInsertion,
)
from mmd_registry.services.structural_material import (
    PmxStructuralMaterialInsertion as _PmxStructuralMaterialInsertion,
)
from mmd_registry.services.structural_morph import (
    PmxStructuralMorphBoneOffset as _PmxStructuralMorphBoneOffset,
    PmxStructuralMorphFlipOffset as _PmxStructuralMorphFlipOffset,
    PmxStructuralMorphGroupOffset as _PmxStructuralMorphGroupOffset,
    PmxStructuralMorphImpulseOffset as _PmxStructuralMorphImpulseOffset,
    PmxStructuralMorphInsertion as _PmxStructuralMorphInsertion,
    PmxStructuralMorphMaterialOffset as _PmxStructuralMorphMaterialOffset,
    PmxStructuralMorphUvOffset as _PmxStructuralMorphUvOffset,
    PmxStructuralMorphVertexOffset as _PmxStructuralMorphVertexOffset,
)
from mmd_registry.services.structural_reference import (
    PmxStructuralNewReference as _PmxStructuralNewReference,
)
from mmd_registry.services.structural_rigid_body import (
    PmxStructuralRigidBodyInsertion as _PmxStructuralRigidBodyInsertion,
)
from mmd_registry.services.structural_texture import (
    PmxStructuralTextureInsertion as _PmxStructuralTextureInsertion,
)
from mmd_registry.services.structural_vertex import (
    PmxStructuralVertexBdef1 as _PmxStructuralVertexBdef1,
    PmxStructuralVertexBdef2 as _PmxStructuralVertexBdef2,
    PmxStructuralVertexBdef4 as _PmxStructuralVertexBdef4,
    PmxStructuralVertexInsertion as _PmxStructuralVertexInsertion,
    PmxStructuralVertexQdef as _PmxStructuralVertexQdef,
    PmxStructuralVertexSdef as _PmxStructuralVertexSdef,
)
from mmd_registry.pmx.collection_transform import (
    PmxCollectionTransform,
    PmxStructuralTransformIntent,
)
from mmd_registry.pmx.document import PmxDocument
from mmd_registry.pmx.editing.output import PmxEditWriteResult, write_pmx_edit
from mmd_registry.pmx.editing.plan import PmxEditPlan
from mmd_registry.pmx.editing.preview import PmxEditPreview, dry_run_pmx_edit
from mmd_registry.pmx.errors import PmxValidationError, PmxValidationIssue
from mmd_registry.pmx.index_remap import PmxIndexRemap
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.reference_diagnostics import (
    PmxReferenceDiagnostic,
    PmxReferenceDiagnosticCode,
    diagnose_reference_graph,
)
from mmd_registry.pmx.reference_graph import (
    PmxReferenceGraph,
    extract_pmx_reference_graph,
)
from mmd_registry.pmx.reference_model import (
    PmxReferenceNode,
    PmxReferenceTargetKind,
)
from mmd_registry.pmx.reference_queries import (
    PmxReferenceImpact,
    analyze_reference_impact,
)
from mmd_registry.pmx.structural_coordinated_insertion import (
    PmxCoordinatedInsertionCollectionSpec as _PmxCoordinatedInsertionCollectionSpec,
    PmxCoordinatedInsertionPayloads as _PmxCoordinatedInsertionPayloads,
    PmxCoordinatedInsertionPreview as _PmxCoordinatedInsertionPreview,
    PmxCoordinatedReferencePlan as _PmxCoordinatedReferencePlan,
    plan_pmx_coordinated_insertion_references as _plan_pmx_coordinated_insertion_references,
    preview_pmx_coordinated_insertions as _preview_pmx_coordinated_insertions,
)
from mmd_registry.pmx.structural_insert_intent import (
    PmxStructuralInsertPosition as _PmxStructuralInsertPosition,
)
from mmd_registry.pmx.structural_bone_insertion import (
    PmxBoneIkInsertionPayload as _PmxBoneIkInsertionPayload,
    PmxBoneIkLinkInsertionPayload as _PmxBoneIkLinkInsertionPayload,
    PmxBoneInsertionPayload as _PmxBoneInsertionPayload,
    PmxBoneInsertionPreview as _PmxBoneInsertionPreview,
    preview_pmx_bone_insertions as _preview_pmx_bone_insertions,
)
from mmd_registry.pmx.structural_material_insertion import (
    PmxMaterialInsertionPayload as _PmxMaterialInsertionPayload,
    PmxMaterialInsertionPreview as _PmxMaterialInsertionPreview,
    preview_pmx_material_insertions as _preview_pmx_material_insertions,
)
from mmd_registry.pmx.structural_morph_insertion import (
    PmxBoneMorphInsertionOffsetPayload as _PmxBoneMorphInsertionOffsetPayload,
    PmxFlipMorphInsertionOffsetPayload as _PmxFlipMorphInsertionOffsetPayload,
    PmxGroupMorphInsertionOffsetPayload as _PmxGroupMorphInsertionOffsetPayload,
    PmxImpulseMorphInsertionOffsetPayload as _PmxImpulseMorphInsertionOffsetPayload,
    PmxMaterialMorphInsertionOffsetPayload as _PmxMaterialMorphInsertionOffsetPayload,
    PmxMorphInsertionPayload as _PmxMorphInsertionPayload,
    PmxMorphInsertionPreview as _PmxMorphInsertionPreview,
    PmxUvMorphInsertionOffsetPayload as _PmxUvMorphInsertionOffsetPayload,
    PmxVertexMorphInsertionOffsetPayload as _PmxVertexMorphInsertionOffsetPayload,
    preview_pmx_morph_insertions as _preview_pmx_morph_insertions,
)
from mmd_registry.pmx.structural_rigid_body_insertion import (
    PmxRigidBodyInsertionPayload as _PmxRigidBodyInsertionPayload,
    PmxRigidBodyInsertionPreview as _PmxRigidBodyInsertionPreview,
    preview_pmx_rigid_body_insertions as _preview_pmx_rigid_body_insertions,
)
from mmd_registry.pmx.structural_preview import (
    PmxStructuralPreview as _PmxStructuralPreview,
    preview_pmx_structural_transform as _preview_pmx_structural_transform,
)
from mmd_registry.pmx.structural_texture_insertion import (
    PmxTextureInsertionPayload as _PmxTextureInsertionPayload,
    PmxTextureInsertionPreview as _PmxTextureInsertionPreview,
    preview_pmx_texture_insertions as _preview_pmx_texture_insertions,
)
from mmd_registry.pmx.structural_vertex_insertion import (
    PmxVertexBdef1InsertionPayload as _PmxVertexBdef1InsertionPayload,
    PmxVertexBdef2InsertionPayload as _PmxVertexBdef2InsertionPayload,
    PmxVertexBdef4InsertionPayload as _PmxVertexBdef4InsertionPayload,
    PmxVertexInsertionPayload as _PmxVertexInsertionPayload,
    PmxVertexInsertionPreview as _PmxVertexInsertionPreview,
    PmxVertexQdefInsertionPayload as _PmxVertexQdefInsertionPayload,
    PmxVertexSdefInsertionPayload as _PmxVertexSdefInsertionPayload,
    preview_pmx_vertex_insertions as _preview_pmx_vertex_insertions,
)
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

    def to_dict(self) -> dict[str, object]:
        """Return a deterministic JSON-ready validation payload."""

        return {
            "is_valid": self.is_valid,
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class PmxReferenceAnalysisResult:
    """Immutable reference-analysis snapshot for reusable public clients."""

    graph: PmxReferenceGraph
    diagnostics: tuple[PmxReferenceDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.graph, PmxReferenceGraph):
            raise TypeError("graph must be a PmxReferenceGraph value.")
        if type(self.diagnostics) is not tuple:
            raise TypeError("diagnostics must be a tuple.")
        if not all(
            isinstance(item, PmxReferenceDiagnostic)
            for item in self.diagnostics
        ):
            raise TypeError(
                "diagnostics must contain only PmxReferenceDiagnostic values."
            )

        expected_diagnostics = diagnose_reference_graph(self.graph)
        if self.diagnostics != expected_diagnostics:
            raise ValueError(
                "diagnostics must exactly match diagnostics derived from graph."
            )

    @property
    def is_clean(self) -> bool:
        """Whether extraction produced no invalid or unsupported evidence."""

        return not self.diagnostics

    @property
    def relationship_counts(self) -> tuple[tuple[str, int], ...]:
        """Return deterministic counts of valid edges by relationship ID."""

        counts: dict[str, int] = {}
        for edge in self.graph.edges:
            counts[edge.relationship_id] = counts.get(edge.relationship_id, 0) + 1
        return tuple(sorted(counts.items()))

    def to_dict(self) -> dict[str, object]:
        """Return a deterministic JSON-ready analysis summary."""

        counts = self.graph.target_counts
        return {
            "is_clean": self.is_clean,
            "target_counts": {
                "vertex": counts.vertex,
                "texture": counts.texture,
                "material": counts.material,
                "bone": counts.bone,
                "morph": counts.morph,
                "rigid_body": counts.rigid_body,
            },
            "edge_count": len(self.graph.edges),
            "relationship_counts": dict(self.relationship_counts),
            "invalid_target_count": len(self.graph.invalid_targets),
            "unsupported_state_count": len(self.graph.unsupported_states),
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }


@dataclass(frozen=True, slots=True)
class PmxStructuralCollectionEdit:
    """One bounded delete/reorder request for a structural target collection."""

    target_kind: PmxReferenceTargetKind
    old_indices_in_new_order: tuple[int, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.target_kind, PmxReferenceTargetKind):
            raise TypeError("target_kind must be a PmxReferenceTargetKind value.")
        if type(self.old_indices_in_new_order) is not tuple:
            raise TypeError("old_indices_in_new_order must be a tuple.")
        if any(type(index) is not int for index in self.old_indices_in_new_order):
            raise TypeError(
                "old_indices_in_new_order must contain only integer indices."
            )
        if any(index < 0 for index in self.old_indices_in_new_order):
            raise ValueError("old_indices_in_new_order cannot contain negative indices.")
        if len(set(self.old_indices_in_new_order)) != len(
            self.old_indices_in_new_order
        ):
            raise ValueError("old_indices_in_new_order cannot contain duplicates.")


@dataclass(frozen=True, slots=True)
class PmxStructuralPreviewRequest:
    """Immutable public request shared by structural preview and execution."""

    collection_edits: tuple[PmxStructuralCollectionEdit, ...] = ()
    texture_insertions: tuple[_PmxStructuralTextureInsertion, ...] = ()
    material_insertions: tuple[_PmxStructuralMaterialInsertion, ...] = ()
    bone_insertions: tuple[_PmxStructuralBoneInsertion, ...] = ()
    morph_insertions: tuple[_PmxStructuralMorphInsertion, ...] = ()
    rigid_body_insertions: tuple[_PmxStructuralRigidBodyInsertion, ...] = ()
    vertex_insertions: tuple[_PmxStructuralVertexInsertion, ...] = ()

    def __post_init__(self) -> None:
        if type(self.collection_edits) is not tuple:
            raise TypeError("collection_edits must be a tuple.")
        if not all(
            isinstance(edit, PmxStructuralCollectionEdit)
            for edit in self.collection_edits
        ):
            raise TypeError(
                "collection_edits must contain only PmxStructuralCollectionEdit values."
            )
        kinds = tuple(edit.target_kind for edit in self.collection_edits)
        if len(set(kinds)) != len(kinds):
            raise ValueError("collection_edits cannot repeat one target_kind.")

        if type(self.texture_insertions) is not tuple:
            raise TypeError("texture_insertions must be a tuple.")
        if not all(
            isinstance(insertion, _PmxStructuralTextureInsertion)
            for insertion in self.texture_insertions
        ):
            raise TypeError(
                "texture_insertions must contain only "
                "PmxStructuralTextureInsertion values."
            )

        if self.collection_edits and self.texture_insertions:
            raise ValueError(
                "texture insertions cannot be combined with legacy collection edits "
                "in the preview-only texture insertion gate."
            )

        if type(self.material_insertions) is not tuple:
            raise TypeError("material_insertions must be a tuple.")
        if not all(
            isinstance(insertion, _PmxStructuralMaterialInsertion)
            for insertion in self.material_insertions
        ):
            raise TypeError(
                "material_insertions must contain only "
                "PmxStructuralMaterialInsertion values."
            )

        if self.material_insertions and self.collection_edits:
            raise ValueError(
                "material insertions cannot be combined with legacy collection edits."
            )

        if type(self.bone_insertions) is not tuple:
            raise TypeError("bone_insertions must be a tuple.")
        if not all(
            isinstance(insertion, _PmxStructuralBoneInsertion)
            for insertion in self.bone_insertions
        ):
            raise TypeError(
                "bone_insertions must contain only PmxStructuralBoneInsertion values."
            )

        if self.bone_insertions and self.collection_edits:
            raise ValueError(
                "bone insertions cannot be combined with legacy collection edits."
            )

        if type(self.morph_insertions) is not tuple:
            raise TypeError("morph_insertions must be a tuple.")
        if not all(
            isinstance(insertion, _PmxStructuralMorphInsertion)
            for insertion in self.morph_insertions
        ):
            raise TypeError(
                "morph_insertions must contain only PmxStructuralMorphInsertion values."
            )

        if self.morph_insertions and self.collection_edits:
            raise ValueError(
                "morph insertions cannot be combined with legacy collection edits."
            )

        if type(self.rigid_body_insertions) is not tuple:
            raise TypeError("rigid_body_insertions must be a tuple.")
        if not all(
            isinstance(insertion, _PmxStructuralRigidBodyInsertion)
            for insertion in self.rigid_body_insertions
        ):
            raise TypeError(
                "rigid_body_insertions must contain only "
                "PmxStructuralRigidBodyInsertion values."
            )
        if self.rigid_body_insertions and self.collection_edits:
            raise ValueError(
                "rigid-body insertions cannot be combined with legacy collection edits."
            )


        if type(self.vertex_insertions) is not tuple:
            raise TypeError("vertex_insertions must be a tuple.")
        if not all(
            isinstance(insertion, _PmxStructuralVertexInsertion)
            for insertion in self.vertex_insertions
        ):
            raise TypeError(
                "vertex_insertions must contain only "
                "PmxStructuralVertexInsertion values."
            )
        if self.vertex_insertions and self.collection_edits:
            raise ValueError(
                "vertex insertions cannot be combined with legacy collection edits."
            )

        seen_new_ids: set[str] = set()
        for insertions in (
            self.vertex_insertions,
            self.texture_insertions,
            self.material_insertions,
            self.bone_insertions,
            self.morph_insertions,
            self.rigid_body_insertions,
        ):
            for insertion in insertions:
                new_id = insertion.new_id
                if new_id is None:
                    continue
                if new_id in seen_new_ids:
                    raise ValueError(
                        f"request-local new_id {new_id!r} must be globally unique."
                    )
                seen_new_ids.add(new_id)


@dataclass(frozen=True, slots=True)
class PmxStructuralPreviewResult:
    """Service-facing structural preview without exporting implementation types."""

    _preview: (
        _PmxStructuralPreview
        | _PmxTextureInsertionPreview
        | _PmxMaterialInsertionPreview
        | _PmxBoneInsertionPreview
        | _PmxMorphInsertionPreview
        | _PmxRigidBodyInsertionPreview
        | _PmxVertexInsertionPreview
        | _PmxCoordinatedInsertionPreview
    ) = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(
            self._preview,
            (
                _PmxStructuralPreview,
                _PmxTextureInsertionPreview,
                _PmxMaterialInsertionPreview,
                _PmxBoneInsertionPreview,
                _PmxMorphInsertionPreview,
                _PmxRigidBodyInsertionPreview,
                _PmxVertexInsertionPreview,
                _PmxCoordinatedInsertionPreview,
            ),
        ):
            raise TypeError("_preview must be an internal structural preview value.")

    @property
    def status(self) -> str:
        """Return the stable preview status."""

        return self._preview.status

    @property
    def document(self) -> PmxDocument:
        """Return the certified intended document represented by this preview."""

        return self._preview.certificate.document

    def to_dict(self) -> dict[str, object]:
        """Return deterministic JSON-ready preview evidence."""

        return self._preview.to_dict()


# v0.9.1 execution deliberately reuses the already-frozen request validation
# instead of introducing a competing structural-intent vocabulary.
PmxStructuralEditRequest = PmxStructuralPreviewRequest


@dataclass(frozen=True, slots=True)
class PmxStructuralExecutionResult:
    """Service-facing committed structural output without exporting the raw writer."""

    _result: object = field(repr=False)

    def __post_init__(self) -> None:
        from mmd_registry.pmx.structural_output import PmxStructuralWriteResult

        if not isinstance(self._result, PmxStructuralWriteResult):
            raise TypeError(
                "_result must be an internal PmxStructuralWriteResult value."
            )

    @property
    def status(self) -> str:
        return self._result.status

    @property
    def input_path(self) -> Path:
        return self._result.input_path

    @property
    def output_path(self) -> Path:
        return self._result.output_path

    @property
    def source_sha256(self) -> str:
        return self._result.source_sha256

    @property
    def output_sha256(self) -> str:
        return self._result.output_sha256

    @property
    def source_size_bytes(self) -> int:
        return self._result.source_size_bytes

    @property
    def output_size_bytes(self) -> int:
        return self._result.output_size_bytes

    @property
    def document(self) -> PmxDocument:
        return self._result.serialization.preview.certificate.document

    def to_dict(self) -> dict[str, object]:
        """Return deterministic JSON-ready committed-output evidence."""

        return self._result.to_dict()


_STRUCTURAL_FAILURE_PROVENANCE: tuple[tuple[str, str], ...] = (
    ("service_validation", "service_boundary"),
    ("path_resolution", "safe_output"),
    ("source_snapshot", "source_input"),
    ("source_parse", "source_input"),
    ("intent_resolution", "service_boundary"),
    ("structural_certification", "structural_pipeline"),
    ("serialization", "structural_pipeline"),
    ("reparse", "structural_pipeline"),
    ("reparse_certification", "structural_pipeline"),
    ("semantic_compare", "structural_pipeline"),
    ("output_commit", "safe_output"),
)


def _structural_failure_provenance(stage: str) -> str:
    """Resolve one frozen semantic stage without mutable process-global state."""

    for candidate_stage, provenance in _STRUCTURAL_FAILURE_PROVENANCE:
        if stage == candidate_stage:
            return provenance
    raise AssertionError(f"unsupported structural execution stage: {stage!r}")


def _with_structural_failure_provenance(
    diagnostic: _PmxServiceDiagnostic,
    stage: str,
) -> _PmxServiceDiagnostic:
    """Attach bounded redacted structural execution provenance to one diagnostic."""

    provenance = _structural_failure_provenance(stage)
    if any(key in {"stage", "provenance"} for key, _value in diagnostic.details):
        raise AssertionError(
            "diagnostic already contains structural provenance details"
        )
    return _PmxServiceDiagnostic(
        code=diagnostic.code,
        operation=diagnostic.operation,
        message=diagnostic.message,
        details=diagnostic.details
        + (
            ("stage", stage),
            ("provenance", provenance),
        ),
    )


_STRUCTURAL_TARGET_ORDER = tuple(PmxReferenceTargetKind)


def _structural_target_rank(target_kind: PmxReferenceTargetKind) -> int:
    return _STRUCTURAL_TARGET_ORDER.index(target_kind)


def _structural_target_size(
    document: PmxDocument,
    target_kind: PmxReferenceTargetKind,
) -> int:
    if target_kind is PmxReferenceTargetKind.VERTEX:
        return len(document.vertices)
    if target_kind is PmxReferenceTargetKind.TEXTURE:
        return len(document.texture_paths)
    if target_kind is PmxReferenceTargetKind.MATERIAL:
        return len(document.materials)
    if target_kind is PmxReferenceTargetKind.BONE:
        return len(document.bones)
    if target_kind is PmxReferenceTargetKind.MORPH:
        return len(document.morphs)
    if target_kind is PmxReferenceTargetKind.RIGID_BODY:
        return len(document.rigid_bodies)
    raise AssertionError(f"unsupported structural target kind: {target_kind!r}")


def _structural_insertion_target_count(
    request: PmxStructuralPreviewRequest,
) -> int:
    return sum(
        bool(values)
        for values in (
            request.vertex_insertions,
            request.texture_insertions,
            request.material_insertions,
            request.bone_insertions,
            request.morph_insertions,
            request.rigid_body_insertions,
        )
    )


def _coordinated_position(insertion: object) -> _PmxStructuralInsertPosition:
    position = getattr(insertion, "position")
    source_index = getattr(insertion, "source_index")
    if position == "append":
        return _PmxStructuralInsertPosition.append()
    if position == "insert_before":
        assert source_index is not None
        return _PmxStructuralInsertPosition.insert_before(source_index)
    raise AssertionError("validated insertion exposed unsupported position.")


def _build_coordinated_reference_plan(
    document: PmxDocument,
    request: PmxStructuralPreviewRequest,
) -> _PmxCoordinatedReferencePlan:
    families = (
        (PmxReferenceTargetKind.VERTEX, request.vertex_insertions),
        (PmxReferenceTargetKind.TEXTURE, request.texture_insertions),
        (PmxReferenceTargetKind.MATERIAL, request.material_insertions),
        (PmxReferenceTargetKind.BONE, request.bone_insertions),
        (PmxReferenceTargetKind.MORPH, request.morph_insertions),
        (PmxReferenceTargetKind.RIGID_BODY, request.rigid_body_insertions),
    )
    specs = tuple(
        _PmxCoordinatedInsertionCollectionSpec(
            target_kind=target_kind,
            positions=tuple(_coordinated_position(value) for value in values),
            new_ids=tuple(value.new_id for value in values),
        )
        for target_kind, values in families
        if values
    )
    return _plan_pmx_coordinated_insertion_references(document, specs)


def _resolve_coordinated_reference(
    plan: _PmxCoordinatedReferencePlan,
    value: object,
    target_kind: PmxReferenceTargetKind,
    *,
    allow_sentinel: bool,
    field_name: str,
) -> int:
    if isinstance(value, _PmxStructuralNewReference):
        if value.target_kind != target_kind.value:
            raise ValueError(
                f"{field_name} new reference must target {target_kind.value}."
            )
        return plan.resolve_new_reference(
            target_kind,
            value.new_id,
            field_name=field_name,
        )
    return plan.resolve_source_reference(
        target_kind,
        value,
        allow_sentinel=allow_sentinel,
        field_name=field_name,
    )


def _resolve_vertex_deform(
    plan: _PmxCoordinatedReferencePlan,
    deform: object,
) -> object:
    if isinstance(deform, _PmxStructuralVertexBdef1):
        return replace(
            deform,
            bone_index=_resolve_coordinated_reference(
                plan,
                deform.bone_index,
                PmxReferenceTargetKind.BONE,
                allow_sentinel=True,
                field_name="vertex.deform.bone_index",
            ),
        )
    if isinstance(
        deform,
        (
            _PmxStructuralVertexBdef2,
            _PmxStructuralVertexBdef4,
            _PmxStructuralVertexSdef,
            _PmxStructuralVertexQdef,
        ),
    ):
        return replace(
            deform,
            bone_indices=tuple(
                _resolve_coordinated_reference(
                    plan,
                    value,
                    PmxReferenceTargetKind.BONE,
                    allow_sentinel=True,
                    field_name=f"vertex.deform.bone_indices[{index}]",
                )
                for index, value in enumerate(deform.bone_indices)
            ),
        )
    raise AssertionError("validated vertex insertion exposed unsupported deform.")


def _resolve_material_insertion(
    plan: _PmxCoordinatedReferencePlan,
    insertion: _PmxStructuralMaterialInsertion,
) -> _PmxStructuralMaterialInsertion:
    toon_reference_index = insertion.toon_reference_index
    if insertion.toon_reference_mode == "texture":
        toon_reference_index = _resolve_coordinated_reference(
            plan,
            toon_reference_index,
            PmxReferenceTargetKind.TEXTURE,
            allow_sentinel=True,
            field_name="material.toon_reference_index",
        )
    return replace(
        insertion,
        texture_index=_resolve_coordinated_reference(
            plan,
            insertion.texture_index,
            PmxReferenceTargetKind.TEXTURE,
            allow_sentinel=True,
            field_name="material.texture_index",
        ),
        sphere_texture_index=_resolve_coordinated_reference(
            plan,
            insertion.sphere_texture_index,
            PmxReferenceTargetKind.TEXTURE,
            allow_sentinel=True,
            field_name="material.sphere_texture_index",
        ),
        toon_reference_index=toon_reference_index,
    )


def _resolve_rigid_body_insertion(
    plan: _PmxCoordinatedReferencePlan,
    insertion: _PmxStructuralRigidBodyInsertion,
) -> _PmxStructuralRigidBodyInsertion:
    return replace(
        insertion,
        bone_index=_resolve_coordinated_reference(
            plan,
            insertion.bone_index,
            PmxReferenceTargetKind.BONE,
            allow_sentinel=True,
            field_name="rigid_body.bone_index",
        ),
    )


def _resolve_morph_offset(
    plan: _PmxCoordinatedReferencePlan,
    offset: object,
) -> object:
    if isinstance(
        offset,
        (_PmxStructuralMorphGroupOffset, _PmxStructuralMorphFlipOffset),
    ):
        return offset
    if isinstance(offset, _PmxStructuralMorphVertexOffset):
        return replace(
            offset,
            vertex_index=_resolve_coordinated_reference(
                plan,
                offset.vertex_index,
                PmxReferenceTargetKind.VERTEX,
                allow_sentinel=False,
                field_name="morph.vertex_index",
            ),
        )
    if isinstance(offset, _PmxStructuralMorphBoneOffset):
        return replace(
            offset,
            bone_index=_resolve_coordinated_reference(
                plan,
                offset.bone_index,
                PmxReferenceTargetKind.BONE,
                allow_sentinel=False,
                field_name="morph.bone_index",
            ),
        )
    if isinstance(offset, _PmxStructuralMorphUvOffset):
        return replace(
            offset,
            vertex_index=_resolve_coordinated_reference(
                plan,
                offset.vertex_index,
                PmxReferenceTargetKind.VERTEX,
                allow_sentinel=False,
                field_name="morph.uv.vertex_index",
            ),
        )
    if isinstance(offset, _PmxStructuralMorphMaterialOffset):
        return replace(
            offset,
            material_index=_resolve_coordinated_reference(
                plan,
                offset.material_index,
                PmxReferenceTargetKind.MATERIAL,
                allow_sentinel=True,
                field_name="morph.material_index",
            ),
        )
    if isinstance(offset, _PmxStructuralMorphImpulseOffset):
        return replace(
            offset,
            rigid_body_index=_resolve_coordinated_reference(
                plan,
                offset.rigid_body_index,
                PmxReferenceTargetKind.RIGID_BODY,
                allow_sentinel=False,
                field_name="morph.rigid_body_index",
            ),
        )
    raise AssertionError("validated morph insertion exposed unsupported offset.")


def _build_coordinated_insertion_payloads(
    document: PmxDocument,
    request: PmxStructuralPreviewRequest,
) -> _PmxCoordinatedInsertionPayloads:
    plan = _build_coordinated_reference_plan(document, request)
    resolved_request = replace(
        request,
        material_insertions=tuple(
            _resolve_material_insertion(plan, insertion)
            for insertion in request.material_insertions
        ),
        vertex_insertions=tuple(
            replace(
                insertion,
                deform=_resolve_vertex_deform(plan, insertion.deform),
            )
            for insertion in request.vertex_insertions
        ),
        rigid_body_insertions=tuple(
            _resolve_rigid_body_insertion(plan, insertion)
            for insertion in request.rigid_body_insertions
        ),
        morph_insertions=tuple(
            replace(
                insertion,
                offsets=tuple(
                    _resolve_morph_offset(plan, offset)
                    for offset in insertion.offsets
                ),
            )
            for insertion in request.morph_insertions
        ),
    )
    return _PmxCoordinatedInsertionPayloads(
        reference_plan=plan,
        texture_insertions=(
            _build_texture_insertion_payloads(resolved_request)
            if resolved_request.texture_insertions
            else ()
        ),
        material_insertions=(
            _build_material_insertion_payloads(resolved_request)
            if resolved_request.material_insertions
            else ()
        ),
        bone_insertions=(
            _build_bone_insertion_payloads(resolved_request)
            if resolved_request.bone_insertions
            else ()
        ),
        vertex_insertions=(
            _build_vertex_insertion_payloads(resolved_request)
            if resolved_request.vertex_insertions
            else ()
        ),
        rigid_body_insertions=(
            _build_rigid_body_insertion_payloads(resolved_request)
            if resolved_request.rigid_body_insertions
            else ()
        ),
        morph_insertions=(
            _build_morph_insertion_payloads(resolved_request)
            if resolved_request.morph_insertions
            else ()
        ),
    )


def _build_vertex_insertion_payloads(
    request: PmxStructuralPreviewRequest,
) -> tuple[_PmxVertexInsertionPayload, ...]:
    payloads: list[_PmxVertexInsertionPayload] = []
    for insertion in request.vertex_insertions:
        if insertion.position == "append":
            position = _PmxStructuralInsertPosition.append()
        else:
            assert insertion.position == "insert_before"
            assert insertion.source_index is not None
            position = _PmxStructuralInsertPosition.insert_before(
                insertion.source_index
            )

        deform = insertion.deform
        if isinstance(deform, _PmxStructuralVertexBdef1):
            deform_payload = _PmxVertexBdef1InsertionPayload(
                bone_index=deform.bone_index,
            )
        elif isinstance(deform, _PmxStructuralVertexBdef2):
            deform_payload = _PmxVertexBdef2InsertionPayload(
                bone_indices=deform.bone_indices,
                bone_1_weight=deform.bone_1_weight,
            )
        elif isinstance(deform, _PmxStructuralVertexBdef4):
            deform_payload = _PmxVertexBdef4InsertionPayload(
                bone_indices=deform.bone_indices,
                weights=deform.weights,
            )
        elif isinstance(deform, _PmxStructuralVertexSdef):
            deform_payload = _PmxVertexSdefInsertionPayload(
                bone_indices=deform.bone_indices,
                bone_1_weight=deform.bone_1_weight,
                c=deform.c,
                r0=deform.r0,
                r1=deform.r1,
            )
        elif isinstance(deform, _PmxStructuralVertexQdef):
            deform_payload = _PmxVertexQdefInsertionPayload(
                bone_indices=deform.bone_indices,
                weights=deform.weights,
            )
        else:
            raise AssertionError(
                "validated vertex insertion exposed an unsupported deform type."
            )

        payloads.append(
            _PmxVertexInsertionPayload(
                vertex_position=insertion.vertex_position,
                normal=insertion.normal,
                uv=insertion.uv,
                additional_uvs=insertion.additional_uvs,
                deform=deform_payload,
                edge_scale=insertion.edge_scale,
                position=position,
            )
        )
    return tuple(payloads)


def _build_texture_insertion_payloads(
    request: PmxStructuralPreviewRequest,
) -> tuple[_PmxTextureInsertionPayload, ...]:
    payloads: list[_PmxTextureInsertionPayload] = []
    for insertion in request.texture_insertions:
        if insertion.position == "append":
            position = _PmxStructuralInsertPosition.append()
        else:
            assert insertion.position == "insert_before"
            assert insertion.source_index is not None
            position = _PmxStructuralInsertPosition.insert_before(
                insertion.source_index
            )
        payloads.append(
            _PmxTextureInsertionPayload(
                path=insertion.path,
                position=position,
            )
        )
    return tuple(payloads)


def _build_bone_insertion_payloads(
    request: PmxStructuralPreviewRequest,
) -> tuple[_PmxBoneInsertionPayload, ...]:
    payloads: list[_PmxBoneInsertionPayload] = []
    for insertion in request.bone_insertions:
        if insertion.position == "append":
            position = _PmxStructuralInsertPosition.append()
        else:
            assert insertion.position == "insert_before"
            assert insertion.source_index is not None
            position = _PmxStructuralInsertPosition.insert_before(
                insertion.source_index
            )

        ik_payload = None
        if insertion.ik is not None:
            ik_payload = _PmxBoneIkInsertionPayload(
                target_bone_index=insertion.ik.target_bone_index,
                loop_count=insertion.ik.loop_count,
                angle_limit=insertion.ik.angle_limit,
                links=tuple(
                    _PmxBoneIkLinkInsertionPayload(
                        bone_index=link.bone_index,
                        lower_limit=link.lower_limit,
                        upper_limit=link.upper_limit,
                    )
                    for link in insertion.ik.links
                ),
            )

        payloads.append(
            _PmxBoneInsertionPayload(
                local_name=insertion.local_name,
                universal_name=insertion.universal_name,
                bone_position=insertion.bone_position,
                parent_bone_index=insertion.parent_bone_index,
                transform_layer=insertion.transform_layer,
                rotatable=insertion.rotatable,
                translatable=insertion.translatable,
                visible=insertion.visible,
                enabled=insertion.enabled,
                local_append=insertion.local_append,
                after_physics=insertion.after_physics,
                tail_offset=insertion.tail_offset,
                tail_bone_index=insertion.tail_bone_index,
                inherit_rotation=insertion.inherit_rotation,
                inherit_translation=insertion.inherit_translation,
                inherit_parent_bone_index=insertion.inherit_parent_bone_index,
                inherit_weight=insertion.inherit_weight,
                fixed_axis=insertion.fixed_axis,
                local_axis_x=insertion.local_axis_x,
                local_axis_z=insertion.local_axis_z,
                external_parent_key=insertion.external_parent_key,
                ik=ik_payload,
                position=position,
            )
        )
    return tuple(payloads)


def _build_material_insertion_payloads(
    request: PmxStructuralPreviewRequest,
) -> tuple[_PmxMaterialInsertionPayload, ...]:
    payloads: list[_PmxMaterialInsertionPayload] = []
    for insertion in request.material_insertions:
        if insertion.position == "append":
            position = _PmxStructuralInsertPosition.append()
        else:
            assert insertion.position == "insert_before"
            assert insertion.source_index is not None
            position = _PmxStructuralInsertPosition.insert_before(
                insertion.source_index
            )

        payloads.append(
            _PmxMaterialInsertionPayload(
                local_name=insertion.local_name,
                universal_name=insertion.universal_name,
                memo=insertion.memo,
                texture_index=insertion.texture_index,
                sphere_texture_index=insertion.sphere_texture_index,
                sphere_mode=insertion.sphere_mode,
                toon_reference_mode=insertion.toon_reference_mode,
                toon_reference_index=insertion.toon_reference_index,
                diffuse=insertion.diffuse,
                specular=insertion.specular,
                specular_strength=insertion.specular_strength,
                ambient=insertion.ambient,
                drawing_flags=insertion.drawing_flags,
                edge_color=insertion.edge_color,
                edge_scale=insertion.edge_scale,
                position=position,
            )
        )
    return tuple(payloads)


def _build_morph_insertion_payloads(
    request: PmxStructuralPreviewRequest,
) -> tuple[_PmxMorphInsertionPayload, ...]:
    panel_codes = {
        "system": 0,
        "eyebrow": 1,
        "eye": 2,
        "mouth": 3,
        "other": 4,
    }
    morph_type_codes = {
        "group": 0,
        "vertex": 1,
        "bone": 2,
        "uv": 3,
        "additional_uv_1": 4,
        "additional_uv_2": 5,
        "additional_uv_3": 6,
        "additional_uv_4": 7,
        "material": 8,
        "flip": 9,
        "impulse": 10,
    }

    payloads: list[_PmxMorphInsertionPayload] = []
    for insertion in request.morph_insertions:
        if insertion.position == "append":
            position = _PmxStructuralInsertPosition.append()
        else:
            assert insertion.position == "insert_before"
            assert insertion.source_index is not None
            position = _PmxStructuralInsertPosition.insert_before(
                insertion.source_index
            )

        offsets: list[object] = []
        for offset in insertion.offsets:
            if isinstance(offset, _PmxStructuralMorphGroupOffset):
                offsets.append(
                    _PmxGroupMorphInsertionOffsetPayload(
                        morph_index=offset.morph_index,
                        weight=offset.weight,
                    )
                )
            elif isinstance(offset, _PmxStructuralMorphVertexOffset):
                offsets.append(
                    _PmxVertexMorphInsertionOffsetPayload(
                        vertex_index=offset.vertex_index,
                        translation=offset.translation,
                    )
                )
            elif isinstance(offset, _PmxStructuralMorphBoneOffset):
                offsets.append(
                    _PmxBoneMorphInsertionOffsetPayload(
                        bone_index=offset.bone_index,
                        translation=offset.translation,
                        rotation=offset.rotation,
                    )
                )
            elif isinstance(offset, _PmxStructuralMorphUvOffset):
                offsets.append(
                    _PmxUvMorphInsertionOffsetPayload(
                        vertex_index=offset.vertex_index,
                        uv_offset=offset.uv_offset,
                    )
                )
            elif isinstance(offset, _PmxStructuralMorphMaterialOffset):
                offsets.append(
                    _PmxMaterialMorphInsertionOffsetPayload(
                        material_index=offset.material_index,
                        operation=offset.operation,
                        diffuse=offset.diffuse,
                        specular=offset.specular,
                        specular_strength=offset.specular_strength,
                        ambient=offset.ambient,
                        edge_color=offset.edge_color,
                        edge_scale=offset.edge_scale,
                        texture_tint=offset.texture_tint,
                        sphere_tint=offset.sphere_tint,
                        toon_tint=offset.toon_tint,
                    )
                )
            elif isinstance(offset, _PmxStructuralMorphFlipOffset):
                offsets.append(
                    _PmxFlipMorphInsertionOffsetPayload(
                        morph_index=offset.morph_index,
                        weight=offset.weight,
                    )
                )
            elif isinstance(offset, _PmxStructuralMorphImpulseOffset):
                offsets.append(
                    _PmxImpulseMorphInsertionOffsetPayload(
                        rigid_body_index=offset.rigid_body_index,
                        local=offset.local,
                        velocity=offset.velocity,
                        angular_torque=offset.angular_torque,
                    )
                )
            else:
                raise AssertionError(
                    "validated morph insertion exposed an unsupported offset type."
                )

        payloads.append(
            _PmxMorphInsertionPayload(
                local_name=insertion.local_name,
                universal_name=insertion.universal_name,
                panel=panel_codes[insertion.panel],
                morph_type=morph_type_codes[insertion.morph_type],
                offsets=tuple(offsets),
                position=position,
            )
        )
    return tuple(payloads)


def _build_rigid_body_insertion_payloads(
    request: PmxStructuralPreviewRequest,
) -> tuple[_PmxRigidBodyInsertionPayload, ...]:
    shape_codes = {"sphere": 0, "box": 1, "capsule": 2}
    physics_mode_codes = {
        "bone_follow": 0,
        "physics": 1,
        "physics_with_bone_alignment": 2,
    }
    payloads: list[_PmxRigidBodyInsertionPayload] = []
    for insertion in request.rigid_body_insertions:
        if insertion.position == "append":
            position = _PmxStructuralInsertPosition.append()
        else:
            assert insertion.position == "insert_before"
            assert insertion.source_index is not None
            position = _PmxStructuralInsertPosition.insert_before(
                insertion.source_index
            )
        payloads.append(
            _PmxRigidBodyInsertionPayload(
                local_name=insertion.local_name,
                universal_name=insertion.universal_name,
                bone_index=insertion.bone_index,
                collision_group=insertion.collision_group,
                collision_mask=insertion.collision_mask,
                shape=shape_codes[insertion.shape],
                size=insertion.size,
                body_position=insertion.body_position,
                rotation=insertion.rotation,
                mass=insertion.mass,
                linear_damping=insertion.linear_damping,
                angular_damping=insertion.angular_damping,
                restitution=insertion.restitution,
                friction=insertion.friction,
                physics_mode=physics_mode_codes[insertion.physics_mode],
                position=position,
            )
        )
    return tuple(payloads)


def _build_structural_preview_intent(
    document: PmxDocument,
    request: PmxStructuralPreviewRequest,
) -> PmxStructuralTransformIntent:
    transforms: list[PmxCollectionTransform] = []
    edits = sorted(
        request.collection_edits,
        key=lambda edit: _structural_target_rank(edit.target_kind),
    )
    for edit in edits:
        old_size = _structural_target_size(document, edit.target_kind)
        for old_index in edit.old_indices_in_new_order:
            if old_index >= old_size:
                raise ValueError(
                    f"{edit.target_kind.value} old index {old_index} "
                    f"is out of range for collection size {old_size}."
                )

        targets: list[int | None] = [None] * old_size
        for new_index, old_index in enumerate(edit.old_indices_in_new_order):
            targets[old_index] = new_index

        transforms.append(
            PmxCollectionTransform(
                kind=edit.target_kind,
                remap=PmxIndexRemap(
                    targets=tuple(targets),
                    new_size=len(edit.old_indices_in_new_order),
                ),
            )
        )

    return PmxStructuralTransformIntent(transforms=tuple(transforms))


def preview_structural_edit(
    document: PmxDocument,
    request: PmxStructuralPreviewRequest,
) -> PmxStructuralPreviewResult:
    """Return a deterministic reference-safe structural preview without writing."""

    try:
        if not isinstance(document, PmxDocument):
            raise TypeError("document must be a PmxDocument instance.")
        if not isinstance(request, PmxStructuralPreviewRequest):
            raise TypeError("request must be a PmxStructuralPreviewRequest instance.")
        if _structural_insertion_target_count(request) > 1:
            return PmxStructuralPreviewResult(
                _preview_pmx_coordinated_insertions(
                    document,
                    _build_coordinated_insertion_payloads(document, request),
                )
            )
        if request.vertex_insertions:
            return PmxStructuralPreviewResult(
                _preview_pmx_vertex_insertions(
                    document,
                    _build_vertex_insertion_payloads(request),
                )
            )
        if request.rigid_body_insertions:
            return PmxStructuralPreviewResult(
                _preview_pmx_rigid_body_insertions(
                    document,
                    _build_rigid_body_insertion_payloads(request),
                )
            )
        if request.morph_insertions:
            return PmxStructuralPreviewResult(
                _preview_pmx_morph_insertions(
                    document,
                    _build_morph_insertion_payloads(request),
                )
            )
        if request.bone_insertions:
            return PmxStructuralPreviewResult(
                _preview_pmx_bone_insertions(
                    document,
                    _build_bone_insertion_payloads(request),
                )
            )
        if request.material_insertions:
            return PmxStructuralPreviewResult(
                _preview_pmx_material_insertions(
                    document,
                    _build_material_insertion_payloads(request),
                )
            )
        if request.texture_insertions:
            return PmxStructuralPreviewResult(
                _preview_pmx_texture_insertions(
                    document,
                    _build_texture_insertion_payloads(request),
                )
            )
        intent = _build_structural_preview_intent(document, request)
        return PmxStructuralPreviewResult(
            _preview_pmx_structural_transform(document, intent)
        )
    except Exception as error:
        failure = PmxServiceError(
            diagnostic_from_service_error(
                PmxServiceOperation.PREVIEW_STRUCTURAL_EDIT,
                error,
            )
        )
    raise failure from None


def apply_structural_edit(
    input_path: str | Path,
    output_path: str | Path,
    request: PmxStructuralEditRequest,
    *,
    overwrite: bool = False,
) -> PmxStructuralExecutionResult:
    """Safely execute one bounded structural request against one source snapshot."""

    failure_stage = "service_validation"

    def record_stage(stage: str) -> None:
        nonlocal failure_stage
        _structural_failure_provenance(stage)
        failure_stage = stage

    try:
        if not isinstance(request, PmxStructuralPreviewRequest):
            raise TypeError("request must be a PmxStructuralEditRequest instance.")
        if not isinstance(overwrite, bool):
            raise TypeError("overwrite must be a boolean.")
        coordinated_insertions = _structural_insertion_target_count(request) > 1
        if coordinated_insertions:
            vertex_payloads = ()
            rigid_body_payloads = ()
            morph_payloads = ()
            bone_payloads = ()
            material_payloads = ()
            texture_payloads = ()
        else:
            vertex_payloads = (
                _build_vertex_insertion_payloads(request)
                if request.vertex_insertions
                else ()
            )
            rigid_body_payloads = (
                _build_rigid_body_insertion_payloads(request)
                if request.rigid_body_insertions
                else ()
            )
            morph_payloads = (
                _build_morph_insertion_payloads(request)
                if request.morph_insertions
                else ()
            )
            bone_payloads = (
                _build_bone_insertion_payloads(request)
                if request.bone_insertions
                else ()
            )
            material_payloads = (
                _build_material_insertion_payloads(request)
                if request.material_insertions
                else ()
            )
            texture_payloads = (
                _build_texture_insertion_payloads(request)
                if request.texture_insertions
                else ()
            )

        # Import the internal output kernel only when execution is requested.
        # Merely importing mmd_registry.services therefore remains side-effect-light.
        from mmd_registry.pmx.structural_output import (
            _write_pmx_bone_insertion_transaction,
            _write_pmx_coordinated_insertion_transaction,
            _write_pmx_material_insertion_transaction,
            _write_pmx_morph_insertion_transaction,
            _write_pmx_rigid_body_insertion_transaction,
            _write_pmx_structural_transaction,
            _write_pmx_texture_insertion_transaction,
            _write_pmx_vertex_insertion_transaction,
        )

        failure_stage = "path_resolution"
        if coordinated_insertions:
            result = _write_pmx_coordinated_insertion_transaction(
                input_path,
                output_path,
                lambda document: _build_coordinated_insertion_payloads(
                    document,
                    request,
                ),
                overwrite=overwrite,
                _stage_callback=record_stage,
            )
        elif vertex_payloads:
            result = _write_pmx_vertex_insertion_transaction(
                input_path,
                output_path,
                vertex_payloads,
                overwrite=overwrite,
                _stage_callback=record_stage,
            )
        elif rigid_body_payloads:
            result = _write_pmx_rigid_body_insertion_transaction(
                input_path,
                output_path,
                rigid_body_payloads,
                overwrite=overwrite,
                _stage_callback=record_stage,
            )
        elif morph_payloads:
            result = _write_pmx_morph_insertion_transaction(
                input_path,
                output_path,
                morph_payloads,
                overwrite=overwrite,
                _stage_callback=record_stage,
            )
        elif bone_payloads:
            result = _write_pmx_bone_insertion_transaction(
                input_path,
                output_path,
                bone_payloads,
                overwrite=overwrite,
                _stage_callback=record_stage,
            )
        elif material_payloads:
            result = _write_pmx_material_insertion_transaction(
                input_path,
                output_path,
                material_payloads,
                overwrite=overwrite,
                _stage_callback=record_stage,
            )
        elif texture_payloads:
            result = _write_pmx_texture_insertion_transaction(
                input_path,
                output_path,
                texture_payloads,
                overwrite=overwrite,
                _stage_callback=record_stage,
            )
        else:
            result = _write_pmx_structural_transaction(
                input_path,
                output_path,
                lambda document: _build_structural_preview_intent(document, request),
                overwrite=overwrite,
                _stage_callback=record_stage,
            )
        return PmxStructuralExecutionResult(result)
    except Exception as error:
        diagnostic = diagnostic_from_service_error(
            PmxServiceOperation.APPLY_STRUCTURAL_EDIT,
            error,
        )
        failure = PmxServiceError(
            _with_structural_failure_provenance(diagnostic, failure_stage)
        )
    raise failure from None


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
    """Return a deterministic result or raise one structured service failure."""

    try:
        if not isinstance(document, PmxDocument):
            raise TypeError("document must be a PmxDocument instance.")
        try:
            validate_pmx_document(document)
        except PmxValidationError as error:
            return PmxDocumentValidationResult(issues=(error.issue,))
        return PmxDocumentValidationResult()
    except Exception as error:
        failure = PmxServiceError(
            diagnostic_from_service_error(
                PmxServiceOperation.VALIDATE_DOCUMENT,
                error,
            )
        )
    raise failure from None


def analyze_references(document: PmxDocument) -> PmxReferenceAnalysisResult:
    """Extract one deterministic reference snapshot without prevalidation."""

    try:
        if not isinstance(document, PmxDocument):
            raise TypeError("document must be a PmxDocument instance.")
        graph = extract_pmx_reference_graph(document)
        return PmxReferenceAnalysisResult(
            graph=graph,
            diagnostics=diagnose_reference_graph(graph),
        )
    except Exception as error:
        failure = PmxServiceError(
            diagnostic_from_service_error(
                PmxServiceOperation.ANALYZE_REFERENCES,
                error,
            )
        )
    raise failure from None


def analyze_reference_node(
    analysis: PmxReferenceAnalysisResult,
    node: PmxReferenceNode,
) -> PmxReferenceImpact:
    """Return conservative direct impact from an existing analysis snapshot."""

    try:
        if not isinstance(analysis, PmxReferenceAnalysisResult):
            raise TypeError(
                "analysis must be a PmxReferenceAnalysisResult instance."
            )
        if not isinstance(node, PmxReferenceNode):
            raise TypeError("node must be a PmxReferenceNode instance.")
        return analyze_reference_impact(analysis.graph, node)
    except Exception as error:
        failure = PmxServiceError(
            diagnostic_from_service_error(
                PmxServiceOperation.ANALYZE_REFERENCE_NODE,
                error,
            )
        )
    raise failure from None


def preview_edit(source_bytes: bytes, plan: PmxEditPlan) -> PmxEditPreview:
    """Return a verified edit preview or one structured service failure."""

    try:
        return dry_run_pmx_edit(source_bytes, plan)
    except Exception as error:
        failure = PmxServiceError(
            diagnostic_from_service_error(
                PmxServiceOperation.PREVIEW_EDIT,
                error,
            )
        )
    raise failure from None


def apply_edit(
    input_path: str | Path,
    output_path: str | Path,
    plan: PmxEditPlan,
    *,
    overwrite: bool = False,
) -> PmxEditWriteResult:
    """Safely write one verified edit or raise a structured service failure."""

    try:
        return write_pmx_edit(
            input_path,
            output_path,
            plan,
            overwrite=overwrite,
        )
    except Exception as error:
        failure = PmxServiceError(
            diagnostic_from_service_error(
                PmxServiceOperation.APPLY_EDIT,
                error,
            )
        )
    raise failure from None


__all__ = (
    "PmxDocumentMetadata",
    "PmxDocumentValidationResult",
    "apply_edit",
    "get_capabilities",
    "inspect_document",
    "load_document",
    "preview_edit",
    "validate_document",
    "PmxReferenceAnalysisResult",
    "PmxReferenceDiagnostic",
    "PmxReferenceDiagnosticCode",
    "PmxReferenceImpact",
    "PmxReferenceNode",
    "PmxReferenceTargetKind",
    "analyze_reference_node",
    "analyze_references",
    "PmxStructuralCollectionEdit",
    "PmxStructuralPreviewRequest",
    "PmxStructuralPreviewResult",
    "preview_structural_edit",
    "PmxStructuralEditRequest",
    "PmxStructuralExecutionResult",
    "apply_structural_edit",
)
