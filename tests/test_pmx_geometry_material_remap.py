from __future__ import annotations

import unittest

import mmd_registry.pmx as pmx_public
import mmd_registry.services as services_public
from mmd_registry.pmx.collection_transform import PmxCollectionTransform
from mmd_registry.pmx.document import PmxMaterial
from mmd_registry.pmx.geometry_material_remap import (
    PmxMaterialSurfacePartitionTransform,
    PmxReferenceRemapError,
    remap_material_texture_references,
    remap_surface_vertex_references,
    transform_material_surface_partition,
)
from mmd_registry.pmx.index_remap import PmxIndexRemap
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


def _material(
    *,
    name: str = "material",
    texture_index: int = -1,
    sphere_texture_index: int = -1,
    toon_reference_mode: str = "texture",
    toon_reference_index: int = -1,
    surface_index_count: int = 3,
) -> PmxMaterial:
    return PmxMaterial(
        local_name=name,
        universal_name=name,
        texture_index=texture_index,
        sphere_texture_index=sphere_texture_index,
        sphere_mode=0,
        toon_reference_mode=toon_reference_mode,
        toon_reference_index=toon_reference_index,
        memo="",
        surface_index_count=surface_index_count,
    )


class SurfaceVertexReferenceRemapTests(unittest.TestCase):
    def test_identity_returns_original_tuple(self) -> None:
        source = (0, 1, 2)
        transform = PmxCollectionTransform.identity(
            PmxReferenceTargetKind.VERTEX,
            3,
        )

        result = remap_surface_vertex_references(source, transform)

        self.assertIs(result, source)

    def test_reorder_remaps_every_surface_reference_deterministically(self) -> None:
        source = (0, 2, 1, 2, 0, 1)
        transform = _transform(
            PmxReferenceTargetKind.VERTEX,
            (2, 0, 1),
            3,
        )

        expected = (2, 1, 0, 1, 2, 0)
        self.assertEqual(
            remap_surface_vertex_references(source, transform),
            expected,
        )
        self.assertEqual(
            remap_surface_vertex_references(source, transform),
            expected,
        )

    def test_repeated_references_remap_consistently(self) -> None:
        transform = _transform(
            PmxReferenceTargetKind.VERTEX,
            (1, 0),
            2,
        )

        self.assertEqual(
            remap_surface_vertex_references((0, 0, 0), transform),
            (1, 1, 1),
        )

    def test_removed_referenced_vertex_blocks(self) -> None:
        transform = _transform(
            PmxReferenceTargetKind.VERTEX,
            (0, None),
            1,
        )

        with self.assertRaisesRegex(
            PmxReferenceRemapError,
            r"surface_indices\[2\] references removed vertex index 1",
        ):
            remap_surface_vertex_references((0, 0, 1), transform)

    def test_boundary_zero_and_last_index_remap(self) -> None:
        transform = _transform(
            PmxReferenceTargetKind.VERTEX,
            (1, 2, 0),
            3,
        )

        self.assertEqual(
            remap_surface_vertex_references((0, 2, 0), transform),
            (1, 0, 1),
        )

    def test_bool_surface_index_is_rejected(self) -> None:
        transform = PmxCollectionTransform.identity(
            PmxReferenceTargetKind.VERTEX,
            2,
        )

        with self.assertRaisesRegex(TypeError, "must be an integer"):
            remap_surface_vertex_references((0, True, 1), transform)

    def test_surface_index_outside_old_domain_is_rejected(self) -> None:
        transform = PmxCollectionTransform.identity(
            PmxReferenceTargetKind.VERTEX,
            2,
        )

        with self.assertRaisesRegex(ValueError, "outside vertex old_size 2"):
            remap_surface_vertex_references((0, 1, 2), transform)

    def test_non_triangle_surface_stream_is_rejected(self) -> None:
        transform = PmxCollectionTransform.identity(
            PmxReferenceTargetKind.VERTEX,
            2,
        )

        with self.assertRaisesRegex(ValueError, "divisible by 3"):
            remap_surface_vertex_references((0, 1), transform)

    def test_vertex_transform_kind_is_required(self) -> None:
        transform = PmxCollectionTransform.identity(
            PmxReferenceTargetKind.TEXTURE,
            3,
        )

        with self.assertRaisesRegex(ValueError, "transform kind must be vertex"):
            remap_surface_vertex_references((0, 1, 2), transform)


class MaterialTextureReferenceRemapTests(unittest.TestCase):
    def test_identity_returns_original_tuple(self) -> None:
        materials = (
            _material(texture_index=0, sphere_texture_index=1, toon_reference_index=2),
        )
        transform = PmxCollectionTransform.identity(
            PmxReferenceTargetKind.TEXTURE,
            3,
        )

        result = remap_material_texture_references(materials, transform)

        self.assertIs(result, materials)

    def test_main_sphere_and_individual_toon_remap(self) -> None:
        materials = (
            _material(texture_index=0, sphere_texture_index=1, toon_reference_index=2),
        )
        transform = _transform(
            PmxReferenceTargetKind.TEXTURE,
            (2, 0, 1),
            3,
        )

        result = remap_material_texture_references(materials, transform)

        self.assertEqual(result[0].texture_index, 2)
        self.assertEqual(result[0].sphere_texture_index, 0)
        self.assertEqual(result[0].toon_reference_index, 1)
        self.assertEqual(materials[0].texture_index, 0)
        self.assertEqual(materials[0].sphere_texture_index, 1)
        self.assertEqual(materials[0].toon_reference_index, 2)

    def test_existing_sentinels_remain_sentinels(self) -> None:
        materials = (
            _material(
                texture_index=-1,
                sphere_texture_index=-1,
                toon_reference_index=-1,
            ),
        )
        transform = _transform(
            PmxReferenceTargetKind.TEXTURE,
            (1, 0),
            2,
        )

        result = remap_material_texture_references(materials, transform)

        self.assertIs(result, materials)

    def test_removed_main_texture_blocks_instead_of_becoming_sentinel(self) -> None:
        materials = (_material(texture_index=1),)
        transform = _transform(
            PmxReferenceTargetKind.TEXTURE,
            (0, None),
            1,
        )

        with self.assertRaisesRegex(
            PmxReferenceRemapError,
            "removed targets are not converted to the -1 sentinel",
        ):
            remap_material_texture_references(materials, transform)

    def test_removed_sphere_texture_blocks(self) -> None:
        materials = (_material(sphere_texture_index=1),)
        transform = _transform(
            PmxReferenceTargetKind.TEXTURE,
            (0, None),
            1,
        )

        with self.assertRaises(PmxReferenceRemapError):
            remap_material_texture_references(materials, transform)

    def test_removed_individual_toon_texture_blocks(self) -> None:
        materials = (_material(toon_reference_index=1),)
        transform = _transform(
            PmxReferenceTargetKind.TEXTURE,
            (0, None),
            1,
        )

        with self.assertRaises(PmxReferenceRemapError):
            remap_material_texture_references(materials, transform)

    def test_shared_toon_slot_is_never_remapped_as_texture(self) -> None:
        materials = (
            _material(
                toon_reference_mode="shared",
                toon_reference_index=1,
            ),
        )
        transform = _transform(
            PmxReferenceTargetKind.TEXTURE,
            (1, 0),
            2,
        )

        result = remap_material_texture_references(materials, transform)

        self.assertIs(result, materials)
        self.assertEqual(result[0].toon_reference_index, 1)

    def test_shared_toon_does_not_require_texture_domain_membership(self) -> None:
        materials = (
            _material(
                toon_reference_mode="shared",
                toon_reference_index=9,
            ),
        )
        transform = PmxCollectionTransform.identity(
            PmxReferenceTargetKind.TEXTURE,
            0,
        )

        result = remap_material_texture_references(materials, transform)

        self.assertIs(result, materials)
        self.assertEqual(result[0].toon_reference_index, 9)

    def test_out_of_domain_real_texture_reference_is_rejected(self) -> None:
        materials = (_material(texture_index=2),)
        transform = PmxCollectionTransform.identity(
            PmxReferenceTargetKind.TEXTURE,
            2,
        )

        with self.assertRaisesRegex(ValueError, "outside texture old_size 2"):
            remap_material_texture_references(materials, transform)

    def test_texture_transform_kind_is_required(self) -> None:
        materials = (_material(),)
        transform = PmxCollectionTransform.identity(
            PmxReferenceTargetKind.MATERIAL,
            1,
        )

        with self.assertRaisesRegex(ValueError, "transform kind must be texture"):
            remap_material_texture_references(materials, transform)


class MaterialSurfacePartitionTransformTests(unittest.TestCase):
    def test_identity_preserves_exact_objects(self) -> None:
        materials = (_material(name="A"), _material(name="B"))
        surfaces = (0, 0, 0, 1, 1, 1)
        proposal = PmxMaterialSurfacePartitionTransform(
            PmxCollectionTransform.identity(
                PmxReferenceTargetKind.MATERIAL,
                2,
            )
        )

        result = transform_material_surface_partition(
            materials,
            surfaces,
            proposal,
        )

        self.assertIs(result.materials, materials)
        self.assertIs(result.surface_indices, surfaces)

    def test_reorder_moves_owned_surface_segments_with_materials(self) -> None:
        materials = (
            _material(name="A", surface_index_count=3),
            _material(name="B", surface_index_count=6),
        )
        surfaces = (0, 0, 0, 1, 1, 1, 2, 2, 2)
        proposal = PmxMaterialSurfacePartitionTransform(
            _transform(
                PmxReferenceTargetKind.MATERIAL,
                (1, 0),
                2,
            )
        )

        result = transform_material_surface_partition(
            materials,
            surfaces,
            proposal,
        )

        self.assertEqual(tuple(material.local_name for material in result.materials), ("B", "A"))
        self.assertEqual(
            result.surface_indices,
            (1, 1, 1, 2, 2, 2, 0, 0, 0),
        )
        self.assertEqual(
            sum(material.surface_index_count for material in result.materials),
            len(result.surface_indices),
        )

    def test_delete_removes_material_and_exact_owned_segment(self) -> None:
        materials = (
            _material(name="A"),
            _material(name="B"),
            _material(name="C"),
        )
        surfaces = (0, 0, 0, 1, 1, 1, 2, 2, 2)
        proposal = PmxMaterialSurfacePartitionTransform(
            _transform(
                PmxReferenceTargetKind.MATERIAL,
                (0, None, 1),
                2,
            )
        )

        result = transform_material_surface_partition(
            materials,
            surfaces,
            proposal,
        )

        self.assertEqual(tuple(material.local_name for material in result.materials), ("A", "C"))
        self.assertEqual(result.surface_indices, (0, 0, 0, 2, 2, 2))
        self.assertEqual(tuple(material.local_name for material in materials), ("A", "B", "C"))
        self.assertEqual(surfaces, (0, 0, 0, 1, 1, 1, 2, 2, 2))

    def test_delete_and_reorder_are_deterministic(self) -> None:
        materials = (
            _material(name="A"),
            _material(name="B"),
            _material(name="C"),
        )
        surfaces = (0, 0, 0, 1, 1, 1, 2, 2, 2)
        proposal = PmxMaterialSurfacePartitionTransform(
            _transform(
                PmxReferenceTargetKind.MATERIAL,
                (1, None, 0),
                2,
            )
        )

        first = transform_material_surface_partition(materials, surfaces, proposal)
        second = transform_material_surface_partition(materials, surfaces, proposal)

        self.assertEqual(first, second)
        self.assertEqual(tuple(material.local_name for material in first.materials), ("C", "A"))
        self.assertEqual(first.surface_indices, (2, 2, 2, 0, 0, 0))

    def test_zero_surface_materials_and_empty_stream_are_supported(self) -> None:
        materials = (
            _material(name="A", surface_index_count=0),
            _material(name="B", surface_index_count=0),
        )
        proposal = PmxMaterialSurfacePartitionTransform(
            _transform(
                PmxReferenceTargetKind.MATERIAL,
                (1, 0),
                2,
            )
        )

        result = transform_material_surface_partition(materials, (), proposal)

        self.assertEqual(tuple(material.local_name for material in result.materials), ("B", "A"))
        self.assertEqual(result.surface_indices, ())

    def test_empty_collections_are_supported(self) -> None:
        proposal = PmxMaterialSurfacePartitionTransform(
            PmxCollectionTransform.identity(
                PmxReferenceTargetKind.MATERIAL,
                0,
            )
        )

        result = transform_material_surface_partition((), (), proposal)

        self.assertEqual(result.materials, ())
        self.assertEqual(result.surface_indices, ())

    def test_material_transform_old_size_must_match_collection(self) -> None:
        proposal = PmxMaterialSurfacePartitionTransform(
            PmxCollectionTransform.identity(
                PmxReferenceTargetKind.MATERIAL,
                2,
            )
        )

        with self.assertRaisesRegex(ValueError, "old_size must match"):
            transform_material_surface_partition(
                (_material(name="A"),),
                (0, 0, 0),
                proposal,
            )

    def test_partition_shortfall_fails_closed(self) -> None:
        materials = (_material(name="A", surface_index_count=3),)
        proposal = PmxMaterialSurfacePartitionTransform(
            PmxCollectionTransform.identity(
                PmxReferenceTargetKind.MATERIAL,
                1,
            )
        )

        with self.assertRaisesRegex(
            ValueError,
            "materials cover 3 surface indices but geometry contains 6",
        ):
            transform_material_surface_partition(
                materials,
                (0, 0, 0, 1, 1, 1),
                proposal,
            )

    def test_partition_overflow_fails_closed(self) -> None:
        materials = (_material(name="A", surface_index_count=6),)
        proposal = PmxMaterialSurfacePartitionTransform(
            PmxCollectionTransform.identity(
                PmxReferenceTargetKind.MATERIAL,
                1,
            )
        )

        with self.assertRaisesRegex(ValueError, "surface segment exceeds"):
            transform_material_surface_partition(
                materials,
                (0, 0, 0),
                proposal,
            )

    def test_bool_surface_index_is_rejected(self) -> None:
        materials = (_material(name="A"),)
        proposal = PmxMaterialSurfacePartitionTransform(
            PmxCollectionTransform.identity(
                PmxReferenceTargetKind.MATERIAL,
                1,
            )
        )

        with self.assertRaisesRegex(TypeError, "must be an integer"):
            transform_material_surface_partition(
                materials,
                (0, True, 0),
                proposal,
            )

    def test_proposal_requires_material_transform(self) -> None:
        with self.assertRaisesRegex(ValueError, "transform kind must be material"):
            PmxMaterialSurfacePartitionTransform(
                PmxCollectionTransform.identity(
                    PmxReferenceTargetKind.TEXTURE,
                    1,
                )
            )


class Cp11BoundaryTests(unittest.TestCase):
    def test_cp11_kernel_is_not_exported_from_public_roots(self) -> None:
        forbidden = (
            "PmxMaterialSurfacePartitionTransform",
            "PmxReferenceRemapError",
            "remap_material_texture_references",
            "remap_surface_vertex_references",
            "transform_material_surface_partition",
        )
        for name in forbidden:
            with self.subTest(name=name):
                self.assertFalse(hasattr(pmx_public, name))
                self.assertFalse(hasattr(services_public, name))


if __name__ == "__main__":
    unittest.main()
