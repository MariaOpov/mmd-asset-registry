"""Shared Unicode normalization helpers for PMX bone names."""

from __future__ import annotations

import re
import unicodedata
from typing import Final


_ACRONYM_BOUNDARY: Final[re.Pattern[str]] = re.compile(r"(?<=[A-Z])(?=[A-Z][a-z])")
_CAMEL_CASE_BOUNDARY: Final[re.Pattern[str]] = re.compile(r"(?<=[a-z])(?=[A-Z])")
_LETTER_DIGIT_BOUNDARY: Final[re.Pattern[str]] = re.compile(
    r"(?<=[A-Za-z])(?=[0-9])|(?<=[0-9])(?=[A-Za-z])"
)
_NON_ASCII_ASCII_BOUNDARY: Final[re.Pattern[str]] = re.compile(
    r"(?<=[^\x00-\x7f])(?=[A-Za-z0-9])|"
    r"(?<=[A-Za-z0-9])(?=[^\x00-\x7f])"
)
_TOKEN_SEPARATOR: Final[re.Pattern[str]] = re.compile(r"[\W_]+")


def _normalize_bone_name_width(value: str) -> str:
    """Normalize Unicode width without translating source text."""

    return unicodedata.normalize("NFKC", value)


def normalize_bone_name(value: str) -> str:
    """Normalize width, whitespace, and case for deterministic matching."""

    normalized = _normalize_bone_name_width(value)

    return " ".join(normalized.split()).casefold()


def split_bone_name_tokens(value: str) -> tuple[str, ...]:
    """Split common bone-name conventions into normalized matching tokens."""

    separated = _normalize_bone_name_width(value)
    separated = _ACRONYM_BOUNDARY.sub(" ", separated)
    separated = _CAMEL_CASE_BOUNDARY.sub(" ", separated)
    separated = _LETTER_DIGIT_BOUNDARY.sub(" ", separated)
    separated = _NON_ASCII_ASCII_BOUNDARY.sub(" ", separated)
    separated = _TOKEN_SEPARATOR.sub(" ", separated)

    return tuple(token.casefold() for token in separated.split())
