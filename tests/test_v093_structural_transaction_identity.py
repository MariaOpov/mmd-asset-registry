"""Freeze the v0.9.3 structural transaction local-ID namespace."""

from __future__ import annotations

from dataclasses import replace
from itertools import combinations
import unittest

from mmd_registry.services.structural_bone import PmxStructuralBoneInsertion
from mmd_registry.services.structural_material import (
    PmxStructuralMaterialInsertion,
)
from mmd_registry.services.structural_morph import PmxStructuralMorphInsertion
from mmd_registry.services.structural_reference import (
    PmxStructuralNewReference,
)
from mmd_registry.services.structural_rigid_body import (
    PmxStructuralRigidBodyInsertion,
)
from mmd_registry.services.structural_texture import PmxStructuralTextureInsertion
from mmd_registry.services.structural_transaction import (
    PmxStructuralTransactionRequest,
)
from mmd_registry.services.structural_vertex import (
    PmxStructuralVertexBdef1,
    PmxStructuralVertexInsertion,
)


def _sample_insertions() -> tuple[object, ...]:
    return (
        PmxStructuralTextureInsertion("shared.png"),
        PmxStructuralMaterialInsertion("shared"),
        PmxStructuralBoneInsertion("shared"),
        PmxStructuralMorphInsertion("shared", "vertex"),
        PmxStructuralRigidBodyInsertion("shared"),
        PmxStructuralVertexInsertion(
            vertex_position=(0.0, 0.0, 0.0),
            normal=(0.0, 1.0, 0.0),
            uv=(0.0, 0.0),
            additional_uvs=(),
            deform=PmxStructuralVertexBdef1(-1),
            edge_scale=1.0,
        ),
    )


class V093StructuralTransactionIdentityTests(unittest.TestCase):
    """Keep CP07 bounded to exact request-local identity validation."""

    def test_duplicate_new_id_within_each_target_kind_is_rejected(self) -> None:
        for insertion in _sample_insertions():
            with self.subTest(insertion_type=type(insertion).__name__):
                first = replace(insertion, new_id="shared")
                second = replace(insertion, new_id="shared")

                with self.assertRaisesRegex(
                    ValueError,
                    r"^request-local new_id 'shared' must be globally unique\.$",
                ):
                    PmxStructuralTransactionRequest((first, second))

    def test_duplicate_new_id_across_every_target_kind_pair_is_rejected(
        self,
    ) -> None:
        insertions = _sample_insertions()
        for left_index, right_index in combinations(range(len(insertions)), 2):
            left = replace(insertions[left_index], new_id="shared")
            right = replace(insertions[right_index], new_id="shared")
            with self.subTest(
                left=type(left).__name__,
                right=type(right).__name__,
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    r"^request-local new_id 'shared' must be globally unique\.$",
                ):
                    PmxStructuralTransactionRequest((left, right))

    def test_namespace_is_case_sensitive_and_preserves_exact_ascii_ids(
        self,
    ) -> None:
        new_ids = (
            "Asset",
            "asset",
            "ASSET",
            "asset.one",
            "asset-one",
            "asset_one",
        )
        operations = tuple(
            replace(insertion, new_id=new_id)
            for insertion, new_id in zip(_sample_insertions(), new_ids, strict=True)
        )

        request = PmxStructuralTransactionRequest(operations)

        self.assertIs(request.operations, operations)
        self.assertEqual(
            tuple(operation.new_id for operation in request.operations),
            new_ids,
        )

    def test_none_does_not_declare_or_collide_in_the_identity_namespace(
        self,
    ) -> None:
        operations = _sample_insertions()

        request = PmxStructuralTransactionRequest(operations)

        self.assertEqual(
            tuple(operation.new_id for operation in request.operations),
            (None,) * len(operations),
        )

    def test_every_insertion_dto_rejects_invalid_or_normalized_ids(self) -> None:
        invalid_ids = (
            "",
            "1asset",
            " asset",
            "asset ",
            "asset/name",
            "téxture",
            "A" * 65,
        )
        for insertion in _sample_insertions():
            for new_id in invalid_ids:
                with self.subTest(
                    insertion_type=type(insertion).__name__,
                    new_id=new_id,
                ):
                    with self.assertRaisesRegex(
                        ValueError,
                        r"^new_id must contain 1\.\.64 ASCII characters matching ",
                    ):
                        replace(insertion, new_id=new_id)

    def test_every_insertion_dto_rejects_non_string_ids(self) -> None:
        for insertion in _sample_insertions():
            for new_id in (0, True, b"asset", object()):
                with self.subTest(
                    insertion_type=type(insertion).__name__,
                    new_id_type=type(new_id).__name__,
                ):
                    with self.assertRaisesRegex(
                        TypeError,
                        r"^new_id must be a string or None\.$",
                    ):
                        replace(insertion, new_id=new_id)

    def test_display_names_are_not_transaction_identity(self) -> None:
        anonymous = PmxStructuralMaterialInsertion("same display name")
        identified = PmxStructuralMaterialInsertion(
            "same display name",
            new_id="material_identity",
        )

        request = PmxStructuralTransactionRequest((anonymous, identified))

        self.assertEqual(request.operations, (anonymous, identified))

    def test_reference_resolution_is_deferred_to_cp08(self) -> None:
        unresolved = PmxStructuralNewReference("texture", "later_texture")
        consumer = PmxStructuralMaterialInsertion(
            "consumer",
            texture_index=unresolved,
            new_id="consumer_material",
        )

        request = PmxStructuralTransactionRequest((consumer,))

        self.assertEqual(request.operations, (consumer,))
        self.assertIs(consumer.texture_index, unresolved)


if __name__ == "__main__":
    unittest.main()
