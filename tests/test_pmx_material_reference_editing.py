"""Tests for pure PMX material text and reference editing."""

from __future__ import annotations

import io
import unittest
from dataclasses import replace

from mmd_registry.pmx import (
    PmxValidationError,
    load_pmx,
    serialize_pmx,
    validate_pmx_document,
)
from mmd_registry.pmx.editing import (
    PmxEditAudit,
    PmxEditPlanError,
    SetModelInfo,
    UpdateMaterial,
    apply_update_material,
)
from tests.mmd_fixtures import (
    build_pmx_bone,
    build_pmx_material,
    build_pmx_structure,
)


def load_document(
    *,
    encoding_flag: int = 1,
    texture_paths: tuple[str, ...] = (
        "textures/body.png",
        "textures/sphere.spa",
        "textures/toon.bmp",
    ),
    first_toon_mode: int = 0,
    first_toon_index: int = 2,
):
    """Return a complete generated PMX with two material partitions."""

    materials = (
        build_pmx_material(
            local_name="Body",
            universal_name="Body EN",
            texture_index=0,
            sphere_texture_index=1,
            sphere_mode=2,
            toon_reference_mode=first_toon_mode,
            toon_reference_index=first_toon_index,
            memo="Body memo",
            surface_index_count=3,
            encoding_flag=encoding_flag,
        ),
        build_pmx_material(
            local_name="Face",
            universal_name="Face EN",
            texture_index=1,
            sphere_texture_index=-1,
            sphere_mode=0,
            toon_reference_mode=1,
            toon_reference_index=4,
            memo="Face memo",
            surface_index_count=3,
            encoding_flag=encoding_flag,
        ),
    )
    return load_pmx(
        io.BytesIO(
            build_pmx_structure(
                encoding_flag=encoding_flag,
                surface_indices=(0, 0, 0, 0, 0, 0),
                texture_paths=texture_paths,
                materials=materials,
                bones=(build_pmx_bone(encoding_flag=encoding_flag),),
            )
        )
    )


class PmxMaterialReferenceEditingTests(unittest.TestCase):
    """Validate immutable material text/reference updates and exact audits."""

    def test_updates_all_supported_fields_in_stable_order(self) -> None:
        source = load_document()
        operation = UpdateMaterial(
            material_index=0,
            local_name="Main Body",
            universal_name="Main Body EN",
            memo="Reviewed safely",
            texture_index=1,
            sphere_texture_index=2,
            sphere_mode=3,
            toon_reference_mode="shared",
            toon_reference_index=7,
        )

        result = apply_update_material(source, operation, operation_index=5)
        material = result.document.materials[0]

        self.assertEqual(material.local_name, "Main Body")
        self.assertEqual(material.universal_name, "Main Body EN")
        self.assertEqual(material.memo, "Reviewed safely")
        self.assertEqual(material.texture_index, 1)
        self.assertEqual(material.sphere_texture_index, 2)
        self.assertEqual(material.sphere_mode, 3)
        self.assertEqual(material.toon_reference_mode, "shared")
        self.assertEqual(material.toon_reference_index, 7)
        self.assertEqual(
            tuple(change.field_path for change in result.audit.changes),
            (
                "materials[0].local_name",
                "materials[0].universal_name",
                "materials[0].memo",
                "materials[0].texture_index",
                "materials[0].sphere_texture_index",
                "materials[0].sphere_mode",
                "materials[0].toon_reference_mode",
                "materials[0].toon_reference_index",
            ),
        )
        self.assertTrue(
            all(change.operation_index == 5 for change in result.audit.changes)
        )
        self.assertEqual(result.audit.category_count("material"), 8)
        validate_pmx_document(result.document)

    def test_audit_contains_exact_material_identity_and_values(self) -> None:
        source = load_document()

        result = apply_update_material(
            source,
            UpdateMaterial(material_index=1, memo="New face memo"),
        )

        change = result.audit.changes[0]
        self.assertEqual(change.category, "material")
        self.assertEqual(change.target_index, 1)
        self.assertEqual(change.target_name, "Face")
        self.assertEqual(change.field_path, "materials[1].memo")
        self.assertEqual(change.before, "Face memo")
        self.assertEqual(change.after, "New face memo")

    def test_noop_returns_source_without_fake_change(self) -> None:
        source = load_document()

        result = apply_update_material(
            source,
            UpdateMaterial(
                material_index=0,
                local_name=source.materials[0].local_name,
                texture_index=source.materials[0].texture_index,
            ),
        )

        self.assertIs(result.document, source)
        self.assertEqual(result.audit, PmxEditAudit())

    def test_mixed_noop_and_effective_fields_only_audits_changes(self) -> None:
        source = load_document()

        result = apply_update_material(
            source,
            UpdateMaterial(
                material_index=0,
                local_name=source.materials[0].local_name,
                memo="Changed only",
            ),
        )

        self.assertEqual(result.audit.changed_fields, 1)
        self.assertEqual(result.audit.changes[0].field_path, "materials[0].memo")

    def test_source_order_partition_and_other_material_remain_unchanged(self) -> None:
        source = load_document()
        source_bytes = serialize_pmx(source)
        original_surface_counts = tuple(
            material.surface_index_count for material in source.materials
        )

        result = apply_update_material(
            source,
            UpdateMaterial(material_index=0, local_name="Changed"),
        )

        self.assertEqual(serialize_pmx(source), source_bytes)
        self.assertEqual(len(result.document.materials), len(source.materials))
        self.assertIs(result.document.materials[1], source.materials[1])
        self.assertEqual(result.document.geometry, source.geometry)
        self.assertIs(result.document.geometry, source.geometry)
        self.assertEqual(
            tuple(
                material.surface_index_count
                for material in result.document.materials
            ),
            original_surface_counts,
        )

    def test_all_reference_sentinels_are_preserved_as_explicit_values(self) -> None:
        source = load_document()

        result = apply_update_material(
            source,
            UpdateMaterial(
                material_index=0,
                texture_index=-1,
                sphere_texture_index=-1,
                toon_reference_mode="texture",
                toon_reference_index=-1,
            ),
        )

        material = result.document.materials[0]
        self.assertEqual(material.texture_index, -1)
        self.assertEqual(material.sphere_texture_index, -1)
        self.assertEqual(material.toon_reference_index, -1)
        validate_pmx_document(result.document)

    def test_invalid_texture_references_have_exact_field_context(self) -> None:
        cases = (
            ("texture_index", {"texture_index": 3}),
            ("sphere_texture_index", {"sphere_texture_index": 3}),
            (
                "toon_reference_index",
                {
                    "toon_reference_mode": "texture",
                    "toon_reference_index": 3,
                },
            ),
        )
        for field_name, payload in cases:
            with self.subTest(field_name=field_name):
                source = load_document()
                with self.assertRaisesRegex(
                    PmxEditPlanError,
                    rf"operations\[4\]\.{field_name}.*index 3 is invalid",
                ) as context:
                    apply_update_material(
                        source,
                        UpdateMaterial(material_index=0, **payload),
                        operation_index=4,
                    )

                self.assertEqual(context.exception.field, field_name)

    def test_invalid_material_index_has_operation_context(self) -> None:
        source = load_document()

        with self.assertRaisesRegex(
            PmxEditPlanError,
            r"operations\[2\]\.material_index.*index 2 is out of range",
        ):
            apply_update_material(
                source,
                UpdateMaterial(material_index=2, memo="Out of range"),
                operation_index=2,
            )

    def test_shared_toon_final_state_is_checked_with_context(self) -> None:
        shared_source = load_document(first_toon_mode=1, first_toon_index=5)
        with self.assertRaisesRegex(
            PmxEditPlanError,
            r"operations\[3\]\.toon_reference_index.*0 through 9",
        ):
            apply_update_material(
                shared_source,
                UpdateMaterial(material_index=0, toon_reference_index=10),
                operation_index=3,
            )

        texture_paths = tuple(f"textures/{index}.png" for index in range(11))
        texture_source = load_document(
            texture_paths=texture_paths,
            first_toon_mode=0,
            first_toon_index=10,
        )
        with self.assertRaisesRegex(
            PmxEditPlanError,
            r"operations\[6\]\.toon_reference_mode.*0 through 9",
        ):
            apply_update_material(
                texture_source,
                UpdateMaterial(
                    material_index=0,
                    toon_reference_mode="shared",
                ),
                operation_index=6,
            )

    def test_toon_mode_change_maps_reference_failure_to_declared_field(self) -> None:
        source = load_document(first_toon_mode=1, first_toon_index=4)

        with self.assertRaisesRegex(
            PmxEditPlanError,
            r"operations\[8\]\.toon_reference_mode.*index 4 is invalid",
        ) as context:
            apply_update_material(
                source,
                UpdateMaterial(
                    material_index=0,
                    toon_reference_mode="texture",
                ),
                operation_index=8,
            )

        self.assertEqual(context.exception.field, "toon_reference_mode")

    def test_unicode_text_roundtrips_in_utf8_and_utf16(self) -> None:
        for encoding_flag in (0, 1):
            with self.subTest(encoding_flag=encoding_flag):
                source = load_document(encoding_flag=encoding_flag)
                result = apply_update_material(
                    source,
                    UpdateMaterial(
                        material_index=0,
                        local_name="材質・体 🌸",
                        memo="安全に編集しました",
                    ),
                )

                reparsed = load_pmx(io.BytesIO(serialize_pmx(result.document)))
                self.assertEqual(reparsed, result.document)

    def test_unencodable_material_text_has_operation_context(self) -> None:
        source = load_document()

        with self.assertRaisesRegex(
            PmxEditPlanError,
            r"operations\[7\]\.memo.*cannot be encoded",
        ):
            apply_update_material(
                source,
                UpdateMaterial(material_index=0, memo="\ud800"),
                operation_index=7,
            )

    def test_surface_partition_field_cannot_be_declared(self) -> None:
        with self.assertRaises(TypeError):
            UpdateMaterial(  # type: ignore[call-arg]
                material_index=0,
                surface_index_count=3,
            )

    def test_visual_fields_remain_outside_checkpoint_scope(self) -> None:
        source = load_document()

        with self.assertRaisesRegex(
            PmxEditPlanError,
            r"operations\[1\]\.diffuse.*visual field",
        ):
            apply_update_material(
                source,
                UpdateMaterial(
                    material_index=0,
                    diffuse=(0.5, 0.5, 0.5, 1.0),
                ),
                operation_index=1,
            )

    def test_rejects_wrong_argument_types_and_operation_index(self) -> None:
        source = load_document()
        operation = UpdateMaterial(material_index=0, memo="Changed")

        with self.assertRaisesRegex(TypeError, "PmxDocument"):
            apply_update_material(object(), operation)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "UpdateMaterial"):
            apply_update_material(
                source,
                SetModelInfo(local_name="Wrong operation"),  # type: ignore[arg-type]
            )
        with self.assertRaisesRegex(TypeError, "operation_index"):
            apply_update_material(
                source,
                operation,
                operation_index=True,  # type: ignore[arg-type]
            )
        with self.assertRaisesRegex(ValueError, "cannot be negative"):
            apply_update_material(source, operation, operation_index=-1)

    def test_complete_document_validation_still_rejects_unrelated_damage(self) -> None:
        source = load_document()
        invalid_geometry = replace(
            source.geometry,
            surface_indices=(2, *source.surface_indices[1:]),
        )
        invalid_source = replace(source, geometry=invalid_geometry)

        with self.assertRaisesRegex(
            PmxValidationError,
            r"surface_indices\[0\]",
        ):
            apply_update_material(
                invalid_source,
                UpdateMaterial(material_index=0, memo="Changed"),
            )


if __name__ == "__main__":
    unittest.main()
