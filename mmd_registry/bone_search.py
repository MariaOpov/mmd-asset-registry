"""Search and basic filtering for presented PMX bones."""

from __future__ import annotations

import unicodedata
from typing import Sequence

from mmd_registry.bone_explorer import BoneView


def _normalize_search_text(value: str) -> str:
    """Normalize user-facing text for predictable matching."""

    normalized = unicodedata.normalize("NFKC", value)

    return " ".join(normalized.split()).casefold()


def _parse_index_query(query: str) -> int | None:
    """Parse supported exact-index query forms."""

    candidate = unicodedata.normalize("NFKC", query).strip()

    if candidate.startswith("#"):
        candidate = candidate[1:].strip()
    elif candidate.startswith("[") and candidate.endswith("]"):
        candidate = candidate[1:-1].strip()

    if not candidate.isdecimal():
        return None

    return int(candidate)


def _matches_search_query(
    view: BoneView,
    *,
    normalized_query: str,
    index_query: int | None,
) -> bool:
    """Return whether one presented bone matches a search query."""

    if index_query is not None:
        return view.index == index_query

    searchable_names = (
        view.display_name,
        view.local_name,
        view.universal_name,
    )

    return any(
        normalized_query in _normalize_search_text(name) for name in searchable_names
    )


def filter_bone_views(
    views: Sequence[BoneView],
    *,
    search_query: str | None = None,
    ik_only: bool = False,
) -> tuple[BoneView, ...]:
    """Search and filter presented bones without modifying their order."""

    normalized_query: str | None = None
    index_query: int | None = None

    if search_query is not None:
        normalized_query = _normalize_search_text(search_query)

        if normalized_query:
            index_query = _parse_index_query(search_query)
        else:
            normalized_query = None

    matches: list[BoneView] = []

    for view in views:
        if ik_only and "IK" not in view.tags:
            continue

        if normalized_query is not None and not _matches_search_query(
            view,
            normalized_query=normalized_query,
            index_query=index_query,
        ):
            continue

        matches.append(view)

    return tuple(matches)
