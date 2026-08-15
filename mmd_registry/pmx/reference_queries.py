"""Deterministic read-only queries over an extracted PMX reference graph.

CP06 operates only on the immutable CP05 snapshot. It does not traverse a
typed model document, mutate model data, remap indices, emit public
diagnostics, or touch the filesystem.
"""

from __future__ import annotations

from dataclasses import dataclass

from mmd_registry.pmx.reference_graph import (
    PmxReferenceGraph,
    PmxReferenceInvalidTarget,
    PmxReferenceUnsupportedState,
)
from mmd_registry.pmx.reference_model import (
    PmxReferenceEdge,
    PmxReferenceNode,
    PmxReferenceSourceSection,
    PmxReferenceTargetKind,
)


_SOURCE_TARGET_OWNERS = {
    PmxReferenceSourceSection.VERTICES: PmxReferenceTargetKind.VERTEX,
    PmxReferenceSourceSection.MATERIALS: PmxReferenceTargetKind.MATERIAL,
    PmxReferenceSourceSection.BONES: PmxReferenceTargetKind.BONE,
    PmxReferenceSourceSection.MORPHS: PmxReferenceTargetKind.MORPH,
    PmxReferenceSourceSection.RIGID_BODIES: PmxReferenceTargetKind.RIGID_BODY,
}


@dataclass(frozen=True, slots=True)
class PmxReferenceImpact:
    """Direct reference impact for one existing globally-addressable PMX node.

    ``unresolved_states`` is intentionally graph-wide. A CP05 unsupported state
    can hide a relationship target, so CP06 must not claim complete inbound
    knowledge for any node while such evidence exists.
    """

    node: PmxReferenceNode
    inbound_edges: tuple[PmxReferenceEdge, ...]
    outbound_edges: tuple[PmxReferenceEdge, ...]
    source_invalid_targets: tuple[PmxReferenceInvalidTarget, ...]
    source_unsupported_states: tuple[PmxReferenceUnsupportedState, ...]
    unresolved_states: tuple[PmxReferenceUnsupportedState, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.node, PmxReferenceNode):
            raise TypeError("node must be a PmxReferenceNode value.")

        for field_name, expected_type in (
            ("inbound_edges", PmxReferenceEdge),
            ("outbound_edges", PmxReferenceEdge),
            ("source_invalid_targets", PmxReferenceInvalidTarget),
            ("source_unsupported_states", PmxReferenceUnsupportedState),
            ("unresolved_states", PmxReferenceUnsupportedState),
        ):
            value = getattr(self, field_name)
            if type(value) is not tuple:
                raise TypeError(f"{field_name} must be a tuple.")
            if not all(isinstance(item, expected_type) for item in value):
                raise TypeError(
                    f"{field_name} must contain only {expected_type.__name__} values."
                )

    @property
    def is_complete(self) -> bool:
        """Whether CP05 left no unsupported relationship state anywhere."""

        return not self.unresolved_states


def _validate_query_node(
    graph: PmxReferenceGraph,
    node: PmxReferenceNode,
) -> None:
    if not isinstance(graph, PmxReferenceGraph):
        raise TypeError("graph must be a PmxReferenceGraph value.")
    if not isinstance(node, PmxReferenceNode):
        raise TypeError("node must be a PmxReferenceNode value.")

    count = graph.target_counts.count_for(node.kind)
    if node.index >= count:
        raise ValueError(
            f"{node.kind.value} node index {node.index} is outside target count {count}."
        )


def _source_is_owned_by_node(
    section: PmxReferenceSourceSection,
    record_index: int,
    node: PmxReferenceNode,
) -> bool:
    return (
        _SOURCE_TARGET_OWNERS.get(section) is node.kind
        and record_index == node.index
    )


def inbound_references(
    graph: PmxReferenceGraph,
    node: PmxReferenceNode,
) -> tuple[PmxReferenceEdge, ...]:
    """Return valid edges targeting ``node`` in deterministic graph order."""

    _validate_query_node(graph, node)
    return tuple(edge for edge in graph.edges if edge.target == node)


def outbound_references(
    graph: PmxReferenceGraph,
    node: PmxReferenceNode,
) -> tuple[PmxReferenceEdge, ...]:
    """Return valid edges owned by ``node`` in deterministic graph order.

    Only the five addressable collections that also own relationship fields
    can have outbound edges. Texture records have no reference-owning fields.
    Non-addressable source sections such as surface indices, display frames,
    joints, and soft bodies are intentionally not attributed to a target node.
    """

    _validate_query_node(graph, node)
    return tuple(
        edge
        for edge in graph.edges
        if _source_is_owned_by_node(
            edge.source.section,
            edge.source.record_index,
            node,
        )
    )


def analyze_reference_impact(
    graph: PmxReferenceGraph,
    node: PmxReferenceNode,
) -> PmxReferenceImpact:
    """Return conservative direct reference impact for one existing node."""

    _validate_query_node(graph, node)

    inbound = tuple(edge for edge in graph.edges if edge.target == node)
    outbound = tuple(
        edge
        for edge in graph.edges
        if _source_is_owned_by_node(
            edge.source.section,
            edge.source.record_index,
            node,
        )
    )
    source_invalid_targets = tuple(
        item
        for item in graph.invalid_targets
        if _source_is_owned_by_node(
            item.source.section,
            item.source.record_index,
            node,
        )
    )
    source_unsupported_states = tuple(
        state
        for state in graph.unsupported_states
        if _source_is_owned_by_node(
            state.source.section,
            state.source.record_index,
            node,
        )
    )

    return PmxReferenceImpact(
        node=node,
        inbound_edges=inbound,
        outbound_edges=outbound,
        source_invalid_targets=source_invalid_targets,
        source_unsupported_states=source_unsupported_states,
        unresolved_states=graph.unsupported_states,
    )


__all__ = (
    "PmxReferenceImpact",
    "analyze_reference_impact",
    "inbound_references",
    "outbound_references",
)
