"""v0.9.5.6 Smart RGB intent contract tests."""

from __future__ import annotations

import dataclasses
import math
import unittest

from mmd_registry._smart_material_color import (
    SmartMaterialColorIntent,
    normalize_smart_material_color,
)
from mmd_registry.pmx.editing.numeric import canonicalize_pmx_float32


class SmartMaterialColorContractTests(unittest.TestCase):
    def test_presets_are_exact_normalized_rgb(self) -> None:
        self.assertEqual(normalize_smart_material_color("blue").rgb, (0.0, 0.0, 1.0))
        self.assertEqual(normalize_smart_material_color("red").rgb, (1.0, 0.0, 0.0))
        self.assertEqual(normalize_smart_material_color("green").rgb, (0.0, 1.0, 0.0))
        self.assertEqual(
            normalize_smart_material_color("purple").rgb,
            (0.5, 0.0, 0.5),
        )

    def test_custom_rgb_is_float32_canonicalized_without_clamping(self) -> None:
        intent = normalize_smart_material_color((0.1, 0.25, 1.0))

        self.assertEqual(
            intent.rgb,
            (
                canonicalize_pmx_float32(0.1),
                canonicalize_pmx_float32(0.25),
                1.0,
            ),
        )

    def test_invalid_custom_rgb_contract_is_rejected(self) -> None:
        invalid_values = (
            [0.0, 0.0, 1.0],
            (0.0, 1.0),
            (0, 0.0, 1.0),
            (True, 0.0, 1.0),
            (math.nan, 0.0, 1.0),
            (math.inf, 0.0, 1.0),
            (-math.inf, 0.0, 1.0),
            (-0.1, 0.0, 1.0),
            (1.1, 0.0, 1.0),
        )

        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises((TypeError, ValueError)):
                    normalize_smart_material_color(value)  # type: ignore[arg-type]

    def test_preset_names_are_exact_and_lowercase(self) -> None:
        for value in ("Blue", " BLUE ", "cyan", ""):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    normalize_smart_material_color(value)

    def test_color_intent_is_frozen(self) -> None:
        intent = SmartMaterialColorIntent((0.0, 0.0, 1.0))

        with self.assertRaises(dataclasses.FrozenInstanceError):
            intent.rgb = (1.0, 0.0, 0.0)  # type: ignore[misc]


class SmartMaterialColorAdversarialTests(unittest.TestCase):
    def test_additional_malformed_custom_rgb_values_are_rejected(self) -> None:
        invalid_values = (
            (0.0, 0.0, 1.0, 1.0),
            ("0.1", 0.0, 1.0),
            (None, 0.0, 1.0),
            (255.0, 0.0, 0.0),
            object(),
        )
        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises((TypeError, ValueError)):
                    normalize_smart_material_color(value)  # type: ignore[arg-type]

    def test_normalized_domain_boundaries_are_accepted(self) -> None:
        self.assertEqual(
            normalize_smart_material_color((0.0, 1.0, 0.0)).rgb,
            (0.0, 1.0, 0.0),
        )
        self.assertEqual(
            normalize_smart_material_color((1.0, 0.0, 1.0)).rgb,
            (1.0, 0.0, 1.0),
        )

    def test_tiny_finite_component_uses_float32_storage_contract(self) -> None:
        intent = normalize_smart_material_color((1e-50, 0.0, 1.0))
        self.assertEqual(intent.rgb[0], canonicalize_pmx_float32(1e-50))
        self.assertEqual(intent.rgb[0], 0.0)

    def test_no_255_inference_clamping_or_case_folding_is_introduced(self) -> None:
        for value in (
            (2.0, 0.0, 0.0),
            (255.0, 0.0, 0.0),
            "Blue",
            " blue ",
        ):
            with self.subTest(value=value):
                with self.assertRaises((TypeError, ValueError)):
                    normalize_smart_material_color(value)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
