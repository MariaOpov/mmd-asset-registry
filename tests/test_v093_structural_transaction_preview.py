"""Freeze CP16 complete structural transaction preview semantics."""

from __future__ import annotations

import builtins
from dataclasses import FrozenInstanceError, fields, is_dataclass, replace
import importlib
import inspect
import io
import unittest
from unittest.mock import patch

import mmd_registry
import mmd_registry.pmx as pmx
import mmd_registry.services as services
from mmd_registry.diagnostics import (
    PmxServiceDiagnosticCode,
    PmxServiceError,
    PmxServiceOperation,
)
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.services.structural_material import (
    PmxStructuralMaterialInsertion,
)
from mmd_registry.services.structural_bone import PmxStructuralBoneInsertion
from mmd_registry.services.structural_morph import (
    PmxStructuralMorphBoneOffset,
    PmxStructuralMorphImpulseOffset,
    PmxStructuralMorphInsertion,
    PmxStructuralMorphMaterialOffset,
    PmxStructuralMorphVertexOffset,
)
from mmd_registry.services.structural_reference import PmxStructuralNewReference
from mmd_registry.services.structural_rigid_body import (
    PmxStructuralRigidBodyInsertion,
)
from mmd_registry.services.structural_texture import PmxStructuralTextureInsertion
from mmd_registry.services.structural_transaction import (
    PmxStructuralTransactionPreviewResult,
    PmxStructuralTransactionRequest,
    preview_structural_transaction,
)
from mmd_registry.services.structural_vertex import (
    PmxStructuralVertexBdef1,
    PmxStructuralVertexInsertion,
)
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


PREVIEW_MODULE_NAME = "mmd_registry.pmx.structural_transaction_preview"


def _clean_document(*, index_size: int = 1):
    return replace(
        load_pmx(
            io.BytesIO(
                build_pmx_roundtrip_fixture(
                    version=2.1,
                    index_size=index_size,
                )
            )
        ),
        trailing_data=b"",
    )


def _details(error: PmxServiceError) -> dict[str, object]:
    payload = error.to_dict()
    details = payload.get("details")
    assert isinstance(details, dict)
    return details


def _material_morph_offset(reference):
    return PmxStructuralMorphMaterialOffset(
        material_index=reference,
        operation="add",
        diffuse=(0.0, 0.0, 0.0, 0.0),
        specular=(0.0, 0.0, 0.0),
        specular_strength=0.0,
        ambient=(0.0, 0.0, 0.0),
        edge_color=(0.0, 0.0, 0.0, 0.0),
        edge_scale=0.0,
        texture_tint=(0.0, 0.0, 0.0, 0.0),
        sphere_tint=(0.0, 0.0, 0.0, 0.0),
        toon_tint=(0.0, 0.0, 0.0, 0.0),
    )


class V093StructuralTransactionPreviewTests(unittest.TestCase):
    def test_explicit_public_surface_and_internal_preview_remain_bounded(
        self,
    ) -> None:
        transaction = importlib.import_module(
            "mmd_registry.services.structural_transaction"
        )
        preview_module = importlib.import_module(PREVIEW_MODULE_NAME)

        self.assertEqual(
            transaction.__all__,
            (
                "PmxStructuralTransactionOperation",
                "PmxStructuralTransactionRequest",
                "PmxStructuralTransactionPreviewResult",
                "preview_structural_transaction",
                "apply_structural_transaction",
            ),
        )
        self.assertEqual(
            tuple(inspect.signature(preview_structural_transaction).parameters),
            ("document", "request"),
        )
        for name in transaction.__all__:
            self.assertFalse(hasattr(mmd_registry, name), name)
            self.assertFalse(hasattr(services, name), name)
        self.assertFalse(hasattr(pmx, "PmxStructuralTransactionPreview"))
        self.assertTrue(hasattr(transaction, "apply_structural_transaction"))

        result = preview_structural_transaction(
            _clean_document(),
            PmxStructuralTransactionRequest(),
        )
        self.assertIsInstance(result, PmxStructuralTransactionPreviewResult)
        self.assertTrue(is_dataclass(result))
        self.assertFalse(hasattr(result, "__dict__"))
        self.assertEqual(tuple(item.name for item in fields(result)), ("_preview",))
        with self.assertRaises(FrozenInstanceError):
            result._preview = object()

        internal = result._preview
        self.assertTrue(is_dataclass(internal))
        self.assertFalse(hasattr(internal, "__dict__"))
        self.assertIn("preview_pmx_structural_transaction", preview_module.__all__)
        source = inspect.getsource(preview_module)
        for forbidden in ("open(", "pathlib", "write_pmx("):
            self.assertNotIn(forbidden, source)
        self.assertIn("serialize_pmx", source)

    def test_empty_request_is_an_unchanged_complete_certified_noop(self) -> None:
        document = _clean_document()
        request = PmxStructuralTransactionRequest()
        with patch.object(
            builtins,
            "open",
            side_effect=AssertionError("preview must not access files"),
        ):
            result = preview_structural_transaction(document, request)

        self.assertEqual(result.status, "no_changes")
        self.assertEqual(result.document, document)
        self.assertEqual(request.operations, ())
        report = result.to_dict()
        self.assertEqual(report["operations"]["original_count"], 0)
        self.assertEqual(report["operations"]["request_order"], [])
        self.assertEqual(report["operations"]["normalized_order"], [])
        self.assertEqual(report["effects"]["changed_targets"], [])
        self.assertEqual(report["effects"]["inserted_count"], 0)
        self.assertEqual(report["effects"]["deleted_count"], 0)
        self.assertEqual(report["dependencies"]["materialization_order"], [])
        self.assertEqual(report["counts"]["captured"], report["counts"]["final"])
        self.assertEqual(report["capacity"]["status"], "passed")
        self.assertEqual(
            report["verification"],
            {
                "invariants": "passed",
                "reference_model": "passed",
                "serialization": "not_performed",
            },
        )
        self.assertEqual(
            report["output"],
            {
                "written": False,
                "source_touched": False,
                "destination_touched": False,
            },
        )
        self.assertEqual(
            report["plan"]["schema"],
            "mmd_registry.structural_transaction.plan.v1",
        )
        self.assertEqual(report["plan"]["sha256"], result.plan_sha256)

    def test_identity_transform_stays_visible_without_false_changes(self) -> None:
        document = _clean_document()
        edit = services.PmxStructuralCollectionEdit(
            services.PmxReferenceTargetKind.TEXTURE,
            tuple(range(len(document.texture_paths))),
        )
        result = preview_structural_transaction(
            document,
            PmxStructuralTransactionRequest((edit,)),
        )
        report = result.to_dict()

        self.assertEqual(result.status, "no_changes")
        self.assertEqual(result.document, document)
        self.assertEqual(report["operations"]["original_count"], 1)
        self.assertEqual(len(report["operations"]["normalized_order"]), 1)
        self.assertEqual(report["effects"]["changed_targets"], [])
        collection = report["effects"]["collections"][0]
        self.assertTrue(collection["explicit_transform"])
        self.assertTrue(collection["is_noop"])
        self.assertEqual(collection["deleted_old_indices"], [])
        self.assertFalse(collection["reordered"])

    def test_forward_local_reference_reorder_and_insert_share_final_state(
        self,
    ) -> None:
        document = _clean_document()
        new_texture = PmxStructuralNewReference("texture", "texture.new")
        material = PmxStructuralMaterialInsertion(
            local_name="transaction material",
            texture_index=new_texture,
        )
        texture = PmxStructuralTextureInsertion(
            "textures/transaction.png",
            position="insert_before",
            source_index=0,
            new_id="texture.new",
        )
        reorder = services.PmxStructuralCollectionEdit(
            services.PmxReferenceTargetKind.TEXTURE,
            (2, 0, 1),
        )
        request = PmxStructuralTransactionRequest((material, texture, reorder))
        original_state = (
            document.texture_paths,
            document.materials,
            request.operations,
        )

        result = preview_structural_transaction(document, request)
        report = result.to_dict()

        self.assertEqual(result.status, "changes_pending")
        self.assertEqual(
            result.document.texture_paths,
            (
                document.texture_paths[2],
                "textures/transaction.png",
                document.texture_paths[0],
                document.texture_paths[1],
            ),
        )
        self.assertEqual(len(result.document.materials), 3)
        self.assertEqual(result.document.materials[-1].texture_index, 1)
        self.assertEqual(
            tuple(
                item["request_ordinal"]
                for item in report["operations"]["normalized_order"]
            ),
            (2, 1, 0),
        )
        self.assertEqual(
            report["dependencies"]["materialization_order"],
            ["texture", "material"],
        )
        self.assertEqual(
            report["references"]["resolved_local"],
            [
                {
                    "request_ordinal": 0,
                    "field": "material.texture_index",
                    "relationship_id": "material.texture",
                    "target_kind": "texture",
                    "new_id": "texture.new",
                    "final_index": 1,
                }
            ],
        )
        self.assertEqual(
            tuple(
                (
                    item["relationship_id"],
                    item["old_target_index"],
                    item["final_target_index"],
                )
                for item in report["references"]["remapped_existing"]
            ),
            (
                ("material.texture", 0, 2),
                ("material.sphere_texture", 1, 3),
                ("material.toon_texture", 2, 0),
            ),
        )
        self.assertEqual(
            report["counts"]["final"]["texture"],
            report["counts"]["captured"]["texture"] + 1,
        )
        self.assertEqual(
            (document.texture_paths, document.materials, request.operations),
            original_state,
        )

    def test_explicit_safe_deletion_is_distinct_from_reorder_and_insert(self) -> None:
        source = _clean_document()
        document = replace(
            source,
            texture_paths=source.texture_paths + ("textures/unused.png",),
        )
        edit = services.PmxStructuralCollectionEdit(
            services.PmxReferenceTargetKind.TEXTURE,
            (0, 1, 2),
        )
        result = preview_structural_transaction(
            document,
            PmxStructuralTransactionRequest((edit,)),
        )
        report = result.to_dict()
        collection = report["effects"]["collections"][0]

        self.assertEqual(result.document.texture_paths, source.texture_paths)
        self.assertEqual(report["effects"]["deleted_count"], 1)
        self.assertEqual(report["effects"]["inserted_count"], 0)
        self.assertEqual(report["effects"]["reordered_target_count"], 0)
        self.assertEqual(collection["deleted_old_indices"], [3])
        self.assertFalse(collection["reordered"])

    def test_complete_six_target_preview_materializes_authorized_references(
        self,
    ) -> None:
        document = _clean_document(index_size=2)
        references = {
            target: PmxStructuralNewReference(target, f"{target}.new")
            for target in (
                "texture",
                "material",
                "bone",
                "vertex",
                "rigid_body",
            )
        }
        request = PmxStructuralTransactionRequest(
            (
                PmxStructuralTextureInsertion(
                    "textures/new.png",
                    new_id="texture.new",
                ),
                PmxStructuralBoneInsertion("bone", new_id="bone.new"),
                PmxStructuralMaterialInsertion(
                    "material",
                    texture_index=references["texture"],
                    new_id="material.new",
                ),
                PmxStructuralVertexInsertion(
                    vertex_position=(0.0, 0.0, 0.0),
                    normal=(0.0, 1.0, 0.0),
                    uv=(0.0, 0.0),
                    additional_uvs=tuple(
                        (0.0, 0.0, 0.0, 0.0)
                        for _ in range(document.header.additional_uv_count)
                    ),
                    deform=PmxStructuralVertexBdef1(references["bone"]),
                    edge_scale=1.0,
                    new_id="vertex.new",
                ),
                PmxStructuralRigidBodyInsertion(
                    "rigid body",
                    bone_index=references["bone"],
                    new_id="rigid_body.new",
                ),
                PmxStructuralMorphInsertion(
                    "vertex morph",
                    "vertex",
                    offsets=(
                        PmxStructuralMorphVertexOffset(
                            references["vertex"],
                            (0.0, 0.0, 0.0),
                        ),
                    ),
                ),
                PmxStructuralMorphInsertion(
                    "bone morph",
                    "bone",
                    offsets=(
                        PmxStructuralMorphBoneOffset(
                            references["bone"],
                            (0.0, 0.0, 0.0),
                            (0.0, 0.0, 0.0, 1.0),
                        ),
                    ),
                ),
                PmxStructuralMorphInsertion(
                    "material morph",
                    "material",
                    offsets=(
                        _material_morph_offset(references["material"]),
                    ),
                ),
                PmxStructuralMorphInsertion(
                    "impulse morph",
                    "impulse",
                    offsets=(
                        PmxStructuralMorphImpulseOffset(
                            references["rigid_body"],
                            False,
                            (0.0, 0.0, 0.0),
                            (0.0, 0.0, 0.0),
                        ),
                    ),
                    new_id="morph.new",
                ),
            )
        )

        result = preview_structural_transaction(document, request)
        report = result.to_dict()

        self.assertEqual(
            report["effects"]["changed_targets"],
            ["vertex", "texture", "material", "bone", "morph", "rigid_body"],
        )
        self.assertEqual(
            report["dependencies"]["materialization_order"],
            ["texture", "material", "bone", "vertex", "rigid_body", "morph"],
        )
        self.assertEqual(len(report["references"]["resolved_local"]), 7)
        self.assertEqual(
            tuple(
                report["counts"]["final"][target]
                - report["counts"]["captured"][target]
                for target in (
                    "vertex",
                    "texture",
                    "material",
                    "bone",
                    "morph",
                    "rigid_body",
                )
            ),
            (1, 1, 1, 1, 4, 1),
        )

    def test_blockers_are_structured_stage_ordered_and_never_partial(self) -> None:
        document = _clean_document()
        bad_inputs = (
            (object(), PmxStructuralTransactionRequest()),
            (document, object()),
        )
        for candidate_document, candidate_request in bad_inputs:
            with self.subTest(candidate_request=type(candidate_request).__name__):
                with self.assertRaises(PmxServiceError) as raised:
                    preview_structural_transaction(
                        candidate_document,
                        candidate_request,
                    )
                self.assertEqual(
                    raised.exception.diagnostic.code,
                    PmxServiceDiagnosticCode.INVALID_ARGUMENT,
                )
                self.assertEqual(
                    _details(raised.exception)["stage"],
                    "service_validation",
                )

        unknown = PmxStructuralTransactionRequest(
            (
                PmxStructuralMaterialInsertion(
                    "unknown",
                    texture_index=PmxStructuralNewReference(
                        "texture",
                        "missing.texture",
                    ),
                ),
            )
        )
        with self.assertRaises(PmxServiceError) as raised_unknown:
            preview_structural_transaction(document, unknown)
        unknown_details = _details(raised_unknown.exception)
        self.assertEqual(unknown_details["stage"], "reference_resolution")
        self.assertEqual(unknown_details["operation_index"], 0)
        self.assertEqual(unknown_details["new_id"], "missing.texture")
        self.assertEqual(unknown_details["relationship_id"], "material.texture")

        deleted_anchor = PmxStructuralTransactionRequest(
            (
                services.PmxStructuralCollectionEdit(
                    services.PmxReferenceTargetKind.TEXTURE,
                    (1, 2),
                ),
                PmxStructuralTextureInsertion(
                    "textures/blocked.png",
                    position="insert_before",
                    source_index=0,
                ),
            )
        )
        with self.assertRaises(PmxServiceError) as raised_anchor:
            preview_structural_transaction(document, deleted_anchor)
        self.assertEqual(
            _details(raised_anchor.exception)["stage"],
            "transaction_normalization",
        )

        referenced_delete = PmxStructuralTransactionRequest(
            (
                services.PmxStructuralCollectionEdit(
                    services.PmxReferenceTargetKind.TEXTURE,
                    (1, 2),
                ),
            )
        )
        with self.assertRaises(PmxServiceError) as raised_delete:
            preview_structural_transaction(document, referenced_delete)
        delete_details = _details(raised_delete.exception)
        self.assertEqual(delete_details["stage"], "reference_resolution")
        self.assertEqual(delete_details["relationship_id"], "material.texture")
        self.assertFalse(delete_details["source_bytes_read"])
        self.assertFalse(delete_details["source_modified"])
        self.assertFalse(delete_details["destination_published"])

    def test_capacity_and_invariant_blockers_fail_before_success(self) -> None:
        document = _clean_document(index_size=1)
        capacity_source = replace(
            document,
            texture_paths=tuple(f"textures/{index}.png" for index in range(128)),
        )
        capacity_request = PmxStructuralTransactionRequest(
            (PmxStructuralTextureInsertion("textures/overflow.png"),)
        )
        with self.assertRaises(PmxServiceError) as raised_capacity:
            preview_structural_transaction(capacity_source, capacity_request)
        self.assertEqual(
            _details(raised_capacity.exception)["stage"],
            "capacity_preflight",
        )

        invalid_source = replace(document, trailing_data=b"private")
        with self.assertRaises(PmxServiceError) as raised_invariant:
            preview_structural_transaction(
                invalid_source,
                PmxStructuralTransactionRequest(),
            )
        self.assertEqual(
            _details(raised_invariant.exception)["stage"],
            "structural_certification",
        )
        invalid_overflow_source = replace(
            capacity_source,
            trailing_data=b"private",
        )
        with self.assertRaises(PmxServiceError) as raised_earliest:
            preview_structural_transaction(
                invalid_overflow_source,
                capacity_request,
            )
        self.assertEqual(
            _details(raised_earliest.exception)["stage"],
            "structural_certification",
        )
        for error in (
            raised_capacity.exception,
            raised_invariant.exception,
            raised_earliest.exception,
        ):
            self.assertEqual(
                error.diagnostic.operation,
                PmxServiceOperation.PREVIEW_STRUCTURAL_TRANSACTION,
            )
            self.assertEqual(
                error.diagnostic.code,
                PmxServiceDiagnosticCode.STRUCTURAL_PREVIEW_FAILED,
            )

    def test_payload_blockers_preflight_before_any_target_materialization(
        self,
    ) -> None:
        document = _clean_document()
        request = PmxStructuralTransactionRequest(
            (
                PmxStructuralTextureInsertion("textures/not-materialized.png"),
                PmxStructuralBoneInsertion("x" * 1_000_001),
            )
        )
        preview_module = importlib.import_module(PREVIEW_MODULE_NAME)
        materializers = tuple(
            f"preview_pmx_{target}_insertions"
            for target in (
                "vertex",
                "texture",
                "material",
                "bone",
                "morph",
                "rigid_body",
            )
        )

        with patch.multiple(
            preview_module,
            **{
                name: unittest.mock.DEFAULT
                for name in materializers
            },
        ) as mocks:
            with self.assertRaises(PmxServiceError) as raised:
                preview_structural_transaction(document, request)

        details = _details(raised.exception)
        self.assertEqual(details["stage"], "capacity_preflight")
        self.assertEqual(details["target_kind"], "bone")
        self.assertTrue(all(not mock.called for mock in mocks.values()))

    def test_earliest_reference_blocker_precedes_capacity_preflight(self) -> None:
        document = replace(
            _clean_document(index_size=1),
            texture_paths=tuple(
                f"textures/{index}.png" for index in range(128)
            ),
        )
        request = PmxStructuralTransactionRequest(
            (
                PmxStructuralMaterialInsertion(
                    "unknown reference",
                    texture_index=PmxStructuralNewReference(
                        "texture",
                        "missing.texture",
                    ),
                ),
                PmxStructuralTextureInsertion("textures/overflow.png"),
            )
        )

        with self.assertRaises(PmxServiceError) as raised:
            preview_structural_transaction(document, request)

        details = _details(raised.exception)
        self.assertEqual(details["stage"], "reference_resolution")
        self.assertEqual(details["operation_index"], 0)
        self.assertEqual(details["new_id"], "missing.texture")

    def test_deleted_existing_reference_precedes_capacity_preflight(self) -> None:
        document = replace(
            _clean_document(index_size=1),
            texture_paths=tuple(
                f"textures/{index}.png" for index in range(128)
            ),
        )
        request = PmxStructuralTransactionRequest(
            (
                services.PmxStructuralCollectionEdit(
                    services.PmxReferenceTargetKind.TEXTURE,
                    tuple(range(1, 128)),
                ),
                PmxStructuralTextureInsertion("textures/overflow-a.png"),
                PmxStructuralTextureInsertion("textures/overflow-b.png"),
            )
        )

        with self.assertRaises(PmxServiceError) as raised:
            preview_structural_transaction(document, request)

        details = _details(raised.exception)
        self.assertEqual(details["stage"], "reference_resolution")
        self.assertEqual(details["relationship_id"], "material.texture")

    def test_normalization_blocker_precedes_reference_and_capacity(self) -> None:
        document = replace(
            _clean_document(index_size=1),
            texture_paths=tuple(
                f"textures/{index}.png" for index in range(128)
            ),
        )
        request = PmxStructuralTransactionRequest(
            (
                services.PmxStructuralCollectionEdit(
                    services.PmxReferenceTargetKind.TEXTURE,
                    tuple(range(1, 128)),
                ),
                PmxStructuralTextureInsertion(
                    "textures/deleted-anchor.png",
                    position="insert_before",
                    source_index=0,
                ),
                PmxStructuralTextureInsertion("textures/overflow.png"),
            )
        )

        with self.assertRaises(PmxServiceError) as raised:
            preview_structural_transaction(document, request)

        self.assertEqual(
            _details(raised.exception)["stage"],
            "transaction_normalization",
        )

    def test_repeated_preview_is_deterministic_and_has_no_filesystem_hook(self) -> None:
        document = _clean_document()
        request = PmxStructuralTransactionRequest(
            (
                PmxStructuralTextureInsertion(
                    "textures/deterministic.png",
                    new_id="deterministic.texture",
                ),
            )
        )
        original = (document, request)
        with patch.object(
            builtins,
            "open",
            side_effect=AssertionError("preview must not access files"),
        ):
            reports = tuple(
                preview_structural_transaction(document, request).to_dict()
                for _ in range(10)
            )

        self.assertTrue(all(report == reports[0] for report in reports))
        self.assertEqual((document, request), original)
        self.assertRegex(reports[0]["plan"]["sha256"], r"\A[0-9a-f]{64}\Z")


if __name__ == "__main__":
    unittest.main()
