"""Freeze internal v0.9.3 final-state structural reference resolution."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, is_dataclass
import importlib
import unittest

import mmd_registry
import mmd_registry.pmx as pmx
import mmd_registry.services as services
from mmd_registry.pmx.index_remap import PmxIndexRemap
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.services.structural_bone import PmxStructuralBoneInsertion
from mmd_registry.services.structural_material import (
    PmxStructuralMaterialInsertion,
)
from mmd_registry.services.structural_morph import (
    PmxStructuralMorphBoneOffset,
    PmxStructuralMorphFlipOffset,
    PmxStructuralMorphGroupOffset,
    PmxStructuralMorphImpulseOffset,
    PmxStructuralMorphInsertion,
    PmxStructuralMorphMaterialOffset,
    PmxStructuralMorphUvOffset,
    PmxStructuralMorphVertexOffset,
)
from mmd_registry.services.structural_reference import PmxStructuralNewReference
from mmd_registry.services.structural_rigid_body import (
    PmxStructuralRigidBodyInsertion,
)
from mmd_registry.services.structural_vertex import (
    PmxStructuralVertexBdef1,
    PmxStructuralVertexBdef4,
    PmxStructuralVertexInsertion,
)


REFERENCE_MODULE_NAME = "mmd_registry.pmx.structural_transaction_reference"


def _reference_module():
    return importlib.import_module(REFERENCE_MODULE_NAME)


def _source_counts(
    **overrides: int,
) -> tuple[tuple[PmxReferenceTargetKind, int], ...]:
    return tuple(
        (kind, overrides.get(kind.value, 0))
        for kind in PmxReferenceTargetKind
    )


def _target_remap(kind: PmxReferenceTargetKind, remap: PmxIndexRemap):
    return _reference_module().PmxStructuralTransactionTargetRemap(kind, remap)


def _identity(
    kind: PmxReferenceTargetKind,
    new_id: str,
    operation_index: int,
    final_index: int,
):
    return _reference_module().PmxStructuralTransactionIdentityBinding(
        kind,
        new_id,
        operation_index,
        final_index,
    )


def _resolver(*, source_counts=None, target_remaps=(), identities=()):
    return _reference_module().PmxStructuralTransactionReferenceResolver(
        _source_counts() if source_counts is None else source_counts,
        target_remaps,
        identities,
    )


def _resolve_dto_reference(resolver, value, kind, field_name: str) -> int:
    if isinstance(value, PmxStructuralNewReference):
        if value.target_kind != kind.value:
            raise ValueError(f"{field_name} new reference must target {kind.value}.")
        return resolver.resolve_new_reference(
            kind,
            value.new_id,
            field_name=field_name,
        )
    return resolver.resolve_source_reference(
        kind,
        value,
        allow_sentinel=False,
        field_name=field_name,
    )


def _new_only_remap(size: int = 1) -> PmxIndexRemap:
    return PmxIndexRemap(
        targets=(),
        new_size=size,
        new_indices_without_old_source=tuple(range(size)),
    )


def _vertex_insertion(deform):
    return PmxStructuralVertexInsertion(
        vertex_position=(0.0, 0.0, 0.0),
        normal=(0.0, 1.0, 0.0),
        uv=(0.0, 0.0),
        additional_uvs=(),
        deform=deform,
        edge_scale=1.0,
    )


def _material_morph_offset(reference):
    return PmxStructuralMorphMaterialOffset(
        material_index=reference,
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


class V093StructuralTransactionReferenceResolutionTests(unittest.TestCase):
    """Keep CP08 internal, immutable and bound to one final-state map."""

    def test_internal_model_is_frozen_slotted_and_not_root_exported(self) -> None:
        reference = _reference_module()
        expected_exports = (
            "PmxStructuralTransactionIdentityBinding",
            "PmxStructuralTransactionReferenceResolver",
            "PmxStructuralTransactionTargetRemap",
        )
        self.assertEqual(reference.__all__, expected_exports)
        for name in expected_exports:
            self.assertTrue(is_dataclass(getattr(reference, name)), name)
            self.assertFalse(hasattr(mmd_registry, name))
            self.assertFalse(hasattr(pmx, name))
            self.assertFalse(hasattr(services, name))

        identity = _identity(PmxReferenceTargetKind.TEXTURE, "texture", 0, 0)
        self.assertFalse(hasattr(identity, "__dict__"))
        self.assertEqual(
            tuple(field.name for field in fields(identity)),
            ("target_kind", "new_id", "operation_index", "final_index"),
        )
        with self.assertRaises(FrozenInstanceError):
            identity.final_index = 1

        for forbidden in (
            "preview_structural_transaction",
            "apply_structural_transaction",
            "execute_structural_transaction",
        ):
            self.assertFalse(hasattr(reference, forbidden), forbidden)

    def test_existing_sentinel_and_final_index_forms_resolve_fail_closed(
        self,
    ) -> None:
        resolver = _resolver(
            source_counts=_source_counts(texture=2, material=3, bone=2),
            target_remaps=(
                _target_remap(
                    PmxReferenceTargetKind.TEXTURE,
                    PmxIndexRemap(
                        targets=(0, 2),
                        new_size=3,
                        new_indices_without_old_source=(1,),
                    ),
                ),
                _target_remap(
                    PmxReferenceTargetKind.MATERIAL,
                    PmxIndexRemap(
                        targets=(2, None, 0),
                        new_size=3,
                        new_indices_without_old_source=(1,),
                    ),
                ),
            ),
        )
        successful = (
            (2, PmxReferenceTargetKind.MATERIAL, False, "material_index", 0),
            (0, PmxReferenceTargetKind.MATERIAL, False, "material_index", 2),
            (1, PmxReferenceTargetKind.BONE, False, "bone_index", 1),
            (-1, PmxReferenceTargetKind.BONE, True, "bone_index", -1),
        )
        for value, kind, sentinel, field_name, expected in successful:
            with self.subTest(value=value, kind=kind.value):
                self.assertEqual(
                    resolver.resolve_source_reference(
                        kind,
                        value,
                        allow_sentinel=sentinel,
                        field_name=field_name,
                    ),
                    expected,
                )

        failures = (
            (
                1,
                PmxReferenceTargetKind.MATERIAL,
                False,
                "material_index",
                ValueError,
                r"removed captured-source material\[1\]",
            ),
            (
                2,
                PmxReferenceTargetKind.TEXTURE,
                False,
                "texture_index",
                ValueError,
                r"captured source texture domain",
            ),
            (
                -1,
                PmxReferenceTargetKind.BONE,
                False,
                "bone_index",
                ValueError,
                r"-1 sentinel",
            ),
            (
                -2,
                PmxReferenceTargetKind.BONE,
                False,
                "bone_index",
                ValueError,
                r"captured source bone domain",
            ),
            (
                True,
                PmxReferenceTargetKind.BONE,
                False,
                "bone_index",
                TypeError,
                r"source reference must be an integer",
            ),
            (
                1.0,
                PmxReferenceTargetKind.BONE,
                False,
                "bone_index",
                TypeError,
                r"source reference must be an integer",
            ),
        )
        for value, kind, sentinel, field_name, error, message in failures:
            with self.subTest(value=value, error=error.__name__):
                with self.assertRaisesRegex(error, message):
                    resolver.resolve_source_reference(
                        kind,
                        value,
                        allow_sentinel=sentinel,
                        field_name=field_name,
                    )

    def test_new_reference_requires_one_matching_planned_identity(self) -> None:
        resolver = _resolver(
            target_remaps=(
                _target_remap(PmxReferenceTargetKind.TEXTURE, _new_only_remap()),
                _target_remap(PmxReferenceTargetKind.BONE, _new_only_remap()),
            ),
            identities=(
                _identity(PmxReferenceTargetKind.TEXTURE, "texture", 4, 0),
                _identity(PmxReferenceTargetKind.BONE, "provider", 5, 0),
            ),
        )
        self.assertEqual(
            resolver.resolve_new_reference(
                PmxReferenceTargetKind.TEXTURE,
                "texture",
                field_name="texture_index",
            ),
            0,
        )

        failures = (
            (
                "missing",
                r"unknown request-local new_id 'missing'",
            ),
            (
                "provider",
                r"new_id 'provider' belongs to bone",
            ),
        )
        for value, message in failures:
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, message):
                    resolver.resolve_new_reference(
                        PmxReferenceTargetKind.TEXTURE,
                        value,
                        field_name="texture_index",
                    )

    def test_resolver_rejects_noncanonical_or_unplanned_evidence(self) -> None:
        resolver_type = _reference_module().PmxStructuralTransactionReferenceResolver
        cases = (
            (lambda: resolver_type([]), TypeError, r"source_counts must be a tuple"),
            (
                lambda: resolver_type(tuple(reversed(_source_counts()))),
                ValueError,
                r"all six target kinds in canonical order",
            ),
            (
                lambda: _resolver(
                    source_counts=_source_counts(texture=1),
                    target_remaps=(
                        _target_remap(
                            PmxReferenceTargetKind.TEXTURE,
                            PmxIndexRemap.identity(0),
                        ),
                    ),
                ),
                ValueError,
                r"remap old_size must match",
            ),
            (
                lambda: _resolver(
                    target_remaps=(
                        _target_remap(
                            PmxReferenceTargetKind.BONE,
                            PmxIndexRemap.identity(0),
                        ),
                        _target_remap(
                            PmxReferenceTargetKind.TEXTURE,
                            PmxIndexRemap.identity(0),
                        ),
                    ),
                ),
                ValueError,
                r"canonical target-kind order",
            ),
            (
                lambda: _resolver(
                    identities=(
                        _identity(PmxReferenceTargetKind.TEXTURE, "texture", 0, 0),
                    ),
                ),
                ValueError,
                r"has no planned texture target remap",
            ),
            (
                lambda: _resolver(
                    source_counts=_source_counts(texture=1),
                    target_remaps=(
                        _target_remap(
                            PmxReferenceTargetKind.TEXTURE,
                            PmxIndexRemap.identity(1),
                        ),
                    ),
                    identities=(
                        _identity(PmxReferenceTargetKind.TEXTURE, "texture", 0, 0),
                    ),
                ),
                ValueError,
                r"final_index must be a planned new-only texture index",
            ),
        )
        for build, error, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(error, message):
                    build()

        texture_map = _target_remap(PmxReferenceTargetKind.TEXTURE, _new_only_remap(2))
        duplicate_cases = (
            (
                _identity(PmxReferenceTargetKind.TEXTURE, "same", 0, 0),
                _identity(PmxReferenceTargetKind.TEXTURE, "same", 1, 1),
                r"new_id 'same' must be globally unique",
            ),
            (
                _identity(PmxReferenceTargetKind.TEXTURE, "first", 0, 0),
                _identity(PmxReferenceTargetKind.TEXTURE, "second", 0, 1),
                r"operation_index values must be globally unique",
            ),
            (
                _identity(PmxReferenceTargetKind.TEXTURE, "first", 0, 0),
                _identity(PmxReferenceTargetKind.TEXTURE, "second", 1, 0),
                r"cannot reuse one target final index",
            ),
        )
        for first, second, message in duplicate_cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    _resolver(
                        target_remaps=(texture_map,),
                        identities=(first, second),
                    )

    def test_complete_authorized_new_reference_matrix_resolves(self) -> None:
        provider_ids = {
            PmxReferenceTargetKind.VERTEX: "vertex",
            PmxReferenceTargetKind.TEXTURE: "texture",
            PmxReferenceTargetKind.MATERIAL: "material",
            PmxReferenceTargetKind.BONE: "bone",
            PmxReferenceTargetKind.RIGID_BODY: "rigid_body",
        }
        provider_kinds = tuple(provider_ids)
        resolver = _resolver(
            target_remaps=tuple(
                _target_remap(kind, _new_only_remap())
                for kind in provider_kinds
            ),
            identities=tuple(
                _identity(kind, provider_ids[kind], operation, 0)
                for operation, kind in enumerate(provider_kinds)
            ),
        )
        references = {
            kind: PmxStructuralNewReference(kind.value, provider_ids[kind])
            for kind in provider_kinds
        }
        texture = references[PmxReferenceTargetKind.TEXTURE]
        bone = references[PmxReferenceTargetKind.BONE]
        vertex = references[PmxReferenceTargetKind.VERTEX]
        material_reference = references[PmxReferenceTargetKind.MATERIAL]
        rigid_reference = references[PmxReferenceTargetKind.RIGID_BODY]

        material = PmxStructuralMaterialInsertion(
            "material",
            texture_index=texture,
            sphere_texture_index=texture,
            toon_reference_index=texture,
        )
        vertices = (
            _vertex_insertion(PmxStructuralVertexBdef1(bone)),
            _vertex_insertion(PmxStructuralVertexBdef4((bone,) * 4, (0.25,) * 4)),
        )
        rigid_body = PmxStructuralRigidBodyInsertion("rigid", bone_index=bone)
        morphs = (
            PmxStructuralMorphInsertion(
                "vertex morph",
                "vertex",
                offsets=(PmxStructuralMorphVertexOffset(vertex, (0.0,) * 3),),
            ),
            PmxStructuralMorphInsertion(
                "uv morph",
                "uv",
                offsets=(PmxStructuralMorphUvOffset(vertex, (0.0,) * 4),),
            ),
            PmxStructuralMorphInsertion(
                "bone morph",
                "bone",
                offsets=(
                    PmxStructuralMorphBoneOffset(
                        bone,
                        (0.0,) * 3,
                        (0.0, 0.0, 0.0, 1.0),
                    ),
                ),
            ),
            PmxStructuralMorphInsertion(
                "material morph",
                "material",
                offsets=(_material_morph_offset(material_reference),),
            ),
            PmxStructuralMorphInsertion(
                "impulse morph",
                "impulse",
                offsets=(
                    PmxStructuralMorphImpulseOffset(
                        rigid_reference,
                        False,
                        (0.0,) * 3,
                        (0.0,) * 3,
                    ),
                ),
            ),
        )

        inputs = [
            (material.texture_index, PmxReferenceTargetKind.TEXTURE),
            (material.sphere_texture_index, PmxReferenceTargetKind.TEXTURE),
            (material.toon_reference_index, PmxReferenceTargetKind.TEXTURE),
            (vertices[0].deform.bone_index, PmxReferenceTargetKind.BONE),
            (rigid_body.bone_index, PmxReferenceTargetKind.BONE),
        ]
        inputs.extend(
            (value, PmxReferenceTargetKind.BONE)
            for value in vertices[1].deform.bone_indices
        )
        morph_kinds = (
            PmxReferenceTargetKind.VERTEX,
            PmxReferenceTargetKind.VERTEX,
            PmxReferenceTargetKind.BONE,
            PmxReferenceTargetKind.MATERIAL,
            PmxReferenceTargetKind.RIGID_BODY,
        )
        for morph, kind in zip(morphs, morph_kinds, strict=True):
            offset = morph.offsets[0]
            attribute = {
                PmxReferenceTargetKind.VERTEX: "vertex_index",
                PmxReferenceTargetKind.BONE: "bone_index",
                PmxReferenceTargetKind.MATERIAL: "material_index",
                PmxReferenceTargetKind.RIGID_BODY: "rigid_body_index",
            }[kind]
            inputs.append((getattr(offset, attribute), kind))

        self.assertEqual(len(inputs), 14)
        for position, (value, kind) in enumerate(inputs):
            self.assertEqual(
                _resolve_dto_reference(
                    resolver,
                    value,
                    kind,
                    f"reference[{position}]",
                ),
                0,
            )

    def test_unauthorized_matrix_expansions_remain_rejected_by_dtos(self) -> None:
        bone = PmxStructuralNewReference("bone", "bone")
        morph = PmxStructuralNewReference("morph", "morph")
        texture = PmxStructuralNewReference("texture", "texture")
        invalid = (
            lambda: PmxStructuralBoneInsertion("bone", parent_bone_index=bone),
            lambda: PmxStructuralMorphGroupOffset(morph, 1.0),
            lambda: PmxStructuralMorphFlipOffset(morph, 1.0),
            lambda: PmxStructuralMaterialInsertion(
                "material",
                toon_reference_mode="shared",
                toon_reference_index=texture,
            ),
        )
        for position, build in enumerate(invalid):
            with self.subTest(position=position):
                with self.assertRaises(TypeError):
                    build()

        wrong_kind = (
            lambda: PmxStructuralMaterialInsertion("material", texture_index=bone),
            lambda: PmxStructuralVertexBdef1(texture),
            lambda: PmxStructuralRigidBodyInsertion("rigid", bone_index=texture),
            lambda: PmxStructuralMorphVertexOffset(bone, (0.0,) * 3),
        )
        for position, build in enumerate(wrong_kind):
            with self.subTest(wrong_kind_position=position):
                with self.assertRaises(ValueError):
                    build()


if __name__ == "__main__":
    unittest.main()
