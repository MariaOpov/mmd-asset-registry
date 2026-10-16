from __future__ import annotations

import hashlib
import io
import tempfile
import unittest
from pathlib import Path

import mmd_registry.services as services
import mmd_registry.services._smart_material_apply as smart_apply
import mmd_registry.services._smart_material_draft as smart_draft
from mmd_registry.pmx import load_pmx
from mmd_registry.pmx.editing import (
    PMX_EDIT_PREVIEW_SCHEMA_VERSION,
    calculate_pmx_edit_plan_sha256,
)
from mmd_registry.services import _smart_inspection
from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringMaterialCatalogEntry,
)
from mmd_registry.smart_parts import SmartPartKind
from tests.test_v0956_smart_material_draft import (
    build_ambiguous_source,
    build_source_bytes,
)


class V09510MultipleSemanticMaterialHardeningTests(unittest.TestCase):
    def material(
        self,
        *,
        source_index: int,
        local_name: str = "",
        universal_name: str = "",
    ) -> PmxStructuralAuthoringMaterialCatalogEntry:
        return PmxStructuralAuthoringMaterialCatalogEntry(
            source_index=source_index,
            local_name=local_name,
            universal_name=universal_name,
            texture_index=-1,
            sphere_texture_index=-1,
            surface_index_count=0,
        )

    def test_all_exact_material_targets_are_retained_in_ascending_source_index_order(
        self,
    ) -> None:
        source_bytes = build_source_bytes()

        draft = smart_draft.build_smart_material_color_draft(
            source_bytes,
            SmartPartKind.EYES,
            "purple",
        )

        self.assertEqual(
            tuple(operation.material_index for operation in draft.operations),
            (1, 2),
        )
        self.assertEqual(len(draft.operations), 2)
        self.assertEqual(
            draft.expected_source_sha256,
            hashlib.sha256(source_bytes).hexdigest(),
        )

    def test_repeated_exact_evidence_deduplicates_without_target_loss(
        self,
    ) -> None:
        entries = (
            self.material(source_index=7, local_name="Eyes"),
            self.material(source_index=2, local_name="瞳"),
            self.material(source_index=7, local_name="EYES"),
            self.material(source_index=2, local_name="  瞳　"),
        )

        forward = _smart_inspection._analyze_entries(entries)
        reverse = _smart_inspection._analyze_entries(tuple(reversed(entries)))

        forward_group = smart_draft.group_smart_materials(
            forward,
            SmartPartKind.EYES,
        )
        reverse_group = smart_draft.group_smart_materials(
            reverse,
            SmartPartKind.EYES,
        )

        self.assertEqual(forward_group.material_indices, (2, 7))
        self.assertEqual(reverse_group.material_indices, (2, 7))
        self.assertEqual(forward_group, reverse_group)
        self.assertEqual(
            tuple(item.source_index for item in forward_group.evidence),
            (2, 7),
        )

    def test_competing_semantic_ambiguity_blocks_without_partial_apply(
        self,
    ) -> None:
        source_bytes = build_ambiguous_source()

        with self.assertRaises(
            smart_draft.SmartMaterialDraftError
        ) as raised:
            smart_draft.build_smart_material_color_draft(
                source_bytes,
                SmartPartKind.EYES,
                "blue",
            )

        self.assertEqual(
            raised.exception.reason,
            "ambiguous_semantic_selection",
        )

        with tempfile.TemporaryDirectory() as directory:
            destination_path = Path(directory) / "destination.pmx"
            self.assertFalse(destination_path.exists())

    def test_multi_material_preview_apply_target_set_parity_is_exact(
        self,
    ) -> None:
        source_bytes = build_source_bytes()
        source_document = load_pmx(io.BytesIO(source_bytes))

        draft = smart_draft.build_smart_material_color_draft(
            source_bytes,
            SmartPartKind.EYES,
            "red",
        )
        preview = services.preview_edit(source_bytes, draft)
        confirmation = smart_apply.SmartMaterialApplyConfirmation(
            preview_schema_version=PMX_EDIT_PREVIEW_SCHEMA_VERSION,
            source_sha256=preview.source_sha256,
            plan_sha256=calculate_pmx_edit_plan_sha256(draft),
        )

        draft_indices = tuple(
            operation.material_index
            for operation in draft.operations
        )
        self.assertEqual(draft_indices, (1, 2))
        self.assertEqual(preview.operation_count, len(draft_indices))
        self.assertEqual(preview.audit.category_count("material"), 2)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.pmx"
            destination_path = root / "destination.pmx"
            source_path.write_bytes(source_bytes)

            result = smart_apply.apply_smart_material_color_draft(
                source_path,
                destination_path,
                draft,
                preview,
                confirmation=confirmation,
            )

            self.assertEqual(result.preview, preview)
            self.assertEqual(source_path.read_bytes(), source_bytes)
            self.assertTrue(destination_path.is_file())

            destination_document = load_pmx(
                io.BytesIO(destination_path.read_bytes())
            )
            self.assertEqual(destination_document, preview.document)

            changed_indices = tuple(
                index
                for index, (before, after)
                in enumerate(
                    zip(
                        source_document.materials,
                        destination_document.materials,
                    )
                )
                if before != after
            )
            self.assertEqual(changed_indices, draft_indices)
            self.assertEqual(changed_indices, (1, 2))


if __name__ == "__main__":
    unittest.main()
