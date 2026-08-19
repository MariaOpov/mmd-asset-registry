"""CP20 adversarial integration matrix for reference-safe structural editing."""

from __future__ import annotations

import io
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import mmd_registry.pmx as pmx_public
import mmd_registry.services as services
from mmd_registry.diagnostics import (
    PmxServiceDiagnosticCode,
    PmxServiceError,
    PmxServiceOperation,
)
from mmd_registry.pmx import load_pmx
from mmd_registry.pmx.collection_transform import (
    PmxCollectionTransform,
    PmxStructuralTransformIntent,
)
from mmd_registry.pmx.index_remap import PmxIndexRemap
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.pmx.structural_output import (
    verify_pmx_structural_serialization,
    write_pmx_structural_transform,
)
from mmd_registry.pmx.structural_preview import preview_pmx_structural_transform
from mmd_registry.pmx.writer import serialize_pmx
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


TARGET_KINDS = tuple(PmxReferenceTargetKind)


def _clean_document(*, version: float = 2.1):
    return replace(
        load_pmx(io.BytesIO(build_pmx_roundtrip_fixture(version=version))),
        trailing_data=b"",
    )


def _target_size(document, kind: PmxReferenceTargetKind) -> int:
    if kind is PmxReferenceTargetKind.VERTEX:
        return len(document.vertices)
    if kind is PmxReferenceTargetKind.TEXTURE:
        return len(document.texture_paths)
    if kind is PmxReferenceTargetKind.MATERIAL:
        return len(document.materials)
    if kind is PmxReferenceTargetKind.BONE:
        return len(document.bones)
    if kind is PmxReferenceTargetKind.MORPH:
        return len(document.morphs)
    if kind is PmxReferenceTargetKind.RIGID_BODY:
        return len(document.rigid_bodies)
    raise AssertionError(f"unexpected target kind: {kind!r}")


def _reverse_transform(
    document,
    kind: PmxReferenceTargetKind,
) -> PmxCollectionTransform:
    size = _target_size(document, kind)
    return PmxCollectionTransform(
        kind=kind,
        remap=PmxIndexRemap(
            targets=tuple(reversed(range(size))),
            new_size=size,
        ),
    )


def _full_reverse_intent(document) -> PmxStructuralTransformIntent:
    return PmxStructuralTransformIntent(
        transforms=tuple(_reverse_transform(document, kind) for kind in TARGET_KINDS)
    )


def _full_reverse_request(
    document,
    *,
    request_order: tuple[PmxReferenceTargetKind, ...] = TARGET_KINDS,
) -> services.PmxStructuralPreviewRequest:
    return services.PmxStructuralPreviewRequest(
        tuple(
            services.PmxStructuralCollectionEdit(
                kind,
                tuple(reversed(range(_target_size(document, kind)))),
            )
            for kind in request_order
        )
    )


class StructuralAdversarialIntegrationTests(unittest.TestCase):
    def test_public_full_reverse_matches_internal_preview_for_all_six_targets(self) -> None:
        source = _clean_document()
        service_result = services.preview_structural_edit(
            source,
            _full_reverse_request(source),
        )
        internal = preview_pmx_structural_transform(
            source,
            _full_reverse_intent(source),
        )

        self.assertEqual(service_result.status, "changes_pending")
        self.assertEqual(service_result.document, internal.certificate.document)
        self.assertEqual(
            service_result.to_dict()["intent"]["changed_kinds"],
            [kind.value for kind in TARGET_KINDS],
        )
        self.assertEqual(
            service_result.to_dict()["output"]["reference_diagnostic_count"],
            0,
        )

    def test_public_request_order_is_normalized_without_changing_semantics(self) -> None:
        source = _clean_document()
        canonical = services.preview_structural_edit(
            source,
            _full_reverse_request(source),
        )
        reversed_request = services.preview_structural_edit(
            source,
            _full_reverse_request(
                source,
                request_order=tuple(reversed(TARGET_KINDS)),
            ),
        )

        self.assertEqual(reversed_request.document, canonical.document)
        self.assertEqual(reversed_request.to_dict(), canonical.to_dict())

    def test_public_full_reverse_does_not_mutate_source_document(self) -> None:
        source = _clean_document()
        baseline = _clean_document()

        services.preview_structural_edit(source, _full_reverse_request(source))

        self.assertEqual(source, baseline)

    def test_public_noop_fails_closed_on_opaque_trailing_data(self) -> None:
        source = load_pmx(io.BytesIO(build_pmx_roundtrip_fixture()))

        with self.assertRaises(PmxServiceError) as raised:
            services.preview_structural_edit(
                source,
                services.PmxStructuralPreviewRequest(),
            )

        self.assertEqual(
            raised.exception.diagnostic.operation,
            PmxServiceOperation.PREVIEW_STRUCTURAL_EDIT,
        )
        self.assertEqual(
            raised.exception.diagnostic.code,
            PmxServiceDiagnosticCode.STRUCTURAL_PREVIEW_FAILED,
        )
        self.assertNotIn("trailing_data", repr(raised.exception.to_dict()))

    def test_public_delete_of_referenced_texture_fails_closed_without_mutation(self) -> None:
        source = _clean_document()
        baseline = _clean_document()
        self.assertGreaterEqual(len(source.texture_paths), 3)
        survivors = tuple(range(1, len(source.texture_paths)))
        request = services.PmxStructuralPreviewRequest(
            (
                services.PmxStructuralCollectionEdit(
                    PmxReferenceTargetKind.TEXTURE,
                    survivors,
                ),
            )
        )

        with self.assertRaises(PmxServiceError) as raised:
            services.preview_structural_edit(source, request)

        self.assertEqual(
            raised.exception.diagnostic.code,
            PmxServiceDiagnosticCode.STRUCTURAL_PREVIEW_FAILED,
        )
        self.assertEqual(source, baseline)

    def test_public_noop_preserves_index_capacity_failure_as_document_invalid(self) -> None:
        source = _clean_document()
        invalid = replace(
            source,
            bones=tuple(source.bones[0] for _ in range(129)),
        )

        with self.assertRaises(PmxServiceError) as raised:
            services.preview_structural_edit(
                invalid,
                services.PmxStructuralPreviewRequest(),
            )

        self.assertEqual(
            raised.exception.diagnostic.code,
            PmxServiceDiagnosticCode.DOCUMENT_INVALID,
        )
        self.assertEqual(
            raised.exception.diagnostic.operation,
            PmxServiceOperation.PREVIEW_STRUCTURAL_EDIT,
        )
        details = dict(raised.exception.diagnostic.details)
        self.assertEqual(details["section"], "header")
        self.assertEqual(details["field"], "index_sizes.bone")

    def test_coordinated_delete_can_remove_invalid_source_without_prevalidation(self) -> None:
        source = _clean_document()
        bad_material = replace(source.materials[0], texture_index=99)
        soft_body = replace(source.soft_bodies[0], material_index=-1)
        source = replace(
            source,
            materials=(bad_material, source.materials[1]),
            soft_bodies=(soft_body,),
        )
        morph_survivors = tuple(
            index for index in range(len(source.morphs)) if index != 8
        )
        request = services.PmxStructuralPreviewRequest(
            (
                services.PmxStructuralCollectionEdit(
                    PmxReferenceTargetKind.MATERIAL,
                    (1,),
                ),
                services.PmxStructuralCollectionEdit(
                    PmxReferenceTargetKind.MORPH,
                    morph_survivors,
                ),
            )
        )

        result = services.preview_structural_edit(source, request)
        report = result.to_dict()

        self.assertEqual(len(result.document.materials), 1)
        self.assertNotIn(8, tuple(morph.morph_type for morph in result.document.morphs))
        self.assertGreater(report["source"]["reference_diagnostic_count"], 0)
        self.assertEqual(report["output"]["reference_diagnostic_count"], 0)

    def test_pmx20_full_reverse_preview_and_serialization_remain_compatible(self) -> None:
        source = _clean_document(version=2.0)
        service_result = services.preview_structural_edit(
            source,
            _full_reverse_request(source),
        )
        verified = verify_pmx_structural_serialization(
            source,
            _full_reverse_intent(source),
        )

        self.assertEqual(service_result.document.header.version, 2.0)
        self.assertEqual(service_result.document.soft_bodies, ())
        self.assertEqual(
            verified.reparsed_certificate.document,
            service_result.document,
        )
        self.assertEqual(verified.to_dict()["verification"]["semantic"], "passed")

    def test_public_preview_and_verified_serialization_agree_on_intended_document(self) -> None:
        source = _clean_document()
        service_result = services.preview_structural_edit(
            source,
            _full_reverse_request(source),
        )
        verified = verify_pmx_structural_serialization(
            source,
            _full_reverse_intent(source),
        )

        self.assertEqual(
            verified.preview.certificate.document,
            service_result.document,
        )
        self.assertEqual(
            verified.reparsed_certificate.document,
            service_result.document,
        )
        self.assertEqual(
            service_result.to_dict()["verification"]["serialization"],
            "not_performed",
        )
        self.assertEqual(
            verified.to_dict()["verification"]["serialization"],
            "passed",
        )
        self.assertEqual(
            verified.to_dict()["verification"]["semantic"],
            "passed",
        )

    def test_verified_serialization_is_repeatable_byte_for_byte(self) -> None:
        source = _clean_document()
        intent = _full_reverse_intent(source)

        first = verify_pmx_structural_serialization(source, intent)
        second = verify_pmx_structural_serialization(source, intent)

        self.assertEqual(first.serialized_bytes, second.serialized_bytes)
        self.assertEqual(first.output_sha256, second.output_sha256)
        self.assertEqual(first.to_dict(), second.to_dict())

    def test_full_reverse_verified_write_matches_public_preview_and_preserves_source(self) -> None:
        source = _clean_document()
        source_bytes = serialize_pmx(source)
        expected = services.preview_structural_edit(
            source,
            _full_reverse_request(source),
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            input_path = root / "source.pmx"
            output_path = root / "output.pmx"
            input_path.write_bytes(source_bytes)

            result = write_pmx_structural_transform(
                input_path,
                output_path,
                _full_reverse_intent(source),
            )

            self.assertEqual(input_path.read_bytes(), source_bytes)
            self.assertTrue(output_path.is_file())
            self.assertEqual(load_pmx(output_path), expected.document)
            self.assertEqual(result.to_dict()["verification"]["semantic"], "passed")
            self.assertEqual(
                set(root.iterdir()),
                {input_path, output_path},
            )

    def test_public_execution_does_not_expose_raw_structural_writer(self) -> None:
        self.assertFalse(hasattr(services, "write_pmx_structural_transform"))
        self.assertFalse(hasattr(services, "PmxStructuralWriteResult"))
        self.assertFalse(hasattr(pmx_public, "write_pmx_structural_transform"))
        self.assertTrue(services.get_capabilities().structural_write)


if __name__ == "__main__":
    unittest.main()
