from __future__ import annotations

import io
import unittest

from mmd_registry.pmx import load_pmx
import mmd_registry.services._smart_inspection as smart_inspection
import mmd_registry.services._smart_material_draft as smart_draft
from mmd_registry.services._smart_material_appearance import (
    SmartMaterialAppearanceCapabilityKind,
    SmartMaterialEdgeIntent,
    SmartMaterialSpecularIntent,
    SmartMaterialTransparencyIntent,
    build_smart_material_appearance_draft,
    resolve_smart_material_appearance_capability,
)
from mmd_registry.services._smart_material_draft import (
    SmartMaterialCapabilityStatus,
)
from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringTextureCatalogEntry,
)
from mmd_registry.smart_parts import SmartPartKind
from tests.test_v0956_smart_material_draft import (
    build_source_bytes,
    build_texture_only_eyes_source,
)


class V09510TextureMaterialOnlyHardeningTests(unittest.TestCase):
    def material_only_source(self) -> tuple[bytes, object]:
        source_bytes = build_source_bytes()
        document = load_pmx(io.BytesIO(source_bytes))
        self.assertEqual(len(document.texture_paths), 0)
        self.assertEqual(
            tuple(
                document.materials[index].texture_index
                for index in (1, 2)
            ),
            (-1, -1),
        )
        return source_bytes, document

    def assert_material_only_targets(
        self,
        draft: object,
    ) -> None:
        operations = tuple(getattr(draft, "operations", ()))
        self.assertEqual(
            tuple(operation.material_index for operation in operations),
            (1, 2),
        )
        self.assertEqual(len(operations), 2)
        for operation in operations:
            payload = operation.to_dict()
            self.assertNotIn("texture_index", payload)
            self.assertNotIn("sphere_texture_index", payload)

    def test_texture_only_hint_does_not_grant_material_edit_permission(
        self,
    ) -> None:
        source_bytes = build_texture_only_eyes_source()

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
            "unsupported_material_color",
        )

        result = smart_inspection._analyze_entries(
            (
                PmxStructuralAuthoringTextureCatalogEntry(
                    source_index=0,
                    path="eyes.png",
                ),
            )
        )
        for capability_kind in SmartMaterialAppearanceCapabilityKind:
            with self.subTest(capability_kind=capability_kind):
                capability = resolve_smart_material_appearance_capability(
                    result,
                    SmartPartKind.EYES,
                    capability_kind,
                )
                self.assertIs(
                    capability.status,
                    SmartMaterialCapabilityStatus.UNSUPPORTED,
                )
                self.assertEqual(
                    capability.reason,
                    "no_exact_material_evidence",
                )
                self.assertEqual(capability.material_indices, ())
                self.assertEqual(capability.evidence, ())

    def test_material_only_color_remains_supported_without_texture_signal(
        self,
    ) -> None:
        source_bytes, _ = self.material_only_source()

        draft = smart_draft.build_smart_material_color_draft(
            source_bytes,
            SmartPartKind.EYES,
            "red",
        )

        self.assert_material_only_targets(draft)
        self.assertTrue(
            all(
                tuple(operation.to_dict().keys())
                == ("op", "material_index", "diffuse")
                for operation in draft.operations
            )
        )

    def test_material_only_transparency_remains_supported_without_texture_signal(
        self,
    ) -> None:
        source_bytes, document = self.material_only_source()

        draft = build_smart_material_appearance_draft(
            source_bytes,
            SmartPartKind.EYES,
            SmartMaterialTransparencyIntent(alpha=0.25),
        )

        self.assert_material_only_targets(draft)
        for operation in draft.operations:
            index = operation.material_index
            self.assertEqual(
                operation.diffuse[:3],
                document.materials[index].diffuse[:3],
            )
            self.assertIsNotNone(operation.diffuse)

    def test_material_only_specular_remains_supported_without_texture_signal(
        self,
    ) -> None:
        source_bytes, _ = self.material_only_source()
        intent = SmartMaterialSpecularIntent(
            specular=(0.1, 0.2, 0.3),
            strength=1.25,
        )

        draft = build_smart_material_appearance_draft(
            source_bytes,
            SmartPartKind.EYES,
            intent,
        )

        self.assert_material_only_targets(draft)
        for operation in draft.operations:
            self.assertEqual(operation.specular, intent.specular)
            self.assertEqual(
                operation.specular_strength,
                intent.strength,
            )

    def test_material_only_edge_remains_supported_without_texture_signal(
        self,
    ) -> None:
        source_bytes, _ = self.material_only_source()
        intent = SmartMaterialEdgeIntent(
            color=(0.1, 0.2, 0.3, 0.4),
            scale=0.75,
        )

        draft = build_smart_material_appearance_draft(
            source_bytes,
            SmartPartKind.EYES,
            intent,
        )

        self.assert_material_only_targets(draft)
        for operation in draft.operations:
            self.assertEqual(operation.edge_color, intent.color)
            self.assertEqual(operation.edge_scale, intent.scale)

    def test_texture_presence_is_not_a_universal_prerequisite(self) -> None:
        source_bytes, _ = self.material_only_source()

        drafts = (
            smart_draft.build_smart_material_color_draft(
                source_bytes,
                SmartPartKind.EYES,
                "purple",
            ),
            build_smart_material_appearance_draft(
                source_bytes,
                SmartPartKind.EYES,
                SmartMaterialTransparencyIntent(alpha=0.5),
            ),
            build_smart_material_appearance_draft(
                source_bytes,
                SmartPartKind.EYES,
                SmartMaterialSpecularIntent(strength=2.0),
            ),
            build_smart_material_appearance_draft(
                source_bytes,
                SmartPartKind.EYES,
                SmartMaterialEdgeIntent(scale=1.0),
            ),
        )

        for draft in drafts:
            self.assert_material_only_targets(draft)

        with self.assertRaises(ValueError):
            SmartMaterialAppearanceCapabilityKind("material_texture")


if __name__ == "__main__":
    unittest.main()
