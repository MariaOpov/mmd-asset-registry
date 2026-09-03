"""Read-only bounded catalog projections for structural plan authoring."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final, TypeAlias

from mmd_registry.pmx.document import PmxDocument
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind


PMX_STRUCTURAL_AUTHORING_CATALOG_DEFAULT_LIMIT: Final[int] = 100
PMX_STRUCTURAL_AUTHORING_CATALOG_MAX_LIMIT: Final[int] = 1000


def _plain_int(value: object, field_name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be an integer.")
    return value


def _nonnegative_int(value: object, field_name: str) -> int:
    value = _plain_int(value, field_name)
    if value < 0:
        raise ValueError(f"{field_name} cannot be negative.")
    return value


def _text(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string.")
    return value


@dataclass(frozen=True, slots=True)
class PmxStructuralAuthoringVertexCatalogEntry:
    source_index: int
    position: tuple[float, float, float]
    deform_type: int

    def __post_init__(self) -> None:
        _nonnegative_int(self.source_index, "source_index")
        if type(self.position) is not tuple or len(self.position) != 3:
            raise TypeError("position must be a three-float tuple.")
        if not all(type(item) is float for item in self.position):
            raise TypeError("position must contain only floats.")
        deform_type = _nonnegative_int(self.deform_type, "deform_type")
        if deform_type > 4:
            raise ValueError("deform_type must be a value from 0 through 4.")

    def to_dict(self) -> dict[str, object]:
        return {
            "source_index": self.source_index,
            "position": list(self.position),
            "deform_type": self.deform_type,
        }


@dataclass(frozen=True, slots=True)
class PmxStructuralAuthoringTextureCatalogEntry:
    source_index: int
    path: str

    def __post_init__(self) -> None:
        _nonnegative_int(self.source_index, "source_index")
        _text(self.path, "path")

    def to_dict(self) -> dict[str, object]:
        return {"source_index": self.source_index, "path": self.path}


@dataclass(frozen=True, slots=True)
class PmxStructuralAuthoringMaterialCatalogEntry:
    source_index: int
    local_name: str
    universal_name: str
    texture_index: int
    sphere_texture_index: int
    surface_index_count: int

    def __post_init__(self) -> None:
        _nonnegative_int(self.source_index, "source_index")
        _text(self.local_name, "local_name")
        _text(self.universal_name, "universal_name")
        for field_name in ("texture_index", "sphere_texture_index"):
            value = _plain_int(getattr(self, field_name), field_name)
            if value < -1:
                raise ValueError(f"{field_name} cannot be smaller than -1.")
        _nonnegative_int(self.surface_index_count, "surface_index_count")

    def to_dict(self) -> dict[str, object]:
        return {
            "source_index": self.source_index,
            "local_name": self.local_name,
            "universal_name": self.universal_name,
            "texture_index": self.texture_index,
            "sphere_texture_index": self.sphere_texture_index,
            "surface_index_count": self.surface_index_count,
        }


@dataclass(frozen=True, slots=True)
class PmxStructuralAuthoringBoneCatalogEntry:
    source_index: int
    local_name: str
    universal_name: str
    parent_bone_index: int
    position: tuple[float, float, float]
    flag_names: tuple[str, ...]

    def __post_init__(self) -> None:
        _nonnegative_int(self.source_index, "source_index")
        _text(self.local_name, "local_name")
        _text(self.universal_name, "universal_name")
        parent = _plain_int(self.parent_bone_index, "parent_bone_index")
        if parent < -1:
            raise ValueError("parent_bone_index cannot be smaller than -1.")
        if type(self.position) is not tuple or len(self.position) != 3:
            raise TypeError("position must be a three-float tuple.")
        if not all(type(item) is float for item in self.position):
            raise TypeError("position must contain only floats.")
        if type(self.flag_names) is not tuple:
            raise TypeError("flag_names must be a tuple.")
        for value in self.flag_names:
            _text(value, "flag_name")

    def to_dict(self) -> dict[str, object]:
        return {
            "source_index": self.source_index,
            "local_name": self.local_name,
            "universal_name": self.universal_name,
            "parent_bone_index": self.parent_bone_index,
            "position": list(self.position),
            "flag_names": list(self.flag_names),
        }


@dataclass(frozen=True, slots=True)
class PmxStructuralAuthoringMorphCatalogEntry:
    source_index: int
    local_name: str
    universal_name: str
    panel_name: str
    morph_type_name: str
    offset_count: int

    def __post_init__(self) -> None:
        _nonnegative_int(self.source_index, "source_index")
        _text(self.local_name, "local_name")
        _text(self.universal_name, "universal_name")
        _text(self.panel_name, "panel_name")
        _text(self.morph_type_name, "morph_type_name")
        _nonnegative_int(self.offset_count, "offset_count")

    def to_dict(self) -> dict[str, object]:
        return {
            "source_index": self.source_index,
            "local_name": self.local_name,
            "universal_name": self.universal_name,
            "panel_name": self.panel_name,
            "morph_type_name": self.morph_type_name,
            "offset_count": self.offset_count,
        }


@dataclass(frozen=True, slots=True)
class PmxStructuralAuthoringRigidBodyCatalogEntry:
    source_index: int
    local_name: str
    universal_name: str
    bone_index: int
    shape_name: str
    physics_mode_name: str

    def __post_init__(self) -> None:
        _nonnegative_int(self.source_index, "source_index")
        _text(self.local_name, "local_name")
        _text(self.universal_name, "universal_name")
        bone_index = _plain_int(self.bone_index, "bone_index")
        if bone_index < -1:
            raise ValueError("bone_index cannot be smaller than -1.")
        _text(self.shape_name, "shape_name")
        _text(self.physics_mode_name, "physics_mode_name")

    def to_dict(self) -> dict[str, object]:
        return {
            "source_index": self.source_index,
            "local_name": self.local_name,
            "universal_name": self.universal_name,
            "bone_index": self.bone_index,
            "shape_name": self.shape_name,
            "physics_mode_name": self.physics_mode_name,
        }


PmxStructuralAuthoringCatalogEntry: TypeAlias = (
    PmxStructuralAuthoringVertexCatalogEntry
    | PmxStructuralAuthoringTextureCatalogEntry
    | PmxStructuralAuthoringMaterialCatalogEntry
    | PmxStructuralAuthoringBoneCatalogEntry
    | PmxStructuralAuthoringMorphCatalogEntry
    | PmxStructuralAuthoringRigidBodyCatalogEntry
)


@dataclass(frozen=True, slots=True)
class PmxStructuralAuthoringCatalogSummary:
    counts: tuple[tuple[PmxReferenceTargetKind, int], ...]

    def __post_init__(self) -> None:
        if type(self.counts) is not tuple:
            raise TypeError("counts must be a tuple.")
        expected = tuple(PmxReferenceTargetKind)
        actual: list[PmxReferenceTargetKind] = []
        for item in self.counts:
            if type(item) is not tuple or len(item) != 2:
                raise TypeError("each count must be one target-kind/count tuple.")
            target_kind, count = item
            if not isinstance(target_kind, PmxReferenceTargetKind):
                raise TypeError("count target kind must be PmxReferenceTargetKind.")
            _nonnegative_int(count, "count")
            actual.append(target_kind)
        if tuple(actual) != expected:
            raise ValueError(
                "counts must contain all target kinds exactly once in canonical order."
            )

    def count_for(self, target_kind: PmxReferenceTargetKind) -> int:
        if not isinstance(target_kind, PmxReferenceTargetKind):
            raise TypeError("target_kind must be PmxReferenceTargetKind.")
        return dict(self.counts)[target_kind]

    def to_dict(self) -> dict[str, object]:
        return {
            "counts": {
                target_kind.value: count
                for target_kind, count in self.counts
            }
        }


_ENTRY_TYPE_BY_TARGET: Final = {
    PmxReferenceTargetKind.VERTEX: PmxStructuralAuthoringVertexCatalogEntry,
    PmxReferenceTargetKind.TEXTURE: PmxStructuralAuthoringTextureCatalogEntry,
    PmxReferenceTargetKind.MATERIAL: PmxStructuralAuthoringMaterialCatalogEntry,
    PmxReferenceTargetKind.BONE: PmxStructuralAuthoringBoneCatalogEntry,
    PmxReferenceTargetKind.MORPH: PmxStructuralAuthoringMorphCatalogEntry,
    PmxReferenceTargetKind.RIGID_BODY: PmxStructuralAuthoringRigidBodyCatalogEntry,
}


@dataclass(frozen=True, slots=True)
class PmxStructuralAuthoringCatalogPage:
    target_kind: PmxReferenceTargetKind
    total_count: int
    offset: int
    limit: int
    entries: tuple[PmxStructuralAuthoringCatalogEntry, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.target_kind, PmxReferenceTargetKind):
            raise TypeError("target_kind must be PmxReferenceTargetKind.")
        _nonnegative_int(self.total_count, "total_count")
        _nonnegative_int(self.offset, "offset")
        limit = _plain_int(self.limit, "limit")
        if not 1 <= limit <= PMX_STRUCTURAL_AUTHORING_CATALOG_MAX_LIMIT:
            raise ValueError(
                "limit must be between 1 and "
                f"{PMX_STRUCTURAL_AUTHORING_CATALOG_MAX_LIMIT}."
            )
        if type(self.entries) is not tuple:
            raise TypeError("entries must be a tuple.")
        expected_type = _ENTRY_TYPE_BY_TARGET[self.target_kind]
        if not all(isinstance(entry, expected_type) for entry in self.entries):
            raise TypeError("entries must match target_kind.")
        if len(self.entries) > self.limit:
            raise ValueError("entries cannot exceed limit.")

    @property
    def returned_count(self) -> int:
        return len(self.entries)

    def to_dict(self) -> dict[str, object]:
        return {
            "target_kind": self.target_kind.value,
            "total_count": self.total_count,
            "offset": self.offset,
            "limit": self.limit,
            "returned_count": self.returned_count,
            "entries": [entry.to_dict() for entry in self.entries],
        }


class PmxStructuralAuthoringCatalogServiceOperation(StrEnum):
    SUMMARY = "summarize_structural_authoring_catalog"
    INSPECT = "inspect_structural_authoring_catalog"


class PmxStructuralAuthoringCatalogServiceDiagnosticCode(StrEnum):
    INVALID_ARGUMENT = "invalid_argument"
    INTERNAL_ERROR = "service_internal_error"


@dataclass(frozen=True, slots=True)
class PmxStructuralAuthoringCatalogServiceDiagnostic:
    code: PmxStructuralAuthoringCatalogServiceDiagnosticCode
    operation: PmxStructuralAuthoringCatalogServiceOperation
    message: str

    def __post_init__(self) -> None:
        if not isinstance(
            self.code,
            PmxStructuralAuthoringCatalogServiceDiagnosticCode,
        ):
            raise TypeError("code must be a catalog diagnostic code.")
        if not isinstance(
            self.operation,
            PmxStructuralAuthoringCatalogServiceOperation,
        ):
            raise TypeError("operation must be a catalog service operation.")
        if type(self.message) is not str or not self.message:
            raise ValueError("message must be a non-empty string.")

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code.value,
            "operation": self.operation.value,
            "message": self.message,
        }


class PmxStructuralAuthoringCatalogServiceError(RuntimeError):
    def __init__(
        self,
        diagnostic: PmxStructuralAuthoringCatalogServiceDiagnostic,
    ) -> None:
        if not isinstance(
            diagnostic,
            PmxStructuralAuthoringCatalogServiceDiagnostic,
        ):
            raise TypeError("diagnostic must be a catalog diagnostic.")
        self.diagnostic = diagnostic
        super().__init__(diagnostic.message)

    def to_dict(self) -> dict[str, object]:
        return self.diagnostic.to_dict()


def _service_error(
    operation: PmxStructuralAuthoringCatalogServiceOperation,
    error: Exception,
) -> PmxStructuralAuthoringCatalogServiceError:
    if isinstance(error, (TypeError, ValueError)):
        diagnostic = PmxStructuralAuthoringCatalogServiceDiagnostic(
            code=PmxStructuralAuthoringCatalogServiceDiagnosticCode.INVALID_ARGUMENT,
            operation=operation,
            message="Invalid structural authoring catalog input.",
        )
    else:
        diagnostic = PmxStructuralAuthoringCatalogServiceDiagnostic(
            code=PmxStructuralAuthoringCatalogServiceDiagnosticCode.INTERNAL_ERROR,
            operation=operation,
            message="Unexpected structural authoring catalog failure.",
        )
    return PmxStructuralAuthoringCatalogServiceError(diagnostic)


def _document(value: object) -> PmxDocument:
    if not isinstance(value, PmxDocument):
        raise TypeError("document must be a PmxDocument instance.")
    return value


def _summary(document: PmxDocument) -> PmxStructuralAuthoringCatalogSummary:
    return PmxStructuralAuthoringCatalogSummary(
        counts=(
            (PmxReferenceTargetKind.VERTEX, len(document.vertices)),
            (PmxReferenceTargetKind.TEXTURE, len(document.texture_paths)),
            (PmxReferenceTargetKind.MATERIAL, len(document.materials)),
            (PmxReferenceTargetKind.BONE, len(document.bones)),
            (PmxReferenceTargetKind.MORPH, len(document.morphs)),
            (PmxReferenceTargetKind.RIGID_BODY, len(document.rigid_bodies)),
        )
    )


def summarize_structural_authoring_catalog(
    document: PmxDocument,
) -> PmxStructuralAuthoringCatalogSummary:
    """Return only six collection counts; perform no filesystem work."""

    try:
        return _summary(_document(document))
    except Exception as error:
        failure = _service_error(
            PmxStructuralAuthoringCatalogServiceOperation.SUMMARY,
            error,
        )
    raise failure from None


def inspect_structural_authoring_catalog(
    document: PmxDocument,
    target_kind: PmxReferenceTargetKind,
    *,
    offset: int = 0,
    limit: int = PMX_STRUCTURAL_AUTHORING_CATALOG_DEFAULT_LIMIT,
) -> PmxStructuralAuthoringCatalogPage:
    """Return one bounded source-index-ordered read-only catalog page."""

    try:
        document = _document(document)
        if not isinstance(target_kind, PmxReferenceTargetKind):
            raise TypeError("target_kind must be PmxReferenceTargetKind.")
        offset = _nonnegative_int(offset, "offset")
        limit = _plain_int(limit, "limit")
        if not 1 <= limit <= PMX_STRUCTURAL_AUTHORING_CATALOG_MAX_LIMIT:
            raise ValueError(
                "limit must be between 1 and "
                f"{PMX_STRUCTURAL_AUTHORING_CATALOG_MAX_LIMIT}."
            )

        total_count = _summary(document).count_for(target_kind)
        start = min(offset, total_count)
        stop = min(start + limit, total_count)

        if target_kind is PmxReferenceTargetKind.VERTEX:
            entries = tuple(
                PmxStructuralAuthoringVertexCatalogEntry(
                    source_index=index,
                    position=vertex.position,
                    deform_type=vertex.deform.deform_type,
                )
                for index, vertex in enumerate(
                    document.vertices[start:stop],
                    start=start,
                )
            )
        elif target_kind is PmxReferenceTargetKind.TEXTURE:
            entries = tuple(
                PmxStructuralAuthoringTextureCatalogEntry(
                    source_index=index,
                    path=path,
                )
                for index, path in enumerate(
                    document.texture_paths[start:stop],
                    start=start,
                )
            )
        elif target_kind is PmxReferenceTargetKind.MATERIAL:
            entries = tuple(
                PmxStructuralAuthoringMaterialCatalogEntry(
                    source_index=index,
                    local_name=material.local_name,
                    universal_name=material.universal_name,
                    texture_index=material.texture_index,
                    sphere_texture_index=material.sphere_texture_index,
                    surface_index_count=material.surface_index_count,
                )
                for index, material in enumerate(
                    document.materials[start:stop],
                    start=start,
                )
            )
        elif target_kind is PmxReferenceTargetKind.BONE:
            entries = tuple(
                PmxStructuralAuthoringBoneCatalogEntry(
                    source_index=index,
                    local_name=bone.local_name,
                    universal_name=bone.universal_name,
                    parent_bone_index=bone.parent_bone_index,
                    position=bone.position,
                    flag_names=bone.flag_names,
                )
                for index, bone in enumerate(
                    document.bones[start:stop],
                    start=start,
                )
            )
        elif target_kind is PmxReferenceTargetKind.MORPH:
            entries = tuple(
                PmxStructuralAuthoringMorphCatalogEntry(
                    source_index=index,
                    local_name=morph.local_name,
                    universal_name=morph.universal_name,
                    panel_name=morph.panel_name,
                    morph_type_name=morph.morph_type_name,
                    offset_count=len(morph.offsets),
                )
                for index, morph in enumerate(
                    document.morphs[start:stop],
                    start=start,
                )
            )
        else:
            entries = tuple(
                PmxStructuralAuthoringRigidBodyCatalogEntry(
                    source_index=index,
                    local_name=rigid_body.local_name,
                    universal_name=rigid_body.universal_name,
                    bone_index=rigid_body.bone_index,
                    shape_name=rigid_body.shape_name,
                    physics_mode_name=rigid_body.physics_mode_name,
                )
                for index, rigid_body in enumerate(
                    document.rigid_bodies[start:stop],
                    start=start,
                )
            )

        return PmxStructuralAuthoringCatalogPage(
            target_kind=target_kind,
            total_count=total_count,
            offset=offset,
            limit=limit,
            entries=entries,
        )
    except Exception as error:
        failure = _service_error(
            PmxStructuralAuthoringCatalogServiceOperation.INSPECT,
            error,
        )
    raise failure from None


__all__ = (
    "PMX_STRUCTURAL_AUTHORING_CATALOG_DEFAULT_LIMIT",
    "PMX_STRUCTURAL_AUTHORING_CATALOG_MAX_LIMIT",
    "PmxStructuralAuthoringVertexCatalogEntry",
    "PmxStructuralAuthoringTextureCatalogEntry",
    "PmxStructuralAuthoringMaterialCatalogEntry",
    "PmxStructuralAuthoringBoneCatalogEntry",
    "PmxStructuralAuthoringMorphCatalogEntry",
    "PmxStructuralAuthoringRigidBodyCatalogEntry",
    "PmxStructuralAuthoringCatalogEntry",
    "PmxStructuralAuthoringCatalogSummary",
    "PmxStructuralAuthoringCatalogPage",
    "PmxStructuralAuthoringCatalogServiceOperation",
    "PmxStructuralAuthoringCatalogServiceDiagnosticCode",
    "PmxStructuralAuthoringCatalogServiceDiagnostic",
    "PmxStructuralAuthoringCatalogServiceError",
    "summarize_structural_authoring_catalog",
    "inspect_structural_authoring_catalog",
)
