"""CP14 rigid-body insertion execution and transaction-safety coverage."""

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
    PmxStructuralMorphImpulseOffset,
    PmxStructuralMorphInsertion,
)
from mmd_registry.services.structural_rigid_body import (
    PmxStructuralRigidBodyInsertion,
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
    name: str = "CP14 appended",
    *,
    value: float = 0.1,
):
    return PmxStructuralRigidBodyInsertion(
        local_name=name,
        size=(1.0, 1.0, 1.0),
        body_position=(value, value, value),
        rotation=(value, value, value),
        mass=1.0,
        linear_damping=value,
        angular_damping=value,
        restitution=value,
        friction=value,
    )


def _append_request(name: str = "CP14 appended"):
    return services.PmxStructuralEditRequest(
        rigid_body_insertions=(_append_insertion(name),),
    )


def _temporary_outputs(destination: Path) -> tuple[Path, ...]:
    return tuple(destination.parent.glob(f".{destination.name}.*.tmp"))


def _failure_stage(error: PmxServiceError) -> str:
    return str(error.to_dict()["details"]["stage"])


class RigidBodyInsertionExecutionTests(unittest.TestCase):
    def test_append_execution_matches_preview_reparse_report_and_is_deterministic(
        self,
    ) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)
        request = _append_request("private-cp14-rigid-name")
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
            self.assertNotIn(
                "private-cp14-rigid-name",
                json.dumps(report, ensure_ascii=False, sort_keys=True),
            )

    def test_insert_before_incoming_references_and_float32_match_preview(self) -> None:
        document = _clean_document(version=2.1)
        value = 0.1
        canonical = struct.unpack("<f", struct.pack("<f", value))[0]
        request = services.PmxStructuralEditRequest(
            rigid_body_insertions=(
                PmxStructuralRigidBodyInsertion(
                    local_name="before",
                    body_position=(value, value, value),
                    rotation=(value, value, value),
                    linear_damping=value,
                    angular_damping=value,
                    restitution=value,
                    friction=value,
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
            source_bytes = serialize_pmx(document)
            source.write_bytes(source_bytes)
            result = services.apply_structural_edit(source, output, request)
            written = load_pmx(output)

            self.assertEqual(result.document, preview.document)
            self.assertEqual(written, preview.document)
            self.assertEqual(written.rigid_bodies[0].position, (canonical,) * 3)
            self.assertEqual(
                written.header.index_sizes.rigid_body,
                document.header.index_sizes.rigid_body,
            )
            self.assertEqual(
                result.to_dict()["verification"]["reference_model"],
                "passed",
            )
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_same_anchor_and_append_order_survives_execution(self) -> None:
        document = _clean_document()
        request = services.PmxStructuralEditRequest(
            rigid_body_insertions=(
                PmxStructuralRigidBodyInsertion(
                    local_name="A",
                    position="insert_before",
                    source_index=0,
                ),
                PmxStructuralRigidBodyInsertion(
                    local_name="B",
                    position="insert_before",
                    source_index=0,
                ),
                PmxStructuralRigidBodyInsertion(local_name="C"),
                PmxStructuralRigidBodyInsertion(local_name="D"),
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(serialize_pmx(document))
            services.apply_structural_edit(source, output, request)
            written = load_pmx(output)
            self.assertEqual(
                [body.local_name for body in written.rigid_bodies[:2]],
                ["A", "B"],
            )
            self.assertEqual(
                [body.local_name for body in written.rigid_bodies[-2:]],
                ["C", "D"],
            )

    def test_execution_matrix_covers_versions_encodings_and_index_widths(self) -> None:
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
                        with tempfile.TemporaryDirectory() as directory:
                            root = Path(directory)
                            source = root / "source.pmx"
                            output = root / "output.pmx"
                            source.write_bytes(source_bytes)
                            result = services.apply_structural_edit(
                                source,
                                output,
                                _append_request("互換 CP14"),
                            )
                            self.assertEqual(
                                load_pmx(output),
                                result.document,
                            )
                            self.assertEqual(
                                result.document.header.index_sizes.rigid_body,
                                index_size,
                            )
                            self.assertEqual(source.read_bytes(), source_bytes)

    def test_pmx21_impulse_execution_targets_source_rigid_body(self) -> None:
        document = _clean_document(version=2.1)
        request = services.PmxStructuralEditRequest(
            morph_insertions=(
                PmxStructuralMorphInsertion(
                    local_name="CP14 impulse",
                    morph_type="impulse",
                    offsets=(
                        PmxStructuralMorphImpulseOffset(
                            rigid_body_index=0,
                            local=True,
                            velocity=(0.1, 0.2, 0.3),
                            angular_torque=(0.4, 0.5, 0.6),
                        ),
                    ),
                ),
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
            self.assertEqual(load_pmx(output), preview.document)
            self.assertEqual(
                result.document.morphs[-1].offsets[0].rigid_body_index,
                0,
            )

    def test_current_rigid_body_index_width_expansion_is_refused_before_publication(
        self,
    ) -> None:
        document = _clean_document(index_size=1)
        template = document.rigid_bodies[0]
        constrained = replace(
            document,
            rigid_bodies=tuple(
                replace(template, local_name=f"Rigid {index}")
                for index in range(128)
            ),
        )
        source_bytes = serialize_pmx(constrained)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)
            with self.assertRaises(PmxServiceError):
                services.apply_structural_edit(source, output, _append_request())
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


    def test_private_boundary_capability_and_prior_execution_paths_remain_stable(
        self,
    ) -> None:
        manifest = services.get_capabilities().to_dict()
        self.assertNotIn("structural_insert", manifest)
        self.assertFalse(
            hasattr(services, "_write_pmx_rigid_body_insertion_transaction")
        )
        self.assertFalse(
            hasattr(pmx_public, "_write_pmx_rigid_body_insertion_transaction")
        )
        self.assertNotIn(
            "_write_pmx_rigid_body_insertion_transaction",
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
            morph_output = root / "morph.pmx"
            source.write_bytes(source_bytes)

            texture = services.apply_structural_edit(
                source,
                texture_output,
                services.PmxStructuralEditRequest(
                    texture_insertions=(
                        PmxStructuralTextureInsertion(
                            "textures/cp14-regression.png"
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
                            local_name="CP14 material regression"
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
                            local_name="CP14 bone regression"
                        ),
                    ),
                ),
            )
            morph = services.apply_structural_edit(
                source,
                morph_output,
                services.PmxStructuralEditRequest(
                    morph_insertions=(
                        PmxStructuralMorphInsertion(
                            local_name="CP14 morph regression",
                            morph_type="vertex",
                        ),
                    ),
                ),
            )

            self.assertEqual(texture.status, "written")
            self.assertEqual(material.status, "written")
            self.assertEqual(bone.status, "written")
            self.assertEqual(morph.status, "written")
            self.assertEqual(source.read_bytes(), source_bytes)


if __name__ == "__main__":
    unittest.main()
