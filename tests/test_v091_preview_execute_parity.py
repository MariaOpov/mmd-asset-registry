"""v0.9.1 preview/execute semantic-parity regression gates."""

from __future__ import annotations

import io
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import mmd_registry.services as services
import mmd_registry.pmx.structural_output as structural_output
from mmd_registry.pmx.collection_transform import (
    PmxCollectionTransform,
    PmxStructuralTransformIntent,
)
from mmd_registry.pmx.index_remap import PmxIndexRemap
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.pmx.structural_output import (
    verify_pmx_structural_serialization,
    write_pmx_structural_transform,
)
from mmd_registry.pmx.structural_preview import (
    preview_pmx_structural_transform,
)
from mmd_registry.pmx.writer import serialize_pmx
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


def _clean_document():
    return replace(
        load_pmx(io.BytesIO(build_pmx_roundtrip_fixture(version=2.1))),
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
            _reverse(
                PmxReferenceTargetKind.RIGID_BODY,
                len(document.rigid_bodies),
            ),
        )
    )


def _texture_reverse_intent(document) -> PmxStructuralTransformIntent:
    return PmxStructuralTransformIntent(
        transforms=(
            _reverse(
                PmxReferenceTargetKind.TEXTURE,
                len(document.texture_paths),
            ),
        )
    )


def _delete_last_vertex_intent(document) -> PmxStructuralTransformIntent:
    size = len(document.vertices)
    if size < 1:
        raise AssertionError("fixture must contain at least one vertex")
    return PmxStructuralTransformIntent(
        transforms=(
            _transform(
                PmxReferenceTargetKind.VERTEX,
                (*range(size - 1), None),
                size - 1,
            ),
        )
    )


def _intent_from_service_order(
    kind: PmxReferenceTargetKind,
    old_indices_in_new_order: tuple[int, ...],
    old_size: int,
) -> PmxStructuralTransformIntent:
    targets: list[int | None] = [None] * old_size
    for new_index, old_index in enumerate(old_indices_in_new_order):
        targets[old_index] = new_index
    return PmxStructuralTransformIntent(
        transforms=(
            _transform(kind, tuple(targets), len(old_indices_in_new_order)),
        )
    )


class V091PreviewExecuteParityTests(unittest.TestCase):
    """Require one certified preview semantics path for preview and execution."""

    def assert_preview_parity(
        self,
        source,
        intent: PmxStructuralTransformIntent,
    ) -> None:
        independent = preview_pmx_structural_transform(source, intent)
        serialization = verify_pmx_structural_serialization(source, intent)

        self.assertEqual(serialization.preview.to_dict(), independent.to_dict())
        self.assertEqual(
            serialization.preview.certificate.document,
            independent.certificate.document,
        )
        self.assertEqual(
            serialization.preview.intent_sha256,
            independent.intent_sha256,
        )
        self.assertEqual(
            serialization.preview.audit.to_dict(),
            independent.audit.to_dict(),
        )
        self.assertEqual(serialization.preview.status, independent.status)

    def test_noop_serialization_uses_exact_preview_semantics(self) -> None:
        source = _clean_document()
        self.assert_preview_parity(
            source,
            PmxStructuralTransformIntent(),
        )

    def test_partial_texture_reorder_uses_exact_preview_semantics(self) -> None:
        source = _clean_document()
        self.assert_preview_parity(
            source,
            _texture_reverse_intent(source),
        )

    def test_all_six_target_reorder_uses_exact_preview_semantics(self) -> None:
        source = _clean_document()
        intent = _full_reverse_intent(source)

        self.assert_preview_parity(source, intent)

        preview = preview_pmx_structural_transform(source, intent)
        self.assertEqual(
            preview.audit.changed_kinds,
            tuple(PmxReferenceTargetKind),
        )

    def test_vertex_deletion_uses_exact_preview_semantics(self) -> None:
        source = _clean_document()
        intent = _delete_last_vertex_intent(source)

        self.assert_preview_parity(source, intent)

        preview = preview_pmx_structural_transform(source, intent)
        vertex_audit = preview.audit.collections[0]
        self.assertTrue(vertex_audit.transform.has_deletions)
        self.assertIn(
            len(source.vertices) - 1,
            vertex_audit.transform.removed_old_indices,
        )

    def test_noop_write_matches_independent_preview(self) -> None:
        source = _clean_document()
        source_bytes = serialize_pmx(source)
        independent = preview_pmx_structural_transform(
            source,
            PmxStructuralTransformIntent(),
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "source.pmx"
            output_path = root / "noop-output.pmx"
            input_path.write_bytes(source_bytes)

            result = write_pmx_structural_transform(
                input_path,
                output_path,
                PmxStructuralTransformIntent(),
            )

            self.assertEqual(
                result.serialization.preview.to_dict(),
                independent.to_dict(),
            )
            self.assertEqual(result.status, "no_changes")
            self.assertEqual(load_pmx(output_path), independent.certificate.document)
            self.assertEqual(input_path.read_bytes(), source_bytes)

    def test_partial_write_matches_independent_preview(self) -> None:
        source = _clean_document()
        source_bytes = serialize_pmx(source)
        intent = _texture_reverse_intent(source)
        independent = preview_pmx_structural_transform(source, intent)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "source.pmx"
            output_path = root / "partial-output.pmx"
            input_path.write_bytes(source_bytes)

            result = write_pmx_structural_transform(
                input_path,
                output_path,
                intent,
            )

            self.assertEqual(
                result.serialization.preview.to_dict(),
                independent.to_dict(),
            )
            self.assertEqual(result.status, "written")
            self.assertEqual(
                result.serialization.preview.intent_sha256,
                independent.intent_sha256,
            )
            self.assertEqual(
                result.serialization.preview.audit.to_dict(),
                independent.audit.to_dict(),
            )
            self.assertEqual(load_pmx(output_path), independent.certificate.document)
            self.assertEqual(input_path.read_bytes(), source_bytes)

    def test_deletion_write_matches_independent_preview(self) -> None:
        source = _clean_document()
        source_bytes = serialize_pmx(source)
        intent = _delete_last_vertex_intent(source)
        independent = preview_pmx_structural_transform(source, intent)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "source.pmx"
            output_path = root / "deletion-output.pmx"
            input_path.write_bytes(source_bytes)

            result = write_pmx_structural_transform(
                input_path,
                output_path,
                intent,
            )

            self.assertEqual(
                result.serialization.preview.to_dict(),
                independent.to_dict(),
            )
            self.assertEqual(
                load_pmx(output_path),
                independent.certificate.document,
            )
            self.assertEqual(
                len(load_pmx(output_path).vertices),
                len(source.vertices) - 1,
            )

    def test_write_calls_preview_once_and_serializes_preview_document(self) -> None:
        source = _clean_document()
        source_bytes = serialize_pmx(source)
        intent = _texture_reverse_intent(source)
        original_preview = structural_output.preview_pmx_structural_transform
        original_serialize = structural_output.serialize_pmx
        serialized_object = None

        def capture_serialize(document):
            nonlocal serialized_object
            serialized_object = document
            return original_serialize(document)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "source.pmx"
            output_path = root / "output.pmx"
            input_path.write_bytes(source_bytes)

            with patch(
                "mmd_registry.pmx.structural_output.preview_pmx_structural_transform",
                wraps=original_preview,
            ) as preview_call, patch(
                "mmd_registry.pmx.structural_output.serialize_pmx",
                side_effect=capture_serialize,
            ):
                result = write_pmx_structural_transform(
                    input_path,
                    output_path,
                    intent,
                )

        preview_call.assert_called_once()
        self.assertIs(
            serialized_object,
            result.serialization.preview.certificate.document,
        )

    def test_preview_failure_stops_before_serialization_and_commit(self) -> None:
        source = _clean_document()
        source_bytes = serialize_pmx(source)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "source.pmx"
            output_path = root / "output.pmx"
            input_path.write_bytes(source_bytes)

            with patch(
                "mmd_registry.pmx.structural_output.preview_pmx_structural_transform",
                side_effect=ValueError("simulated preview failure"),
            ), patch(
                "mmd_registry.pmx.structural_output.serialize_pmx",
            ) as serialize_call, patch(
                "mmd_registry.pmx.structural_output._edit_output._commit_verified_bytes",
            ) as commit_call:
                with self.assertRaisesRegex(ValueError, "preview failure"):
                    write_pmx_structural_transform(
                        input_path,
                        output_path,
                        PmxStructuralTransformIntent(),
                    )

            serialize_call.assert_not_called()
            commit_call.assert_not_called()
            self.assertFalse(output_path.exists())
            self.assertEqual(input_path.read_bytes(), source_bytes)

    def test_service_texture_preview_matches_internal_preview(self) -> None:
        source = _clean_document()
        order = tuple(reversed(range(len(source.texture_paths))))
        request = services.PmxStructuralPreviewRequest(
            (
                services.PmxStructuralCollectionEdit(
                    services.PmxReferenceTargetKind.TEXTURE,
                    order,
                ),
            )
        )
        intent = _intent_from_service_order(
            PmxReferenceTargetKind.TEXTURE,
            order,
            len(source.texture_paths),
        )

        service_result = services.preview_structural_edit(source, request)
        internal = preview_pmx_structural_transform(source, intent)

        self.assertEqual(service_result.to_dict(), internal.to_dict())
        self.assertEqual(service_result.document, internal.certificate.document)
        self.assertEqual(service_result.status, internal.status)

    def test_service_noop_preview_matches_internal_preview(self) -> None:
        source = _clean_document()

        service_result = services.preview_structural_edit(
            source,
            services.PmxStructuralPreviewRequest(),
        )
        internal = preview_pmx_structural_transform(
            source,
            PmxStructuralTransformIntent(),
        )

        self.assertEqual(service_result.to_dict(), internal.to_dict())
        self.assertIs(service_result.document, source)
        self.assertIs(internal.certificate.document, source)


if __name__ == "__main__":
    unittest.main()
