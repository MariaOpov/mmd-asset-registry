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


def _source_target_owner(
    section: PmxReferenceSourceSection,
) -> PmxReferenceTargetKind | None:
    """Return the addressable owner kind for one reference-source section."""

    if section is PmxReferenceSourceSection.VERTICES:
        return PmxReferenceTargetKind.VERTEX
    if section is PmxReferenceSourceSection.MATERIALS:
        return PmxReferenceTargetKind.MATERIAL
    if section is PmxReferenceSourceSection.BONES:
        return PmxReferenceTargetKind.BONE
    if section is PmxReferenceSourceSection.MORPHS:
        return PmxReferenceTargetKind.MORPH
    if section is PmxReferenceSourceSection.RIGID_BODIES:
        return PmxReferenceTargetKind.RIGID_BODY
    return None


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

    @classmethod
    def _from_validated_graph_parts(
        cls,
        *,
        node: PmxReferenceNode,
        inbound_edges: tuple[PmxReferenceEdge, ...],
        outbound_edges: tuple[PmxReferenceEdge, ...],
        source_invalid_targets: tuple[PmxReferenceInvalidTarget, ...],
        source_unsupported_states: tuple[PmxReferenceUnsupportedState, ...],
        unresolved_states: tuple[PmxReferenceUnsupportedState, ...],
    ) -> PmxReferenceImpact:
        """Build one impact from already-validated immutable graph evidence."""

        instance = object.__new__(cls)
        object.__setattr__(instance, "node", node)
        object.__setattr__(instance, "inbound_edges", inbound_edges)
        object.__setattr__(instance, "outbound_edges", outbound_edges)
        object.__setattr__(
            instance,
            "source_invalid_targets",
            source_invalid_targets,
        )
        object.__setattr__(
            instance,
            "source_unsupported_states",
            source_unsupported_states,
        )
        object.__setattr__(instance, "unresolved_states", unresolved_states)
        return instance


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
        _source_target_owner(section) is node.kind
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


def _analyze_reference_impacts(
    graph: PmxReferenceGraph,
    nodes: tuple[PmxReferenceNode, ...],
) -> tuple[PmxReferenceImpact, ...]:
    """Analyze many existing nodes with one bounded pass over graph evidence."""

    if not isinstance(graph, PmxReferenceGraph):
        raise TypeError("graph must be a PmxReferenceGraph value.")
    if type(nodes) is not tuple:
        raise TypeError("nodes must be a tuple.")
    if not all(isinstance(node, PmxReferenceNode) for node in nodes):
        raise TypeError("nodes must contain only PmxReferenceNode values.")

    for node in nodes:
        _validate_query_node(graph, node)
    if not nodes:
        return ()

    requested_keys = {(node.kind, node.index) for node in nodes}
    inbound_by_key = {key: [] for key in requested_keys}
    outbound_by_key = {key: [] for key in requested_keys}
    invalid_by_key = {key: [] for key in requested_keys}
    unsupported_by_key = {key: [] for key in requested_keys}

    for edge in graph.edges:
        inbound_bucket = inbound_by_key.get((edge.target.kind, edge.target.index))
        if inbound_bucket is not None:
            inbound_bucket.append(edge)

        owner_kind = _source_target_owner(edge.source.section)
        if owner_kind is not None:
            outbound_bucket = outbound_by_key.get(
                (owner_kind, edge.source.record_index)
            )
            if outbound_bucket is not None:
                outbound_bucket.append(edge)

    for item in graph.invalid_targets:
        owner_kind = _source_target_owner(item.source.section)
        if owner_kind is not None:
            invalid_bucket = invalid_by_key.get(
                (owner_kind, item.source.record_index)
            )
            if invalid_bucket is not None:
                invalid_bucket.append(item)

    for state in graph.unsupported_states:
        owner_kind = _source_target_owner(state.source.section)
        if owner_kind is not None:
            unsupported_bucket = unsupported_by_key.get(
                (owner_kind, state.source.record_index)
            )
            if unsupported_bucket is not None:
                unsupported_bucket.append(state)

    return tuple(
        PmxReferenceImpact._from_validated_graph_parts(
            node=node,
            inbound_edges=tuple(inbound_by_key[(node.kind, node.index)]),
            outbound_edges=tuple(outbound_by_key[(node.kind, node.index)]),
            source_invalid_targets=tuple(invalid_by_key[(node.kind, node.index)]),
            source_unsupported_states=tuple(
                unsupported_by_key[(node.kind, node.index)]
            ),
            unresolved_states=graph.unsupported_states,
        )
        for node in nodes
    )


def analyze_reference_impact(
    graph: PmxReferenceGraph,
    node: PmxReferenceNode,
) -> PmxReferenceImpact:
    """Return conservative direct reference impact for one existing node."""

    _validate_query_node(graph, node)
    return _analyze_reference_impacts(graph, (node,))[0]


__all__ = (
    "PmxReferenceImpact",
    "analyze_reference_impact",
    "inbound_references",
    "outbound_references",
)
