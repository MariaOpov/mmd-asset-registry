"""v0.9.1 cross-section coordinated structural-execution regression gates."""

from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from mmd_registry.pmx.collection_transform import (
    PmxCollectionTransform,
    PmxStructuralTransformIntent,
)
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


TARGET_KINDS = tuple(PmxReferenceTargetKind)


def _clean_document():
    from dataclasses import replace

    return replace(
        load_pmx(io.BytesIO(build_pmx_roundtrip_fixture(version=2.1))),
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
    raise AssertionError(f"unhandled target kind {kind!r}")


def _reverse(document, kind: PmxReferenceTargetKind) -> PmxCollectionTransform:
    size = _target_size(document, kind)
    return PmxCollectionTransform(
        kind=kind,
        remap=PmxIndexRemap(
            targets=tuple(reversed(range(size))),
            new_size=size,
        ),
    )


def _identity(document, kind: PmxReferenceTargetKind) -> PmxCollectionTransform:
    return PmxCollectionTransform.identity(kind, _target_size(document, kind))


def _intent_for(
    document,
    *changed_kinds: PmxReferenceTargetKind,
) -> PmxStructuralTransformIntent:
    changed = set(changed_kinds)
    return PmxStructuralTransformIntent(
        transforms=tuple(
            _reverse(document, kind) if kind in changed else _identity(document, kind)
            for kind in TARGET_KINDS
        )
    )


def _full_reverse_intent(document) -> PmxStructuralTransformIntent:
    return _intent_for(document, *TARGET_KINDS)


class V091CrossSectionCoordinatedExecutionTests(unittest.TestCase):
    """Freeze coordinated multi-section execution across all six target domains."""

    def test_explicit_all_kind_identity_matches_implicit_noop(self) -> None:
        source = _clean_document()
        explicit = PmxStructuralTransformIntent(
            transforms=tuple(_identity(source, kind) for kind in TARGET_KINDS)
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

    def test_full_reverse_reports_all_six_changed_kinds_in_canonical_order(self) -> None:
        source = _clean_document()
        preview = preview_pmx_structural_transform(
            source,
            _full_reverse_intent(source),
        )

        self.assertEqual(preview.audit.changed_kinds, TARGET_KINDS)
        self.assertEqual(len(preview.audit.collections), len(TARGET_KINDS))
        for audit, kind in zip(preview.audit.collections, TARGET_KINDS, strict=True):
            self.assertIs(audit.kind, kind)
            self.assertTrue(audit.transform.has_reorder)
            self.assertFalse(audit.transform.has_deletions)

    def test_full_reverse_produces_clean_certified_reference_graph(self) -> None:
        source = _clean_document()
        preview = preview_pmx_structural_transform(
            source,
            _full_reverse_intent(source),
        )

        self.assertEqual(preview.certificate.reference_graph.invalid_targets, ())
        self.assertEqual(preview.certificate.reference_graph.unsupported_states, ())
        self.assertGreater(preview.certificate.edge_count, 0)

    def test_full_reverse_is_deterministic_and_preserves_source_document(self) -> None:
        source = _clean_document()
        source_bytes = serialize_pmx(source)
        intent = _full_reverse_intent(source)

        first = preview_pmx_structural_transform(source, intent)
        second = preview_pmx_structural_transform(source, intent)

        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(first.certificate.document, second.certificate.document)
        self.assertEqual(serialize_pmx(source), source_bytes)

    def test_full_reverse_serialization_reparses_to_independent_preview(self) -> None:
        source = _clean_document()
        intent = _full_reverse_intent(source)
        independent = preview_pmx_structural_transform(source, intent)
        serialization = verify_pmx_structural_serialization(source, intent)

        self.assertEqual(serialization.preview.to_dict(), independent.to_dict())
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

    def test_full_reverse_write_is_distinct_verified_and_source_immutable(self) -> None:
        source = _clean_document()
        source_bytes = serialize_pmx(source)
        intent = _full_reverse_intent(source)
        independent = preview_pmx_structural_transform(source, intent)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "source.pmx"
            output_path = root / "all-six-reverse.pmx"
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

    def test_vertex_and_bone_reverse_coordinate_with_clean_certificate(self) -> None:
        source = _clean_document()
        preview = preview_pmx_structural_transform(
            source,
            _intent_for(
                source,
                PmxReferenceTargetKind.VERTEX,
                PmxReferenceTargetKind.BONE,
            ),
        )

        self.assertEqual(
            preview.audit.changed_kinds,
            (
                PmxReferenceTargetKind.VERTEX,
                PmxReferenceTargetKind.BONE,
            ),
        )
        self.assertEqual(preview.certificate.reference_graph.invalid_targets, ())
        self.assertEqual(preview.certificate.reference_graph.unsupported_states, ())

    def test_texture_and_material_reverse_coordinate_with_clean_certificate(self) -> None:
        source = _clean_document()
        preview = preview_pmx_structural_transform(
            source,
            _intent_for(
                source,
                PmxReferenceTargetKind.TEXTURE,
                PmxReferenceTargetKind.MATERIAL,
            ),
        )

        self.assertEqual(
            preview.audit.changed_kinds,
            (
                PmxReferenceTargetKind.TEXTURE,
                PmxReferenceTargetKind.MATERIAL,
            ),
        )
        self.assertEqual(preview.certificate.reference_graph.invalid_targets, ())
        self.assertEqual(preview.certificate.reference_graph.unsupported_states, ())

    def test_bone_morph_and_rigid_body_reverse_coordinate_cleanly(self) -> None:
        source = _clean_document()
        preview = preview_pmx_structural_transform(
            source,
            _intent_for(
                source,
                PmxReferenceTargetKind.BONE,
                PmxReferenceTargetKind.MORPH,
                PmxReferenceTargetKind.RIGID_BODY,
            ),
        )

        self.assertEqual(
            preview.audit.changed_kinds,
            (
                PmxReferenceTargetKind.BONE,
                PmxReferenceTargetKind.MORPH,
                PmxReferenceTargetKind.RIGID_BODY,
            ),
        )
        self.assertEqual(preview.certificate.reference_graph.invalid_targets, ())
        self.assertEqual(preview.certificate.reference_graph.unsupported_states, ())

    def test_vertex_material_and_rigid_body_reverse_coordinate_soft_body_edges(self) -> None:
        source = _clean_document()
        self.assertTrue(source.soft_bodies)
        preview = preview_pmx_structural_transform(
            source,
            _intent_for(
                source,
                PmxReferenceTargetKind.VERTEX,
                PmxReferenceTargetKind.MATERIAL,
                PmxReferenceTargetKind.RIGID_BODY,
            ),
        )

        self.assertEqual(
            preview.audit.changed_kinds,
            (
                PmxReferenceTargetKind.VERTEX,
                PmxReferenceTargetKind.MATERIAL,
                PmxReferenceTargetKind.RIGID_BODY,
            ),
        )
        self.assertEqual(preview.certificate.reference_graph.invalid_targets, ())
        self.assertEqual(preview.certificate.reference_graph.unsupported_states, ())

    def test_noncanonical_insertion_and_trailing_data_fail_closed(self) -> None:
        source = _clean_document()

        with self.assertRaisesRegex(ValueError, "canonical"):
            PmxStructuralTransformIntent(
                transforms=(
                    _reverse(source, PmxReferenceTargetKind.BONE),
                    _reverse(source, PmxReferenceTargetKind.VERTEX),
                )
            )

        vertex_size = len(source.vertices)
        insertion_capable = PmxIndexRemap(
            targets=tuple(range(vertex_size)),
            new_size=vertex_size + 1,
            new_indices_without_old_source=(vertex_size,),
        )
        with self.assertRaisesRegex(
            ValueError,
            "do not authorize new indices without old sources",
        ):
            PmxCollectionTransform(
                PmxReferenceTargetKind.VERTEX,
                insertion_capable,
            )

        unsafe = load_pmx(io.BytesIO(build_pmx_roundtrip_fixture(version=2.1)))
        self.assertTrue(unsafe.trailing_data)
        with self.assertRaisesRegex(
            PmxStructuralTransformError,
            "trailing_data",
        ):
            verify_pmx_structural_serialization(
                unsafe,
                _full_reverse_intent(unsafe),
            )


if __name__ == "__main__":
    unittest.main()
