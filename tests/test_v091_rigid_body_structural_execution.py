"""v0.9.1 rigid-body structural-execution regression gates."""

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
from mmd_registry.pmx.index_remap import PmxIndexRemap
from mmd_registry.pmx.physics_reference_remap import (
    PmxPhysicsReferenceRemapError,
    remap_impulse_morph_rigid_body_references,
    remap_joint_rigid_body_references,
    remap_soft_body_references,
    transform_rigid_body_collection_references,
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


def _rigid_body_transform(
    targets: tuple[int | None, ...],
    new_size: int,
) -> PmxCollectionTransform:
    return PmxCollectionTransform(
        kind=PmxReferenceTargetKind.RIGID_BODY,
        remap=PmxIndexRemap(targets=targets, new_size=new_size),
    )


def _rigid_body_reverse_intent(document) -> PmxStructuralTransformIntent:
    size = len(document.rigid_bodies)
    return PmxStructuralTransformIntent(
        transforms=(
            _rigid_body_transform(tuple(reversed(range(size))), size),
        )
    )


def _rigid_body_delete_intent(
    document,
    deleted_index: int,
) -> PmxStructuralTransformIntent:
    size = len(document.rigid_bodies)
    if not 0 <= deleted_index < size:
        raise AssertionError("deleted rigid-body index must be inside the fixture domain")
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
            _rigid_body_transform(targets, size - 1),
        )
    )


def _mapped_required(index: int, transform: PmxCollectionTransform) -> int:
    mapped = transform.remap.target_for(index)
    if mapped is None:
        raise AssertionError("test expected a surviving required rigid-body reference")
    return mapped


def _mapped_optional(index: int, transform: PmxCollectionTransform) -> int:
    if index == -1:
        return -1
    mapped = transform.remap.target_for(index)
    if mapped is None:
        raise AssertionError("test expected a surviving optional rigid-body reference")
    return mapped


def _clear_incoming_rigid_body_references(document, deleted_index: int):
    if len(document.rigid_bodies) < 2:
        raise AssertionError("safe deletion fixture requires at least two rigid bodies")
    fallback = 0 if deleted_index != 0 else 1

    morphs = []
    for morph in document.morphs:
        if morph.morph_type != 10:
            morphs.append(morph)
            continue
        offsets = tuple(
            replace(offset, rigid_body_index=fallback)
            if offset.rigid_body_index == deleted_index
            else offset
            for offset in morph.offsets
        )
        morphs.append(
            morph if offsets == morph.offsets else replace(morph, offsets=offsets)
        )

    joints = tuple(
        replace(
            joint,
            rigid_body_a_index=(
                -1
                if joint.rigid_body_a_index == deleted_index
                else joint.rigid_body_a_index
            ),
            rigid_body_b_index=(
                -1
                if joint.rigid_body_b_index == deleted_index
                else joint.rigid_body_b_index
            ),
        )
        for joint in document.joints
    )

    soft_bodies = []
    for body in document.soft_bodies:
        anchors = tuple(
            replace(anchor, rigid_body_index=fallback)
            if anchor.rigid_body_index == deleted_index
            else anchor
            for anchor in body.anchors
        )
        soft_bodies.append(
            body if anchors == body.anchors else replace(body, anchors=anchors)
        )

    return replace(
        document,
        morphs=tuple(morphs),
        joints=joints,
        soft_bodies=tuple(soft_bodies),
    )


def _first_impulse_location(document) -> tuple[int, int]:
    for morph_index, morph in enumerate(document.morphs):
        if morph.morph_type == 10 and morph.offsets:
            return morph_index, 0
    raise AssertionError("roundtrip fixture must contain an impulse morph offset")


class V091RigidBodyStructuralExecutionTests(unittest.TestCase):
    """Freeze end-to-end rigid-body keep/delete/reorder execution semantics."""

    def test_explicit_rigid_body_identity_matches_implicit_noop_preview(self) -> None:
        source = _clean_document()
        size = len(source.rigid_bodies)
        explicit = PmxStructuralTransformIntent(
            transforms=(
                PmxCollectionTransform.identity(
                    PmxReferenceTargetKind.RIGID_BODY,
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

    def test_rigid_body_reorder_moves_sources_and_remaps_all_incoming_references(
        self,
    ) -> None:
        source = _clean_document()
        self.assertGreaterEqual(len(source.rigid_bodies), 2)
        intent = _rigid_body_reverse_intent(source)
        transform = intent.transforms[0]
        result = preview_pmx_structural_transform(
            source,
            intent,
        ).certificate.document

        for old_index, original in enumerate(source.rigid_bodies):
            new_index = _mapped_required(old_index, transform)
            self.assertEqual(result.rigid_bodies[new_index], original)

        for original_morph, rewritten_morph in zip(
            source.morphs,
            result.morphs,
            strict=True,
        ):
            if original_morph.morph_type != 10:
                continue
            for original_offset, rewritten_offset in zip(
                original_morph.offsets,
                rewritten_morph.offsets,
                strict=True,
            ):
                self.assertEqual(
                    rewritten_offset.rigid_body_index,
                    _mapped_required(original_offset.rigid_body_index, transform),
                )
                self.assertEqual(
                    replace(
                        rewritten_offset,
                        rigid_body_index=original_offset.rigid_body_index,
                    ),
                    original_offset,
                )

        for original_joint, rewritten_joint in zip(
            source.joints,
            result.joints,
            strict=True,
        ):
            self.assertEqual(
                rewritten_joint.rigid_body_a_index,
                _mapped_optional(original_joint.rigid_body_a_index, transform),
            )
            self.assertEqual(
                rewritten_joint.rigid_body_b_index,
                _mapped_optional(original_joint.rigid_body_b_index, transform),
            )

        for original_body, rewritten_body in zip(
            source.soft_bodies,
            result.soft_bodies,
            strict=True,
        ):
            self.assertEqual(len(rewritten_body.anchors), len(original_body.anchors))
            for original_anchor, rewritten_anchor in zip(
                original_body.anchors,
                rewritten_body.anchors,
                strict=True,
            ):
                self.assertEqual(
                    rewritten_anchor.rigid_body_index,
                    _mapped_required(original_anchor.rigid_body_index, transform),
                )
                self.assertEqual(
                    replace(
                        rewritten_anchor,
                        rigid_body_index=original_anchor.rigid_body_index,
                    ),
                    original_anchor,
                )

    def test_optional_rigid_body_sentinels_are_preserved_under_reorder(self) -> None:
        source = _clean_document()
        self.assertGreaterEqual(len(source.rigid_bodies), 2)
        self.assertTrue(source.joints)

        bodies = list(source.rigid_bodies)
        bodies[0] = replace(bodies[0], bone_index=-1)
        joints = list(source.joints)
        joints[0] = replace(
            joints[0],
            rigid_body_a_index=-1,
            rigid_body_b_index=-1,
        )
        source = replace(
            source,
            rigid_bodies=tuple(bodies),
            joints=tuple(joints),
        )

        intent = _rigid_body_reverse_intent(source)
        transform = intent.transforms[0]
        result = preview_pmx_structural_transform(
            source,
            intent,
        ).certificate.document

        moved_body_index = _mapped_required(0, transform)
        self.assertEqual(result.rigid_bodies[moved_body_index].bone_index, -1)
        self.assertEqual(result.joints[0].rigid_body_a_index, -1)
        self.assertEqual(result.joints[0].rigid_body_b_index, -1)

    def test_rigid_body_reorder_changes_only_rigid_body_target_kind(self) -> None:
        source = _clean_document()
        preview = preview_pmx_structural_transform(
            source,
            _rigid_body_reverse_intent(source),
        )

        self.assertEqual(
            preview.audit.changed_kinds,
            (PmxReferenceTargetKind.RIGID_BODY,),
        )
        self.assertEqual(len(preview.audit.collections), 6)
        rigid_body_audit = preview.audit.collections[5]
        self.assertIs(
            rigid_body_audit.kind,
            PmxReferenceTargetKind.RIGID_BODY,
        )
        self.assertTrue(rigid_body_audit.transform.has_reorder)
        self.assertFalse(rigid_body_audit.transform.has_deletions)

    def test_rigid_body_reorder_serialization_reparses_to_certified_preview(
        self,
    ) -> None:
        source = _clean_document()
        intent = _rigid_body_reverse_intent(source)
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

    def test_rigid_body_reorder_write_is_distinct_verified_and_source_immutable(
        self,
    ) -> None:
        source = _clean_document()
        source_bytes = serialize_pmx(source)
        intent = _rigid_body_reverse_intent(source)
        independent = preview_pmx_structural_transform(source, intent)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "source.pmx"
            output_path = root / "rigid-body-reorder.pmx"
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

    def test_safe_rigid_body_deletion_preserves_width_and_ignores_deleted_source(
        self,
    ) -> None:
        source = _clean_document()
        self.assertGreaterEqual(len(source.rigid_bodies), 2)
        deleted_index = len(source.rigid_bodies) - 1
        source = _clear_incoming_rigid_body_references(source, deleted_index)

        source_bytes = serialize_pmx(source)
        intent = _rigid_body_delete_intent(source, deleted_index)
        independent = preview_pmx_structural_transform(source, intent)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "source.pmx"
            output_path = root / "rigid-body-delete.pmx"
            input_path.write_bytes(source_bytes)

            result = write_pmx_structural_transform(
                input_path,
                output_path,
                intent,
            )
            written = load_pmx(output_path)

            self.assertEqual(written, independent.certificate.document)
            self.assertEqual(
                len(written.rigid_bodies),
                len(source.rigid_bodies) - 1,
            )
            self.assertEqual(
                written.header.index_sizes.rigid_body,
                source.header.index_sizes.rigid_body,
            )
            self.assertEqual(
                result.serialization.reparsed_certificate.reference_graph.invalid_targets,
                (),
            )
            self.assertEqual(input_path.read_bytes(), source_bytes)

    def test_deleting_impulse_referenced_rigid_body_fails_closed_before_output(
        self,
    ) -> None:
        source = _clean_document()
        self.assertGreaterEqual(len(source.rigid_bodies), 2)
        deleted_index = len(source.rigid_bodies) - 1
        source = _clear_incoming_rigid_body_references(source, deleted_index)

        morph_index, offset_index = _first_impulse_location(source)
        morphs = list(source.morphs)
        offsets = list(morphs[morph_index].offsets)
        offsets[offset_index] = replace(
            offsets[offset_index],
            rigid_body_index=deleted_index,
        )
        morphs[morph_index] = replace(
            morphs[morph_index],
            offsets=tuple(offsets),
        )
        source = replace(source, morphs=tuple(morphs))

        source_bytes = serialize_pmx(source)
        intent = _rigid_body_delete_intent(source, deleted_index)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "source.pmx"
            output_path = root / "must-not-exist.pmx"
            input_path.write_bytes(source_bytes)

            with self.assertRaisesRegex(
                PmxPhysicsReferenceRemapError,
                rf"removed rigid_body index {deleted_index}",
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

    def test_deleted_rigid_body_source_outgoing_bone_reference_is_ignored_and_format_guards_hold(
        self,
    ) -> None:
        source = _clean_document()
        self.assertGreaterEqual(len(source.rigid_bodies), 2)
        self.assertGreaterEqual(len(source.bones), 2)

        controlled_bodies = (
            replace(source.rigid_bodies[0], bone_index=0),
            replace(source.rigid_bodies[1], bone_index=1),
        )
        rigid_body_transform = _rigid_body_transform((0, None), 1)
        bone_transform = PmxCollectionTransform(
            kind=PmxReferenceTargetKind.BONE,
            remap=PmxIndexRemap(
                targets=(0, None, *range(1, len(source.bones) - 1)),
                new_size=len(source.bones) - 1,
            ),
        )
        result = transform_rigid_body_collection_references(
            controlled_bodies,
            rigid_body_transform,
            bone_transform,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].bone_index, 0)

        identity_rigid = PmxCollectionTransform.identity(
            PmxReferenceTargetKind.RIGID_BODY,
            len(source.rigid_bodies),
        )

        impulse_morphs = tuple(
            morph for morph in source.morphs if morph.morph_type == 10
        )
        self.assertTrue(impulse_morphs)
        with self.assertRaisesRegex(ValueError, "requires PMX 2.1"):
            remap_impulse_morph_rigid_body_references(
                impulse_morphs,
                identity_rigid,
                pmx_version=2.0,
            )

        self.assertTrue(source.soft_bodies)
        with self.assertRaisesRegex(
            ValueError,
            "PMX 2.0 cannot contain a soft-body section",
        ):
            remap_soft_body_references(
                source.soft_bodies,
                PmxCollectionTransform.identity(
                    PmxReferenceTargetKind.MATERIAL,
                    len(source.materials),
                ),
                identity_rigid,
                PmxCollectionTransform.identity(
                    PmxReferenceTargetKind.VERTEX,
                    len(source.vertices),
                ),
                pmx_version=2.0,
            )

        self.assertTrue(source.joints)
        pmx21_joint = replace(source.joints[0], joint_type=1)
        with self.assertRaisesRegex(ValueError, "requires PMX 2.1"):
            remap_joint_rigid_body_references(
                (pmx21_joint,),
                identity_rigid,
                pmx_version=2.0,
            )

    def test_rigid_body_transform_shape_guards_fail_closed(self) -> None:
        source = _clean_document()
        size = len(source.rigid_bodies)
        bad_intent = PmxStructuralTransformIntent(
            transforms=(
                PmxCollectionTransform.identity(
                    PmxReferenceTargetKind.RIGID_BODY,
                    size + 1,
                ),
            )
        )

        with self.assertRaisesRegex(
            PmxStructuralTransformError,
            r"rigid_body transform old_size .* does not match source collection size",
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
                PmxReferenceTargetKind.RIGID_BODY,
                insertion_capable,
            )

    def test_rigid_body_execution_fails_closed_on_opaque_trailing_data(self) -> None:
        unsafe = load_pmx(io.BytesIO(build_pmx_roundtrip_fixture(version=2.1)))
        self.assertTrue(unsafe.trailing_data)
        intent = _rigid_body_reverse_intent(unsafe)

        with self.assertRaisesRegex(
            PmxStructuralTransformError,
            "trailing_data",
        ):
            verify_pmx_structural_serialization(unsafe, intent)


if __name__ == "__main__":
    unittest.main()
