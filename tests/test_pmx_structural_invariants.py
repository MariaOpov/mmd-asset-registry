from __future__ import annotations

import io
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
from mmd_registry.pmx.reference_diagnostics import (
    PmxReferenceDiagnostic,
    PmxReferenceDiagnosticCode,
)
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.pmx.structural_invariants import (
    PmxStructuralInvariantCertificate,
    PmxStructuralInvariantError,
    transform_and_certify_pmx_document,
)
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


EXPECTED_RELATIONSHIPS = {
    "surface.vertex",
    "vertex.deform.bdef1.bone",
    "vertex.deform.multi.bone",
    "material.texture",
    "material.sphere_texture",
    "material.toon_texture",
    "bone.parent",
    "bone.tail",
    "bone.inherit_parent",
    "bone.ik_target",
    "bone.ik_link",
    "morph.group.morph",
    "morph.vertex.vertex",
    "morph.bone.bone",
    "morph.uv.vertex",
    "morph.material.material",
    "morph.flip.morph",
    "morph.impulse.rigid_body",
    "display_frame.bone",
    "display_frame.morph",
    "rigid_body.bone",
    "joint.rigid_body_a",
    "joint.rigid_body_b",
    "soft_body.material",
    "soft_body.anchor.rigid_body",
    "soft_body.anchor.vertex",
    "soft_body.pin.vertex",
}


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


def _reverse(
    kind: PmxReferenceTargetKind,
    size: int,
) -> PmxCollectionTransform:
    return _transform(
        kind,
        tuple(reversed(range(size))),
        size,
    )


def _full_reverse_intent(document) -> PmxStructuralTransformIntent:
    return PmxStructuralTransformIntent(
        transforms=(
            _reverse(PmxReferenceTargetKind.VERTEX, len(document.vertices)),
            _reverse(PmxReferenceTargetKind.TEXTURE, len(document.texture_paths)),
            _reverse(PmxReferenceTargetKind.MATERIAL, len(document.materials)),
            _reverse(PmxReferenceTargetKind.BONE, len(document.bones)),
            _reverse(PmxReferenceTargetKind.MORPH, len(document.morphs)),
            _reverse(PmxReferenceTargetKind.RIGID_BODY, len(document.rigid_bodies)),
        )
    )


class StructuralInvariantCertificateTests(unittest.TestCase):
    def test_direct_certificate_construction_self_validates_document(self) -> None:
        source = _document()
        certificate = PmxStructuralInvariantCertificate(document=source)

        self.assertIs(certificate.document, source)
        self.assertFalse(certificate.reference_graph.invalid_targets)
        self.assertFalse(certificate.reference_graph.unsupported_states)

    def test_direct_certificate_rejects_invalid_document(self) -> None:
        source = _document()
        invalid_body = replace(source.rigid_bodies[0], mass=-1.0)
        invalid = replace(
            source,
            rigid_bodies=(invalid_body, source.rigid_bodies[1]),
        )

        with self.assertRaises(PmxValidationError) as raised:
            PmxStructuralInvariantCertificate(document=invalid)

        self.assertEqual(raised.exception.section, "rigid_bodies")
        self.assertEqual(raised.exception.field, "mass")

    def test_direct_certificate_rejects_opaque_trailing_data(self) -> None:
        source = load_pmx(io.BytesIO(build_pmx_roundtrip_fixture()))

        with self.assertRaisesRegex(PmxStructuralInvariantError, "trailing_data"):
            PmxStructuralInvariantCertificate(document=source)

    def test_reference_graph_cannot_be_supplied_by_caller(self) -> None:
        source = _document()
        graph = PmxStructuralInvariantCertificate(document=source).reference_graph

        with self.assertRaises(TypeError):
            PmxStructuralInvariantCertificate(  # type: ignore[call-arg]
                document=source,
                reference_graph=graph,
            )

    def test_full_reverse_transform_receives_certificate(self) -> None:
        source = _document()
        certificate = transform_and_certify_pmx_document(
            source,
            _full_reverse_intent(source),
        )

        self.assertIsInstance(certificate, PmxStructuralInvariantCertificate)
        self.assertEqual(
            certificate.document.texture_paths,
            tuple(reversed(source.texture_paths)),
        )
        self.assertFalse(certificate.reference_graph.invalid_targets)
        self.assertFalse(certificate.reference_graph.unsupported_states)

    def test_certificate_covers_all_frozen_relationship_ids(self) -> None:
        source = _document()
        certificate = transform_and_certify_pmx_document(
            source,
            _full_reverse_intent(source),
        )

        observed = set(dict(certificate.relationship_counts))
        self.assertEqual(observed, EXPECTED_RELATIONSHIPS)

    def test_certificate_target_counts_match_transformed_document(self) -> None:
        source = _document()
        certificate = transform_and_certify_pmx_document(
            source,
            _full_reverse_intent(source),
        )
        counts = certificate.reference_graph.target_counts
        result = certificate.document

        self.assertEqual(counts.vertex, len(result.vertices))
        self.assertEqual(counts.texture, len(result.texture_paths))
        self.assertEqual(counts.material, len(result.materials))
        self.assertEqual(counts.bone, len(result.bones))
        self.assertEqual(counts.morph, len(result.morphs))
        self.assertEqual(counts.rigid_body, len(result.rigid_bodies))

    def test_certificate_to_dict_is_deterministic_and_json_ready(self) -> None:
        source = _document()
        first = transform_and_certify_pmx_document(
            source,
            _full_reverse_intent(source),
        )
        second = transform_and_certify_pmx_document(
            source,
            _full_reverse_intent(source),
        )

        self.assertEqual(first, second)
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(first.to_dict()["reference_diagnostic_count"], 0)
        self.assertEqual(
            set(first.to_dict()["relationship_counts"]),
            EXPECTED_RELATIONSHIPS,
        )

    def test_certificate_is_immutable(self) -> None:
        source = _document()
        certificate = transform_and_certify_pmx_document(
            source,
            PmxStructuralTransformIntent(),
        )

        with self.assertRaises(FrozenInstanceError):
            certificate.document = source  # type: ignore[misc]


class StructuralInvariantGateTests(unittest.TestCase):
    def test_source_document_remains_immutable(self) -> None:
        source = _document()
        baseline = _document()
        transform_and_certify_pmx_document(source, _full_reverse_intent(source))
        self.assertEqual(source, baseline)

    def test_noop_with_opaque_trailing_data_is_not_certifiable(self) -> None:
        source = load_pmx(io.BytesIO(build_pmx_roundtrip_fixture()))

        with self.assertRaisesRegex(PmxStructuralInvariantError, "trailing_data"):
            transform_and_certify_pmx_document(
                source,
                PmxStructuralTransformIntent(),
            )

    def test_validator_failure_is_preserved_without_wrapper(self) -> None:
        source = _document()
        invalid_body = replace(source.rigid_bodies[0], mass=-1.0)
        source = replace(
            source,
            rigid_bodies=(invalid_body, source.rigid_bodies[1]),
        )

        with self.assertRaises(PmxValidationError) as raised:
            transform_and_certify_pmx_document(
                source,
                PmxStructuralTransformIntent(),
            )

        self.assertEqual(raised.exception.section, "rigid_bodies")
        self.assertEqual(raised.exception.record_index, 0)
        self.assertEqual(raised.exception.field, "mass")

    def test_declared_index_width_capacity_is_enforced_by_validator(self) -> None:
        source = _document()
        source = replace(
            source,
            bones=tuple(source.bones[0] for _ in range(129)),
        )

        with self.assertRaises(PmxValidationError) as raised:
            transform_and_certify_pmx_document(
                source,
                PmxStructuralTransformIntent(),
            )

        self.assertEqual(raised.exception.section, "header")
        self.assertEqual(raised.exception.field, "index_sizes.bone")
        self.assertIn("cannot address 129 bone records", raised.exception.reason)

    def test_material_surface_coverage_is_enforced_by_validator(self) -> None:
        source = _document()
        first = replace(source.materials[0], surface_index_count=0)
        source = replace(
            source,
            materials=(first, *source.materials[1:]),
        )

        with self.assertRaises(PmxValidationError) as raised:
            transform_and_certify_pmx_document(
                source,
                PmxStructuralTransformIntent(),
            )

        self.assertEqual(raised.exception.section, "materials")
        self.assertEqual(raised.exception.field, "surface_index_count")

    def test_version_specific_soft_body_rule_is_enforced_by_validator(self) -> None:
        source20 = _document(version=2.0)
        source21 = _document(version=2.1)
        source20 = replace(source20, soft_bodies=source21.soft_bodies)

        with self.assertRaises(PmxValidationError) as raised:
            transform_and_certify_pmx_document(
                source20,
                PmxStructuralTransformIntent(),
            )

        self.assertEqual(raised.exception.section, "soft_bodies")
        self.assertEqual(raised.exception.field, "count")

    def test_validator_runs_before_reference_graph_cross_check(self) -> None:
        source = _document()
        marker = RuntimeError("validator-first-marker")

        with (
            patch(
                "mmd_registry.pmx.structural_invariants.validate_pmx_document",
                side_effect=marker,
            ),
            patch(
                "mmd_registry.pmx.structural_invariants.extract_pmx_reference_graph"
            ) as graph_mock,
        ):
            with self.assertRaisesRegex(RuntimeError, "validator-first-marker"):
                PmxStructuralInvariantCertificate(document=source)

        graph_mock.assert_not_called()

    def test_reference_model_disagreement_fails_closed(self) -> None:
        source = _document()
        certificate = PmxStructuralInvariantCertificate(document=source)
        edge = certificate.reference_graph.edges[0]
        diagnostic = PmxReferenceDiagnostic(
            code=PmxReferenceDiagnosticCode.INVALID_TARGET,
            message="Reference target index is invalid.",
            relationship_id=edge.relationship_id,
            source=edge.source,
            target_kind=edge.target.kind,
            raw_index=edge.target.index,
            target_count=0,
        )

        with patch(
            "mmd_registry.pmx.structural_invariants.diagnose_reference_graph",
            return_value=(diagnostic,),
        ):
            with self.assertRaisesRegex(
                PmxStructuralInvariantError,
                "disagrees with the reference model",
            ):
                PmxStructuralInvariantCertificate(document=source)

    def test_pmx20_structural_transform_can_be_certified(self) -> None:
        source = _document(version=2.0)
        intent = PmxStructuralTransformIntent(
            transforms=(
                _reverse(PmxReferenceTargetKind.TEXTURE, len(source.texture_paths)),
            )
        )

        certificate = transform_and_certify_pmx_document(source, intent)

        self.assertEqual(certificate.document.header.version, 2.0)
        self.assertEqual(certificate.document.soft_bodies, ())
        self.assertFalse(certificate.reference_graph.invalid_targets)
        self.assertFalse(certificate.reference_graph.unsupported_states)

    def test_header_and_non_target_sections_remain_preserved(self) -> None:
        source = _document()
        intent = PmxStructuralTransformIntent(
            transforms=(
                _reverse(PmxReferenceTargetKind.TEXTURE, len(source.texture_paths)),
            )
        )

        certificate = transform_and_certify_pmx_document(source, intent)
        result = certificate.document

        self.assertIs(result.header, source.header)
        self.assertIs(result.model_info, source.model_info)
        self.assertIs(result.geometry, source.geometry)
        self.assertIs(result.display_frames, source.display_frames)
        self.assertIs(result.rigid_bodies, source.rigid_bodies)
        self.assertIs(result.joints, source.joints)
        self.assertIs(result.soft_bodies, source.soft_bodies)

    def test_extra_global_data_remains_opaque_and_preserved(self) -> None:
        source = _document()
        header = replace(source.header, extra_global_data=b"\xaa\x55")
        source = replace(source, header=header)
        intent = PmxStructuralTransformIntent(
            transforms=(
                _reverse(PmxReferenceTargetKind.TEXTURE, len(source.texture_paths)),
            )
        )

        certificate = transform_and_certify_pmx_document(source, intent)

        self.assertIs(certificate.document.header, header)
        self.assertEqual(certificate.document.header.extra_global_data, b"\xaa\x55")


class Cp16BoundaryTests(unittest.TestCase):
    def test_cp16_symbols_are_not_exported_from_public_roots(self) -> None:
        forbidden = (
            "PmxStructuralInvariantCertificate",
            "PmxStructuralInvariantError",
            "transform_and_certify_pmx_document",
        )
        for name in forbidden:
            with self.subTest(name=name):
                self.assertFalse(hasattr(pmx_public, name))
                self.assertFalse(hasattr(services_public, name))


if __name__ == "__main__":
    unittest.main()
