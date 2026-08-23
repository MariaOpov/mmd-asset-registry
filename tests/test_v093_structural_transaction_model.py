"""Freeze the smallest public v0.9.3 structural transaction request model."""

from __future__ import annotations

import importlib
import inspect
import subprocess
import sys
from dataclasses import FrozenInstanceError, fields, is_dataclass
from pathlib import Path
from typing import get_args
import unittest

import mmd_registry
import mmd_registry.services as services
from mmd_registry.services.structural_bone import PmxStructuralBoneInsertion
from mmd_registry.services.structural_material import (
    PmxStructuralMaterialInsertion,
)
from mmd_registry.services.structural_morph import PmxStructuralMorphInsertion
from mmd_registry.services.structural_rigid_body import (
    PmxStructuralRigidBodyInsertion,
)
from mmd_registry.services.structural_texture import PmxStructuralTextureInsertion
from mmd_registry.services.structural_vertex import (
    PmxStructuralVertexBdef1,
    PmxStructuralVertexInsertion,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TRANSACTION_MODULE_NAME = "mmd_registry.services.structural_transaction"
EXPECTED_OPERATION_TYPES = (
    services.PmxStructuralCollectionEdit,
    PmxStructuralTextureInsertion,
    PmxStructuralMaterialInsertion,
    PmxStructuralBoneInsertion,
    PmxStructuralMorphInsertion,
    PmxStructuralRigidBodyInsertion,
    PmxStructuralVertexInsertion,
)


def _transaction_module():
    return importlib.import_module(TRANSACTION_MODULE_NAME)


def _sample_operations() -> tuple[object, ...]:
    return (
        services.PmxStructuralCollectionEdit(
            services.PmxReferenceTargetKind.TEXTURE,
            (),
        ),
        PmxStructuralTextureInsertion("new_texture.png"),
        PmxStructuralMaterialInsertion("new_material"),
        PmxStructuralBoneInsertion("new_bone"),
        PmxStructuralMorphInsertion("new_morph", "vertex"),
        PmxStructuralRigidBodyInsertion("new_rigid_body"),
        PmxStructuralVertexInsertion(
            vertex_position=(0.0, 0.0, 0.0),
            normal=(0.0, 1.0, 0.0),
            uv=(0.0, 0.0),
            additional_uvs=(),
            deform=PmxStructuralVertexBdef1(-1),
            edge_scale=1.0,
        ),
    )


class V093StructuralTransactionModelTests(unittest.TestCase):
    """Keep CP06 bounded to immutable typed request construction."""

    def test_explicit_submodule_exports_only_the_model_foundation(self) -> None:
        transaction = _transaction_module()

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
        for name in transaction.__all__:
            self.assertTrue(hasattr(transaction, name), name)

        for forbidden in ("PmxStructuralTransactionExecutionResult",):
            self.assertFalse(hasattr(transaction, forbidden), forbidden)

    def test_operation_union_reuses_exact_released_dto_identities(self) -> None:
        transaction = _transaction_module()

        self.assertEqual(
            get_args(transaction.PmxStructuralTransactionOperation),
            EXPECTED_OPERATION_TYPES,
        )

    def test_request_has_one_frozen_slotted_tuple_field(self) -> None:
        transaction = _transaction_module()
        request_type = transaction.PmxStructuralTransactionRequest

        self.assertTrue(is_dataclass(request_type))
        self.assertEqual(
            tuple(field.name for field in fields(request_type)),
            ("operations",),
        )
        parameter = inspect.signature(request_type).parameters["operations"]
        self.assertEqual(parameter.default, ())

        request = request_type()
        self.assertEqual(request.operations, ())
        self.assertFalse(hasattr(request, "__dict__"))
        with self.assertRaises(FrozenInstanceError):
            request.operations = ()

        self.assertEqual(request, request_type(()))
        self.assertEqual(hash(request), hash(request_type(())))

    def test_request_accepts_every_operation_and_preserves_tuple_order(self) -> None:
        transaction = _transaction_module()
        operations = _sample_operations()

        request = transaction.PmxStructuralTransactionRequest(operations)

        self.assertIs(request.operations, operations)
        self.assertEqual(
            tuple(type(operation) for operation in request.operations),
            EXPECTED_OPERATION_TYPES,
        )

    def test_request_rejects_every_non_tuple_operations_container(self) -> None:
        transaction = _transaction_module()

        for value in ([], set(), "", iter(())):
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaisesRegex(
                    TypeError,
                    r"^operations must be a tuple\.$",
                ):
                    transaction.PmxStructuralTransactionRequest(value)

    def test_request_rejects_values_outside_the_operation_union(self) -> None:
        transaction = _transaction_module()

        for value in (None, object(), True, 0, "texture"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    TypeError,
                    "^operations must contain only "
                    "PmxStructuralCollectionEdit or supported "
                    "structural insertion values\\.$",
                ):
                    transaction.PmxStructuralTransactionRequest((value,))

    def test_request_rejects_duplicate_collection_transform_targets(self) -> None:
        transaction = _transaction_module()
        texture_edit = services.PmxStructuralCollectionEdit(
            services.PmxReferenceTargetKind.TEXTURE,
            (),
        )
        repeated_texture_edit = services.PmxStructuralCollectionEdit(
            services.PmxReferenceTargetKind.TEXTURE,
            (0,),
        )

        with self.assertRaisesRegex(
            ValueError,
            "^operations cannot repeat one "
            "PmxStructuralCollectionEdit target_kind\\.$",
        ):
            transaction.PmxStructuralTransactionRequest(
                (texture_edit, repeated_texture_edit)
            )

        material_edit = services.PmxStructuralCollectionEdit(
            services.PmxReferenceTargetKind.MATERIAL,
            (),
        )
        request = transaction.PmxStructuralTransactionRequest(
            (texture_edit, material_edit)
        )
        self.assertEqual(request.operations, (texture_edit, material_edit))

    def test_model_is_additive_and_does_not_promote_authority(self) -> None:
        transaction = _transaction_module()

        for name in transaction.__all__:
            self.assertNotIn(name, services.__all__)
            self.assertFalse(hasattr(services, name))
            self.assertFalse(hasattr(mmd_registry, name))

        capabilities = services.get_capabilities()
        self.assertFalse(hasattr(capabilities, "structural_transaction"))
        self.assertNotIn("structural_transaction", capabilities.to_dict())

    def test_explicit_submodule_supports_a_clean_cold_import(self) -> None:
        script = "\n".join(
            (
                "import mmd_registry",
                "import mmd_registry.services as services",
                "import mmd_registry.services.structural_transaction as transaction",
                "assert transaction.__all__ == (",
                "    'PmxStructuralTransactionOperation',",
                "    'PmxStructuralTransactionRequest',",
                "    'PmxStructuralTransactionPreviewResult',",
                "    'preview_structural_transaction',",
                "    'apply_structural_transaction',",
                ")",
                "assert not hasattr(services, 'PmxStructuralTransactionRequest')",
                "assert not hasattr(mmd_registry, 'PmxStructuralTransactionRequest')",
                "print('CP06_COLD_IMPORT_PASS')",
            )
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout, "CP06_COLD_IMPORT_PASS\n")


if __name__ == "__main__":
    unittest.main()
