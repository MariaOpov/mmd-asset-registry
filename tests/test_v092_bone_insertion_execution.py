"""CP12 bone insertion execution through the shared verified transaction."""

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
from mmd_registry.services.structural_bone import (
    PmxStructuralBoneIk,
    PmxStructuralBoneIkLink,
    PmxStructuralBoneInsertion,
)
from mmd_registry.services.structural_material import PmxStructuralMaterialInsertion
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


def _append_request(name: str = "CP12 appended"):
    return services.PmxStructuralEditRequest(
        bone_insertions=(PmxStructuralBoneInsertion(local_name=name),),
    )


def _temporary_outputs(destination: Path) -> tuple[Path, ...]:
    return tuple(destination.parent.glob(f".{destination.name}.*.tmp"))


def _failure_stage(error: PmxServiceError) -> str:
    return str(error.to_dict()["details"]["stage"])


class BoneInsertionExecutionTests(unittest.TestCase):
    def test_append_execution_matches_preview_reparse_report_and_is_deterministic(
        self,
    ) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)
        request = _append_request("private-cp12-bone-name")
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
            self.assertNotIn("private-cp12-bone-name", encoded)

    def test_insert_before_full_semantic_payload_preserves_exact_cp11_intent(
        self,
    ) -> None:
        document = _clean_document()
        self.assertGreaterEqual(len(document.bones), 2)
        request = services.PmxStructuralEditRequest(
            bone_insertions=(
                PmxStructuralBoneInsertion(
                    local_name="Full semantic bone",
                    universal_name="Full Bone",
                    bone_position=(0.1, 0.2, 0.3),
                    parent_bone_index=0,
                    transform_layer=3,
                    rotatable=True,
                    translatable=True,
                    visible=True,
                    enabled=True,
                    local_append=True,
                    after_physics=True,
                    tail_offset=None,
                    tail_bone_index=1,
                    inherit_rotation=True,
                    inherit_translation=True,
                    inherit_parent_bone_index=0,
                    inherit_weight=0.1,
                    fixed_axis=(0.1, 0.2, 0.3),
                    local_axis_x=(1.0, 0.0, 0.0),
                    local_axis_z=(0.0, 0.0, 1.0),
                    external_parent_key=17,
                    ik=PmxStructuralBoneIk(
                        target_bone_index=0,
                        loop_count=8,
                        angle_limit=0.1,
                        links=(
                            PmxStructuralBoneIkLink(0),
                            PmxStructuralBoneIkLink(
                                1,
                                lower_limit=(-0.1, -0.2, -0.3),
                                upper_limit=(0.1, 0.2, 0.3),
                            ),
                        ),
                    ),
                    position="insert_before",
                    source_index=0,
                ),
            ),
        )
        preview = services.preview_structural_edit(document, request)
        inserted = preview.document.bones[0]
        expected_float = struct.unpack("<f", struct.pack("<f", 0.1))[0]

        self.assertEqual(inserted.parent_bone_index, 1)
        self.assertEqual(inserted.tail_bone_index, 2)
        self.assertEqual(inserted.inherit_parent_bone_index, 1)
        self.assertEqual(inserted.position[0], expected_float)
        self.assertEqual(inserted.inherit_weight, expected_float)
        self.assertIsNotNone(inserted.ik)
        assert inserted.ik is not None
        self.assertEqual(inserted.ik.target_bone_index, 1)
        self.assertEqual(
            tuple(link.bone_index for link in inserted.ik.links),
            (1, 2),
        )

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
        preview = services.preview_structural_edit(document, request)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(serialize_pmx(document))

            result = services.apply_structural_edit(source, output, request)

            self.assertEqual(result.document, preview.document)
            self.assertEqual(
                tuple(bone.local_name for bone in result.document.bones[:2]),
                ("First", "Second"),
            )
            self.assertEqual(result.document.bones[-1].local_name, "Append")

    def test_execution_matrix_covers_pmx20_pmx21_both_encodings_and_index_widths(
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
                        request = _append_request("互換 CP12")
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

    def test_current_index_width_expansion_is_refused_before_publication(self) -> None:
        document = _clean_document(index_size=1)
        constrained = replace(
            document,
            bones=tuple(
                document.bones[index % len(document.bones)]
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

            self.assertEqual(_failure_stage(raised.exception), "structural_certification")
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

            self.assertEqual(_failure_stage(raised.exception), "structural_certification")
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
                side_effect=RuntimeError("simulated serialization failure"),
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
            hasattr(services, "_write_pmx_bone_insertion_transaction")
        )
        self.assertFalse(
            hasattr(pmx_public, "_write_pmx_bone_insertion_transaction")
        )
        self.assertNotIn(
            "_write_pmx_bone_insertion_transaction",
            structural_output_module.__all__,
        )

        document = _clean_document()
        source_bytes = serialize_pmx(document)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            texture_output = root / "texture.pmx"
            material_output = root / "material.pmx"
            legacy_output = root / "legacy.pmx"
            source.write_bytes(source_bytes)

            texture = services.apply_structural_edit(
                source,
                texture_output,
                services.PmxStructuralEditRequest(
                    texture_insertions=(
                        PmxStructuralTextureInsertion(
                            "textures/cp12-regression.png"
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
                            local_name="CP12 material regression"
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
                "textures/cp12-regression.png",
            )
            self.assertEqual(material.status, "written")
            self.assertEqual(
                load_pmx(material_output).materials[-1].local_name,
                "CP12 material regression",
            )
            self.assertEqual(legacy.status, "no_changes")
            self.assertEqual(load_pmx(legacy_output), document)
            self.assertEqual(source.read_bytes(), source_bytes)


if __name__ == "__main__":
    unittest.main()
