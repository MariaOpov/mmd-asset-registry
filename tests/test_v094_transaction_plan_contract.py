"""Freeze the v0.9.4 structural transaction-plan schema decisions."""

from __future__ import annotations

from dataclasses import fields
import inspect
from pathlib import Path
import typing
import unittest

import mmd_registry
import mmd_registry.pmx as pmx
import mmd_registry.services as services
import mmd_registry.services.structural_bone as structural_bone
import mmd_registry.services.structural_material as structural_material
import mmd_registry.services.structural_morph as structural_morph
import mmd_registry.services.structural_reference as structural_reference
import mmd_registry.services.structural_rigid_body as structural_rigid_body
import mmd_registry.services.structural_texture as structural_texture
import mmd_registry.services.structural_transaction as transactions
import mmd_registry.services.structural_vertex as structural_vertex


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPOSITORY_ROOT / "docs" / "v094_transaction_plan_contract.md"

TRANSACTION_PLAN_SCHEMA_VERSION = 1
AUTHORING_NAMESPACE = "mmd_registry.pmx.transaction_plan"

OPERATION_TYPES = (
    "transform_collection",
    "insert_texture",
    "insert_material",
    "insert_bone",
    "insert_morph",
    "insert_rigid_body",
    "insert_vertex",
)

TRANSACTION_OPERATION_CLASSES = (
    services.PmxStructuralCollectionEdit,
    structural_texture.PmxStructuralTextureInsertion,
    structural_material.PmxStructuralMaterialInsertion,
    structural_bone.PmxStructuralBoneInsertion,
    structural_morph.PmxStructuralMorphInsertion,
    structural_rigid_body.PmxStructuralRigidBodyInsertion,
    structural_vertex.PmxStructuralVertexInsertion,
)

MORPH_TYPES = (
    "group",
    "vertex",
    "bone",
    "uv",
    "additional_uv_1",
    "additional_uv_2",
    "additional_uv_3",
    "additional_uv_4",
    "material",
    "flip",
    "impulse",
)

MORPH_OFFSET_TYPES = (
    "group",
    "vertex",
    "bone",
    "uv",
    "material",
    "flip",
    "impulse",
)

VERTEX_DEFORM_TYPES = ("bdef1", "bdef2", "bdef4", "sdef", "qdef")

TARGET_KINDS = ("vertex", "texture", "material", "bone", "morph", "rigid_body")


class V094TransactionPlanContractTests(unittest.TestCase):
    """Keep schema one aligned with the released v0.9.3 transaction authority."""

    def test_schema_identity_and_operation_vocabulary_are_frozen(self) -> None:
        self.assertEqual(TRANSACTION_PLAN_SCHEMA_VERSION, 1)
        self.assertEqual(
            OPERATION_TYPES,
            (
                "transform_collection",
                "insert_texture",
                "insert_material",
                "insert_bone",
                "insert_morph",
                "insert_rigid_body",
                "insert_vertex",
            ),
        )
        self.assertEqual(MORPH_OFFSET_TYPES, ("group", "vertex", "bone", "uv", "material", "flip", "impulse"))
        self.assertEqual(VERTEX_DEFORM_TYPES, ("bdef1", "bdef2", "bdef4", "sdef", "qdef"))

    def test_operation_vocabulary_maps_one_to_one_to_released_dto_families(self) -> None:
        actual = typing.get_args(transactions.PmxStructuralTransactionOperation)
        self.assertEqual(actual, TRANSACTION_OPERATION_CLASSES)
        self.assertEqual(len(OPERATION_TYPES), len(actual))
        self.assertEqual(
            tuple(field.name for field in fields(transactions.PmxStructuralTransactionRequest)),
            ("operations",),
        )

    def test_new_reference_shape_and_target_kinds_remain_bounded(self) -> None:
        self.assertEqual(
            tuple(field.name for field in fields(structural_reference.PmxStructuralNewReference)),
            ("target_kind", "new_id"),
        )
        for target_kind in TARGET_KINDS:
            value = structural_reference.PmxStructuralNewReference(
                target_kind=target_kind,
                new_id=f"{target_kind}-id",
            )
            self.assertEqual(value.target_kind, target_kind)
        with self.assertRaises(ValueError):
            structural_reference.PmxStructuralNewReference(
                target_kind="joint",
                new_id="x",
            )

    def test_morph_and_vertex_union_vocabularies_match_released_types(self) -> None:
        morph_hints = typing.get_type_hints(
            structural_morph.PmxStructuralMorphInsertion,
            globalns=vars(structural_morph),
            localns=vars(structural_morph),
        )
        self.assertEqual(typing.get_args(morph_hints["morph_type"]), MORPH_TYPES)

        vertex_hints = typing.get_type_hints(
            structural_vertex.PmxStructuralVertexInsertion,
            globalns=vars(structural_vertex),
            localns=vars(structural_vertex),
        )
        self.assertEqual(
            typing.get_args(vertex_hints["deform"]),
            (
                structural_vertex.PmxStructuralVertexBdef1,
                structural_vertex.PmxStructuralVertexBdef2,
                structural_vertex.PmxStructuralVertexBdef4,
                structural_vertex.PmxStructuralVertexSdef,
                structural_vertex.PmxStructuralVertexQdef,
            ),
        )

    def test_same_target_new_bone_references_are_not_added_to_bone_dto(self) -> None:
        hints = typing.get_type_hints(
            structural_bone.PmxStructuralBoneInsertion,
            globalns=vars(structural_bone),
            localns=vars(structural_bone),
        )
        for field_name in (
            "parent_bone_index",
            "tail_bone_index",
            "inherit_parent_bone_index",
        ):
            args = typing.get_args(hints[field_name])
            self.assertNotIn(structural_reference.PmxStructuralNewReference, args)
        ik_hints = typing.get_type_hints(
            structural_bone.PmxStructuralBoneIk,
            globalns=vars(structural_bone),
            localns=vars(structural_bone),
        )
        self.assertIs(ik_hints["target_bone_index"], int)

    def test_reviewed_cross_target_new_reference_fields_remain_available(self) -> None:
        material_hints = typing.get_type_hints(
            structural_material.PmxStructuralMaterialInsertion,
            globalns=vars(structural_material),
            localns=vars(structural_material),
        )
        self.assertIn(
            structural_reference.PmxStructuralNewReference,
            typing.get_args(material_hints["texture_index"]),
        )

        rigid_hints = typing.get_type_hints(
            structural_rigid_body.PmxStructuralRigidBodyInsertion,
            globalns=vars(structural_rigid_body),
            localns=vars(structural_rigid_body),
        )
        self.assertIn(
            structural_reference.PmxStructuralNewReference,
            typing.get_args(rigid_hints["bone_index"]),
        )

        vertex_hints = typing.get_type_hints(
            structural_vertex.PmxStructuralVertexBdef1,
            globalns=vars(structural_vertex),
            localns=vars(structural_vertex),
        )
        self.assertIn(
            structural_reference.PmxStructuralNewReference,
            typing.get_args(vertex_hints["bone_index"]),
        )

    def test_authoring_must_not_be_promoted_to_legacy_public_roots(self) -> None:
        reserved_names = (
            "PMX_STRUCTURAL_TRANSACTION_PLAN_SCHEMA_VERSION",
            "PmxStructuralTransactionPlan",
            "parse_pmx_structural_transaction_plan_json",
            "load_pmx_structural_transaction_plan",
            "render_pmx_structural_transaction_plan_json",
        )
        for root in (mmd_registry, pmx, services):
            for name in reserved_names:
                self.assertFalse(hasattr(root, name), (root.__name__, name))
        self.assertEqual(mmd_registry.__all__, ("__version__",))

    def test_transaction_execution_authority_remains_the_v093_service(self) -> None:
        self.assertEqual(
            transactions.__all__,
            (
                "PmxStructuralTransactionOperation",
                "PmxStructuralTransactionRequest",
                "PmxStructuralTransactionPreviewResult",
                "preview_structural_transaction",
                "apply_structural_transaction",
            ),
        )
        preview_source = inspect.getsource(transactions.preview_structural_transaction)
        apply_source = inspect.getsource(transactions.apply_structural_transaction)
        self.assertIn("_plan_structural_transaction", preview_source)
        self.assertIn("_write_structural_transaction_with_stage_callback", apply_source)
        self.assertNotIn("_plan_structural_transaction", transactions.__all__)
        self.assertNotIn("_write_structural_transaction", transactions.__all__)

    def test_contract_document_contains_the_frozen_schema_markers(self) -> None:
        text = CONTRACT_PATH.read_text(encoding="utf-8")
        for marker in (
            "`mmd_registry.pmx.transaction_plan`",
            "`transform_collection`",
            "`insert_texture`",
            "`insert_material`",
            "`insert_bone`",
            "`insert_morph`",
            "`insert_rigid_body`",
            "`insert_vertex`",
            '"ref": "new"',
            "`bdef1`",
            "`qdef`",
            "`impulse`",
            "PMX_STRUCTURAL_TRANSACTION_PLAN_SCHEMA_VERSION",
            "PmxStructuralTransactionPlan",
        ):
            self.assertIn(marker, text)


if __name__ == "__main__":
    unittest.main()
