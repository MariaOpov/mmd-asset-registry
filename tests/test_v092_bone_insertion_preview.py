"""CP11 public and internal contracts for preview-only semantic bone insertion."""

from __future__ import annotations

import io
import json
import math
import struct
import tempfile
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from unittest.mock import patch

import mmd_registry.pmx as pmx_public
import mmd_registry.services as services
import mmd_registry.services.structural_bone as structural_bone_service
from mmd_registry.diagnostics import PmxServiceError
from mmd_registry.pmx.document import (
    PMX_BONE_FLAG_AFTER_PHYSICS,
    PMX_BONE_FLAG_ENABLED,
    PMX_BONE_FLAG_EXTERNAL_PARENT,
    PMX_BONE_FLAG_FIXED_AXIS,
    PMX_BONE_FLAG_IK,
    PMX_BONE_FLAG_INHERIT_ROTATION,
    PMX_BONE_FLAG_INHERIT_TRANSLATION,
    PMX_BONE_FLAG_LOCAL_APPEND,
    PMX_BONE_FLAG_LOCAL_AXES,
    PMX_BONE_FLAG_ROTATABLE,
    PMX_BONE_FLAG_TAIL_INDEX,
    PMX_BONE_FLAG_TRANSLATABLE,
    PMX_BONE_FLAG_VISIBLE,
    PmxBdef1,
    PmxBdef2,
    PmxBdef4,
    PmxBoneMorphOffset,
    PmxQdef,
    PmxSdef,
)
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.structural_bone_insertion import (
    PmxBoneIkInsertionPayload,
    PmxBoneIkLinkInsertionPayload,
    PmxBoneInsertionPayload,
    PmxStructuralBoneInsertionError,
    preview_pmx_bone_insertions,
)
from mmd_registry.pmx.structural_insert_intent import PmxStructuralInsertPosition
from mmd_registry.services.structural_bone import (
    PmxStructuralBoneIk,
    PmxStructuralBoneIkLink,
    PmxStructuralBoneInsertion,
)
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


def _clean_document(*, version: float = 2.1, index_size: int = 1):
    return replace(
        load_pmx(
            io.BytesIO(
                build_pmx_roundtrip_fixture(
                    version=version,
                    index_size=index_size,
                )
            )
        ),
        trailing_data=b"",
    )


def _shift_optional(index: int, anchor: int) -> int:
    if index == -1:
        return -1
    return index + 1 if index >= anchor else index


def _shift_required(index: int, anchor: int) -> int:
    return index + 1 if index >= anchor else index


def _bone_payload(
    name: str = "Inserted Bone",
    *,
    position: PmxStructuralInsertPosition | None = None,
    **kwargs,
) -> PmxBoneInsertionPayload:
    defaults = {
        "local_name": name,
        "universal_name": "",
        "bone_position": (0.0, 0.0, 0.0),
        "parent_bone_index": -1,
        "transform_layer": 0,
        "rotatable": False,
        "translatable": False,
        "visible": False,
        "enabled": False,
        "local_append": False,
        "after_physics": False,
        "tail_offset": (0.0, 1.0, 0.0),
        "tail_bone_index": None,
        "inherit_rotation": False,
        "inherit_translation": False,
        "inherit_parent_bone_index": None,
        "inherit_weight": None,
        "fixed_axis": None,
        "local_axis_x": None,
        "local_axis_z": None,
        "external_parent_key": None,
        "ik": None,
        "position": position or PmxStructuralInsertPosition.append(),
    }
    defaults.update(kwargs)
    return PmxBoneInsertionPayload(**defaults)


def _assert_vertex_deforms_shifted(
    test: unittest.TestCase,
    source,
    rewritten,
    *,
    anchor: int,
) -> None:
    for source_vertex, output_vertex in zip(
        source.vertices,
        rewritten.vertices,
        strict=True,
    ):
        source_deform = source_vertex.deform
        output_deform = output_vertex.deform
        if isinstance(source_deform, PmxBdef1):
            test.assertIsInstance(output_deform, PmxBdef1)
            test.assertEqual(
                output_deform.bone_index,
                _shift_optional(source_deform.bone_index, anchor),
            )
            continue
        if isinstance(source_deform, (PmxBdef2, PmxBdef4, PmxSdef, PmxQdef)):
            test.assertIsInstance(
                output_deform,
                (PmxBdef2, PmxBdef4, PmxSdef, PmxQdef),
            )
            test.assertEqual(
                output_deform.bone_indices,
                tuple(
                    _shift_optional(index, anchor)
                    for index in source_deform.bone_indices
                ),
            )
            continue
        test.fail(f"unsupported fixture deform {type(source_deform).__name__}")


def _assert_existing_bone_refs_shifted(
    test: unittest.TestCase,
    source,
    rewritten,
    *,
    anchor: int,
) -> None:
    for old_index, source_bone in enumerate(source.bones):
        new_index = _shift_required(old_index, anchor)
        output_bone = rewritten.bones[new_index]
        test.assertEqual(
            output_bone.parent_bone_index,
            _shift_optional(source_bone.parent_bone_index, anchor),
        )
        if source_bone.tail_bone_index is None:
            test.assertIsNone(output_bone.tail_bone_index)
            test.assertEqual(output_bone.tail_offset, source_bone.tail_offset)
        else:
            test.assertEqual(
                output_bone.tail_bone_index,
                _shift_optional(source_bone.tail_bone_index, anchor),
            )
        if source_bone.inherit_parent_bone_index is None:
            test.assertIsNone(output_bone.inherit_parent_bone_index)
        else:
            test.assertEqual(
                output_bone.inherit_parent_bone_index,
                _shift_optional(
                    source_bone.inherit_parent_bone_index,
                    anchor,
                ),
            )
        if source_bone.ik is None:
            test.assertIsNone(output_bone.ik)
        else:
            test.assertIsNotNone(output_bone.ik)
            assert output_bone.ik is not None
            test.assertEqual(
                output_bone.ik.target_bone_index,
                _shift_required(source_bone.ik.target_bone_index, anchor),
            )
            test.assertEqual(
                tuple(link.bone_index for link in output_bone.ik.links),
                tuple(
                    _shift_required(link.bone_index, anchor)
                    for link in source_bone.ik.links
                ),
            )


def _assert_external_bone_owners_shifted(
    test: unittest.TestCase,
    source,
    rewritten,
    *,
    anchor: int,
) -> None:
    for source_morph, output_morph in zip(
        source.morphs,
        rewritten.morphs,
        strict=True,
    ):
        for source_offset, output_offset in zip(
            source_morph.offsets,
            output_morph.offsets,
            strict=True,
        ):
            if isinstance(source_offset, PmxBoneMorphOffset):
                test.assertIsInstance(output_offset, PmxBoneMorphOffset)
                test.assertEqual(
                    output_offset.bone_index,
                    _shift_required(source_offset.bone_index, anchor),
                )

    for source_frame, output_frame in zip(
        source.display_frames,
        rewritten.display_frames,
        strict=True,
    ):
        for source_element, output_element in zip(
            source_frame.elements,
            output_frame.elements,
            strict=True,
        ):
            if source_element.target_type == "bone":
                test.assertEqual(
                    output_element.target_index,
                    _shift_required(source_element.target_index, anchor),
                )
            else:
                test.assertEqual(output_element, source_element)

    for source_body, output_body in zip(
        source.rigid_bodies,
        rewritten.rigid_bodies,
        strict=True,
    ):
        test.assertEqual(
            output_body.bone_index,
            _shift_optional(source_body.bone_index, anchor),
        )


class BoneInsertionPublicContractTests(unittest.TestCase):
    def test_public_dtos_are_additive_immutable_hashable_and_not_root_exported(
        self,
    ) -> None:
        link = PmxStructuralBoneIkLink(0)
        ik = PmxStructuralBoneIk(0, links=(link,))
        insertion = PmxStructuralBoneInsertion(local_name="CP11", ik=ik)
        request = services.PmxStructuralPreviewRequest(
            bone_insertions=(insertion,),
        )

        self.assertEqual(
            structural_bone_service.__all__,
            (
                "PmxStructuralBoneIkLink",
                "PmxStructuralBoneIk",
                "PmxStructuralBoneInsertion",
            ),
        )
        self.assertFalse(hasattr(services, "PmxStructuralBoneInsertion"))
        self.assertFalse(hasattr(pmx_public, "PmxStructuralBoneInsertion"))
        self.assertIs(
            services.PmxStructuralEditRequest,
            services.PmxStructuralPreviewRequest,
        )
        self.assertEqual(request.bone_insertions, (insertion,))
        self.assertEqual(hash(link), hash(link))
        self.assertEqual(hash(ik), hash(ik))
        self.assertEqual(hash(insertion), hash(insertion))
        self.assertEqual(hash(request), hash(request))

        with self.assertRaises(FrozenInstanceError):
            insertion.local_name = "changed"  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            request.bone_insertions = ()  # type: ignore[misc]

        for name in (
            "PmxBoneInsertionPayload",
            "PmxBoneInsertionPreview",
            "preview_pmx_bone_insertions",
        ):
            self.assertFalse(hasattr(services, name))
        self.assertEqual(
            services.__all__[-7:],
            (
                "PmxStructuralCollectionEdit",
                "PmxStructuralPreviewRequest",
                "PmxStructuralPreviewResult",
                "preview_structural_edit",
                "PmxStructuralEditRequest",
                "PmxStructuralExecutionResult",
                "apply_structural_edit",
            ),
        )

    def test_public_bone_dto_has_semantic_vocabulary_not_raw_section_fields(self) -> None:
        insertion = PmxStructuralBoneInsertion(local_name="Semantic")
        self.assertFalse(hasattr(insertion, "flags"))
        self.assertFalse(hasattr(insertion, "flag_names"))
        self.assertFalse(hasattr(insertion, "tail_mode"))

        with self.assertRaises(TypeError):
            PmxStructuralBoneInsertion(
                local_name="A",
                flags=0,  # type: ignore[call-arg]
            )
        with self.assertRaises(TypeError):
            PmxStructuralBoneInsertion(
                local_name="A",
                tail_mode="offset",  # type: ignore[call-arg]
            )

    def test_public_dto_rejects_invalid_tail_inherit_axes_and_boolean_shapes(self) -> None:
        with self.assertRaises(ValueError):
            PmxStructuralBoneInsertion(
                local_name="A",
                tail_offset=None,
                tail_bone_index=None,
            )
        with self.assertRaises(ValueError):
            PmxStructuralBoneInsertion(
                local_name="A",
                tail_offset=(0.0, 1.0, 0.0),
                tail_bone_index=0,
            )
        with self.assertRaises(ValueError):
            PmxStructuralBoneInsertion(
                local_name="A",
                inherit_rotation=True,
            )
        with self.assertRaises(ValueError):
            PmxStructuralBoneInsertion(
                local_name="A",
                inherit_parent_bone_index=0,
                inherit_weight=0.5,
            )
        with self.assertRaises(ValueError):
            PmxStructuralBoneInsertion(
                local_name="A",
                local_axis_x=(1.0, 0.0, 0.0),
            )
        with self.assertRaises(TypeError):
            PmxStructuralBoneInsertion(
                local_name="A",
                visible=1,  # type: ignore[arg-type]
            )

    def test_public_ik_dtos_reject_sentinel_and_limit_pair_mismatches(self) -> None:
        with self.assertRaises(ValueError):
            PmxStructuralBoneIkLink(-1)
        with self.assertRaises(ValueError):
            PmxStructuralBoneIk(-1)
        with self.assertRaises(ValueError):
            PmxStructuralBoneIkLink(
                0,
                lower_limit=(-1.0, -1.0, -1.0),
                upper_limit=None,
            )
        with self.assertRaises(ValueError):
            PmxStructuralBoneIk(0, loop_count=-1)
        with self.assertRaises(ValueError):
            PmxStructuralBoneIk(0, angle_limit=math.nan)
        with self.assertRaises(TypeError):
            PmxStructuralBoneIk(0, links=[PmxStructuralBoneIkLink(0)])  # type: ignore[arg-type]

    def test_collection_position_contract_remains_source_domain(self) -> None:
        with self.assertRaises(ValueError):
            PmxStructuralBoneInsertion(
                local_name="A",
                position="append",
                source_index=0,
            )
        with self.assertRaises(TypeError):
            PmxStructuralBoneInsertion(
                local_name="A",
                position="insert_before",
            )
        with self.assertRaises(TypeError):
            PmxStructuralBoneInsertion(
                local_name="A",
                position="insert_before",
                source_index=True,  # type: ignore[arg-type]
            )
        with self.assertRaises(ValueError):
            PmxStructuralBoneInsertion(
                local_name="A",
                position="insert_before",
                source_index=-1,
            )

    def test_request_rejects_wrong_container_and_all_mixed_mutation_vocabularies(
        self,
    ) -> None:
        insertion = PmxStructuralBoneInsertion(local_name="A")
        with self.assertRaises(TypeError):
            services.PmxStructuralPreviewRequest(
                bone_insertions=[insertion],  # type: ignore[arg-type]
            )
        with self.assertRaises(TypeError):
            services.PmxStructuralPreviewRequest(
                bone_insertions=(object(),),  # type: ignore[arg-type]
            )

        edit = services.PmxStructuralCollectionEdit(
            services.PmxReferenceTargetKind.BONE,
            (),
        )
        with self.assertRaisesRegex(ValueError, "cannot be combined"):
            services.PmxStructuralPreviewRequest(
                collection_edits=(edit,),
                bone_insertions=(insertion,),
            )

        from mmd_registry.services.structural_material import (
            PmxStructuralMaterialInsertion,
        )
        from mmd_registry.services.structural_texture import (
            PmxStructuralTextureInsertion,
        )

        texture_request = services.PmxStructuralPreviewRequest(
            texture_insertions=(
                PmxStructuralTextureInsertion("textures/a.png"),
            ),
            bone_insertions=(insertion,),
        )
        self.assertEqual(texture_request.bone_insertions, (insertion,))
        material_request = services.PmxStructuralPreviewRequest(
            material_insertions=(
                PmxStructuralMaterialInsertion(local_name="M"),
            ),
            bone_insertions=(insertion,),
        )
        self.assertEqual(material_request.bone_insertions, (insertion,))

    def test_capability_manifest_is_not_promoted(self) -> None:
        payload = services.get_capabilities().to_dict()
        self.assertTrue(payload["structural_preview"])
        self.assertTrue(payload["structural_write"])
        self.assertNotIn("structural_insert", payload)
        self.assertNotIn("PmxStructuralBoneInsertion", json.dumps(payload))


class BoneInsertionPreviewTests(unittest.TestCase):
    def test_append_preview_adds_one_offset_tail_bone_without_mutating_source(self) -> None:
        source = _clean_document()
        request = services.PmxStructuralPreviewRequest(
            bone_insertions=(
                PmxStructuralBoneInsertion(
                    local_name="CP11 append",
                    universal_name="Bone",
                    bone_position=(0.1, 0.2, 0.3),
                    rotatable=True,
                    visible=True,
                    enabled=True,
                ),
            ),
        )

        first = services.preview_structural_edit(source, request)
        second = services.preview_structural_edit(source, request)
        output = first.document
        inserted = output.bones[-1]

        self.assertEqual(first.status, "changes_pending")
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(output.bones[:-1], source.bones)
        self.assertEqual(inserted.local_name, "CP11 append")
        self.assertEqual(inserted.parent_bone_index, -1)
        self.assertEqual(inserted.tail_mode, "offset")
        self.assertEqual(inserted.tail_offset, (0.0, 0.0, 0.0))
        self.assertTrue(inserted.flags & PMX_BONE_FLAG_ROTATABLE)
        self.assertTrue(inserted.flags & PMX_BONE_FLAG_VISIBLE)
        self.assertTrue(inserted.flags & PMX_BONE_FLAG_ENABLED)
        self.assertEqual(source, _clean_document())

        expected = struct.unpack("<f", struct.pack("<f", 0.1))[0]
        self.assertEqual(inserted.position[0], expected)

        evidence = first.to_dict()
        self.assertEqual(evidence["preview_schema_version"], 1)
        self.assertFalse(evidence["output"]["written"])
        self.assertEqual(evidence["verification"]["serialization"], "not_performed")
        self.assertEqual(
            evidence["output"]["target_counts"]["bone"],
            len(source.bones) + 1,
        )
        self.assertEqual(
            evidence["audit"]["bone_insertion"]["new_indices_in_request_order"],
            [len(source.bones)],
        )

    def test_insert_before_zero_shifts_every_existing_bone_owner_exactly_once(self) -> None:
        source = _clean_document()
        request = services.PmxStructuralPreviewRequest(
            bone_insertions=(
                PmxStructuralBoneInsertion(
                    local_name="Before zero",
                    position="insert_before",
                    source_index=0,
                ),
            ),
        )

        result = services.preview_structural_edit(source, request)
        output = result.document

        self.assertEqual(output.bones[0].local_name, "Before zero")
        self.assertEqual(output.bones[0].parent_bone_index, -1)
        self.assertEqual(len(output.bones), len(source.bones) + 1)
        _assert_vertex_deforms_shifted(self, source, output, anchor=0)
        _assert_existing_bone_refs_shifted(self, source, output, anchor=0)
        _assert_external_bone_owners_shifted(self, source, output, anchor=0)

        self.assertEqual(output.materials, source.materials)
        self.assertEqual(output.texture_paths, source.texture_paths)
        self.assertEqual(output.joints, source.joints)
        self.assertEqual(output.soft_bodies, source.soft_bodies)
        self.assertEqual(output.surface_indices, source.surface_indices)

    def test_inserted_outgoing_references_are_source_domain_then_shifted(self) -> None:
        source = _clean_document()
        self.assertGreaterEqual(len(source.bones), 2)
        ik = PmxStructuralBoneIk(
            target_bone_index=0,
            loop_count=4,
            angle_limit=0.1,
            links=(
                PmxStructuralBoneIkLink(0),
                PmxStructuralBoneIkLink(
                    1,
                    lower_limit=(-0.1, -0.2, -0.3),
                    upper_limit=(0.1, 0.2, 0.3),
                ),
            ),
        )
        request = services.PmxStructuralPreviewRequest(
            bone_insertions=(
                PmxStructuralBoneInsertion(
                    local_name="Referenced",
                    parent_bone_index=0,
                    tail_offset=None,
                    tail_bone_index=1,
                    inherit_rotation=True,
                    inherit_parent_bone_index=0,
                    inherit_weight=0.25,
                    ik=ik,
                    position="insert_before",
                    source_index=0,
                ),
            ),
        )

        output = services.preview_structural_edit(source, request).document
        inserted = output.bones[0]

        self.assertEqual(inserted.parent_bone_index, 1)
        self.assertEqual(inserted.tail_bone_index, 2)
        self.assertEqual(inserted.inherit_parent_bone_index, 1)
        self.assertIsNotNone(inserted.ik)
        assert inserted.ik is not None
        self.assertEqual(inserted.ik.target_bone_index, 1)
        self.assertEqual(
            tuple(link.bone_index for link in inserted.ik.links),
            (1, 2),
        )

    def test_full_semantic_payload_derives_only_expected_flag_bits(self) -> None:
        source = _clean_document()
        ik = PmxStructuralBoneIk(
            target_bone_index=0,
            links=(PmxStructuralBoneIkLink(0),),
        )
        request = services.PmxStructuralPreviewRequest(
            bone_insertions=(
                PmxStructuralBoneInsertion(
                    local_name="All flags",
                    parent_bone_index=0,
                    rotatable=True,
                    translatable=True,
                    visible=True,
                    enabled=True,
                    local_append=True,
                    after_physics=True,
                    tail_offset=None,
                    tail_bone_index=0,
                    inherit_rotation=True,
                    inherit_translation=True,
                    inherit_parent_bone_index=0,
                    inherit_weight=0.5,
                    fixed_axis=(1.0, 0.0, 0.0),
                    local_axis_x=(1.0, 0.0, 0.0),
                    local_axis_z=(0.0, 0.0, 1.0),
                    external_parent_key=7,
                    ik=ik,
                ),
            ),
        )

        inserted = services.preview_structural_edit(source, request).document.bones[-1]
        expected_flags = (
            PMX_BONE_FLAG_TAIL_INDEX
            | PMX_BONE_FLAG_ROTATABLE
            | PMX_BONE_FLAG_TRANSLATABLE
            | PMX_BONE_FLAG_VISIBLE
            | PMX_BONE_FLAG_ENABLED
            | PMX_BONE_FLAG_IK
            | PMX_BONE_FLAG_LOCAL_APPEND
            | PMX_BONE_FLAG_INHERIT_ROTATION
            | PMX_BONE_FLAG_INHERIT_TRANSLATION
            | PMX_BONE_FLAG_FIXED_AXIS
            | PMX_BONE_FLAG_LOCAL_AXES
            | PMX_BONE_FLAG_AFTER_PHYSICS
            | PMX_BONE_FLAG_EXTERNAL_PARENT
        )
        self.assertEqual(inserted.flags, expected_flags)
        self.assertEqual(set(inserted.flag_names), {
            "tail_index",
            "rotatable",
            "translatable",
            "visible",
            "enabled",
            "ik",
            "local_append",
            "inherit_rotation",
            "inherit_translation",
            "fixed_axis",
            "local_axes",
            "after_physics",
            "external_parent",
        })

    def test_same_anchor_and_append_order_are_stable(self) -> None:
        source = _clean_document()
        request = services.PmxStructuralPreviewRequest(
            bone_insertions=(
                PmxStructuralBoneInsertion(
                    local_name="First",
                    position="insert_before",
                    source_index=0,
                ),
                PmxStructuralBoneInsertion(
                    local_name="Second",
                    position="insert_before",
                    source_index=0,
                ),
                PmxStructuralBoneInsertion(local_name="Append"),
            ),
        )
        output = services.preview_structural_edit(source, request).document

        self.assertEqual(
            tuple(bone.local_name for bone in output.bones[:2]),
            ("First", "Second"),
        )
        self.assertEqual(
            tuple(
                bone.local_name
                for bone in output.bones[2 : 2 + len(source.bones)]
            ),
            tuple(bone.local_name for bone in source.bones),
        )
        self.assertEqual(output.bones[-1].local_name, "Append")

    def test_new_to_new_parent_tail_inherit_and_ik_references_are_refused(self) -> None:
        source = _clean_document()
        new_index = len(source.bones)
        cases = (
            PmxStructuralBoneInsertion(
                local_name="Parent",
                parent_bone_index=new_index,
            ),
            PmxStructuralBoneInsertion(
                local_name="Tail",
                tail_offset=None,
                tail_bone_index=new_index,
            ),
            PmxStructuralBoneInsertion(
                local_name="Inherit",
                inherit_rotation=True,
                inherit_parent_bone_index=new_index,
                inherit_weight=0.5,
            ),
            PmxStructuralBoneInsertion(
                local_name="IK target",
                ik=PmxStructuralBoneIk(new_index),
            ),
            PmxStructuralBoneInsertion(
                local_name="IK link",
                ik=PmxStructuralBoneIk(
                    0,
                    links=(PmxStructuralBoneIkLink(new_index),),
                ),
            ),
        )
        for insertion in cases:
            with self.subTest(name=insertion.local_name):
                with self.assertRaises(PmxServiceError):
                    services.preview_structural_edit(
                        source,
                        services.PmxStructuralPreviewRequest(
                            bone_insertions=(insertion,),
                        ),
                    )

    def test_optional_minus_one_bone_references_are_preserved(self) -> None:
        source = _clean_document()
        request = services.PmxStructuralPreviewRequest(
            bone_insertions=(
                PmxStructuralBoneInsertion(
                    local_name="Sentinels",
                    parent_bone_index=-1,
                    tail_offset=None,
                    tail_bone_index=-1,
                    inherit_rotation=True,
                    inherit_parent_bone_index=-1,
                    inherit_weight=0.5,
                ),
            ),
        )

        inserted = services.preview_structural_edit(source, request).document.bones[-1]
        self.assertEqual(inserted.parent_bone_index, -1)
        self.assertEqual(inserted.tail_bone_index, -1)
        self.assertEqual(inserted.inherit_parent_bone_index, -1)

    def test_float32_canonicalization_covers_bone_and_ik_numeric_payloads(self) -> None:
        source = _clean_document()
        insertion = PmxStructuralBoneInsertion(
            local_name="Float32",
            bone_position=(0.1, 0.2, 0.3),
            tail_offset=(0.1, 0.2, 0.3),
            inherit_rotation=True,
            inherit_parent_bone_index=0,
            inherit_weight=0.1,
            fixed_axis=(0.1, 0.2, 0.3),
            local_axis_x=(0.1, 0.2, 0.3),
            local_axis_z=(0.3, 0.2, 0.1),
            ik=PmxStructuralBoneIk(
                0,
                angle_limit=0.1,
                links=(
                    PmxStructuralBoneIkLink(
                        0,
                        lower_limit=(-0.1, -0.2, -0.3),
                        upper_limit=(0.1, 0.2, 0.3),
                    ),
                ),
            ),
        )

        inserted = services.preview_structural_edit(
            source,
            services.PmxStructuralPreviewRequest(bone_insertions=(insertion,)),
        ).document.bones[-1]
        expected = struct.unpack("<f", struct.pack("<f", 0.1))[0]

        self.assertEqual(inserted.position[0], expected)
        self.assertEqual(inserted.tail_offset[0], expected)
        self.assertEqual(inserted.inherit_weight, expected)
        self.assertEqual(inserted.fixed_axis[0], expected)
        self.assertEqual(inserted.local_axis_x[0], expected)
        self.assertIsNotNone(inserted.ik)
        assert inserted.ik is not None
        self.assertEqual(inserted.ik.angle_limit, expected)
        self.assertEqual(inserted.ik.links[0].upper_limit[0], expected)

    def test_unrepresentable_float32_fails_before_reference_shift_planner(self) -> None:
        source = _clean_document()
        payload = _bone_payload(
            bone_position=(1e300, 0.0, 0.0),
        )
        with patch(
            "mmd_registry.pmx.structural_bone_insertion."
            "plan_collection_reference_shift",
            side_effect=AssertionError("planner must not run"),
        ):
            with self.assertRaises(PmxStructuralBoneInsertionError):
                preview_pmx_bone_insertions(source, (payload,))

    def test_name_parser_bound_fails_before_planning(self) -> None:
        source = _clean_document()
        payload = _bone_payload("x" * (64 * 1024 + 1))
        with patch(
            "mmd_registry.pmx.structural_bone_insertion."
            "plan_collection_reference_shift",
            side_effect=AssertionError("planner must not run"),
        ):
            with self.assertRaises(PmxStructuralBoneInsertionError):
                preview_pmx_bone_insertions(source, (payload,))

    def test_reader_bone_count_limit_fails_before_planning(self) -> None:
        source = _clean_document()
        payload = _bone_payload()
        with patch(
            "mmd_registry.pmx.structural_bone_insertion.MAX_PMX_BONE_COUNT",
            len(source.bones),
        ), patch(
            "mmd_registry.pmx.structural_bone_insertion."
            "plan_collection_reference_shift",
            side_effect=AssertionError("planner must not run"),
        ):
            with self.assertRaises(PmxStructuralBoneInsertionError):
                preview_pmx_bone_insertions(source, (payload,))

    def test_per_bone_ik_loop_and_link_limits_fail_before_planning(self) -> None:
        source = _clean_document()
        over_loop = _bone_payload(
            ik=PmxBoneIkInsertionPayload(
                target_bone_index=0,
                loop_count=11,
                angle_limit=0.0,
                links=(),
            ),
        )
        link = PmxBoneIkLinkInsertionPayload(
            bone_index=0,
            lower_limit=None,
            upper_limit=None,
        )
        over_links = _bone_payload(
            ik=PmxBoneIkInsertionPayload(
                target_bone_index=0,
                loop_count=1,
                angle_limit=0.0,
                links=(link, link),
            ),
        )

        with patch(
            "mmd_registry.pmx.structural_bone_insertion.MAX_PMX_IK_LOOP_COUNT",
            10,
        ), patch(
            "mmd_registry.pmx.structural_bone_insertion."
            "plan_collection_reference_shift",
            side_effect=AssertionError("planner must not run"),
        ):
            with self.assertRaises(PmxStructuralBoneInsertionError):
                preview_pmx_bone_insertions(source, (over_loop,))

        with patch(
            "mmd_registry.pmx.structural_bone_insertion.MAX_PMX_IK_LINK_COUNT",
            1,
        ), patch(
            "mmd_registry.pmx.structural_bone_insertion."
            "plan_collection_reference_shift",
            side_effect=AssertionError("planner must not run"),
        ):
            with self.assertRaises(PmxStructuralBoneInsertionError):
                preview_pmx_bone_insertions(source, (over_links,))

    def test_cumulative_ik_link_limit_includes_existing_and_inserted_links(self) -> None:
        source = _clean_document()
        existing = sum(
            len(bone.ik.links) for bone in source.bones if bone.ik is not None
        )
        link = PmxBoneIkLinkInsertionPayload(
            bone_index=0,
            lower_limit=None,
            upper_limit=None,
        )
        payload = _bone_payload(
            ik=PmxBoneIkInsertionPayload(
                target_bone_index=0,
                loop_count=1,
                angle_limit=0.0,
                links=(link,),
            ),
        )
        with patch(
            "mmd_registry.pmx.structural_bone_insertion."
            "MAX_PMX_TOTAL_IK_LINK_COUNT",
            existing,
        ), patch(
            "mmd_registry.pmx.structural_bone_insertion."
            "plan_collection_reference_shift",
            side_effect=AssertionError("planner must not run"),
        ):
            with self.assertRaises(PmxStructuralBoneInsertionError):
                preview_pmx_bone_insertions(source, (payload,))

    def test_bone_index_width_capacity_refuses_expansion(self) -> None:
        source = _clean_document(index_size=1)
        constrained = replace(
            source,
            bones=tuple(
                source.bones[index % len(source.bones)]
                for index in range(128)
            ),
        )
        with self.assertRaises(PmxServiceError):
            services.preview_structural_edit(
                constrained,
                services.PmxStructuralPreviewRequest(
                    bone_insertions=(
                        PmxStructuralBoneInsertion(local_name="Overflow"),
                    ),
                ),
            )

    def test_internal_preview_rejects_wrong_container_and_payload_type(self) -> None:
        source = _clean_document()
        with self.assertRaises(TypeError):
            preview_pmx_bone_insertions(source, [_bone_payload()])  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            preview_pmx_bone_insertions(source, (object(),))  # type: ignore[arg-type]

    def test_preview_audit_is_deterministic_and_does_not_leak_names(self) -> None:
        source = _clean_document()
        secret_local = "private-cp11-bone-local"
        secret_universal = "private-cp11-bone-universal"
        request = services.PmxStructuralPreviewRequest(
            bone_insertions=(
                PmxStructuralBoneInsertion(
                    local_name=secret_local,
                    universal_name=secret_universal,
                ),
            ),
        )

        first = services.preview_structural_edit(source, request)
        second = services.preview_structural_edit(source, request)
        encoded = json.dumps(first.to_dict(), ensure_ascii=False, sort_keys=True)

        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertNotIn(secret_local, encoded)
        self.assertNotIn(secret_universal, encoded)
        payload = first.to_dict()["audit"]["bone_insertion"]["payloads"][0]
        self.assertEqual(len(payload["payload_sha256"]), 64)

    def test_preview_performs_no_filesystem_output(self) -> None:
        source = _clean_document()
        request = services.PmxStructuralPreviewRequest(
            bone_insertions=(PmxStructuralBoneInsertion(local_name="No IO"),),
        )
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "must-not-exist.pmx"
            result = services.preview_structural_edit(source, request)
            self.assertEqual(result.status, "changes_pending")
            self.assertFalse(marker.exists())

    def test_texture_material_and_legacy_preview_paths_still_work(self) -> None:
        source = _clean_document()
        legacy = services.preview_structural_edit(
            source,
            services.PmxStructuralPreviewRequest(),
        )
        self.assertEqual(legacy.status, "no_changes")

        from mmd_registry.services.structural_material import (
            PmxStructuralMaterialInsertion,
        )
        from mmd_registry.services.structural_texture import (
            PmxStructuralTextureInsertion,
        )

        texture = services.preview_structural_edit(
            source,
            services.PmxStructuralPreviewRequest(
                texture_insertions=(
                    PmxStructuralTextureInsertion("textures/cp11.png"),
                ),
            ),
        )
        material = services.preview_structural_edit(
            source,
            services.PmxStructuralPreviewRequest(
                material_insertions=(
                    PmxStructuralMaterialInsertion(local_name="CP11 regression"),
                ),
            ),
        )
        self.assertEqual(texture.document.texture_paths[-1], "textures/cp11.png")
        self.assertEqual(material.document.materials[-1].local_name, "CP11 regression")


if __name__ == "__main__":
    unittest.main()
