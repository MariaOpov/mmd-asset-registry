"""v0.9.1 material structural-execution regression gates."""

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
from mmd_registry.pmx.document import PmxMaterialMorphOffset
from mmd_registry.pmx.index_remap import PmxIndexRemap
from mmd_registry.pmx.morph_display_remap import PmxMorphDisplayRemapError
from mmd_registry.pmx.physics_reference_remap import PmxPhysicsReferenceRemapError
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


def _material_transform(
    targets: tuple[int | None, ...],
    new_size: int,
) -> PmxCollectionTransform:
    return PmxCollectionTransform(
        kind=PmxReferenceTargetKind.MATERIAL,
        remap=PmxIndexRemap(targets=targets, new_size=new_size),
    )


def _material_reverse_intent(document) -> PmxStructuralTransformIntent:
    size = len(document.materials)
    return PmxStructuralTransformIntent(
        transforms=(
            _material_transform(tuple(reversed(range(size))), size),
        )
    )


def _material_delete_intent(document, deleted_index: int) -> PmxStructuralTransformIntent:
    size = len(document.materials)
    if not 0 <= deleted_index < size:
        raise AssertionError("deleted material index must be inside the fixture domain")
    targets = tuple(
        None
        if old_index == deleted_index
        else old_index
        if old_index < deleted_index
        else old_index - 1
        for old_index in range(size)
    )
    return PmxStructuralTransformIntent(
        transforms=(
            _material_transform(targets, size - 1),
        )
    )


def _mapped_optional(index: int, transform: PmxCollectionTransform) -> int:
    if index == -1:
        return -1
    mapped = transform.remap.target_for(index)
    if mapped is None:
        raise AssertionError("test expected a surviving referenced material")
    return mapped


def _surface_segments(document) -> tuple[tuple[int, ...], ...]:
    segments: list[tuple[int, ...]] = []
    offset = 0
    for material in document.materials:
        end = offset + material.surface_index_count
        segments.append(document.surface_indices[offset:end])
        offset = end
    if offset != len(document.surface_indices):
        raise AssertionError("fixture material/surface partition must be complete")
    return tuple(segments)


def _clear_incoming_material_references(document, deleted_index: int):
    morphs = []
    for morph in document.morphs:
        if morph.morph_type != 8:
            morphs.append(morph)
            continue
        offsets = tuple(
            replace(offset, material_index=-1)
            if isinstance(offset, PmxMaterialMorphOffset)
            and offset.material_index == deleted_index
            else offset
            for offset in morph.offsets
        )
        morphs.append(
            morph if offsets == morph.offsets else replace(morph, offsets=offsets)
        )

    soft_bodies = tuple(
        replace(body, material_index=-1)
        if body.material_index == deleted_index
        else body
        for body in document.soft_bodies
    )
    return replace(
        document,
        morphs=tuple(morphs),
        soft_bodies=soft_bodies,
    )


class V091MaterialStructuralExecutionTests(unittest.TestCase):
    """Freeze end-to-end material keep/delete/reorder execution semantics."""

    def test_explicit_material_identity_matches_implicit_noop_preview(self) -> None:
        source = _clean_document()
        size = len(source.materials)
        explicit = PmxStructuralTransformIntent(
            transforms=(
                PmxCollectionTransform.identity(
                    PmxReferenceTargetKind.MATERIAL,
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

    def test_material_reorder_moves_owned_surfaces_and_remaps_incoming_refs(self) -> None:
        source = _clean_document()
        self.assertGreaterEqual(len(source.materials), 2)
        intent = _material_reverse_intent(source)
        transform = intent.transforms[0]
        preview = preview_pmx_structural_transform(source, intent)
        result = preview.certificate.document

        self.assertEqual(result.materials, tuple(reversed(source.materials)))

        source_segments = _surface_segments(source)
        expected_surfaces = tuple(
            vertex_index
            for old_material_index in transform.old_indices_in_new_order
            for vertex_index in source_segments[old_material_index]
        )
        self.assertEqual(result.surface_indices, expected_surfaces)
        self.assertEqual(
            sum(material.surface_index_count for material in result.materials),
            len(result.surface_indices),
        )

        for original_morph, rewritten_morph in zip(
            source.morphs,
            result.morphs,
            strict=True,
        ):
            if original_morph.morph_type != 8:
                continue
            for original_offset, rewritten_offset in zip(
                original_morph.offsets,
                rewritten_morph.offsets,
                strict=True,
            ):
                self.assertIsInstance(original_offset, PmxMaterialMorphOffset)
                self.assertIsInstance(rewritten_offset, PmxMaterialMorphOffset)
                self.assertEqual(
                    rewritten_offset.material_index,
                    _mapped_optional(original_offset.material_index, transform),
                )

        for original_body, rewritten_body in zip(
            source.soft_bodies,
            result.soft_bodies,
            strict=True,
        ):
            self.assertEqual(
                rewritten_body.material_index,
                _mapped_optional(original_body.material_index, transform),
            )

    def test_material_reorder_changes_only_material_target_kind(self) -> None:
        source = _clean_document()
        preview = preview_pmx_structural_transform(
            source,
            _material_reverse_intent(source),
        )

        self.assertEqual(
            preview.audit.changed_kinds,
            (PmxReferenceTargetKind.MATERIAL,),
        )
        self.assertEqual(len(preview.audit.collections), 6)
        material_audit = preview.audit.collections[2]
        self.assertIs(material_audit.kind, PmxReferenceTargetKind.MATERIAL)
        self.assertTrue(material_audit.transform.has_reorder)
        self.assertFalse(material_audit.transform.has_deletions)

    def test_material_reorder_serialization_reparses_to_certified_preview(self) -> None:
        source = _clean_document()
        intent = _material_reverse_intent(source)
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

    def test_material_reorder_write_is_distinct_verified_and_source_immutable(self) -> None:
        source = _clean_document()
        source_bytes = serialize_pmx(source)
        intent = _material_reverse_intent(source)
        independent = preview_pmx_structural_transform(source, intent)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "source.pmx"
            output_path = root / "material-reorder.pmx"
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

    def test_safe_material_deletion_removes_owned_segment_without_width_resize(self) -> None:
        source = _clean_document()
        self.assertGreaterEqual(len(source.materials), 2)
        deleted_index = len(source.materials) - 1
        source = _clear_incoming_material_references(source, deleted_index)
        source_segments = _surface_segments(source)
        expected_surfaces = tuple(
            vertex_index
            for material_index, segment in enumerate(source_segments)
            if material_index != deleted_index
            for vertex_index in segment
        )
        source_bytes = serialize_pmx(source)
        intent = _material_delete_intent(source, deleted_index)
        independent = preview_pmx_structural_transform(source, intent)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "source.pmx"
            output_path = root / "material-delete.pmx"
            input_path.write_bytes(source_bytes)

            result = write_pmx_structural_transform(
                input_path,
                output_path,
                intent,
            )
            written = load_pmx(output_path)

            self.assertEqual(written, independent.certificate.document)
            self.assertEqual(len(written.materials), len(source.materials) - 1)
            self.assertEqual(written.surface_indices, expected_surfaces)
            self.assertEqual(
                sum(material.surface_index_count for material in written.materials),
                len(written.surface_indices),
            )
            self.assertEqual(
                written.header.index_sizes.material,
                source.header.index_sizes.material,
            )
            self.assertEqual(
                result.serialization.reparsed_certificate.reference_graph.invalid_targets,
                (),
            )
            self.assertEqual(input_path.read_bytes(), source_bytes)

    def test_deleting_referenced_material_fails_closed_before_output(self) -> None:
        source = _clean_document()
        deleted_index = 0
        expected_exception: type[ValueError]

        material_offset_location: tuple[int, int] | None = None
        for morph_index, morph in enumerate(source.morphs):
            if morph.morph_type != 8 or not morph.offsets:
                continue
            for offset_index, offset in enumerate(morph.offsets):
                if isinstance(offset, PmxMaterialMorphOffset):
                    material_offset_location = (morph_index, offset_index)
                    break
            if material_offset_location is not None:
                break

        if material_offset_location is not None:
            morph_index, offset_index = material_offset_location
            morph = source.morphs[morph_index]
            offsets = list(morph.offsets)
            offsets[offset_index] = replace(
                offsets[offset_index],
                material_index=deleted_index,
            )
            morphs = list(source.morphs)
            morphs[morph_index] = replace(morph, offsets=tuple(offsets))
            source = replace(source, morphs=tuple(morphs))
            expected_exception = PmxMorphDisplayRemapError
        elif source.soft_bodies:
            source = replace(
                source,
                soft_bodies=(
                    replace(source.soft_bodies[0], material_index=deleted_index),
                    *source.soft_bodies[1:],
                ),
            )
            expected_exception = PmxPhysicsReferenceRemapError
        else:
            self.fail("fixture must expose a material morph or soft body reference")

        source_bytes = serialize_pmx(source)
        intent = _material_delete_intent(source, deleted_index)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "source.pmx"
            output_path = root / "must-not-exist.pmx"
            input_path.write_bytes(source_bytes)

            with self.assertRaisesRegex(
                expected_exception,
                rf"references removed material index {deleted_index}",
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

    def test_material_sentinels_remain_sentinels_under_reorder(self) -> None:
        source = _clean_document()

        morphs = []
        for morph in source.morphs:
            if morph.morph_type != 8:
                morphs.append(morph)
                continue
            offsets = tuple(
                replace(offset, material_index=-1)
                if isinstance(offset, PmxMaterialMorphOffset)
                else offset
                for offset in morph.offsets
            )
            morphs.append(replace(morph, offsets=offsets))

        soft_bodies = tuple(
            replace(body, material_index=-1)
            for body in source.soft_bodies
        )
        source = replace(
            source,
            morphs=tuple(morphs),
            soft_bodies=soft_bodies,
        )

        preview = preview_pmx_structural_transform(
            source,
            _material_reverse_intent(source),
        )
        result = preview.certificate.document

        for morph in result.morphs:
            if morph.morph_type != 8:
                continue
            for offset in morph.offsets:
                self.assertIsInstance(offset, PmxMaterialMorphOffset)
                self.assertEqual(offset.material_index, -1)
        self.assertTrue(
            all(body.material_index == -1 for body in result.soft_bodies)
        )

    def test_material_transform_old_size_mismatch_fails_closed(self) -> None:
        source = _clean_document()
        size = len(source.materials)
        bad_intent = PmxStructuralTransformIntent(
            transforms=(
                PmxCollectionTransform.identity(
                    PmxReferenceTargetKind.MATERIAL,
                    size + 1,
                ),
            )
        )

        with self.assertRaisesRegex(
            PmxStructuralTransformError,
            r"material transform old_size .* does not match source collection size",
        ):
            preview_pmx_structural_transform(source, bad_intent)

    def test_material_insertion_mapping_is_not_authorized(self) -> None:
        source = _clean_document()
        size = len(source.materials)
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
                PmxReferenceTargetKind.MATERIAL,
                insertion_capable,
            )

    def test_material_execution_fails_closed_on_opaque_trailing_data(self) -> None:
        unsafe = load_pmx(io.BytesIO(build_pmx_roundtrip_fixture(version=2.1)))
        self.assertTrue(unsafe.trailing_data)
        intent = _material_reverse_intent(unsafe)

        with self.assertRaisesRegex(
            PmxStructuralTransformError,
            "trailing_data",
        ):
            verify_pmx_structural_serialization(unsafe, intent)


if __name__ == "__main__":
    unittest.main()
