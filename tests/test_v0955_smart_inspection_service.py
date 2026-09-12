"""Tests for v0.9.5.5 Smart Inspect read-only orchestration."""

from __future__ import annotations

import inspect
import unittest
from unittest.mock import patch

import mmd_registry.services._smart_inspection as smart_inspection
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.services.structural_authoring_catalog import (
    PMX_STRUCTURAL_AUTHORING_CATALOG_MAX_LIMIT,
    PmxStructuralAuthoringBoneCatalogEntry,
    PmxStructuralAuthoringCatalogPage,
    PmxStructuralAuthoringMaterialCatalogEntry,
    PmxStructuralAuthoringTextureCatalogEntry,
)
from mmd_registry.smart_part_confidence import SmartPartConfidence
from mmd_registry.smart_parts import SmartPartKind


class SmartInspectionServiceTests(unittest.TestCase):
    def material(
        self,
        source_index: int,
        local_name: str,
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

    def bone(
        self,
        source_index: int,
        local_name: str,
        universal_name: str = "",
    ) -> PmxStructuralAuthoringBoneCatalogEntry:
        return PmxStructuralAuthoringBoneCatalogEntry(
            source_index=source_index,
            local_name=local_name,
            universal_name=universal_name,
            parent_bone_index=-1,
            position=(0.0, 0.0, 0.0),
            flag_names=(),
        )

    def test_analysis_reuses_detector_explainer_and_confidence_authorities(self) -> None:
        entries = (
            self.material(2, "瞳"),
            self.bone(4, "左目"),
        )

        result = smart_inspection._analyze_entries(entries)

        self.assertEqual(result.entries, entries)
        self.assertEqual(tuple(part.kind for part in result.parts), (SmartPartKind.EYES,))
        self.assertEqual(
            tuple(item.kind for item in result.explanations),
            (SmartPartKind.EYES,),
        )
        self.assertEqual(len(result.assessments), 1)
        self.assertIs(result.assessments[0].confidence, SmartPartConfidence.HIGH)
        self.assertEqual(
            tuple(candidate.kind for candidate in result.assessments[0].candidates),
            (SmartPartKind.EYES,),
        )

    def test_collection_uses_only_semantic_authority_kinds_and_catalog_paging(self) -> None:
        texture0 = PmxStructuralAuthoringTextureCatalogEntry(
            source_index=0,
            path="eye.png",
        )
        texture1 = PmxStructuralAuthoringTextureCatalogEntry(
            source_index=1,
            path="hair.png",
        )

        def page_for(document, target_kind, *, offset, limit):
            self.assertIs(document, sentinel_document)
            self.assertEqual(limit, PMX_STRUCTURAL_AUTHORING_CATALOG_MAX_LIMIT)
            if target_kind is PmxReferenceTargetKind.TEXTURE:
                entry = texture0 if offset == 0 else texture1
                return PmxStructuralAuthoringCatalogPage(
                    target_kind=target_kind,
                    total_count=2,
                    offset=offset,
                    limit=limit,
                    entries=(entry,),
                )
            return PmxStructuralAuthoringCatalogPage(
                target_kind=target_kind,
                total_count=0,
                offset=offset,
                limit=limit,
                entries=(),
            )

        sentinel_document = object()
        with patch.object(
            smart_inspection,
            "inspect_structural_authoring_catalog",
            side_effect=page_for,
        ) as inspect_catalog:
            entries = smart_inspection._collect_semantic_entries(sentinel_document)

        self.assertEqual(entries, (texture0, texture1))
        self.assertEqual(
            [
                (call.args[1], call.kwargs["offset"])
                for call in inspect_catalog.call_args_list
            ],
            [
                (PmxReferenceTargetKind.TEXTURE, 0),
                (PmxReferenceTargetKind.TEXTURE, 1),
                (PmxReferenceTargetKind.MATERIAL, 0),
                (PmxReferenceTargetKind.BONE, 0),
                (PmxReferenceTargetKind.MORPH, 0),
            ],
        )

    def test_service_module_has_no_cli_or_mutation_authority(self) -> None:
        source = inspect.getsource(smart_inspection)
        for forbidden in (
            "argparse",
            "sys.exit",
            "print(",
            "preview_",
            "apply_",
            "serialize_pmx",
            "pmx.writer",
            "index_remap",
            "transaction_plan",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
