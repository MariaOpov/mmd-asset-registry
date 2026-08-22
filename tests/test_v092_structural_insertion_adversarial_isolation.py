"""CP21 v0.9.2 adversarial capacity and state-isolation gates."""

from __future__ import annotations

import io
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import mmd_registry.services as services
from mmd_registry.diagnostics import PmxServiceError
from mmd_registry.pmx.document import PmxMaterialMorphOffset
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.pmx.structural_capacity import analyze_structural_capacity
from mmd_registry.pmx.writer import serialize_pmx
from mmd_registry.services.structural_bone import PmxStructuralBoneInsertion
from mmd_registry.services.structural_material import PmxStructuralMaterialInsertion
from mmd_registry.services.structural_reference import PmxStructuralNewReference
from mmd_registry.services.structural_texture import PmxStructuralTextureInsertion
from mmd_registry.services.structural_vertex import (
    PmxStructuralVertexBdef1,
    PmxStructuralVertexBdef2,
    PmxStructuralVertexInsertion,
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


def _source_bytes(**kwargs) -> bytes:
    return serialize_pmx(_clean_document(**kwargs))


def _vertex(deform, *, additional_uv_count: int = 4):
    return PmxStructuralVertexInsertion(
        vertex_position=(1.0, 2.0, 3.0),
        normal=(0.0, 1.0, 0.0),
        uv=(0.25, 0.75),
        additional_uvs=tuple(
            (float(index), 0.2, 0.3, 0.4)
            for index in range(additional_uv_count)
        ),
        deform=deform,
        edge_scale=1.0,
    )


def _good_coordinated_request():
    return services.PmxStructuralEditRequest(
        bone_insertions=(
            PmxStructuralBoneInsertion(
                local_name="CP21 new bone",
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


def _unknown_reference_request():
    return services.PmxStructuralEditRequest(
        bone_insertions=(
            PmxStructuralBoneInsertion(
                local_name="Known",
                new_id="known",
            ),
        ),
        vertex_insertions=(
            _vertex(
                PmxStructuralVertexBdef1(
                    PmxStructuralNewReference("bone", "missing")
                )
            ),
        ),
    )


def _temporary_outputs(destination: Path) -> tuple[Path, ...]:
    return tuple(destination.parent.glob(f".{destination.name}.*.tmp"))


def _clear_incoming_material_references(document):
    morphs = []
    for morph in document.morphs:
        if morph.morph_type != 8:
            morphs.append(morph)
            continue
        offsets = tuple(
            replace(offset, material_index=-1)
            if isinstance(offset, PmxMaterialMorphOffset)
            else offset
            for offset in morph.offsets
        )
        morphs.append(
            morph if offsets == morph.offsets else replace(morph, offsets=offsets)
        )

    soft_bodies = tuple(
        replace(body, material_index=-1)
        for body in document.soft_bodies
    )
    return replace(document, morphs=tuple(morphs), soft_bodies=soft_bodies)


class StructuralInsertionAdversarialIsolationTests(unittest.TestCase):
    def test_capacity_math_covers_signed_unsigned_two_and_four_byte_edges(self) -> None:
        signed_ok = analyze_structural_capacity(
            PmxReferenceTargetKind.BONE,
            current_count=32767,
            insert_count=1,
            index_width=2,
        )
        signed_over = analyze_structural_capacity(
            PmxReferenceTargetKind.BONE,
            current_count=32768,
            insert_count=1,
            index_width=2,
        )
        self.assertEqual(signed_ok.result_count, 32768)
        self.assertTrue(signed_ok.representable)
        self.assertFalse(signed_ok.expansion_required)
        self.assertEqual(signed_ok.maximum_addressable_index, 32767)
        self.assertFalse(signed_over.representable)
        self.assertTrue(signed_over.expansion_required)

        unsigned_ok = analyze_structural_capacity(
            PmxReferenceTargetKind.VERTEX,
            current_count=65535,
            insert_count=1,
            index_width=2,
        )
        unsigned_over = analyze_structural_capacity(
            PmxReferenceTargetKind.VERTEX,
            current_count=65536,
            insert_count=1,
            index_width=2,
        )
        self.assertEqual(unsigned_ok.result_count, 65536)
        self.assertTrue(unsigned_ok.representable)
        self.assertEqual(unsigned_ok.maximum_addressable_index, 65535)
        self.assertFalse(unsigned_over.representable)
        self.assertTrue(unsigned_over.expansion_required)

        signed_4_ok = analyze_structural_capacity(
            PmxReferenceTargetKind.MATERIAL,
            current_count=(1 << 31) - 2,
            insert_count=1,
            index_width=4,
        )
        signed_4_count_over = analyze_structural_capacity(
            PmxReferenceTargetKind.MATERIAL,
            current_count=(1 << 31) - 1,
            insert_count=1,
            index_width=4,
        )
        vertex_4_count_over = analyze_structural_capacity(
            PmxReferenceTargetKind.VERTEX,
            current_count=(1 << 31) - 1,
            insert_count=1,
            index_width=4,
        )
        self.assertTrue(signed_4_ok.representable)
        self.assertFalse(signed_4_count_over.representable)
        self.assertFalse(signed_4_count_over.expansion_required)
        self.assertFalse(vertex_4_count_over.representable)
        self.assertFalse(vertex_4_count_over.expansion_required)
        self.assertEqual(
            signed_4_count_over.section_count_limit,
            (1 << 31) - 1,
        )
        self.assertEqual(
            signed_4_count_over.to_dict(),
            analyze_structural_capacity(
                PmxReferenceTargetKind.MATERIAL,
                current_count=(1 << 31) - 1,
                insert_count=1,
                index_width=4,
            ).to_dict(),
        )

    def test_large_same_anchor_append_and_mixed_batches_are_deterministic(self) -> None:
        source = _clean_document()
        source_snapshot = source
        same_anchor = tuple(
            PmxStructuralTextureInsertion(
                f"textures/cp21-anchor-{index:02d}.png",
                position="insert_before",
                source_index=0,
            )
            for index in range(24)
        )
        appended = tuple(
            PmxStructuralTextureInsertion(
                f"textures/cp21-append-{index:02d}.png",
            )
            for index in range(24)
        )
        materials = tuple(
            PmxStructuralMaterialInsertion(local_name=f"CP21 material {index:02d}")
            for index in range(16)
        )
        request = services.PmxStructuralEditRequest(
            texture_insertions=same_anchor + appended,
            material_insertions=materials,
        )
        request_snapshot = repr(request)

        first = services.preview_structural_edit(source, request)
        second = services.preview_structural_edit(source, request)

        self.assertEqual(first.document, second.document)
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(source, source_snapshot)
        self.assertEqual(repr(request), request_snapshot)
        self.assertEqual(
            first.document.texture_paths[:24],
            tuple(item.path for item in same_anchor),
        )
        self.assertEqual(
            first.document.texture_paths[-24:],
            tuple(item.path for item in appended),
        )
        self.assertEqual(
            len(first.document.materials),
            len(source.materials) + 16,
        )

    def test_format_encoding_and_index_width_matrix_preview_execute(self) -> None:
        request = services.PmxStructuralEditRequest(
            texture_insertions=(
                PmxStructuralTextureInsertion("textures/日本語-cp21.png"),
            ),
        )
        for version in (2.0, 2.1):
            for encoding_flag in (0, 1):
                for index_size in (1, 2, 4):
                    with self.subTest(
                        version=version,
                        encoding_flag=encoding_flag,
                        index_size=index_size,
                    ):
                        source_document = _clean_document(
                            version=version,
                            encoding_flag=encoding_flag,
                            index_size=index_size,
                        )
                        preview = services.preview_structural_edit(
                            source_document,
                            request,
                        )
                        self.assertEqual(
                            preview.document.header,
                            source_document.header,
                        )

                        with tempfile.TemporaryDirectory() as directory:
                            root = Path(directory)
                            source = root / "source.pmx"
                            output = root / "output.pmx"
                            source_bytes = serialize_pmx(source_document)
                            source.write_bytes(source_bytes)

                            written = services.apply_structural_edit(
                                source,
                                output,
                                request,
                            )

                            self.assertEqual(
                                written.document,
                                preview.document,
                            )
                            self.assertEqual(
                                load_pmx(output),
                                preview.document,
                            )
                            self.assertEqual(
                                source.read_bytes(),
                                source_bytes,
                            )
                            self.assertEqual(
                                _temporary_outputs(output),
                                (),
                            )

    def test_additional_uv_count_matrix_zero_through_four(self) -> None:
        base = _clean_document()
        for count in range(5):
            with self.subTest(additional_uv_count=count):
                header = replace(base.header, additional_uv_count=count)
                vertices = tuple(
                    replace(
                        vertex,
                        additional_uvs=vertex.additional_uvs[:count],
                    )
                    for vertex in base.vertices
                )
                morphs = tuple(
                    morph
                    if not (
                        4 <= morph.morph_type <= 7
                        and morph.morph_type > 3 + count
                    )
                    else replace(morph, morph_type=3)
                    for morph in base.morphs
                )
                source = replace(
                    base,
                    header=header,
                    geometry=replace(base.geometry, vertices=vertices),
                    morphs=morphs,
                )
                request = services.PmxStructuralEditRequest(
                    vertex_insertions=(
                        _vertex(
                            PmxStructuralVertexBdef1(0),
                            additional_uv_count=count,
                        ),
                    ),
                )
                result = services.preview_structural_edit(source, request)
                self.assertEqual(
                    len(result.document.vertices[-1].additional_uvs),
                    count,
                )
                self.assertEqual(
                    result.document.header.additional_uv_count,
                    count,
                )

    def test_empty_texture_and_material_collections_keep_append_boundary(self) -> None:
        source = _clean_document()
        materials_without_textures = tuple(
            replace(
                material,
                texture_index=-1,
                sphere_texture_index=-1,
                toon_reference_mode="shared",
                toon_reference_index=0,
            )
            for material in source.materials
        )
        empty_textures = replace(
            source,
            texture_paths=(),
            materials=materials_without_textures,
        )
        texture_result = services.preview_structural_edit(
            empty_textures,
            services.PmxStructuralEditRequest(
                texture_insertions=(
                    PmxStructuralTextureInsertion("textures/first.png"),
                ),
            ),
        )
        self.assertEqual(
            texture_result.document.texture_paths,
            ("textures/first.png",),
        )
        with self.assertRaises(PmxServiceError):
            services.preview_structural_edit(
                empty_textures,
                services.PmxStructuralEditRequest(
                    texture_insertions=(
                        PmxStructuralTextureInsertion(
                            "textures/first.png",
                            position="insert_before",
                            source_index=0,
                        ),
                    ),
                ),
            )

        cleared = _clear_incoming_material_references(source)
        empty_materials = replace(
            cleared,
            geometry=replace(cleared.geometry, surface_indices=()),
            materials=(),
        )
        material_result = services.preview_structural_edit(
            empty_materials,
            services.PmxStructuralEditRequest(
                material_insertions=(
                    PmxStructuralMaterialInsertion(local_name="First"),
                ),
            ),
        )
        self.assertEqual(len(material_result.document.materials), 1)
        self.assertEqual(material_result.document.surface_indices, ())
        with self.assertRaises(PmxServiceError):
            services.preview_structural_edit(
                empty_materials,
                services.PmxStructuralEditRequest(
                    material_insertions=(
                        PmxStructuralMaterialInsertion(
                            local_name="First",
                            position="insert_before",
                            source_index=0,
                        ),
                    ),
                ),
            )

    def test_reference_adversaries_and_source_new_domains_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            PmxStructuralNewReference("unknown", "good")
        with self.assertRaises(ValueError):
            PmxStructuralVertexBdef1(
                PmxStructuralNewReference("texture", "tex")
            )
        with self.assertRaisesRegex(ValueError, "globally unique"):
            services.PmxStructuralEditRequest(
                bone_insertions=(
                    PmxStructuralBoneInsertion(local_name="B", new_id="same"),
                ),
                vertex_insertions=(
                    _vertex(PmxStructuralVertexBdef1(0)),
                ),
                texture_insertions=(
                    PmxStructuralTextureInsertion(
                        "textures/x.png",
                        new_id="same",
                    ),
                ),
            )

        source = _clean_document()
        collision_request = services.PmxStructuralEditRequest(
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
        collision = services.preview_structural_edit(
            source,
            collision_request,
        )
        self.assertEqual(
            collision.document.vertices[-1].deform.bone_indices,
            (1, 0),
        )

        forward_request = services.PmxStructuralEditRequest(
            material_insertions=(
                PmxStructuralMaterialInsertion(
                    local_name="Forward material",
                    texture_index=PmxStructuralNewReference(
                        "texture",
                        "future_texture",
                    ),
                ),
            ),
            texture_insertions=(
                PmxStructuralTextureInsertion(
                    "textures/future.png",
                    new_id="future_texture",
                ),
            ),
        )
        forward = services.preview_structural_edit(source, forward_request)
        self.assertEqual(
            forward.document.materials[-1].texture_index,
            len(source.texture_paths),
        )

    def test_same_request_reuse_and_a_b_a_preview_isolation(self) -> None:
        source = _clean_document()
        request_a = services.PmxStructuralEditRequest(
            texture_insertions=(
                PmxStructuralTextureInsertion("textures/a.png"),
            ),
        )
        request_b = services.PmxStructuralEditRequest(
            bone_insertions=(
                PmxStructuralBoneInsertion(local_name="B"),
            ),
        )
        snapshot_a = repr(request_a)
        snapshot_b = repr(request_b)

        a1 = services.preview_structural_edit(source, request_a)
        a2 = services.preview_structural_edit(source, request_a)
        _ = services.preview_structural_edit(source, request_b)
        a3 = services.preview_structural_edit(source, request_a)

        self.assertEqual(a1.document, a2.document)
        self.assertEqual(a1.document, a3.document)
        self.assertEqual(a1.to_dict(), a2.to_dict())
        self.assertEqual(a1.to_dict(), a3.to_dict())
        self.assertEqual(repr(request_a), snapshot_a)
        self.assertEqual(repr(request_b), snapshot_b)

    def test_failure_success_failure_preview_isolation(self) -> None:
        source = _clean_document()
        good = _good_coordinated_request()
        bad = _unknown_reference_request()

        with self.assertRaises(PmxServiceError) as first_failure:
            services.preview_structural_edit(source, bad)
        success = services.preview_structural_edit(source, good)
        with self.assertRaises(PmxServiceError) as second_failure:
            services.preview_structural_edit(source, bad)
        repeated_success = services.preview_structural_edit(source, good)

        self.assertEqual(
            first_failure.exception.to_dict(),
            second_failure.exception.to_dict(),
        )
        self.assertEqual(success.document, repeated_success.document)
        self.assertEqual(success.to_dict(), repeated_success.to_dict())

    def test_preview_execute_preview_and_cross_request_execution_isolation(self) -> None:
        source_document = _clean_document()
        source_bytes = serialize_pmx(source_document)
        request_a = services.PmxStructuralEditRequest(
            texture_insertions=(
                PmxStructuralTextureInsertion("textures/a.png"),
            ),
        )
        request_b = services.PmxStructuralEditRequest(
            bone_insertions=(
                PmxStructuralBoneInsertion(local_name="B"),
            ),
        )

        before = services.preview_structural_edit(source_document, request_a)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output_a1 = root / "a1.pmx"
            output_b = root / "b.pmx"
            output_a2 = root / "a2.pmx"
            source.write_bytes(source_bytes)

            written_a1 = services.apply_structural_edit(
                source,
                output_a1,
                request_a,
            )
            _ = services.apply_structural_edit(source, output_b, request_b)
            written_a2 = services.apply_structural_edit(
                source,
                output_a2,
                request_a,
            )

            self.assertEqual(written_a1.document, written_a2.document)
            self.assertEqual(
                output_a1.read_bytes(),
                output_a2.read_bytes(),
            )
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(_temporary_outputs(output_a1), ())
            self.assertEqual(_temporary_outputs(output_b), ())
            self.assertEqual(_temporary_outputs(output_a2), ())

        after = services.preview_structural_edit(source_document, request_a)
        self.assertEqual(before.document, after.document)
        self.assertEqual(before.to_dict(), after.to_dict())

    def test_failure_success_failure_execution_leaves_no_residue(self) -> None:
        source_document = _clean_document()
        source_bytes = serialize_pmx(source_document)
        bad = _unknown_reference_request()
        good = _good_coordinated_request()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            bad_one = root / "bad-one.pmx"
            good_output = root / "good.pmx"
            bad_two = root / "bad-two.pmx"
            source.write_bytes(source_bytes)

            with self.assertRaises(PmxServiceError) as first_failure:
                services.apply_structural_edit(source, bad_one, bad)
            success = services.apply_structural_edit(
                source,
                good_output,
                good,
            )
            with self.assertRaises(PmxServiceError) as second_failure:
                services.apply_structural_edit(source, bad_two, bad)

            self.assertEqual(
                first_failure.exception.to_dict(),
                second_failure.exception.to_dict(),
            )
            self.assertEqual(load_pmx(good_output), success.document)
            self.assertFalse(bad_one.exists())
            self.assertFalse(bad_two.exists())
            self.assertEqual(_temporary_outputs(bad_one), ())
            self.assertEqual(_temporary_outputs(bad_two), ())
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_malformed_trailing_data_failure_then_clean_success_isolated(self) -> None:
        request = services.PmxStructuralEditRequest(
            texture_insertions=(
                PmxStructuralTextureInsertion("textures/cp21.png"),
            ),
        )
        malformed_bytes = build_pmx_roundtrip_fixture(
            version=2.1,
            encoding_flag=1,
            index_size=1,
        )
        self.assertTrue(
            load_pmx(io.BytesIO(malformed_bytes)).trailing_data
        )
        clean_bytes = _source_bytes(
            version=2.1,
            encoding_flag=1,
            index_size=1,
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            failed_output = root / "failed.pmx"
            success_output = root / "success.pmx"

            source.write_bytes(malformed_bytes)
            with self.assertRaises(PmxServiceError):
                services.apply_structural_edit(
                    source,
                    failed_output,
                    request,
                )
            self.assertFalse(failed_output.exists())
            self.assertEqual(_temporary_outputs(failed_output), ())

            source.write_bytes(clean_bytes)
            result = services.apply_structural_edit(
                source,
                success_output,
                request,
            )
            self.assertTrue(success_output.is_file())
            self.assertEqual(load_pmx(success_output), result.document)
            self.assertEqual(source.read_bytes(), clean_bytes)
            self.assertEqual(_temporary_outputs(success_output), ())

    def test_release_freezes_remain_unpromoted(self) -> None:
        self.assertEqual(services.PmxStructuralEditRequest.__name__, "PmxStructuralPreviewRequest")
        self.assertIs(
            services.PmxStructuralEditRequest,
            services.PmxStructuralPreviewRequest,
        )
        self.assertNotIn(
            "structural_insert",
            services.get_capabilities().to_dict(),
        )


if __name__ == "__main__":
    unittest.main()
