"""Tests for pure PMX material visual-property editing."""

from __future__ import annotations

import io
import math
import struct
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
    UpdateMaterial,
    apply_update_material,
    canonicalize_pmx_float32,
)
from tests.mmd_fixtures import (
    build_pmx_bone,
    build_pmx_material,
    build_pmx_structure,
)


def load_document(
    *,
    diffuse: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0),
    specular: tuple[float, float, float] = (0.0, 0.0, 0.0),
    specular_strength: float = 0.0,
    ambient: tuple[float, float, float] = (0.5, 0.5, 0.5),
    drawing_flags: int = 0,
    edge_color: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0),
    edge_scale: float = 1.0,
):
    """Return a complete generated PMX with two material partitions."""

    materials = (
        build_pmx_material(
            local_name="Body",
            universal_name="Body EN",
            diffuse=diffuse,
            specular=specular,
            specular_strength=specular_strength,
            ambient=ambient,
            drawing_flags=drawing_flags,
            edge_color=edge_color,
            edge_scale=edge_scale,
            texture_index=0,
            sphere_texture_index=1,
            sphere_mode=2,
            toon_reference_mode=0,
            toon_reference_index=2,
            memo="Body memo",
            surface_index_count=3,
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
        ),
    )
    return load_pmx(
        io.BytesIO(
            build_pmx_structure(
                surface_indices=(0, 0, 0, 0, 0, 0),
                texture_paths=(
                    "textures/body.png",
                    "textures/sphere.spa",
                    "textures/toon.bmp",
                ),
                materials=materials,
                bones=(build_pmx_bone(),),
            )
        )
    )


class PmxMaterialVisualEditingTests(unittest.TestCase):
    """Validate exact visual updates, float32 storage, and safe failures."""

    def test_updates_all_visual_fields_in_stable_order(self) -> None:
        source = load_document()
        operation = UpdateMaterial(
            material_index=0,
            diffuse=(0.25, 0.5, 0.75, 0.875),
            specular=(0.125, 0.25, 0.5),
            specular_strength=0.625,
            ambient=(0.125, 0.25, 0.375),
            drawing_flags=0xFF,
            edge_color=(0.25, 0.5, 0.75, 0.5),
            edge_scale=1.5,
        )

        result = apply_update_material(source, operation, operation_index=6)
        material = result.document.materials[0]

        self.assertEqual(material.diffuse, operation.diffuse)
        self.assertEqual(material.specular, operation.specular)
        self.assertEqual(
            material.specular_strength,
            operation.specular_strength,
        )
        self.assertEqual(material.ambient, operation.ambient)
        self.assertEqual(material.drawing_flags, 0xFF)
        self.assertEqual(material.edge_color, operation.edge_color)
        self.assertEqual(material.edge_scale, operation.edge_scale)
        self.assertEqual(
            tuple(change.field_path for change in result.audit.changes),
            (
                "materials[0].diffuse",
                "materials[0].specular",
                "materials[0].specular_strength",
                "materials[0].ambient",
                "materials[0].drawing_flags",
                "materials[0].edge_color",
                "materials[0].edge_scale",
            ),
        )
        self.assertTrue(
            all(change.operation_index == 6 for change in result.audit.changes)
        )
        validate_pmx_document(result.document)

    def test_float_values_are_canonicalized_before_storage_and_audit(self) -> None:
        source = load_document()
        operation = UpdateMaterial(
            material_index=0,
            diffuse=(0.1, 0.2, 0.3, 0.4),
            specular_strength=0.1,
        )
        expected_diffuse = tuple(
            struct.unpack("<f", struct.pack("<f", value))[0]
            for value in operation.diffuse
        )
        expected_strength = struct.unpack("<f", struct.pack("<f", 0.1))[0]

        result = apply_update_material(source, operation)

        self.assertEqual(result.document.materials[0].diffuse, expected_diffuse)
        self.assertEqual(
            result.document.materials[0].specular_strength,
            expected_strength,
        )
        self.assertEqual(result.audit.changes[0].after, expected_diffuse)
        self.assertEqual(result.audit.changes[1].after, expected_strength)
        self.assertEqual(operation.diffuse, (0.1, 0.2, 0.3, 0.4))
        self.assertEqual(
            operation.to_dict()["diffuse"],
            [0.1, 0.2, 0.3, 0.4],
        )

    def test_float32_equivalent_update_is_a_noop(self) -> None:
        source = load_document(diffuse=(0.1, 0.2, 0.3, 0.4))

        result = apply_update_material(
            source,
            UpdateMaterial(
                material_index=0,
                diffuse=(0.1, 0.2, 0.3, 0.4),
            ),
        )

        self.assertIs(result.document, source)
        self.assertEqual(result.audit, PmxEditAudit())

    def test_finite_values_are_not_clamped(self) -> None:
        source = load_document()

        result = apply_update_material(
            source,
            UpdateMaterial(
                material_index=0,
                diffuse=(-2.0, 3.5, 8.0, -0.5),
                specular_strength=99.0,
                edge_color=(4.0, -3.0, 2.0, 7.0),
                edge_scale=-1.25,
            ),
        )
        material = result.document.materials[0]

        self.assertEqual(material.diffuse, (-2.0, 3.5, 8.0, -0.5))
        self.assertEqual(material.specular_strength, 99.0)
        self.assertEqual(material.edge_color, (4.0, -3.0, 2.0, 7.0))
        self.assertEqual(material.edge_scale, -1.25)
        validate_pmx_document(result.document)

    def test_scalar_outside_float32_range_has_operation_context(self) -> None:
        source = load_document()

        with self.assertRaisesRegex(
            PmxEditPlanError,
            (
                r"operations\[3\]\.specular_strength.*outside the finite "
                r"IEEE-754 float32 range"
            ),
        ) as context:
            apply_update_material(
                source,
                UpdateMaterial(material_index=0, specular_strength=1e40),
                operation_index=3,
            )

        self.assertEqual(context.exception.field, "specular_strength")

    def test_vector_component_outside_range_has_exact_context(self) -> None:
        source = load_document()

        with self.assertRaisesRegex(
            PmxEditPlanError,
            r"operations\[4\]\.diffuse\[2\].*outside.*float32 range",
        ) as context:
            apply_update_material(
                source,
                UpdateMaterial(
                    material_index=0,
                    diffuse=(0.0, 1.0, 1e40, 1.0),
                ),
                operation_index=4,
            )

        self.assertEqual(context.exception.field, "diffuse[2]")

    def test_complete_document_validator_rejects_float32_overflow(self) -> None:
        source = load_document()
        invalid_material = replace(
            source.materials[0],
            specular_strength=1e40,
        )
        invalid_document = replace(
            source,
            materials=(invalid_material, source.materials[1]),
        )

        with self.assertRaisesRegex(
            PmxValidationError,
            (
                r"materials\[0\]\.specular_strength.*finite IEEE-754 "
                r"float32 range"
            ),
        ):
            validate_pmx_document(invalid_document)

        with self.assertRaises(PmxValidationError):
            serialize_pmx(invalid_document)

    def test_roundtrip_and_repeated_serialization_are_deterministic(self) -> None:
        source = load_document()
        result = apply_update_material(
            source,
            UpdateMaterial(
                material_index=0,
                diffuse=(0.1, 0.2, 0.3, 0.4),
                specular=(0.9, 0.8, 0.7),
                specular_strength=0.6,
                ambient=(0.05, 0.15, 0.25),
                edge_color=(0.4, 0.3, 0.2, 0.1),
                edge_scale=1.1,
            ),
        )

        first = serialize_pmx(result.document)
        second = serialize_pmx(result.document)
        reparsed = load_pmx(io.BytesIO(first))

        self.assertEqual(first, second)
        self.assertEqual(reparsed, result.document)

    def test_edit_preserves_source_geometry_order_and_partitions(self) -> None:
        source = load_document()
        source_bytes = serialize_pmx(source)
        surface_counts = tuple(
            material.surface_index_count for material in source.materials
        )

        result = apply_update_material(
            source,
            UpdateMaterial(material_index=0, diffuse=(0.5, 0.5, 0.5, 0.5)),
        )

        self.assertEqual(serialize_pmx(source), source_bytes)
        self.assertIs(result.document.geometry, source.geometry)
        self.assertIs(result.document.materials[1], source.materials[1])
        self.assertEqual(
            tuple(
                material.surface_index_count
                for material in result.document.materials
            ),
            surface_counts,
        )

    def test_text_reference_and_visual_fields_can_share_one_operation(self) -> None:
        source = load_document()

        result = apply_update_material(
            source,
            UpdateMaterial(
                material_index=0,
                local_name="Main Body",
                texture_index=1,
                diffuse=(0.25, 0.5, 0.75, 1.0),
                drawing_flags=0x1F,
            ),
        )

        self.assertEqual(result.document.materials[0].local_name, "Main Body")
        self.assertEqual(result.document.materials[0].texture_index, 1)
        self.assertEqual(
            tuple(change.field_path for change in result.audit.changes),
            (
                "materials[0].local_name",
                "materials[0].texture_index",
                "materials[0].diffuse",
                "materials[0].drawing_flags",
            ),
        )

    def test_drawing_flag_byte_boundaries_are_supported(self) -> None:
        high_result = apply_update_material(
            load_document(),
            UpdateMaterial(material_index=0, drawing_flags=0xFF),
        )
        low_result = apply_update_material(
            load_document(drawing_flags=0xFF),
            UpdateMaterial(material_index=0, drawing_flags=0),
        )

        self.assertEqual(high_result.document.materials[0].drawing_flags, 0xFF)
        self.assertEqual(low_result.document.materials[0].drawing_flags, 0)
        with self.assertRaisesRegex(ValueError, "unsigned byte"):
            UpdateMaterial(material_index=0, drawing_flags=0x100)

    def test_public_float32_helper_exposes_pmx_storage_contract(self) -> None:
        expected = struct.unpack("<f", struct.pack("<f", 0.1))[0]

        self.assertEqual(canonicalize_pmx_float32(0.1), expected)
        self.assertEqual(canonicalize_pmx_float32(1e-50), 0.0)
        with self.assertRaisesRegex(TypeError, "must be a float"):
            canonicalize_pmx_float32(1)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "must be finite"):
            canonicalize_pmx_float32(math.inf)
        with self.assertRaisesRegex(ValueError, "float32 range"):
            canonicalize_pmx_float32(1e40)


if __name__ == "__main__":
    unittest.main()
