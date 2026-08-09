"""Shared PMX parsing errors independent of scanner and CLI layers."""

from __future__ import annotations

from typing import NoReturn

from mmd_registry.binary_reader import BinaryParseError


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
