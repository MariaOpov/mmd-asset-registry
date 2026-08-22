"""Typed request-local references for CP17 coordinated structural insertion."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final


_TARGET_KINDS: Final[frozenset[str]] = frozenset(
    {"vertex", "texture", "material", "bone", "morph", "rigid_body"}
)
_NEW_ID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"[A-Za-z][A-Za-z0-9_.-]{0,63}\Z"
)


def _require_optional_new_id(
    value: object,
    field_name: str = "new_id",
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string or None.")
    if _NEW_ID_PATTERN.fullmatch(value) is None:
        raise ValueError(
            f"{field_name} must contain 1..64 ASCII characters matching "
            "[A-Za-z][A-Za-z0-9_.-]{0,63}."
        )
    return value


@dataclass(frozen=True, slots=True)
class PmxStructuralNewReference:
    """Reference one entity created by the same structural request."""

    target_kind: str
    new_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.target_kind, str):
            raise TypeError("target_kind must be a string.")
        if self.target_kind not in _TARGET_KINDS:
            raise ValueError(
                "target_kind must be vertex, texture, material, bone, morph, "
                "or rigid_body."
            )
        if not isinstance(self.new_id, str):
            raise TypeError("new_id must be a string.")
        _require_optional_new_id(self.new_id, "new_id")


__all__ = ("PmxStructuralNewReference",)
