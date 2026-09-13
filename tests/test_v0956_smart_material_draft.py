"""v0.9.5.6 source-bound Smart material color draft tests."""

from __future__ import annotations

import dataclasses
import hashlib
import inspect
import io
import unittest

import mmd_registry.services as services
import mmd_registry.services._smart_material_draft as smart_material_draft
from mmd_registry.pmx import load_pmx
from mmd_registry.pmx.editing.operations import UpdateMaterial
from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringMaterialCatalogEntry,
)
from mmd_registry.smart_parts import SmartPartKind
from tests.mmd_fixtures import (
    build_pmx_bone,
    build_pmx_material,
    build_pmx_structure,
)


def build_source_bytes(
    *,
    eye_rgb: tuple[float, float, float] = (0.2, 0.3, 0.4),
) -> bytes:
    materials = (
        build_pmx_material(
            local_name="Hair",
            universal_name="",
            diffuse=(0.8, 0.7, 0.6, 0.9),
            texture_index=-1,
            sphere_texture_index=-1,
            sphere_mode=0,
            toon_reference_mode=1,
            toon_reference_index=0,
            memo="",
            surface_index_count=3,
        ),
        build_pmx_material(
            local_name="Eyes",
            universal_name="",
            diffuse=(eye_rgb[0], eye_rgb[1], eye_rgb[2], 0.35),
            texture_index=-1,
            sphere_texture_index=-1,
            sphere_mode=0,
            toon_reference_mode=1,
            toon_reference_index=0,
            memo="",
            surface_index_count=3,
        ),
        build_pmx_material(
            local_name="瞳",
            universal_name="",
            diffuse=(0.6, 0.5, 0.4, 0.65),
            texture_index=-1,
            sphere_texture_index=-1,
            sphere_mode=0,
            toon_reference_mode=1,
            toon_reference_index=0,
            memo="",
            surface_index_count=3,
        ),
    )
    return build_pmx_structure(
        surface_indices=(0, 0, 0, 0, 0, 0, 0, 0, 0),
        texture_paths=(),
        materials=materials,
        bones=(build_pmx_bone(),),
    )


def build_texture_only_eyes_source() -> bytes:
    material = build_pmx_material(
        local_name="Body",
        universal_name="",
        texture_index=0,
        sphere_texture_index=-1,
        sphere_mode=0,
        toon_reference_mode=1,
        toon_reference_index=0,
        memo="",
        surface_index_count=3,
    )
    return build_pmx_structure(
        surface_indices=(0, 0, 0),
        texture_paths=("eyes.png",),
        materials=(material,),
        bones=(build_pmx_bone(),),
    )


def build_ambiguous_source() -> bytes:
    material = build_pmx_material(
        local_name="Eyes",
        universal_name="Hair",
        texture_index=-1,
        sphere_texture_index=-1,
        sphere_mode=0,
        toon_reference_mode=1,
        toon_reference_index=0,
        memo="",
        surface_index_count=3,
    )
    return build_pmx_structure(
        surface_indices=(0, 0, 0),
        texture_paths=(),
        materials=(material,),
        bones=(build_pmx_bone(),),
    )


class SmartMaterialDraftTests(unittest.TestCase):
    def test_draft_uses_existing_edit_plan_and_preserves_each_source_alpha(self) -> None:
        source_bytes = build_source_bytes()
        source = load_pmx(io.BytesIO(source_bytes))

        plan = smart_material_draft.build_smart_material_color_draft(
            source_bytes,
            SmartPartKind.EYES,
            "purple",
        )

        self.assertEqual(plan.schema_version, 1)
        self.assertEqual(
            plan.expected_source_sha256,
            hashlib.sha256(source_bytes).hexdigest(),
        )
        self.assertEqual(
            tuple(operation.material_index for operation in plan.operations),
            (1, 2),
        )
        self.assertTrue(all(isinstance(operation, UpdateMaterial) for operation in plan.operations))
        self.assertEqual(
            plan.operations[0].diffuse,
            (0.5, 0.0, 0.5, source.materials[1].diffuse[3]),
        )
        self.assertEqual(
            plan.operations[1].diffuse,
            (0.5, 0.0, 0.5, source.materials[2].diffuse[3]),
        )
        self.assertEqual(
            tuple(
                tuple(key for key in operation.to_dict() if key not in {"op", "material_index"})
                for operation in plan.operations
            ),
            (("diffuse",), ("diffuse",)),
        )

    def test_generated_plan_is_accepted_by_existing_preview_authority(self) -> None:
        source_bytes = build_source_bytes()
        plan = smart_material_draft.build_smart_material_color_draft(
            source_bytes,
            SmartPartKind.EYES,
            "red",
        )

        preview = services.preview_edit(source_bytes, plan)

        self.assertEqual(preview.audit.category_count("material"), 2)
        self.assertEqual(preview.status, "changes_pending")
        self.assertTrue(preview.to_dict()["verification"]["input_unchanged"])

    def test_draft_keeps_operations_even_when_rgb_is_already_equal(self) -> None:
        source_bytes = build_source_bytes(eye_rgb=(0.0, 0.0, 1.0))
        plan = smart_material_draft.build_smart_material_color_draft(
            source_bytes,
            SmartPartKind.EYES,
            "blue",
        )

        self.assertEqual(len(plan.operations), 2)
        self.assertEqual(plan.operations[0].material_index, 1)

    def test_source_bytes_are_unchanged(self) -> None:
        source_bytes = build_source_bytes()
        before = hashlib.sha256(source_bytes).hexdigest()

        smart_material_draft.build_smart_material_color_draft(
            source_bytes,
            SmartPartKind.EYES,
            (0.1, 0.2, 0.3),
        )

        self.assertEqual(hashlib.sha256(source_bytes).hexdigest(), before)

    def test_texture_only_semantics_are_unsupported(self) -> None:
        with self.assertRaises(smart_material_draft.SmartMaterialDraftError) as raised:
            smart_material_draft.build_smart_material_color_draft(
                build_texture_only_eyes_source(),
                SmartPartKind.EYES,
                "blue",
            )

        self.assertEqual(raised.exception.reason, "unsupported_material_color")

    def test_ambiguous_semantics_block_draft(self) -> None:
        with self.assertRaises(smart_material_draft.SmartMaterialDraftError) as raised:
            smart_material_draft.build_smart_material_color_draft(
                build_ambiguous_source(),
                SmartPartKind.EYES,
                "blue",
            )

        self.assertEqual(raised.exception.reason, "ambiguous_semantic_selection")

    def test_module_has_no_apply_write_writer_remapper_or_structural_plan_authority(self) -> None:
        source = inspect.getsource(smart_material_draft)

        for forbidden in (
            "services.apply_edit",
            "write_pmx_edit",
            "serialize_pmx",
            "pmx.writer",
            "index_remap",
            "transaction_plan",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


def build_duplicate_eye_name_source() -> bytes:
    materials = tuple(
        build_pmx_material(
            local_name="Eyes",
            universal_name="",
            diffuse=(0.2 + index * 0.1, 0.3, 0.4, 0.5 + index * 0.1),
            texture_index=-1,
            sphere_texture_index=-1,
            sphere_mode=0,
            toon_reference_mode=1,
            toon_reference_index=0,
            memo="",
            surface_index_count=3,
        )
        for index in range(2)
    )
    return build_pmx_structure(
        surface_indices=(0, 0, 0, 0, 0, 0),
        texture_paths=(),
        materials=materials,
        bones=(build_pmx_bone(),),
    )


def build_fullwidth_eye_source() -> bytes:
    material = build_pmx_material(
        local_name="Ｅｙｅｓ",
        universal_name="",
        diffuse=(0.2, 0.3, 0.4, 0.8),
        texture_index=-1,
        sphere_texture_index=-1,
        sphere_mode=0,
        toon_reference_mode=1,
        toon_reference_index=0,
        memo="",
        surface_index_count=3,
    )
    return build_pmx_structure(
        surface_indices=(0, 0, 0),
        texture_paths=(),
        materials=(material,),
        bones=(build_pmx_bone(),),
    )


class SmartMaterialDraftAdversarialTests(unittest.TestCase):
    def test_out_of_range_material_evidence_fails_closed(self) -> None:
        source_bytes = build_source_bytes()
        document = load_pmx(io.BytesIO(source_bytes))
        result = smart_material_draft._smart_inspection._analyze_entries(
            (
                PmxStructuralAuthoringMaterialCatalogEntry(
                    source_index=99,
                    local_name="Eyes",
                    universal_name="",
                    texture_index=-1,
                    sphere_texture_index=-1,
                    surface_index_count=3,
                ),
            )
        )
        group = smart_material_draft.group_smart_materials(
            result,
            SmartPartKind.EYES,
        )

        with self.assertRaises(smart_material_draft.SmartMaterialDraftError) as raised:
            smart_material_draft._validate_material_group_against_document(
                document,
                result,
                group,
            )

        self.assertEqual(raised.exception.reason, "source_evidence_mismatch")

    def test_catalog_document_identity_mismatch_fails_closed(self) -> None:
        source_bytes = build_source_bytes()
        document = load_pmx(io.BytesIO(source_bytes))
        result = smart_material_draft._smart_inspection._analyze_entries(
            (
                PmxStructuralAuthoringMaterialCatalogEntry(
                    source_index=1,
                    local_name="Eyes",
                    universal_name="",
                    texture_index=-1,
                    sphere_texture_index=-1,
                    surface_index_count=3,
                ),
            )
        )
        mismatched = dataclasses.replace(
            result,
            entries=(
                PmxStructuralAuthoringMaterialCatalogEntry(
                    source_index=1,
                    local_name="Eyes",
                    universal_name="DIFFERENT",
                    texture_index=-1,
                    sphere_texture_index=-1,
                    surface_index_count=3,
                ),
            ),
        )
        group = smart_material_draft.group_smart_materials(
            result,
            SmartPartKind.EYES,
        )

        with self.assertRaises(smart_material_draft.SmartMaterialDraftError) as raised:
            smart_material_draft._validate_material_group_against_document(
                document,
                mismatched,
                group,
            )

        self.assertEqual(raised.exception.reason, "source_evidence_mismatch")

    def test_conflicting_duplicate_catalog_identity_fails_closed(self) -> None:
        result = smart_material_draft._smart_inspection._analyze_entries(
            (
                PmxStructuralAuthoringMaterialCatalogEntry(
                    source_index=1,
                    local_name="Eyes",
                    universal_name="",
                    texture_index=-1,
                    sphere_texture_index=-1,
                    surface_index_count=3,
                ),
            )
        )
        conflicting = dataclasses.replace(
            result,
            entries=(
                PmxStructuralAuthoringMaterialCatalogEntry(
                    source_index=1,
                    local_name="Eyes",
                    universal_name="",
                    texture_index=-1,
                    sphere_texture_index=-1,
                    surface_index_count=3,
                ),
                PmxStructuralAuthoringMaterialCatalogEntry(
                    source_index=1,
                    local_name="Hair",
                    universal_name="",
                    texture_index=-1,
                    sphere_texture_index=-1,
                    surface_index_count=3,
                ),
            ),
        )

        with self.assertRaises(smart_material_draft.SmartMaterialDraftError) as raised:
            smart_material_draft._material_catalog_entries(conflicting)

        self.assertEqual(raised.exception.reason, "source_evidence_mismatch")

    def test_duplicate_exact_material_names_keep_distinct_indices(self) -> None:
        plan = smart_material_draft.build_smart_material_color_draft(
            build_duplicate_eye_name_source(),
            SmartPartKind.EYES,
            "green",
        )
        self.assertEqual(
            tuple(operation.material_index for operation in plan.operations),
            (0, 1),
        )

    def test_unusual_unicode_uses_existing_nfkc_detector_authority(self) -> None:
        plan = smart_material_draft.build_smart_material_color_draft(
            build_fullwidth_eye_source(),
            SmartPartKind.EYES,
            "blue",
        )
        self.assertEqual(len(plan.operations), 1)
        self.assertEqual(plan.operations[0].material_index, 0)

    def test_malformed_top_level_inputs_are_rejected(self) -> None:
        source_bytes = build_source_bytes()
        with self.assertRaises(TypeError):
            smart_material_draft.build_smart_material_color_draft(
                bytearray(source_bytes),  # type: ignore[arg-type]
                SmartPartKind.EYES,
                "blue",
            )
        with self.assertRaises(TypeError):
            smart_material_draft.build_smart_material_color_draft(
                source_bytes,
                "eyes",  # type: ignore[arg-type]
                "blue",
            )
        with self.assertRaises(TypeError):
            smart_material_draft.build_smart_material_color_draft(
                source_bytes,
                SmartPartKind.EYES,
                [0.0, 0.0, 1.0],  # type: ignore[arg-type]
            )


if __name__ == "__main__":
    unittest.main()
