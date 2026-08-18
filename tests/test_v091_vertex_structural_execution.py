"""v0.9.1 vertex structural-execution regression gates."""

from __future__ import annotations

import io
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from mmd_registry.pmx.collection_transform import (
    PmxCollectionTransform,
    PmxStructuralTransformIntent,
)
from mmd_registry.pmx.geometry_material_remap import PmxReferenceRemapError
from mmd_registry.pmx.index_remap import PmxIndexRemap
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.pmx.structural_orchestrator import PmxStructuralTransformError
from mmd_registry.pmx.structural_output import (
    verify_pmx_structural_serialization,
    write_pmx_structural_transform,
)
from mmd_registry.pmx.structural_preview import preview_pmx_structural_transform
from mmd_registry.pmx.writer import serialize_pmx
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


def _clean_document():
    return replace(
        load_pmx(io.BytesIO(build_pmx_roundtrip_fixture(version=2.1))),
        trailing_data=b"",
    )


def _vertex_transform(
    targets: tuple[int | None, ...],
    new_size: int,
) -> PmxCollectionTransform:
    return PmxCollectionTransform(
        kind=PmxReferenceTargetKind.VERTEX,
        remap=PmxIndexRemap(targets=targets, new_size=new_size),
    )


def _vertex_reverse_intent(document) -> PmxStructuralTransformIntent:
    size = len(document.vertices)
    return PmxStructuralTransformIntent(
        transforms=(
            _vertex_transform(tuple(reversed(range(size))), size),
        )
    )


def _vertex_delete_last_intent(document) -> PmxStructuralTransformIntent:
    size = len(document.vertices)
    if size < 1:
        raise AssertionError("fixture must contain at least one vertex")
    return PmxStructuralTransformIntent(
        transforms=(
            _vertex_transform((*range(size - 1), None), size - 1),
        )
    )


def _vertex_delete_first_intent(document) -> PmxStructuralTransformIntent:
    size = len(document.vertices)
    if size < 2:
        raise AssertionError("fixture must contain at least two vertices")
    return PmxStructuralTransformIntent(
        transforms=(
            _vertex_transform(
                (None, *range(size - 1)),
                size - 1,
            ),
        )
    )


def _mapped_reverse(index: int, size: int) -> int:
    return size - 1 - index


class V091VertexStructuralExecutionTests(unittest.TestCase):
    """Freeze end-to-end vertex keep/delete/reorder execution semantics."""

    def test_explicit_vertex_identity_matches_implicit_noop_preview(self) -> None:
        source = _clean_document()
        size = len(source.vertices)
        explicit = PmxStructuralTransformIntent(
            transforms=(
                PmxCollectionTransform.identity(
                    PmxReferenceTargetKind.VERTEX,
                    size,
                ),
            )
        )

        implicit_preview = preview_pmx_structural_transform(
            source,
            PmxStructuralTransformIntent(),
        )
        explicit_preview = preview_pmx_structural_transform(source, explicit)

        self.assertEqual(explicit_preview.status, "no_changes")
        self.assertEqual(explicit_preview.to_dict(), implicit_preview.to_dict())
        self.assertEqual(
            explicit_preview.intent_sha256,
            implicit_preview.intent_sha256,
        )
        self.assertIs(explicit_preview.certificate.document, source)

    def test_vertex_reorder_reorders_records_and_all_incoming_vertex_references(self) -> None:
        source = _clean_document()
        intent = _vertex_reverse_intent(source)
        preview = preview_pmx_structural_transform(source, intent)
        result = preview.certificate.document
        size = len(source.vertices)

        self.assertEqual(result.vertices, tuple(reversed(source.vertices)))
        self.assertEqual(
            result.surface_indices,
            tuple(_mapped_reverse(index, size) for index in source.surface_indices),
        )

        for source_morph, result_morph in zip(source.morphs, result.morphs, strict=True):
            self.assertEqual(source_morph.morph_type, result_morph.morph_type)
            if source_morph.morph_type not in (1, 3, 4, 5, 6, 7):
                continue
            for source_offset, result_offset in zip(
                source_morph.offsets,
                result_morph.offsets,
                strict=True,
            ):
                self.assertEqual(
                    result_offset.vertex_index,
                    _mapped_reverse(source_offset.vertex_index, size),
                )

        for source_body, result_body in zip(
            source.soft_bodies,
            result.soft_bodies,
            strict=True,
        ):
            for source_anchor, result_anchor in zip(
                source_body.anchors,
                result_body.anchors,
                strict=True,
            ):
                self.assertEqual(
                    result_anchor.vertex_index,
                    _mapped_reverse(source_anchor.vertex_index, size),
                )
            self.assertEqual(
                result_body.pinned_vertex_indices,
                tuple(
                    _mapped_reverse(index, size)
                    for index in source_body.pinned_vertex_indices
                ),
            )

    def test_vertex_reorder_changes_only_vertex_target_kind(self) -> None:
        source = _clean_document()
        preview = preview_pmx_structural_transform(
            source,
            _vertex_reverse_intent(source),
        )

        self.assertEqual(
            preview.audit.changed_kinds,
            (PmxReferenceTargetKind.VERTEX,),
        )
        self.assertEqual(len(preview.audit.collections), 6)
        vertex_audit = preview.audit.collections[0]
        self.assertTrue(vertex_audit.transform.has_reorder)
        self.assertFalse(vertex_audit.transform.has_deletions)

    def test_vertex_reorder_serialization_reparses_to_certified_preview(self) -> None:
        source = _clean_document()
        intent = _vertex_reverse_intent(source)
        independent = preview_pmx_structural_transform(source, intent)
        serialization = verify_pmx_structural_serialization(source, intent)

        self.assertEqual(
            serialization.preview.to_dict(),
            independent.to_dict(),
        )
        self.assertEqual(
            serialization.reparsed_certificate.document,
            independent.certificate.document,
        )
        self.assertEqual(
            serialization.reparsed_certificate.reference_graph.invalid_targets,
            (),
        )
        self.assertEqual(
            serialization.reparsed_certificate.reference_graph.unsupported_states,
            (),
        )

    def test_vertex_reorder_write_is_distinct_verified_and_source_immutable(self) -> None:
        source = _clean_document()
        source_bytes = serialize_pmx(source)
        intent = _vertex_reverse_intent(source)
        independent = preview_pmx_structural_transform(source, intent)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "source.pmx"
            output_path = root / "vertex-reorder.pmx"
            input_path.write_bytes(source_bytes)

            result = write_pmx_structural_transform(
                input_path,
                output_path,
                intent,
            )

            self.assertEqual(result.status, "written")
            self.assertEqual(load_pmx(output_path), independent.certificate.document)
            self.assertEqual(
                output_path.read_bytes(),
                result.serialization.serialized_bytes,
            )
            self.assertEqual(input_path.read_bytes(), source_bytes)
            self.assertNotEqual(input_path.resolve(), output_path.resolve())

    def test_safe_last_vertex_deletion_executes_without_dangling_references(self) -> None:
        source = _clean_document()
        source_bytes = serialize_pmx(source)
        intent = _vertex_delete_last_intent(source)
        independent = preview_pmx_structural_transform(source, intent)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "source.pmx"
            output_path = root / "vertex-delete.pmx"
            input_path.write_bytes(source_bytes)

            result = write_pmx_structural_transform(
                input_path,
                output_path,
                intent,
            )
            written = load_pmx(output_path)

            self.assertEqual(written, independent.certificate.document)
            self.assertEqual(len(written.vertices), len(source.vertices) - 1)
            self.assertEqual(
                result.serialization.reparsed_certificate.reference_graph.invalid_targets,
                (),
            )
            self.assertEqual(
                result.serialization.reparsed_certificate.reference_graph.unsupported_states,
                (),
            )
            self.assertEqual(input_path.read_bytes(), source_bytes)

    def test_safe_vertex_deletion_does_not_resize_declared_vertex_index_width(self) -> None:
        source = _clean_document()
        intent = _vertex_delete_last_intent(source)
        serialization = verify_pmx_structural_serialization(source, intent)

        self.assertEqual(
            serialization.reparsed_certificate.document.header.index_sizes.vertex,
            source.header.index_sizes.vertex,
        )
        self.assertEqual(
            len(serialization.reparsed_certificate.document.vertices),
            len(source.vertices) - 1,
        )

    def test_deleting_surface_referenced_vertex_fails_closed_before_output(self) -> None:
        source = _clean_document()
        self.assertIn(0, source.surface_indices)
        source_bytes = serialize_pmx(source)
        intent = _vertex_delete_first_intent(source)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "source.pmx"
            output_path = root / "must-not-exist.pmx"
            input_path.write_bytes(source_bytes)

            with self.assertRaisesRegex(
                PmxReferenceRemapError,
                r"references removed vertex index 0",
            ):
                write_pmx_structural_transform(
                    input_path,
                    output_path,
                    intent,
                )

            self.assertFalse(output_path.exists())
            self.assertEqual(input_path.read_bytes(), source_bytes)
            self.assertEqual(
                list(root.glob(f".{output_path.name}.*.tmp")),
                [],
            )

    def test_vertex_transform_old_size_mismatch_fails_closed(self) -> None:
        source = _clean_document()
        size = len(source.vertices)
        bad_intent = PmxStructuralTransformIntent(
            transforms=(
                PmxCollectionTransform.identity(
                    PmxReferenceTargetKind.VERTEX,
                    size + 1,
                ),
            )
        )

        with self.assertRaisesRegex(
            PmxStructuralTransformError,
            r"vertex transform old_size .* does not match source collection size",
        ):
            preview_pmx_structural_transform(source, bad_intent)

    def test_vertex_insertion_mapping_is_not_authorized(self) -> None:
        source = _clean_document()
        size = len(source.vertices)
        insertion_capable = PmxIndexRemap(
            targets=tuple(range(size)),
            new_size=size + 1,
            new_indices_without_old_source=(size,),
        )

        with self.assertRaisesRegex(
            ValueError,
            r"do not authorize new indices without old sources",
        ):
            PmxCollectionTransform(
                PmxReferenceTargetKind.VERTEX,
                insertion_capable,
            )

    def test_vertex_execution_fails_closed_on_opaque_trailing_data(self) -> None:
        unsafe = load_pmx(io.BytesIO(build_pmx_roundtrip_fixture(version=2.1)))
        self.assertTrue(unsafe.trailing_data)
        intent = _vertex_reverse_intent(unsafe)

        with self.assertRaisesRegex(
            PmxStructuralTransformError,
            "trailing_data",
        ):
            verify_pmx_structural_serialization(unsafe, intent)


if __name__ == "__main__":
    unittest.main()
