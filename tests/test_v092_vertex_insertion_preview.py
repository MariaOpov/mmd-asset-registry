"""CP15 contracts for preview-only semantic PMX vertex insertion."""

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
import mmd_registry.services.structural_vertex as structural_vertex_service
from mmd_registry.diagnostics import PmxServiceError
from mmd_registry.pmx.document import (
    PmxBdef1,
    PmxBdef2,
    PmxBdef4,
    PmxQdef,
    PmxSdef,
    PmxUvMorphOffset,
    PmxVertexMorphOffset,
)
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.services.structural_bone import PmxStructuralBoneInsertion
from mmd_registry.services.structural_vertex import (
    PmxStructuralVertexBdef1,
    PmxStructuralVertexBdef2,
    PmxStructuralVertexBdef4,
    PmxStructuralVertexInsertion,
    PmxStructuralVertexQdef,
    PmxStructuralVertexSdef,
)
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


def _f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


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


def _additional_uvs(count: int = 4):
    return tuple(
        (
            0.1 + index,
            0.2 + index,
            0.3 + index,
            0.4 + index,
        )
        for index in range(count)
    )


def _insertion(
    deform=None,
    *,
    vertex_position=(1.25, 2.5, 3.75),
    additional_uvs=None,
    edge_scale=1.0,
    position="append",
    source_index=None,
):
    if deform is None:
        deform = PmxStructuralVertexBdef1(0)
    if additional_uvs is None:
        additional_uvs = _additional_uvs()
    return PmxStructuralVertexInsertion(
        vertex_position=vertex_position,
        normal=(0.0, 1.0, 0.0),
        uv=(0.25, 0.75),
        additional_uvs=additional_uvs,
        deform=deform,
        edge_scale=edge_scale,
        position=position,
        source_index=source_index,
    )


def _request(insertion):
    return services.PmxStructuralPreviewRequest(vertex_insertions=(insertion,))


def _shift_required(index: int, anchor: int) -> int:
    return index + 1 if index >= anchor else index


class VertexInsertionPublicContractTests(unittest.TestCase):
    def test_public_surface_is_target_scoped_immutable_and_alias_is_preserved(self) -> None:
        deform = PmxStructuralVertexBdef1(0)
        insertion = _insertion(deform)
        request = _request(insertion)

        self.assertEqual(
            structural_vertex_service.__all__,
            (
                "PmxStructuralVertexBdef1",
                "PmxStructuralVertexBdef2",
                "PmxStructuralVertexBdef4",
                "PmxStructuralVertexSdef",
                "PmxStructuralVertexQdef",
                "PmxStructuralVertexInsertion",
            ),
        )
        self.assertFalse(hasattr(services, "PmxStructuralVertexInsertion"))
        self.assertFalse(hasattr(pmx_public, "PmxStructuralVertexInsertion"))
        self.assertIs(
            services.PmxStructuralEditRequest,
            services.PmxStructuralPreviewRequest,
        )
        self.assertEqual(request.vertex_insertions, (insertion,))
        self.assertEqual(hash(deform), hash(deform))
        self.assertEqual(hash(insertion), hash(insertion))
        self.assertEqual(hash(request), hash(request))
        with self.assertRaises(FrozenInstanceError):
            insertion.edge_scale = 2.0  # type: ignore[misc]

    def test_raw_vertex_payload_is_not_accepted(self) -> None:
        source = _clean_document()
        with self.assertRaises(TypeError):
            services.PmxStructuralPreviewRequest(
                vertex_insertions=(source.vertices[0],),  # type: ignore[arg-type]
            )

    def test_position_contract_is_source_domain(self) -> None:
        with self.assertRaises(ValueError):
            _insertion(position="append", source_index=0)
        with self.assertRaises(TypeError):
            _insertion(position="insert_before")
        with self.assertRaises(TypeError):
            _insertion(position="insert_before", source_index=True)
        with self.assertRaises(ValueError):
            _insertion(position="insert_before", source_index=-1)

    def test_public_additional_uv_shape_supports_zero_through_four_only(self) -> None:
        for count in range(5):
            with self.subTest(count=count):
                insertion = _insertion(additional_uvs=_additional_uvs(count))
                self.assertEqual(len(insertion.additional_uvs), count)
        with self.assertRaises(ValueError):
            _insertion(additional_uvs=_additional_uvs(5))

    def test_deform_dtos_reject_bad_shapes_but_do_not_normalize_weights(self) -> None:
        with self.assertRaises(ValueError):
            PmxStructuralVertexBdef1(-2)
        with self.assertRaises(ValueError):
            PmxStructuralVertexBdef2((0,), 0.5)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            PmxStructuralVertexBdef4((0, 0, 0, 0), [0.25] * 4)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            PmxStructuralVertexSdef(
                (0, 0),
                0.5,
                (0.0, 0.0, 0.0),
                (0.0, 0.0, 0.0),
                (0.0, 0.0),  # type: ignore[arg-type]
            )

        weights = (0.2, 0.2, 0.2, 0.2)
        deform = PmxStructuralVertexBdef4((0, 1, -1, 0), weights)
        self.assertEqual(deform.weights, weights)
        self.assertNotEqual(sum(deform.weights), 1.0)

    def test_request_refuses_mixed_target_and_legacy_vocabularies(self) -> None:
        vertex = _insertion()
        bone = PmxStructuralBoneInsertion(local_name="B")
        with self.assertRaisesRegex(ValueError, "cannot be combined"):
            services.PmxStructuralPreviewRequest(
                vertex_insertions=(vertex,),
                bone_insertions=(bone,),
            )

        edit = services.PmxStructuralCollectionEdit(
            services.PmxReferenceTargetKind.VERTEX,
            (),
        )
        with self.assertRaisesRegex(ValueError, "cannot be combined"):
            services.PmxStructuralPreviewRequest(
                collection_edits=(edit,),
                vertex_insertions=(vertex,),
            )

    def test_capability_manifest_is_not_promoted(self) -> None:
        payload = services.get_capabilities().to_dict()
        self.assertNotIn("structural_insert", payload)
        self.assertNotIn("PmxStructuralVertexInsertion", json.dumps(payload))


class VertexInsertionPreviewTests(unittest.TestCase):
    def test_append_preview_adds_vertex_and_preserves_existing_incoming_owners(self) -> None:
        source = _clean_document()
        result = services.preview_structural_edit(source, _request(_insertion()))
        output = result.document

        self.assertEqual(len(output.vertices), len(source.vertices) + 1)
        self.assertEqual(output.vertices[:-1], source.vertices)
        self.assertEqual(output.surface_indices, source.surface_indices)
        self.assertEqual(output.morphs, source.morphs)
        self.assertEqual(output.soft_bodies, source.soft_bodies)
        self.assertEqual(output.materials, source.materials)
        self.assertEqual(source, _clean_document())

        report = result.to_dict()
        self.assertEqual(report["intent"]["changed_kinds"], ["vertex"])
        self.assertEqual(report["intent"]["insert_count"], 1)
        self.assertFalse(report["output"]["written"])
        self.assertEqual(report["verification"]["serialization"], "not_performed")

    def test_insert_before_zero_shifts_every_existing_incoming_vertex_owner(self) -> None:
        source = _clean_document(version=2.1)
        result = services.preview_structural_edit(
            source,
            _request(_insertion(position="insert_before", source_index=0)),
        )
        output = result.document

        self.assertEqual(
            output.surface_indices,
            tuple(index + 1 for index in source.surface_indices),
        )
        self.assertEqual(
            tuple(material.surface_index_count for material in output.materials),
            tuple(material.surface_index_count for material in source.materials),
        )
        self.assertEqual(len(output.surface_indices), len(source.surface_indices))

        vertex_owned_morph_offsets = 0
        for source_morph, output_morph in zip(
            source.morphs,
            output.morphs,
            strict=True,
        ):
            for source_offset, output_offset in zip(
                source_morph.offsets,
                output_morph.offsets,
                strict=True,
            ):
                if isinstance(source_offset, (PmxVertexMorphOffset, PmxUvMorphOffset)):
                    vertex_owned_morph_offsets += 1
                    self.assertEqual(
                        output_offset.vertex_index,
                        source_offset.vertex_index + 1,
                    )
                else:
                    self.assertEqual(output_offset, source_offset)
        self.assertGreater(vertex_owned_morph_offsets, 0)

        self.assertTrue(source.soft_bodies)
        for source_body, output_body in zip(
            source.soft_bodies,
            output.soft_bodies,
            strict=True,
        ):
            self.assertEqual(output_body.material_index, source_body.material_index)
            for source_anchor, output_anchor in zip(
                source_body.anchors,
                output_body.anchors,
                strict=True,
            ):
                self.assertEqual(
                    output_anchor.rigid_body_index,
                    source_anchor.rigid_body_index,
                )
                self.assertEqual(
                    output_anchor.vertex_index,
                    source_anchor.vertex_index + 1,
                )
            self.assertEqual(
                output_body.pinned_vertex_indices,
                tuple(index + 1 for index in source_body.pinned_vertex_indices),
            )

    def test_same_anchor_and_append_order_are_deterministic(self) -> None:
        source = _clean_document()
        first = _insertion(
            vertex_position=(10.0, 0.0, 0.0),
            position="insert_before",
            source_index=1,
        )
        second = _insertion(
            vertex_position=(20.0, 0.0, 0.0),
            position="insert_before",
            source_index=1,
        )
        third = _insertion(vertex_position=(30.0, 0.0, 0.0))
        request = services.PmxStructuralPreviewRequest(
            vertex_insertions=(first, second, third),
        )

        a = services.preview_structural_edit(source, request)
        b = services.preview_structural_edit(source, request)
        self.assertEqual(a.document, b.document)
        self.assertEqual(a.to_dict(), b.to_dict())
        self.assertEqual(a.document.vertices[1].position, (10.0, 0.0, 0.0))
        self.assertEqual(a.document.vertices[2].position, (20.0, 0.0, 0.0))
        self.assertEqual(a.document.vertices[-1].position, (30.0, 0.0, 0.0))

    def test_all_frozen_deform_types_materialize_without_weight_normalization(self) -> None:
        source = _clean_document(version=2.1)
        deforms = (
            PmxStructuralVertexBdef1(-1),
            PmxStructuralVertexBdef2((0, 1), 0.3),
            PmxStructuralVertexBdef4((0, 1, -1, 0), (0.2, 0.2, 0.2, 0.2)),
            PmxStructuralVertexSdef(
                (0, 1),
                0.4,
                (0.1, 0.2, 0.3),
                (0.4, 0.5, 0.6),
                (0.7, 0.8, 0.9),
            ),
            PmxStructuralVertexQdef((0, 1, -1, 0), (0.1, 0.2, 0.3, 0.1)),
        )
        expected_types = (PmxBdef1, PmxBdef2, PmxBdef4, PmxSdef, PmxQdef)

        for deform, expected_type in zip(deforms, expected_types, strict=True):
            with self.subTest(deform=type(deform).__name__):
                result = services.preview_structural_edit(
                    source,
                    _request(_insertion(deform)),
                )
                output_deform = result.document.vertices[-1].deform
                self.assertIsInstance(output_deform, expected_type)

        bdef4 = services.preview_structural_edit(
            source,
            _request(_insertion(deforms[2])),
        ).document.vertices[-1].deform
        assert isinstance(bdef4, PmxBdef4)
        self.assertEqual(bdef4.weights, tuple(_f32(0.2) for _ in range(4)))
        self.assertNotEqual(sum(bdef4.weights), 1.0)

    def test_qdef_is_refused_on_pmx20(self) -> None:
        source = _clean_document(version=2.0)
        insertion = _insertion(
            PmxStructuralVertexQdef((0, 1, -1, 0), (0.25, 0.25, 0.25, 0.25))
        )
        with self.assertRaises(PmxServiceError):
            services.preview_structural_edit(source, _request(insertion))

    def test_source_bone_domain_is_validated_and_sentinel_is_preserved(self) -> None:
        source = _clean_document()
        sentinel = services.preview_structural_edit(
            source,
            _request(_insertion(PmxStructuralVertexBdef1(-1))),
        ).document.vertices[-1]
        self.assertIsInstance(sentinel.deform, PmxBdef1)
        self.assertEqual(sentinel.deform.bone_index, -1)

        invalid = _insertion(PmxStructuralVertexBdef1(len(source.bones)))
        with self.assertRaises(PmxServiceError):
            services.preview_structural_edit(source, _request(invalid))

    def test_additional_uv_count_must_exactly_match_source_header(self) -> None:
        source = _clean_document()
        self.assertEqual(source.header.additional_uv_count, 4)
        with self.assertRaises(PmxServiceError):
            services.preview_structural_edit(
                source,
                _request(_insertion(additional_uvs=_additional_uvs(3))),
            )

    def test_all_vertex_float_fields_are_canonicalized_before_certificate(self) -> None:
        source = _clean_document()
        insertion = PmxStructuralVertexInsertion(
            vertex_position=(0.1, 0.2, 0.3),
            normal=(0.4, 0.5, 0.6),
            uv=(0.7, 0.8),
            additional_uvs=tuple(
                (0.1, 0.2, 0.3, 0.4) for _ in range(4)
            ),
            deform=PmxStructuralVertexSdef(
                (0, 1),
                0.3,
                (0.1, 0.2, 0.3),
                (0.4, 0.5, 0.6),
                (0.7, 0.8, 0.9),
            ),
            edge_scale=0.9,
        )
        vertex = services.preview_structural_edit(
            source,
            _request(insertion),
        ).document.vertices[-1]

        self.assertEqual(vertex.position, tuple(_f32(v) for v in insertion.vertex_position))
        self.assertEqual(vertex.normal, tuple(_f32(v) for v in insertion.normal))
        self.assertEqual(vertex.uv, tuple(_f32(v) for v in insertion.uv))
        self.assertEqual(
            vertex.additional_uvs,
            tuple(tuple(_f32(v) for v in uv) for uv in insertion.additional_uvs),
        )
        self.assertEqual(vertex.edge_scale, _f32(insertion.edge_scale))
        assert isinstance(vertex.deform, PmxSdef)
        self.assertEqual(vertex.deform.bone_1_weight, _f32(0.3))
        self.assertEqual(vertex.deform.c, tuple(_f32(v) for v in (0.1, 0.2, 0.3)))

    def test_nonfinite_is_rejected_at_dto_and_float32_overflow_fails_preview(self) -> None:
        with self.assertRaises(ValueError):
            _insertion(edge_scale=math.nan)
        source = _clean_document()
        overflow = _insertion(edge_scale=1.0e100)
        with self.assertRaises(PmxServiceError):
            services.preview_structural_edit(source, _request(overflow))

    def test_unsigned_one_byte_vertex_capacity_boundary_is_exact(self) -> None:
        source = _clean_document(index_size=1)
        repeated = source.vertices[0]
        source_255 = replace(
            source,
            geometry=replace(source.geometry, vertices=(repeated,) * 255),
        )
        accepted = services.preview_structural_edit(
            source_255,
            _request(_insertion()),
        )
        self.assertEqual(len(accepted.document.vertices), 256)

        source_256 = replace(
            source,
            geometry=replace(source.geometry, vertices=(repeated,) * 256),
        )
        with self.assertRaises(PmxServiceError):
            services.preview_structural_edit(source_256, _request(_insertion()))

    def test_reader_safety_limit_fails_before_materialization(self) -> None:
        source = _clean_document()
        with patch(
            "mmd_registry.pmx.structural_vertex_insertion.MAX_PMX_VERTEX_COUNT",
            len(source.vertices),
        ):
            with self.assertRaises(PmxServiceError):
                services.preview_structural_edit(source, _request(_insertion()))

    def test_preview_matrix_covers_versions_and_vertex_index_widths(self) -> None:
        for version in (2.0, 2.1):
            for index_size in (1, 2, 4):
                with self.subTest(version=version, index_size=index_size):
                    source = _clean_document(version=version, index_size=index_size)
                    result = services.preview_structural_edit(
                        source,
                        _request(_insertion(PmxStructuralVertexBdef1(0))),
                    )
                    self.assertEqual(len(result.document.vertices), len(source.vertices) + 1)
                    self.assertEqual(
                        result.document.header.index_sizes.vertex,
                        source.header.index_sizes.vertex,
                    )

    def test_pmx20_has_no_soft_body_but_surface_and_morph_shifts_still_apply(self) -> None:
        source = _clean_document(version=2.0)
        self.assertFalse(source.soft_bodies)
        output = services.preview_structural_edit(
            source,
            _request(_insertion(position="insert_before", source_index=0)),
        ).document
        self.assertFalse(output.soft_bodies)
        self.assertEqual(
            output.surface_indices,
            tuple(index + 1 for index in source.surface_indices),
        )

    def test_cp15_apply_refuses_vertex_execution_without_creating_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.pmx"
            output_path = root / "output.pmx"
            source_path.write_bytes(build_pmx_roundtrip_fixture(version=2.1))
            request = _request(_insertion())

            with self.assertRaises(PmxServiceError):
                services.apply_structural_edit(
                    source_path,
                    output_path,
                    request,
                )
            self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()
