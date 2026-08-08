"""Deterministic name-based semantic resolution for PMX bones."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, Literal, Sequence, TypeAlias

from mmd_registry.bone_names import (
    normalize_bone_name,
    split_bone_name_tokens,
)
from mmd_registry.bone_semantics import (
    DEFAULT_BONE_SEMANTIC_PROFILE,
    BoneCategory,
    BoneConfidence,
    BoneEvidenceCode,
    BoneSemanticAlias,
    BoneSemanticProfile,
    BoneSemanticResult,
    BoneSemanticRole,
    BoneSide,
    order_bone_evidence,
    specialize_bone_semantic_role,
)
from mmd_registry.model_scanning import PmxBone


_NameConvention: TypeAlias = Literal[
    "deform",
    "helper",
]

_IK_ROLES: Final[frozenset[BoneSemanticRole]] = frozenset(
    {
        "leg_ik_parent",
        "leg_ik",
        "toe_ik",
    }
)


@dataclass(frozen=True, slots=True)
class _PreparedAlias:
    """One alias normalized once for repeated resolver use."""

    source: BoneSemanticAlias
    normalized: str
    tokens: tuple[str, ...]
    contains_non_ascii: bool


@dataclass(frozen=True, slots=True)
class _AliasMatch:
    """One internal alias match and its deterministic strength."""

    alias: _PreparedAlias
    strength: int


@dataclass(frozen=True, slots=True)
class _NameResolution:
    """The strongest unambiguous result from one source name."""

    role: BoneSemanticRole | None
    category: BoneCategory | None
    sides: tuple[BoneSide, ...]
    aliases: tuple[str, ...]
    strength: int
    ambiguous: bool


def _prepare_alias(alias: BoneSemanticAlias) -> _PreparedAlias | None:
    """Normalize one alias or ignore an empty declaration safely."""

    normalized = normalize_bone_name(alias.alias)

    if not normalized:
        return None

    return _PreparedAlias(
        source=alias,
        normalized=normalized,
        tokens=split_bone_name_tokens(alias.alias),
        contains_non_ascii=any(ord(character) > 127 for character in normalized),
    )


def _contains_token_sequence(
    tokens: tuple[str, ...],
    candidate: tuple[str, ...],
) -> bool:
    """Return whether a non-empty token sequence occurs contiguously."""

    if not candidate or len(candidate) > len(tokens):
        return False

    width = len(candidate)

    return any(
        tokens[start : start + width] == candidate
        for start in range(len(tokens) - width + 1)
    )


def _match_alias(
    normalized_name: str,
    name_tokens: tuple[str, ...],
    alias: _PreparedAlias,
) -> _AliasMatch | None:
    """Match one alias using exact, token, or conservative CJK containment."""

    if normalized_name == alias.normalized:
        return _AliasMatch(
            alias=alias,
            strength=3,
        )

    if _contains_token_sequence(name_tokens, alias.tokens):
        return _AliasMatch(
            alias=alias,
            strength=2,
        )

    if alias.contains_non_ascii and alias.normalized in normalized_name:
        return _AliasMatch(
            alias=alias,
            strength=1,
        )

    return None


def _deduplicate_strings(values: Sequence[str]) -> tuple[str, ...]:
    """Deduplicate strings while preserving deterministic source order."""

    seen: set[str] = set()
    result: list[str] = []

    for value in values:
        if value in seen:
            continue

        seen.add(value)
        result.append(value)

    return tuple(result)


def _resolve_name(
    value: str,
    prepared_aliases: tuple[_PreparedAlias, ...],
) -> _NameResolution:
    """Resolve the strongest aliases from one source name."""

    normalized_name = normalize_bone_name(value)

    if not normalized_name:
        return _NameResolution(
            role=None,
            category=None,
            sides=(),
            aliases=(),
            strength=0,
            ambiguous=False,
        )

    name_tokens = split_bone_name_tokens(value)
    matches = tuple(
        match
        for alias in prepared_aliases
        if (match := _match_alias(normalized_name, name_tokens, alias)) is not None
    )

    if not matches:
        return _NameResolution(
            role=None,
            category=None,
            sides=(),
            aliases=(),
            strength=0,
            ambiguous=False,
        )

    strongest = max(match.strength for match in matches)
    strongest_matches = tuple(match for match in matches if match.strength == strongest)
    longest = max(len(match.alias.normalized) for match in strongest_matches)
    selected = tuple(
        match for match in strongest_matches if len(match.alias.normalized) == longest
    )
    roles = {match.alias.source.role for match in selected}
    categories = {match.alias.source.category for match in selected}
    sides = tuple(
        sorted(
            {
                match.alias.source.side
                for match in selected
                if match.alias.source.side is not None
            }
        )
    )
    aliases = _deduplicate_strings(
        tuple(match.alias.source.alias for match in selected)
    )
    ambiguous = len(roles) != 1 or len(categories) != 1

    return _NameResolution(
        role=(next(iter(roles)) if not ambiguous else None),
        category=(next(iter(categories)) if not ambiguous else None),
        sides=sides,
        aliases=aliases,
        strength=strongest,
        ambiguous=ambiguous,
    )


def _find_side_markers(value: str) -> tuple[BoneSide, ...]:
    """Find explicit left/right markers without guessing from substrings."""

    normalized = normalize_bone_name(value)
    tokens = set(split_bone_name_tokens(value))
    sides: set[BoneSide] = set()

    if "左" in normalized or tokens.intersection({"left", "l"}):
        sides.add("left")

    if "右" in normalized or tokens.intersection({"right", "r"}):
        sides.add("right")

    return tuple(sorted(sides))


def _find_name_conventions(value: str) -> tuple[_NameConvention, ...]:
    """Find explicit deform/helper conventions in one source name."""

    normalized = normalize_bone_name(value)
    tokens = split_bone_name_tokens(value)
    token_set = set(tokens)
    conventions: set[_NameConvention] = set()

    if (
        "deform" in token_set
        or "変形" in normalized
        or (len(tokens) > 1 and tokens[-1] == "d")
    ):
        conventions.add("deform")

    if token_set.intersection({"helper", "dummy", "support"}) or ("補助" in normalized):
        conventions.add("helper")

    return tuple(sorted(conventions))


@dataclass(frozen=True, slots=True)
class BoneSemanticResolver:
    """Resolve PMX bone semantics using one replaceable alias profile."""

    profile: BoneSemanticProfile = DEFAULT_BONE_SEMANTIC_PROFILE
    _prepared_aliases: tuple[_PreparedAlias, ...] = field(
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        """Prepare immutable alias data once per resolver."""

        prepared = tuple(
            normalized
            for alias in self.profile.aliases
            if (normalized := _prepare_alias(alias)) is not None
        )
        object.__setattr__(
            self,
            "_prepared_aliases",
            prepared,
        )

    def resolve(
        self,
        index: int,
        bone: PmxBone,
    ) -> BoneSemanticResult:
        """Resolve one scanner record without modifying it."""

        local = _resolve_name(
            bone.local_name,
            self._prepared_aliases,
        )
        universal = _resolve_name(
            bone.universal_name,
            self._prepared_aliases,
        )
        evidence: set[BoneEvidenceCode] = set()

        if local.aliases:
            evidence.add("local_name_alias")

        if universal.aliases:
            evidence.add("universal_name_alias")

        matched_aliases = _deduplicate_strings((*local.aliases, *universal.aliases))
        role: BoneSemanticRole = "unknown"
        category: BoneCategory = "unknown"
        confidence: BoneConfidence = "unknown"
        alias_conflict = local.ambiguous or universal.ambiguous
        category_conflict = False

        if alias_conflict:
            evidence.add("alias_conflict")
            confidence = "low"
        else:
            resolved_names = tuple(
                resolution
                for resolution in (local, universal)
                if resolution.role is not None
            )
            resolved_roles = {resolution.role for resolution in resolved_names}

            if len(resolved_roles) > 1:
                alias_conflict = True
                evidence.add("alias_conflict")
                confidence = "low"
            elif len(resolved_roles) == 1:
                resolved_role = next(iter(resolved_roles))
                assert resolved_role is not None
                role = resolved_role
                resolved_categories = {
                    resolution.category for resolution in resolved_names
                }

                if len(resolved_categories) == 1:
                    resolved_category = next(iter(resolved_categories))
                    assert resolved_category is not None
                    category = resolved_category
                else:
                    category_conflict = True
                    evidence.add("category_conflict")
                    category = "unknown"

                if len(resolved_names) == 2:
                    confidence = "high"
                elif resolved_names[0].strength == 3:
                    confidence = "high"
                else:
                    confidence = "medium"

                if category_conflict:
                    confidence = "low"

        local_conventions = _find_name_conventions(bone.local_name)
        universal_conventions = _find_name_conventions(bone.universal_name)

        if local_conventions:
            evidence.add("local_name_convention")

        if universal_conventions:
            evidence.add("universal_name_convention")

        conventions = set((*local_conventions, *universal_conventions))

        if len(conventions) > 1:
            evidence.add("naming_conflict")
            category = "unknown"
            confidence = "low"
        elif conventions and not alias_conflict and role not in _IK_ROLES:
            convention = next(iter(conventions))

            if convention == "deform":
                category = "deform"
            else:
                category = "helper"

            role = specialize_bone_semantic_role(
                role,
                category,
            )

            if role == "unknown":
                confidence = "low"

        marker_sides = (
            *_find_side_markers(bone.local_name),
            *_find_side_markers(bone.universal_name),
        )

        if marker_sides:
            evidence.add("side_marker")

        side_candidates = {
            *local.sides,
            *universal.sides,
            *marker_sides,
        }
        side: BoneSide = "none"

        if len(side_candidates) == 1:
            side = next(iter(side_candidates))
        elif len(side_candidates) > 1:
            evidence.add("side_conflict")
            confidence = "low"

        has_ik_flag = "ik" in bone.flag_names
        has_ik_definition = bone.ik is not None

        if has_ik_flag:
            evidence.add("bone_flags")

        if has_ik_definition:
            evidence.add("ik_definition")

        if has_ik_flag or has_ik_definition:
            if role in _IK_ROLES:
                category = "ik"

                if not {
                    "alias_conflict",
                    "naming_conflict",
                    "category_conflict",
                    "side_conflict",
                }.intersection(evidence):
                    confidence = "high"
            elif role == "unknown" and not alias_conflict:
                category = "ik"
                confidence = "low"
            else:
                evidence.add("category_conflict")
                category = "unknown"
                confidence = "low"

        return BoneSemanticResult(
            index=index,
            local_name=bone.local_name,
            universal_name=bone.universal_name,
            role=role,
            side=side,
            category=category,
            confidence=confidence,
            evidence=order_bone_evidence(evidence),
            matched_aliases=matched_aliases,
        )


DEFAULT_BONE_SEMANTIC_RESOLVER: Final[BoneSemanticResolver] = BoneSemanticResolver()


def resolve_bone_semantic(
    index: int,
    bone: PmxBone,
    *,
    resolver: BoneSemanticResolver = DEFAULT_BONE_SEMANTIC_RESOLVER,
) -> BoneSemanticResult:
    """Resolve one PMX bone with a reusable resolver."""

    return resolver.resolve(
        index,
        bone,
    )


def resolve_bone_semantics(
    bones: Sequence[PmxBone],
    *,
    resolver: BoneSemanticResolver = DEFAULT_BONE_SEMANTIC_RESOLVER,
) -> tuple[BoneSemanticResult, ...]:
    """Resolve a sequence without modifying its records or order."""

    source_bones = tuple(bones)

    return tuple(
        resolver.resolve(index, bone) for index, bone in enumerate(source_bones)
    )
