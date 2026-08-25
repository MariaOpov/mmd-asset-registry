"""Internal deterministic dependency evidence for structural transactions."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from mmd_registry.pmx.reference_model import PmxReferenceTargetKind


_CANONICAL_NODE_ORDER = tuple(PmxReferenceTargetKind)
_MATERIALIZATION_TIE_ORDER = (
    PmxReferenceTargetKind.TEXTURE,
    PmxReferenceTargetKind.MATERIAL,
    PmxReferenceTargetKind.BONE,
    PmxReferenceTargetKind.VERTEX,
    PmxReferenceTargetKind.RIGID_BODY,
    PmxReferenceTargetKind.MORPH,
)
_MATERIALIZATION_RANK = MappingProxyType(
    {
        target_kind: rank
        for rank, target_kind in enumerate(_MATERIALIZATION_TIE_ORDER)
    }
)
_SEMANTIC_EDGE_PAIRS = (
    (PmxReferenceTargetKind.TEXTURE, PmxReferenceTargetKind.MATERIAL),
    (PmxReferenceTargetKind.BONE, PmxReferenceTargetKind.VERTEX),
    (PmxReferenceTargetKind.BONE, PmxReferenceTargetKind.RIGID_BODY),
    (PmxReferenceTargetKind.MATERIAL, PmxReferenceTargetKind.MORPH),
    (PmxReferenceTargetKind.BONE, PmxReferenceTargetKind.MORPH),
    (PmxReferenceTargetKind.VERTEX, PmxReferenceTargetKind.MORPH),
    (PmxReferenceTargetKind.RIGID_BODY, PmxReferenceTargetKind.MORPH),
)


@dataclass(frozen=True, slots=True)
class PmxStructuralTransactionDependencyEdge:
    """One provider-before-consumer target-stage dependency."""

    provider_target: PmxReferenceTargetKind
    consumer_target: PmxReferenceTargetKind

    def __post_init__(self) -> None:
        if not isinstance(self.provider_target, PmxReferenceTargetKind):
            raise TypeError(
                "provider_target must be a PmxReferenceTargetKind value."
            )
        if not isinstance(self.consumer_target, PmxReferenceTargetKind):
            raise TypeError(
                "consumer_target must be a PmxReferenceTargetKind value."
            )


@dataclass(frozen=True, slots=True)
class PmxStructuralTransactionDependencyEvidence:
    """One immutable canonical target-stage dependency result."""

    nodes: tuple[PmxReferenceTargetKind, ...]
    edges: tuple[PmxStructuralTransactionDependencyEdge, ...]
    materialization_order: tuple[PmxReferenceTargetKind, ...]

    def __post_init__(self) -> None:
        if type(self.nodes) is not tuple:
            raise TypeError("nodes must be a tuple.")
        if type(self.edges) is not tuple:
            raise TypeError("edges must be a tuple.")
        if type(self.materialization_order) is not tuple:
            raise TypeError("materialization_order must be a tuple.")
        if any(
            not isinstance(node, PmxReferenceTargetKind)
            for node in self.nodes
        ):
            raise TypeError(
                "nodes must contain only PmxReferenceTargetKind values."
            )
        if any(
            not isinstance(edge, PmxStructuralTransactionDependencyEdge)
            for edge in self.edges
        ):
            raise TypeError(
                "edges must contain only "
                "PmxStructuralTransactionDependencyEdge values."
            )
        if any(
            not isinstance(node, PmxReferenceTargetKind)
            for node in self.materialization_order
        ):
            raise TypeError(
                "materialization_order must contain only "
                "PmxReferenceTargetKind values."
            )

        canonical_nodes = _validate_and_canonicalize_nodes(self.nodes)
        if self.nodes != canonical_nodes:
            raise ValueError("nodes must use canonical target-kind evidence order.")
        validated_edges = _validate_edges(self.nodes, self.edges)
        node_set = set(self.nodes)
        expected_pairs = tuple(
            pair
            for pair in _SEMANTIC_EDGE_PAIRS
            if pair[0] in node_set and pair[1] in node_set
        )
        actual_pairs = tuple(
            (edge.provider_target, edge.consumer_target)
            for edge in validated_edges
        )
        if actual_pairs != expected_pairs:
            raise ValueError(
                "edges must contain the exact applicable semantic dependencies "
                "in canonical order."
            )
        expected_order = _canonical_topological_order(
            self.nodes,
            validated_edges,
        )
        if self.materialization_order != expected_order:
            raise ValueError(
                "materialization_order must equal the canonical dependency order."
            )


def _materialization_rank(target_kind: PmxReferenceTargetKind) -> int:
    return _MATERIALIZATION_RANK[target_kind]


def _validate_and_canonicalize_nodes(
    nodes: tuple[PmxReferenceTargetKind, ...],
) -> tuple[PmxReferenceTargetKind, ...]:
    if type(nodes) is not tuple:
        raise TypeError("nodes must be a tuple.")

    seen: set[PmxReferenceTargetKind] = set()
    for position, node in enumerate(nodes):
        if not isinstance(node, PmxReferenceTargetKind):
            raise TypeError(
                f"nodes[{position}] must be a PmxReferenceTargetKind value."
            )
        if node in seen:
            raise ValueError(
                f"dependency nodes cannot repeat target {node.value}."
            )
        seen.add(node)
    return tuple(node for node in _CANONICAL_NODE_ORDER if node in seen)


def _validate_edges(
    nodes: tuple[PmxReferenceTargetKind, ...],
    edges: tuple[PmxStructuralTransactionDependencyEdge, ...],
) -> tuple[PmxStructuralTransactionDependencyEdge, ...]:
    if type(edges) is not tuple:
        raise TypeError("edges must be a tuple.")

    node_set = set(nodes)
    seen_pairs: set[
        tuple[PmxReferenceTargetKind, PmxReferenceTargetKind]
    ] = set()
    validated: list[PmxStructuralTransactionDependencyEdge] = []
    for position, edge in enumerate(edges):
        if not isinstance(edge, PmxStructuralTransactionDependencyEdge):
            raise TypeError(
                f"edges[{position}] must be a "
                "PmxStructuralTransactionDependencyEdge value."
            )
        pair = (edge.provider_target, edge.consumer_target)
        if pair in seen_pairs:
            raise ValueError(
                "dependency edges cannot repeat "
                f"{edge.provider_target.value} -> {edge.consumer_target.value}."
            )
        seen_pairs.add(pair)
        if edge.provider_target not in node_set:
            raise ValueError(
                "dependency edge "
                f"{edge.provider_target.value} -> {edge.consumer_target.value} "
                f"references missing provider node {edge.provider_target.value}."
            )
        if edge.consumer_target not in node_set:
            raise ValueError(
                "dependency edge "
                f"{edge.provider_target.value} -> {edge.consumer_target.value} "
                f"references missing consumer node {edge.consumer_target.value}."
            )
        validated.append(edge)
    return tuple(validated)


def _canonical_cycle_witness(
    nodes: tuple[PmxReferenceTargetKind, ...],
    adjacency: dict[
        PmxReferenceTargetKind,
        tuple[PmxReferenceTargetKind, ...],
    ],
) -> tuple[PmxReferenceTargetKind, ...]:
    exhausted: set[PmxReferenceTargetKind] = set()
    path: list[PmxReferenceTargetKind] = []
    path_positions: dict[PmxReferenceTargetKind, int] = {}

    def visit(
        node: PmxReferenceTargetKind,
    ) -> tuple[PmxReferenceTargetKind, ...] | None:
        path_positions[node] = len(path)
        path.append(node)
        for consumer in adjacency[node]:
            cycle_start = path_positions.get(consumer)
            if cycle_start is not None:
                cycle = tuple(path[cycle_start:])
                start = min(
                    range(len(cycle)),
                    key=lambda position: _materialization_rank(cycle[position]),
                )
                rotated = cycle[start:] + cycle[:start]
                return rotated + (rotated[0],)
            if consumer in exhausted:
                continue
            witness = visit(consumer)
            if witness is not None:
                return witness
        path.pop()
        path_positions.pop(node)
        exhausted.add(node)
        return None

    for node in sorted(nodes, key=_materialization_rank):
        if node in exhausted:
            continue
        witness = visit(node)
        if witness is not None:
            return witness
    raise AssertionError("cycle witness missing for a cyclic dependency graph")


def _canonical_topological_order(
    nodes: tuple[PmxReferenceTargetKind, ...],
    edges: tuple[PmxStructuralTransactionDependencyEdge, ...],
) -> tuple[PmxReferenceTargetKind, ...]:
    indegree = {node: 0 for node in nodes}
    adjacency_lists = {node: [] for node in nodes}
    for edge in edges:
        adjacency_lists[edge.provider_target].append(edge.consumer_target)
        indegree[edge.consumer_target] += 1

    adjacency = {
        node: tuple(sorted(consumers, key=_materialization_rank))
        for node, consumers in adjacency_lists.items()
    }
    ready = [node for node in nodes if indegree[node] == 0]
    ordered: list[PmxReferenceTargetKind] = []
    while ready:
        node = min(ready, key=_materialization_rank)
        ready.remove(node)
        ordered.append(node)
        for consumer in adjacency[node]:
            indegree[consumer] -= 1
            if indegree[consumer] == 0:
                ready.append(consumer)

    if len(ordered) != len(nodes):
        witness = _canonical_cycle_witness(nodes, adjacency)
        rendered = " -> ".join(node.value for node in witness)
        raise ValueError(f"unsupported dependency cycle: {rendered}.")
    return tuple(ordered)


def _build_dependency_evidence(
    nodes: tuple[PmxReferenceTargetKind, ...],
    edges: tuple[PmxStructuralTransactionDependencyEdge, ...],
) -> PmxStructuralTransactionDependencyEvidence:
    canonical_nodes = _validate_and_canonicalize_nodes(nodes)
    validated_edges = _validate_edges(canonical_nodes, edges)

    materialization_order = _canonical_topological_order(
        canonical_nodes,
        validated_edges,
    )

    pair_to_edge = {
        (edge.provider_target, edge.consumer_target): edge
        for edge in validated_edges
    }
    unsupported_pairs = tuple(
        pair
        for pair in pair_to_edge
        if pair not in _SEMANTIC_EDGE_PAIRS
    )
    if unsupported_pairs:
        provider, consumer = min(
            unsupported_pairs,
            key=lambda pair: (
                _materialization_rank(pair[0]),
                _materialization_rank(pair[1]),
            ),
        )
        raise ValueError(
            "unsupported dependency relationship "
            f"{provider.value} -> {consumer.value}."
        )

    canonical_edges = tuple(
        pair_to_edge[pair]
        for pair in _SEMANTIC_EDGE_PAIRS
        if pair in pair_to_edge
    )
    return PmxStructuralTransactionDependencyEvidence(
        nodes=canonical_nodes,
        edges=canonical_edges,
        materialization_order=materialization_order,
    )


def build_structural_transaction_dependency_evidence(
    changed_targets: tuple[PmxReferenceTargetKind, ...],
) -> PmxStructuralTransactionDependencyEvidence:
    """Build contract-fixed dependency evidence for changed target stages."""

    canonical_nodes = _validate_and_canonicalize_nodes(changed_targets)
    node_set = set(canonical_nodes)
    edges = tuple(
        PmxStructuralTransactionDependencyEdge(provider, consumer)
        for provider, consumer in _SEMANTIC_EDGE_PAIRS
        if provider in node_set and consumer in node_set
    )
    return _build_dependency_evidence(canonical_nodes, edges)


__all__ = (
    "PmxStructuralTransactionDependencyEdge",
    "PmxStructuralTransactionDependencyEvidence",
    "build_structural_transaction_dependency_evidence",
)
