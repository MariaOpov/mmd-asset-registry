"""CP14 semantic rigid-body insertion preview safety and reference coverage."""

from __future__ import annotations

import io
import struct
import unittest
from dataclasses import FrozenInstanceError, replace
from unittest.mock import patch

import mmd_registry.pmx as pmx_public
import mmd_registry.services as services
from mmd_registry.diagnostics import PmxServiceError
from mmd_registry.pmx import structural_rigid_body_insertion as rigid_module
from mmd_registry.pmx.document import PmxImpulseMorphOffset
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.services.structural_bone import PmxStructuralBoneInsertion
from mmd_registry.services.structural_morph import (
    PmxStructuralMorphImpulseOffset,
    PmxStructuralMorphInsertion,
)
from mmd_registry.services.structural_rigid_body import (
    PmxStructuralRigidBodyInsertion,
)
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


def _clean_document(
    *,
    version: float = 2.1,
    encoding_flag: int = 1,
    index_size: int = 1,
):
    return replace(
        load_pmx(
            io.BytesIO(
                build_pmx_roundtrip_fixture(
                    version=version,
                    encoding_flag=encoding_flag,
                    index_size=index_size,
                )
            )
        ),
        trailing_data=b"",
    )


def _rigid(
    name: str = "CP14 rigid",
    *,
    position: str = "append",
    source_index: int | None = None,
    **kwargs,
):
    return PmxStructuralRigidBodyInsertion(
        local_name=name,
        position=position,
        source_index=source_index,
        **kwargs,
    )


def _shift_required(index: int, anchor: int) -> int:
    return index + 1 if index >= anchor else index


def _shift_optional(index: int, anchor: int) -> int:
    if index == -1:
        return -1
    return _shift_required(index, anchor)


class RigidBodyInsertionPreviewTests(unittest.TestCase):
    def test_public_boundary_and_alias_remain_frozen(self) -> None:
        self.assertFalse(hasattr(services, "PmxStructuralRigidBodyInsertion"))
        self.assertFalse(hasattr(pmx_public, "PmxStructuralRigidBodyInsertion"))
        self.assertIs(
            services.PmxStructuralEditRequest,
            services.PmxStructuralPreviewRequest,
        )
        self.assertIs((services.get_capabilities().to_dict())["structural_insert"], True)

    def test_semantic_dto_is_frozen_and_uses_bounded_vocabulary(self) -> None:
        insertion = _rigid(
            shape="capsule",
            physics_mode="physics_with_bone_alignment",
        )
        with self.assertRaises(FrozenInstanceError):
            insertion.mass = 2.0  # type: ignore[misc]
        with self.assertRaises(ValueError):
            _rigid(shape="mesh")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            _rigid(physics_mode="automatic")  # type: ignore[arg-type]

    def test_append_preview_materializes_complete_semantic_record(self) -> None:
        source = _clean_document()
        request = services.PmxStructuralPreviewRequest(
            rigid_body_insertions=(
                _rigid(
                    "private-cp14-rigid-name",
                    bone_index=0,
                    collision_group=7,
                    collision_mask=0x1234,
                    shape="box",
                    size=(1.25, 2.5, 3.75),
                    body_position=(4.0, -5.0, 6.0),
                    rotation=(0.1, 0.2, 0.3),
                    mass=2.0,
                    linear_damping=0.2,
                    angular_damping=0.3,
                    restitution=0.4,
                    friction=0.5,
                    physics_mode="physics",
                ),
            ),
        )
        result = services.preview_structural_edit(source, request)
        body = result.document.rigid_bodies[-1]

        self.assertEqual(len(result.document.rigid_bodies), len(source.rigid_bodies) + 1)
        self.assertEqual(body.local_name, "private-cp14-rigid-name")
        self.assertEqual(body.bone_index, 0)
        self.assertEqual(body.collision_group, 7)
        self.assertEqual(body.collision_mask, 0x1234)
        self.assertEqual((body.shape, body.shape_name), (1, "box"))
        self.assertEqual((body.physics_mode, body.physics_mode_name), (1, "physics"))
        self.assertIsNot(result.document, source)
        self.assertEqual(source.rigid_bodies, _clean_document().rigid_bodies)

    def test_insert_before_shifts_all_existing_incoming_rigid_body_owners(self) -> None:
        source = _clean_document(version=2.1)
        self.assertGreaterEqual(len(source.rigid_bodies), 2)
        anchor = 0
        result = services.preview_structural_edit(
            source,
            services.PmxStructuralPreviewRequest(
                rigid_body_insertions=(
                    _rigid(position="insert_before", source_index=anchor),
                ),
            ),
        ).document

        for old_morph, new_morph in zip(source.morphs, result.morphs, strict=True):
            if old_morph.morph_type != 10:
                continue
            for old_offset, new_offset in zip(
                old_morph.offsets,
                new_morph.offsets,
                strict=True,
            ):
                self.assertIsInstance(old_offset, PmxImpulseMorphOffset)
                self.assertEqual(
                    new_offset.rigid_body_index,
                    _shift_required(old_offset.rigid_body_index, anchor),
                )

        for old_joint, new_joint in zip(source.joints, result.joints, strict=True):
            self.assertEqual(
                new_joint.rigid_body_a_index,
                _shift_optional(old_joint.rigid_body_a_index, anchor),
            )
            self.assertEqual(
                new_joint.rigid_body_b_index,
                _shift_optional(old_joint.rigid_body_b_index, anchor),
            )

        for old_soft, new_soft in zip(
            source.soft_bodies,
            result.soft_bodies,
            strict=True,
        ):
            for old_anchor, new_anchor in zip(
                old_soft.anchors,
                new_soft.anchors,
                strict=True,
            ):
                self.assertEqual(
                    new_anchor.rigid_body_index,
                    _shift_required(old_anchor.rigid_body_index, anchor),
                )
                self.assertEqual(new_anchor.vertex_index, old_anchor.vertex_index)

    def test_source_domain_bone_and_minus_one_are_preserved(self) -> None:
        source = _clean_document()
        result = services.preview_structural_edit(
            source,
            services.PmxStructuralPreviewRequest(
                rigid_body_insertions=(
                    _rigid("sentinel", bone_index=-1),
                    _rigid("bone", bone_index=0),
                ),
            ),
        ).document
        self.assertEqual(result.rigid_bodies[-2].bone_index, -1)
        self.assertEqual(result.rigid_bodies[-1].bone_index, 0)

        with self.assertRaises(PmxServiceError):
            services.preview_structural_edit(
                source,
                services.PmxStructuralPreviewRequest(
                    rigid_body_insertions=(
                        _rigid(bone_index=len(source.bones)),
                    ),
                ),
            )

    def test_same_anchor_and_append_order_are_stable(self) -> None:
        source = _clean_document()
        result = services.preview_structural_edit(
            source,
            services.PmxStructuralPreviewRequest(
                rigid_body_insertions=(
                    _rigid("A", position="insert_before", source_index=0),
                    _rigid("B", position="insert_before", source_index=0),
                    _rigid("C"),
                    _rigid("D"),
                ),
            ),
        ).document
        self.assertEqual([body.local_name for body in result.rigid_bodies[:2]], ["A", "B"])
        self.assertEqual([body.local_name for body in result.rigid_bodies[-2:]], ["C", "D"])

    def test_exact_float32_canonicalization_occurs_before_certification(self) -> None:
        source = _clean_document()
        value = 0.1
        canonical = struct.unpack("<f", struct.pack("<f", value))[0]
        body = services.preview_structural_edit(
            source,
            services.PmxStructuralPreviewRequest(
                rigid_body_insertions=(
                    _rigid(
                        size=(value, value, value),
                        body_position=(value, value, value),
                        rotation=(value, value, value),
                        mass=value,
                        linear_damping=value,
                        angular_damping=value,
                        restitution=value,
                        friction=value,
                    ),
                ),
            ),
        ).document.rigid_bodies[-1]
        self.assertEqual(body.size, (canonical, canonical, canonical))
        self.assertEqual(body.position, (canonical, canonical, canonical))
        self.assertEqual(body.rotation, (canonical, canonical, canonical))
        self.assertEqual(body.mass, canonical)

    def test_unrepresentable_float32_fails_before_shift_planner(self) -> None:
        source = _clean_document()
        with patch.object(
            rigid_module,
            "plan_collection_reference_shift",
            wraps=rigid_module.plan_collection_reference_shift,
        ) as planner:
            with self.assertRaises(PmxServiceError):
                services.preview_structural_edit(
                    source,
                    services.PmxStructuralPreviewRequest(
                        rigid_body_insertions=(_rigid(mass=1.0e100),),
                    ),
                )
            planner.assert_not_called()

    def test_invalid_domains_are_rejected(self) -> None:
        for kwargs in (
            {"collision_group": 16},
            {"collision_mask": 0x10000},
            {"size": (-1.0, 1.0, 1.0)},
            {"mass": -1.0},
            {"linear_damping": -1.0},
            {"angular_damping": -1.0},
            {"restitution": -1.0},
            {"friction": -1.0},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    _rigid(**kwargs)

    def test_parser_limit_fails_before_reference_shift_planner(self) -> None:
        source = _clean_document()
        with patch.object(rigid_module, "MAX_PMX_RIGID_BODY_COUNT", len(source.rigid_bodies)):
            with patch.object(
                rigid_module,
                "plan_collection_reference_shift",
                wraps=rigid_module.plan_collection_reference_shift,
            ) as planner:
                with self.assertRaises(PmxServiceError):
                    services.preview_structural_edit(
                        source,
                        services.PmxStructuralPreviewRequest(
                            rigid_body_insertions=(_rigid(),),
                        ),
                    )
                planner.assert_not_called()

    def test_one_byte_width_expansion_is_refused(self) -> None:
        source = _clean_document(index_size=1)
        template = source.rigid_bodies[0]
        constrained = replace(
            source,
            rigid_bodies=tuple(
                replace(template, local_name=f"Rigid {index}")
                for index in range(128)
            ),
            morphs=(),
            joints=(),
            soft_bodies=(),
        )
        with self.assertRaises(PmxServiceError):
            services.preview_structural_edit(
                constrained,
                services.PmxStructuralPreviewRequest(
                    rigid_body_insertions=(_rigid(),),
                ),
            )

    def test_preview_matrix_covers_versions_encodings_and_index_widths(self) -> None:
        for version in (2.0, 2.1):
            for encoding_flag in (0, 1):
                for index_size in (1, 2, 4):
                    with self.subTest(
                        version=version,
                        encoding_flag=encoding_flag,
                        index_size=index_size,
                    ):
                        source = _clean_document(
                            version=version,
                            encoding_flag=encoding_flag,
                            index_size=index_size,
                        )
                        result = services.preview_structural_edit(
                            source,
                            services.PmxStructuralPreviewRequest(
                                rigid_body_insertions=(_rigid("互換 CP14"),),
                            ),
                        )
                        self.assertEqual(
                            len(result.document.rigid_bodies),
                            len(source.rigid_bodies) + 1,
                        )
                        self.assertEqual(result.document.header, source.header)

    def test_impulse_morph_insertion_uses_existing_source_rigid_body(self) -> None:
        source = _clean_document(version=2.1)
        insertion = PmxStructuralMorphInsertion(
            local_name="Impulse",
            morph_type="impulse",
            offsets=(
                PmxStructuralMorphImpulseOffset(
                    rigid_body_index=0,
                    local=True,
                    velocity=(0.1, 0.2, 0.3),
                    angular_torque=(0.4, 0.5, 0.6),
                ),
            ),
        )
        result = services.preview_structural_edit(
            source,
            services.PmxStructuralPreviewRequest(morph_insertions=(insertion,)),
        )
        offset = result.document.morphs[-1].offsets[0]
        self.assertIsInstance(offset, PmxImpulseMorphOffset)
        self.assertEqual(offset.rigid_body_index, 0)
        self.assertTrue(offset.local)

    def test_impulse_morph_requires_pmx21(self) -> None:
        source = _clean_document(version=2.0)
        insertion = PmxStructuralMorphInsertion(
            local_name="Impulse",
            morph_type="impulse",
            offsets=(
                PmxStructuralMorphImpulseOffset(
                    rigid_body_index=0,
                    local=False,
                    velocity=(0.0, 0.0, 0.0),
                    angular_torque=(0.0, 0.0, 0.0),
                ),
            ),
        )
        with self.assertRaises(PmxServiceError):
            services.preview_structural_edit(
                source,
                services.PmxStructuralPreviewRequest(morph_insertions=(insertion,)),
            )

    def test_impulse_new_to_new_rigid_reference_is_refused(self) -> None:
        source = _clean_document(version=2.1)
        insertion = PmxStructuralMorphInsertion(
            local_name="Impulse",
            morph_type="impulse",
            offsets=(
                PmxStructuralMorphImpulseOffset(
                    rigid_body_index=len(source.rigid_bodies),
                    local=False,
                    velocity=(0.0, 0.0, 0.0),
                    angular_torque=(0.0, 0.0, 0.0),
                ),
            ),
        )
        with self.assertRaises(PmxServiceError):
            services.preview_structural_edit(
                source,
                services.PmxStructuralPreviewRequest(morph_insertions=(insertion,)),
            )

    def test_morph_and_rigid_body_insertions_can_mix_in_cp17(self) -> None:
        request = services.PmxStructuralPreviewRequest(
            morph_insertions=(
                PmxStructuralMorphInsertion(
                    local_name="Impulse",
                    morph_type="impulse",
                ),
            ),
            rigid_body_insertions=(_rigid(),),
        )
        self.assertEqual(len(request.morph_insertions), 1)
        self.assertEqual(len(request.rigid_body_insertions), 1)

    def test_rigid_body_insertion_can_mix_with_prior_targets(self) -> None:
        request = services.PmxStructuralPreviewRequest(
            bone_insertions=(PmxStructuralBoneInsertion(local_name="mixed"),),
            rigid_body_insertions=(_rigid(),),
        )
        self.assertEqual(len(request.bone_insertions), 1)
        self.assertEqual(len(request.rigid_body_insertions), 1)

    def test_preview_is_deterministic_and_report_is_privacy_bounded(self) -> None:
        source = _clean_document()
        request = services.PmxStructuralPreviewRequest(
            rigid_body_insertions=(_rigid("private-rigid-name"),),
        )
        first = services.preview_structural_edit(source, request)
        second = services.preview_structural_edit(source, request)
        self.assertEqual(first.document, second.document)
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertNotIn("private-rigid-name", str(first.to_dict()))


if __name__ == "__main__":
    unittest.main()
