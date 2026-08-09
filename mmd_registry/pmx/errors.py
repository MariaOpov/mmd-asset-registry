"""Shared PMX read/write errors independent of scanner and CLI layers."""

from __future__ import annotations

from typing import NoReturn

from mmd_registry.binary_reader import BinaryParseError


class PmxValidationError(ValueError):
    """One contextual failure found before PMX serialization."""

    def __init__(
        self,
        *,
        section: str,
        field: str,
        reason: str,
        record_index: int | None = None,
    ) -> None:
        location = section
        if record_index is not None:
            location = f"{section}[{record_index}]"

        self.section = section
        self.record_index = record_index
        self.field = field
        self.reason = reason
        super().__init__(
            f"Invalid PMX document in {location}.{field}: {reason}"
        )


def raise_pmx_error(
    *,
    section: str,
    offset: int,
    operation: str,
    reason: str,
    record_index: int | None = None,
) -> NoReturn:
    """Raise one contextual PMX parse error with stable wording."""

    raise BinaryParseError(
        format_name="PMX",
        section=section,
        record_index=record_index,
        offset=offset,
        operation=operation,
        reason=reason,
    )
