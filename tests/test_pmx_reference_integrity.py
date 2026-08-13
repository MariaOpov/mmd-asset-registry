"""Cross-reference, sentinel, and PMX-version integrity contracts."""

from __future__ import annotations

import io
import unittest
from dataclasses import replace

from mmd_registry.pmx import (
    PmxValidationError,
    load_pmx,
    validate_pmx_document,
)
from tests.mmd_fixtures import build_pmx_structure
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


class PmxReferenceIntegrityTests(unittest.TestCase):
    """Lock the existing whole-document reference and version boundaries."""

    def setUp(self) -> None:
        self.document21 = load_pmx(
            io.BytesIO(build_pmx_roundtrip_fixture(version=2.1))
        )
        self.document20 = load_pmx(
            io.BytesIO(build_pmx_roundtrip_fixture(version=2.0))
        )

    def assert_validation_issue(
        self,
        document,
        *,
        section: str,
        field: str,
        record_index: int | None = None,
        reason_fragment: str | None = None,
    ) -> PmxValidationError:
        with self.assertRaises(PmxValidationError) as context:
            validate_pmx_document(document)

        error = context.exception
        self.assertEqual(error.issue.section, section)
        self.assertEqual(error.issue.field, field)
        self.assertEqual(error.issue.record_index, record_index)
        if reason_fragment is not None:
            self.assertIn(reason_fragment, error.issue.reason)
        return error

    def test_allowed_minus_one_sentinels_validate_across_sections(self) -> None:
        document = self.document21

        first_vertex = document.vertices[0]
        first_vertex = replace(
            first_vertex,
            deform=replace(first_vertex.deform, bone_index=-1),
        )
        geometry = replace(
            document.geometry,
            vertices=(first_vertex, *document.vertices[1:]),
        )

        first_material = replace(
            document.materials[0],
            texture_index=-1,
            sphere_texture_index=-1,
            toon_reference_index=-1,
        )

        second_bone = replace(
            document.bones[1],
            parent_bone_index=-1,
            tail_bone_index=-1,
            inherit_parent_bone_index=-1,
        )

        material_morph = document.morphs[8]
        material_morph = replace(
            material_morph,
            offsets=(
                replace(material_morph.offsets[0], material_index=-1),
            ),
        )

        first_rigid_body = replace(document.rigid_bodies[0], bone_index=-1)
        first_joint = replace(
            document.joints[0],
            rigid_body_a_index=-1,
            rigid_body_b_index=-1,
        )
        soft_body = replace(document.soft_bodies[0], material_index=-1)

        candidate = replace(
            document,
            geometry=geometry,
            materials=(first_material, *document.materials[1:]),
            bones=(document.bones[0], second_bone),
            morphs=(
                *document.morphs[:8],
                material_morph,
                *document.morphs[9:],
            ),
            rigid_bodies=(first_rigid_body, *document.rigid_bodies[1:]),
            joints=(first_joint, *document.joints[1:]),
            soft_bodies=(soft_body,),
        )

        self.assertIsNone(validate_pmx_document(candidate))

    def test_zero_target_count_accepts_only_supported_texture_sentinels(
        self,
    ) -> None:
        first_material = replace(
            self.document21.materials[0],
            texture_index=-1,
            sphere_texture_index=-1,
            toon_reference_index=-1,
        )
        candidate = replace(
            self.document21,
            texture_paths=(),
            materials=(first_material, *self.document21.materials[1:]),
        )

        self.assertIsNone(validate_pmx_document(candidate))

    def test_forbidden_minus_one_sentinels_fail_closed(self) -> None:
        document = self.document21

        cases = []

        second_bone = document.bones[1]
        assert second_bone.ik is not None
        invalid_ik_bone = replace(
            second_bone,
            ik=replace(second_bone.ik, target_bone_index=-1),
        )
        cases.append(
            (
                "ik_target",
                replace(
                    document,
                    bones=(document.bones[0], invalid_ik_bone),
                ),
                "bones",
                "ik.target_bone_index",
                1,
            )
        )

        first_frame = document.display_frames[0]
        first_element = replace(first_frame.elements[0], target_index=-1)
        cases.append(
            (
                "display_bone",
                replace(
                    document,
                    display_frames=(
                        replace(
                            first_frame,
                            elements=(
                                first_element,
                                *first_frame.elements[1:],
                            ),
                        ),
                    ),
                ),
                "display_frames",
                "elements[0].target_index",
                0,
            )
        )

        for morph_index in (0, 1, 2, 9, 10):
            morph = document.morphs[morph_index]
            offset = morph.offsets[0]
            if morph_index in (0, 9):
                invalid_offset = replace(offset, morph_index=-1)
            elif morph_index == 1:
                invalid_offset = replace(offset, vertex_index=-1)
            elif morph_index == 2:
                invalid_offset = replace(offset, bone_index=-1)
            else:
                invalid_offset = replace(offset, rigid_body_index=-1)
            invalid_morph = replace(morph, offsets=(invalid_offset,))
            morphs = list(document.morphs)
            morphs[morph_index] = invalid_morph
            cases.append(
                (
                    f"morph_{morph_index}",
                    replace(document, morphs=tuple(morphs)),
                    "morphs",
                    "offsets[0]",
                    morph_index,
                )
            )

        soft_body = document.soft_bodies[0]
        anchor = soft_body.anchors[0]
        cases.append(
            (
                "soft_anchor_rigid",
                replace(
                    document,
                    soft_bodies=(
                        replace(
                            soft_body,
                            anchors=(
                                replace(anchor, rigid_body_index=-1),
                            ),
                        ),
                    ),
                ),
                "soft_bodies",
                "anchors[0].rigid_body_index",
                0,
            )
        )
        cases.append(
            (
                "soft_anchor_vertex",
                replace(
                    document,
                    soft_bodies=(
                        replace(
                            soft_body,
                            anchors=(
                                replace(anchor, vertex_index=-1),
                            ),
                        ),
                    ),
                ),
                "soft_bodies",
                "anchors[0].vertex_index",
                0,
            )
        )
        cases.append(
            (
                "soft_pin",
                replace(
                    document,
                    soft_bodies=(
                        replace(
                            soft_body,
                            pinned_vertex_indices=(
                                -1,
                                *soft_body.pinned_vertex_indices[1:],
                            ),
                        ),
                    ),
                ),
                "soft_bodies",
                "pinned_vertex_indices[0]",
                0,
            )
        )

        for name, candidate, section, field, record_index in cases:
            with self.subTest(name=name):
                self.assert_validation_issue(
                    candidate,
                    section=section,
                    field=field,
                    record_index=record_index,
                    reason_fragment="index -1 is invalid",
                )

    def test_positive_out_of_range_reference_matrix_fails_closed(self) -> None:
        document = self.document21
        bone_count = len(document.bones)
        texture_count = len(document.texture_paths)
        material_count = len(document.materials)
        rigid_body_count = len(document.rigid_bodies)

        cases = []

        first_vertex = document.vertices[0]
        invalid_vertex = replace(
            first_vertex,
            deform=replace(first_vertex.deform, bone_index=bone_count),
        )
        cases.append(
            (
                "vertex_bone",
                replace(
                    document,
                    geometry=replace(
                        document.geometry,
                        vertices=(invalid_vertex, *document.vertices[1:]),
                    ),
                ),
                "vertices",
                "deform.bone_indices[0]",
                0,
            )
        )

        first_material = replace(
            document.materials[0],
            texture_index=texture_count,
        )
        cases.append(
            (
                "material_texture",
                replace(
                    document,
                    materials=(first_material, *document.materials[1:]),
                ),
                "materials",
                "texture_index",
                0,
            )
        )

        cases.append(
            (
                "bone_parent",
                replace(
                    document,
                    bones=(
                        replace(
                            document.bones[0],
                            parent_bone_index=bone_count,
                        ),
                        *document.bones[1:],
                    ),
                ),
                "bones",
                "parent_bone_index",
                0,
            )
        )

        material_morph = document.morphs[8]
        invalid_material_morph = replace(
            material_morph,
            offsets=(
                replace(
                    material_morph.offsets[0],
                    material_index=material_count,
                ),
            ),
        )
        morphs = list(document.morphs)
        morphs[8] = invalid_material_morph
        cases.append(
            (
                "material_morph",
                replace(document, morphs=tuple(morphs)),
                "morphs",
                "offsets[0]",
                8,
            )
        )

        cases.append(
            (
                "rigid_body_bone",
                replace(
                    document,
                    rigid_bodies=(
                        replace(
                            document.rigid_bodies[0],
                            bone_index=bone_count,
                        ),
                        *document.rigid_bodies[1:],
                    ),
                ),
                "rigid_bodies",
                "bone_index",
                0,
            )
        )

        cases.append(
            (
                "joint_rigid_body",
                replace(
                    document,
                    joints=(
                        replace(
                            document.joints[0],
                            rigid_body_a_index=rigid_body_count,
                        ),
                        *document.joints[1:],
                    ),
                ),
                "joints",
                "rigid_body_a_index",
                0,
            )
        )

        cases.append(
            (
                "soft_material",
                replace(
                    document,
                    soft_bodies=(
                        replace(
                            document.soft_bodies[0],
                            material_index=material_count,
                        ),
                    ),
                ),
                "soft_bodies",
                "material_index",
                0,
            )
        )

        for name, candidate, section, field, record_index in cases:
            with self.subTest(name=name):
                self.assert_validation_issue(
                    candidate,
                    section=section,
                    field=field,
                    record_index=record_index,
                    reason_fragment="is invalid",
                )

    def test_negative_surface_sentinel_is_rejected_by_geometry_model(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            r"surface indices cannot be negative\.",
        ):
            replace(
                self.document21.geometry,
                surface_indices=(-1, *self.document21.surface_indices[1:]),
            )

    def test_zero_count_non_sentinel_reference_reports_no_valid_value(
        self,
    ) -> None:
        base = load_pmx(
            io.BytesIO(
                build_pmx_structure(
                    deform_types=(),
                    surface_indices=(),
                    materials=(),
                    bones=(),
                    display_frames=(),
                )
            )
        )
        source_frame = self.document21.display_frames[0]
        frame = replace(
            source_frame,
            elements=(source_frame.elements[0],),
        )
        candidate = replace(
            base,
            display_frames=(frame,),
        )

        error = self.assert_validation_issue(
            candidate,
            section="display_frames",
            field="elements[0].target_index",
            record_index=0,
            reason_fragment="expected no value",
        )
        self.assertEqual(
            error.issue.to_dict()["record_index"],
            0,
        )

    def test_pmx21_only_constructs_are_rejected_under_pmx20(self) -> None:
        qdef_candidate = replace(
            self.document21,
            header=replace(self.document21.header, version=2.0),
        )
        self.assert_validation_issue(
            qdef_candidate,
            section="vertices",
            field="deform",
            record_index=4,
            reason_fragment="QDEF requires PMX 2.1",
        )

        for morph_index in (9, 10):
            with self.subTest(morph_type=morph_index):
                morph_candidate = replace(
                    self.document20,
                    morphs=(
                        *self.document20.morphs,
                        self.document21.morphs[morph_index],
                    ),
                )
                self.assert_validation_issue(
                    morph_candidate,
                    section="morphs",
                    field="morph_type",
                    record_index=len(self.document20.morphs),
                    reason_fragment="requires PMX 2.1",
                )

        joint_candidate = replace(
            self.document20,
            joints=(self.document21.joints[1],),
        )
        self.assert_validation_issue(
            joint_candidate,
            section="joints",
            field="joint_type",
            record_index=0,
            reason_fragment="requires PMX 2.1",
        )

        soft_body_candidate = replace(
            self.document20,
            soft_bodies=self.document21.soft_bodies,
        )
        self.assert_validation_issue(
            soft_body_candidate,
            section="soft_bodies",
            field="count",
            record_index=None,
            reason_fragment="PMX 2.0 cannot contain a soft-body section",
        )

    def test_additional_uv_morph_requires_declared_layer(self) -> None:
        vertices = tuple(
            replace(vertex, additional_uvs=())
            for vertex in self.document21.vertices
        )
        candidate = replace(
            self.document21,
            header=replace(
                self.document21.header,
                additional_uv_count=0,
            ),
            geometry=replace(
                self.document21.geometry,
                vertices=vertices,
            ),
        )

        self.assert_validation_issue(
            candidate,
            section="morphs",
            field="morph_type",
            record_index=4,
            reason_fragment="requires additional UV layer 1",
        )


if __name__ == "__main__":
    unittest.main()
