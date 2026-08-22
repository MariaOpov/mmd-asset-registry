from __future__ import annotations

import inspect
import unittest
from pathlib import Path

from mmd_registry import services
from mmd_registry.pmx.collection_transform import PmxCollectionTransform
from mmd_registry.pmx.index_remap import PmxIndexRemap
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind


class V092StructuralInsertionContractTests(unittest.TestCase):
    def test_released_request_alias_and_default_shape_remain_consumable(self) -> None:
        self.assertIs(
            services.PmxStructuralEditRequest,
            services.PmxStructuralPreviewRequest,
        )
        request = services.PmxStructuralPreviewRequest()
        self.assertEqual(request.collection_edits, ())

    def test_released_service_authority_signatures_remain_stable(self) -> None:
        preview = inspect.signature(services.preview_structural_edit)
        self.assertEqual(tuple(preview.parameters), ("document", "request"))

        apply = inspect.signature(services.apply_structural_edit)
        self.assertEqual(
            tuple(apply.parameters),
            ("input_path", "output_path", "request", "overwrite"),
        )
        self.assertEqual(
            apply.parameters["overwrite"].kind,
            inspect.Parameter.KEYWORD_ONLY,
        )
        self.assertIs(apply.parameters["overwrite"].default, False)

    def test_legacy_collection_edit_rejects_bool_and_negative_indices(self) -> None:
        with self.assertRaises(TypeError):
            services.PmxStructuralCollectionEdit(
                target_kind=PmxReferenceTargetKind.TEXTURE,
                old_indices_in_new_order=(True,),  # type: ignore[arg-type]
            )

        with self.assertRaises(ValueError):
            services.PmxStructuralCollectionEdit(
                target_kind=PmxReferenceTargetKind.TEXTURE,
                old_indices_in_new_order=(-1,),
            )

    def test_index_remap_represents_new_only_positions_deterministically(self) -> None:
        remap = PmxIndexRemap(
            targets=(0, 2, 3),
            new_size=4,
            new_indices_without_old_source=(1,),
        )
        self.assertEqual(remap.old_size, 3)
        self.assertEqual(remap.new_size, 4)
        self.assertEqual(remap.targets, (0, 2, 3))
        self.assertEqual(remap.new_indices_without_old_source, (1,))
        self.assertTrue(remap.has_new_indices_without_old_source)
        self.assertEqual(remap.target_for(0), 0)
        self.assertEqual(remap.target_for(1), 2)
        self.assertEqual(remap.target_for(2), 3)

    def test_legacy_collection_transform_still_does_not_authorize_insertion(self) -> None:
        remap = PmxIndexRemap(
            targets=(0,),
            new_size=2,
            new_indices_without_old_source=(1,),
        )
        with self.assertRaisesRegex(
            ValueError,
            "do not authorize new indices without old sources",
        ):
            PmxCollectionTransform(
                kind=PmxReferenceTargetKind.TEXTURE,
                remap=remap,
            )

    def test_cp02_does_not_add_parallel_public_mutation_authority(self) -> None:
        forbidden = {
            "insert_structural_edit",
            "apply_structural_insert",
            "write_pmx_structural_transform",
            "PmxStructuralWriteResult",
        }
        self.assertTrue(forbidden.isdisjoint(services.__all__))
        for name in forbidden:
            self.assertFalse(hasattr(services, name))

    def test_contract_document_freezes_required_policy(self) -> None:
        contract_path = (
            Path(__file__).resolve().parents[1]
            / "docs"
            / "structural_insertion_contract.md"
        )
        contract = contract_path.read_text(encoding="utf-8")

        required_phrases = (
            "insert_before(source_index)",
            "captured source snapshot",
            "new_indices_without_old_source",
            "Automatic PMX index-width expansion is out of scope for v0.9.2.",
            "PmxStructuralEditRequest",
            "apply_structural_edit",
            "source PMX must remain byte-for-byte unchanged",
            "CP02 does not add or imply `structural_insert=True`",
            "no production insertion path is enabled by CP02",
        )
        for phrase in required_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, contract)


if __name__ == "__main__":
    unittest.main()
