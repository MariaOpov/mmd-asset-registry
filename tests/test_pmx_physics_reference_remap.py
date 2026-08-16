from __future__ import annotations

import unittest

import mmd_registry.pmx as pmx_public
import mmd_registry.services as services_public
from mmd_registry.pmx.collection_transform import PmxCollectionTransform
from mmd_registry.pmx.document import (
    PmxGroupMorphOffset,
    PmxImpulseMorphOffset,
    PmxJoint,
    PmxMorph,
    PmxRigidBody,
    PmxSoftBody,
    PmxSoftBodyAnchor,
    PmxSoftBodyClusterConfig,
    PmxSoftBodyConfig,
    PmxSoftBodyIterationConfig,
    PmxSoftBodyMaterialConfig,
)
from mmd_registry.pmx.index_remap import PmxIndexRemap
from mmd_registry.pmx.physics_reference_remap import (
    PmxPhysicsReferenceRemapError,
    remap_impulse_morph_rigid_body_references,
    remap_joint_rigid_body_references,
    remap_soft_body_references,
    transform_rigid_body_collection_references,
)
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind


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


def _impulse(index: int) -> PmxImpulseMorphOffset:
    return PmxImpulseMorphOffset(
        rigid_body_index=index,
        local=False,
        velocity=(1.0, 2.0, 3.0),
        angular_torque=(4.0, 5.0, 6.0),
    )


def _morph(
    name: str,
    morph_type: int,
    offsets: tuple[object, ...],
) -> PmxMorph:
    return PmxMorph(
        local_name=name,
        universal_name=name,
        panel=1,
        panel_name="eyebrows",
        morph_type=morph_type,
        morph_type_name=f"type_{morph_type}",
        offsets=offsets,
    )


def _rigid_body(name: str, bone_index: int) -> PmxRigidBody:
    return PmxRigidBody(
        local_name=name,
        universal_name=name,
        bone_index=bone_index,
        collision_group=0,
        collision_mask=0xFFFF,
        shape=0,
        shape_name="sphere",
        size=(1.0, 1.0, 1.0),
        position=(0.0, 0.0, 0.0),
        rotation=(0.0, 0.0, 0.0),
        mass=1.0,
        linear_damping=0.5,
        angular_damping=0.5,
        restitution=0.0,
        friction=0.5,
        physics_mode=0,
        physics_mode_name="follow_bone",
    )


def _joint(
    *,
    joint_type: int = 0,
    rigid_body_a_index: int = 0,
    rigid_body_b_index: int = 1,
) -> PmxJoint:
    zero = (0.0, 0.0, 0.0)
    return PmxJoint(
        local_name="Joint",
        universal_name="Joint",
        joint_type=joint_type,
        joint_type_name=f"type_{joint_type}",
        rigid_body_a_index=rigid_body_a_index,
        rigid_body_b_index=rigid_body_b_index,
        position=zero,
        rotation=zero,
        translation_limit_minimum=zero,
        translation_limit_maximum=zero,
        rotation_limit_minimum=zero,
        rotation_limit_maximum=zero,
        translation_spring=zero,
        rotation_spring=zero,
    )


def _soft_body(
    *,
    material_index: int = 0,
    anchors: tuple[PmxSoftBodyAnchor, ...] = (),
    pinned_vertex_indices: tuple[int, ...] = (),
) -> PmxSoftBody:
    config = PmxSoftBodyConfig(
        aerodynamics_model=0,
        aerodynamics_model_name="vertex_point",
        velocity_correction_factor=0.0,
        damping_coefficient=0.0,
        drag_coefficient=0.0,
        lift_coefficient=0.0,
        pressure_coefficient=0.0,
        volume_conservation_coefficient=0.0,
        dynamic_friction_coefficient=0.0,
        pose_matching_coefficient=0.0,
        rigid_contact_hardness=0.0,
        kinetic_contact_hardness=0.0,
        soft_contact_hardness=0.0,
        anchor_hardness=0.0,
    )
    cluster_config = PmxSoftBodyClusterConfig(
        soft_rigid_hardness=0.0,
        soft_kinetic_hardness=0.0,
        soft_soft_hardness=0.0,
        soft_rigid_impulse_split=0.0,
        soft_kinetic_impulse_split=0.0,
        soft_soft_impulse_split=0.0,
    )
    iteration_config = PmxSoftBodyIterationConfig(
        velocity=0,
        position=0,
        drift=0,
        cluster=0,
    )
    material_config = PmxSoftBodyMaterialConfig(
        linear_stiffness=0.0,
        area_angular_stiffness=0.0,
        volume_stiffness=0.0,
    )
    return PmxSoftBody(
        local_name="Soft",
        universal_name="Soft",
        shape=0,
        shape_name="tri_mesh",
        material_index=material_index,
        collision_group=0,
        collision_mask=0xFFFF,
        flags=0,
        flag_names=(),
        bending_link_distance=0,
        cluster_count=0,
        total_mass=1.0,
        collision_margin=0.1,
        config=config,
        cluster_config=cluster_config,
        iteration_config=iteration_config,
        material_config=material_config,
        anchors=anchors,
        pinned_vertex_indices=pinned_vertex_indices,
    )


class ImpulseMorphRigidBodyReferenceTests(unittest.TestCase):
    def test_identity_returns_original_tuple(self) -> None:
        morphs = (_morph("Impulse", 10, (_impulse(0),)),)
        result = remap_impulse_morph_rigid_body_references(
            morphs,
            _identity(PmxReferenceTargetKind.RIGID_BODY, 1),
            pmx_version=2.1,
        )
        self.assertIs(result, morphs)

    def test_impulse_reference_is_remapped(self) -> None:
        morphs = (_morph("Impulse", 10, (_impulse(0),)),)
        result = remap_impulse_morph_rigid_body_references(
            morphs,
            _transform(PmxReferenceTargetKind.RIGID_BODY, (1, 0), 2),
            pmx_version=2.1,
        )
        offset = result[0].offsets[0]
        self.assertEqual(offset.rigid_body_index, 1)
        self.assertEqual(offset.velocity, (1.0, 2.0, 3.0))
        self.assertEqual(offset.angular_torque, (4.0, 5.0, 6.0))

    def test_removed_impulse_target_blocks(self) -> None:
        morphs = (_morph("Impulse", 10, (_impulse(1),)),)
        with self.assertRaisesRegex(
            PmxPhysicsReferenceRemapError,
            "removed rigid_body index 1",
        ):
            remap_impulse_morph_rigid_body_references(
                morphs,
                _transform(
                    PmxReferenceTargetKind.RIGID_BODY,
                    (0, None),
                    1,
                ),
                pmx_version=2.1,
            )

    def test_impulse_reference_rejects_sentinel(self) -> None:
        morphs = (_morph("Impulse", 10, (_impulse(-1),)),)
        with self.assertRaisesRegex(ValueError, "cannot be negative"):
            remap_impulse_morph_rigid_body_references(
                morphs,
                _identity(PmxReferenceTargetKind.RIGID_BODY, 1),
                pmx_version=2.1,
            )

    def test_impulse_morph_requires_pmx21(self) -> None:
        morphs = (_morph("Impulse", 10, (_impulse(0),)),)
        with self.assertRaisesRegex(ValueError, "type 10 requires PMX 2.1"):
            remap_impulse_morph_rigid_body_references(
                morphs,
                _identity(PmxReferenceTargetKind.RIGID_BODY, 1),
                pmx_version=2.0,
            )

    def test_non_impulse_morph_is_not_cp14_validated_or_rewritten(self) -> None:
        foreign_offset = PmxGroupMorphOffset(morph_index=99, weight=0.5)
        morphs = (_morph("Group", 0, (foreign_offset,)),)
        result = remap_impulse_morph_rigid_body_references(
            morphs,
            _identity(PmxReferenceTargetKind.RIGID_BODY, 0),
            pmx_version=2.0,
        )
        self.assertIs(result, morphs)
        self.assertIs(result[0].offsets[0], foreign_offset)

    def test_type10_offset_mismatch_fails_closed(self) -> None:
        morphs = (
            _morph(
                "Impulse",
                10,
                (PmxGroupMorphOffset(morph_index=0, weight=0.5),),
            ),
        )
        with self.assertRaisesRegex(ValueError, "requires PmxImpulseMorphOffset"):
            remap_impulse_morph_rigid_body_references(
                morphs,
                _identity(PmxReferenceTargetKind.RIGID_BODY, 1),
                pmx_version=2.1,
            )

    def test_wrong_rigid_body_transform_kind_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "rigid_body_transform kind must be rigid_body",
        ):
            remap_impulse_morph_rigid_body_references(
                (),
                _identity(PmxReferenceTargetKind.BONE, 0),
                pmx_version=2.1,
            )

    def test_impulse_remap_is_deterministic(self) -> None:
        morphs = (_morph("Impulse", 10, (_impulse(0),)),)
        transform = _transform(
            PmxReferenceTargetKind.RIGID_BODY,
            (1, 0),
            2,
        )
        first = remap_impulse_morph_rigid_body_references(
            morphs,
            transform,
            pmx_version=2.1,
        )
        second = remap_impulse_morph_rigid_body_references(
            morphs,
            transform,
            pmx_version=2.1,
        )
        self.assertEqual(first, second)


class RigidBodyCollectionReferenceTransformTests(unittest.TestCase):
    def test_identity_returns_original_tuple(self) -> None:
        bodies = (_rigid_body("A", 0),)
        result = transform_rigid_body_collection_references(
            bodies,
            _identity(PmxReferenceTargetKind.RIGID_BODY, 1),
            _identity(PmxReferenceTargetKind.BONE, 1),
        )
        self.assertIs(result, bodies)

    def test_reorder_moves_bodies_and_remaps_bones(self) -> None:
        bodies = (
            _rigid_body("A", 0),
            _rigid_body("B", 1),
        )
        result = transform_rigid_body_collection_references(
            bodies,
            _transform(
                PmxReferenceTargetKind.RIGID_BODY,
                (1, 0),
                2,
            ),
            _transform(PmxReferenceTargetKind.BONE, (1, 0), 2),
        )
        self.assertEqual(
            tuple(body.local_name for body in result),
            ("B", "A"),
        )
        self.assertEqual(
            tuple(body.bone_index for body in result),
            (0, 1),
        )
        self.assertEqual(
            tuple(body.bone_index for body in bodies),
            (0, 1),
        )

    def test_delete_unreferenced_rigid_body_is_allowed(self) -> None:
        bodies = (
            _rigid_body("A", 0),
            _rigid_body("B", -1),
        )
        result = transform_rigid_body_collection_references(
            bodies,
            _transform(
                PmxReferenceTargetKind.RIGID_BODY,
                (0, None),
                1,
            ),
            _identity(PmxReferenceTargetKind.BONE, 1),
        )
        self.assertEqual(
            tuple(body.local_name for body in result),
            ("A",),
        )

    def test_deleted_source_outgoing_bone_reference_is_ignored(self) -> None:
        bodies = (
            _rigid_body("Deleted", 1),
            _rigid_body("Survivor", 0),
        )
        result = transform_rigid_body_collection_references(
            bodies,
            _transform(
                PmxReferenceTargetKind.RIGID_BODY,
                (None, 0),
                1,
            ),
            _transform(PmxReferenceTargetKind.BONE, (0, None), 1),
        )
        self.assertEqual(
            tuple(body.local_name for body in result),
            ("Survivor",),
        )
        self.assertEqual(result[0].bone_index, 0)

    def test_surviving_body_reference_to_deleted_bone_blocks(self) -> None:
        bodies = (_rigid_body("A", 1),)
        with self.assertRaisesRegex(
            PmxPhysicsReferenceRemapError,
            "removed bone index 1",
        ):
            transform_rigid_body_collection_references(
                bodies,
                _identity(PmxReferenceTargetKind.RIGID_BODY, 1),
                _transform(PmxReferenceTargetKind.BONE, (0, None), 1),
            )

    def test_rigid_body_bone_sentinel_is_preserved(self) -> None:
        bodies = (_rigid_body("A", -1),)
        result = transform_rigid_body_collection_references(
            bodies,
            _identity(PmxReferenceTargetKind.RIGID_BODY, 1),
            _identity(PmxReferenceTargetKind.BONE, 0),
        )
        self.assertIs(result, bodies)

    def test_removed_bone_target_does_not_become_sentinel(self) -> None:
        bodies = (_rigid_body("A", 1),)
        with self.assertRaisesRegex(
            PmxPhysicsReferenceRemapError,
            "not converted to the -1 sentinel",
        ):
            transform_rigid_body_collection_references(
                bodies,
                _identity(PmxReferenceTargetKind.RIGID_BODY, 1),
                _transform(PmxReferenceTargetKind.BONE, (0, None), 1),
            )

    def test_source_transform_old_size_must_match(self) -> None:
        bodies = (_rigid_body("A", 0),)
        with self.assertRaisesRegex(ValueError, "old_size must match"):
            transform_rigid_body_collection_references(
                bodies,
                _identity(PmxReferenceTargetKind.RIGID_BODY, 2),
                _identity(PmxReferenceTargetKind.BONE, 1),
            )

    def test_wrong_source_transform_kind_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "rigid_body_transform kind must be rigid_body",
        ):
            transform_rigid_body_collection_references(
                (),
                _identity(PmxReferenceTargetKind.BONE, 0),
                _identity(PmxReferenceTargetKind.BONE, 0),
            )

    def test_wrong_bone_transform_kind_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "bone_transform kind must be bone"):
            transform_rigid_body_collection_references(
                (),
                _identity(PmxReferenceTargetKind.RIGID_BODY, 0),
                _identity(PmxReferenceTargetKind.VERTEX, 0),
            )

    def test_rigid_body_transform_is_deterministic(self) -> None:
        bodies = (
            _rigid_body("A", 0),
            _rigid_body("B", 1),
        )
        source_transform = _transform(
            PmxReferenceTargetKind.RIGID_BODY,
            (1, 0),
            2,
        )
        bone_transform = _transform(
            PmxReferenceTargetKind.BONE,
            (1, 0),
            2,
        )
        first = transform_rigid_body_collection_references(
            bodies,
            source_transform,
            bone_transform,
        )
        second = transform_rigid_body_collection_references(
            bodies,
            source_transform,
            bone_transform,
        )
        self.assertEqual(first, second)


class JointRigidBodyReferenceTests(unittest.TestCase):
    def test_identity_returns_original_tuple(self) -> None:
        joints = (_joint(),)
        result = remap_joint_rigid_body_references(
            joints,
            _identity(PmxReferenceTargetKind.RIGID_BODY, 2),
            pmx_version=2.0,
        )
        self.assertIs(result, joints)

    def test_both_joint_references_are_remapped(self) -> None:
        joints = (_joint(rigid_body_a_index=0, rigid_body_b_index=1),)
        result = remap_joint_rigid_body_references(
            joints,
            _transform(
                PmxReferenceTargetKind.RIGID_BODY,
                (1, 0),
                2,
            ),
            pmx_version=2.1,
        )
        self.assertEqual(result[0].rigid_body_a_index, 1)
        self.assertEqual(result[0].rigid_body_b_index, 0)

    def test_joint_sentinels_are_preserved(self) -> None:
        joints = (
            _joint(
                rigid_body_a_index=-1,
                rigid_body_b_index=-1,
            ),
        )
        result = remap_joint_rigid_body_references(
            joints,
            _identity(PmxReferenceTargetKind.RIGID_BODY, 0),
            pmx_version=2.0,
        )
        self.assertIs(result, joints)

    def test_removed_joint_target_blocks(self) -> None:
        joints = (_joint(rigid_body_a_index=1, rigid_body_b_index=-1),)
        with self.assertRaises(PmxPhysicsReferenceRemapError):
            remap_joint_rigid_body_references(
                joints,
                _transform(
                    PmxReferenceTargetKind.RIGID_BODY,
                    (0, None),
                    1,
                ),
                pmx_version=2.1,
            )

    def test_removed_joint_target_does_not_become_sentinel(self) -> None:
        joints = (_joint(rigid_body_a_index=1, rigid_body_b_index=-1),)
        with self.assertRaisesRegex(
            PmxPhysicsReferenceRemapError,
            "not converted to the -1 sentinel",
        ):
            remap_joint_rigid_body_references(
                joints,
                _transform(
                    PmxReferenceTargetKind.RIGID_BODY,
                    (0, None),
                    1,
                ),
                pmx_version=2.1,
            )

    def test_pmx20_allows_joint_type_zero(self) -> None:
        joints = (_joint(joint_type=0),)
        self.assertIs(
            remap_joint_rigid_body_references(
                joints,
                _identity(PmxReferenceTargetKind.RIGID_BODY, 2),
                pmx_version=2.0,
            ),
            joints,
        )

    def test_pmx20_rejects_nonzero_joint_type(self) -> None:
        joints = (_joint(joint_type=1),)
        with self.assertRaisesRegex(ValueError, "type 1 requires PMX 2.1"):
            remap_joint_rigid_body_references(
                joints,
                _identity(PmxReferenceTargetKind.RIGID_BODY, 2),
                pmx_version=2.0,
            )

    def test_pmx21_accepts_all_joint_types(self) -> None:
        joints = tuple(_joint(joint_type=value) for value in range(6))
        result = remap_joint_rigid_body_references(
            joints,
            _identity(PmxReferenceTargetKind.RIGID_BODY, 2),
            pmx_version=2.1,
        )
        self.assertIs(result, joints)

    def test_wrong_transform_kind_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "rigid_body_transform kind must be rigid_body",
        ):
            remap_joint_rigid_body_references(
                (),
                _identity(PmxReferenceTargetKind.BONE, 0),
                pmx_version=2.1,
            )

    def test_invalid_pmx_version_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "pmx_version must be 2.0 or 2.1"):
            remap_joint_rigid_body_references(
                (),
                _identity(PmxReferenceTargetKind.RIGID_BODY, 0),
                pmx_version=2.2,
            )

    def test_non_float_pmx_version_is_rejected(self) -> None:
        with self.assertRaisesRegex(TypeError, "pmx_version must be a float"):
            remap_joint_rigid_body_references(
                (),
                _identity(PmxReferenceTargetKind.RIGID_BODY, 0),
                pmx_version=2,  # type: ignore[arg-type]
            )

    def test_joint_remap_is_deterministic(self) -> None:
        joints = (_joint(rigid_body_a_index=0, rigid_body_b_index=1),)
        transform = _transform(
            PmxReferenceTargetKind.RIGID_BODY,
            (1, 0),
            2,
        )
        first = remap_joint_rigid_body_references(
            joints,
            transform,
            pmx_version=2.1,
        )
        second = remap_joint_rigid_body_references(
            joints,
            transform,
            pmx_version=2.1,
        )
        self.assertEqual(first, second)


class SoftBodyReferenceTests(unittest.TestCase):
    def test_identity_returns_original_tuple(self) -> None:
        bodies = (
            _soft_body(
                anchors=(
                    PmxSoftBodyAnchor(
                        rigid_body_index=0,
                        vertex_index=0,
                        near_mode=False,
                    ),
                ),
                pinned_vertex_indices=(0,),
            ),
        )
        result = remap_soft_body_references(
            bodies,
            _identity(PmxReferenceTargetKind.MATERIAL, 1),
            _identity(PmxReferenceTargetKind.RIGID_BODY, 1),
            _identity(PmxReferenceTargetKind.VERTEX, 1),
            pmx_version=2.1,
        )
        self.assertIs(result, bodies)

    def test_material_reference_is_remapped(self) -> None:
        bodies = (_soft_body(material_index=0),)
        result = remap_soft_body_references(
            bodies,
            _transform(PmxReferenceTargetKind.MATERIAL, (1, 0), 2),
            _identity(PmxReferenceTargetKind.RIGID_BODY, 0),
            _identity(PmxReferenceTargetKind.VERTEX, 0),
            pmx_version=2.1,
        )
        self.assertEqual(result[0].material_index, 1)

    def test_material_sentinel_is_preserved(self) -> None:
        bodies = (_soft_body(material_index=-1),)
        result = remap_soft_body_references(
            bodies,
            _identity(PmxReferenceTargetKind.MATERIAL, 0),
            _identity(PmxReferenceTargetKind.RIGID_BODY, 0),
            _identity(PmxReferenceTargetKind.VERTEX, 0),
            pmx_version=2.1,
        )
        self.assertIs(result, bodies)

    def test_removed_material_target_blocks(self) -> None:
        bodies = (_soft_body(material_index=1),)
        with self.assertRaisesRegex(
            PmxPhysicsReferenceRemapError,
            "not converted to the -1 sentinel",
        ):
            remap_soft_body_references(
                bodies,
                _transform(PmxReferenceTargetKind.MATERIAL, (0, None), 1),
                _identity(PmxReferenceTargetKind.RIGID_BODY, 0),
                _identity(PmxReferenceTargetKind.VERTEX, 0),
                pmx_version=2.1,
            )

    def test_anchor_rigid_body_and_vertex_are_remapped(self) -> None:
        anchor = PmxSoftBodyAnchor(
            rigid_body_index=0,
            vertex_index=0,
            near_mode=True,
        )
        bodies = (_soft_body(anchors=(anchor,)),)
        result = remap_soft_body_references(
            bodies,
            _identity(PmxReferenceTargetKind.MATERIAL, 1),
            _transform(PmxReferenceTargetKind.RIGID_BODY, (1, 0), 2),
            _transform(PmxReferenceTargetKind.VERTEX, (1, 0), 2),
            pmx_version=2.1,
        )
        rewritten_anchor = result[0].anchors[0]
        self.assertEqual(rewritten_anchor.rigid_body_index, 1)
        self.assertEqual(rewritten_anchor.vertex_index, 1)
        self.assertTrue(rewritten_anchor.near_mode)

    def test_pinned_vertex_indices_are_remapped_in_order(self) -> None:
        bodies = (_soft_body(pinned_vertex_indices=(0, 1)),)
        result = remap_soft_body_references(
            bodies,
            _identity(PmxReferenceTargetKind.MATERIAL, 1),
            _identity(PmxReferenceTargetKind.RIGID_BODY, 0),
            _transform(PmxReferenceTargetKind.VERTEX, (1, 0), 2),
            pmx_version=2.1,
        )
        self.assertEqual(result[0].pinned_vertex_indices, (1, 0))

    def test_removed_anchor_rigid_body_target_blocks(self) -> None:
        bodies = (
            _soft_body(
                anchors=(
                    PmxSoftBodyAnchor(
                        rigid_body_index=1,
                        vertex_index=0,
                        near_mode=False,
                    ),
                ),
            ),
        )
        with self.assertRaises(PmxPhysicsReferenceRemapError):
            remap_soft_body_references(
                bodies,
                _identity(PmxReferenceTargetKind.MATERIAL, 1),
                _transform(
                    PmxReferenceTargetKind.RIGID_BODY,
                    (0, None),
                    1,
                ),
                _identity(PmxReferenceTargetKind.VERTEX, 1),
                pmx_version=2.1,
            )

    def test_removed_anchor_vertex_target_blocks(self) -> None:
        bodies = (
            _soft_body(
                anchors=(
                    PmxSoftBodyAnchor(
                        rigid_body_index=0,
                        vertex_index=1,
                        near_mode=False,
                    ),
                ),
            ),
        )
        with self.assertRaises(PmxPhysicsReferenceRemapError):
            remap_soft_body_references(
                bodies,
                _identity(PmxReferenceTargetKind.MATERIAL, 1),
                _identity(PmxReferenceTargetKind.RIGID_BODY, 1),
                _transform(PmxReferenceTargetKind.VERTEX, (0, None), 1),
                pmx_version=2.1,
            )

    def test_removed_pinned_vertex_target_blocks(self) -> None:
        bodies = (_soft_body(pinned_vertex_indices=(1,)),)
        with self.assertRaises(PmxPhysicsReferenceRemapError):
            remap_soft_body_references(
                bodies,
                _identity(PmxReferenceTargetKind.MATERIAL, 1),
                _identity(PmxReferenceTargetKind.RIGID_BODY, 0),
                _transform(PmxReferenceTargetKind.VERTEX, (0, None), 1),
                pmx_version=2.1,
            )

    def test_anchor_required_reference_rejects_sentinel(self) -> None:
        bodies = (
            _soft_body(
                anchors=(
                    PmxSoftBodyAnchor(
                        rigid_body_index=-1,
                        vertex_index=0,
                        near_mode=False,
                    ),
                ),
            ),
        )
        with self.assertRaisesRegex(ValueError, "cannot be negative"):
            remap_soft_body_references(
                bodies,
                _identity(PmxReferenceTargetKind.MATERIAL, 1),
                _identity(PmxReferenceTargetKind.RIGID_BODY, 1),
                _identity(PmxReferenceTargetKind.VERTEX, 1),
                pmx_version=2.1,
            )

    def test_pin_required_reference_rejects_sentinel(self) -> None:
        bodies = (_soft_body(pinned_vertex_indices=(-1,)),)
        with self.assertRaisesRegex(ValueError, "cannot be negative"):
            remap_soft_body_references(
                bodies,
                _identity(PmxReferenceTargetKind.MATERIAL, 1),
                _identity(PmxReferenceTargetKind.RIGID_BODY, 0),
                _identity(PmxReferenceTargetKind.VERTEX, 1),
                pmx_version=2.1,
            )

    def test_pmx20_allows_empty_soft_body_section(self) -> None:
        result = remap_soft_body_references(
            (),
            _identity(PmxReferenceTargetKind.MATERIAL, 0),
            _identity(PmxReferenceTargetKind.RIGID_BODY, 0),
            _identity(PmxReferenceTargetKind.VERTEX, 0),
            pmx_version=2.0,
        )
        self.assertEqual(result, ())

    def test_pmx20_rejects_nonempty_soft_body_section(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "PMX 2.0 cannot contain a soft-body section",
        ):
            remap_soft_body_references(
                (_soft_body(material_index=-1),),
                _identity(PmxReferenceTargetKind.MATERIAL, 0),
                _identity(PmxReferenceTargetKind.RIGID_BODY, 0),
                _identity(PmxReferenceTargetKind.VERTEX, 0),
                pmx_version=2.0,
            )

    def test_wrong_material_transform_kind_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "material_transform kind must be material",
        ):
            remap_soft_body_references(
                (),
                _identity(PmxReferenceTargetKind.BONE, 0),
                _identity(PmxReferenceTargetKind.RIGID_BODY, 0),
                _identity(PmxReferenceTargetKind.VERTEX, 0),
                pmx_version=2.1,
            )

    def test_wrong_rigid_body_transform_kind_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "rigid_body_transform kind must be rigid_body",
        ):
            remap_soft_body_references(
                (),
                _identity(PmxReferenceTargetKind.MATERIAL, 0),
                _identity(PmxReferenceTargetKind.BONE, 0),
                _identity(PmxReferenceTargetKind.VERTEX, 0),
                pmx_version=2.1,
            )

    def test_wrong_vertex_transform_kind_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "vertex_transform kind must be vertex",
        ):
            remap_soft_body_references(
                (),
                _identity(PmxReferenceTargetKind.MATERIAL, 0),
                _identity(PmxReferenceTargetKind.RIGID_BODY, 0),
                _identity(PmxReferenceTargetKind.BONE, 0),
                pmx_version=2.1,
            )

    def test_soft_body_remap_is_deterministic(self) -> None:
        bodies = (
            _soft_body(
                anchors=(
                    PmxSoftBodyAnchor(
                        rigid_body_index=0,
                        vertex_index=0,
                        near_mode=True,
                    ),
                ),
                pinned_vertex_indices=(0, 1),
            ),
        )
        material_transform = _identity(PmxReferenceTargetKind.MATERIAL, 1)
        rigid_body_transform = _transform(
            PmxReferenceTargetKind.RIGID_BODY,
            (1, 0),
            2,
        )
        vertex_transform = _transform(
            PmxReferenceTargetKind.VERTEX,
            (1, 0),
            2,
        )
        first = remap_soft_body_references(
            bodies,
            material_transform,
            rigid_body_transform,
            vertex_transform,
            pmx_version=2.1,
        )
        second = remap_soft_body_references(
            bodies,
            material_transform,
            rigid_body_transform,
            vertex_transform,
            pmx_version=2.1,
        )
        self.assertEqual(first, second)


class Cp14BoundaryTests(unittest.TestCase):
    def test_cp14_kernel_is_not_exported_from_public_roots(self) -> None:
        forbidden = (
            "PmxPhysicsReferenceRemapError",
            "remap_impulse_morph_rigid_body_references",
            "remap_joint_rigid_body_references",
            "remap_soft_body_references",
            "transform_rigid_body_collection_references",
        )
        for name in forbidden:
            with self.subTest(name=name):
                self.assertFalse(hasattr(pmx_public, name))
                self.assertFalse(hasattr(services_public, name))


if __name__ == "__main__":
    unittest.main()
