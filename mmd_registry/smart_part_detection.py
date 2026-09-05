"""Deterministic read-only Smart Part semantic detection.

The v0.9.5.2 detector consumes immutable structural-authoring catalog DTOs and
emits immutable SmartPart values. It is lexical and conservative only: no
confidence, fuzzy matching, statistical inference, AI, transaction planning,
preview, apply, writing, remapping, or CLI authority.

Frozen contract:
- input is an exact tuple of immutable structural-authoring catalog entries;
- output is an exact tuple of SmartPart values;
- output part order follows SmartPartKind declaration order;
- semantic text normalization is NFKC, Unicode-whitespace collapse, casefold;
- lexical matching is normalized exact-alias matching only;
- empty or whitespace-only names produce no evidence;
- texture lexical scope is basename stem only, never parent-directory inference;
- unknown labels do not block a known exact match on another name field;
- conflicting exact kinds on one source entity produce no classification for
  that entity rather than selecting a winner;
- duplicate exact evidence is removed before SmartPart construction;
- evidence reasons use the stable machine form
  "<source_kind>.<field_name>:exact_alias:<part_kind>";
- vertex and rigid-body DTOs are accepted by the boundary but have no lexical
  classification authority in v0.9.5.2.

CP06 makes same-source ambiguity handling explicit. A named source entity is
classified only when all of its recognized exact-name fields agree on one
SmartPartKind. Conflicting recognized kinds contribute zero evidence; unknown
fields do not block an otherwise unique recognized kind. No local-name or
universal-name priority, scoring, confidence, or heuristic winner exists.
"""

from __future__ import annotations

import unicodedata
from typing import Final, TypeAlias

from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringBoneCatalogEntry,
    PmxStructuralAuthoringCatalogEntry,
    PmxStructuralAuthoringMaterialCatalogEntry,
    PmxStructuralAuthoringMorphCatalogEntry,
    PmxStructuralAuthoringRigidBodyCatalogEntry,
    PmxStructuralAuthoringTextureCatalogEntry,
    PmxStructuralAuthoringVertexCatalogEntry,
)
from mmd_registry.smart_parts import (
    SmartPart,
    SmartPartEvidence,
    SmartPartEvidenceKind,
    SmartPartKind,
)


SmartPartDetectionEntry: TypeAlias = PmxStructuralAuthoringCatalogEntry
_ExactAliasTable: TypeAlias = tuple[
    tuple[SmartPartKind, tuple[str, ...]],
    ...,
]
_NormalizedAliasIndex: TypeAlias = tuple[tuple[str, SmartPartKind], ...]

_SUPPORTED_ENTRY_TYPES: Final[tuple[type[object], ...]] = (
    PmxStructuralAuthoringVertexCatalogEntry,
    PmxStructuralAuthoringTextureCatalogEntry,
    PmxStructuralAuthoringMaterialCatalogEntry,
    PmxStructuralAuthoringBoneCatalogEntry,
    PmxStructuralAuthoringMorphCatalogEntry,
    PmxStructuralAuthoringRigidBodyCatalogEntry,
)

_SMART_PART_ORDER: Final[tuple[SmartPartKind, ...]] = tuple(SmartPartKind)

_NORMALIZATION_CONTRACT: Final[str] = "NFKC+unicode-whitespace-collapse+casefold"
_MATCH_CONTRACT: Final[str] = "normalized-exact-alias-only"
_TEXTURE_LEXICAL_SCOPE: Final[str] = "basename-stem-only"
_EMPTY_NAME_POLICY: Final[str] = "ignore"
_UNKNOWN_NAME_POLICY: Final[str] = "does-not-block-known-exact-match"
_CONFLICT_POLICY: Final[str] = "same-source-conflict-no-classification"
_DUPLICATE_EVIDENCE_POLICY: Final[str] = "deduplicate-exact-before-smart-part"
_REASON_PATTERN: Final[str] = "<source_kind>.<field_name>:exact_alias:<part_kind>"
_VERTEX_POLICY: Final[str] = "accepted-no-lexical-authority-v0.9.5.2"
_RIGID_BODY_POLICY: Final[str] = "accepted-no-lexical-authority-v0.9.5.2"

_GENERIC_EXACT_ALIASES: Final[_ExactAliasTable] = (
    (SmartPartKind.EYES, ("eyes",)),
    (SmartPartKind.HAIR, ("hair",)),
    (SmartPartKind.FACE, ("face",)),
    (SmartPartKind.SKIN, ("skin",)),
    (SmartPartKind.CHEST, ("chest",)),
    (SmartPartKind.UPPER_BODY, ("upper_body", "upper body")),
    (SmartPartKind.LOWER_BODY, ("lower_body", "lower body")),
    (SmartPartKind.ARMS, ("arms",)),
    (SmartPartKind.HANDS, ("hands",)),
    (SmartPartKind.LEGS, ("legs",)),
    (SmartPartKind.FEET, ("feet",)),
    (SmartPartKind.CLOTHING, ("clothing",)),
    (SmartPartKind.SHOES, ("shoes",)),
    (SmartPartKind.ACCESSORIES, ("accessories",)),
    (SmartPartKind.MATERIALS, ("materials",)),
)

_MATERIAL_EXACT_ALIASES: Final[_ExactAliasTable] = (
    (SmartPartKind.EYES, ("eyes", "eye", "目", "瞳")),
    (SmartPartKind.HAIR, ("hair", "髪")),
    (SmartPartKind.FACE, ("face", "顔")),
    (SmartPartKind.SKIN, ("skin", "肌")),
    (SmartPartKind.CHEST, ("chest", "胸")),
    (SmartPartKind.UPPER_BODY, ("upper body", "upper_body", "上半身")),
    (SmartPartKind.LOWER_BODY, ("lower body", "lower_body", "下半身")),
    (SmartPartKind.ARMS, ("arms", "arm", "腕")),
    (SmartPartKind.HANDS, ("hands", "hand", "手")),
    (SmartPartKind.LEGS, ("legs", "leg", "脚")),
    (SmartPartKind.FEET, ("feet", "foot", "足首")),
    (SmartPartKind.CLOTHING, ("clothing", "clothes", "服")),
    (SmartPartKind.SHOES, ("shoes", "shoe", "靴")),
    (
        SmartPartKind.ACCESSORIES,
        ("accessories", "accessory", "アクセサリー", "アクセサリ"),
    ),
    (SmartPartKind.MATERIALS, ("materials", "material", "材質")),
)

_BONE_EXACT_ALIASES: Final[_ExactAliasTable] = (
    (
        SmartPartKind.EYES,
        ("eyes", "eye", "左目", "右目", "left eye", "right eye"),
    ),
    (SmartPartKind.HAIR, ("hair", "髪")),
    (SmartPartKind.FACE, ("face", "顔")),
    (SmartPartKind.CHEST, ("chest", "胸")),
    (SmartPartKind.UPPER_BODY, ("upper body", "upper_body", "上半身")),
    (SmartPartKind.LOWER_BODY, ("lower body", "lower_body", "下半身")),
    (
        SmartPartKind.ARMS,
        ("arms", "arm", "左腕", "右腕", "left arm", "right arm"),
    ),
    (
        SmartPartKind.HANDS,
        (
            "hands",
            "hand",
            "左手",
            "右手",
            "left hand",
            "right hand",
            "左手首",
            "右手首",
            "left wrist",
            "right wrist",
        ),
    ),
    (
        SmartPartKind.LEGS,
        (
            "legs",
            "leg",
            "左脚",
            "右脚",
            "left leg",
            "right leg",
            "左ひざ",
            "右ひざ",
            "左膝",
            "右膝",
            "left knee",
            "right knee",
        ),
    ),
    (
        SmartPartKind.FEET,
        (
            "feet",
            "foot",
            "左足首",
            "右足首",
            "left ankle",
            "right ankle",
            "left foot",
            "right foot",
            "左つま先",
            "右つま先",
            "left toe",
            "right toe",
        ),
    ),
)

_MORPH_EXACT_ALIASES: Final[_ExactAliasTable] = (
    (
        SmartPartKind.EYES,
        (
            "eyes",
            "eye",
            "blink",
            "まばたき",
            "wink",
            "ウィンク",
            "ウィンク右",
            "ウィンク左",
        ),
    ),
    (SmartPartKind.FACE, ("face", "顔", "smile", "笑顔", "笑い")),
)

_TEXTURE_EXACT_ALIASES: Final[_ExactAliasTable] = (
    (SmartPartKind.EYES, ("eyes", "eye")),
    (SmartPartKind.HAIR, ("hair",)),
    (SmartPartKind.FACE, ("face",)),
    (SmartPartKind.SKIN, ("skin",)),
    (SmartPartKind.CHEST, ("chest",)),
    (SmartPartKind.UPPER_BODY, ("upper body", "upper_body")),
    (SmartPartKind.LOWER_BODY, ("lower body", "lower_body")),
    (SmartPartKind.ARMS, ("arms", "arm")),
    (SmartPartKind.HANDS, ("hands", "hand")),
    (SmartPartKind.LEGS, ("legs", "leg")),
    (SmartPartKind.FEET, ("feet", "foot")),
    (SmartPartKind.CLOTHING, ("clothing", "clothes")),
    (SmartPartKind.SHOES, ("shoes", "shoe")),
    (SmartPartKind.ACCESSORIES, ("accessories", "accessory")),
    (SmartPartKind.MATERIALS, ("materials", "material")),
)


def _normalize_semantic_text(value: str) -> str:
    if type(value) is not str:
        raise TypeError("semantic text must be a string.")
    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.split()).casefold()


def _build_normalized_alias_index(
    table: _ExactAliasTable,
) -> _NormalizedAliasIndex:
    if type(table) is not tuple:
        raise TypeError("alias table must be a tuple.")

    alias_to_kind: dict[str, SmartPartKind] = {}
    for item in table:
        if type(item) is not tuple or len(item) != 2:
            raise TypeError("alias table items must be kind/aliases tuples.")
        kind, aliases = item
        if not isinstance(kind, SmartPartKind):
            raise TypeError("alias table kind must be a SmartPartKind value.")
        if type(aliases) is not tuple:
            raise TypeError("aliases must be a tuple.")

        for alias in aliases:
            normalized = _normalize_semantic_text(alias)
            if not normalized:
                raise ValueError("aliases must normalize to non-empty text.")
            existing = alias_to_kind.get(normalized)
            if existing is not None and existing is not kind:
                raise ValueError(
                    "normalized alias cannot identify multiple Smart Part kinds."
                )
            alias_to_kind[normalized] = kind

    return tuple(sorted(alias_to_kind.items(), key=lambda item: item[0]))


_NORMALIZED_ALIAS_INDEX: Final[_NormalizedAliasIndex] = (
    _build_normalized_alias_index(_GENERIC_EXACT_ALIASES)
)
_MATERIAL_ALIAS_INDEX: Final[_NormalizedAliasIndex] = (
    _build_normalized_alias_index(_MATERIAL_EXACT_ALIASES)
)
_BONE_ALIAS_INDEX: Final[_NormalizedAliasIndex] = (
    _build_normalized_alias_index(_BONE_EXACT_ALIASES)
)
_MORPH_ALIAS_INDEX: Final[_NormalizedAliasIndex] = (
    _build_normalized_alias_index(_MORPH_EXACT_ALIASES)
)
_TEXTURE_ALIAS_INDEX: Final[_NormalizedAliasIndex] = (
    _build_normalized_alias_index(_TEXTURE_EXACT_ALIASES)
)


def _exact_alias_kind_from_index(
    value: str,
    index: _NormalizedAliasIndex,
) -> SmartPartKind | None:
    normalized = _normalize_semantic_text(value)
    if not normalized:
        return None

    for alias, kind in index:
        if normalized == alias:
            return kind
    return None


def _exact_alias_kind(value: str) -> SmartPartKind | None:
    return _exact_alias_kind_from_index(value, _NORMALIZED_ALIAS_INDEX)


def _texture_basename_stem(path: str) -> str:
    if type(path) is not str:
        raise TypeError("texture path must be a string.")
    normalized_separators = path.replace("\\", "/")
    basename = normalized_separators.rsplit("/", 1)[-1]
    if "." in basename:
        return basename.rsplit(".", 1)[0]
    return basename


def _reason(
    source_kind: SmartPartEvidenceKind,
    field_name: str,
    kind: SmartPartKind,
) -> str:
    return f"{source_kind.value}.{field_name}:exact_alias:{kind.value}"


def _resolve_named_field_matches(
    matches: tuple[tuple[str, SmartPartKind], ...],
) -> SmartPartKind | None:
    if type(matches) is not tuple:
        raise TypeError("matches must be a tuple.")

    matched_kinds: set[SmartPartKind] = set()
    for item in matches:
        if type(item) is not tuple or len(item) != 2:
            raise TypeError("matches must contain field-name/kind tuples.")
        field_name, kind = item
        if type(field_name) is not str or not field_name:
            raise ValueError("match field name must be a non-empty string.")
        if not isinstance(kind, SmartPartKind):
            raise TypeError("match kind must be a SmartPartKind value.")
        matched_kinds.add(kind)

    if len(matched_kinds) != 1:
        return None
    return next(iter(matched_kinds))


def _detect_named_entry(
    *,
    source_kind: SmartPartEvidenceKind,
    source_index: int,
    local_name: str,
    universal_name: str,
    alias_index: _NormalizedAliasIndex,
) -> SmartPart | None:
    matches: list[tuple[str, SmartPartKind]] = []
    for field_name, value in (
        ("local_name", local_name),
        ("universal_name", universal_name),
    ):
        kind = _exact_alias_kind_from_index(value, alias_index)
        if kind is not None:
            matches.append((field_name, kind))

    frozen_matches = tuple(matches)
    kind = _resolve_named_field_matches(frozen_matches)
    if kind is None:
        return None

    evidence = tuple(
        SmartPartEvidence(
            source_kind=source_kind,
            source_index=source_index,
            reason=_reason(source_kind, field_name, kind),
        )
        for field_name, matched_kind in frozen_matches
        if matched_kind is kind
    )
    return SmartPart(kind=kind, evidence=evidence)


def _detect_texture_entry(
    entry: PmxStructuralAuthoringTextureCatalogEntry,
) -> SmartPart | None:
    stem = _texture_basename_stem(entry.path)
    kind = _exact_alias_kind_from_index(stem, _TEXTURE_ALIAS_INDEX)
    if kind is None:
        return None
    return SmartPart(
        kind=kind,
        evidence=(
            SmartPartEvidence(
                source_kind=SmartPartEvidenceKind.TEXTURE,
                source_index=entry.source_index,
                reason=_reason(
                    SmartPartEvidenceKind.TEXTURE,
                    "path",
                    kind,
                ),
            ),
        ),
    )


def _detect_single_entry(
    entry: SmartPartDetectionEntry,
) -> SmartPart | None:
    if isinstance(entry, PmxStructuralAuthoringTextureCatalogEntry):
        return _detect_texture_entry(entry)
    if isinstance(entry, PmxStructuralAuthoringMaterialCatalogEntry):
        return _detect_named_entry(
            source_kind=SmartPartEvidenceKind.MATERIAL,
            source_index=entry.source_index,
            local_name=entry.local_name,
            universal_name=entry.universal_name,
            alias_index=_MATERIAL_ALIAS_INDEX,
        )
    if isinstance(entry, PmxStructuralAuthoringBoneCatalogEntry):
        return _detect_named_entry(
            source_kind=SmartPartEvidenceKind.BONE,
            source_index=entry.source_index,
            local_name=entry.local_name,
            universal_name=entry.universal_name,
            alias_index=_BONE_ALIAS_INDEX,
        )
    if isinstance(entry, PmxStructuralAuthoringMorphCatalogEntry):
        return _detect_named_entry(
            source_kind=SmartPartEvidenceKind.MORPH,
            source_index=entry.source_index,
            local_name=entry.local_name,
            universal_name=entry.universal_name,
            alias_index=_MORPH_ALIAS_INDEX,
        )
    if isinstance(
        entry,
        (
            PmxStructuralAuthoringVertexCatalogEntry,
            PmxStructuralAuthoringRigidBodyCatalogEntry,
        ),
    ):
        return None
    raise TypeError("entry must be a structural-authoring catalog entry.")


def _smart_part_sort_key(part: SmartPart) -> int:
    if not isinstance(part, SmartPart):
        raise TypeError("part must be a SmartPart value.")
    return _SMART_PART_ORDER.index(part.kind)


def _smart_part_collection_sort_key(
    part: SmartPart,
) -> tuple[int, tuple[tuple[str, int, str], ...]]:
    return (
        _smart_part_sort_key(part),
        tuple(
            (
                evidence.source_kind.value,
                evidence.source_index,
                evidence.reason,
            )
            for evidence in part.evidence
        ),
    )


def _validated_entries(
    entries: tuple[SmartPartDetectionEntry, ...],
) -> tuple[SmartPartDetectionEntry, ...]:
    if type(entries) is not tuple:
        raise TypeError("entries must be a tuple.")
    if not all(isinstance(entry, _SUPPORTED_ENTRY_TYPES) for entry in entries):
        raise TypeError(
            "entries must contain only structural-authoring catalog entries."
        )
    return entries


def _aggregate_parts(
    parts: tuple[SmartPart, ...],
) -> tuple[SmartPart, ...]:
    if type(parts) is not tuple:
        raise TypeError("parts must be a tuple.")
    if not all(isinstance(part, SmartPart) for part in parts):
        raise TypeError("parts must contain only SmartPart values.")

    evidence_by_kind: dict[SmartPartKind, set[SmartPartEvidence]] = {}
    for part in parts:
        evidence_by_kind.setdefault(part.kind, set()).update(part.evidence)

    return tuple(
        SmartPart(
            kind=kind,
            evidence=tuple(evidence_by_kind[kind]),
        )
        for kind in _SMART_PART_ORDER
        if kind in evidence_by_kind
    )


def detect_smart_parts(
    entries: tuple[SmartPartDetectionEntry, ...],
) -> tuple[SmartPart, ...]:
    """Return canonical Smart Parts aggregated across source entities."""

    validated = _validated_entries(entries)
    per_entity_parts = tuple(
        part
        for part in (_detect_single_entry(entry) for entry in validated)
        if part is not None
    )
    return _aggregate_parts(per_entity_parts)


__all__ = ("detect_smart_parts",)
