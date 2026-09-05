from __future__ import annotations

import ast
import dataclasses
import unittest
from pathlib import Path

import mmd_registry
import mmd_registry.smart_part_detection as detection
import mmd_registry.smart_parts as smart_parts
from mmd_registry.services import structural_authoring_catalog as catalog
from mmd_registry.smart_parts import (
    SmartPart,
    SmartPartEvidence,
    SmartPartEvidenceKind,
    SmartPartKind,
)


class SmartPartDetectionBackwardCompatibilityTests(unittest.TestCase):
    def test_root_package_surface_is_unchanged(self) -> None:
        self.assertEqual(mmd_registry.__version__, "0.9.5.3")
        self.assertEqual(mmd_registry.__all__, ("__version__",))
        self.assertFalse(hasattr(mmd_registry, "detect_smart_parts"))

    def test_smart_parts_public_surface_is_unchanged(self) -> None:
        self.assertEqual(
            smart_parts.__all__,
            (
                "SmartPartKind",
                "SmartPartEvidenceKind",
                "SmartPartEvidence",
                "SmartPart",
            ),
        )
        self.assertFalse(hasattr(smart_parts, "detect_smart_parts"))

    def test_detector_public_surface_is_narrow(self) -> None:
        self.assertEqual(detection.__all__, ("detect_smart_parts",))
        self.assertEqual(mmd_registry.__all__, ("__version__",))
        self.assertFalse(hasattr(mmd_registry, "detect_smart_parts"))

    def test_smart_part_vocabulary_is_unchanged(self) -> None:
        self.assertEqual(
            tuple((item.name, item.value) for item in SmartPartKind),
            (
                ("EYES", "eyes"),
                ("HAIR", "hair"),
                ("FACE", "face"),
                ("SKIN", "skin"),
                ("CHEST", "chest"),
                ("UPPER_BODY", "upper_body"),
                ("LOWER_BODY", "lower_body"),
                ("ARMS", "arms"),
                ("HANDS", "hands"),
                ("LEGS", "legs"),
                ("FEET", "feet"),
                ("CLOTHING", "clothing"),
                ("SHOES", "shoes"),
                ("ACCESSORIES", "accessories"),
                ("MATERIALS", "materials"),
            ),
        )

    def test_evidence_vocabulary_is_unchanged(self) -> None:
        self.assertEqual(
            tuple((item.name, item.value) for item in SmartPartEvidenceKind),
            (
                ("VERTEX", "vertex"),
                ("TEXTURE", "texture"),
                ("MATERIAL", "material"),
                ("BONE", "bone"),
                ("MORPH", "morph"),
                ("RIGID_BODY", "rigid_body"),
            ),
        )

    def test_smart_part_dataclass_fields_remain_exact(self) -> None:
        self.assertEqual(
            tuple(field.name for field in dataclasses.fields(SmartPartEvidence)),
            ("source_kind", "source_index", "reason"),
        )
        self.assertEqual(
            tuple(field.name for field in dataclasses.fields(SmartPart)),
            ("kind", "evidence"),
        )

    def test_catalog_entry_type_alias_still_covers_six_families(self) -> None:
        names = {
            "PmxStructuralAuthoringVertexCatalogEntry",
            "PmxStructuralAuthoringTextureCatalogEntry",
            "PmxStructuralAuthoringMaterialCatalogEntry",
            "PmxStructuralAuthoringBoneCatalogEntry",
            "PmxStructuralAuthoringMorphCatalogEntry",
            "PmxStructuralAuthoringRigidBodyCatalogEntry",
        }
        for name in names:
            with self.subTest(name=name):
                self.assertTrue(hasattr(catalog, name))

    def test_detector_imports_no_execution_authority_modules(self) -> None:
        tree = ast.parse(Path(detection.__file__).read_text(encoding="utf-8"))
        imported_modules: set[str] = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported_modules.add(node.module or "")

        forbidden = (
            "transaction",
            "preview",
            "apply",
            "writer",
            "remap",
            "transaction_plan_cli",
            "bone_semantic_resolver",
            "bone_semantic_inference",
        )
        for module_name in imported_modules:
            with self.subTest(module_name=module_name):
                self.assertFalse(
                    any(token in module_name.lower() for token in forbidden)
                )

    def test_detector_import_dependency_is_one_way(self) -> None:
        older_modules = (
            Path(smart_parts.__file__),
            Path(catalog.__file__),
            Path(mmd_registry.__file__),
        )
        for path in older_modules:
            with self.subTest(path=str(path)):
                source = path.read_text(encoding="utf-8")
                self.assertNotIn("smart_part_detection", source)

    def test_execution_authority_modules_do_not_depend_on_detector(self) -> None:
        root = Path(detection.__file__).resolve().parents[1]
        authority_paths = (
            root / "mmd_registry" / "pmx" / "transaction_plan.py",
            root / "mmd_registry" / "services" / "structural_transaction.py",
            root
            / "mmd_registry"
            / "services"
            / "structural_transaction_plan_preview.py",
            root
            / "mmd_registry"
            / "services"
            / "structural_transaction_plan_apply.py",
            root / "mmd_registry" / "transaction_plan_cli.py",
        )
        for path in authority_paths:
            with self.subTest(path=str(path)):
                source = path.read_text(encoding="utf-8")
                self.assertNotIn("smart_part_detection", source)
                self.assertNotIn("detect_smart_parts", source)

    def test_detector_has_no_filesystem_or_process_authority_imports(self) -> None:
        tree = ast.parse(Path(detection.__file__).read_text(encoding="utf-8"))
        imported_modules: set[str] = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported_modules.add(node.module or "")
        forbidden_roots = {"os", "pathlib", "subprocess", "shutil", "tempfile"}
        self.assertTrue(
            all(module.split(".", 1)[0] not in forbidden_roots for module in imported_modules)
        )

    def test_detector_rejects_non_catalog_objects(self) -> None:
        with self.assertRaises(TypeError):
            detection.detect_smart_parts((object(),))  # type: ignore[arg-type]

    def test_detector_returns_existing_smart_part_type(self) -> None:
        entry = catalog.PmxStructuralAuthoringMaterialCatalogEntry(
            source_index=1,
            local_name="Face",
            universal_name="Face",
            texture_index=-1,
            sphere_texture_index=-1,
            surface_index_count=0,
        )
        result = detection.detect_smart_parts((entry,))
        self.assertEqual(len(result), 1)
        self.assertIs(type(result[0]), SmartPart)

    def test_detector_does_not_mutate_catalog_entry(self) -> None:
        entry = catalog.PmxStructuralAuthoringMaterialCatalogEntry(
            source_index=2,
            local_name="  Ｆａｃｅ  ",
            universal_name="Face",
            texture_index=-1,
            sphere_texture_index=-1,
            surface_index_count=0,
        )
        before = repr(entry)
        detection.detect_smart_parts((entry,))
        self.assertEqual(repr(entry), before)

    def test_detector_source_has_no_serialization_contract(self) -> None:
        for name in detection.__all__:
            self.assertNotIn("json", name.lower())
            self.assertNotIn("serialize", name.lower())
            self.assertNotIn("dict", name.lower())


if __name__ == "__main__":
    unittest.main()
