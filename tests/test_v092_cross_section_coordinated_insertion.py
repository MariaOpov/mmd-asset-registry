"""CP17 cross-section coordinated insertion contract tests."""

from __future__ import annotations

import io
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import mmd_registry.pmx as pmx_public
import mmd_registry.services as services
from mmd_registry.diagnostics import PmxServiceError
from mmd_registry.pmx.document import (
    PmxBoneMorphOffset,
    PmxImpulseMorphOffset,
    PmxMaterialMorphOffset,
    PmxVertexMorphOffset,
)
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.writer import serialize_pmx
from mmd_registry.services.structural_bone import PmxStructuralBoneInsertion
from mmd_registry.services.structural_material import PmxStructuralMaterialInsertion
from mmd_registry.services.structural_morph import (
    PmxStructuralMorphBoneOffset,
    PmxStructuralMorphGroupOffset,
    PmxStructuralMorphImpulseOffset,
    PmxStructuralMorphInsertion,
    PmxStructuralMorphMaterialOffset,
    PmxStructuralMorphVertexOffset,
)
from mmd_registry.services.structural_reference import PmxStructuralNewReference
from mmd_registry.services.structural_rigid_body import PmxStructuralRigidBodyInsertion
from mmd_registry.services.structural_texture import PmxStructuralTextureInsertion
from mmd_registry.services.structural_vertex import (
    PmxStructuralVertexBdef1,
    PmxStructuralVertexBdef2,
    PmxStructuralVertexBdef4,
    PmxStructuralVertexInsertion,
    PmxStructuralVertexQdef,
    PmxStructuralVertexSdef,
)
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


def _clean_document():
    return replace(
        load_pmx(
            io.BytesIO(
                build_pmx_roundtrip_fixture(
                    version=2.1,
                    index_size=1,
                )
            )
        ),
        trailing_data=b"",
    )


def _vertex(deform, *, new_id=None):
    return PmxStructuralVertexInsertion(
        vertex_position=(1.0, 2.0, 3.0),
        normal=(0.0, 1.0, 0.0),
        uv=(0.25, 0.75),
        additional_uvs=(
            (0.1, 0.2, 0.3, 0.4),
            (1.1, 1.2, 1.3, 1.4),
            (2.1, 2.2, 2.3, 2.4),
            (3.1, 3.2, 3.3, 3.4),
        ),
        deform=deform,
        edge_scale=1.0,
        new_id=new_id,
    )


def _material_morph_offset(material_reference):
    return PmxStructuralMorphMaterialOffset(
        material_index=material_reference,
        operation="add",
        diffuse=(0.0, 0.0, 0.0, 0.0),
        specular=(0.0, 0.0, 0.0),
        specular_strength=0.0,
        ambient=(0.0, 0.0, 0.0),
        edge_color=(0.0, 0.0, 0.0, 0.0),
        edge_scale=0.0,
        texture_tint=(0.0, 0.0, 0.0, 0.0),
        sphere_tint=(0.0, 0.0, 0.0, 0.0),
        toon_tint=(0.0, 0.0, 0.0, 0.0),
    )


class CoordinatedReferenceDtoTests(unittest.TestCase):
    def test_new_reference_is_immutable_bounded_and_not_root_exported(self) -> None:
        reference = PmxStructuralNewReference("bone", "arm.L")
        self.assertEqual(reference.target_kind, "bone")
        self.assertEqual(reference.new_id, "arm.L")
        self.assertFalse(hasattr(services, "PmxStructuralNewReference"))
        self.assertFalse(hasattr(pmx_public, "PmxStructuralNewReference"))
        with self.assertRaises(ValueError):
            PmxStructuralNewReference("bone", "1bad")
        with self.assertRaises(ValueError):
            PmxStructuralNewReference("unknown", "good")
        with self.assertRaises(TypeError):
            PmxStructuralNewReference("bone", None)  # type: ignore[arg-type]

    def test_wrong_target_kind_is_rejected_by_target_scoped_dto(self) -> None:
        with self.assertRaises(ValueError):
            PmxStructuralVertexBdef1(
                PmxStructuralNewReference("texture", "tex")
            )
        with self.assertRaises(ValueError):
            PmxStructuralRigidBodyInsertion(
                local_name="R",
                bone_index=PmxStructuralNewReference("material", "M"),
            )

    def test_duplicate_request_local_identity_is_rejected_globally(self) -> None:
        with self.assertRaisesRegex(ValueError, "globally unique"):
            services.PmxStructuralPreviewRequest(
                bone_insertions=(
                    PmxStructuralBoneInsertion(local_name="B", new_id="same"),
                ),
                vertex_insertions=(
                    _vertex(PmxStructuralVertexBdef1(0), new_id="same"),
                ),
            )

    def test_same_target_new_references_remain_out_of_scope(self) -> None:
        with self.assertRaises(TypeError):
            PmxStructuralBoneInsertion(
                local_name="B",
                parent_bone_index=PmxStructuralNewReference("bone", "parent"),  # type: ignore[arg-type]
            )
        with self.assertRaises(TypeError):
            PmxStructuralMorphGroupOffset(
                PmxStructuralNewReference("morph", "other"),  # type: ignore[arg-type]
                1.0,
            )


class CoordinatedPreviewTests(unittest.TestCase):
    def test_material_can_reference_new_texture(self) -> None:
        source = _clean_document()
        request = services.PmxStructuralPreviewRequest(
            texture_insertions=(
                PmxStructuralTextureInsertion(
                    "textures/cp17.png",
                    position="insert_before",
                    source_index=0,
                    new_id="tex",
                ),
            ),
            material_insertions=(
                PmxStructuralMaterialInsertion(
                    local_name="CP17 material",
                    texture_index=PmxStructuralNewReference("texture", "tex"),
                    new_id="mat",
                ),
            ),
        )

        result = services.preview_structural_edit(source, request)
        self.assertEqual(result.document.materials[-1].texture_index, 0)
        self.assertEqual(len(result.document.texture_paths), len(source.texture_paths) + 1)
        self.assertEqual(len(result.document.materials), len(source.materials) + 1)

    def test_vertex_source_and_new_bone_domains_do_not_collide(self) -> None:
        source = _clean_document()
        request = services.PmxStructuralPreviewRequest(
            bone_insertions=(
                PmxStructuralBoneInsertion(
                    local_name="New bone",
                    position="insert_before",
                    source_index=0,
                    new_id="new_bone",
                ),
            ),
            vertex_insertions=(
                _vertex(
                    PmxStructuralVertexBdef2(
                        (
                            0,
                            PmxStructuralNewReference("bone", "new_bone"),
                        ),
                        0.5,
                    )
                ),
            ),
        )

        result = services.preview_structural_edit(source, request)
        deform = result.document.vertices[-1].deform
        self.assertEqual(deform.bone_indices, (1, 0))

    def test_remaining_vertex_deform_modes_can_reference_new_bone(self) -> None:
        source = _clean_document()
        new_bone_index = len(source.bones)
        reference = PmxStructuralNewReference("bone", "bone")
        cases = (
            PmxStructuralVertexBdef4(
                (reference, reference, reference, reference),
                (0.25, 0.25, 0.25, 0.25),
            ),
            PmxStructuralVertexSdef(
                (reference, reference),
                0.5,
                (0.0, 0.0, 0.0),
                (0.0, 0.0, 0.0),
                (0.0, 0.0, 0.0),
            ),
            PmxStructuralVertexQdef(
                (reference, reference, reference, reference),
                (0.25, 0.25, 0.25, 0.25),
            ),
        )

        for deform in cases:
            with self.subTest(deform_type=type(deform).__name__):
                request = services.PmxStructuralPreviewRequest(
                    bone_insertions=(
                        PmxStructuralBoneInsertion(local_name="B", new_id="bone"),
                    ),
                    vertex_insertions=(_vertex(deform),),
                )
                result = services.preview_structural_edit(source, request)
                self.assertEqual(
                    result.document.vertices[-1].deform.bone_indices,
                    tuple(new_bone_index for _ in deform.bone_indices),
                )

    def test_rigid_body_can_reference_new_bone(self) -> None:
        source = _clean_document()
        new_bone_index = len(source.bones)
        request = services.PmxStructuralPreviewRequest(
            bone_insertions=(
                PmxStructuralBoneInsertion(local_name="B", new_id="bone"),
            ),
            rigid_body_insertions=(
                PmxStructuralRigidBodyInsertion(
                    local_name="R",
                    bone_index=PmxStructuralNewReference("bone", "bone"),
                    new_id="rigid",
                ),
            ),
        )
        result = services.preview_structural_edit(source, request)
        self.assertEqual(result.document.rigid_bodies[-1].bone_index, new_bone_index)

    def test_morphs_can_reference_new_vertex_bone_material_and_rigid_body(self) -> None:
        source = _clean_document()
        new_vertex = len(source.vertices)
        new_bone = len(source.bones)
        new_material = len(source.materials)
        new_rigid = len(source.rigid_bodies)

        request = services.PmxStructuralPreviewRequest(
            bone_insertions=(
                PmxStructuralBoneInsertion(local_name="B", new_id="bone"),
            ),
            material_insertions=(
                PmxStructuralMaterialInsertion(local_name="M", new_id="material"),
            ),
            vertex_insertions=(
                _vertex(
                    PmxStructuralVertexBdef1(
                        PmxStructuralNewReference("bone", "bone")
                    ),
                    new_id="vertex",
                ),
            ),
            rigid_body_insertions=(
                PmxStructuralRigidBodyInsertion(
                    local_name="R",
                    bone_index=PmxStructuralNewReference("bone", "bone"),
                    new_id="rigid",
                ),
            ),
            morph_insertions=(
                PmxStructuralMorphInsertion(
                    local_name="MV",
                    morph_type="vertex",
                    offsets=(
                        PmxStructuralMorphVertexOffset(
                            PmxStructuralNewReference("vertex", "vertex"),
                            (0.1, 0.0, 0.0),
                        ),
                    ),
                ),
                PmxStructuralMorphInsertion(
                    local_name="MB",
                    morph_type="bone",
                    offsets=(
                        PmxStructuralMorphBoneOffset(
                            PmxStructuralNewReference("bone", "bone"),
                            (0.0, 0.1, 0.0),
                            (0.0, 0.0, 0.0, 1.0),
                        ),
                    ),
                ),
                PmxStructuralMorphInsertion(
                    local_name="MM",
                    morph_type="material",
                    offsets=(
                        _material_morph_offset(
                            PmxStructuralNewReference("material", "material")
                        ),
                    ),
                ),
                PmxStructuralMorphInsertion(
                    local_name="MR",
                    morph_type="impulse",
                    offsets=(
                        PmxStructuralMorphImpulseOffset(
                            PmxStructuralNewReference("rigid_body", "rigid"),
                            False,
                            (0.0, 0.0, 0.0),
                            (0.0, 0.0, 0.0),
                        ),
                    ),
                ),
            ),
        )

        result = services.preview_structural_edit(source, request)
        inserted = result.document.morphs[-4:]
        self.assertIsInstance(inserted[0].offsets[0], PmxVertexMorphOffset)
        self.assertEqual(inserted[0].offsets[0].vertex_index, new_vertex)
        self.assertIsInstance(inserted[1].offsets[0], PmxBoneMorphOffset)
        self.assertEqual(inserted[1].offsets[0].bone_index, new_bone)
        self.assertIsInstance(inserted[2].offsets[0], PmxMaterialMorphOffset)
        self.assertEqual(inserted[2].offsets[0].material_index, new_material)
        self.assertIsInstance(inserted[3].offsets[0], PmxImpulseMorphOffset)
        self.assertEqual(inserted[3].offsets[0].rigid_body_index, new_rigid)

    def test_unknown_new_reference_fails_closed(self) -> None:
        source = _clean_document()
        request = services.PmxStructuralPreviewRequest(
            bone_insertions=(
                PmxStructuralBoneInsertion(local_name="B", new_id="known"),
            ),
            vertex_insertions=(
                _vertex(
                    PmxStructuralVertexBdef1(
                        PmxStructuralNewReference("bone", "missing")
                    )
                ),
            ),
        )
        with self.assertRaises(PmxServiceError):
            services.preview_structural_edit(source, request)

    def test_preview_is_deterministic_and_capability_is_not_promoted(self) -> None:
        source = _clean_document()
        request = services.PmxStructuralPreviewRequest(
            bone_insertions=(
                PmxStructuralBoneInsertion(local_name="B", new_id="bone"),
            ),
            vertex_insertions=(
                _vertex(
                    PmxStructuralVertexBdef1(
                        PmxStructuralNewReference("bone", "bone")
                    )
                ),
            ),
        )
        first = services.preview_structural_edit(source, request)
        second = services.preview_structural_edit(source, request)
        self.assertEqual(first.document, second.document)
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertIs((services.get_capabilities().to_dict())["structural_insert"], True)
        self.assertIs(
            services.PmxStructuralEditRequest,
            services.PmxStructuralPreviewRequest,
        )

    def test_cross_section_capacity_failure_is_inherited_from_frozen_planner(self) -> None:
        source = _clean_document()
        source = replace(source, bones=(source.bones[0],) * 128)
        request = services.PmxStructuralPreviewRequest(
            bone_insertions=(
                PmxStructuralBoneInsertion(local_name="overflow", new_id="bone"),
            ),
            vertex_insertions=(
                _vertex(PmxStructuralVertexBdef1(0)),
            ),
        )
        with self.assertRaises(PmxServiceError):
            services.preview_structural_edit(source, request)


class CoordinatedExecutionTests(unittest.TestCase):
    def test_execution_reuses_preview_semantics_and_preserves_source_bytes(self) -> None:
        source_document = _clean_document()
        request = services.PmxStructuralPreviewRequest(
            bone_insertions=(
                PmxStructuralBoneInsertion(
                    local_name="B",
                    position="insert_before",
                    source_index=0,
                    new_id="bone",
                ),
            ),
            vertex_insertions=(
                _vertex(
                    PmxStructuralVertexBdef1(
                        PmxStructuralNewReference("bone", "bone")
                    )
                ),
            ),
        )
        expected = services.preview_structural_edit(source_document, request)

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.pmx"
            output = Path(tmp) / "output.pmx"
            source_bytes = serialize_pmx(source_document)
            source.write_bytes(source_bytes)

            result = services.apply_structural_edit(source, output, request)

            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertTrue(output.is_file())
            self.assertEqual(result.document, expected.document)
            self.assertEqual(load_pmx(output), expected.document)

    def test_resolution_failure_does_not_publish_output(self) -> None:
        source_document = _clean_document()
        request = services.PmxStructuralPreviewRequest(
            bone_insertions=(
                PmxStructuralBoneInsertion(local_name="B", new_id="known"),
            ),
            vertex_insertions=(
                _vertex(
                    PmxStructuralVertexBdef1(
                        PmxStructuralNewReference("bone", "missing")
                    )
                ),
            ),
        )

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.pmx"
            output = Path(tmp) / "output.pmx"
            source_bytes = serialize_pmx(source_document)
            source.write_bytes(source_bytes)

            with self.assertRaises(PmxServiceError):
                services.apply_structural_edit(source, output, request)

            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertFalse(output.exists())
            self.assertEqual(
                {path.name for path in Path(tmp).iterdir()},
                {"source.pmx"},
            )


if __name__ == "__main__":
    unittest.main()
