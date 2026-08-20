"""CP10 material insertion execution through the shared verified transaction."""

from __future__ import annotations

import hashlib
import io
import json
import struct
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import mmd_registry.pmx as pmx_public
import mmd_registry.services as services
from mmd_registry.diagnostics import (
    PmxServiceDiagnosticCode,
    PmxServiceError,
)
from mmd_registry.pmx import structural_output as structural_output_module
from mmd_registry.pmx.document import PmxMaterialMorphOffset
from mmd_registry.pmx.editing import output as edit_output
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.writer import serialize_pmx
from mmd_registry.services.structural_material import PmxStructuralMaterialInsertion
from mmd_registry.services.structural_texture import PmxStructuralTextureInsertion
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


def _clean_document():
    return replace(
        load_pmx(io.BytesIO(build_pmx_roundtrip_fixture(version=2.1))),
        trailing_data=b"",
    )


def _source_bytes():
    return serialize_pmx(_clean_document())


def _append_request(
    name: str = "CP10 appended",
    **kwargs,
):
    return services.PmxStructuralEditRequest(
        material_insertions=(
            PmxStructuralMaterialInsertion(local_name=name, **kwargs),
        ),
    )


def _temporary_outputs(destination: Path) -> tuple[Path, ...]:
    return tuple(destination.parent.glob(f".{destination.name}.*.tmp"))


def _shift_optional(index: int, anchor: int) -> int:
    if index == -1:
        return -1
    return index + 1 if index >= anchor else index


def _assert_incoming_material_refs_shifted(
    test: unittest.TestCase,
    source,
    rewritten,
    *,
    anchor: int,
) -> None:
    saw_reference = False
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
            if isinstance(source_offset, PmxMaterialMorphOffset):
                test.assertIsInstance(output_offset, PmxMaterialMorphOffset)
                test.assertEqual(
                    output_offset.material_index,
                    _shift_optional(source_offset.material_index, anchor),
                )
                saw_reference = saw_reference or source_offset.material_index >= 0

    for source_body, output_body in zip(
        source.soft_bodies,
        rewritten.soft_bodies,
        strict=True,
    ):
        test.assertEqual(
            output_body.material_index,
            _shift_optional(source_body.material_index, anchor),
        )
        test.assertEqual(output_body.anchors, source_body.anchors)
        test.assertEqual(
            output_body.pinned_vertex_indices,
            source_body.pinned_vertex_indices,
        )
        saw_reference = saw_reference or source_body.material_index >= 0

    test.assertTrue(
        saw_reference,
        "fixture must expose a material morph or soft-body material reference",
    )


class MaterialInsertionExecutionTests(unittest.TestCase):
    def test_append_execution_matches_preview_and_preserves_source(self) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)
        request = _append_request()
        preview = services.preview_structural_edit(document, request)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)

            result = services.apply_structural_edit(source, output, request)

            self.assertEqual(result.status, "written")
            self.assertEqual(result.document, preview.document)
            self.assertEqual(load_pmx(output), preview.document)
            self.assertEqual(result.document.materials[-1].surface_index_count, 0)
            self.assertEqual(result.document.surface_indices, document.surface_indices)
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(
                result.source_sha256,
                hashlib.sha256(source_bytes).hexdigest(),
            )
            self.assertEqual(
                result.output_sha256,
                hashlib.sha256(output.read_bytes()).hexdigest(),
            )
            self.assertEqual(result.output_size_bytes, output.stat().st_size)
            self.assertEqual(_temporary_outputs(output), ())

    def test_insert_before_zero_executes_exact_incoming_reference_shift(self) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)
        request = services.PmxStructuralEditRequest(
            material_insertions=(
                PmxStructuralMaterialInsertion(
                    local_name="CP10 before zero",
                    position="insert_before",
                    source_index=0,
                ),
            ),
        )
        preview = services.preview_structural_edit(document, request)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)

            result = services.apply_structural_edit(source, output, request)

            self.assertEqual(result.document, preview.document)
            self.assertEqual(result.document.materials[0].local_name, "CP10 before zero")
            self.assertEqual(result.document.materials[0].surface_index_count, 0)
            self.assertEqual(result.document.materials[1:], document.materials)
            self.assertEqual(result.document.surface_indices, document.surface_indices)
            _assert_incoming_material_refs_shifted(
                self,
                document,
                result.document,
                anchor=0,
            )
            self.assertEqual(load_pmx(output), result.document)
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_same_anchor_and_append_order_survive_execution(self) -> None:
        document = _clean_document()
        self.assertGreaterEqual(len(document.materials), 1)
        request = services.PmxStructuralEditRequest(
            material_insertions=(
                PmxStructuralMaterialInsertion(
                    local_name="First",
                    position="insert_before",
                    source_index=0,
                ),
                PmxStructuralMaterialInsertion(
                    local_name="Second",
                    position="insert_before",
                    source_index=0,
                ),
                PmxStructuralMaterialInsertion(local_name="Append"),
            ),
        )
        preview = services.preview_structural_edit(document, request)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(serialize_pmx(document))

            result = services.apply_structural_edit(source, output, request)

            self.assertEqual(result.document, preview.document)
            self.assertEqual(
                tuple(material.local_name for material in result.document.materials[:2]),
                ("First", "Second"),
            )
            self.assertEqual(result.document.materials[2:-1], document.materials)
            self.assertEqual(result.document.materials[-1].local_name, "Append")
            self.assertTrue(
                all(
                    material.surface_index_count == 0
                    for material in (
                        result.document.materials[0],
                        result.document.materials[1],
                        result.document.materials[-1],
                    )
                )
            )
            self.assertEqual(load_pmx(output), preview.document)

    def test_source_domain_texture_references_survive_execution(self) -> None:
        document = _clean_document()
        self.assertGreater(len(document.texture_paths), 0)
        request = _append_request(
            "Textured material",
            texture_index=0,
            sphere_texture_index=0,
            sphere_mode=1,
            toon_reference_mode="texture",
            toon_reference_index=0,
        )
        preview = services.preview_structural_edit(document, request)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(serialize_pmx(document))

            result = services.apply_structural_edit(source, output, request)
            inserted = result.document.materials[-1]

            self.assertEqual(result.document, preview.document)
            self.assertEqual(inserted.texture_index, 0)
            self.assertEqual(inserted.sphere_texture_index, 0)
            self.assertEqual(inserted.toon_reference_index, 0)
            self.assertEqual(result.document.texture_paths, document.texture_paths)
            self.assertEqual(load_pmx(output), result.document)

    def test_float32_canonicalization_keeps_preview_execute_semantics_exact(self) -> None:
        document = _clean_document()
        request = _append_request(
            "Float32 parity",
            diffuse=(0.1, 0.2, 0.3, 0.4),
            specular=(0.1, 0.2, 0.3),
            specular_strength=0.1,
            ambient=(0.1, 0.2, 0.3),
            edge_color=(0.1, 0.2, 0.3, 0.4),
            edge_scale=0.1,
        )
        preview = services.preview_structural_edit(document, request)
        expected = struct.unpack("<f", struct.pack("<f", 0.1))[0]
        self.assertEqual(preview.document.materials[-1].edge_scale, expected)
        self.assertNotEqual(expected, 0.1)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(serialize_pmx(document))

            result = services.apply_structural_edit(source, output, request)

            self.assertEqual(result.document, preview.document)
            self.assertEqual(load_pmx(output), preview.document)
            self.assertEqual(result.document.materials[-1].edge_scale, expected)

    def test_execution_report_promotes_cp09_evidence_without_payload_leak(self) -> None:
        document = _clean_document()
        name = "private-cp10-material-name"
        memo = "private-cp10-material-memo"
        request = _append_request(name, memo=memo)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(serialize_pmx(document))

            result = services.apply_structural_edit(source, output, request)
            report = result.to_dict()
            encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

            self.assertEqual(report["preview_schema_version"], 1)
            self.assertEqual(report["status"], "written")
            self.assertFalse(report["dry_run"])
            self.assertTrue(report["output"]["written"])
            self.assertEqual(report["verification"]["invariants"], "passed")
            self.assertEqual(report["verification"]["reference_model"], "passed")
            self.assertEqual(report["verification"]["serialization"], "passed")
            self.assertEqual(report["verification"]["semantic"], "passed")
            self.assertTrue(report["verification"]["input_unchanged"])
            self.assertEqual(report["intent"]["insert_count"], 1)
            payload = report["audit"]["material_insertion"]["payloads"][0]
            self.assertEqual(payload["surface_index_count"], 0)
            self.assertEqual(len(payload["payload_sha256"]), 64)
            self.assertNotIn(name, encoded)
            self.assertNotIn(memo, encoded)

    def test_execution_is_deterministic_for_same_source_and_request(self) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)
        request = _append_request(
            "Deterministic",
            diffuse=(0.1, 0.2, 0.3, 0.4),
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            first_output = root / "first.pmx"
            second_output = root / "second.pmx"
            source.write_bytes(source_bytes)

            first = services.apply_structural_edit(source, first_output, request)
            second = services.apply_structural_edit(source, second_output, request)

            self.assertEqual(first_output.read_bytes(), second_output.read_bytes())
            self.assertEqual(first.output_sha256, second.output_sha256)
            self.assertEqual(first.document, second.document)
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_existing_destination_is_preserved_without_overwrite(self) -> None:
        source_bytes = _source_bytes()
        request = _append_request()
        sentinel = b"existing-output"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)
            output.write_bytes(sentinel)

            with self.assertRaises(PmxServiceError) as raised:
                services.apply_structural_edit(source, output, request)

            self.assertEqual(
                raised.exception.diagnostic.code,
                PmxServiceDiagnosticCode.STRUCTURAL_PATH_UNSAFE,
            )
            self.assertEqual(output.read_bytes(), sentinel)
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(_temporary_outputs(output), ())

    def test_overwrite_replaces_only_distinct_destination(self) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)
        request = _append_request()
        preview = services.preview_structural_edit(document, request)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)
            output.write_bytes(b"old-output")

            result = services.apply_structural_edit(
                source,
                output,
                request,
                overwrite=True,
            )

            self.assertEqual(load_pmx(output), preview.document)
            self.assertEqual(result.document, preview.document)
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(_temporary_outputs(output), ())

    def test_in_place_execution_is_refused_even_with_overwrite(self) -> None:
        source_bytes = _source_bytes()
        request = _append_request()

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.pmx"
            source.write_bytes(source_bytes)

            with self.assertRaises(PmxServiceError) as raised:
                services.apply_structural_edit(
                    source,
                    source,
                    request,
                    overwrite=True,
                )

            self.assertEqual(
                raised.exception.diagnostic.code,
                PmxServiceDiagnosticCode.STRUCTURAL_PATH_UNSAFE,
            )
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_out_of_range_anchor_fails_before_publication(self) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)
        request = services.PmxStructuralEditRequest(
            material_insertions=(
                PmxStructuralMaterialInsertion(
                    local_name="OOB",
                    position="insert_before",
                    source_index=len(document.materials),
                ),
            ),
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)

            with self.assertRaises(PmxServiceError) as raised:
                services.apply_structural_edit(source, output, request)

            self.assertEqual(
                raised.exception.diagnostic.code,
                PmxServiceDiagnosticCode.STRUCTURAL_VERIFICATION_FAILED,
            )
            self.assertEqual(
                raised.exception.to_dict()["details"]["stage"],
                "structural_certification",
            )
            self.assertFalse(output.exists())
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(_temporary_outputs(output), ())

    def test_unrepresentable_float32_fails_before_publication(self) -> None:
        source_bytes = _source_bytes()
        request = _append_request("Float overflow", edge_scale=1e300)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)

            with self.assertRaises(PmxServiceError) as raised:
                services.apply_structural_edit(source, output, request)

            self.assertEqual(
                raised.exception.to_dict()["details"]["stage"],
                "structural_certification",
            )
            self.assertFalse(output.exists())
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(_temporary_outputs(output), ())

    def test_serialization_failure_does_not_publish_output(self) -> None:
        source_bytes = _source_bytes()
        request = _append_request()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)

            with patch(
                "mmd_registry.pmx.structural_output.serialize_pmx",
                side_effect=ValueError("simulated serialization failure"),
            ):
                with self.assertRaises(PmxServiceError) as raised:
                    services.apply_structural_edit(source, output, request)

            self.assertEqual(
                raised.exception.to_dict()["details"]["stage"],
                "serialization",
            )
            self.assertFalse(output.exists())
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_reparse_failure_does_not_publish_output(self) -> None:
        source_bytes = _source_bytes()
        request = _append_request()
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

            with patch(
                "mmd_registry.pmx.structural_output.load_pmx",
                side_effect=fail_second_load,
            ):
                with self.assertRaises(PmxServiceError) as raised:
                    services.apply_structural_edit(source, output, request)

            self.assertEqual(raised.exception.to_dict()["details"]["stage"], "reparse")
            self.assertFalse(output.exists())
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_reparse_certification_failure_does_not_publish_output(self) -> None:
        source_bytes = _source_bytes()
        request = _append_request()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)

            with patch(
                "mmd_registry.pmx.structural_output."
                "PmxStructuralInvariantCertificate",
                side_effect=ValueError("simulated certificate failure"),
            ):
                with self.assertRaises(PmxServiceError) as raised:
                    services.apply_structural_edit(source, output, request)

            self.assertEqual(
                raised.exception.to_dict()["details"]["stage"],
                "reparse_certification",
            )
            self.assertFalse(output.exists())
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_semantic_mismatch_does_not_publish_output(self) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)
        request = _append_request()
        preview = services.preview_structural_edit(document, request)
        mismatched = replace(
            preview.document,
            model_info=replace(
                preview.document.model_info,
                local_name=preview.document.model_info.local_name + " mismatch",
            ),
        )
        original_load = structural_output_module.load_pmx
        calls = 0

        def mismatch_second_load(source):
            nonlocal calls
            calls += 1
            if calls == 2:
                return mismatched
            return original_load(source)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)

            with patch(
                "mmd_registry.pmx.structural_output.load_pmx",
                side_effect=mismatch_second_load,
            ):
                with self.assertRaises(PmxServiceError) as raised:
                    services.apply_structural_edit(source, output, request)

            self.assertEqual(
                raised.exception.to_dict()["details"]["stage"],
                "semantic_compare",
            )
            self.assertFalse(output.exists())
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_source_race_is_detected_and_temporary_output_is_removed(self) -> None:
        source_bytes = _source_bytes()
        request = _append_request()
        original_serialize = structural_output_module.serialize_pmx

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)

            def serialize_then_change_source(document):
                data = original_serialize(document)
                source.write_bytes(source.read_bytes() + b"race")
                return data

            with patch(
                "mmd_registry.pmx.structural_output.serialize_pmx",
                side_effect=serialize_then_change_source,
            ):
                with self.assertRaises(PmxServiceError) as raised:
                    services.apply_structural_edit(source, output, request)

            self.assertEqual(
                raised.exception.diagnostic.code,
                PmxServiceDiagnosticCode.STRUCTURAL_VERIFICATION_FAILED,
            )
            self.assertEqual(
                raised.exception.to_dict()["details"]["stage"],
                "output_commit",
            )
            self.assertFalse(output.exists())
            self.assertEqual(_temporary_outputs(output), ())

    def test_destination_race_is_detected_without_clobber_or_temp_residue(self) -> None:
        source_bytes = _source_bytes()
        request = _append_request()
        original_validate = edit_output._validate_destination_state
        calls = 0
        racer = b"racing-destination"

        def race_on_second_validation(source_path, destination, *, overwrite):
            nonlocal calls
            calls += 1
            if calls == 2:
                destination.write_bytes(racer)
            return original_validate(
                source_path,
                destination,
                overwrite=overwrite,
            )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)

            with patch(
                "mmd_registry.pmx.structural_output._edit_output."
                "_validate_destination_state",
                side_effect=race_on_second_validation,
            ):
                with self.assertRaises(PmxServiceError) as raised:
                    services.apply_structural_edit(source, output, request)

            self.assertEqual(
                raised.exception.diagnostic.code,
                PmxServiceDiagnosticCode.STRUCTURAL_PATH_UNSAFE,
            )
            self.assertEqual(
                raised.exception.to_dict()["details"]["stage"],
                "output_commit",
            )
            self.assertEqual(output.read_bytes(), racer)
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(_temporary_outputs(output), ())

    def test_public_boundary_and_capability_are_not_promoted(self) -> None:
        manifest = services.get_capabilities().to_dict()

        self.assertNotIn("structural_insert", manifest)
        self.assertFalse(
            hasattr(services, "_write_pmx_material_insertion_transaction")
        )
        self.assertFalse(
            hasattr(pmx_public, "_write_pmx_material_insertion_transaction")
        )
        self.assertNotIn(
            "_write_pmx_material_insertion_transaction",
            services.__all__,
        )
        self.assertNotIn(
            "_write_pmx_material_insertion_transaction",
            structural_output_module.__all__,
        )
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

    def test_texture_and_legacy_execution_remain_routed_through_same_public_result(
        self,
    ) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            texture_output = root / "texture.pmx"
            legacy_output = root / "legacy.pmx"
            source.write_bytes(source_bytes)

            texture_request = services.PmxStructuralEditRequest(
                texture_insertions=(
                    PmxStructuralTextureInsertion("textures/cp10-regression.png"),
                ),
            )
            texture_result = services.apply_structural_edit(
                source,
                texture_output,
                texture_request,
            )
            legacy_result = services.apply_structural_edit(
                source,
                legacy_output,
                services.PmxStructuralEditRequest(),
            )

            self.assertIsInstance(
                texture_result,
                services.PmxStructuralExecutionResult,
            )
            self.assertEqual(
                load_pmx(texture_output).texture_paths[-1],
                "textures/cp10-regression.png",
            )
            self.assertIsInstance(
                legacy_result,
                services.PmxStructuralExecutionResult,
            )
            self.assertEqual(legacy_result.status, "no_changes")
            self.assertEqual(load_pmx(legacy_output), document)
            self.assertEqual(source.read_bytes(), source_bytes)


if __name__ == "__main__":
    unittest.main()
