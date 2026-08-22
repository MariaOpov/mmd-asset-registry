"""CP20 v0.9.2 structural insertion diagnostics and provenance gates."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import mmd_registry.services as services
from mmd_registry.diagnostics import (
    PmxServiceDiagnosticCode,
    PmxServiceError,
)
from mmd_registry.pmx import structural_output as structural_output_module
from mmd_registry.pmx.editing import output as edit_output
from mmd_registry.pmx.editing.errors import PmxEditVerificationError
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


PRIVATE_EXCEPTION = r"C:\private\秘密-cp20-diagnostic.pmx"
PRIVATE_NAME = "private-cp20-inserted-name"
PRIVATE_TEXTURE = "textures/private-cp20-secret.png"

EXPECTED_STAGE_PROVENANCE = (
    ("service_validation", "service_boundary"),
    ("path_resolution", "safe_output"),
    ("source_snapshot", "source_input"),
    ("source_parse", "source_input"),
    ("intent_resolution", "service_boundary"),
    ("structural_certification", "structural_pipeline"),
    ("serialization", "structural_pipeline"),
    ("reparse", "structural_pipeline"),
    ("reparse_certification", "structural_pipeline"),
    ("semantic_compare", "structural_pipeline"),
    ("output_commit", "safe_output"),
)

BOUNDED_DETAIL_KEYS = frozenset(
    {
        "errno",
        "field",
        "format_name",
        "offset",
        "parse_operation",
        "provenance",
        "reason",
        "record_index",
        "section",
        "stage",
    }
)


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
                local_name="CP20 coordinated bone",
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


def _private_coordinated_request():
    return services.PmxStructuralEditRequest(
        texture_insertions=(
            PmxStructuralTextureInsertion(PRIVATE_TEXTURE),
        ),
        bone_insertions=(
            PmxStructuralBoneInsertion(local_name=PRIVATE_NAME),
        ),
    )


def _unknown_reference_request():
    return services.PmxStructuralEditRequest(
        bone_insertions=(
            PmxStructuralBoneInsertion(local_name="known", new_id="known"),
        ),
        vertex_insertions=(
            _vertex(
                PmxStructuralVertexBdef1(
                    PmxStructuralNewReference("bone", "missing")
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
                    PmxStructuralTextureInsertion("textures/cp20.png"),
                ),
            ),
        ),
        (
            "material",
            services.PmxStructuralEditRequest(
                material_insertions=(
                    PmxStructuralMaterialInsertion(local_name="CP20 material"),
                ),
            ),
        ),
        (
            "bone",
            services.PmxStructuralEditRequest(
                bone_insertions=(
                    PmxStructuralBoneInsertion(local_name="CP20 bone"),
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
                        local_name="CP20 rigid body",
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
                        local_name="CP20 morph",
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


def _payload(error: PmxServiceError) -> dict[str, object]:
    payload = error.to_dict()
    json.dumps(payload, ensure_ascii=False, allow_nan=False, sort_keys=True)
    return payload


def _assert_failure(
    case: unittest.TestCase,
    error: PmxServiceError,
    *,
    code: PmxServiceDiagnosticCode,
    stage: str,
    provenance: str,
    forbidden: tuple[str, ...] = (),
) -> dict[str, object]:
    case.assertEqual(error.diagnostic.code, code)
    payload = _payload(error)
    case.assertEqual(payload["operation"], "apply_structural_edit")
    details = payload.get("details")
    case.assertIsInstance(details, dict)
    assert isinstance(details, dict)
    case.assertEqual(details["stage"], stage)
    case.assertEqual(details["provenance"], provenance)
    case.assertTrue(set(details).issubset(BOUNDED_DETAIL_KEYS))
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
    )
    for secret in (PRIVATE_EXCEPTION, PRIVATE_NAME, PRIVATE_TEXTURE, *forbidden):
        case.assertNotIn(secret, encoded)
    return payload


class StructuralInsertionFailureProvenanceTests(unittest.TestCase):
    def test_frozen_stage_vocabulary_and_provenance_mapping(self) -> None:
        self.assertEqual(
            services._STRUCTURAL_FAILURE_PROVENANCE,
            EXPECTED_STAGE_PROVENANCE,
        )
        self.assertIsInstance(services._STRUCTURAL_FAILURE_PROVENANCE, tuple)
        for stage, provenance in EXPECTED_STAGE_PROVENANCE:
            self.assertEqual(
                services._structural_failure_provenance(stage),
                provenance,
            )

    def test_boundary_and_source_failures_are_bounded_and_redacted(self) -> None:
        with self.subTest(stage="service_validation"):
            with self.assertRaises(PmxServiceError) as raised:
                services.apply_structural_edit(
                    PRIVATE_EXCEPTION,
                    "private-output.pmx",
                    object(),  # type: ignore[arg-type]
                )
            payload = _assert_failure(
                self,
                raised.exception,
                code=PmxServiceDiagnosticCode.INVALID_ARGUMENT,
                stage="service_validation",
                provenance="service_boundary",
            )
            self.assertEqual(
                set(payload["details"]),  # type: ignore[arg-type]
                {"provenance", "stage"},
            )

        source_bytes = _source_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)

            with self.subTest(stage="path_resolution"):
                with self.assertRaises(PmxServiceError) as raised:
                    services.apply_structural_edit(
                        source,
                        source,
                        _coordinated_request(),
                        overwrite=True,
                    )
                payload = _assert_failure(
                    self,
                    raised.exception,
                    code=PmxServiceDiagnosticCode.STRUCTURAL_PATH_UNSAFE,
                    stage="path_resolution",
                    provenance="safe_output",
                    forbidden=(str(source),),
                )
                self.assertEqual(
                    set(payload["details"]),  # type: ignore[arg-type]
                    {"provenance", "stage"},
                )

            with self.subTest(stage="source_snapshot"):
                with patch.object(
                    edit_output,
                    "_file_identity",
                    side_effect=PermissionError(13, PRIVATE_EXCEPTION),
                ):
                    with self.assertRaises(PmxServiceError) as raised:
                        services.apply_structural_edit(
                            source,
                            output,
                            _coordinated_request(),
                        )
                payload = _assert_failure(
                    self,
                    raised.exception,
                    code=PmxServiceDiagnosticCode.IO_FAILED,
                    stage="source_snapshot",
                    provenance="source_input",
                )
                self.assertEqual(
                    payload["details"],  # type: ignore[index]
                    {
                        "errno": 13,
                        "provenance": "source_input",
                        "stage": "source_snapshot",
                    },
                )

        malformed = _source_bytes()[:12]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "malformed.pmx"
            output = root / "output.pmx"
            source.write_bytes(malformed)

            with self.subTest(stage="source_parse"):
                with self.assertRaises(PmxServiceError) as raised:
                    services.apply_structural_edit(
                        source,
                        output,
                        _coordinated_request(),
                    )
                _assert_failure(
                    self,
                    raised.exception,
                    code=PmxServiceDiagnosticCode.SOURCE_INVALID,
                    stage="source_parse",
                    provenance="source_input",
                )

    def test_intent_and_structural_certification_failures_have_correct_provenance(
        self,
    ) -> None:
        source_bytes = _source_bytes()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)

            with self.subTest(stage="intent_resolution"):
                with self.assertRaises(PmxServiceError) as raised:
                    services.apply_structural_edit(
                        source,
                        output,
                        _unknown_reference_request(),
                    )
                _assert_failure(
                    self,
                    raised.exception,
                    code=PmxServiceDiagnosticCode.STRUCTURAL_VERIFICATION_FAILED,
                    stage="intent_resolution",
                    provenance="service_boundary",
                )

        unsafe_bytes = build_pmx_roundtrip_fixture(
            version=2.1,
            index_size=1,
        )
        self.assertTrue(load_pmx(io.BytesIO(unsafe_bytes)).trailing_data)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(unsafe_bytes)

            with self.subTest(stage="structural_certification"):
                with self.assertRaises(PmxServiceError) as raised:
                    services.apply_structural_edit(
                        source,
                        output,
                        _coordinated_request(),
                    )
                _assert_failure(
                    self,
                    raised.exception,
                    code=PmxServiceDiagnosticCode.STRUCTURAL_VERIFICATION_FAILED,
                    stage="structural_certification",
                    provenance="structural_pipeline",
                )

    def test_serialization_failure_is_consistent_across_all_target_families(
        self,
    ) -> None:
        source_bytes = _source_bytes()
        requests = (*_single_target_requests(), ("coordinated", _coordinated_request()))
        observed: list[dict[str, object]] = []

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            source.write_bytes(source_bytes)

            for name, request in requests:
                with self.subTest(target=name):
                    output = root / f"{name}.pmx"
                    with patch.object(
                        structural_output_module,
                        "serialize_pmx",
                        side_effect=ValueError(PRIVATE_EXCEPTION),
                    ):
                        with self.assertRaises(PmxServiceError) as raised:
                            services.apply_structural_edit(
                                source,
                                output,
                                request,
                            )
                    observed.append(
                        _assert_failure(
                            self,
                            raised.exception,
                            code=(
                                PmxServiceDiagnosticCode
                                .STRUCTURAL_VERIFICATION_FAILED
                            ),
                            stage="serialization",
                            provenance="structural_pipeline",
                        )
                    )
                    self.assertFalse(output.exists())

        self.assertEqual(len(observed), 7)
        self.assertTrue(all(payload == observed[0] for payload in observed[1:]))

    def test_coordinated_reparse_certification_and_semantic_stages_are_bounded(
        self,
    ) -> None:
        source_document = _clean_document()
        source_bytes = serialize_pmx(source_document)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "reparse.pmx"
            source.write_bytes(source_bytes)
            original_load = structural_output_module.load_pmx
            calls = 0

            def fail_second_load(value):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise ValueError(PRIVATE_EXCEPTION)
                return original_load(value)

            with patch.object(
                structural_output_module,
                "load_pmx",
                side_effect=fail_second_load,
            ):
                with self.assertRaises(PmxServiceError) as raised:
                    services.apply_structural_edit(
                        source,
                        output,
                        _private_coordinated_request(),
                    )
            _assert_failure(
                self,
                raised.exception,
                code=PmxServiceDiagnosticCode.STRUCTURAL_VERIFICATION_FAILED,
                stage="reparse",
                provenance="structural_pipeline",
            )
            self.assertFalse(output.exists())

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "certification.pmx"
            source.write_bytes(source_bytes)

            with patch.object(
                structural_output_module,
                "PmxStructuralInvariantCertificate",
                side_effect=ValueError(PRIVATE_EXCEPTION),
            ):
                with self.assertRaises(PmxServiceError) as raised:
                    services.apply_structural_edit(
                        source,
                        output,
                        _private_coordinated_request(),
                    )
            _assert_failure(
                self,
                raised.exception,
                code=PmxServiceDiagnosticCode.STRUCTURAL_VERIFICATION_FAILED,
                stage="reparse_certification",
                provenance="structural_pipeline",
            )
            self.assertFalse(output.exists())

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "semantic.pmx"
            source.write_bytes(source_bytes)
            original_load = structural_output_module.load_pmx
            calls = 0

            def mismatch_second_load(value):
                nonlocal calls
                calls += 1
                if calls == 2:
                    return source_document
                return original_load(value)

            with patch.object(
                structural_output_module,
                "load_pmx",
                side_effect=mismatch_second_load,
            ):
                with self.assertRaises(PmxServiceError) as raised:
                    services.apply_structural_edit(
                        source,
                        output,
                        _private_coordinated_request(),
                    )
            _assert_failure(
                self,
                raised.exception,
                code=PmxServiceDiagnosticCode.STRUCTURAL_VERIFICATION_FAILED,
                stage="semantic_compare",
                provenance="structural_pipeline",
            )
            self.assertFalse(output.exists())

    def test_output_commit_failure_is_safe_output_and_redacted(self) -> None:
        source_bytes = _source_bytes()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)

            with patch.object(
                edit_output,
                "_commit_verified_bytes",
                side_effect=PmxEditVerificationError(PRIVATE_EXCEPTION),
            ):
                with self.assertRaises(PmxServiceError) as raised:
                    services.apply_structural_edit(
                        source,
                        output,
                        _private_coordinated_request(),
                    )

            payload = _assert_failure(
                self,
                raised.exception,
                code=PmxServiceDiagnosticCode.STRUCTURAL_VERIFICATION_FAILED,
                stage="output_commit",
                provenance="safe_output",
                forbidden=(str(source), str(output)),
            )
            self.assertEqual(
                set(payload["details"]),  # type: ignore[arg-type]
                {"provenance", "stage"},
            )
            self.assertFalse(output.exists())

    def test_private_inserted_payload_and_exception_text_never_escape(self) -> None:
        source_bytes = _source_bytes()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)

            with patch.object(
                structural_output_module,
                "serialize_pmx",
                side_effect=ValueError(PRIVATE_EXCEPTION),
            ):
                with self.assertRaises(PmxServiceError) as raised:
                    services.apply_structural_edit(
                        source,
                        output,
                        _private_coordinated_request(),
                    )

            payload = _assert_failure(
                self,
                raised.exception,
                code=PmxServiceDiagnosticCode.STRUCTURAL_VERIFICATION_FAILED,
                stage="serialization",
                provenance="structural_pipeline",
                forbidden=(str(source), str(output)),
            )
            encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            self.assertNotIn(PRIVATE_NAME, encoded)
            self.assertNotIn(PRIVATE_TEXTURE, encoded)
            self.assertNotIn(PRIVATE_EXCEPTION, encoded)

    def test_repeated_identical_failure_has_exact_deterministic_payload(self) -> None:
        source_bytes = _source_bytes()
        payloads: list[dict[str, object]] = []

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)

            for _ in range(2):
                with patch.object(
                    structural_output_module,
                    "serialize_pmx",
                    side_effect=ValueError(PRIVATE_EXCEPTION),
                ):
                    with self.assertRaises(PmxServiceError) as raised:
                        services.apply_structural_edit(
                            source,
                            output,
                            _private_coordinated_request(),
                        )
                payloads.append(
                    _assert_failure(
                        self,
                        raised.exception,
                        code=(
                            PmxServiceDiagnosticCode
                            .STRUCTURAL_VERIFICATION_FAILED
                        ),
                        stage="serialization",
                        provenance="structural_pipeline",
                    )
                )

        self.assertEqual(payloads[0], payloads[1])
        self.assertEqual(
            json.dumps(payloads[0], ensure_ascii=False, sort_keys=True),
            json.dumps(payloads[1], ensure_ascii=False, sort_keys=True),
        )

    def test_release_freezes_remain_unpromoted(self) -> None:
        self.assertNotIn("structural_insert", services.get_capabilities().to_dict())
        self.assertIs(
            services.PmxStructuralEditRequest,
            services.PmxStructuralPreviewRequest,
        )


if __name__ == "__main__":
    unittest.main()
