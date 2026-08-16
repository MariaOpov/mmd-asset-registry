from __future__ import annotations

import io
import unittest
from dataclasses import replace

import mmd_registry.pmx as pmx_public
import mmd_registry.services as services_public
from mmd_registry.pmx import load_pmx
from mmd_registry.pmx.collection_transform import (
    PmxCollectionTransform,
    PmxStructuralTransformIntent,
)
from mmd_registry.pmx.index_remap import PmxIndexRemap
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.pmx.structural_orchestrator import (
    PmxStructuralTransformError,
    transform_pmx_document,
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


class StructuralOrchestratorContractTests(unittest.TestCase):
    def test_empty_intent_returns_original_document_even_with_trailing_data(self) -> None:
        source = load_pmx(io.BytesIO(build_pmx_roundtrip_fixture()))
        result = transform_pmx_document(source, PmxStructuralTransformIntent())
        self.assertIs(result, source)

    def test_explicit_identity_intent_returns_original_document(self) -> None:
        source = load_pmx(io.BytesIO(build_pmx_roundtrip_fixture()))
        intent = PmxStructuralTransformIntent(
            transforms=(
                _identity(PmxReferenceTargetKind.VERTEX, len(source.vertices)),
                _identity(PmxReferenceTargetKind.TEXTURE, len(source.texture_paths)),
                _identity(PmxReferenceTargetKind.MATERIAL, len(source.materials)),
                _identity(PmxReferenceTargetKind.BONE, len(source.bones)),
                _identity(PmxReferenceTargetKind.MORPH, len(source.morphs)),
                _identity(PmxReferenceTargetKind.RIGID_BODY, len(source.rigid_bodies)),
            )
        )
        self.assertIs(transform_pmx_document(source, intent), source)

    def test_changed_intent_fails_closed_on_trailing_data(self) -> None:
        source = load_pmx(io.BytesIO(build_pmx_roundtrip_fixture()))
        intent = PmxStructuralTransformIntent(
            transforms=(
                _reverse(PmxReferenceTargetKind.TEXTURE, len(source.texture_paths)),
            )
        )
        with self.assertRaisesRegex(PmxStructuralTransformError, "trailing_data"):
            transform_pmx_document(source, intent)

    def test_document_type_is_required(self) -> None:
        with self.assertRaisesRegex(TypeError, "document must be a PmxDocument"):
            transform_pmx_document(  # type: ignore[arg-type]
                object(),
                PmxStructuralTransformIntent(),
            )

    def test_intent_type_is_required(self) -> None:
        with self.assertRaisesRegex(
            TypeError,
            "intent must be a PmxStructuralTransformIntent",
        ):
            transform_pmx_document(_document(), object())  # type: ignore[arg-type]

    def test_explicit_old_size_must_match_source_collection(self) -> None:
        source = _document()
        intent = PmxStructuralTransformIntent(
            transforms=(
                _identity(PmxReferenceTargetKind.VERTEX, len(source.vertices) + 1),
            )
        )
        with self.assertRaisesRegex(
            PmxStructuralTransformError,
            "does not match source collection size",
        ):
            transform_pmx_document(source, intent)

    def test_extra_global_data_is_preserved_for_changed_transform(self) -> None:
        source = _document()
        header = replace(source.header, extra_global_data=b"\xaa\x55")
        source = replace(source, header=header)
        intent = PmxStructuralTransformIntent(
            transforms=(
                _reverse(PmxReferenceTargetKind.TEXTURE, len(source.texture_paths)),
            )
        )
        result = transform_pmx_document(source, intent)
        self.assertIs(result.header, header)
        self.assertEqual(result.header.extra_global_data, b"\xaa\x55")

    def test_orchestrator_is_not_exported_from_public_roots(self) -> None:
        forbidden = (
            "PmxStructuralTransformError",
            "transform_pmx_document",
        )
        for name in forbidden:
            with self.subTest(name=name):
                self.assertFalse(hasattr(pmx_public, name))
                self.assertFalse(hasattr(services_public, name))


class CoordinatedTransformTests(unittest.TestCase):
    def test_texture_only_intent_synthesizes_identity_for_other_targets(self) -> None:
        source = _document()
        texture_transform = _reverse(
            PmxReferenceTargetKind.TEXTURE,
            len(source.texture_paths),
        )
        intent = PmxStructuralTransformIntent(transforms=(texture_transform,))

        result = transform_pmx_document(source, intent)

        self.assertEqual(result.texture_paths, tuple(reversed(source.texture_paths)))
        self.assertIs(result.geometry, source.geometry)
        self.assertIs(result.bones, source.bones)
        self.assertIs(result.morphs, source.morphs)
        self.assertIs(result.display_frames, source.display_frames)
        self.assertIs(result.rigid_bodies, source.rigid_bodies)
        self.assertIs(result.joints, source.joints)
        self.assertIs(result.soft_bodies, source.soft_bodies)

        original = source.materials[0]
        rewritten = result.materials[0]
        self.assertEqual(
            rewritten.texture_index,
            texture_transform.remap.target_for(original.texture_index),
        )
        self.assertEqual(
            rewritten.sphere_texture_index,
            texture_transform.remap.target_for(original.sphere_texture_index),
        )
        self.assertEqual(
            rewritten.toon_reference_index,
            texture_transform.remap.target_for(original.toon_reference_index),
        )

    def test_full_reverse_coordinates_all_six_target_domains(self) -> None:
        source = _document()
        intent = _full_reverse_intent(source)
        result = transform_pmx_document(source, intent)

        self.assertEqual(result.texture_paths, tuple(reversed(source.texture_paths)))
        self.assertEqual(
            tuple(item.local_name for item in result.materials),
            tuple(reversed(tuple(item.local_name for item in source.materials))),
        )
        self.assertEqual(
            tuple(item.local_name for item in result.bones),
            tuple(reversed(tuple(item.local_name for item in source.bones))),
        )
        self.assertEqual(
            tuple(item.local_name for item in result.morphs),
            tuple(reversed(tuple(item.local_name for item in source.morphs))),
        )
        self.assertEqual(
            tuple(item.local_name for item in result.rigid_bodies),
            tuple(reversed(tuple(item.local_name for item in source.rigid_bodies))),
        )

        self.assertEqual(result.surface_indices, (4, 3, 2))

        body_material = result.materials[1]
        self.assertEqual(body_material.texture_index, 2)
        self.assertEqual(body_material.sphere_texture_index, 1)
        self.assertEqual(body_material.toon_reference_index, 0)

        self.assertEqual(result.vertices[4].deform.bone_index, 1)

        moved_ik_bone = result.bones[0]
        self.assertEqual(moved_ik_bone.parent_bone_index, 1)
        self.assertEqual(moved_ik_bone.tail_bone_index, 1)
        self.assertEqual(moved_ik_bone.inherit_parent_bone_index, 1)
        self.assertEqual(moved_ik_bone.ik.target_bone_index, 1)
        self.assertEqual(moved_ik_bone.ik.links[0].bone_index, 1)

        self.assertEqual(result.morphs[10].offsets[0].morph_index, 9)
        self.assertEqual(result.morphs[9].offsets[0].vertex_index, 4)
        self.assertEqual(result.morphs[8].offsets[0].bone_index, 1)
        self.assertEqual(result.morphs[2].offsets[0].material_index, 1)
        self.assertEqual(result.morphs[1].offsets[0].morph_index, 9)
        self.assertEqual(result.morphs[0].offsets[0].rigid_body_index, 1)

        frame = result.display_frames[0]
        self.assertEqual(frame.elements[0].target_index, 1)
        self.assertEqual(frame.elements[1].target_index, 9)

        self.assertEqual(result.rigid_bodies[1].bone_index, 1)
        for joint in result.joints:
            self.assertEqual(joint.rigid_body_a_index, 1)
            self.assertEqual(joint.rigid_body_b_index, 0)

        soft_body = result.soft_bodies[0]
        self.assertEqual(soft_body.material_index, 1)
        self.assertEqual(soft_body.anchors[0].rigid_body_index, 1)
        self.assertEqual(soft_body.anchors[0].vertex_index, 4)
        self.assertEqual(soft_body.pinned_vertex_indices, (3, 2))

    def test_full_reverse_preserves_source_document(self) -> None:
        source = _document()
        baseline = _document()
        transform_pmx_document(source, _full_reverse_intent(source))
        self.assertEqual(source, baseline)

    def test_full_reverse_is_deterministic(self) -> None:
        source = _document()
        intent = _full_reverse_intent(source)
        first = transform_pmx_document(source, intent)
        second = transform_pmx_document(source, intent)
        self.assertEqual(first, second)

    def test_output_target_sizes_match_transform_new_sizes(self) -> None:
        source = _document()
        intent = _full_reverse_intent(source)
        result = transform_pmx_document(source, intent)
        self.assertEqual(len(result.vertices), len(source.vertices))
        self.assertEqual(len(result.texture_paths), len(source.texture_paths))
        self.assertEqual(len(result.materials), len(source.materials))
        self.assertEqual(len(result.bones), len(source.bones))
        self.assertEqual(len(result.morphs), len(source.morphs))
        self.assertEqual(len(result.rigid_bodies), len(source.rigid_bodies))

    def test_pmx20_path_uses_same_orchestrator_without_soft_body_assumptions(self) -> None:
        source = _document(version=2.0)
        intent = PmxStructuralTransformIntent(
            transforms=(
                _reverse(PmxReferenceTargetKind.TEXTURE, len(source.texture_paths)),
            )
        )
        result = transform_pmx_document(source, intent)
        self.assertEqual(result.header.version, 2.0)
        self.assertEqual(result.soft_bodies, ())
        self.assertEqual(result.texture_paths, tuple(reversed(source.texture_paths)))


class DeletedSourceOrderingTests(unittest.TestCase):
    def test_deleted_material_source_is_removed_before_texture_reference_remap(self) -> None:
        source = _document()
        bad_material = replace(source.materials[0], texture_index=99)
        soft_body = replace(source.soft_bodies[0], material_index=-1)
        source = replace(
            source,
            materials=(bad_material, source.materials[1]),
            soft_bodies=(soft_body,),
        )

        material_transform = _transform(
            PmxReferenceTargetKind.MATERIAL,
            (None, 0),
            1,
        )
        morph_targets = tuple(
            None if index == 8 else index if index < 8 else index - 1
            for index in range(len(source.morphs))
        )
        morph_transform = _transform(
            PmxReferenceTargetKind.MORPH,
            morph_targets,
            len(source.morphs) - 1,
        )
        intent = PmxStructuralTransformIntent(
            transforms=(material_transform, morph_transform)
        )

        result = transform_pmx_document(source, intent)

        self.assertEqual(len(result.materials), 1)
        self.assertEqual(result.materials[0].local_name, source.materials[1].local_name)
        self.assertEqual(result.surface_indices, ())
        self.assertNotIn(8, tuple(morph.morph_type for morph in result.morphs))

    def test_surviving_material_dangling_texture_reference_still_blocks(self) -> None:
        source = _document()
        bad_material = replace(source.materials[1], texture_index=99)
        source = replace(
            source,
            materials=(source.materials[0], bad_material),
        )
        intent = PmxStructuralTransformIntent(
            transforms=(
                _reverse(PmxReferenceTargetKind.VERTEX, len(source.vertices)),
            )
        )
        with self.assertRaisesRegex(ValueError, "texture old_size"):
            transform_pmx_document(source, intent)

    def test_deleted_rigid_body_source_is_removed_before_bone_reference_remap(self) -> None:
        source = _document()
        bad_body = replace(source.rigid_bodies[1], bone_index=99)
        joints = tuple(
            replace(joint, rigid_body_b_index=-1)
            for joint in source.joints
        )
        source = replace(
            source,
            rigid_bodies=(source.rigid_bodies[0], bad_body),
            joints=joints,
        )
        rigid_transform = _transform(
            PmxReferenceTargetKind.RIGID_BODY,
            (0, None),
            1,
        )
        result = transform_pmx_document(
            source,
            PmxStructuralTransformIntent(transforms=(rigid_transform,)),
        )
        self.assertEqual(len(result.rigid_bodies), 1)
        self.assertEqual(result.rigid_bodies[0].local_name, source.rigid_bodies[0].local_name)

    def test_surviving_rigid_body_dangling_bone_reference_still_blocks(self) -> None:
        source = _document()
        bad_body = replace(source.rigid_bodies[0], bone_index=99)
        source = replace(
            source,
            rigid_bodies=(bad_body, source.rigid_bodies[1]),
        )
        intent = PmxStructuralTransformIntent(
            transforms=(
                _reverse(
                    PmxReferenceTargetKind.RIGID_BODY,
                    len(source.rigid_bodies),
                ),
            )
        )
        with self.assertRaisesRegex(ValueError, "bone old_size"):
            transform_pmx_document(source, intent)

    def test_deleted_impulse_morph_is_removed_before_cp14_impulse_remap(self) -> None:
        source = _document()
        impulse = source.morphs[10]
        bad_offset = replace(impulse.offsets[0], rigid_body_index=99)
        bad_impulse = replace(impulse, offsets=(bad_offset,))
        source = replace(
            source,
            morphs=(*source.morphs[:10], bad_impulse),
        )
        morph_transform = _transform(
            PmxReferenceTargetKind.MORPH,
            tuple((*range(10), None)),
            10,
        )
        result = transform_pmx_document(
            source,
            PmxStructuralTransformIntent(transforms=(morph_transform,)),
        )
        self.assertEqual(len(result.morphs), 10)
        self.assertTrue(all(morph.morph_type != 10 for morph in result.morphs))

    def test_surviving_impulse_dangling_rigid_body_reference_still_blocks(self) -> None:
        source = _document()
        impulse = source.morphs[10]
        bad_offset = replace(impulse.offsets[0], rigid_body_index=99)
        bad_impulse = replace(impulse, offsets=(bad_offset,))
        source = replace(
            source,
            morphs=(*source.morphs[:10], bad_impulse),
        )
        intent = PmxStructuralTransformIntent(
            transforms=(
                _reverse(PmxReferenceTargetKind.TEXTURE, len(source.texture_paths)),
            )
        )
        with self.assertRaisesRegex(ValueError, "rigid_body old_size"):
            transform_pmx_document(source, intent)

    def test_deleted_vertex_source_is_removed_before_deform_bone_remap(self) -> None:
        source = _document()
        vertex = source.vertices[4]
        bad_deform = replace(vertex.deform, bone_indices=(99, 0, 0, 0))
        bad_vertex = replace(vertex, deform=bad_deform)
        geometry = replace(
            source.geometry,
            vertices=(*source.vertices[:4], bad_vertex),
        )
        source = replace(source, geometry=geometry)
        vertex_transform = _transform(
            PmxReferenceTargetKind.VERTEX,
            (0, 1, 2, 3, None),
            4,
        )
        result = transform_pmx_document(
            source,
            PmxStructuralTransformIntent(transforms=(vertex_transform,)),
        )
        self.assertEqual(len(result.vertices), 4)

    def test_surviving_vertex_dangling_bone_reference_still_blocks(self) -> None:
        source = _document()
        vertex = source.vertices[4]
        bad_deform = replace(vertex.deform, bone_indices=(99, 0, 0, 0))
        bad_vertex = replace(vertex, deform=bad_deform)
        geometry = replace(
            source.geometry,
            vertices=(*source.vertices[:4], bad_vertex),
        )
        source = replace(source, geometry=geometry)
        intent = PmxStructuralTransformIntent(
            transforms=(
                _reverse(PmxReferenceTargetKind.VERTEX, len(source.vertices)),
            )
        )
        with self.assertRaisesRegex(ValueError, "bone old_size"):
            transform_pmx_document(source, intent)


class Cp15ValidationBoundaryTests(unittest.TestCase):
    def test_cp15_does_not_claim_cp16_complete_validation(self) -> None:
        source = _document()
        invalid_body = replace(source.rigid_bodies[0], mass=-1.0)
        source = replace(
            source,
            rigid_bodies=(invalid_body, source.rigid_bodies[1]),
        )
        intent = PmxStructuralTransformIntent(
            transforms=(
                _reverse(PmxReferenceTargetKind.TEXTURE, len(source.texture_paths)),
            )
        )

        result = transform_pmx_document(source, intent)

        self.assertEqual(result.rigid_bodies[0].mass, -1.0)

    def test_noop_intent_does_not_turn_orchestrator_into_validator(self) -> None:
        source = _document()
        invalid_body = replace(source.rigid_bodies[0], mass=-1.0)
        source = replace(
            source,
            rigid_bodies=(invalid_body, source.rigid_bodies[1]),
        )
        self.assertIs(
            transform_pmx_document(source, PmxStructuralTransformIntent()),
            source,
        )


if __name__ == "__main__":
    unittest.main()
