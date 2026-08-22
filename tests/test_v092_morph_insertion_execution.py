"""CP13 morph insertion execution through the shared verified transaction."""

from __future__ import annotations

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
from mmd_registry.diagnostics import PmxServiceError
from mmd_registry.pmx import structural_output as structural_output_module
from mmd_registry.pmx.editing import output as edit_output
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.writer import serialize_pmx
from mmd_registry.services.structural_bone import PmxStructuralBoneInsertion
from mmd_registry.services.structural_material import PmxStructuralMaterialInsertion
from mmd_registry.services.structural_morph import (
    PmxStructuralMorphFlipOffset,
    PmxStructuralMorphGroupOffset,
    PmxStructuralMorphInsertion,
    PmxStructuralMorphMaterialOffset,
    PmxStructuralMorphVertexOffset,
)
from mmd_registry.services.structural_texture import PmxStructuralTextureInsertion
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


def _append_insertion(
    name: str = "CP13 appended",
    *,
    value: float = 0.1,
):
    return PmxStructuralMorphInsertion(
        local_name=name,
        morph_type="vertex",
        offsets=(
            PmxStructuralMorphVertexOffset(
                vertex_index=0,
                translation=(value, value, value),
            ),
        ),
    )


def _append_request(name: str = "CP13 appended"):
    return services.PmxStructuralEditRequest(
        morph_insertions=(_append_insertion(name),),
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


def _temporary_outputs(destination: Path) -> tuple[Path, ...]:
    return tuple(destination.parent.glob(f".{destination.name}.*.tmp"))


def _failure_stage(error: PmxServiceError) -> str:
    return str(error.to_dict()["details"]["stage"])


class MorphInsertionExecutionTests(unittest.TestCase):
    def test_append_execution_matches_preview_reparse_report_and_is_deterministic(
        self,
    ) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)
        request = _append_request("private-cp13-morph-name")
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
            encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)
            self.assertNotIn("private-cp13-morph-name", encoded)

    def test_insert_before_source_domain_group_and_float32_semantics_match_preview(
        self,
    ) -> None:
        document = _clean_document()
        expected = struct.unpack("<f", struct.pack("<f", 0.1))[0]
        request = services.PmxStructuralEditRequest(
            morph_insertions=(
                PmxStructuralMorphInsertion(
                    local_name="Group",
                    morph_type="group",
                    offsets=(PmxStructuralMorphGroupOffset(0, 0.1),),
                    position="insert_before",
                    source_index=0,
                ),
                PmxStructuralMorphInsertion(
                    local_name="All materials",
                    morph_type="material",
                    offsets=(_material_offset(-1),),
                ),
            ),
        )
        preview = services.preview_structural_edit(document, request)
        inserted_group = preview.document.morphs[0]

        self.assertEqual(inserted_group.offsets[0].morph_index, 1)
        self.assertEqual(inserted_group.offsets[0].weight, expected)
        self.assertEqual(preview.document.morphs[-1].offsets[0].material_index, -1)

        source_bytes = serialize_pmx(document)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)

            result = services.apply_structural_edit(source, output, request)

            self.assertEqual(result.document, preview.document)
            self.assertEqual(load_pmx(output), preview.document)
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_same_anchor_and_append_order_survives_execution(self) -> None:
        document = _clean_document()
        request = services.PmxStructuralEditRequest(
            morph_insertions=(
                PmxStructuralMorphInsertion(
                    local_name="First",
                    morph_type="vertex",
                    offsets=(PmxStructuralMorphVertexOffset(0, (0.0, 0.0, 0.0)),),
                    position="insert_before",
                    source_index=0,
                ),
                PmxStructuralMorphInsertion(
                    local_name="Second",
                    morph_type="vertex",
                    offsets=(PmxStructuralMorphVertexOffset(0, (0.0, 0.0, 0.0)),),
                    position="insert_before",
                    source_index=0,
                ),
                _append_insertion("Append"),
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
                tuple(morph.local_name for morph in result.document.morphs[:2]),
                ("First", "Second"),
            )
            self.assertEqual(result.document.morphs[-1].local_name, "Append")

    def test_execution_matrix_covers_versions_encodings_and_morph_index_widths(
        self,
    ) -> None:
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
                        request = _append_request("互換 CP13")
                        preview = services.preview_structural_edit(document, request)

                        with tempfile.TemporaryDirectory() as directory:
                            root = Path(directory)
                            source = root / "source.pmx"
                            output = root / "output.pmx"
                            source.write_bytes(source_bytes)

                            result = services.apply_structural_edit(
                                source,
                                output,
                                request,
                            )

                            self.assertEqual(result.document, preview.document)
                            self.assertEqual(load_pmx(output), preview.document)
                            self.assertEqual(source.read_bytes(), source_bytes)

    def test_pmx21_flip_execution_maps_source_domain_reference(self) -> None:
        document = _clean_document(version=2.1)
        request = services.PmxStructuralEditRequest(
            morph_insertions=(
                PmxStructuralMorphInsertion(
                    "Flip",
                    "flip",
                    offsets=(PmxStructuralMorphFlipOffset(0, 0.5),),
                    position="insert_before",
                    source_index=0,
                ),
            ),
        )
        preview = services.preview_structural_edit(document, request)
        self.assertEqual(preview.document.morphs[0].offsets[0].morph_index, 1)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(serialize_pmx(document))

            result = services.apply_structural_edit(source, output, request)

            self.assertEqual(result.document, preview.document)
            self.assertEqual(load_pmx(output), preview.document)

    def test_current_morph_index_width_expansion_is_refused_before_publication(
        self,
    ) -> None:
        document = _clean_document(index_size=1)
        template = next(morph for morph in document.morphs if morph.morph_type == 1)
        constrained = replace(
            document,
            morphs=tuple(
                replace(template, local_name=f"Morph {index}")
                for index in range(128)
            ),
        )
        source_bytes = serialize_pmx(constrained)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)

            with self.assertRaises(PmxServiceError) as raised:
                services.apply_structural_edit(source, output, _append_request())

            self.assertEqual(
                _failure_stage(raised.exception),
                "structural_certification",
            )
            self.assertFalse(output.exists())
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(_temporary_outputs(output), ())

    def test_opaque_trailing_data_fails_closed_before_publication(self) -> None:
        source_bytes = build_pmx_roundtrip_fixture(version=2.1)
        self.assertTrue(load_pmx(io.BytesIO(source_bytes)).trailing_data)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)

            with self.assertRaises(PmxServiceError) as raised:
                services.apply_structural_edit(source, output, _append_request())

            self.assertEqual(
                _failure_stage(raised.exception),
                "structural_certification",
            )
            self.assertFalse(output.exists())
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_existing_destination_no_clobber_and_explicit_overwrite(self) -> None:
        source_bytes = _source_bytes()
        request = _append_request()

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
                    _append_request(),
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
                    services.apply_structural_edit(source, output, _append_request())

            self.assertEqual(_failure_stage(raised.exception), "serialization")
            self.assertFalse(output.exists())
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
                    services.apply_structural_edit(source, output, _append_request())

            self.assertEqual(_failure_stage(raised.exception), "reparse")
            self.assertFalse(output.exists())
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_reparse_certification_failure_is_bounded_and_publishes_nothing(
        self,
    ) -> None:
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
                    services.apply_structural_edit(source, output, _append_request())

            self.assertEqual(
                _failure_stage(raised.exception),
                "reparse_certification",
            )
            self.assertFalse(output.exists())
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
                    services.apply_structural_edit(source, output, _append_request())

            self.assertEqual(_failure_stage(raised.exception), "semantic_compare")
            self.assertFalse(output.exists())
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
                    services.apply_structural_edit(source, output, _append_request())

            self.assertEqual(_failure_stage(raised.exception), "output_commit")
            self.assertFalse(output.exists())
            self.assertEqual(_temporary_outputs(output), ())

    def test_destination_race_is_detected_without_clobber_or_temp_residue(
        self,
    ) -> None:
        source_bytes = _source_bytes()
        original_validate = edit_output._validate_destination_state
        calls = 0

        def race_on_second_validation(source, destination, *, overwrite):
            nonlocal calls
            calls += 1
            if calls == 2:
                destination.write_bytes(b"racer")
            return original_validate(
                source,
                destination,
                overwrite=overwrite,
            )

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
                    services.apply_structural_edit(source, output, _append_request())

            self.assertEqual(_failure_stage(raised.exception), "output_commit")
            self.assertEqual(output.read_bytes(), b"racer")
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(_temporary_outputs(output), ())

    def test_private_boundary_capability_and_existing_execution_paths_remain_stable(
        self,
    ) -> None:
        manifest = services.get_capabilities().to_dict()
        self.assertIs((manifest)["structural_insert"], True)
        self.assertFalse(
            hasattr(services, "_write_pmx_morph_insertion_transaction")
        )
        self.assertFalse(
            hasattr(pmx_public, "_write_pmx_morph_insertion_transaction")
        )
        self.assertNotIn(
            "_write_pmx_morph_insertion_transaction",
            structural_output_module.__all__,
        )

        document = _clean_document()
        source_bytes = serialize_pmx(document)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            texture_output = root / "texture.pmx"
            material_output = root / "material.pmx"
            bone_output = root / "bone.pmx"
            legacy_output = root / "legacy.pmx"
            source.write_bytes(source_bytes)

            texture = services.apply_structural_edit(
                source,
                texture_output,
                services.PmxStructuralEditRequest(
                    texture_insertions=(
                        PmxStructuralTextureInsertion(
                            "textures/cp13-regression.png"
                        ),
                    ),
                ),
            )
            material = services.apply_structural_edit(
                source,
                material_output,
                services.PmxStructuralEditRequest(
                    material_insertions=(
                        PmxStructuralMaterialInsertion(
                            local_name="CP13 material regression"
                        ),
                    ),
                ),
            )
            bone = services.apply_structural_edit(
                source,
                bone_output,
                services.PmxStructuralEditRequest(
                    bone_insertions=(
                        PmxStructuralBoneInsertion(
                            local_name="CP13 bone regression"
                        ),
                    ),
                ),
            )
            legacy = services.apply_structural_edit(
                source,
                legacy_output,
                services.PmxStructuralEditRequest(),
            )

            self.assertEqual(texture.status, "written")
            self.assertEqual(
                load_pmx(texture_output).texture_paths[-1],
                "textures/cp13-regression.png",
            )
            self.assertEqual(material.status, "written")
            self.assertEqual(
                load_pmx(material_output).materials[-1].local_name,
                "CP13 material regression",
            )
            self.assertEqual(bone.status, "written")
            self.assertEqual(
                load_pmx(bone_output).bones[-1].local_name,
                "CP13 bone regression",
            )
            self.assertEqual(legacy.status, "no_changes")
            self.assertEqual(load_pmx(legacy_output), document)
            self.assertEqual(source.read_bytes(), source_bytes)


if __name__ == "__main__":
    unittest.main()
