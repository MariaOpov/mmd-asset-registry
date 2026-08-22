"""CP19 cross-target structural insertion atomicity and failure-residue gates."""

from __future__ import annotations

import io
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import mmd_registry.services as services
from mmd_registry.diagnostics import PmxServiceError
from mmd_registry.pmx import structural_output as structural_output_module
from mmd_registry.pmx.editing import output as edit_output
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.writer import serialize_pmx
from mmd_registry.services.structural_bone import PmxStructuralBoneInsertion
from mmd_registry.services.structural_material import PmxStructuralMaterialInsertion
from mmd_registry.services.structural_morph import (
    PmxStructuralMorphInsertion,
    PmxStructuralMorphVertexOffset,
)
from mmd_registry.services.structural_reference import PmxStructuralNewReference
from mmd_registry.services.structural_rigid_body import PmxStructuralRigidBodyInsertion
from mmd_registry.services.structural_texture import PmxStructuralTextureInsertion
from mmd_registry.services.structural_vertex import (
    PmxStructuralVertexBdef1,
    PmxStructuralVertexInsertion,
)
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


def _clean_document():
    return replace(
        load_pmx(
            io.BytesIO(
                build_pmx_roundtrip_fixture(
                    version=2.1,
                    index_size=1,
                )
            )
        ),
        trailing_data=b"",
    )


def _source_bytes() -> bytes:
    return serialize_pmx(_clean_document())


def _vertex(deform):
    return PmxStructuralVertexInsertion(
        vertex_position=(1.0, 2.0, 3.0),
        normal=(0.0, 1.0, 0.0),
        uv=(0.25, 0.75),
        additional_uvs=(
            (0.1, 0.2, 0.3, 0.4),
            (1.1, 1.2, 1.3, 1.4),
            (2.1, 2.2, 2.3, 2.4),
            (3.1, 3.2, 3.3, 3.4),
        ),
        deform=deform,
        edge_scale=1.0,
    )


def _coordinated_request():
    return services.PmxStructuralEditRequest(
        bone_insertions=(
            PmxStructuralBoneInsertion(
                local_name="CP19 coordinated bone",
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


def _single_target_requests():
    return (
        (
            "texture",
            services.PmxStructuralEditRequest(
                texture_insertions=(
                    PmxStructuralTextureInsertion("textures/cp19.png"),
                ),
            ),
        ),
        (
            "material",
            services.PmxStructuralEditRequest(
                material_insertions=(
                    PmxStructuralMaterialInsertion(local_name="CP19 material"),
                ),
            ),
        ),
        (
            "bone",
            services.PmxStructuralEditRequest(
                bone_insertions=(
                    PmxStructuralBoneInsertion(local_name="CP19 bone"),
                ),
            ),
        ),
        (
            "vertex",
            services.PmxStructuralEditRequest(
                vertex_insertions=(
                    _vertex(PmxStructuralVertexBdef1(0)),
                ),
            ),
        ),
        (
            "rigid_body",
            services.PmxStructuralEditRequest(
                rigid_body_insertions=(
                    PmxStructuralRigidBodyInsertion(
                        local_name="CP19 rigid body",
                        bone_index=0,
                    ),
                ),
            ),
        ),
        (
            "morph",
            services.PmxStructuralEditRequest(
                morph_insertions=(
                    PmxStructuralMorphInsertion(
                        local_name="CP19 morph",
                        morph_type="vertex",
                        offsets=(
                            PmxStructuralMorphVertexOffset(
                                0,
                                (0.1, 0.0, 0.0),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )


def _temporary_outputs(destination: Path) -> tuple[Path, ...]:
    return tuple(destination.parent.glob(f".{destination.name}.*.tmp"))


def _failure_stage(error: PmxServiceError) -> str:
    return str(error.to_dict()["details"]["stage"])


class StructuralInsertionAtomicityTests(unittest.TestCase):
    def test_all_six_single_targets_and_coordinated_path_use_shared_kernel(self) -> None:
        source_bytes = _source_bytes()
        requests = (*_single_target_requests(), ("coordinated", _coordinated_request()))
        original_kernel = structural_output_module._write_verified_structural_transaction

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            source.write_bytes(source_bytes)

            with patch.object(
                structural_output_module,
                "_write_verified_structural_transaction",
                wraps=original_kernel,
            ) as shared_kernel:
                for name, request in requests:
                    with self.subTest(target=name):
                        output = root / f"{name}.pmx"
                        result = services.apply_structural_edit(source, output, request)
                        self.assertEqual(result.status, "written")
                        self.assertEqual(load_pmx(output), result.document)
                        self.assertEqual(_temporary_outputs(output), ())

            self.assertEqual(shared_kernel.call_count, 7)
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_coordinated_success_preserves_source_and_leaves_no_temp_residue(self) -> None:
        source_bytes = _source_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)

            result = services.apply_structural_edit(
                source,
                output,
                _coordinated_request(),
            )

            self.assertEqual(result.status, "written")
            self.assertEqual(load_pmx(output), result.document)
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(_temporary_outputs(output), ())

    def test_coordinated_existing_destination_refuses_then_explicit_overwrite_succeeds(
        self,
    ) -> None:
        source_bytes = _source_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)
            output.write_bytes(b"existing")

            with self.assertRaises(PmxServiceError) as raised:
                services.apply_structural_edit(source, output, _coordinated_request())

            self.assertEqual(_failure_stage(raised.exception), "path_resolution")
            self.assertEqual(output.read_bytes(), b"existing")
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(_temporary_outputs(output), ())

            result = services.apply_structural_edit(
                source,
                output,
                _coordinated_request(),
                overwrite=True,
            )

            self.assertEqual(result.status, "written")
            self.assertEqual(load_pmx(output), result.document)
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(_temporary_outputs(output), ())

    def test_coordinated_in_place_is_refused_even_with_overwrite(self) -> None:
        source_bytes = _source_bytes()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.pmx"
            source.write_bytes(source_bytes)

            with self.assertRaises(PmxServiceError) as raised:
                services.apply_structural_edit(
                    source,
                    source,
                    _coordinated_request(),
                    overwrite=True,
                )

            self.assertEqual(_failure_stage(raised.exception), "path_resolution")
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_coordinated_serialization_failure_publishes_nothing(self) -> None:
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
                    services.apply_structural_edit(
                        source,
                        output,
                        _coordinated_request(),
                    )

            self.assertEqual(_failure_stage(raised.exception), "serialization")
            self.assertFalse(output.exists())
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(_temporary_outputs(output), ())

    def test_coordinated_reparse_failure_publishes_nothing(self) -> None:
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
                    services.apply_structural_edit(
                        source,
                        output,
                        _coordinated_request(),
                    )

            self.assertEqual(_failure_stage(raised.exception), "reparse")
            self.assertFalse(output.exists())
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(_temporary_outputs(output), ())

    def test_coordinated_reparse_certification_failure_publishes_nothing(self) -> None:
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
                    services.apply_structural_edit(
                        source,
                        output,
                        _coordinated_request(),
                    )

            self.assertEqual(
                _failure_stage(raised.exception),
                "reparse_certification",
            )
            self.assertFalse(output.exists())
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(_temporary_outputs(output), ())

    def test_coordinated_semantic_mismatch_publishes_nothing(self) -> None:
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
                    services.apply_structural_edit(
                        source,
                        output,
                        _coordinated_request(),
                    )

            self.assertEqual(_failure_stage(raised.exception), "semantic_compare")
            self.assertFalse(output.exists())
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(_temporary_outputs(output), ())

    def test_coordinated_source_race_fails_closed_and_cleans_temp(self) -> None:
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
                    services.apply_structural_edit(
                        source,
                        output,
                        _coordinated_request(),
                    )

            self.assertEqual(_failure_stage(raised.exception), "output_commit")
            self.assertFalse(output.exists())
            self.assertEqual(_temporary_outputs(output), ())

    def test_coordinated_destination_race_preserves_racer_and_cleans_temp(self) -> None:
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
                    services.apply_structural_edit(
                        source,
                        output,
                        _coordinated_request(),
                    )

            self.assertEqual(_failure_stage(raised.exception), "output_commit")
            self.assertEqual(output.read_bytes(), b"racer")
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(_temporary_outputs(output), ())

    def test_coordinated_replace_failure_preserves_existing_and_cleans_temp(self) -> None:
        source_bytes = _source_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)
            output.write_bytes(b"existing")

            with patch.object(
                edit_output.os,
                "replace",
                side_effect=OSError("simulated replace failure"),
            ):
                with self.assertRaises(PmxServiceError) as raised:
                    services.apply_structural_edit(
                        source,
                        output,
                        _coordinated_request(),
                        overwrite=True,
                    )

            self.assertEqual(_failure_stage(raised.exception), "output_commit")
            self.assertEqual(output.read_bytes(), b"existing")
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(_temporary_outputs(output), ())

    def test_release_freezes_remain_unpromoted(self) -> None:
        self.assertIs((services.get_capabilities().to_dict())["structural_insert"], True)
        self.assertIs(
            services.PmxStructuralEditRequest,
            services.PmxStructuralPreviewRequest,
        )


if __name__ == "__main__":
    unittest.main()
