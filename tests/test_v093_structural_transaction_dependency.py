"""Freeze v0.9.3 deterministic structural dependency evidence."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, is_dataclass
from itertools import combinations, permutations
import importlib
import inspect
import unittest

import mmd_registry
import mmd_registry.pmx as pmx
import mmd_registry.services as services
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind


DEPENDENCY_MODULE_NAME = "mmd_registry.pmx.structural_transaction_dependency"
CANONICAL_NODE_ORDER = tuple(PmxReferenceTargetKind)
MATERIALIZATION_TIE_ORDER = (
    PmxReferenceTargetKind.TEXTURE,
    PmxReferenceTargetKind.MATERIAL,
    PmxReferenceTargetKind.BONE,
    PmxReferenceTargetKind.VERTEX,
    PmxReferenceTargetKind.RIGID_BODY,
    PmxReferenceTargetKind.MORPH,
)
SEMANTIC_EDGE_PAIRS = (
    (PmxReferenceTargetKind.TEXTURE, PmxReferenceTargetKind.MATERIAL),
    (PmxReferenceTargetKind.BONE, PmxReferenceTargetKind.VERTEX),
    (PmxReferenceTargetKind.BONE, PmxReferenceTargetKind.RIGID_BODY),
    (PmxReferenceTargetKind.MATERIAL, PmxReferenceTargetKind.MORPH),
    (PmxReferenceTargetKind.BONE, PmxReferenceTargetKind.MORPH),
    (PmxReferenceTargetKind.VERTEX, PmxReferenceTargetKind.MORPH),
    (PmxReferenceTargetKind.RIGID_BODY, PmxReferenceTargetKind.MORPH),
)


def _dependency_module():
    return importlib.import_module(DEPENDENCY_MODULE_NAME)


def _edge(
    provider: PmxReferenceTargetKind,
    consumer: PmxReferenceTargetKind,
):
    return _dependency_module().PmxStructuralTransactionDependencyEdge(
        provider,
        consumer,
    )


def _build(changed_targets):
    return _dependency_module().build_structural_transaction_dependency_evidence(
        changed_targets
    )


def _expected_order(
    nodes: tuple[PmxReferenceTargetKind, ...],
    pairs: tuple[
        tuple[PmxReferenceTargetKind, PmxReferenceTargetKind],
        ...,
    ],
) -> tuple[PmxReferenceTargetKind, ...]:
    rank = {node: position for position, node in enumerate(MATERIALIZATION_TIE_ORDER)}
    remaining = list(nodes)
    ordered: list[PmxReferenceTargetKind] = []
    while remaining:
        ready = tuple(
            node
            for node in remaining
            if all(
                consumer is not node or provider in ordered
                for provider, consumer in pairs
            )
        )
        node = min(ready, key=rank.__getitem__)
        remaining.remove(node)
        ordered.append(node)
    return tuple(ordered)


class V093StructuralTransactionDependencyTests(unittest.TestCase):
    """Keep CP09 deterministic, PMX-specific and internal."""

    def test_model_is_frozen_slotted_internal_dependency_evidence(self) -> None:
        dependency = _dependency_module()
        expected_exports = (
            "PmxStructuralTransactionDependencyEdge",
            "PmxStructuralTransactionDependencyEvidence",
            "build_structural_transaction_dependency_evidence",
        )
        self.assertEqual(dependency.__all__, expected_exports)
        for name in expected_exports:
            self.assertFalse(hasattr(mmd_registry, name), name)
            self.assertFalse(hasattr(pmx, name), name)
            self.assertFalse(hasattr(services, name), name)

        edge = _edge(
            PmxReferenceTargetKind.TEXTURE,
            PmxReferenceTargetKind.MATERIAL,
        )
        evidence = _build(
            (
                PmxReferenceTargetKind.TEXTURE,
                PmxReferenceTargetKind.MATERIAL,
            )
        )
        for value in (edge, evidence):
            self.assertTrue(is_dataclass(value))
            self.assertFalse(hasattr(value, "__dict__"))

        self.assertEqual(
            tuple(field.name for field in fields(edge)),
            ("provider_target", "consumer_target"),
        )
        self.assertEqual(
            tuple(field.name for field in fields(evidence)),
            ("nodes", "edges", "materialization_order"),
        )
        with self.assertRaises(FrozenInstanceError):
            edge.consumer_target = PmxReferenceTargetKind.BONE
        with self.assertRaises(FrozenInstanceError):
            evidence.nodes = ()

        source = inspect.getsource(dependency)
        self.assertNotIn("mmd_registry.services", source)
        self.assertNotIn("structural_transaction_reference", source)
        for forbidden in (
            "preview_structural_transaction",
            "apply_structural_transaction",
            "execute_structural_transaction",
            "open(",
        ):
            self.assertNotIn(forbidden, source)

    def test_complete_graph_has_exact_edges_and_released_safe_order(self) -> None:
        evidence = _build(tuple(reversed(CANONICAL_NODE_ORDER)))
        self.assertEqual(evidence.nodes, CANONICAL_NODE_ORDER)
        self.assertEqual(
            tuple(
                (edge.provider_target, edge.consumer_target)
                for edge in evidence.edges
            ),
            SEMANTIC_EDGE_PAIRS,
        )
        self.assertEqual(
            evidence.materialization_order,
            MATERIALIZATION_TIE_ORDER,
        )

        for request_order in permutations(CANONICAL_NODE_ORDER):
            with self.subTest(request_order=request_order):
                self.assertEqual(_build(request_order), evidence)

    def test_every_target_subset_uses_fixed_edges_and_tie_order(self) -> None:
        for size in range(len(CANONICAL_NODE_ORDER) + 1):
            for selected in combinations(CANONICAL_NODE_ORDER, size):
                expected_nodes = tuple(
                    node for node in CANONICAL_NODE_ORDER if node in selected
                )
                expected_pairs = tuple(
                    pair
                    for pair in SEMANTIC_EDGE_PAIRS
                    if pair[0] in selected and pair[1] in selected
                )
                evidence = _build(tuple(reversed(selected)))
                with self.subTest(selected=selected):
                    self.assertEqual(evidence.nodes, expected_nodes)
                    self.assertEqual(
                        tuple(
                            (edge.provider_target, edge.consumer_target)
                            for edge in evidence.edges
                        ),
                        expected_pairs,
                    )
                    self.assertEqual(
                        evidence.materialization_order,
                        _expected_order(expected_nodes, expected_pairs),
                    )

                    positions = {
                        node: position
                        for position, node in enumerate(
                            evidence.materialization_order
                        )
                    }
                    for provider, consumer in expected_pairs:
                        self.assertLess(positions[provider], positions[consumer])

    def test_invalid_or_duplicate_nodes_and_edges_fail_closed(self) -> None:
        dependency = _dependency_module()
        edge_type = dependency.PmxStructuralTransactionDependencyEdge
        evidence_type = dependency.PmxStructuralTransactionDependencyEvidence

        cases = (
            (
                lambda: _build([]),
                TypeError,
                r"changed_targets|nodes must be a tuple",
            ),
            (
                lambda: _build((PmxReferenceTargetKind.TEXTURE, "material")),
                TypeError,
                r"nodes\[1\].*PmxReferenceTargetKind",
            ),
            (
                lambda: _build(
                    (
                        PmxReferenceTargetKind.TEXTURE,
                        PmxReferenceTargetKind.TEXTURE,
                    )
                ),
                ValueError,
                r"cannot repeat target texture",
            ),
            (
                lambda: edge_type("texture", PmxReferenceTargetKind.MATERIAL),
                TypeError,
                r"provider_target.*PmxReferenceTargetKind",
            ),
            (
                lambda: edge_type(PmxReferenceTargetKind.TEXTURE, "material"),
                TypeError,
                r"consumer_target.*PmxReferenceTargetKind",
            ),
            (
                lambda: evidence_type([], (), ()),
                TypeError,
                r"nodes must be a tuple",
            ),
            (
                lambda: evidence_type((), [], ()),
                TypeError,
                r"edges must be a tuple",
            ),
            (
                lambda: evidence_type((), (), []),
                TypeError,
                r"materialization_order must be a tuple",
            ),
            (
                lambda: evidence_type(
                    (
                        PmxReferenceTargetKind.MATERIAL,
                        PmxReferenceTargetKind.TEXTURE,
                    ),
                    (),
                    (
                        PmxReferenceTargetKind.TEXTURE,
                        PmxReferenceTargetKind.MATERIAL,
                    ),
                ),
                ValueError,
                r"canonical target-kind evidence order",
            ),
            (
                lambda: evidence_type(
                    (
                        PmxReferenceTargetKind.TEXTURE,
                        PmxReferenceTargetKind.MATERIAL,
                    ),
                    (),
                    (
                        PmxReferenceTargetKind.TEXTURE,
                        PmxReferenceTargetKind.MATERIAL,
                    ),
                ),
                ValueError,
                r"exact applicable semantic dependencies",
            ),
            (
                lambda: evidence_type(
                    (
                        PmxReferenceTargetKind.TEXTURE,
                        PmxReferenceTargetKind.MATERIAL,
                    ),
                    (
                        edge_type(
                            PmxReferenceTargetKind.TEXTURE,
                            PmxReferenceTargetKind.MATERIAL,
                        ),
                    ),
                    (
                        PmxReferenceTargetKind.MATERIAL,
                        PmxReferenceTargetKind.TEXTURE,
                    ),
                ),
                ValueError,
                r"materialization_order must equal the canonical",
            ),
        )
        for build, error, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(error, message):
                    build()

        duplicate = _edge(
            PmxReferenceTargetKind.TEXTURE,
            PmxReferenceTargetKind.MATERIAL,
        )
        with self.assertRaisesRegex(
            ValueError,
            r"cannot repeat texture -> material",
        ):
            dependency._build_dependency_evidence(
                (
                    PmxReferenceTargetKind.TEXTURE,
                    PmxReferenceTargetKind.MATERIAL,
                ),
                (duplicate, duplicate),
            )

    def test_missing_nodes_and_unsupported_relationships_are_explicit(self) -> None:
        dependency = _dependency_module()
        cases = (
            (
                (PmxReferenceTargetKind.MATERIAL,),
                (
                    _edge(
                        PmxReferenceTargetKind.TEXTURE,
                        PmxReferenceTargetKind.MATERIAL,
                    ),
                ),
                r"missing provider node texture",
            ),
            (
                (PmxReferenceTargetKind.TEXTURE,),
                (
                    _edge(
                        PmxReferenceTargetKind.TEXTURE,
                        PmxReferenceTargetKind.MATERIAL,
                    ),
                ),
                r"missing consumer node material",
            ),
            (
                (
                    PmxReferenceTargetKind.TEXTURE,
                    PmxReferenceTargetKind.BONE,
                ),
                (
                    _edge(
                        PmxReferenceTargetKind.TEXTURE,
                        PmxReferenceTargetKind.BONE,
                    ),
                ),
                r"unsupported dependency relationship texture -> bone",
            ),
            (
                (
                    PmxReferenceTargetKind.TEXTURE,
                    PmxReferenceTargetKind.MATERIAL,
                ),
                (
                    _edge(
                        PmxReferenceTargetKind.MATERIAL,
                        PmxReferenceTargetKind.TEXTURE,
                    ),
                ),
                r"unsupported dependency relationship material -> texture",
            ),
        )
        for nodes, edges, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    dependency._build_dependency_evidence(nodes, edges)

    def test_cycles_report_one_canonical_directed_witness(self) -> None:
        dependency = _dependency_module()
        cases = (
            (
                (
                    PmxReferenceTargetKind.MATERIAL,
                    PmxReferenceTargetKind.TEXTURE,
                ),
                (
                    _edge(
                        PmxReferenceTargetKind.MATERIAL,
                        PmxReferenceTargetKind.TEXTURE,
                    ),
                    _edge(
                        PmxReferenceTargetKind.TEXTURE,
                        PmxReferenceTargetKind.MATERIAL,
                    ),
                ),
                "texture -> material -> texture",
            ),
            (
                (
                    PmxReferenceTargetKind.MORPH,
                    PmxReferenceTargetKind.VERTEX,
                    PmxReferenceTargetKind.BONE,
                ),
                (
                    _edge(
                        PmxReferenceTargetKind.MORPH,
                        PmxReferenceTargetKind.BONE,
                    ),
                    _edge(
                        PmxReferenceTargetKind.VERTEX,
                        PmxReferenceTargetKind.MORPH,
                    ),
                    _edge(
                        PmxReferenceTargetKind.BONE,
                        PmxReferenceTargetKind.VERTEX,
                    ),
                ),
                "bone -> vertex -> morph -> bone",
            ),
        )
        for nodes, edges, witness in cases:
            messages: set[str] = set()
            for node_order in permutations(nodes):
                for edge_order in permutations(edges):
                    with self.assertRaises(ValueError) as caught:
                        dependency._build_dependency_evidence(
                            node_order,
                            edge_order,
                        )
                    messages.add(str(caught.exception))
            with self.subTest(witness=witness):
                self.assertEqual(
                    messages,
                    {f"unsupported dependency cycle: {witness}."},
                )


if __name__ == "__main__":
    unittest.main()
