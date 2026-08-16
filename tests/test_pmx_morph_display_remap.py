from __future__ import annotations

import unittest

import mmd_registry.pmx as pmx_public
import mmd_registry.services as services_public
from mmd_registry.pmx.collection_transform import PmxCollectionTransform
from mmd_registry.pmx.document import (
    PmxBoneMorphOffset,
    PmxDisplayFrame,
    PmxDisplayFrameElement,
    PmxFlipMorphOffset,
    PmxGroupMorphOffset,
    PmxImpulseMorphOffset,
    PmxMaterialMorphOffset,
    PmxMorph,
    PmxUvMorphOffset,
    PmxVertexMorphOffset,
)
from mmd_registry.pmx.index_remap import PmxIndexRemap
from mmd_registry.pmx.morph_display_remap import (
    PmxMorphDisplayRemapError,
    remap_display_frame_references,
    transform_morph_collection_references,
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


def _identity(kind: PmxReferenceTargetKind, size: int) -> PmxCollectionTransform:
    return PmxCollectionTransform.identity(kind, size)


def _group(index: int) -> PmxGroupMorphOffset:
    return PmxGroupMorphOffset(morph_index=index, weight=0.5)


def _vertex(index: int) -> PmxVertexMorphOffset:
    return PmxVertexMorphOffset(vertex_index=index, translation=(1.0, 2.0, 3.0))


def _bone(index: int) -> PmxBoneMorphOffset:
    return PmxBoneMorphOffset(
        bone_index=index,
        translation=(1.0, 2.0, 3.0),
        rotation=(0.0, 0.0, 0.0, 1.0),
    )


def _uv(index: int) -> PmxUvMorphOffset:
    return PmxUvMorphOffset(vertex_index=index, uv_offset=(0.1, 0.2, 0.3, 0.4))


def _material(index: int) -> PmxMaterialMorphOffset:
    return PmxMaterialMorphOffset(
        material_index=index,
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


def _flip(index: int) -> PmxFlipMorphOffset:
    return PmxFlipMorphOffset(morph_index=index, weight=0.5)


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


def _frame(*elements: PmxDisplayFrameElement) -> PmxDisplayFrame:
    return PmxDisplayFrame(
        local_name="Frame",
        universal_name="Frame",
        special=False,
        elements=tuple(elements),
    )


def _run_morph_transform(
    morphs: tuple[PmxMorph, ...],
    *,
    morph_transform: PmxCollectionTransform | None = None,
    vertex_transform: PmxCollectionTransform | None = None,
    bone_transform: PmxCollectionTransform | None = None,
    material_transform: PmxCollectionTransform | None = None,
    pmx_version: float = 2.1,
    additional_uv_count: int = 4,
) -> tuple[PmxMorph, ...]:
    return transform_morph_collection_references(
        morphs,
        morph_transform or _identity(PmxReferenceTargetKind.MORPH, len(morphs)),
        vertex_transform or _identity(PmxReferenceTargetKind.VERTEX, 4),
        bone_transform or _identity(PmxReferenceTargetKind.BONE, 4),
        material_transform or _identity(PmxReferenceTargetKind.MATERIAL, 4),
        pmx_version=pmx_version,
        additional_uv_count=additional_uv_count,
    )


class MorphCollectionReferenceTransformTests(unittest.TestCase):
    def test_identity_returns_original_tuple(self) -> None:
        morphs = (_morph("A", 1, (_vertex(0),)),)
        self.assertIs(_run_morph_transform(morphs), morphs)

    def test_reorder_moves_morphs_and_remaps_group_reference(self) -> None:
        morphs = (
            _morph("A", 0, (_group(1),)),
            _morph("B", 1, (_vertex(0),)),
        )
        result = _run_morph_transform(
            morphs,
            morph_transform=_transform(PmxReferenceTargetKind.MORPH, (1, 0), 2),
        )
        self.assertEqual(tuple(morph.local_name for morph in result), ("B", "A"))
        self.assertEqual(result[1].offsets[0].morph_index, 0)
        self.assertEqual(morphs[0].offsets[0].morph_index, 1)

    def test_delete_unreferenced_morph_is_allowed(self) -> None:
        morphs = (
            _morph("A", 1, (_vertex(0),)),
            _morph("B", 1, (_vertex(1),)),
        )
        result = _run_morph_transform(
            morphs,
            morph_transform=_transform(PmxReferenceTargetKind.MORPH, (0, None), 1),
        )
        self.assertEqual(tuple(morph.local_name for morph in result), ("A",))

    def test_deleted_source_outgoing_group_reference_is_ignored(self) -> None:
        morphs = (
            _morph("A", 0, (_group(1),)),
            _morph("B", 1, (_vertex(0),)),
        )
        result = _run_morph_transform(
            morphs,
            morph_transform=_transform(PmxReferenceTargetKind.MORPH, (None, 0), 1),
        )
        self.assertEqual(tuple(morph.local_name for morph in result), ("B",))

    def test_surviving_group_reference_to_deleted_morph_blocks(self) -> None:
        morphs = (
            _morph("A", 0, (_group(1),)),
            _morph("B", 1, (_vertex(0),)),
        )
        with self.assertRaisesRegex(PmxMorphDisplayRemapError, "removed morph index 1"):
            _run_morph_transform(
                morphs,
                morph_transform=_transform(PmxReferenceTargetKind.MORPH, (0, None), 1),
            )

    def test_group_reference_is_required_and_rejects_sentinel(self) -> None:
        morphs = (_morph("A", 0, (_group(-1),)),)
        with self.assertRaisesRegex(ValueError, "cannot be negative"):
            _run_morph_transform(morphs)

    def test_vertex_morph_reference_is_remapped(self) -> None:
        morphs = (_morph("A", 1, (_vertex(0),)),)
        result = _run_morph_transform(
            morphs,
            vertex_transform=_transform(PmxReferenceTargetKind.VERTEX, (1, 0), 2),
        )
        self.assertEqual(result[0].offsets[0].vertex_index, 1)

    def test_removed_vertex_morph_target_blocks(self) -> None:
        morphs = (_morph("A", 1, (_vertex(1),)),)
        with self.assertRaises(PmxMorphDisplayRemapError):
            _run_morph_transform(
                morphs,
                vertex_transform=_transform(PmxReferenceTargetKind.VERTEX, (0, None), 1),
            )

    def test_bone_morph_reference_is_remapped(self) -> None:
        morphs = (_morph("A", 2, (_bone(0),)),)
        result = _run_morph_transform(
            morphs,
            bone_transform=_transform(PmxReferenceTargetKind.BONE, (1, 0), 2),
        )
        self.assertEqual(result[0].offsets[0].bone_index, 1)
        self.assertEqual(result[0].offsets[0].translation, (1.0, 2.0, 3.0))

    def test_removed_bone_morph_target_blocks(self) -> None:
        morphs = (_morph("A", 2, (_bone(1),)),)
        with self.assertRaises(PmxMorphDisplayRemapError):
            _run_morph_transform(
                morphs,
                bone_transform=_transform(PmxReferenceTargetKind.BONE, (0, None), 1),
            )

    def test_base_uv_morph_reference_is_remapped(self) -> None:
        morphs = (_morph("A", 3, (_uv(0),)),)
        result = _run_morph_transform(
            morphs,
            vertex_transform=_transform(PmxReferenceTargetKind.VERTEX, (1, 0), 2),
        )
        self.assertEqual(result[0].offsets[0].vertex_index, 1)
        self.assertEqual(result[0].offsets[0].uv_offset, (0.1, 0.2, 0.3, 0.4))

    def test_additional_uv_morph_reference_is_remapped_when_layer_exists(self) -> None:
        morphs = (_morph("A", 7, (_uv(0),)),)
        result = _run_morph_transform(
            morphs,
            vertex_transform=_transform(PmxReferenceTargetKind.VERTEX, (1, 0), 2),
            additional_uv_count=4,
        )
        self.assertEqual(result[0].offsets[0].vertex_index, 1)

    def test_additional_uv_layer_requirement_fails_closed(self) -> None:
        morphs = (_morph("A", 6, (_uv(0),)),)
        with self.assertRaisesRegex(ValueError, "additional UV layer 3"):
            _run_morph_transform(morphs, additional_uv_count=2)

    def test_material_morph_reference_is_remapped(self) -> None:
        morphs = (_morph("A", 8, (_material(0),)),)
        result = _run_morph_transform(
            morphs,
            material_transform=_transform(PmxReferenceTargetKind.MATERIAL, (1, 0), 2),
        )
        self.assertEqual(result[0].offsets[0].material_index, 1)
        self.assertEqual(result[0].offsets[0].operation, "add")

    def test_material_morph_sentinel_is_preserved(self) -> None:
        morphs = (_morph("A", 8, (_material(-1),)),)
        self.assertIs(_run_morph_transform(morphs), morphs)

    def test_removed_material_target_blocks_instead_of_becoming_sentinel(self) -> None:
        morphs = (_morph("A", 8, (_material(1),)),)
        with self.assertRaisesRegex(
            PmxMorphDisplayRemapError,
            "removed targets are not converted to the -1 sentinel",
        ):
            _run_morph_transform(
                morphs,
                material_transform=_transform(
                    PmxReferenceTargetKind.MATERIAL, (0, None), 1
                ),
            )

    def test_flip_morph_reference_is_remapped_in_pmx21(self) -> None:
        morphs = (
            _morph("A", 9, (_flip(1),)),
            _morph("B", 1, (_vertex(0),)),
        )
        result = _run_morph_transform(
            morphs,
            morph_transform=_transform(PmxReferenceTargetKind.MORPH, (1, 0), 2),
            pmx_version=2.1,
        )
        self.assertEqual(result[1].offsets[0].morph_index, 0)

    def test_flip_morph_is_rejected_for_pmx20(self) -> None:
        morphs = (_morph("A", 9, (_flip(0),)),)
        with self.assertRaisesRegex(ValueError, "type 9 requires PMX 2.1"):
            _run_morph_transform(morphs, pmx_version=2.0)

    def test_impulse_morph_payload_is_preserved_without_cp14_rewrite(self) -> None:
        offset = _impulse(7)
        morphs = (_morph("A", 10, (offset,)),)
        result = _run_morph_transform(morphs, pmx_version=2.1)
        self.assertIs(result, morphs)
        self.assertIs(result[0].offsets[0], offset)
        self.assertEqual(result[0].offsets[0].rigid_body_index, 7)

    def test_impulse_morph_is_rejected_for_pmx20(self) -> None:
        morphs = (_morph("A", 10, (_impulse(0),)),)
        with self.assertRaisesRegex(ValueError, "type 10 requires PMX 2.1"):
            _run_morph_transform(morphs, pmx_version=2.0)

    def test_morph_type_offset_mismatch_fails_closed(self) -> None:
        morphs = (_morph("A", 1, (_bone(0),)),)
        with self.assertRaisesRegex(ValueError, "requires PmxVertexMorphOffset"):
            _run_morph_transform(morphs)

    def test_wrong_morph_transform_kind_is_rejected(self) -> None:
        morphs = (_morph("A", 1, (_vertex(0),)),)
        with self.assertRaisesRegex(ValueError, "morph_transform kind must be morph"):
            _run_morph_transform(
                morphs,
                morph_transform=_identity(PmxReferenceTargetKind.BONE, 1),
            )

    def test_wrong_vertex_transform_kind_is_rejected(self) -> None:
        morphs = (_morph("A", 1, (_vertex(0),)),)
        with self.assertRaisesRegex(ValueError, "vertex_transform kind must be vertex"):
            _run_morph_transform(
                morphs,
                vertex_transform=_identity(PmxReferenceTargetKind.BONE, 1),
            )

    def test_wrong_bone_transform_kind_is_rejected(self) -> None:
        morphs = (_morph("A", 2, (_bone(0),)),)
        with self.assertRaisesRegex(ValueError, "bone_transform kind must be bone"):
            _run_morph_transform(
                morphs,
                bone_transform=_identity(PmxReferenceTargetKind.VERTEX, 1),
            )

    def test_wrong_material_transform_kind_is_rejected(self) -> None:
        morphs = (_morph("A", 8, (_material(0),)),)
        with self.assertRaisesRegex(ValueError, "material_transform kind must be material"):
            _run_morph_transform(
                morphs,
                material_transform=_identity(PmxReferenceTargetKind.TEXTURE, 1),
            )

    def test_morph_transform_old_size_must_match_collection(self) -> None:
        morphs = (_morph("A", 1, (_vertex(0),)),)
        with self.assertRaisesRegex(ValueError, "old_size must match"):
            _run_morph_transform(
                morphs,
                morph_transform=_identity(PmxReferenceTargetKind.MORPH, 2),
            )

    def test_invalid_pmx_version_is_rejected(self) -> None:
        morphs = (_morph("A", 1, (_vertex(0),)),)
        with self.assertRaisesRegex(ValueError, "pmx_version must be 2.0 or 2.1"):
            _run_morph_transform(morphs, pmx_version=2.2)

    def test_non_float_pmx_version_is_rejected(self) -> None:
        morphs = (_morph("A", 1, (_vertex(0),)),)
        with self.assertRaisesRegex(TypeError, "pmx_version must be a float"):
            _run_morph_transform(morphs, pmx_version=2)  # type: ignore[arg-type]

    def test_invalid_additional_uv_count_is_rejected(self) -> None:
        morphs = (_morph("A", 1, (_vertex(0),)),)
        with self.assertRaisesRegex(ValueError, "from 0 through 4"):
            _run_morph_transform(morphs, additional_uv_count=5)

    def test_bool_additional_uv_count_is_rejected(self) -> None:
        morphs = (_morph("A", 1, (_vertex(0),)),)
        with self.assertRaisesRegex(TypeError, "must be an integer"):
            _run_morph_transform(morphs, additional_uv_count=True)  # type: ignore[arg-type]

    def test_empty_morph_collection_is_supported(self) -> None:
        self.assertEqual(
            transform_morph_collection_references(
                (),
                _identity(PmxReferenceTargetKind.MORPH, 0),
                _identity(PmxReferenceTargetKind.VERTEX, 0),
                _identity(PmxReferenceTargetKind.BONE, 0),
                _identity(PmxReferenceTargetKind.MATERIAL, 0),
                pmx_version=2.0,
                additional_uv_count=0,
            ),
            (),
        )

    def test_morph_transform_is_deterministic(self) -> None:
        morphs = (
            _morph("A", 0, (_group(1),)),
            _morph("B", 1, (_vertex(0),)),
        )
        transform = _transform(PmxReferenceTargetKind.MORPH, (1, 0), 2)
        first = _run_morph_transform(morphs, morph_transform=transform)
        second = _run_morph_transform(morphs, morph_transform=transform)
        self.assertEqual(first, second)


class DisplayFrameReferenceRemapTests(unittest.TestCase):
    def test_identity_returns_original_tuple(self) -> None:
        frames = (
            _frame(
                PmxDisplayFrameElement(target_type="bone", target_index=0),
                PmxDisplayFrameElement(target_type="morph", target_index=0),
            ),
        )
        result = remap_display_frame_references(
            frames,
            _identity(PmxReferenceTargetKind.BONE, 1),
            _identity(PmxReferenceTargetKind.MORPH, 1),
        )
        self.assertIs(result, frames)

    def test_bone_target_is_remapped(self) -> None:
        frames = (_frame(PmxDisplayFrameElement(target_type="bone", target_index=0)),)
        result = remap_display_frame_references(
            frames,
            _transform(PmxReferenceTargetKind.BONE, (1, 0), 2),
            _identity(PmxReferenceTargetKind.MORPH, 0),
        )
        self.assertEqual(result[0].elements[0].target_index, 1)
        self.assertEqual(result[0].elements[0].target_type, "bone")

    def test_morph_target_is_remapped(self) -> None:
        frames = (_frame(PmxDisplayFrameElement(target_type="morph", target_index=0)),)
        result = remap_display_frame_references(
            frames,
            _identity(PmxReferenceTargetKind.BONE, 0),
            _transform(PmxReferenceTargetKind.MORPH, (1, 0), 2),
        )
        self.assertEqual(result[0].elements[0].target_index, 1)
        self.assertEqual(result[0].elements[0].target_type, "morph")

    def test_mixed_element_order_and_types_are_preserved(self) -> None:
        frames = (
            _frame(
                PmxDisplayFrameElement(target_type="morph", target_index=1),
                PmxDisplayFrameElement(target_type="bone", target_index=0),
            ),
        )
        result = remap_display_frame_references(
            frames,
            _transform(PmxReferenceTargetKind.BONE, (1, 0), 2),
            _transform(PmxReferenceTargetKind.MORPH, (1, 0), 2),
        )
        self.assertEqual(
            tuple((element.target_type, element.target_index) for element in result[0].elements),
            (("morph", 0), ("bone", 1)),
        )

    def test_removed_bone_target_blocks(self) -> None:
        frames = (_frame(PmxDisplayFrameElement(target_type="bone", target_index=1)),)
        with self.assertRaises(PmxMorphDisplayRemapError):
            remap_display_frame_references(
                frames,
                _transform(PmxReferenceTargetKind.BONE, (0, None), 1),
                _identity(PmxReferenceTargetKind.MORPH, 0),
            )

    def test_removed_morph_target_blocks(self) -> None:
        frames = (_frame(PmxDisplayFrameElement(target_type="morph", target_index=1)),)
        with self.assertRaises(PmxMorphDisplayRemapError):
            remap_display_frame_references(
                frames,
                _identity(PmxReferenceTargetKind.BONE, 0),
                _transform(PmxReferenceTargetKind.MORPH, (0, None), 1),
            )

    def test_required_display_frame_reference_rejects_sentinel(self) -> None:
        frames = (_frame(PmxDisplayFrameElement(target_type="bone", target_index=-1)),)
        with self.assertRaisesRegex(ValueError, "cannot be negative"):
            remap_display_frame_references(
                frames,
                _identity(PmxReferenceTargetKind.BONE, 1),
                _identity(PmxReferenceTargetKind.MORPH, 0),
            )

    def test_wrong_bone_transform_kind_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "bone_transform kind must be bone"):
            remap_display_frame_references(
                (),
                _identity(PmxReferenceTargetKind.VERTEX, 0),
                _identity(PmxReferenceTargetKind.MORPH, 0),
            )

    def test_wrong_morph_transform_kind_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "morph_transform kind must be morph"):
            remap_display_frame_references(
                (),
                _identity(PmxReferenceTargetKind.BONE, 0),
                _identity(PmxReferenceTargetKind.VERTEX, 0),
            )

    def test_empty_display_frames_are_supported(self) -> None:
        self.assertEqual(
            remap_display_frame_references(
                (),
                _identity(PmxReferenceTargetKind.BONE, 0),
                _identity(PmxReferenceTargetKind.MORPH, 0),
            ),
            (),
        )

    def test_display_frame_remap_is_deterministic(self) -> None:
        frames = (_frame(PmxDisplayFrameElement(target_type="bone", target_index=0)),)
        transform = _transform(PmxReferenceTargetKind.BONE, (1, 0), 2)
        first = remap_display_frame_references(
            frames, transform, _identity(PmxReferenceTargetKind.MORPH, 0)
        )
        second = remap_display_frame_references(
            frames, transform, _identity(PmxReferenceTargetKind.MORPH, 0)
        )
        self.assertEqual(first, second)


class Cp13BoundaryTests(unittest.TestCase):
    def test_cp13_kernel_is_not_exported_from_public_roots(self) -> None:
        forbidden = (
            "PmxMorphDisplayRemapError",
            "remap_display_frame_references",
            "transform_morph_collection_references",
        )
        for name in forbidden:
            with self.subTest(name=name):
                self.assertFalse(hasattr(pmx_public, name))
                self.assertFalse(hasattr(services_public, name))


if __name__ == "__main__":
    unittest.main()
