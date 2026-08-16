from __future__ import annotations

import unittest

import mmd_registry.pmx as pmx_public
import mmd_registry.services as services_public
from mmd_registry.pmx.bone_reference_remap import (
    PmxBoneReferenceRemapError,
    remap_vertex_deform_bone_references,
    transform_bone_collection_references,
)
from mmd_registry.pmx.collection_transform import PmxCollectionTransform
from mmd_registry.pmx.document import (
    PMX_BONE_FLAG_IK,
    PMX_BONE_FLAG_INHERIT_ROTATION,
    PMX_BONE_FLAG_TAIL_INDEX,
    PmxBdef1,
    PmxBdef2,
    PmxBdef4,
    PmxBone,
    PmxIk,
    PmxIkLink,
    PmxQdef,
    PmxSdef,
    PmxVertex,
)
from mmd_registry.pmx.index_remap import PmxIndexRemap
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind


def _transform(
    targets: tuple[int | None, ...],
    new_size: int,
    *,
    kind: PmxReferenceTargetKind = PmxReferenceTargetKind.BONE,
) -> PmxCollectionTransform:
    return PmxCollectionTransform(
        kind=kind,
        remap=PmxIndexRemap(targets=targets, new_size=new_size),
    )


def _vertex(deform: object) -> PmxVertex:
    return PmxVertex(
        position=(0.0, 0.0, 0.0),
        normal=(0.0, 1.0, 0.0),
        uv=(0.0, 0.0),
        additional_uvs=(),
        deform=deform,
        edge_scale=1.0,
    )


def _ik(target: int, *links: int) -> PmxIk:
    return PmxIk(
        target_bone_index=target,
        loop_count=1,
        angle_limit=0.5,
        links=tuple(
            PmxIkLink(
                bone_index=index,
                angle_limits_enabled=False,
                lower_limit=None,
                upper_limit=None,
            )
            for index in links
        ),
    )


def _bone(
    name: str,
    *,
    parent: int = -1,
    flags: int = 0,
    tail_mode: str = "offset",
    tail_bone_index: int | None = None,
    tail_offset: tuple[float, float, float] | None = (0.0, 1.0, 0.0),
    inherit_parent: int | None = None,
    inherit_weight: float | None = None,
    ik: PmxIk | None = None,
) -> PmxBone:
    return PmxBone(
        local_name=name,
        universal_name=name,
        position=(0.0, 0.0, 0.0),
        parent_bone_index=parent,
        transform_layer=0,
        flags=flags,
        flag_names=(),
        tail_mode=tail_mode,
        tail_bone_index=tail_bone_index,
        tail_offset=tail_offset,
        inherit_parent_bone_index=inherit_parent,
        inherit_weight=inherit_weight,
        fixed_axis=None,
        local_axis_x=None,
        local_axis_z=None,
        external_parent_key=None,
        ik=ik,
    )


class VertexDeformBoneReferenceRemapTests(unittest.TestCase):
    def test_identity_returns_original_tuple(self) -> None:
        vertices = (_vertex(PmxBdef1(0)),)
        result = remap_vertex_deform_bone_references(
            vertices,
            PmxCollectionTransform.identity(PmxReferenceTargetKind.BONE, 1),
            pmx_version=2.0,
        )
        self.assertIs(result, vertices)

    def test_bdef1_reorders_reference(self) -> None:
        vertices = (_vertex(PmxBdef1(0)),)
        result = remap_vertex_deform_bone_references(
            vertices, _transform((1, 0), 2), pmx_version=2.0
        )
        self.assertEqual(result[0].deform.bone_index, 1)
        self.assertEqual(vertices[0].deform.bone_index, 0)

    def test_bdef1_sentinel_is_preserved(self) -> None:
        vertices = (_vertex(PmxBdef1(-1)),)
        result = remap_vertex_deform_bone_references(
            vertices, _transform((1, 0), 2), pmx_version=2.0
        )
        self.assertIs(result, vertices)

    def test_removed_bdef1_reference_blocks(self) -> None:
        vertices = (_vertex(PmxBdef1(1)),)
        with self.assertRaisesRegex(PmxBoneReferenceRemapError, "removed bone index 1"):
            remap_vertex_deform_bone_references(
                vertices, _transform((0, None), 1), pmx_version=2.0
            )

    def test_bdef2_remaps_each_slot_and_preserves_sentinel(self) -> None:
        vertices = (_vertex(PmxBdef2((0, -1), 0.75)),)
        result = remap_vertex_deform_bone_references(
            vertices, _transform((1, 0), 2), pmx_version=2.0
        )
        self.assertEqual(result[0].deform.bone_indices, (1, -1))
        self.assertEqual(result[0].deform.bone_1_weight, 0.75)

    def test_bdef4_remaps_all_slots(self) -> None:
        deform = PmxBdef4((0, 1, 2, 3), (0.1, 0.2, 0.3, 0.4))
        result = remap_vertex_deform_bone_references(
            (_vertex(deform),), _transform((3, 2, 1, 0), 4), pmx_version=2.0
        )
        self.assertEqual(result[0].deform.bone_indices, (3, 2, 1, 0))
        self.assertEqual(result[0].deform.weights, deform.weights)

    def test_sdef_remap_preserves_geometry_payload(self) -> None:
        deform = PmxSdef(
            (0, 1),
            0.4,
            (1.0, 2.0, 3.0),
            (4.0, 5.0, 6.0),
            (7.0, 8.0, 9.0),
        )
        result = remap_vertex_deform_bone_references(
            (_vertex(deform),), _transform((1, 0), 2), pmx_version=2.0
        )
        self.assertEqual(result[0].deform.bone_indices, (1, 0))
        self.assertEqual(result[0].deform.c, deform.c)
        self.assertEqual(result[0].deform.r0, deform.r0)
        self.assertEqual(result[0].deform.r1, deform.r1)

    def test_qdef_remaps_in_pmx21(self) -> None:
        deform = PmxQdef((0, 1, -1, -1), (0.5, 0.5, 0.0, 0.0))
        result = remap_vertex_deform_bone_references(
            (_vertex(deform),), _transform((1, 0), 2), pmx_version=2.1
        )
        self.assertEqual(result[0].deform.bone_indices, (1, 0, -1, -1))

    def test_qdef_is_rejected_for_pmx20(self) -> None:
        deform = PmxQdef((0, -1, -1, -1), (1.0, 0.0, 0.0, 0.0))
        with self.assertRaisesRegex(ValueError, "QDEF requires PMX 2.1"):
            remap_vertex_deform_bone_references(
                (_vertex(deform),), _transform((0,), 1), pmx_version=2.0
            )

    def test_invalid_version_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "pmx_version must be 2.0 or 2.1"):
            remap_vertex_deform_bone_references(
                (_vertex(PmxBdef1(0)),), _transform((0,), 1), pmx_version=2.2
            )

    def test_non_float_version_is_rejected(self) -> None:
        with self.assertRaisesRegex(TypeError, "pmx_version must be a float"):
            remap_vertex_deform_bone_references(
                (_vertex(PmxBdef1(0)),), _transform((0,), 1), pmx_version=2
            )

    def test_wrong_transform_kind_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "kind must be bone"):
            remap_vertex_deform_bone_references(
                (_vertex(PmxBdef1(0)),),
                _transform((0,), 1, kind=PmxReferenceTargetKind.TEXTURE),
                pmx_version=2.0,
            )

    def test_out_of_domain_reference_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "outside bone old_size 1"):
            remap_vertex_deform_bone_references(
                (_vertex(PmxBdef1(1)),), _transform((0,), 1), pmx_version=2.0
            )

    def test_remap_is_deterministic(self) -> None:
        vertices = (_vertex(PmxBdef2((0, 1), 0.5)),)
        transform = _transform((1, 0), 2)
        first = remap_vertex_deform_bone_references(
            vertices, transform, pmx_version=2.0
        )
        second = remap_vertex_deform_bone_references(
            vertices, transform, pmx_version=2.0
        )
        self.assertEqual(first, second)


class BoneCollectionReferenceTransformTests(unittest.TestCase):
    def test_identity_returns_original_tuple(self) -> None:
        bones = (_bone("A"), _bone("B", parent=0))
        result = transform_bone_collection_references(
            bones, PmxCollectionTransform.identity(PmxReferenceTargetKind.BONE, 2)
        )
        self.assertIs(result, bones)

    def test_reorder_moves_bones_and_remaps_parent(self) -> None:
        bones = (_bone("A"), _bone("B", parent=0))
        result = transform_bone_collection_references(bones, _transform((1, 0), 2))
        self.assertEqual(tuple(bone.local_name for bone in result), ("B", "A"))
        self.assertEqual(result[0].parent_bone_index, 1)
        self.assertEqual(result[1].parent_bone_index, -1)
        self.assertEqual(bones[1].parent_bone_index, 0)

    def test_delete_unreferenced_bone_is_allowed(self) -> None:
        bones = (_bone("A"), _bone("B"), _bone("C", parent=0))
        result = transform_bone_collection_references(
            bones, _transform((0, None, 1), 2)
        )
        self.assertEqual(tuple(bone.local_name for bone in result), ("A", "C"))
        self.assertEqual(result[1].parent_bone_index, 0)

    def test_delete_referenced_parent_blocks(self) -> None:
        bones = (_bone("A"), _bone("B", parent=0))
        with self.assertRaisesRegex(PmxBoneReferenceRemapError, "removed bone index 0"):
            transform_bone_collection_references(bones, _transform((None, 0), 1))

    def test_deleted_source_outgoing_reference_is_ignored(self) -> None:
        bones = (_bone("A", parent=1), _bone("B"))
        result = transform_bone_collection_references(
            bones, _transform((None, 0), 1)
        )
        self.assertEqual(tuple(bone.local_name for bone in result), ("B",))

    def test_parent_sentinel_is_preserved(self) -> None:
        bones = (_bone("A", parent=-1),)
        result = transform_bone_collection_references(
            bones, PmxCollectionTransform.identity(PmxReferenceTargetKind.BONE, 1)
        )
        self.assertIs(result, bones)

    def test_active_tail_reference_is_remapped(self) -> None:
        bones = (
            _bone(
                "A",
                flags=PMX_BONE_FLAG_TAIL_INDEX,
                tail_mode="bone",
                tail_bone_index=1,
                tail_offset=None,
            ),
            _bone("B"),
        )
        result = transform_bone_collection_references(bones, _transform((1, 0), 2))
        self.assertEqual(result[1].tail_bone_index, 0)

    def test_active_tail_sentinel_is_preserved(self) -> None:
        bones = (
            _bone(
                "A",
                flags=PMX_BONE_FLAG_TAIL_INDEX,
                tail_mode="bone",
                tail_bone_index=-1,
                tail_offset=None,
            ),
        )
        result = transform_bone_collection_references(
            bones, PmxCollectionTransform.identity(PmxReferenceTargetKind.BONE, 1)
        )
        self.assertIs(result, bones)

    def test_removed_active_tail_target_blocks(self) -> None:
        bones = (
            _bone(
                "A",
                flags=PMX_BONE_FLAG_TAIL_INDEX,
                tail_mode="bone",
                tail_bone_index=1,
                tail_offset=None,
            ),
            _bone("B"),
        )
        with self.assertRaises(PmxBoneReferenceRemapError):
            transform_bone_collection_references(bones, _transform((0, None), 1))

    def test_offset_tail_is_not_treated_as_reference(self) -> None:
        bones = (_bone("A", tail_offset=(3.0, 2.0, 1.0)),)
        result = transform_bone_collection_references(
            bones, PmxCollectionTransform.identity(PmxReferenceTargetKind.BONE, 1)
        )
        self.assertIs(result, bones)
        self.assertEqual(result[0].tail_offset, (3.0, 2.0, 1.0))

    def test_tail_flag_requires_bone_payload(self) -> None:
        bones = (_bone("A", flags=PMX_BONE_FLAG_TAIL_INDEX),)
        with self.assertRaisesRegex(ValueError, "tail-index flag requires"):
            transform_bone_collection_references(
                bones, PmxCollectionTransform.identity(PmxReferenceTargetKind.BONE, 1)
            )

    def test_offset_tail_rejects_stale_bone_reference(self) -> None:
        bones = (_bone("A", tail_bone_index=0),)
        with self.assertRaisesRegex(ValueError, "offset-tail mode cannot retain"):
            transform_bone_collection_references(
                bones, PmxCollectionTransform.identity(PmxReferenceTargetKind.BONE, 1)
            )

    def test_active_inherit_reference_is_remapped(self) -> None:
        bones = (
            _bone(
                "A",
                flags=PMX_BONE_FLAG_INHERIT_ROTATION,
                inherit_parent=1,
                inherit_weight=0.5,
            ),
            _bone("B"),
        )
        result = transform_bone_collection_references(bones, _transform((1, 0), 2))
        self.assertEqual(result[1].inherit_parent_bone_index, 0)
        self.assertEqual(result[1].inherit_weight, 0.5)

    def test_active_inherit_sentinel_is_preserved(self) -> None:
        bones = (
            _bone(
                "A",
                flags=PMX_BONE_FLAG_INHERIT_ROTATION,
                inherit_parent=-1,
                inherit_weight=0.5,
            ),
        )
        result = transform_bone_collection_references(
            bones, PmxCollectionTransform.identity(PmxReferenceTargetKind.BONE, 1)
        )
        self.assertIs(result, bones)

    def test_removed_inherit_target_blocks(self) -> None:
        bones = (
            _bone(
                "A",
                flags=PMX_BONE_FLAG_INHERIT_ROTATION,
                inherit_parent=1,
                inherit_weight=0.5,
            ),
            _bone("B"),
        )
        with self.assertRaises(PmxBoneReferenceRemapError):
            transform_bone_collection_references(bones, _transform((0, None), 1))

    def test_inactive_inherit_payload_is_rejected(self) -> None:
        bones = (_bone("A", inherit_parent=0, inherit_weight=0.5),)
        with self.assertRaisesRegex(ValueError, "inherit payload requires"):
            transform_bone_collection_references(
                bones, PmxCollectionTransform.identity(PmxReferenceTargetKind.BONE, 1)
            )

    def test_active_ik_target_and_links_are_remapped(self) -> None:
        bones = (
            _bone("A", flags=PMX_BONE_FLAG_IK, ik=_ik(1, 2, 0)),
            _bone("B"),
            _bone("C"),
        )
        result = transform_bone_collection_references(
            bones, _transform((2, 0, 1), 3)
        )
        ik = result[2].ik
        self.assertIsNotNone(ik)
        self.assertEqual(ik.target_bone_index, 0)
        self.assertEqual(tuple(link.bone_index for link in ik.links), (1, 2))

    def test_removed_ik_target_blocks(self) -> None:
        bones = (
            _bone("A", flags=PMX_BONE_FLAG_IK, ik=_ik(1, 0)),
            _bone("B"),
        )
        with self.assertRaises(PmxBoneReferenceRemapError):
            transform_bone_collection_references(bones, _transform((0, None), 1))

    def test_removed_ik_link_blocks(self) -> None:
        bones = (
            _bone("A", flags=PMX_BONE_FLAG_IK, ik=_ik(0, 1)),
            _bone("B"),
        )
        with self.assertRaises(PmxBoneReferenceRemapError):
            transform_bone_collection_references(bones, _transform((0, None), 1))

    def test_ik_flag_requires_payload(self) -> None:
        bones = (_bone("A", flags=PMX_BONE_FLAG_IK),)
        with self.assertRaisesRegex(ValueError, "IK flag requires IK payload"):
            transform_bone_collection_references(
                bones, PmxCollectionTransform.identity(PmxReferenceTargetKind.BONE, 1)
            )

    def test_inactive_ik_payload_is_rejected(self) -> None:
        bones = (_bone("A", ik=_ik(0, 0)),)
        with self.assertRaisesRegex(ValueError, "IK payload requires the IK flag"):
            transform_bone_collection_references(
                bones, PmxCollectionTransform.identity(PmxReferenceTargetKind.BONE, 1)
            )

    def test_required_ik_reference_does_not_accept_sentinel(self) -> None:
        bones = (_bone("A", flags=PMX_BONE_FLAG_IK, ik=_ik(-1)),)
        with self.assertRaisesRegex(ValueError, "cannot be negative"):
            transform_bone_collection_references(
                bones, PmxCollectionTransform.identity(PmxReferenceTargetKind.BONE, 1)
            )

    def test_self_reference_is_allowed_and_remapped(self) -> None:
        bones = (_bone("A", parent=0), _bone("B"))
        result = transform_bone_collection_references(bones, _transform((1, 0), 2))
        self.assertEqual(result[1].parent_bone_index, 1)

    def test_old_size_must_match_bone_collection(self) -> None:
        with self.assertRaisesRegex(ValueError, "old_size must match"):
            transform_bone_collection_references(
                (_bone("A"),),
                PmxCollectionTransform.identity(PmxReferenceTargetKind.BONE, 2),
            )

    def test_bone_transform_is_deterministic(self) -> None:
        bones = (_bone("A"), _bone("B", parent=0))
        transform = _transform((1, 0), 2)
        self.assertEqual(
            transform_bone_collection_references(bones, transform),
            transform_bone_collection_references(bones, transform),
        )


class Cp12BoundaryTests(unittest.TestCase):
    def test_cp12_kernel_is_not_exported_from_public_roots(self) -> None:
        forbidden = (
            "PmxBoneReferenceRemapError",
            "remap_vertex_deform_bone_references",
            "transform_bone_collection_references",
        )
        for name in forbidden:
            with self.subTest(name=name):
                self.assertFalse(hasattr(pmx_public, name))
                self.assertFalse(hasattr(services_public, name))


if __name__ == "__main__":
    unittest.main()
