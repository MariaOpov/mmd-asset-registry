"""v0.9.1 bone structural-execution regression gates."""

from __future__ import annotations

import io
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from mmd_registry.pmx.bone_reference_remap import PmxBoneReferenceRemapError
from mmd_registry.pmx.collection_transform import (
    PmxCollectionTransform,
    PmxStructuralTransformIntent,
)
from mmd_registry.pmx.document import (
    PMX_BONE_FLAG_IK,
    PMX_BONE_FLAG_INHERIT_ROTATION,
    PMX_BONE_FLAG_INHERIT_TRANSLATION,
    PMX_BONE_FLAG_TAIL_INDEX,
    PmxBdef1,
    PmxBdef2,
    PmxBdef4,
    PmxBoneMorphOffset,
    PmxQdef,
    PmxSdef,
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


def _clean_document():
    return replace(
        load_pmx(io.BytesIO(build_pmx_roundtrip_fixture(version=2.1))),
        trailing_data=b"",
    )


def _bone_transform(
    targets: tuple[int | None, ...],
    new_size: int,
) -> PmxCollectionTransform:
    return PmxCollectionTransform(
        kind=PmxReferenceTargetKind.BONE,
        remap=PmxIndexRemap(targets=targets, new_size=new_size),
    )


def _bone_reverse_intent(document) -> PmxStructuralTransformIntent:
    size = len(document.bones)
    return PmxStructuralTransformIntent(
        transforms=(
            _bone_transform(tuple(reversed(range(size))), size),
        )
    )


def _bone_delete_intent(document, deleted_index: int) -> PmxStructuralTransformIntent:
    size = len(document.bones)
    if not 0 <= deleted_index < size:
        raise AssertionError("deleted bone index must be inside the fixture domain")
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
            _bone_transform(targets, size - 1),
        )
    )


def _mapped_optional(index: int, transform: PmxCollectionTransform) -> int:
    if index == -1:
        return -1
    mapped = transform.remap.target_for(index)
    if mapped is None:
        raise AssertionError("test expected a surviving optional bone reference")
    return mapped


def _mapped_required(index: int, transform: PmxCollectionTransform) -> int:
    mapped = transform.remap.target_for(index)
    if mapped is None:
        raise AssertionError("test expected a surviving required bone reference")
    return mapped


def _deform_indices(deform: object) -> tuple[int, ...]:
    if isinstance(deform, PmxBdef1):
        return (deform.bone_index,)
    if isinstance(deform, (PmxBdef2, PmxBdef4, PmxSdef, PmxQdef)):
        return tuple(deform.bone_indices)
    raise TypeError("fixture contains an unsupported deform record")


def _clear_deform_reference(deform: object, deleted_index: int) -> object:
    if isinstance(deform, PmxBdef1):
        if deform.bone_index == deleted_index:
            return replace(deform, bone_index=-1)
        return deform
    if isinstance(deform, (PmxBdef2, PmxBdef4, PmxSdef, PmxQdef)):
        indices = tuple(
            -1 if bone_index == deleted_index else bone_index
            for bone_index in deform.bone_indices
        )
        return deform if indices == deform.bone_indices else replace(
            deform,
            bone_indices=indices,
        )
    raise TypeError("fixture contains an unsupported deform record")


def _clear_incoming_bone_references(document, deleted_index: int):
    if len(document.bones) < 2:
        raise AssertionError("safe deletion fixture requires at least two bones")
    fallback = 0 if deleted_index != 0 else 1

    vertices = tuple(
        replace(
            vertex,
            deform=_clear_deform_reference(vertex.deform, deleted_index),
        )
        for vertex in document.vertices
    )

    inherit_mask = (
        PMX_BONE_FLAG_INHERIT_ROTATION | PMX_BONE_FLAG_INHERIT_TRANSLATION
    )
    bones = []
    for old_index, bone in enumerate(document.bones):
        if old_index == deleted_index:
            bones.append(bone)
            continue

        parent_bone_index = (
            -1 if bone.parent_bone_index == deleted_index else bone.parent_bone_index
        )

        tail_bone_index = bone.tail_bone_index
        if (
            bone.flags & PMX_BONE_FLAG_TAIL_INDEX
            and tail_bone_index == deleted_index
        ):
            tail_bone_index = -1

        inherit_parent_bone_index = bone.inherit_parent_bone_index
        if (
            bone.flags & inherit_mask
            and inherit_parent_bone_index == deleted_index
        ):
            inherit_parent_bone_index = -1

        ik = bone.ik
        if bone.flags & PMX_BONE_FLAG_IK and ik is not None:
            target_bone_index = (
                fallback
                if ik.target_bone_index == deleted_index
                else ik.target_bone_index
            )
            links = tuple(
                replace(link, bone_index=fallback)
                if link.bone_index == deleted_index
                else link
                for link in ik.links
            )
            if target_bone_index != ik.target_bone_index or links != ik.links:
                ik = replace(
                    ik,
                    target_bone_index=target_bone_index,
                    links=links,
                )

        bones.append(
            replace(
                bone,
                parent_bone_index=parent_bone_index,
                tail_bone_index=tail_bone_index,
                inherit_parent_bone_index=inherit_parent_bone_index,
                ik=ik,
            )
        )

    morphs = []
    for morph in document.morphs:
        if morph.morph_type != 2:
            morphs.append(morph)
            continue
        offsets = tuple(
            replace(offset, bone_index=fallback)
            if isinstance(offset, PmxBoneMorphOffset)
            and offset.bone_index == deleted_index
            else offset
            for offset in morph.offsets
        )
        morphs.append(
            morph if offsets == morph.offsets else replace(morph, offsets=offsets)
        )

    display_frames = []
    for frame in document.display_frames:
        elements = tuple(
            replace(element, target_index=fallback)
            if element.target_type == "bone"
            and element.target_index == deleted_index
            else element
            for element in frame.elements
        )
        display_frames.append(
            frame if elements == frame.elements else replace(frame, elements=elements)
        )

    rigid_bodies = tuple(
        replace(body, bone_index=-1)
        if body.bone_index == deleted_index
        else body
        for body in document.rigid_bodies
    )

    return replace(
        document,
        geometry=replace(document.geometry, vertices=vertices),
        bones=tuple(bones),
        morphs=tuple(morphs),
        display_frames=tuple(display_frames),
        rigid_bodies=rigid_bodies,
    )


class V091BoneStructuralExecutionTests(unittest.TestCase):
    """Freeze end-to-end bone keep/delete/reorder execution semantics."""

    def test_explicit_bone_identity_matches_implicit_noop_preview(self) -> None:
        source = _clean_document()
        size = len(source.bones)
        explicit = PmxStructuralTransformIntent(
            transforms=(
                PmxCollectionTransform.identity(
                    PmxReferenceTargetKind.BONE,
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

    def test_bone_reorder_remaps_vertex_and_surviving_bone_references(self) -> None:
        source = _clean_document()
        self.assertGreaterEqual(len(source.bones), 2)
        intent = _bone_reverse_intent(source)
        transform = intent.transforms[0]
        result = preview_pmx_structural_transform(
            source,
            intent,
        ).certificate.document

        for original, rewritten in zip(
            source.vertices,
            result.vertices,
            strict=True,
        ):
            expected = tuple(
                _mapped_optional(index, transform)
                for index in _deform_indices(original.deform)
            )
            self.assertEqual(_deform_indices(rewritten.deform), expected)

        inherit_mask = (
            PMX_BONE_FLAG_INHERIT_ROTATION | PMX_BONE_FLAG_INHERIT_TRANSLATION
        )
        for old_index, original in enumerate(source.bones):
            new_index = _mapped_required(old_index, transform)
            rewritten = result.bones[new_index]
            self.assertEqual(rewritten.local_name, original.local_name)
            self.assertEqual(
                rewritten.parent_bone_index,
                _mapped_optional(original.parent_bone_index, transform),
            )

            if original.flags & PMX_BONE_FLAG_TAIL_INDEX:
                self.assertEqual(
                    rewritten.tail_bone_index,
                    _mapped_optional(original.tail_bone_index, transform),
                )
            else:
                self.assertEqual(rewritten.tail_bone_index, original.tail_bone_index)

            if original.flags & inherit_mask:
                self.assertEqual(
                    rewritten.inherit_parent_bone_index,
                    _mapped_optional(
                        original.inherit_parent_bone_index,
                        transform,
                    ),
                )

            if original.flags & PMX_BONE_FLAG_IK:
                self.assertIsNotNone(original.ik)
                self.assertIsNotNone(rewritten.ik)
                self.assertEqual(
                    rewritten.ik.target_bone_index,
                    _mapped_required(original.ik.target_bone_index, transform),
                )
                self.assertEqual(
                    tuple(link.bone_index for link in rewritten.ik.links),
                    tuple(
                        _mapped_required(link.bone_index, transform)
                        for link in original.ik.links
                    ),
                )

    def test_bone_reorder_remaps_morph_display_and_rigid_body_references(self) -> None:
        source = _clean_document()
        intent = _bone_reverse_intent(source)
        transform = intent.transforms[0]
        result = preview_pmx_structural_transform(
            source,
            intent,
        ).certificate.document

        for original_morph, rewritten_morph in zip(
            source.morphs,
            result.morphs,
            strict=True,
        ):
            if original_morph.morph_type != 2:
                continue
            for original_offset, rewritten_offset in zip(
                original_morph.offsets,
                rewritten_morph.offsets,
                strict=True,
            ):
                self.assertIsInstance(original_offset, PmxBoneMorphOffset)
                self.assertIsInstance(rewritten_offset, PmxBoneMorphOffset)
                self.assertEqual(
                    rewritten_offset.bone_index,
                    _mapped_required(original_offset.bone_index, transform),
                )

        for original_frame, rewritten_frame in zip(
            source.display_frames,
            result.display_frames,
            strict=True,
        ):
            for original_element, rewritten_element in zip(
                original_frame.elements,
                rewritten_frame.elements,
                strict=True,
            ):
                if original_element.target_type == "bone":
                    self.assertEqual(
                        rewritten_element.target_index,
                        _mapped_required(
                            original_element.target_index,
                            transform,
                        ),
                    )

        for original_body, rewritten_body in zip(
            source.rigid_bodies,
            result.rigid_bodies,
            strict=True,
        ):
            self.assertEqual(
                rewritten_body.bone_index,
                _mapped_optional(original_body.bone_index, transform),
            )

    def test_bone_reorder_changes_only_bone_target_kind(self) -> None:
        source = _clean_document()
        preview = preview_pmx_structural_transform(
            source,
            _bone_reverse_intent(source),
        )

        self.assertEqual(
            preview.audit.changed_kinds,
            (PmxReferenceTargetKind.BONE,),
        )
        self.assertEqual(len(preview.audit.collections), 6)
        bone_audit = preview.audit.collections[3]
        self.assertIs(bone_audit.kind, PmxReferenceTargetKind.BONE)
        self.assertTrue(bone_audit.transform.has_reorder)
        self.assertFalse(bone_audit.transform.has_deletions)

    def test_bone_reorder_serialization_reparses_to_certified_preview(self) -> None:
        source = _clean_document()
        intent = _bone_reverse_intent(source)
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

    def test_bone_reorder_write_is_distinct_verified_and_source_immutable(self) -> None:
        source = _clean_document()
        source_bytes = serialize_pmx(source)
        intent = _bone_reverse_intent(source)
        independent = preview_pmx_structural_transform(source, intent)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "source.pmx"
            output_path = root / "bone-reorder.pmx"
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

    def test_safe_bone_deletion_executes_without_index_width_resize(self) -> None:
        source = _clean_document()
        self.assertGreaterEqual(len(source.bones), 2)
        deleted_index = len(source.bones) - 1
        source = _clear_incoming_bone_references(source, deleted_index)
        source_bytes = serialize_pmx(source)
        intent = _bone_delete_intent(source, deleted_index)
        independent = preview_pmx_structural_transform(source, intent)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "source.pmx"
            output_path = root / "bone-delete.pmx"
            input_path.write_bytes(source_bytes)

            result = write_pmx_structural_transform(
                input_path,
                output_path,
                intent,
            )
            written = load_pmx(output_path)

            self.assertEqual(written, independent.certificate.document)
            self.assertEqual(len(written.bones), len(source.bones) - 1)
            self.assertEqual(
                written.header.index_sizes.bone,
                source.header.index_sizes.bone,
            )
            self.assertEqual(
                result.serialization.reparsed_certificate.reference_graph.invalid_targets,
                (),
            )
            self.assertEqual(input_path.read_bytes(), source_bytes)

    def test_deleting_referenced_bone_fails_closed_before_output(self) -> None:
        source = _clean_document()
        self.assertGreaterEqual(len(source.bones), 2)
        deleted_index = len(source.bones) - 1
        first_vertex = replace(
            source.vertices[0],
            deform=PmxBdef1(deleted_index),
        )
        source = replace(
            source,
            geometry=replace(
                source.geometry,
                vertices=(first_vertex, *source.vertices[1:]),
            ),
        )
        source_bytes = serialize_pmx(source)
        intent = _bone_delete_intent(source, deleted_index)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "source.pmx"
            output_path = root / "must-not-exist.pmx"
            input_path.write_bytes(source_bytes)

            with self.assertRaisesRegex(
                PmxBoneReferenceRemapError,
                rf"removed bone index {deleted_index}",
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

    def test_bone_optional_sentinels_remain_sentinels_under_reorder(self) -> None:
        source = _clean_document()
        self.assertTrue(source.vertices)
        self.assertTrue(source.bones)

        first_vertex = replace(source.vertices[0], deform=PmxBdef1(-1))
        first_bone = replace(source.bones[0], parent_bone_index=-1)
        rigid_bodies = (
            (
                replace(source.rigid_bodies[0], bone_index=-1),
                *source.rigid_bodies[1:],
            )
            if source.rigid_bodies
            else ()
        )
        source = replace(
            source,
            geometry=replace(
                source.geometry,
                vertices=(first_vertex, *source.vertices[1:]),
            ),
            bones=(first_bone, *source.bones[1:]),
            rigid_bodies=rigid_bodies,
        )

        intent = _bone_reverse_intent(source)
        transform = intent.transforms[0]
        result = preview_pmx_structural_transform(
            source,
            intent,
        ).certificate.document

        self.assertEqual(_deform_indices(result.vertices[0].deform), (-1,))
        new_first_bone_index = _mapped_required(0, transform)
        self.assertEqual(
            result.bones[new_first_bone_index].parent_bone_index,
            -1,
        )
        if result.rigid_bodies:
            self.assertEqual(result.rigid_bodies[0].bone_index, -1)

    def test_bone_transform_shape_guards_fail_closed(self) -> None:
        source = _clean_document()
        size = len(source.bones)
        bad_intent = PmxStructuralTransformIntent(
            transforms=(
                PmxCollectionTransform.identity(
                    PmxReferenceTargetKind.BONE,
                    size + 1,
                ),
            )
        )

        with self.assertRaisesRegex(
            PmxStructuralTransformError,
            r"bone transform old_size .* does not match source collection size",
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
                PmxReferenceTargetKind.BONE,
                insertion_capable,
            )

    def test_bone_execution_fails_closed_on_opaque_trailing_data(self) -> None:
        unsafe = load_pmx(io.BytesIO(build_pmx_roundtrip_fixture(version=2.1)))
        self.assertTrue(unsafe.trailing_data)
        intent = _bone_reverse_intent(unsafe)

        with self.assertRaisesRegex(
            PmxStructuralTransformError,
            "trailing_data",
        ):
            verify_pmx_structural_serialization(unsafe, intent)


if __name__ == "__main__":
    unittest.main()
