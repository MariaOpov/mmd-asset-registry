# CP16 vertex insertion execution and transaction-safety coverage.

from __future__ import annotations

import io
import struct
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import mmd_registry.pmx as pmx_public
import mmd_registry.services as services
from mmd_registry.diagnostics import PmxServiceError
from mmd_registry.pmx import structural_output as structural_output_module
from mmd_registry.pmx.document import PmxUvMorphOffset, PmxVertexMorphOffset
from mmd_registry.pmx.editing import output as edit_output
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.writer import serialize_pmx
from mmd_registry.services.structural_vertex import (
    PmxStructuralVertexBdef1,
    PmxStructuralVertexInsertion,
    PmxStructuralVertexQdef,
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


def _additional_uvs(count: int = 4):
    return tuple(
        (0.1 + index, 0.2 + index, 0.3 + index, 0.4 + index)
        for index in range(count)
    )


def _insertion(
    *,
    value: float = 0.1,
    deform=None,
    position: str = "append",
    source_index=None,
):
    if deform is None:
        deform = PmxStructuralVertexBdef1(0)
    return PmxStructuralVertexInsertion(
        vertex_position=(value, value + 1.0, value + 2.0),
        normal=(0.0, 1.0, 0.0),
        uv=(value, value + 0.25),
        additional_uvs=_additional_uvs(),
        deform=deform,
        edge_scale=value + 1.0,
        position=position,
        source_index=source_index,
    )


def _request(*insertions):
    return services.PmxStructuralEditRequest(vertex_insertions=tuple(insertions))


def _temporary_outputs(destination: Path) -> tuple[Path, ...]:
    return tuple(destination.parent.glob(f".{destination.name}.*.tmp"))


def _failure_stage(error: PmxServiceError) -> str:
    return str(error.to_dict()["details"]["stage"])


class VertexInsertionExecutionTests(unittest.TestCase):
    def test_append_execution_matches_preview_reparse_report_and_is_deterministic(self) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)
        request = _request(_insertion(value=0.1))
        preview = services.preview_structural_edit(document, request)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            first_output = root / "first.pmx"
            second_output = root / "second.pmx"
            source.write_bytes(source_bytes)

            first = services.apply_structural_edit(source, first_output, request)
            second = services.apply_structural_edit(source, second_output, request)

            self.assertEqual(first.status, "written")
            self.assertEqual(first.document, preview.document)
            self.assertEqual(load_pmx(first_output), preview.document)
            self.assertEqual(load_pmx(second_output), preview.document)
            self.assertEqual(first_output.read_bytes(), second_output.read_bytes())
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(_temporary_outputs(first_output), ())
            self.assertEqual(_temporary_outputs(second_output), ())

            report = first.to_dict()
            self.assertFalse(report["dry_run"])
            self.assertTrue(report["output"]["written"])
            self.assertTrue(report["verification"]["input_unchanged"])
            self.assertEqual(report["verification"]["invariants"], "passed")
            self.assertEqual(report["verification"]["reference_model"], "passed")
            self.assertEqual(report["verification"]["serialization"], "passed")
            self.assertEqual(report["verification"]["semantic"], "passed")

    def test_insert_before_execution_shifts_all_incoming_vertex_owners(self) -> None:
        document = _clean_document(version=2.1)
        request = _request(
            _insertion(value=0.2, position="insert_before", source_index=0)
        )
        preview = services.preview_structural_edit(document, request)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source_bytes = serialize_pmx(document)
            source.write_bytes(source_bytes)
            result = services.apply_structural_edit(source, output, request)
            written = load_pmx(output)

            self.assertEqual(result.document, preview.document)
            self.assertEqual(written, preview.document)
            self.assertEqual(
                written.surface_indices,
                tuple(index + 1 for index in document.surface_indices),
            )
            self.assertEqual(
                tuple(material.surface_index_count for material in written.materials),
                tuple(material.surface_index_count for material in document.materials),
            )
            self.assertEqual(len(written.surface_indices), len(document.surface_indices))

            saw_morph_owner = False
            for source_morph, output_morph in zip(
                document.morphs, written.morphs, strict=True
            ):
                for source_offset, output_offset in zip(
                    source_morph.offsets, output_morph.offsets, strict=True
                ):
                    if isinstance(
                        source_offset,
                        (PmxVertexMorphOffset, PmxUvMorphOffset),
                    ):
                        saw_morph_owner = True
                        self.assertEqual(
                            output_offset.vertex_index,
                            source_offset.vertex_index + 1,
                        )
            self.assertTrue(saw_morph_owner)

            self.assertTrue(document.soft_bodies)
            for old_body, new_body in zip(
                document.soft_bodies, written.soft_bodies, strict=True
            ):
                for old_anchor, new_anchor in zip(
                    old_body.anchors, new_body.anchors, strict=True
                ):
                    self.assertEqual(new_anchor.vertex_index, old_anchor.vertex_index + 1)
                self.assertEqual(
                    new_body.pinned_vertex_indices,
                    tuple(index + 1 for index in old_body.pinned_vertex_indices),
                )
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_same_anchor_and_append_request_order_survives_execution(self) -> None:
        document = _clean_document()
        request = _request(
            _insertion(value=10.0, position="insert_before", source_index=0),
            _insertion(value=20.0, position="insert_before", source_index=0),
            _insertion(value=30.0),
            _insertion(value=40.0),
        )
        preview = services.preview_structural_edit(document, request)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(serialize_pmx(document))
            result = services.apply_structural_edit(source, output, request)
            written = load_pmx(output)
            self.assertEqual(written, preview.document)
            self.assertEqual(result.document, preview.document)
            self.assertEqual(written.vertices[0].position[0], 10.0)
            self.assertEqual(written.vertices[1].position[0], 20.0)
            self.assertEqual(written.vertices[-2].position[0], 30.0)
            self.assertEqual(written.vertices[-1].position[0], 40.0)

    def test_execution_matrix_covers_versions_encodings_and_vertex_index_widths(self) -> None:
        for version in (2.0, 2.1):
            for encoding_flag in (0, 1):
                for index_size in (1, 2, 4):
                    with self.subTest(
                        version=version,
                        encoding_flag=encoding_flag,
                        index_size=index_size,
                    ):
                        document = _clean_document(
                            version=version,
                            encoding_flag=encoding_flag,
                            index_size=index_size,
                        )
                        source_bytes = serialize_pmx(document)
                        request = _request(_insertion(value=0.3))
                        with tempfile.TemporaryDirectory() as directory:
                            root = Path(directory)
                            source = root / "source.pmx"
                            output = root / "output.pmx"
                            source.write_bytes(source_bytes)
                            result = services.apply_structural_edit(source, output, request)
                            written = load_pmx(output)
                            self.assertEqual(written, result.document)
                            self.assertEqual(
                                written.header.index_sizes.vertex,
                                index_size,
                            )
                            self.assertEqual(source.read_bytes(), source_bytes)

    def test_execution_preserves_exact_float32_semantics(self) -> None:
        value = 0.1
        canonical = struct.unpack("<f", struct.pack("<f", value))[0]
        document = _clean_document()
        request = _request(_insertion(value=value))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(serialize_pmx(document))
            result = services.apply_structural_edit(source, output, request)
            vertex = result.document.vertices[-1]
            self.assertEqual(vertex.position[0], canonical)
            self.assertEqual(vertex.uv[0], canonical)

    def test_qdef_is_refused_on_pmx20_before_publication(self) -> None:
        document = _clean_document(version=2.0)
        request = _request(
            _insertion(
                deform=PmxStructuralVertexQdef(
                    (0, 0, 0, 0),
                    (0.25, 0.25, 0.25, 0.25),
                )
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source_bytes = serialize_pmx(document)
            source.write_bytes(source_bytes)
            with self.assertRaises(PmxServiceError):
                services.apply_structural_edit(source, output, request)
            self.assertFalse(output.exists())
            self.assertEqual(_temporary_outputs(output), ())
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_unsigned_one_byte_vertex_capacity_boundary_is_exact_on_execution(self) -> None:
        document = _clean_document(index_size=1)
        repeated = document.vertices[0]
        source_255 = replace(
            document,
            geometry=replace(document.geometry, vertices=(repeated,) * 255),
        )
        source_256 = replace(
            document,
            geometry=replace(document.geometry, vertices=(repeated,) * 256),
        )
        request = _request(_insertion())

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(serialize_pmx(source_255))
            result = services.apply_structural_edit(source, output, request)
            self.assertEqual(len(result.document.vertices), 256)
            self.assertEqual(result.document.header.index_sizes.vertex, 1)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source_bytes = serialize_pmx(source_256)
            source.write_bytes(source_bytes)
            with self.assertRaises(PmxServiceError):
                services.apply_structural_edit(source, output, request)
            self.assertFalse(output.exists())
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_reader_safety_limit_fails_before_publication(self) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)
            with patch(
                "mmd_registry.pmx.structural_vertex_insertion.MAX_PMX_VERTEX_COUNT",
                len(document.vertices),
            ):
                with self.assertRaises(PmxServiceError):
                    services.apply_structural_edit(source, output, _request(_insertion()))
            self.assertFalse(output.exists())
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_opaque_trailing_data_fails_closed_before_publication(self) -> None:
        source_bytes = build_pmx_roundtrip_fixture(version=2.1)
        self.assertTrue(load_pmx(io.BytesIO(source_bytes)).trailing_data)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)
            with self.assertRaises(PmxServiceError) as raised:
                services.apply_structural_edit(source, output, _request(_insertion()))
            self.assertEqual(_failure_stage(raised.exception), "structural_certification")
            self.assertFalse(output.exists())
            self.assertEqual(_temporary_outputs(output), ())
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_existing_destination_no_clobber_and_explicit_overwrite(self) -> None:
        source_bytes = _source_bytes()
        request = _request(_insertion())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)
            output.write_bytes(b"existing")

            with self.assertRaises(PmxServiceError) as raised:
                services.apply_structural_edit(source, output, request)
            self.assertEqual(_failure_stage(raised.exception), "path_resolution")
            self.assertEqual(output.read_bytes(), b"existing")
            self.assertEqual(_temporary_outputs(output), ())

            result = services.apply_structural_edit(
                source,
                output,
                request,
                overwrite=True,
            )
            self.assertEqual(result.status, "written")
            self.assertEqual(load_pmx(output), result.document)
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(_temporary_outputs(output), ())

    def test_in_place_execution_is_refused_even_with_overwrite(self) -> None:
        source_bytes = _source_bytes()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.pmx"
            source.write_bytes(source_bytes)
            with self.assertRaises(PmxServiceError) as raised:
                services.apply_structural_edit(
                    source,
                    source,
                    _request(_insertion()),
                    overwrite=True,
                )
            self.assertEqual(_failure_stage(raised.exception), "path_resolution")
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_serialization_failure_is_bounded_and_publishes_nothing(self) -> None:
        source_bytes = _source_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)
            with patch.object(
                structural_output_module,
                "serialize_pmx",
                side_effect=ValueError("simulated serialization failure"),
            ):
                with self.assertRaises(PmxServiceError) as raised:
                    services.apply_structural_edit(source, output, _request(_insertion()))
            self.assertEqual(_failure_stage(raised.exception), "serialization")
            self.assertFalse(output.exists())
            self.assertEqual(_temporary_outputs(output), ())
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_reparse_failure_is_bounded_and_publishes_nothing(self) -> None:
        source_bytes = _source_bytes()
        original_load = structural_output_module.load_pmx
        calls = 0

        def fail_second_load(source):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise ValueError("simulated reparse failure")
            return original_load(source)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)
            with patch.object(
                structural_output_module,
                "load_pmx",
                side_effect=fail_second_load,
            ):
                with self.assertRaises(PmxServiceError) as raised:
                    services.apply_structural_edit(source, output, _request(_insertion()))
            self.assertEqual(_failure_stage(raised.exception), "reparse")
            self.assertFalse(output.exists())
            self.assertEqual(_temporary_outputs(output), ())
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_reparse_certification_failure_is_bounded_and_publishes_nothing(self) -> None:
        source_bytes = _source_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)
            with patch.object(
                structural_output_module,
                "PmxStructuralInvariantCertificate",
                side_effect=ValueError("simulated certification failure"),
            ):
                with self.assertRaises(PmxServiceError) as raised:
                    services.apply_structural_edit(source, output, _request(_insertion()))
            self.assertEqual(_failure_stage(raised.exception), "reparse_certification")
            self.assertFalse(output.exists())
            self.assertEqual(_temporary_outputs(output), ())
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_semantic_mismatch_is_bounded_and_publishes_nothing(self) -> None:
        source_document = _clean_document()
        source_bytes = serialize_pmx(source_document)
        original_load = structural_output_module.load_pmx
        calls = 0

        def mismatch_second_load(source):
            nonlocal calls
            calls += 1
            if calls == 2:
                return source_document
            return original_load(source)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)
            with patch.object(
                structural_output_module,
                "load_pmx",
                side_effect=mismatch_second_load,
            ):
                with self.assertRaises(PmxServiceError) as raised:
                    services.apply_structural_edit(source, output, _request(_insertion()))
            self.assertEqual(_failure_stage(raised.exception), "semantic_compare")
            self.assertFalse(output.exists())
            self.assertEqual(_temporary_outputs(output), ())
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_source_content_race_is_detected_and_temp_is_removed(self) -> None:
        source_bytes = _source_bytes()
        original_commit = edit_output._commit_verified_bytes

        def race_commit(data: bytes, **kwargs) -> None:
            requested_source = kwargs["requested_source"]
            requested_source.write_bytes(source_bytes + b"external-race")
            return original_commit(data, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)
            with patch.object(
                edit_output,
                "_commit_verified_bytes",
                side_effect=race_commit,
            ):
                with self.assertRaises(PmxServiceError) as raised:
                    services.apply_structural_edit(source, output, _request(_insertion()))
            self.assertEqual(_failure_stage(raised.exception), "output_commit")
            self.assertFalse(output.exists())
            self.assertEqual(_temporary_outputs(output), ())

    def test_destination_race_is_detected_without_clobber_or_temp_residue(self) -> None:
        source_bytes = _source_bytes()
        original_validate = edit_output._validate_destination_state
        calls = 0

        def race_on_second_validation(source, destination, *, overwrite):
            nonlocal calls
            calls += 1
            if calls == 2:
                destination.write_bytes(b"racer")
            return original_validate(source, destination, overwrite=overwrite)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)
            with patch.object(
                edit_output,
                "_validate_destination_state",
                side_effect=race_on_second_validation,
            ):
                with self.assertRaises(PmxServiceError) as raised:
                    services.apply_structural_edit(source, output, _request(_insertion()))
            self.assertEqual(_failure_stage(raised.exception), "output_commit")
            self.assertEqual(output.read_bytes(), b"racer")
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(_temporary_outputs(output), ())

    def test_private_boundary_alias_and_capability_remain_frozen(self) -> None:
        manifest = services.get_capabilities().to_dict()
        self.assertIs((manifest)["structural_insert"], True)
        self.assertIs(
            services.PmxStructuralEditRequest,
            services.PmxStructuralPreviewRequest,
        )
        self.assertFalse(
            hasattr(services, "_write_pmx_vertex_insertion_transaction")
        )
        self.assertFalse(
            hasattr(pmx_public, "_write_pmx_vertex_insertion_transaction")
        )
        self.assertNotIn(
            "_write_pmx_vertex_insertion_transaction",
            structural_output_module.__all__,
        )


if __name__ == "__main__":
    unittest.main()
