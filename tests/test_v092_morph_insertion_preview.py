"""CP13 semantic morph insertion preview safety and reference coverage."""

from __future__ import annotations

import io
import json
import struct
import unittest
from dataclasses import replace
from unittest.mock import patch

import mmd_registry.pmx as pmx_public
import mmd_registry.services as services
from mmd_registry.diagnostics import PmxServiceError
from mmd_registry.pmx.document import (
    PmxFlipMorphOffset,
    PmxGroupMorphOffset,
)
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx import structural_morph_insertion as morph_insertion_module
from mmd_registry.services.structural_bone import PmxStructuralBoneInsertion
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


def _material_offset(material_index: int = -1, value: float = 0.1):
    return PmxStructuralMorphMaterialOffset(
        material_index=material_index,
        operation="add",
        diffuse=(value, value, value, value),
        specular=(value, value, value),
        specular_strength=value,
        ambient=(value, value, value),
        edge_color=(value, value, value, value),
        edge_scale=value,
        texture_tint=(value, value, value, value),
        sphere_tint=(value, value, value, value),
        toon_tint=(value, value, value, value),
    )


def _assert_bounded_preview_failure(
    testcase: unittest.TestCase,
    error: PmxServiceError,
) -> None:
    # Frozen service boundary deliberately redacts internal validation reasons.
    testcase.assertEqual(
        error.to_dict()["code"],
        "structural_preview_failed",
    )
    testcase.assertEqual(
        str(error),
        "Structural preview failed reference-safety validation.",
    )


def _vertex_insertion(
    name: str = "CP13 vertex",
    *,
    position: str = "append",
    source_index: int | None = None,
    value: float = 0.1,
):
    return PmxStructuralMorphInsertion(
        local_name=name,
        morph_type="vertex",
        panel="other",
        offsets=(
            PmxStructuralMorphVertexOffset(
                vertex_index=0,
                translation=(value, value, value),
            ),
        ),
        position=position,
        source_index=source_index,
    )


class MorphInsertionPreviewTests(unittest.TestCase):
    def test_public_boundary_uses_semantic_submodule_without_root_dto_promotion(
        self,
    ) -> None:
        self.assertFalse(hasattr(services, "PmxStructuralMorphInsertion"))
        self.assertFalse(hasattr(pmx_public, "PmxStructuralMorphInsertion"))
        self.assertNotIn("structural_insert", services.get_capabilities().to_dict())

        impulse = PmxStructuralMorphInsertion(
            local_name="impulse-is-cp14",
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
        self.assertEqual(impulse.morph_type, "impulse")

    def test_append_preview_is_certified_private_and_source_is_immutable(self) -> None:
        source = _clean_document()
        before = source.morphs
        request = services.PmxStructuralPreviewRequest(
            morph_insertions=(_vertex_insertion("private-cp13-morph-name"),),
        )

        result = services.preview_structural_edit(source, request)

        self.assertEqual(result.status, "changes_pending")
        self.assertEqual(len(result.document.morphs), len(source.morphs) + 1)
        self.assertEqual(result.document.morphs[-1].morph_type, 1)
        self.assertEqual(result.document.morphs[-1].morph_type_name, "vertex")
        self.assertEqual(result.document.morphs[-1].panel_name, "other")
        self.assertEqual(source.morphs, before)

        report = result.to_dict()
        self.assertTrue(report["dry_run"])
        self.assertFalse(report["output"]["written"])
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("private-cp13-morph-name", encoded)

    def test_insert_before_maps_new_group_reference_from_source_domain(self) -> None:
        source = _clean_document()
        self.assertTrue(source.morphs)
        request = services.PmxStructuralPreviewRequest(
            morph_insertions=(
                PmxStructuralMorphInsertion(
                    local_name="Group",
                    morph_type="group",
                    offsets=(
                        PmxStructuralMorphGroupOffset(
                            morph_index=0,
                            weight=0.5,
                        ),
                    ),
                    position="insert_before",
                    source_index=0,
                ),
            ),
        )

        result = services.preview_structural_edit(source, request)
        inserted = result.document.morphs[0]

        self.assertEqual(inserted.morph_type, 0)
        self.assertIsInstance(inserted.offsets[0], PmxGroupMorphOffset)
        self.assertEqual(inserted.offsets[0].morph_index, 1)

    def test_existing_group_flip_and_display_morph_targets_shift(self) -> None:
        source = _clean_document(version=2.1)
        request = services.PmxStructuralPreviewRequest(
            morph_insertions=(
                _vertex_insertion(
                    "insert first",
                    position="insert_before",
                    source_index=0,
                ),
            ),
        )
        result = services.preview_structural_edit(source, request).document

        for old_index, morph in enumerate(source.morphs):
            rewritten = result.morphs[old_index + 1]
            if morph.morph_type not in (0, 9):
                continue
            for old_offset, new_offset in zip(
                morph.offsets,
                rewritten.offsets,
                strict=True,
            ):
                if isinstance(old_offset, (PmxGroupMorphOffset, PmxFlipMorphOffset)):
                    self.assertEqual(
                        new_offset.morph_index,
                        old_offset.morph_index + 1,
                    )

        for old_frame, new_frame in zip(
            source.display_frames,
            result.display_frames,
            strict=True,
        ):
            for old_element, new_element in zip(
                old_frame.elements,
                new_frame.elements,
                strict=True,
            ):
                if old_element.target_type == "morph":
                    self.assertEqual(
                        new_element.target_index,
                        old_element.target_index + 1,
                    )
                else:
                    self.assertEqual(new_element, old_element)

    def test_same_anchor_and_append_order_is_request_stable(self) -> None:
        source = _clean_document()
        request = services.PmxStructuralPreviewRequest(
            morph_insertions=(
                _vertex_insertion(
                    "First",
                    position="insert_before",
                    source_index=0,
                ),
                _vertex_insertion(
                    "Second",
                    position="insert_before",
                    source_index=0,
                ),
                _vertex_insertion("Append"),
            ),
        )
        result = services.preview_structural_edit(source, request).document

        self.assertEqual(
            tuple(morph.local_name for morph in result.morphs[:2]),
            ("First", "Second"),
        )
        self.assertEqual(result.morphs[-1].local_name, "Append")

    def test_types_zero_through_eight_materialize_exact_semantic_offsets(self) -> None:
        source = _clean_document(version=2.1)
        self.assertTrue(source.vertices)
        self.assertTrue(source.bones)
        self.assertTrue(source.materials)
        self.assertTrue(source.morphs)

        insertions = (
            PmxStructuralMorphInsertion(
                "group",
                "group",
                offsets=(PmxStructuralMorphGroupOffset(0, 0.1),),
            ),
            _vertex_insertion("vertex"),
            PmxStructuralMorphInsertion(
                "bone",
                "bone",
                offsets=(
                    PmxStructuralMorphBoneOffset(
                        bone_index=0,
                        translation=(0.1, 0.2, 0.3),
                        rotation=(0.0, 0.0, 0.0, 1.0),
                    ),
                ),
            ),
            PmxStructuralMorphInsertion(
                "uv",
                "uv",
                offsets=(
                    PmxStructuralMorphUvOffset(
                        vertex_index=0,
                        uv_offset=(0.1, 0.2, 0.3, 0.4),
                    ),
                ),
            ),
            PmxStructuralMorphInsertion(
                "auv1",
                "additional_uv_1",
                offsets=(
                    PmxStructuralMorphUvOffset(
                        vertex_index=0,
                        uv_offset=(0.1, 0.2, 0.3, 0.4),
                    ),
                ),
            ),
            PmxStructuralMorphInsertion(
                "auv2",
                "additional_uv_2",
                offsets=(
                    PmxStructuralMorphUvOffset(
                        vertex_index=0,
                        uv_offset=(0.1, 0.2, 0.3, 0.4),
                    ),
                ),
            ),
            PmxStructuralMorphInsertion(
                "auv3",
                "additional_uv_3",
                offsets=(
                    PmxStructuralMorphUvOffset(
                        vertex_index=0,
                        uv_offset=(0.1, 0.2, 0.3, 0.4),
                    ),
                ),
            ),
            PmxStructuralMorphInsertion(
                "auv4",
                "additional_uv_4",
                offsets=(
                    PmxStructuralMorphUvOffset(
                        vertex_index=0,
                        uv_offset=(0.1, 0.2, 0.3, 0.4),
                    ),
                ),
            ),
            PmxStructuralMorphInsertion(
                "material",
                "material",
                offsets=(_material_offset(0),),
            ),
        )
        result = services.preview_structural_edit(
            source,
            services.PmxStructuralPreviewRequest(morph_insertions=insertions),
        ).document
        appended = result.morphs[-len(insertions):]

        self.assertEqual(
            tuple(morph.morph_type for morph in appended),
            tuple(range(9)),
        )
        self.assertEqual(
            tuple(morph.morph_type_name for morph in appended),
            (
                "group",
                "vertex",
                "bone",
                "uv",
                "additional_uv_1",
                "additional_uv_2",
                "additional_uv_3",
                "additional_uv_4",
                "material",
            ),
        )

    def test_flip_is_pmx21_only(self) -> None:
        source = _clean_document(version=2.0)
        request = services.PmxStructuralPreviewRequest(
            morph_insertions=(
                PmxStructuralMorphInsertion(
                    "flip",
                    "flip",
                    offsets=(PmxStructuralMorphFlipOffset(0, 0.5),),
                ),
            ),
        )

        with self.assertRaises(PmxServiceError) as raised:
            services.preview_structural_edit(source, request)

        _assert_bounded_preview_failure(self, raised.exception)

    def test_additional_uv_layer_requirement_fails_closed(self) -> None:
        source = _clean_document(version=2.1)
        source = replace(
            source,
            header=replace(source.header, additional_uv_count=0),
        )
        request = services.PmxStructuralPreviewRequest(
            morph_insertions=(
                PmxStructuralMorphInsertion(
                    "auv4",
                    "additional_uv_4",
                    offsets=(
                        PmxStructuralMorphUvOffset(
                            0,
                            (0.1, 0.2, 0.3, 0.4),
                        ),
                    ),
                ),
            ),
        )

        with self.assertRaises(PmxServiceError) as raised:
            services.preview_structural_edit(source, request)

        _assert_bounded_preview_failure(self, raised.exception)

    def test_material_minus_one_sentinel_is_preserved(self) -> None:
        source = _clean_document()
        request = services.PmxStructuralPreviewRequest(
            morph_insertions=(
                PmxStructuralMorphInsertion(
                    "all-materials",
                    "material",
                    offsets=(_material_offset(-1),),
                ),
            ),
        )

        inserted = services.preview_structural_edit(source, request).document.morphs[-1]
        self.assertEqual(inserted.offsets[0].material_index, -1)

    def test_required_source_reference_domains_are_enforced(self) -> None:
        source = _clean_document()
        cases = (
            PmxStructuralMorphInsertion(
                "bad morph",
                "group",
                offsets=(
                    PmxStructuralMorphGroupOffset(
                        len(source.morphs),
                        0.5,
                    ),
                ),
            ),
            PmxStructuralMorphInsertion(
                "bad vertex",
                "vertex",
                offsets=(
                    PmxStructuralMorphVertexOffset(
                        len(source.vertices),
                        (0.0, 0.0, 0.0),
                    ),
                ),
            ),
            PmxStructuralMorphInsertion(
                "bad bone",
                "bone",
                offsets=(
                    PmxStructuralMorphBoneOffset(
                        len(source.bones),
                        (0.0, 0.0, 0.0),
                        (0.0, 0.0, 0.0, 1.0),
                    ),
                ),
            ),
            PmxStructuralMorphInsertion(
                "bad material",
                "material",
                offsets=(_material_offset(len(source.materials)),),
            ),
        )
        for insertion in cases:
            with self.subTest(morph_type=insertion.morph_type):
                with self.assertRaises(PmxServiceError):
                    services.preview_structural_edit(
                        source,
                        services.PmxStructuralPreviewRequest(
                            morph_insertions=(insertion,),
                        ),
                    )

    def test_new_to_new_morph_reference_is_refused(self) -> None:
        source = _clean_document()
        request = services.PmxStructuralPreviewRequest(
            morph_insertions=(
                _vertex_insertion("new target"),
                PmxStructuralMorphInsertion(
                    "new referrer",
                    "group",
                    offsets=(
                        PmxStructuralMorphGroupOffset(
                            len(source.morphs),
                            0.5,
                        ),
                    ),
                ),
            ),
        )

        with self.assertRaises(PmxServiceError) as raised:
            services.preview_structural_edit(source, request)

        _assert_bounded_preview_failure(self, raised.exception)

    def test_float32_canonicalization_is_exact_for_all_cp13_numeric_shapes(self) -> None:
        source = _clean_document(version=2.1)
        value = 0.1
        expected = struct.unpack("<f", struct.pack("<f", value))[0]
        insertions = (
            PmxStructuralMorphInsertion(
                "group",
                "group",
                offsets=(PmxStructuralMorphGroupOffset(0, value),),
            ),
            _vertex_insertion("vertex", value=value),
            PmxStructuralMorphInsertion(
                "bone",
                "bone",
                offsets=(
                    PmxStructuralMorphBoneOffset(
                        0,
                        (value, value, value),
                        (value, value, value, value),
                    ),
                ),
            ),
            PmxStructuralMorphInsertion(
                "uv",
                "uv",
                offsets=(
                    PmxStructuralMorphUvOffset(
                        0,
                        (value, value, value, value),
                    ),
                ),
            ),
            PmxStructuralMorphInsertion(
                "material",
                "material",
                offsets=(_material_offset(-1, value),),
            ),
            PmxStructuralMorphInsertion(
                "flip",
                "flip",
                offsets=(PmxStructuralMorphFlipOffset(0, value),),
            ),
        )

        result = services.preview_structural_edit(
            source,
            services.PmxStructuralPreviewRequest(morph_insertions=insertions),
        ).document
        appended = result.morphs[-len(insertions):]

        self.assertEqual(appended[0].offsets[0].weight, expected)
        self.assertEqual(appended[1].offsets[0].translation[0], expected)
        self.assertEqual(appended[2].offsets[0].translation[0], expected)
        self.assertEqual(appended[2].offsets[0].rotation[0], expected)
        self.assertEqual(appended[3].offsets[0].uv_offset[0], expected)
        self.assertEqual(appended[4].offsets[0].diffuse[0], expected)
        self.assertEqual(appended[4].offsets[0].specular_strength, expected)
        self.assertEqual(appended[5].offsets[0].weight, expected)

    def test_unrepresentable_float32_fails_before_reference_shift_planner(self) -> None:
        source = _clean_document()
        request = services.PmxStructuralPreviewRequest(
            morph_insertions=(
                _vertex_insertion("too-large", value=1e39),
            ),
        )

        with patch.object(
            morph_insertion_module,
            "plan_collection_reference_shift",
        ) as planner:
            with self.assertRaises(PmxServiceError) as raised:
                services.preview_structural_edit(source, request)

        planner.assert_not_called()
        _assert_bounded_preview_failure(self, raised.exception)

    def test_parser_morph_count_limit_fails_before_reference_shift_planner(
        self,
    ) -> None:
        source = _clean_document()
        request = services.PmxStructuralPreviewRequest(
            morph_insertions=(_vertex_insertion(),),
        )

        with (
            patch.object(
                morph_insertion_module,
                "MAX_PMX_MORPH_COUNT",
                len(source.morphs),
            ),
            patch.object(
                morph_insertion_module,
                "plan_collection_reference_shift",
            ) as planner,
        ):
            with self.assertRaises(PmxServiceError) as raised:
                services.preview_structural_edit(source, request)

        planner.assert_not_called()
        _assert_bounded_preview_failure(self, raised.exception)

    def test_per_morph_offset_limit_fails_before_reference_shift_planner(
        self,
    ) -> None:
        source = _clean_document()
        request = services.PmxStructuralPreviewRequest(
            morph_insertions=(_vertex_insertion(),),
        )

        with (
            patch.object(
                morph_insertion_module,
                "MAX_PMX_MORPH_OFFSET_COUNT",
                0,
            ),
            patch.object(
                morph_insertion_module,
                "plan_collection_reference_shift",
            ) as planner,
        ):
            with self.assertRaises(PmxServiceError) as raised:
                services.preview_structural_edit(source, request)

        planner.assert_not_called()
        _assert_bounded_preview_failure(self, raised.exception)

    def test_total_offset_limit_fails_before_reference_shift_planner(self) -> None:
        source = _clean_document()
        current_total = sum(len(morph.offsets) for morph in source.morphs)
        request = services.PmxStructuralPreviewRequest(
            morph_insertions=(_vertex_insertion(),),
        )

        with (
            patch.object(
                morph_insertion_module,
                "MAX_PMX_TOTAL_MORPH_OFFSET_COUNT",
                current_total,
            ),
            patch.object(
                morph_insertion_module,
                "plan_collection_reference_shift",
            ) as planner,
        ):
            with self.assertRaises(PmxServiceError) as raised:
                services.preview_structural_edit(source, request)

        planner.assert_not_called()
        _assert_bounded_preview_failure(self, raised.exception)

    def test_current_morph_index_width_expansion_is_refused(self) -> None:
        source = _clean_document(index_size=1)
        template = next(morph for morph in source.morphs if morph.morph_type == 1)
        constrained = replace(
            source,
            morphs=tuple(
                replace(template, local_name=f"Morph {index}")
                for index in range(128)
            ),
        )

        with self.assertRaises(PmxServiceError) as raised:
            services.preview_structural_edit(
                constrained,
                services.PmxStructuralPreviewRequest(
                    morph_insertions=(_vertex_insertion(),),
                ),
            )

        _assert_bounded_preview_failure(self, raised.exception)

    def test_preview_matrix_covers_versions_encodings_and_morph_index_widths(self) -> None:
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
                                morph_insertions=(
                                    _vertex_insertion("互換 CP13"),
                                ),
                            ),
                        )
                        self.assertEqual(
                            len(result.document.morphs),
                            len(source.morphs) + 1,
                        )
                        self.assertEqual(
                            result.document.header,
                            source.header,
                        )

    def test_morph_insertion_can_mix_with_other_structural_targets(self) -> None:
        insertion = _vertex_insertion()
        request = services.PmxStructuralPreviewRequest(
            morph_insertions=(insertion,),
            bone_insertions=(
                PmxStructuralBoneInsertion(local_name="mixed"),
            ),
        )
        self.assertEqual(request.morph_insertions, (insertion,))
        self.assertEqual(len(request.bone_insertions), 1)

    def test_preview_is_deterministic(self) -> None:
        source = _clean_document()
        request = services.PmxStructuralPreviewRequest(
            morph_insertions=(
                _vertex_insertion("A"),
                _vertex_insertion("B"),
            ),
        )

        first = services.preview_structural_edit(source, request)
        second = services.preview_structural_edit(source, request)

        self.assertEqual(first.document, second.document)
        self.assertEqual(first.to_dict(), second.to_dict())


if __name__ == "__main__":
    unittest.main()
