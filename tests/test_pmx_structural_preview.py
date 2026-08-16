from __future__ import annotations

import io
import json
import unittest
from dataclasses import FrozenInstanceError, replace
from unittest.mock import patch

import mmd_registry.pmx as pmx_public
import mmd_registry.services as services_public
from mmd_registry.pmx import PmxValidationError, load_pmx
from mmd_registry.pmx.collection_transform import (
    PmxCollectionTransform,
    PmxStructuralTransformIntent,
)
from mmd_registry.pmx.index_remap import PmxIndexRemap
from mmd_registry.pmx.reference_diagnostics import PmxReferenceDiagnosticCode
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.pmx.structural_invariants import PmxStructuralInvariantError
from mmd_registry.pmx.structural_preview import (
    PMX_STRUCTURAL_PREVIEW_SCHEMA_VERSION,
    PmxStructuralAudit,
    PmxStructuralPreview,
    preview_pmx_structural_transform,
)
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


def _document(*, version: float = 2.1):
    return replace(
        load_pmx(io.BytesIO(build_pmx_roundtrip_fixture(version=version))),
        trailing_data=b"",
    )


def _transform(
    kind: PmxReferenceTargetKind,
    targets: tuple[int | None, ...],
    new_size: int,
) -> PmxCollectionTransform:
    return PmxCollectionTransform(
        kind=kind,
        remap=PmxIndexRemap(targets=targets, new_size=new_size),
    )


def _identity(
    kind: PmxReferenceTargetKind,
    size: int,
) -> PmxCollectionTransform:
    return PmxCollectionTransform.identity(kind, size)


def _reverse(
    kind: PmxReferenceTargetKind,
    size: int,
) -> PmxCollectionTransform:
    return _transform(
        kind,
        tuple(reversed(range(size))),
        size,
    )


def _explicit_identity_intent(document) -> PmxStructuralTransformIntent:
    return PmxStructuralTransformIntent(
        transforms=(
            _identity(PmxReferenceTargetKind.VERTEX, len(document.vertices)),
            _identity(PmxReferenceTargetKind.TEXTURE, len(document.texture_paths)),
            _identity(PmxReferenceTargetKind.MATERIAL, len(document.materials)),
            _identity(PmxReferenceTargetKind.BONE, len(document.bones)),
            _identity(PmxReferenceTargetKind.MORPH, len(document.morphs)),
            _identity(
                PmxReferenceTargetKind.RIGID_BODY,
                len(document.rigid_bodies),
            ),
        )
    )


def _full_reverse_intent(document) -> PmxStructuralTransformIntent:
    return PmxStructuralTransformIntent(
        transforms=(
            _reverse(PmxReferenceTargetKind.VERTEX, len(document.vertices)),
            _reverse(PmxReferenceTargetKind.TEXTURE, len(document.texture_paths)),
            _reverse(PmxReferenceTargetKind.MATERIAL, len(document.materials)),
            _reverse(PmxReferenceTargetKind.BONE, len(document.bones)),
            _reverse(PmxReferenceTargetKind.MORPH, len(document.morphs)),
            _reverse(
                PmxReferenceTargetKind.RIGID_BODY,
                len(document.rigid_bodies),
            ),
        )
    )


class StructuralPreviewContractTests(unittest.TestCase):
    def test_direct_preview_construction_self_derives_evidence(self) -> None:
        source = _document()
        preview = PmxStructuralPreview(
            source_document=source,
            intent=PmxStructuralTransformIntent(),
        )

        self.assertIs(preview.source_document, source)
        self.assertIs(preview.certificate.document, source)
        self.assertIsInstance(preview.audit, PmxStructuralAudit)
        self.assertEqual(len(preview.intent_sha256), 64)

    def test_helper_matches_direct_preview_report(self) -> None:
        source = _document()
        intent = _full_reverse_intent(source)

        direct = PmxStructuralPreview(source_document=source, intent=intent)
        helper = preview_pmx_structural_transform(source, intent)

        self.assertEqual(direct.to_dict(), helper.to_dict())
        self.assertEqual(direct.certificate, helper.certificate)

    def test_derived_evidence_cannot_be_supplied_by_caller(self) -> None:
        source = _document()
        preview = preview_pmx_structural_transform(
            source,
            PmxStructuralTransformIntent(),
        )

        with self.assertRaises(TypeError):
            PmxStructuralPreview(  # type: ignore[call-arg]
                source_document=source,
                intent=PmxStructuralTransformIntent(),
                certificate=preview.certificate,
            )

    def test_preview_is_immutable(self) -> None:
        source = _document()
        preview = preview_pmx_structural_transform(
            source,
            PmxStructuralTransformIntent(),
        )

        with self.assertRaises(FrozenInstanceError):
            preview.intent_sha256 = "0" * 64  # type: ignore[misc]

    def test_wrong_argument_types_fail_before_work(self) -> None:
        source = _document()

        with self.assertRaisesRegex(TypeError, "source_document"):
            PmxStructuralPreview(  # type: ignore[arg-type]
                source_document=object(),
                intent=PmxStructuralTransformIntent(),
            )
        with self.assertRaisesRegex(TypeError, "PmxStructuralTransformIntent"):
            PmxStructuralPreview(  # type: ignore[arg-type]
                source_document=source,
                intent=object(),
            )

    def test_structural_symbols_are_not_publicly_exported(self) -> None:
        forbidden = (
            "PmxStructuralAudit",
            "PmxStructuralPreview",
            "preview_pmx_structural_transform",
        )
        for name in forbidden:
            with self.subTest(name=name):
                self.assertFalse(hasattr(pmx_public, name))
                self.assertFalse(hasattr(services_public, name))


class StructuralPreviewNoopTests(unittest.TestCase):
    def test_empty_intent_has_stable_no_changes_status(self) -> None:
        source = _document()
        preview = preview_pmx_structural_transform(
            source,
            PmxStructuralTransformIntent(),
        )

        self.assertEqual(preview.status, "no_changes")
        self.assertEqual(preview.audit.changed_kinds, ())
        self.assertEqual(preview.audit.changed_node_count, 0)
        self.assertEqual(preview.audit.direct_reference_edge_count, 0)
        self.assertTrue(preview.audit.direct_reference_impact_complete)

    def test_preview_always_resolves_all_six_target_collections(self) -> None:
        source = _document()
        preview = preview_pmx_structural_transform(
            source,
            PmxStructuralTransformIntent(),
        )

        self.assertEqual(
            tuple(item.kind for item in preview.audit.collections),
            tuple(PmxReferenceTargetKind),
        )
        self.assertTrue(
            all(item.transform.is_noop for item in preview.audit.collections)
        )

    def test_absent_and_explicit_identity_have_same_report_and_hash(self) -> None:
        source = _document()
        implicit = preview_pmx_structural_transform(
            source,
            PmxStructuralTransformIntent(),
        )
        explicit = preview_pmx_structural_transform(
            source,
            _explicit_identity_intent(source),
        )

        self.assertEqual(implicit.intent_sha256, explicit.intent_sha256)
        self.assertEqual(implicit.to_dict(), explicit.to_dict())

    def test_intent_hash_is_lowercase_sha256(self) -> None:
        source = _document()
        preview = preview_pmx_structural_transform(
            source,
            PmxStructuralTransformIntent(),
        )

        self.assertRegex(preview.intent_sha256, r"\A[0-9a-f]{64}\Z")

    def test_noop_with_trailing_data_is_not_previewable(self) -> None:
        source = load_pmx(io.BytesIO(build_pmx_roundtrip_fixture()))

        with self.assertRaisesRegex(PmxStructuralInvariantError, "trailing_data"):
            preview_pmx_structural_transform(
                source,
                PmxStructuralTransformIntent(),
            )


class StructuralPreviewTransformAuditTests(unittest.TestCase):
    def test_full_reverse_reports_all_six_changed_kinds(self) -> None:
        source = _document()
        preview = preview_pmx_structural_transform(
            source,
            _full_reverse_intent(source),
        )

        self.assertEqual(preview.status, "changes_pending")
        self.assertEqual(
            preview.audit.changed_kinds,
            tuple(PmxReferenceTargetKind),
        )

    def test_collection_audit_exposes_complete_remap_evidence(self) -> None:
        source = _document()
        texture_transform = _reverse(
            PmxReferenceTargetKind.TEXTURE,
            len(source.texture_paths),
        )
        preview = preview_pmx_structural_transform(
            source,
            PmxStructuralTransformIntent(transforms=(texture_transform,)),
        )
        texture_audit = preview.audit.collections[1]

        self.assertEqual(texture_audit.kind, PmxReferenceTargetKind.TEXTURE)
        self.assertEqual(
            texture_audit.to_dict()["targets"],
            list(texture_transform.remap.targets),
        )
        self.assertEqual(
            texture_audit.to_dict()["old_indices_in_new_order"],
            list(texture_transform.old_indices_in_new_order),
        )
        self.assertTrue(texture_audit.transform.has_reorder)
        self.assertFalse(texture_audit.transform.has_deletions)

    def test_reference_impacts_cover_exactly_changed_old_nodes(self) -> None:
        source = _document()
        preview = preview_pmx_structural_transform(
            source,
            _full_reverse_intent(source),
        )

        expected = [
            (collection.kind, old_index)
            for collection in preview.audit.collections
            for old_index in collection.changed_old_indices
        ]
        observed = [
            (item.node.kind, item.node.index)
            for item in preview.audit.reference_impacts
        ]
        self.assertEqual(observed, expected)
        self.assertEqual(preview.audit.changed_node_count, len(expected))

    def test_reference_impact_new_indices_match_resolved_remaps(self) -> None:
        source = _document()
        preview = preview_pmx_structural_transform(
            source,
            _full_reverse_intent(source),
        )
        collections = {
            item.kind: item for item in preview.audit.collections
        }

        for impact in preview.audit.reference_impacts:
            with self.subTest(kind=impact.node.kind, index=impact.node.index):
                self.assertEqual(
                    impact.new_index,
                    collections[
                        impact.node.kind
                    ].transform.remap.targets[impact.node.index],
                )

    def test_clean_fixture_reference_impact_is_complete(self) -> None:
        source = _document()
        preview = preview_pmx_structural_transform(
            source,
            _full_reverse_intent(source),
        )

        self.assertTrue(preview.audit.direct_reference_impact_complete)
        self.assertTrue(
            all(item.impact.is_complete for item in preview.audit.reference_impacts)
        )

    def test_direct_edge_count_is_unique_not_naive_double_count(self) -> None:
        source = _document()
        preview = preview_pmx_structural_transform(
            source,
            _full_reverse_intent(source),
        )
        naive = sum(
            len(item.impact.inbound_edges) + len(item.impact.outbound_edges)
            for item in preview.audit.reference_impacts
        )

        self.assertGreater(preview.audit.direct_reference_edge_count, 0)
        self.assertLessEqual(preview.audit.direct_reference_edge_count, naive)

    def test_audit_uses_conservative_direct_impact_vocabulary(self) -> None:
        source = _document()
        preview = preview_pmx_structural_transform(
            source,
            _full_reverse_intent(source),
        )
        summary = preview.to_dict()["audit"]["summary"]

        self.assertIn("direct_reference_edge_count", summary)
        self.assertIn("direct_reference_impact_complete", summary)
        self.assertNotIn("affected_reference_edge_count", summary)
        self.assertNotIn("reference_impact_complete", summary)

    def test_intent_hash_changes_when_resolved_mapping_changes(self) -> None:
        source = _document()
        noop = preview_pmx_structural_transform(
            source,
            PmxStructuralTransformIntent(),
        )
        changed = preview_pmx_structural_transform(
            source,
            PmxStructuralTransformIntent(
                transforms=(
                    _reverse(
                        PmxReferenceTargetKind.TEXTURE,
                        len(source.texture_paths),
                    ),
                )
            ),
        )

        self.assertNotEqual(noop.intent_sha256, changed.intent_sha256)

    def test_source_document_remains_immutable(self) -> None:
        source = _document()
        baseline = _document()

        preview_pmx_structural_transform(
            source,
            _full_reverse_intent(source),
        )

        self.assertEqual(source, baseline)

    def test_preview_does_not_call_serializer(self) -> None:
        source = _document()

        with patch(
            "mmd_registry.pmx.writer.serialize_pmx",
            side_effect=AssertionError("CP17 must not serialize"),
        ):
            preview = preview_pmx_structural_transform(
                source,
                _full_reverse_intent(source),
            )

        self.assertEqual(preview.status, "changes_pending")


class StructuralPreviewSourceEvidenceTests(unittest.TestCase):
    def test_deleted_invalid_source_is_reported_but_certified_output_is_clean(self) -> None:
        source = _document()
        last_index = len(source.vertices) - 1
        vertex = source.vertices[last_index]
        bad_deform = replace(vertex.deform, bone_indices=(99, 0, 0, 0))
        bad_vertex = replace(vertex, deform=bad_deform)
        source = replace(
            source,
            geometry=replace(
                source.geometry,
                vertices=(*source.vertices[:-1], bad_vertex),
            ),
        )
        vertex_transform = _transform(
            PmxReferenceTargetKind.VERTEX,
            tuple((*range(last_index), None)),
            last_index,
        )

        preview = preview_pmx_structural_transform(
            source,
            PmxStructuralTransformIntent(transforms=(vertex_transform,)),
        )

        self.assertEqual(
            len(preview.audit.source_reference_diagnostics),
            1,
        )
        self.assertEqual(
            preview.audit.source_reference_diagnostics[0].code,
            PmxReferenceDiagnosticCode.INVALID_TARGET,
        )
        removed = preview.audit.reference_impacts[0]
        self.assertEqual(removed.node.kind, PmxReferenceTargetKind.VERTEX)
        self.assertEqual(removed.node.index, last_index)
        self.assertIsNone(removed.new_index)
        self.assertEqual(len(removed.impact.source_invalid_targets), 1)
        self.assertFalse(preview.certificate.reference_graph.invalid_targets)
        self.assertFalse(preview.certificate.reference_graph.unsupported_states)

    def test_invalid_surviving_semantic_state_still_blocks_preview(self) -> None:
        source = _document()
        invalid_body = replace(source.rigid_bodies[0], mass=-1.0)
        source = replace(
            source,
            rigid_bodies=(invalid_body, source.rigid_bodies[1]),
        )

        with self.assertRaises(PmxValidationError):
            preview_pmx_structural_transform(
                source,
                PmxStructuralTransformIntent(),
            )


class StructuralPreviewReportTests(unittest.TestCase):
    def test_report_uses_existing_preview_vocabulary(self) -> None:
        source = _document()
        preview = preview_pmx_structural_transform(
            source,
            _full_reverse_intent(source),
        )
        report = preview.to_dict()

        self.assertEqual(
            report["preview_schema_version"],
            PMX_STRUCTURAL_PREVIEW_SCHEMA_VERSION,
        )
        self.assertEqual(report["status"], "changes_pending")
        self.assertIs(report["dry_run"], True)
        self.assertEqual(
            set(report),
            {
                "preview_schema_version",
                "status",
                "dry_run",
                "source",
                "intent",
                "output",
                "verification",
                "audit",
            },
        )
        self.assertIs(report["output"]["written"], False)
        self.assertEqual(report["verification"]["invariants"], "passed")
        self.assertEqual(report["verification"]["reference_model"], "passed")
        self.assertEqual(
            report["verification"]["serialization"],
            "not_performed",
        )
        self.assertNotIn("semantic", report["verification"])

    def test_report_is_deterministic_and_json_ready(self) -> None:
        source = _document()
        intent = _full_reverse_intent(source)
        first = preview_pmx_structural_transform(source, intent)
        second = preview_pmx_structural_transform(source, intent)

        self.assertEqual(first.to_dict(), second.to_dict())
        first_json = json.dumps(
            first.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        second_json = json.dumps(
            second.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        self.assertEqual(first_json, second_json)

    def test_report_target_counts_match_source_and_certificate(self) -> None:
        source = _document()
        preview = preview_pmx_structural_transform(
            source,
            _full_reverse_intent(source),
        )
        report = preview.to_dict()

        self.assertEqual(
            report["source"]["target_counts"]["vertex"],
            len(source.vertices),
        )
        self.assertEqual(
            report["output"]["target_counts"]["vertex"],
            len(preview.certificate.document.vertices),
        )
        self.assertEqual(
            report["output"]["reference_diagnostic_count"],
            0,
        )
        self.assertEqual(
            report["output"]["reference_edge_count"],
            preview.certificate.edge_count,
        )
        self.assertGreaterEqual(report["source"]["reference_edge_count"], 0)

    def test_report_contains_deterministic_collection_and_impact_order(self) -> None:
        source = _document()
        preview = preview_pmx_structural_transform(
            source,
            _full_reverse_intent(source),
        )
        report = preview.to_dict()

        self.assertEqual(
            [item["kind"] for item in report["audit"]["collections"]],
            [kind.value for kind in PmxReferenceTargetKind],
        )
        impact_keys = [
            (
                list(PmxReferenceTargetKind).index(
                    PmxReferenceTargetKind(item["kind"])
                ),
                item["old_index"],
            )
            for item in report["audit"]["reference_impacts"]
        ]
        self.assertEqual(impact_keys, sorted(impact_keys))

    def test_pmx20_preview_path_is_supported(self) -> None:
        source = _document(version=2.0)
        intent = PmxStructuralTransformIntent(
            transforms=(
                _reverse(
                    PmxReferenceTargetKind.TEXTURE,
                    len(source.texture_paths),
                ),
            )
        )

        preview = preview_pmx_structural_transform(source, intent)

        self.assertEqual(preview.certificate.document.header.version, 2.0)
        self.assertEqual(preview.certificate.document.soft_bodies, ())
        self.assertEqual(preview.status, "changes_pending")

    def test_extra_global_data_remains_opaque_and_preserved(self) -> None:
        source = _document()
        header = replace(source.header, extra_global_data=b"\xaa\x55")
        source = replace(source, header=header)

        preview = preview_pmx_structural_transform(
            source,
            PmxStructuralTransformIntent(
                transforms=(
                    _reverse(
                        PmxReferenceTargetKind.TEXTURE,
                        len(source.texture_paths),
                    ),
                )
            ),
        )

        self.assertIs(preview.certificate.document.header, header)
        self.assertEqual(
            preview.certificate.document.header.extra_global_data,
            b"\xaa\x55",
        )


class StructuralAuditDefensiveTests(unittest.TestCase):
    def test_audit_rejects_incomplete_collection_coverage(self) -> None:
        with self.assertRaisesRegex(ValueError, "all target kinds"):
            PmxStructuralAudit(
                collections=(),
                reference_impacts=(),
            )


if __name__ == "__main__":
    unittest.main()
