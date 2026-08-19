"""Internal read-only structural capacity evidence for v0.9.2.

This module does not mutate a :class:`PmxDocument`, resize PMX index widths,
authorize insertion execution, or expose a public service boundary. It models
whether one proposed structural result count fits both the already-declared PMX
index width and the independent signed 32-bit PMX section-count field.

The whole-document validator remains the final PMX validity authority.
"""

from __future__ import annotations

from dataclasses import dataclass

from mmd_registry.pmx.document import VALID_PMX_INDEX_SIZES
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.pmx.validation import MAX_INT32


def _require_nonnegative_plain_int(value: object, field_name: str) -> int:
    """Return one exact nonnegative integer, rejecting booleans."""

    if type(value) is not int:
        raise TypeError(f"{field_name} must be an integer.")
    if value < 0:
        raise ValueError(f"{field_name} must be nonnegative.")
    return value


def _require_index_width(value: object) -> int:
    """Return one supported PMX index width."""

    if type(value) is not int:
        raise TypeError("index_width must be an integer.")
    if value not in VALID_PMX_INDEX_SIZES:
        raise ValueError(
            "index_width must be one of "
            f"{sorted(VALID_PMX_INDEX_SIZES)}; got {value!r}."
        )
    return value


@dataclass(frozen=True, slots=True)
class PmxStructuralCapacityAnalysis:
    """Immutable mathematical capacity evidence for one structural target kind."""

    target_kind: PmxReferenceTargetKind
    current_count: int
    insert_count: int
    index_width: int

    def __post_init__(self) -> None:
        if not isinstance(self.target_kind, PmxReferenceTargetKind):
            raise TypeError("target_kind must be a PmxReferenceTargetKind value.")
        _require_nonnegative_plain_int(self.current_count, "current_count")
        _require_nonnegative_plain_int(self.insert_count, "insert_count")
        _require_index_width(self.index_width)

    @property
    def result_count(self) -> int:
        """Return the proposed collection size after insertion."""

        return self.current_count + self.insert_count

    @property
    def signed(self) -> bool:
        """Whether this target kind uses a signed PMX index encoding."""

        return self.target_kind is not PmxReferenceTargetKind.VERTEX

    @property
    def maximum_addressable_index(self) -> int:
        """Return the largest index representable by the declared width."""

        return (1 << (self.index_width * 8 - (1 if self.signed else 0))) - 1

    @property
    def index_addressable_count(self) -> int:
        """Return how many records the declared index width can name."""

        return self.maximum_addressable_index + 1

    @property
    def section_count_limit(self) -> int:
        """Return the independent signed 32-bit PMX section-count limit."""

        return MAX_INT32

    @property
    def effective_max_count(self) -> int:
        """Return the maximum result count allowed by both PMX constraints."""

        return min(self.index_addressable_count, self.section_count_limit)

    @property
    def width_representable(self) -> bool:
        """Whether the declared index width can name every proposed record."""

        return self.result_count <= self.index_addressable_count

    @property
    def count_representable(self) -> bool:
        """Whether the proposed count fits the PMX signed 32-bit count field."""

        return self.result_count <= self.section_count_limit

    @property
    def representable(self) -> bool:
        """Whether both independent PMX capacity constraints are satisfied."""

        return self.width_representable and self.count_representable

    @property
    def expansion_required(self) -> bool:
        """Whether the current index width alone is insufficient.

        This is evidence only. v0.9.2 does not authorize automatic width
        expansion, and a wider width cannot cure an independent section-count
        overflow.
        """

        return not self.width_representable

    def to_dict(self) -> dict[str, object]:
        """Return deterministic JSON-ready bounded capacity evidence."""

        return {
            "target_kind": self.target_kind.value,
            "current_count": self.current_count,
            "insert_count": self.insert_count,
            "result_count": self.result_count,
            "index_width": self.index_width,
            "signed": self.signed,
            "maximum_addressable_index": self.maximum_addressable_index,
            "index_addressable_count": self.index_addressable_count,
            "section_count_limit": self.section_count_limit,
            "effective_max_count": self.effective_max_count,
            "width_representable": self.width_representable,
            "count_representable": self.count_representable,
            "representable": self.representable,
            "expansion_required": self.expansion_required,
        }


def analyze_structural_capacity(
    target_kind: PmxReferenceTargetKind,
    *,
    current_count: int,
    insert_count: int,
    index_width: int,
) -> PmxStructuralCapacityAnalysis:
    """Return read-only deterministic capacity evidence.

    The inputs are mathematical structural facts. This function deliberately
    does not validate a complete PMX document or decide whether an insertion
    operation is otherwise safe.
    """

    return PmxStructuralCapacityAnalysis(
        target_kind=target_kind,
        current_count=current_count,
        insert_count=insert_count,
        index_width=index_width,
    )


__all__ = (
    "PmxStructuralCapacityAnalysis",
    "analyze_structural_capacity",
)
