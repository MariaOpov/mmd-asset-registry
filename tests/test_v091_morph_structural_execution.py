"""v0.9.1 morph structural-execution regression gates."""

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
from mmd_registry.pmx.document import (
    PmxFlipMorphOffset,
    PmxGroupMorphOffset,
    PmxUvMorphOffset,
)
from mmd_registry.pmx.index_remap import PmxIndexRemap
from mmd_registry.pmx.morph_display_remap import (
    PmxMorphDisplayRemapError,
    transform_morph_collection_references,
)
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


def _morph_transform(
    targets: tuple[int | None, ...],
    new_size: int,
) -> PmxCollectionTransform:
    return PmxCollectionTransform(
        kind=PmxReferenceTargetKind.MORPH,
        remap=PmxIndexRemap(targets=targets, new_size=new_size),
    )


def _morph_reverse_intent(document) -> PmxStructuralTransformIntent:
    size = len(document.morphs)
    return PmxStructuralTransformIntent(
        transforms=(
            _morph_transform(tuple(reversed(range(size))), size),
        )
    )


def _morph_delete_intent(document, deleted_index: int) -> PmxStructuralTransformIntent:
    size = len(document.morphs)
    if not 0 <= deleted_index < size:
        raise AssertionError("deleted morph index must be inside the fixture domain")
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
            _morph_transform(targets, size - 1),
        )
    )


def _mapped_required(index: int, transform: PmxCollectionTransform) -> int:
    mapped = transform.remap.target_for(index)
    if mapped is None:
        raise AssertionError("test expected a surviving required morph reference")
    return mapped


def _controlled_self_reference_source():
    source = _clean_document()
    if len(source.morphs) < 2:
        raise AssertionError("morph execution fixture requires at least two morphs")

    morphs = list(source.morphs)
    morphs[0] = replace(
        morphs[0],
        morph_type=0,
        morph_type_name="group",
        offsets=(PmxGroupMorphOffset(morph_index=1, weight=0.5),),
    )
    morphs[1] = replace(
        morphs[1],
        morph_type=9,
        morph_type_name="flip",
        offsets=(PmxFlipMorphOffset(morph_index=0, weight=0.5),),
    )
    return replace(source, morphs=tuple(morphs))


def _clear_incoming_morph_references(document, deleted_index: int):
    if len(document.morphs) < 2:
        raise AssertionError("safe deletion fixture requires at least two morphs")
    fallback = 0 if deleted_index != 0 else 1

    morphs = []
    for old_index, morph in enumerate(document.morphs):
        if old_index == deleted_index:
            morphs.append(morph)
            continue
        if morph.morph_type not in (0, 9):
            morphs.append(morph)
            continue

        rewritten_offsets = tuple(
            replace(offset, morph_index=fallback)
            if isinstance(offset, (PmxGroupMorphOffset, PmxFlipMorphOffset))
            and offset.morph_index == deleted_index
            else offset
            for offset in morph.offsets
        )
        morphs.append(
            morph
            if rewritten_offsets == morph.offsets
            else replace(morph, offsets=rewritten_offsets)
        )

    display_frames = []
    for frame in document.display_frames:
        elements = tuple(
            replace(element, target_index=fallback)
            if element.target_type == "morph"
            and element.target_index == deleted_index
            else element
            for element in frame.elements
        )
        display_frames.append(
            frame if elements == frame.elements else replace(frame, elements=elements)
        )

    return replace(
        document,
        morphs=tuple(morphs),
        display_frames=tuple(display_frames),
    )


class V091MorphStructuralExecutionTests(unittest.TestCase):
    """Freeze end-to-end morph keep/delete/reorder execution semantics."""

    def test_explicit_morph_identity_matches_implicit_noop_preview(self) -> None:
        source = _clean_document()
        size = len(source.morphs)
        explicit = PmxStructuralTransformIntent(
            transforms=(
                PmxCollectionTransform.identity(
                    PmxReferenceTargetKind.MORPH,
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

    def test_morph_reorder_moves_sources_and_remaps_group_flip_self_references(self) -> None:
        source = _controlled_self_reference_source()
        intent = _morph_reverse_intent(source)
        transform = intent.transforms[0]
        result = preview_pmx_structural_transform(
            source,
            intent,
        ).certificate.document

        for old_index, original in enumerate(source.morphs):
            new_index = _mapped_required(old_index, transform)
            rewritten = result.morphs[new_index]

            self.assertEqual(rewritten.local_name, original.local_name)
            self.assertEqual(rewritten.panel, original.panel)
            self.assertEqual(rewritten.morph_type, original.morph_type)
            self.assertEqual(rewritten.morph_type_name, original.morph_type_name)
            self.assertEqual(len(rewritten.offsets), len(original.offsets))

            for original_offset, rewritten_offset in zip(
                original.offsets,
                rewritten.offsets,
                strict=True,
            ):
                if isinstance(
                    original_offset,
                    (PmxGroupMorphOffset, PmxFlipMorphOffset),
                ):
                    self.assertIs(type(rewritten_offset), type(original_offset))
                    self.assertEqual(
                        rewritten_offset.morph_index,
                        _mapped_required(original_offset.morph_index, transform),
                    )
                    self.assertEqual(
                        replace(
                            rewritten_offset,
                            morph_index=original_offset.morph_index,
                        ),
                        original_offset,
                    )
                else:
                    self.assertEqual(rewritten_offset, original_offset)

    def test_morph_reorder_remaps_display_frame_morph_targets_only(self) -> None:
        source = _controlled_self_reference_source()
        intent = _morph_reverse_intent(source)
        transform = intent.transforms[0]
        result = preview_pmx_structural_transform(
            source,
            intent,
        ).certificate.document

        self.assertEqual(len(result.display_frames), len(source.display_frames))
        for original_frame, rewritten_frame in zip(
            source.display_frames,
            result.display_frames,
            strict=True,
        ):
            self.assertEqual(
                len(rewritten_frame.elements),
                len(original_frame.elements),
            )
            for original_element, rewritten_element in zip(
                original_frame.elements,
                rewritten_frame.elements,
                strict=True,
            ):
                self.assertEqual(
                    rewritten_element.target_type,
                    original_element.target_type,
                )
                if original_element.target_type == "morph":
                    self.assertEqual(
                        rewritten_element.target_index,
                        _mapped_required(
                            original_element.target_index,
                            transform,
                        ),
                    )
                else:
                    self.assertEqual(
                        rewritten_element.target_index,
                        original_element.target_index,
                    )

    def test_morph_reorder_changes_only_morph_target_kind(self) -> None:
        source = _controlled_self_reference_source()
        preview = preview_pmx_structural_transform(
            source,
            _morph_reverse_intent(source),
        )

        self.assertEqual(
            preview.audit.changed_kinds,
            (PmxReferenceTargetKind.MORPH,),
        )
        self.assertEqual(len(preview.audit.collections), 6)
        morph_audit = preview.audit.collections[4]
        self.assertIs(morph_audit.kind, PmxReferenceTargetKind.MORPH)
        self.assertTrue(morph_audit.transform.has_reorder)
        self.assertFalse(morph_audit.transform.has_deletions)

    def test_morph_reorder_serialization_reparses_to_certified_preview(self) -> None:
        source = _controlled_self_reference_source()
        intent = _morph_reverse_intent(source)
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

    def test_morph_reorder_write_is_distinct_verified_and_source_immutable(self) -> None:
        source = _controlled_self_reference_source()
        source_bytes = serialize_pmx(source)
        intent = _morph_reverse_intent(source)
        independent = preview_pmx_structural_transform(source, intent)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "source.pmx"
            output_path = root / "morph-reorder.pmx"
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

    def test_safe_morph_deletion_ignores_deleted_source_outgoing_reference_without_width_resize(
        self,
    ) -> None:
        source = _clean_document()
        self.assertGreaterEqual(len(source.morphs), 2)
        deleted_index = len(source.morphs) - 1
        fallback = 0
        source = _clear_incoming_morph_references(source, deleted_index)

        morphs = list(source.morphs)
        morphs[deleted_index] = replace(
            morphs[deleted_index],
            morph_type=0,
            morph_type_name="group",
            offsets=(PmxGroupMorphOffset(morph_index=fallback, weight=0.5),),
        )
        source = replace(source, morphs=tuple(morphs))

        source_bytes = serialize_pmx(source)
        intent = _morph_delete_intent(source, deleted_index)
        independent = preview_pmx_structural_transform(source, intent)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "source.pmx"
            output_path = root / "morph-delete.pmx"
            input_path.write_bytes(source_bytes)

            result = write_pmx_structural_transform(
                input_path,
                output_path,
                intent,
            )
            written = load_pmx(output_path)

            self.assertEqual(written, independent.certificate.document)
            self.assertEqual(len(written.morphs), len(source.morphs) - 1)
            self.assertEqual(
                written.header.index_sizes.morph,
                source.header.index_sizes.morph,
            )
            self.assertEqual(
                result.serialization.reparsed_certificate.reference_graph.invalid_targets,
                (),
            )
            self.assertEqual(input_path.read_bytes(), source_bytes)

    def test_deleting_referenced_morph_fails_closed_before_output(self) -> None:
        source = _clean_document()
        self.assertGreaterEqual(len(source.morphs), 2)
        deleted_index = len(source.morphs) - 1
        source = _clear_incoming_morph_references(source, deleted_index)

        morphs = list(source.morphs)
        morphs[0] = replace(
            morphs[0],
            morph_type=0,
            morph_type_name="group",
            offsets=(PmxGroupMorphOffset(morph_index=deleted_index, weight=0.5),),
        )
        source = replace(source, morphs=tuple(morphs))

        source_bytes = serialize_pmx(source)
        intent = _morph_delete_intent(source, deleted_index)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "source.pmx"
            output_path = root / "must-not-exist.pmx"
            input_path.write_bytes(source_bytes)

            with self.assertRaisesRegex(
                PmxMorphDisplayRemapError,
                rf"removed morph index {deleted_index}",
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

    def test_morph_type_version_uv_and_required_reference_guards_fail_closed(
        self,
    ) -> None:
        source = _clean_document()
        self.assertTrue(source.morphs)
        self.assertTrue(source.vertices)

        morph_identity = PmxCollectionTransform.identity(
            PmxReferenceTargetKind.MORPH,
            1,
        )
        vertex_identity = PmxCollectionTransform.identity(
            PmxReferenceTargetKind.VERTEX,
            len(source.vertices),
        )
        bone_identity = PmxCollectionTransform.identity(
            PmxReferenceTargetKind.BONE,
            len(source.bones),
        )
        material_identity = PmxCollectionTransform.identity(
            PmxReferenceTargetKind.MATERIAL,
            len(source.materials),
        )

        invalid_group = replace(
            source.morphs[0],
            morph_type=0,
            morph_type_name="group",
            offsets=(PmxGroupMorphOffset(morph_index=-1, weight=0.5),),
        )
        with self.assertRaisesRegex(ValueError, "cannot be negative"):
            transform_morph_collection_references(
                (invalid_group,),
                morph_identity,
                vertex_identity,
                bone_identity,
                material_identity,
                pmx_version=2.1,
                additional_uv_count=source.header.additional_uv_count,
            )

        flip = replace(
            source.morphs[0],
            morph_type=9,
            morph_type_name="flip",
            offsets=(PmxFlipMorphOffset(morph_index=0, weight=0.5),),
        )
        with self.assertRaisesRegex(ValueError, "requires PMX 2.1"):
            transform_morph_collection_references(
                (flip,),
                morph_identity,
                vertex_identity,
                bone_identity,
                material_identity,
                pmx_version=2.0,
                additional_uv_count=source.header.additional_uv_count,
            )

        additional_uv = replace(
            source.morphs[0],
            morph_type=4,
            morph_type_name="additional_uv_1",
            offsets=(
                PmxUvMorphOffset(
                    vertex_index=0,
                    uv_offset=(0.1, 0.2, 0.3, 0.4),
                ),
            ),
        )
        with self.assertRaisesRegex(ValueError, "requires additional UV layer 1"):
            transform_morph_collection_references(
                (additional_uv,),
                morph_identity,
                vertex_identity,
                bone_identity,
                material_identity,
                pmx_version=2.1,
                additional_uv_count=0,
            )

        wrong_offset_type = replace(
            source.morphs[0],
            morph_type=1,
            morph_type_name="vertex",
            offsets=(PmxGroupMorphOffset(morph_index=0, weight=0.5),),
        )
        with self.assertRaisesRegex(ValueError, "requires PmxVertexMorphOffset"):
            transform_morph_collection_references(
                (wrong_offset_type,),
                morph_identity,
                vertex_identity,
                bone_identity,
                material_identity,
                pmx_version=2.1,
                additional_uv_count=source.header.additional_uv_count,
            )

    def test_morph_transform_shape_guards_fail_closed(self) -> None:
        source = _clean_document()
        size = len(source.morphs)
        bad_intent = PmxStructuralTransformIntent(
            transforms=(
                PmxCollectionTransform.identity(
                    PmxReferenceTargetKind.MORPH,
                    size + 1,
                ),
            )
        )

        with self.assertRaisesRegex(
            PmxStructuralTransformError,
            r"morph transform old_size .* does not match source collection size",
        ):
            preview_pmx_structural_transform(source, bad_intent)

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
                PmxReferenceTargetKind.MORPH,
                insertion_capable,
            )

    def test_morph_execution_fails_closed_on_opaque_trailing_data(self) -> None:
        unsafe = load_pmx(io.BytesIO(build_pmx_roundtrip_fixture(version=2.1)))
        self.assertTrue(unsafe.trailing_data)
        intent = _morph_reverse_intent(unsafe)

        with self.assertRaisesRegex(
            PmxStructuralTransformError,
            "trailing_data",
        ):
            verify_pmx_structural_serialization(unsafe, intent)


if __name__ == "__main__":
    unittest.main()
