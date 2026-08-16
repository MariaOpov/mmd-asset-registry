"""Specification freeze for the v0.9.0 PMX reference taxonomy."""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path
import unittest

from mmd_registry.pmx.document import PmxDocument, PmxIndexSizes


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = PROJECT_ROOT / "docs" / "pmx_reference_taxonomy.md"

TARGET_COLLECTIONS = ('vertex', 'texture', 'material', 'bone', 'morph', 'rigid_body')
ORDERED_NON_TARGET_COLLECTIONS = ('surface_indices', 'display_frames', 'joints', 'soft_bodies')

# id, source_section, source_path, target, requirement, sentinel,
# active_condition, nested_repeated, remap_owner
REFERENCE_SPECS = (
    ('surface.vertex', 'surface_indices', 'surface_indices[*]', 'vertex', 'required', 'none', 'always', 'yes', 'CP11'),
    ('vertex.deform.bdef1.bone', 'vertices', 'vertices[*].deform.bone_index', 'bone', 'optional', '-1', 'deform_type == 0 (BDEF1)', 'no', 'CP12'),
    ('vertex.deform.multi.bone', 'vertices', 'vertices[*].deform.bone_indices[*]', 'bone', 'optional', '-1', 'deform_type in {1,2,3,4}; QDEF type 4 requires PMX 2.1', 'yes', 'CP12'),
    ('material.texture', 'materials', 'materials[*].texture_index', 'texture', 'optional', '-1', 'always', 'no', 'CP11'),
    ('material.sphere_texture', 'materials', 'materials[*].sphere_texture_index', 'texture', 'optional', '-1', 'always', 'no', 'CP11'),
    ('material.toon_texture', 'materials', 'materials[*].toon_reference_index', 'texture', 'optional', '-1', "toon_reference_mode == 'texture'", 'no', 'CP11'),
    ('bone.parent', 'bones', 'bones[*].parent_bone_index', 'bone', 'optional', '-1', 'always', 'no', 'CP12'),
    ('bone.tail', 'bones', 'bones[*].tail_bone_index', 'bone', 'optional', '-1', 'PMX_BONE_FLAG_TAIL_INDEX enabled; otherwise tail_offset is active and this is not an edge', 'no', 'CP12'),
    ('bone.inherit_parent', 'bones', 'bones[*].inherit_parent_bone_index', 'bone', 'optional', '-1', 'inherit-rotation or inherit-translation flag enabled', 'no', 'CP12'),
    ('bone.ik_target', 'bones', 'bones[*].ik.target_bone_index', 'bone', 'required', 'none', 'PMX_BONE_FLAG_IK enabled', 'no', 'CP12'),
    ('bone.ik_link', 'bones', 'bones[*].ik.links[*].bone_index', 'bone', 'required', 'none', 'PMX_BONE_FLAG_IK enabled', 'yes', 'CP12'),
    ('morph.group.morph', 'morphs', 'morphs[*].offsets[*].morph_index', 'morph', 'required', 'none', 'morph_type == 0 (group)', 'yes', 'CP13'),
    ('morph.vertex.vertex', 'morphs', 'morphs[*].offsets[*].vertex_index', 'vertex', 'required', 'none', 'morph_type == 1 (vertex)', 'yes', 'CP13'),
    ('morph.bone.bone', 'morphs', 'morphs[*].offsets[*].bone_index', 'bone', 'required', 'none', 'morph_type == 2 (bone)', 'yes', 'CP13'),
    ('morph.uv.vertex', 'morphs', 'morphs[*].offsets[*].vertex_index', 'vertex', 'required', 'none', 'morph_type in {3,4,5,6,7}; types 4-7 require the corresponding additional-UV layer', 'yes', 'CP13'),
    ('morph.material.material', 'morphs', 'morphs[*].offsets[*].material_index', 'material', 'optional', '-1', 'morph_type == 8 (material)', 'yes', 'CP13'),
    ('morph.flip.morph', 'morphs', 'morphs[*].offsets[*].morph_index', 'morph', 'required', 'none', 'morph_type == 9 (flip), PMX 2.1 only', 'yes', 'CP13'),
    ('morph.impulse.rigid_body', 'morphs', 'morphs[*].offsets[*].rigid_body_index', 'rigid_body', 'required', 'none', 'morph_type == 10 (impulse), PMX 2.1 only', 'yes', 'CP14'),
    ('display_frame.bone', 'display_frames', 'display_frames[*].elements[*].target_index', 'bone', 'required', 'none', "element.target_type == 'bone'", 'yes', 'CP13'),
    ('display_frame.morph', 'display_frames', 'display_frames[*].elements[*].target_index', 'morph', 'required', 'none', "element.target_type == 'morph'", 'yes', 'CP13'),
    ('rigid_body.bone', 'rigid_bodies', 'rigid_bodies[*].bone_index', 'bone', 'optional', '-1', 'always', 'no', 'CP14'),
    ('joint.rigid_body_a', 'joints', 'joints[*].rigid_body_a_index', 'rigid_body', 'optional', '-1', 'always; non-zero joint_type itself requires PMX 2.1', 'no', 'CP14'),
    ('joint.rigid_body_b', 'joints', 'joints[*].rigid_body_b_index', 'rigid_body', 'optional', '-1', 'always; non-zero joint_type itself requires PMX 2.1', 'no', 'CP14'),
    ('soft_body.material', 'soft_bodies', 'soft_bodies[*].material_index', 'material', 'optional', '-1', 'soft-body section, PMX 2.1 only', 'no', 'CP14'),
    ('soft_body.anchor.rigid_body', 'soft_bodies', 'soft_bodies[*].anchors[*].rigid_body_index', 'rigid_body', 'required', 'none', 'soft-body section, PMX 2.1 only', 'yes', 'CP14'),
    ('soft_body.anchor.vertex', 'soft_bodies', 'soft_bodies[*].anchors[*].vertex_index', 'vertex', 'required', 'none', 'soft-body section, PMX 2.1 only', 'yes', 'CP14'),
    ('soft_body.pin.vertex', 'soft_bodies', 'soft_bodies[*].pinned_vertex_indices[*]', 'vertex', 'required', 'none', 'soft-body section, PMX 2.1 only', 'yes', 'CP14'),
)

EXPECTED_SENTINEL_RELATIONSHIPS = ('vertex.deform.bdef1.bone', 'vertex.deform.multi.bone', 'material.texture', 'material.sphere_texture', 'material.toon_texture', 'bone.parent', 'bone.tail', 'bone.inherit_parent', 'morph.material.material', 'rigid_body.bone', 'joint.rigid_body_a', 'joint.rigid_body_b', 'soft_body.material')

EXPECTED_OWNER_RELATIONSHIPS = {'CP11': ('surface.vertex', 'material.texture', 'material.sphere_texture', 'material.toon_texture'), 'CP12': ('vertex.deform.bdef1.bone', 'vertex.deform.multi.bone', 'bone.parent', 'bone.tail', 'bone.inherit_parent', 'bone.ik_target', 'bone.ik_link'), 'CP13': ('morph.group.morph', 'morph.vertex.vertex', 'morph.bone.bone', 'morph.uv.vertex', 'morph.material.material', 'morph.flip.morph', 'display_frame.bone', 'display_frame.morph'), 'CP14': ('morph.impulse.rigid_body', 'rigid_body.bone', 'joint.rigid_body_a', 'joint.rigid_body_b', 'soft_body.material', 'soft_body.anchor.rigid_body', 'soft_body.anchor.vertex', 'soft_body.pin.vertex')}


class PmxReferenceTaxonomySpecTests(unittest.TestCase):
    """Freeze the reviewed CP03 inventory before graph/remap implementation."""

    def test_global_target_collections_match_the_six_pmx_index_widths(self) -> None:
        self.assertEqual(
            tuple(field.name for field in fields(PmxIndexSizes)),
            TARGET_COLLECTIONS,
        )

        document_fields = {field.name for field in fields(PmxDocument)}
        self.assertTrue(
            {
                "geometry",
                "texture_paths",
                "materials",
                "bones",
                "morphs",
                "rigid_bodies",
            }.issubset(document_fields)
        )
        self.assertIn("trailing_data", document_fields)

    def test_relationship_inventory_is_complete_unique_and_typed_by_target(self) -> None:
        ids = tuple(spec[0] for spec in REFERENCE_SPECS)
        self.assertEqual(len(REFERENCE_SPECS), 27)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids, ('surface.vertex', 'vertex.deform.bdef1.bone', 'vertex.deform.multi.bone', 'material.texture', 'material.sphere_texture', 'material.toon_texture', 'bone.parent', 'bone.tail', 'bone.inherit_parent', 'bone.ik_target', 'bone.ik_link', 'morph.group.morph', 'morph.vertex.vertex', 'morph.bone.bone', 'morph.uv.vertex', 'morph.material.material', 'morph.flip.morph', 'morph.impulse.rigid_body', 'display_frame.bone', 'display_frame.morph', 'rigid_body.bone', 'joint.rigid_body_a', 'joint.rigid_body_b', 'soft_body.material', 'soft_body.anchor.rigid_body', 'soft_body.anchor.vertex', 'soft_body.pin.vertex'))

        for spec in REFERENCE_SPECS:
            (
                relationship_id,
                source_section,
                source_path,
                target,
                requirement,
                sentinel,
                condition,
                repeated,
                owner,
            ) = spec
            with self.subTest(relationship=relationship_id):
                self.assertTrue(relationship_id)
                self.assertTrue(source_section)
                self.assertIn("[*]", source_path)
                self.assertIn(target, TARGET_COLLECTIONS)
                self.assertIn(requirement, ("required", "optional"))
                self.assertIn(sentinel, ("none", "-1"))
                self.assertTrue(condition)
                self.assertIn(repeated, ("yes", "no"))
                self.assertIn(owner, ("CP11", "CP12", "CP13", "CP14"))

    def test_allowed_sentinel_relationships_are_explicit_and_closed(self) -> None:
        sentinel_ids = tuple(
            spec[0] for spec in REFERENCE_SPECS if spec[5] == "-1"
        )
        self.assertEqual(sentinel_ids, EXPECTED_SENTINEL_RELATIONSHIPS)

        for spec in REFERENCE_SPECS:
            relationship_id, _, _, _, requirement, sentinel, *_ = spec
            with self.subTest(relationship=relationship_id):
                self.assertEqual(requirement == "optional", sentinel == "-1")

    def test_remap_checkpoint_ownership_is_exact_and_non_overlapping(self) -> None:
        actual: dict[str, list[str]] = {}
        for spec in REFERENCE_SPECS:
            actual.setdefault(spec[8], []).append(spec[0])

        self.assertEqual(
            {owner: tuple(ids) for owner, ids in actual.items()},
            EXPECTED_OWNER_RELATIONSHIPS,
        )

        owned_ids = [
            relationship_id
            for ids in EXPECTED_OWNER_RELATIONSHIPS.values()
            for relationship_id in ids
        ]
        self.assertEqual(len(owned_ids), len(set(owned_ids)))
        self.assertEqual(set(owned_ids), {spec[0] for spec in REFERENCE_SPECS})

    def test_dynamic_target_and_variant_relationships_are_separate(self) -> None:
        by_id = {spec[0]: spec for spec in REFERENCE_SPECS}

        self.assertEqual(by_id["material.toon_texture"][3], "texture")
        self.assertIn(
            "toon_reference_mode == 'texture'",
            by_id["material.toon_texture"][6],
        )

        self.assertEqual(
            by_id["display_frame.bone"][2],
            by_id["display_frame.morph"][2],
        )
        self.assertEqual(by_id["display_frame.bone"][3], "bone")
        self.assertEqual(by_id["display_frame.morph"][3], "morph")

        self.assertIn("QDEF", by_id["vertex.deform.multi.bone"][6])
        self.assertIn("PMX 2.1", by_id["morph.flip.morph"][6])
        self.assertIn("PMX 2.1", by_id["morph.impulse.rigid_body"][6])

    def test_ordered_non_target_collections_do_not_appear_as_edge_targets(self) -> None:
        targets = {spec[3] for spec in REFERENCE_SPECS}
        self.assertTrue(targets.issubset(set(TARGET_COLLECTIONS)))
        self.assertTrue(targets.isdisjoint(ORDERED_NON_TARGET_COLLECTIONS))

    def test_markdown_spec_contains_every_relationship_and_safety_policy(self) -> None:
        source = SPEC_PATH.read_text(encoding="utf-8")

        for relationship_id in ('surface.vertex', 'vertex.deform.bdef1.bone', 'vertex.deform.multi.bone', 'material.texture', 'material.sphere_texture', 'material.toon_texture', 'bone.parent', 'bone.tail', 'bone.inherit_parent', 'bone.ik_target', 'bone.ik_link', 'morph.group.morph', 'morph.vertex.vertex', 'morph.bone.bone', 'morph.uv.vertex', 'morph.material.material', 'morph.flip.morph', 'morph.impulse.rigid_body', 'display_frame.bone', 'display_frame.morph', 'rigid_body.bone', 'joint.rigid_body_a', 'joint.rigid_body_b', 'soft_body.material', 'soft_body.anchor.rigid_body', 'soft_body.anchor.vertex', 'soft_body.pin.vertex'):
            with self.subTest(relationship=relationship_id):
                self.assertIn(f"`{relationship_id}`", source)

        required_policy_phrases = (
            "sentinel/no-edge state",
            "not a synonym for \"target removed by remap\"",
            "shared toon slot `0..9`",
            "surface_index_count",
            "must **fail closed**",
            "must **not** call `validate_pmx_document()` as an unconditional precondition",
            "must not silently resize those widths",
            "graph is not assumed to be a DAG",
            "A relationship has exactly one remap owner",
        )
        for phrase in required_policy_phrases:
            with self.subTest(policy=phrase):
                self.assertIn(phrase, source)

    def test_spec_does_not_authorize_structural_public_write_surface(self) -> None:
        source = SPEC_PATH.read_text(encoding="utf-8").lower()

        self.assertIn("does **not** add a public mutation api", source)
        self.assertIn(
            "no graph extraction or remap implementation may start",
            source,
        )
        for forbidden_claim in (
            "bone editor is complete",
            "morph editor is complete",
            "physics editor is complete",
        ):
            with self.subTest(claim=forbidden_claim):
                self.assertNotIn(forbidden_claim, source)


if __name__ == "__main__":
    unittest.main()
