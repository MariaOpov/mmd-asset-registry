"""CP18 public preview/execute semantic-parity gates for v0.9.2 insertion."""

from __future__ import annotations

import hashlib
import io
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import mmd_registry
import mmd_registry.pmx as pmx_public
import mmd_registry.services as services
from mmd_registry.pmx import structural_output as structural_output_module
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.writer import serialize_pmx
from mmd_registry.services.structural_bone import PmxStructuralBoneInsertion
from mmd_registry.services.structural_material import PmxStructuralMaterialInsertion
from mmd_registry.services.structural_morph import (
    PmxStructuralMorphBoneOffset,
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
    PmxStructuralVertexInsertion,
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


class PreviewExecuteSemanticParityTests(unittest.TestCase):
    def _assert_public_parity(self, request) -> None:
        source_document = _clean_document()
        source_bytes = serialize_pmx(source_document)
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()

        first_preview = services.preview_structural_edit(source_document, request)
        second_preview = services.preview_structural_edit(source_document, request)

        self.assertEqual(first_preview.status, "changes_pending")
        self.assertEqual(first_preview.document, second_preview.document)
        self.assertEqual(first_preview.to_dict(), second_preview.to_dict())

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            first_output = root / "first.pmx"
            second_output = root / "second.pmx"
            source.write_bytes(source_bytes)

            first_execution = services.apply_structural_edit(
                source,
                first_output,
                request,
            )
            second_execution = services.apply_structural_edit(
                source,
                second_output,
                request,
            )

            first_bytes = first_output.read_bytes()
            second_bytes = second_output.read_bytes()

            self.assertEqual(first_execution.status, "written")
            self.assertEqual(second_execution.status, "written")

            self.assertEqual(first_preview.document, first_execution.document)
            self.assertEqual(first_preview.document, second_execution.document)
            self.assertEqual(load_pmx(first_output), first_preview.document)
            self.assertEqual(load_pmx(second_output), first_preview.document)

            self.assertEqual(first_bytes, second_bytes)
            self.assertEqual(
                first_execution.output_sha256,
                hashlib.sha256(first_bytes).hexdigest(),
            )
            self.assertEqual(
                second_execution.output_sha256,
                hashlib.sha256(second_bytes).hexdigest(),
            )
            self.assertEqual(
                first_execution.output_sha256,
                second_execution.output_sha256,
            )
            self.assertEqual(first_execution.output_size_bytes, len(first_bytes))
            self.assertEqual(second_execution.output_size_bytes, len(second_bytes))

            self.assertEqual(first_execution.source_sha256, source_sha256)
            self.assertEqual(second_execution.source_sha256, source_sha256)
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_texture_insertion_preview_execute_parity(self) -> None:
        request = services.PmxStructuralEditRequest(
            texture_insertions=(
                PmxStructuralTextureInsertion("textures/cp18-texture.png"),
            ),
        )
        self._assert_public_parity(request)

    def test_material_insertion_preview_execute_parity(self) -> None:
        request = services.PmxStructuralEditRequest(
            material_insertions=(
                PmxStructuralMaterialInsertion(local_name="CP18 material"),
            ),
        )
        self._assert_public_parity(request)

    def test_bone_insertion_preview_execute_parity(self) -> None:
        request = services.PmxStructuralEditRequest(
            bone_insertions=(
                PmxStructuralBoneInsertion(local_name="CP18 bone"),
            ),
        )
        self._assert_public_parity(request)

    def test_vertex_insertion_preview_execute_parity(self) -> None:
        request = services.PmxStructuralEditRequest(
            vertex_insertions=(
                _vertex(PmxStructuralVertexBdef1(0)),
            ),
        )
        self._assert_public_parity(request)

    def test_rigid_body_insertion_preview_execute_parity(self) -> None:
        request = services.PmxStructuralEditRequest(
            rigid_body_insertions=(
                PmxStructuralRigidBodyInsertion(
                    local_name="CP18 rigid body",
                    bone_index=0,
                ),
            ),
        )
        self._assert_public_parity(request)

    def test_morph_insertion_preview_execute_parity(self) -> None:
        request = services.PmxStructuralEditRequest(
            morph_insertions=(
                PmxStructuralMorphInsertion(
                    local_name="CP18 morph",
                    morph_type="vertex",
                    offsets=(
                        PmxStructuralMorphVertexOffset(
                            0,
                            (0.1, 0.0, 0.0),
                        ),
                    ),
                ),
            ),
        )
        self._assert_public_parity(request)

    def test_coordinated_mixed_insertion_preview_execute_parity(self) -> None:
        request = services.PmxStructuralEditRequest(
            texture_insertions=(
                PmxStructuralTextureInsertion("textures/cp18-mixed.png"),
            ),
            material_insertions=(
                PmxStructuralMaterialInsertion(local_name="CP18 mixed material"),
            ),
            bone_insertions=(
                PmxStructuralBoneInsertion(local_name="CP18 mixed bone"),
            ),
            vertex_insertions=(
                _vertex(PmxStructuralVertexBdef1(0)),
            ),
            rigid_body_insertions=(
                PmxStructuralRigidBodyInsertion(
                    local_name="CP18 mixed rigid",
                    bone_index=0,
                ),
            ),
            morph_insertions=(
                PmxStructuralMorphInsertion(
                    local_name="CP18 mixed morph",
                    morph_type="vertex",
                    offsets=(
                        PmxStructuralMorphVertexOffset(
                            0,
                            (0.0, 0.1, 0.0),
                        ),
                    ),
                ),
            ),
        )
        self._assert_public_parity(request)

    def test_coordinated_new_reference_dependency_parity(self) -> None:
        request = services.PmxStructuralEditRequest(
            texture_insertions=(
                PmxStructuralTextureInsertion(
                    "textures/cp18-new-ref.png",
                    new_id="tex",
                ),
            ),
            material_insertions=(
                PmxStructuralMaterialInsertion(
                    local_name="CP18 referenced material",
                    texture_index=PmxStructuralNewReference("texture", "tex"),
                    new_id="material",
                ),
            ),
            bone_insertions=(
                PmxStructuralBoneInsertion(
                    local_name="CP18 referenced bone",
                    new_id="bone",
                ),
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
                    local_name="CP18 referenced rigid",
                    bone_index=PmxStructuralNewReference("bone", "bone"),
                    new_id="rigid",
                ),
            ),
            morph_insertions=(
                PmxStructuralMorphInsertion(
                    local_name="CP18 vertex dependency",
                    morph_type="vertex",
                    offsets=(
                        PmxStructuralMorphVertexOffset(
                            PmxStructuralNewReference("vertex", "vertex"),
                            (0.1, 0.0, 0.0),
                        ),
                    ),
                ),
                PmxStructuralMorphInsertion(
                    local_name="CP18 bone dependency",
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
                    local_name="CP18 material dependency",
                    morph_type="material",
                    offsets=(
                        _material_morph_offset(
                            PmxStructuralNewReference(
                                "material",
                                "material",
                            )
                        ),
                    ),
                ),
                PmxStructuralMorphInsertion(
                    local_name="CP18 rigid dependency",
                    morph_type="impulse",
                    offsets=(
                        PmxStructuralMorphImpulseOffset(
                            PmxStructuralNewReference(
                                "rigid_body",
                                "rigid",
                            ),
                            False,
                            (0.0, 0.0, 0.0),
                            (0.0, 0.0, 0.0),
                        ),
                    ),
                ),
            ),
        )
        self._assert_public_parity(request)

    def test_public_authority_and_capability_freeze_survives_cp18(self) -> None:
        self.assertEqual(mmd_registry.__version__, "0.9.2")
        self.assertIs(
            services.PmxStructuralEditRequest,
            services.PmxStructuralPreviewRequest,
        )
        self.assertTrue(callable(services.preview_structural_edit))
        self.assertTrue(callable(services.apply_structural_edit))
        self.assertFalse(hasattr(services, "PmxStructuralNewReference"))
        self.assertFalse(hasattr(pmx_public, "PmxCoordinatedInsertionPreview"))
        self.assertFalse(
            any(
                "coordinated" in name.lower()
                for name in structural_output_module.__all__
            )
        )
        self.assertIs((services.get_capabilities().to_dict())["structural_insert"], True)


if __name__ == "__main__":
    unittest.main()
