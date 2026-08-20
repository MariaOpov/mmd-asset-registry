"""Public bounded DTO for CP07 texture insertion preview requests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class PmxStructuralTextureInsertion:
    """One bounded public texture-path insertion request."""

    path: str
    position: Literal["append", "insert_before"] = "append"
    source_index: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.path, str):
            raise TypeError("path must be a string.")
        if not isinstance(self.position, str):
            raise TypeError("position must be a string.")
        if self.position not in ("append", "insert_before"):
            raise ValueError("position must be either 'append' or 'insert_before'.")

        if self.position == "append":
            if self.source_index is not None:
                raise ValueError("append insertion cannot define source_index.")
            return

        if type(self.source_index) is not int:
            raise TypeError("insert_before source_index must be an integer.")
        if self.source_index < 0:
            raise ValueError("insert_before source_index cannot be negative.")


__all__ = ("PmxStructuralTextureInsertion",)
