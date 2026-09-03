"""v0.9.5 builder boundary tests for structural authoring."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import inspect
import unittest
from unittest.mock import patch

import mmd_registry.services as services
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.pmx.transaction_plan import (
    PmxStructuralTransactionPlan,
    parse_pmx_structural_transaction_plan_json,
    render_pmx_structural_transaction_plan_json,
)
from mmd_registry.services import structural_authoring_builder as builder
from mmd_registry.services.structural_authoring_selector import (
    PmxStructuralAuthoringSelectorField,
    PmxStructuralAuthoringSelectorResolution,
)
from mmd_registry.services.structural_bone import PmxStructuralBoneInsertion
from mmd_registry.services.structural_material import PmxStructuralMaterialInsertion
from mmd_registry.services.structural_morph import PmxStructuralMorphInsertion
from mmd_registry.services.structural_rigid_body import (
    PmxStructuralRigidBodyInsertion,
)
from mmd_registry.services.structural_texture import PmxStructuralTextureInsertion
from mmd_registry.services.structural_vertex import (
    PmxStructuralVertexBdef1,
    PmxStructuralVertexInsertion,
)


def _resolution(
    target_kind: PmxReferenceTargetKind,
    source_index: int = 1,
) -> PmxStructuralAuthoringSelectorResolution:
    return PmxStructuralAuthoringSelectorResolution(
        target_kind=target_kind,
        source_index=source_index,
        matched_by=PmxStructuralAuthoringSelectorField.SOURCE_INDEX,
    )


def _insertions():
    return (
        (
            PmxStructuralTextureInsertion(path="textures/example.png"),
            PmxReferenceTargetKind.TEXTURE,
        ),
        (
            PmxStructuralMaterialInsertion(local_name="material"),
            PmxReferenceTargetKind.MATERIAL,
        ),
        (
            PmxStructuralBoneInsertion(local_name="bone"),
            PmxReferenceTargetKind.BONE,
        ),
        (
            PmxStructuralMorphInsertion(
                local_name="morph",
                morph_type="vertex",
            ),
            PmxReferenceTargetKind.MORPH,
        ),
        (
            PmxStructuralRigidBodyInsertion(local_name="body"),
            PmxReferenceTargetKind.RIGID_BODY,
        ),
        (
            PmxStructuralVertexInsertion(
                vertex_position=(0.0, 0.0, 0.0),
                normal=(0.0, 1.0, 0.0),
                uv=(0.0, 0.0),
                additional_uvs=(),
                deform=PmxStructuralVertexBdef1(bone_index=0),
                edge_scale=1.0,
            ),
            PmxReferenceTargetKind.VERTEX,
        ),
    )


class StructuralAuthoringBuilderTests(unittest.TestCase):
    def test_selector_resolution_compiles_into_all_insertion_families(self) -> None:
        for insertion, target_kind in _insertions():
            with self.subTest(target_kind=target_kind):
                compiled = builder.compile_structural_authoring_insert_before(
                    insertion,
                    _resolution(target_kind, 3),
                )
                self.assertIs(type(compiled), type(insertion))
                self.assertEqual(compiled.position, "insert_before")
                self.assertEqual(compiled.source_index, 3)
                self.assertEqual(insertion.position, "append")
                self.assertIsNone(insertion.source_index)

    def test_target_kind_mismatch_fails_closed(self) -> None:
        insertion = PmxStructuralTextureInsertion(path="x.png")
        with self.assertRaises(
            builder.PmxStructuralAuthoringBuilderServiceError
        ) as raised:
            builder.compile_structural_authoring_insert_before(
                insertion,
                _resolution(PmxReferenceTargetKind.BONE),
            )
        self.assertEqual(
            raised.exception.to_dict(),
            {
                "code": "target_kind_mismatch",
                "operation": "compile_structural_authoring_insert_before",
                "message": (
                    "Selector resolution target does not match insertion target."
                ),
            },
        )

    def test_builder_rejects_raw_selector_like_or_already_anchored_input(self) -> None:
        insertion = PmxStructuralTextureInsertion(path="x.png")
        with self.assertRaises(
            builder.PmxStructuralAuthoringBuilderServiceError
        ) as wrong_resolution:
            builder.compile_structural_authoring_insert_before(
                insertion,
                object(),  # type: ignore[arg-type]
            )
        self.assertEqual(
            wrong_resolution.exception.to_dict()["code"],
            "invalid_argument",
        )

        anchored = PmxStructuralTextureInsertion(
            path="x.png",
            position="insert_before",
            source_index=0,
        )
        with self.assertRaises(
            builder.PmxStructuralAuthoringBuilderServiceError
        ) as anchored_error:
            builder.compile_structural_authoring_insert_before(
                anchored,
                _resolution(PmxReferenceTargetKind.TEXTURE, 1),
            )
        self.assertEqual(
            anchored_error.exception.to_dict()["code"],
            "invalid_argument",
        )

    def test_plan_builder_returns_existing_plan_with_exact_operation_order(self) -> None:
        texture = PmxStructuralTextureInsertion(
            path="textures/a.png",
            new_id="texA",
        )
        material = PmxStructuralMaterialInsertion(local_name="mat")
        digest = "a" * 64

        plan = builder.build_structural_authoring_plan(
            (texture, material),
            expected_source_sha256=digest,
        )

        self.assertIsInstance(plan, PmxStructuralTransactionPlan)
        self.assertEqual(plan.operations, (texture, material))
        self.assertIs(plan.operations[0], texture)
        self.assertIs(plan.operations[1], material)
        self.assertEqual(plan.expected_source_sha256, digest)

    def test_builder_does_not_accept_selector_objects_as_plan_operations(self) -> None:
        with self.assertRaises(
            builder.PmxStructuralAuthoringBuilderServiceError
        ) as raised:
            builder.build_structural_authoring_plan(
                (_resolution(PmxReferenceTargetKind.BONE),),  # type: ignore[arg-type]
            )
        self.assertEqual(
            raised.exception.to_dict()["code"],
            "structural_authoring_plan_invalid",
        )

    def test_invalid_source_digest_is_rejected_without_disclosure(self) -> None:
        secret = "NOT-A-SHA-SECRET"
        with self.assertRaises(
            builder.PmxStructuralAuthoringBuilderServiceError
        ) as raised:
            builder.build_structural_authoring_plan(
                (),
                expected_source_sha256=secret,
            )
        payload = raised.exception.to_dict()
        self.assertEqual(
            payload["code"],
            "structural_authoring_plan_invalid",
        )
        self.assertNotIn(secret, str(payload))

    def test_render_delegates_to_existing_canonical_renderer(self) -> None:
        plan = builder.build_structural_authoring_plan(
            (PmxStructuralTextureInsertion(path="テクスチャ/目.png"),)
        )
        rendered = builder.render_structural_authoring_plan(plan)

        self.assertEqual(
            rendered,
            render_pmx_structural_transaction_plan_json(plan),
        )
        self.assertEqual(
            parse_pmx_structural_transaction_plan_json(rendered),
            plan,
        )
        self.assertEqual(
            builder.render_structural_authoring_plan(
                parse_pmx_structural_transaction_plan_json(rendered)
            ),
            rendered,
        )

    def test_resulting_plan_is_frozen(self) -> None:
        plan = builder.build_structural_authoring_plan(())
        with self.assertRaises(FrozenInstanceError):
            plan.operations = ()  # type: ignore[misc]

    def test_builder_is_filesystem_cli_preview_apply_and_hash_independent(self) -> None:
        source = inspect.getsource(builder)
        for forbidden in (
            "transaction_plan_cli",
            "load_document",
            "Path(",
            ".open(",
            "hashlib",
            "preview_structural",
            "apply_structural",
            "structural_output",
            "index_remap",
            "write_pmx",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

        self.assertIn(
            "render_pmx_structural_transaction_plan_json",
            source,
        )
        self.assertNotIn(
            "build_structural_authoring_plan",
            services.__all__,
        )

    def test_builder_does_not_import_selector_resolver_or_document(self) -> None:
        source = inspect.getsource(builder)
        self.assertNotIn(
            "resolve_structural_authoring_selector",
            source,
        )
        self.assertNotIn("PmxDocument", source)

    def test_process_control_exceptions_escape(self) -> None:
        plan = builder.build_structural_authoring_plan(())
        with patch.object(
            builder,
            "render_pmx_structural_transaction_plan_json",
            side_effect=KeyboardInterrupt(),
        ):
            with self.assertRaises(KeyboardInterrupt):
                builder.render_structural_authoring_plan(plan)


if __name__ == "__main__":
    unittest.main()
