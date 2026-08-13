"""Shared PMX read/write errors independent of scanner and CLI layers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn

from mmd_registry.binary_reader import BinaryParseError


@dataclass(frozen=True, slots=True)
class PmxValidationIssue:
    """One immutable machine-readable PMX semantic-validation issue."""

    section: str
    field: str
    reason: str
    record_index: int | None = None

    @property
    def location(self) -> str:
        """Return the stable section location used by legacy error text."""

        if self.record_index is None:
            return self.section
        return f"{self.section}[{self.record_index}]"

    @property
    def message(self) -> str:
        """Return the legacy human-readable validation message."""

        return (
            f"Invalid PMX document in {self.location}.{self.field}: "
            f"{self.reason}"
        )

    def to_dict(self) -> dict[str, object]:
        """Return a deterministic JSON-ready issue representation."""

        return {
            "section": self.section,
            "record_index": self.record_index,
            "field": self.field,
            "reason": self.reason,
        }


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
        issue = PmxValidationIssue(
            section=section,
            record_index=record_index,
            field=field,
            reason=reason,
        )

        self.issue = issue
        self.section = issue.section
        self.record_index = issue.record_index
        self.field = issue.field
        self.reason = issue.reason
        super().__init__(issue.message)


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
