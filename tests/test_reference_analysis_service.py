"""Stable public service contracts for PMX reference analysis."""

from __future__ import annotations

import io
import unittest
from dataclasses import FrozenInstanceError, replace
from unittest.mock import patch

import mmd_registry.services as services
from mmd_registry.diagnostics import (
    PmxServiceDiagnosticCode,
    PmxServiceError,
    PmxServiceOperation,
)
from mmd_registry.pmx.reference_diagnostics import PmxReferenceDiagnosticCode
from tests.mmd_fixtures import build_pmx_bone, build_pmx_structure


PRIVATE_DETAIL = r"C:\\private\\秘密-model.pmx"


class ReferenceAnalysisServiceTests(unittest.TestCase):
    """Freeze the additive v0.9 public reference-analysis service."""

    def test_public_service_surface_is_additive_and_exact(self) -> None:
        legacy = (
            "PmxDocumentMetadata",
            "PmxDocumentValidationResult",
            "apply_edit",
            "get_capabilities",
            "inspect_document",
            "load_document",
            "preview_edit",
            "validate_document",
        )
        expected = legacy + (
            "PmxReferenceAnalysisResult",
            "PmxReferenceDiagnostic",
            "PmxReferenceDiagnosticCode",
            "PmxReferenceImpact",
            "PmxReferenceNode",
            "PmxReferenceTargetKind",
            "analyze_reference_node",
            "analyze_references",
            "PmxStructuralCollectionEdit",
            "PmxStructuralPreviewRequest",
            "PmxStructuralPreviewResult",
            "preview_structural_edit",
            "PmxStructuralEditRequest",
            "PmxStructuralExecutionResult",
            "apply_structural_edit",
        )

        self.assertEqual(services.__all__, expected)
        self.assertEqual(services.__all__[: len(legacy)], legacy)
        self.assertEqual(len(services.__all__), len(set(services.__all__)))

    def test_service_operations_add_reference_analysis_without_changing_legacy_order(
        self,
    ) -> None:
        self.assertEqual(
            tuple(operation.value for operation in PmxServiceOperation),
            (
                "load_document",
                "inspect_document",
                "validate_document",
                "analyze_references",
                "analyze_reference_node",
                "preview_edit",
                "apply_edit",
                "preview_structural_edit",
                "apply_structural_edit",
            ),
        )

    def test_analysis_preserves_invalid_reference_evidence_without_prevalidation(
        self,
    ) -> None:
        source = build_pmx_structure(
            deform_types=(0,),
            surface_indices=(),
            materials=(),
            bones=(build_pmx_bone(),),
        )
        valid_document = services.load_document(io.BytesIO(source))
        document = replace(
            valid_document,
            geometry=replace(
                valid_document.geometry,
                surface_indices=(9, 0, 0),
            ),
        )

        with patch("mmd_registry.services.validate_pmx_document") as validator:
            result = services.analyze_references(document)

        validator.assert_not_called()
        self.assertFalse(result.is_clean)
        self.assertEqual(len(result.graph.invalid_targets), 1)
        self.assertEqual(len(result.graph.unsupported_states), 0)
        self.assertEqual(len(result.diagnostics), 1)

        diagnostic = result.diagnostics[0]
        self.assertEqual(
            diagnostic.code,
            PmxReferenceDiagnosticCode.INVALID_TARGET,
        )
        self.assertEqual(diagnostic.relationship_id, "surface.vertex")
        self.assertEqual(diagnostic.raw_index, 9)
        self.assertEqual(diagnostic.target_count, 1)
        self.assertEqual(
            result.relationship_counts,
            (
                ("surface.vertex", 2),
                ("vertex.deform.bdef1.bone", 1),
            ),
        )

        with self.assertRaises(ValueError):
            services.PmxReferenceAnalysisResult(
                graph=result.graph,
                diagnostics=(),
            )

        self.assertEqual(
            result.to_dict(),
            {
                "is_clean": False,
                "target_counts": {
                    "vertex": 1,
                    "texture": 0,
                    "material": 0,
                    "bone": 1,
                    "morph": 0,
                    "rigid_body": 0,
                },
                "edge_count": 3,
                "relationship_counts": {
                    "surface.vertex": 2,
                    "vertex.deform.bdef1.bone": 1,
                },
                "invalid_target_count": 1,
                "unsupported_state_count": 0,
                "diagnostics": [diagnostic.to_dict()],
            },
        )

    def test_node_analysis_reuses_one_snapshot_for_inbound_and_outbound_impact(
        self,
    ) -> None:
        source = build_pmx_structure(
            deform_types=(),
            surface_indices=(),
            materials=(),
            bones=(
                build_pmx_bone(local_name="Root"),
                build_pmx_bone(
                    local_name="Child",
                    parent_bone_index=0,
                ),
            ),
        )
        document = services.load_document(io.BytesIO(source))
        analysis = services.analyze_references(document)

        root = services.PmxReferenceNode(
            services.PmxReferenceTargetKind.BONE,
            0,
        )
        child = services.PmxReferenceNode(
            services.PmxReferenceTargetKind.BONE,
            1,
        )

        with patch(
            "mmd_registry.services.extract_pmx_reference_graph",
            side_effect=AssertionError("node query must not re-extract"),
        ):
            root_impact = services.analyze_reference_node(analysis, root)
            child_impact = services.analyze_reference_node(analysis, child)

        self.assertIsInstance(root_impact, services.PmxReferenceImpact)
        self.assertEqual(
            tuple(edge.relationship_id for edge in root_impact.inbound_edges),
            ("bone.parent",),
        )
        self.assertEqual(root_impact.outbound_edges, ())
        self.assertTrue(root_impact.is_complete)

        self.assertEqual(child_impact.inbound_edges, ())
        self.assertEqual(
            tuple(edge.relationship_id for edge in child_impact.outbound_edges),
            ("bone.parent",),
        )
        self.assertTrue(child_impact.is_complete)

    def test_analysis_result_is_immutable_hashable_and_validates_shape(self) -> None:
        document = services.load_document(
            io.BytesIO(
                build_pmx_structure(
                    deform_types=(),
                    surface_indices=(),
                    materials=(),
                )
            )
        )
        result = services.analyze_references(document)

        self.assertTrue(result.is_clean)
        self.assertEqual(result.relationship_counts, ())
        self.assertEqual(hash(result), hash(result))
        with self.assertRaises(FrozenInstanceError):
            result.diagnostics = ()  # type: ignore[misc]

        with self.assertRaises(TypeError):
            services.PmxReferenceAnalysisResult(  # type: ignore[arg-type]
                graph=object(),
                diagnostics=(),
            )
        with self.assertRaises(TypeError):
            services.PmxReferenceAnalysisResult(
                graph=result.graph,
                diagnostics=[],  # type: ignore[arg-type]
            )

    def test_service_failures_are_structured_and_redacted(self) -> None:
        with self.assertRaises(PmxServiceError) as analyze_error:
            services.analyze_references(object())  # type: ignore[arg-type]

        self.assertEqual(
            analyze_error.exception.diagnostic.code,
            PmxServiceDiagnosticCode.INVALID_ARGUMENT,
        )
        self.assertEqual(
            analyze_error.exception.diagnostic.operation,
            PmxServiceOperation.ANALYZE_REFERENCES,
        )

        document = services.load_document(
            io.BytesIO(
                build_pmx_structure(
                    deform_types=(),
                    surface_indices=(),
                    materials=(),
                )
            )
        )
        analysis = services.analyze_references(document)

        with self.assertRaises(PmxServiceError) as node_error:
            services.analyze_reference_node(
                analysis,
                object(),  # type: ignore[arg-type]
            )

        self.assertEqual(
            node_error.exception.diagnostic.code,
            PmxServiceDiagnosticCode.INVALID_ARGUMENT,
        )
        self.assertEqual(
            node_error.exception.diagnostic.operation,
            PmxServiceOperation.ANALYZE_REFERENCE_NODE,
        )

        with patch(
            "mmd_registry.services.extract_pmx_reference_graph",
            side_effect=RuntimeError(PRIVATE_DETAIL),
        ):
            with self.assertRaises(PmxServiceError) as internal_error:
                services.analyze_references(document)

        payload = internal_error.exception.to_dict()
        self.assertEqual(payload["code"], "service_internal_error")
        self.assertEqual(payload["operation"], "analyze_references")
        self.assertNotIn(PRIVATE_DETAIL, repr(payload))
        self.assertNotIn("RuntimeError", repr(payload))

    def test_missing_node_fails_through_service_boundary(self) -> None:
        document = services.load_document(
            io.BytesIO(
                build_pmx_structure(
                    deform_types=(),
                    surface_indices=(),
                    materials=(),
                    bones=(build_pmx_bone(),),
                )
            )
        )
        analysis = services.analyze_references(document)
        missing = services.PmxReferenceNode(
            services.PmxReferenceTargetKind.BONE,
            1,
        )

        with self.assertRaises(PmxServiceError) as raised:
            services.analyze_reference_node(analysis, missing)

        self.assertEqual(
            raised.exception.diagnostic.code,
            PmxServiceDiagnosticCode.INVALID_ARGUMENT,
        )
        self.assertEqual(
            raised.exception.diagnostic.operation,
            PmxServiceOperation.ANALYZE_REFERENCE_NODE,
        )


if __name__ == "__main__":
    unittest.main()
