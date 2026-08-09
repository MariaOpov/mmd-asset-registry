"""Tests for typed PMX rigid-body, joint, and soft-body reading."""

from __future__ import annotations

import io
import unittest
from dataclasses import FrozenInstanceError, replace

from mmd_registry.binary_reader import BinaryParseError, BinaryReader
from mmd_registry.model_scanning import (
    PmxJoint as LegacyPmxJoint,
    PmxRigidBody as LegacyPmxRigidBody,
    PmxSoftBody as LegacyPmxSoftBody,
    PmxSoftBodyAnchor as LegacyPmxSoftBodyAnchor,
    PmxSoftBodyClusterConfig as LegacyPmxSoftBodyClusterConfig,
    PmxSoftBodyConfig as LegacyPmxSoftBodyConfig,
    PmxSoftBodyIterationConfig as LegacyPmxSoftBodyIterationConfig,
    PmxSoftBodyMaterialConfig as LegacyPmxSoftBodyMaterialConfig,
)
from mmd_registry.pmx import (
    PmxHeader,
    PmxJoint,
    PmxRigidBody,
    PmxSoftBody,
    PmxSoftBodyAnchor,
    PmxSoftBodyClusterConfig,
    PmxSoftBodyConfig,
    PmxSoftBodyIterationConfig,
    PmxSoftBodyMaterialConfig,
)
from mmd_registry.pmx.sections.bones import read_pmx_bones
from mmd_registry.pmx.sections.display_frames import read_pmx_display_frames
from mmd_registry.pmx.sections.geometry import read_pmx_geometry
from mmd_registry.pmx.sections.header import read_pmx_header
from mmd_registry.pmx.sections.joints import (
    PmxJointReadState,
    read_pmx_joints,
)
from mmd_registry.pmx.sections.materials import read_pmx_materials
from mmd_registry.pmx.sections.morphs import read_pmx_morphs
from mmd_registry.pmx.sections.rigid_bodies import (
    PmxRigidBodyReadState,
    read_pmx_rigid_bodies,
)
from mmd_registry.pmx.sections.soft_bodies import (
    PmxSoftBodyReadState,
    read_pmx_soft_bodies,
)
from mmd_registry.pmx.sections.textures import read_pmx_textures
from tests.mmd_fixtures import (
    build_pmx_bone,
    build_pmx_joint,
    build_pmx_rigid_body,
    build_pmx_soft_body,
    build_pmx_soft_body_anchor,
    build_pmx_structure,
)


def reader_at_rigid_body_section(
    data: bytes,
) -> tuple[BinaryReader, PmxHeader, int, int, int]:
    """Return a reader and counts positioned at the rigid-body section."""

    reader = BinaryReader(io.BytesIO(data), format_name="PMX")
    header = read_pmx_header(reader).header
    geometry = read_pmx_geometry(reader, header=header)
    textures = read_pmx_textures(reader, header=header)
    materials = read_pmx_materials(
        reader,
        header=header,
        texture_count=len(textures),
        surface_index_count=len(geometry.surface_indices),
    )
    bones = read_pmx_bones(reader, header=header)
    morphs = read_pmx_morphs(
        reader,
        header=header,
        vertex_count=len(geometry.vertices),
        bone_count=len(bones),
        material_count=len(materials),
    )
    read_pmx_display_frames(
        reader,
        header=header,
        bone_count=len(bones),
        morph_count=len(morphs),
    )
    return (
        reader,
        header,
        len(geometry.vertices),
        len(materials),
        len(bones),
    )


class PmxPhysicsReaderTests(unittest.TestCase):
    """Validate complete immutable PMX physics records."""

    def test_reads_complete_rigid_body_metadata(self) -> None:
        reader, header, _, _, bone_count = reader_at_rigid_body_section(
            build_pmx_structure(
                encoding_flag=0,
                bones=(build_pmx_bone(encoding_flag=0),),
                rigid_bodies=(
                    build_pmx_rigid_body(
                        local_name="剛体",
                        universal_name="Rigid Body",
                        bone_index=0,
                        collision_group=3,
                        collision_mask=0xFF00,
                        shape=2,
                        size=(1.0, 2.0, 3.0),
                        position=(-1.0, 2.0, -3.0),
                        rotation=(0.1, 0.2, 0.3),
                        mass=4.0,
                        linear_damping=0.1,
                        angular_damping=0.2,
                        restitution=0.3,
                        friction=0.4,
                        physics_mode=2,
                        encoding_flag=0,
                    ),
                ),
            )
        )

        records = read_pmx_rigid_bodies(
            reader,
            header=header,
            bone_count=bone_count,
        )

        body = records[0]
        self.assertEqual(body.local_name, "剛体")
        self.assertEqual(body.bone_index, 0)
        self.assertEqual(body.collision_group, 3)
        self.assertEqual(body.collision_mask, 0xFF00)
        self.assertEqual((body.shape, body.shape_name), (2, "capsule"))
        self.assertEqual(body.size, (1.0, 2.0, 3.0))
        self.assertAlmostEqual(body.position[0], -1.0)
        self.assertAlmostEqual(body.mass, 4.0)
        self.assertEqual(
            (body.physics_mode, body.physics_mode_name),
            (2, "physics_with_bone_alignment"),
        )

    def test_rigid_body_state_preserves_count_after_record_error(self) -> None:
        reader, header, _, _, bone_count = reader_at_rigid_body_section(
            build_pmx_structure(
                rigid_bodies=(build_pmx_rigid_body(shape=3),),
            )
        )
        state = PmxRigidBodyReadState()

        with self.assertRaisesRegex(BinaryParseError, "rigid-body shape 3"):
            read_pmx_rigid_bodies(
                reader,
                header=header,
                bone_count=bone_count,
                state=state,
            )

        self.assertEqual(state.rigid_body_count, 1)
        self.assertEqual(state.rigid_bodies, ())

    def test_reads_joint_metadata_and_all_pmx21_types(self) -> None:
        joints = tuple(
            build_pmx_joint(
                local_name=f"Joint {joint_type}",
                joint_type=joint_type,
                rigid_body_a_index=0,
                rigid_body_b_index=1,
                position=(1.0, 2.0, 3.0),
                translation_spring=(4.0, 5.0, 6.0),
            )
            for joint_type in range(6)
        )
        reader, header, _, _, bone_count = reader_at_rigid_body_section(
            build_pmx_structure(
                version=2.1,
                rigid_bodies=(build_pmx_rigid_body(), build_pmx_rigid_body()),
                joints=joints,
            )
        )
        rigid_bodies = read_pmx_rigid_bodies(
            reader,
            header=header,
            bone_count=bone_count,
        )

        records = read_pmx_joints(
            reader,
            header=header,
            rigid_body_count=len(rigid_bodies),
        )

        self.assertEqual(
            [record.joint_type_name for record in records],
            [
                "spring_6dof",
                "6dof",
                "point_to_point",
                "cone_twist",
                "slider",
                "hinge",
            ],
        )
        self.assertEqual(records[0].position, (1.0, 2.0, 3.0))
        self.assertEqual(records[0].translation_spring, (4.0, 5.0, 6.0))

    def test_joint_state_preserves_count_after_record_error(self) -> None:
        reader, header, _, _, bone_count = reader_at_rigid_body_section(
            build_pmx_structure(
                version=2.1,
                joints=(build_pmx_joint(joint_type=6),),
            )
        )
        rigid_bodies = read_pmx_rigid_bodies(
            reader,
            header=header,
            bone_count=bone_count,
        )
        state = PmxJointReadState()

        with self.assertRaisesRegex(BinaryParseError, "joint type 6"):
            read_pmx_joints(
                reader,
                header=header,
                rigid_body_count=len(rigid_bodies),
                state=state,
            )

        self.assertEqual(state.joint_count, 1)
        self.assertEqual(state.joints, ())

    def test_reads_complete_soft_body_metadata(self) -> None:
        anchor = build_pmx_soft_body_anchor(
            rigid_body_index=0,
            vertex_index=0,
            near_mode=1,
        )
        reader, header, vertex_count, material_count, bone_count = (
            reader_at_rigid_body_section(
                build_pmx_structure(
                    version=2.1,
                    deform_types=(0, 0),
                    rigid_bodies=(build_pmx_rigid_body(),),
                    soft_bodies=(
                        build_pmx_soft_body(
                            local_name="Cape",
                            shape=1,
                            flags=0x07,
                            bending_link_distance=2,
                            cluster_count=4,
                            total_mass=5.0,
                            collision_margin=0.25,
                            aerodynamics_model=3,
                            config=tuple(
                                float(value) / 10.0 for value in range(1, 13)
                            ),
                            cluster_config=(1.1, 1.2, 1.3, 1.4, 1.5, 1.6),
                            iteration_config=(2, 3, 4, 5),
                            material_config=(0.7, 0.8, 0.9),
                            anchors=(anchor,),
                            pinned_vertex_indices=(1,),
                        ),
                    ),
                )
            )
        )
        rigid_bodies = read_pmx_rigid_bodies(
            reader,
            header=header,
            bone_count=bone_count,
        )
        read_pmx_joints(
            reader,
            header=header,
            rigid_body_count=len(rigid_bodies),
        )

        records = read_pmx_soft_bodies(
            reader,
            header=header,
            material_count=material_count,
            rigid_body_count=len(rigid_bodies),
            vertex_count=vertex_count,
        )

        body = records[0]
        self.assertEqual((body.shape, body.shape_name), (1, "rope"))
        self.assertEqual(
            body.flag_names,
            (
                "generate_bending_links",
                "generate_clusters",
                "randomize_constraints",
            ),
        )
        self.assertEqual(body.config.aerodynamics_model_name, "face_two_sided")
        self.assertEqual(body.iteration_config.position, 3)
        self.assertAlmostEqual(body.material_config.volume_stiffness, 0.9)
        self.assertTrue(body.anchors[0].near_mode)
        self.assertEqual(body.pinned_vertex_indices, (1,))

    def test_pmx20_soft_body_reader_consumes_no_bytes(self) -> None:
        reader, header, vertex_count, material_count, bone_count = (
            reader_at_rigid_body_section(build_pmx_structure(version=2.0))
        )
        rigid_bodies = read_pmx_rigid_bodies(
            reader,
            header=header,
            bone_count=bone_count,
        )
        read_pmx_joints(
            reader,
            header=header,
            rigid_body_count=len(rigid_bodies),
        )
        starting_offset = reader.offset

        records = read_pmx_soft_bodies(
            reader,
            header=header,
            material_count=material_count,
            rigid_body_count=len(rigid_bodies),
            vertex_count=vertex_count,
        )

        self.assertEqual(records, ())
        self.assertEqual(reader.offset, starting_offset)

    def test_soft_body_state_preserves_count_after_record_error(self) -> None:
        reader, header, vertex_count, material_count, bone_count = (
            reader_at_rigid_body_section(
                build_pmx_structure(
                    version=2.1,
                    soft_bodies=(build_pmx_soft_body(shape=2),),
                )
            )
        )
        rigid_bodies = read_pmx_rigid_bodies(
            reader,
            header=header,
            bone_count=bone_count,
        )
        read_pmx_joints(
            reader,
            header=header,
            rigid_body_count=len(rigid_bodies),
        )
        state = PmxSoftBodyReadState()

        with self.assertRaisesRegex(BinaryParseError, "soft-body shape 2"):
            read_pmx_soft_bodies(
                reader,
                header=header,
                material_count=material_count,
                rigid_body_count=len(rigid_bodies),
                vertex_count=vertex_count,
                state=state,
            )

        self.assertEqual(state.soft_body_count, 1)
        self.assertEqual(state.soft_bodies, ())

    def test_records_are_immutable_validated_and_legacy_compatible(self) -> None:
        identity_pairs = (
            (PmxRigidBody, LegacyPmxRigidBody),
            (PmxJoint, LegacyPmxJoint),
            (PmxSoftBody, LegacyPmxSoftBody),
            (PmxSoftBodyAnchor, LegacyPmxSoftBodyAnchor),
            (PmxSoftBodyConfig, LegacyPmxSoftBodyConfig),
            (PmxSoftBodyClusterConfig, LegacyPmxSoftBodyClusterConfig),
            (PmxSoftBodyIterationConfig, LegacyPmxSoftBodyIterationConfig),
            (PmxSoftBodyMaterialConfig, LegacyPmxSoftBodyMaterialConfig),
        )
        for typed_record, legacy_record in identity_pairs:
            self.assertIs(typed_record, legacy_record)

        reader, header, _, _, bone_count = reader_at_rigid_body_section(
            build_pmx_structure(rigid_bodies=(build_pmx_rigid_body(),))
        )
        body = read_pmx_rigid_bodies(
            reader,
            header=header,
            bone_count=bone_count,
        )[0]

        with self.assertRaises(FrozenInstanceError):
            body.local_name = "changed"  # type: ignore[misc]

        with self.assertRaisesRegex(ValueError, "exactly 3 values"):
            replace(body, position=(0.0, 0.0))  # type: ignore[arg-type]

        with self.assertRaisesRegex(ValueError, "collision_group"):
            replace(body, collision_group=16)

        self.assertEqual(body.to_dict()["shape_name"], "sphere")


if __name__ == "__main__":
    unittest.main()
