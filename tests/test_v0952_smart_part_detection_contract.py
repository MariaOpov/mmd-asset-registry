from __future__ import annotations

import ast
import inspect
import unittest
from pathlib import Path

import mmd_registry
import mmd_registry.smart_part_detection as detection
from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringBoneCatalogEntry,
    PmxStructuralAuthoringMaterialCatalogEntry,
    PmxStructuralAuthoringMorphCatalogEntry,
    PmxStructuralAuthoringRigidBodyCatalogEntry,
    PmxStructuralAuthoringTextureCatalogEntry,
    PmxStructuralAuthoringVertexCatalogEntry,
)
from mmd_registry.smart_parts import (
    SmartPart,
    SmartPartEvidence,
    SmartPartEvidenceKind,
    SmartPartKind,
)


class SmartPartDetectionContractTests(unittest.TestCase):
    def test_public_module_surface_is_exact(self) -> None:
        self.assertEqual(detection.__all__, ("detect_smart_parts",))

    def test_root_public_surface_remains_unchanged(self) -> None:
        self.assertEqual(mmd_registry.__all__, ("__version__",))
        self.assertEqual(mmd_registry.__version__, "0.9.5.4")
        self.assertFalse(hasattr(mmd_registry, "detect_smart_parts"))

    def test_detector_signature_has_one_input_and_tuple_output(self) -> None:
        signature = inspect.signature(detection.detect_smart_parts)
        self.assertEqual(tuple(signature.parameters), ("entries",))
        self.assertEqual(
            detection.detect_smart_parts.__annotations__["return"],
            "tuple[SmartPart, ...]",
        )

    def test_empty_input_is_empty_tuple(self) -> None:
        result = detection.detect_smart_parts(())
        self.assertIs(type(result), tuple)
        self.assertEqual(result, ())

    def test_input_container_must_be_exact_tuple(self) -> None:
        with self.assertRaises(TypeError):
            detection.detect_smart_parts([])  # type: ignore[arg-type]

    def test_unknown_entry_type_is_rejected(self) -> None:
        with self.assertRaises(TypeError):
            detection.detect_smart_parts((object(),))  # type: ignore[arg-type]

    def test_all_catalog_entry_families_are_boundary_accepted(self) -> None:
        entries = (
            PmxStructuralAuthoringVertexCatalogEntry(
                source_index=0,
                position=(0.0, 0.0, 0.0),
                deform_type=0,
            ),
            PmxStructuralAuthoringTextureCatalogEntry(
                source_index=1,
                path=r"textures\Face.png",
            ),
            PmxStructuralAuthoringMaterialCatalogEntry(
                source_index=2,
                local_name="顔",
                universal_name="Face",
                texture_index=1,
                sphere_texture_index=-1,
                surface_index_count=3,
            ),
            PmxStructuralAuthoringBoneCatalogEntry(
                source_index=3,
                local_name="右腕",
                universal_name="Right Arm",
                parent_bone_index=-1,
                position=(1.0, 2.0, 3.0),
                flag_names=("ROTATABLE",),
            ),
            PmxStructuralAuthoringMorphCatalogEntry(
                source_index=4,
                local_name="まばたき",
                universal_name="Blink",
                panel_name="EYE",
                morph_type_name="VERTEX",
                offset_count=1,
            ),
            PmxStructuralAuthoringRigidBodyCatalogEntry(
                source_index=5,
                local_name="右腕剛体",
                universal_name="Right Arm Body",
                bone_index=3,
                shape_name="CAPSULE",
                physics_mode_name="BONE_FOLLOW",
            ),
        )
        result = detection.detect_smart_parts(entries)
        self.assertIs(type(result), tuple)
        self.assertEqual(
            tuple(part.kind for part in result),
            (SmartPartKind.EYES, SmartPartKind.FACE, SmartPartKind.ARMS),
        )

    def test_cp02_shell_does_not_mutate_input_tuple(self) -> None:
        entry = PmxStructuralAuthoringMaterialCatalogEntry(
            source_index=7,
            local_name="  Ｆａｃｅ  ",
            universal_name="Face",
            texture_index=-1,
            sphere_texture_index=-1,
            surface_index_count=0,
        )
        entries = (entry,)
        before = repr(entries)
        detection.detect_smart_parts(entries)
        self.assertEqual(repr(entries), before)
        self.assertIs(entries[0], entry)

    def test_normalization_contract_is_exact(self) -> None:
        cases = (
            ("  Ｆａｃｅ　 ", "face"),
            ("Straße", "strasse"),
            ("  左ひざＤ  ", "左ひざd"),
            ("Upper\t  Body\r\n", "upper body"),
            ("", ""),
            (" \t\r\n ", ""),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(
                    detection._normalize_semantic_text(source),
                    expected,
                )

    def test_normalization_does_not_modify_source_string(self) -> None:
        source = "  Ｆａｃｅ　 "
        detection._normalize_semantic_text(source)
        self.assertEqual(source, "  Ｆａｃｅ　 ")

    def test_normalizer_rejects_non_string(self) -> None:
        with self.assertRaises(TypeError):
            detection._normalize_semantic_text(1)  # type: ignore[arg-type]

    def test_contract_constants_are_frozen_as_expected(self) -> None:
        self.assertEqual(
            detection._NORMALIZATION_CONTRACT,
            "NFKC+unicode-whitespace-collapse+casefold",
        )
        self.assertEqual(detection._MATCH_CONTRACT, "normalized-exact-alias-only")
        self.assertEqual(detection._TEXTURE_LEXICAL_SCOPE, "basename-stem-only")
        self.assertEqual(detection._EMPTY_NAME_POLICY, "ignore")
        self.assertEqual(
            detection._UNKNOWN_NAME_POLICY,
            "does-not-block-known-exact-match",
        )
        self.assertEqual(
            detection._CONFLICT_POLICY,
            "same-source-conflict-no-classification",
        )
        self.assertEqual(
            detection._DUPLICATE_EVIDENCE_POLICY,
            "deduplicate-exact-before-smart-part",
        )
        self.assertEqual(
            detection._REASON_PATTERN,
            "<source_kind>.<field_name>:exact_alias:<part_kind>",
        )
        self.assertEqual(
            detection._VERTEX_POLICY,
            "accepted-no-lexical-authority-v0.9.5.2",
        )
        self.assertEqual(
            detection._RIGID_BODY_POLICY,
            "accepted-no-lexical-authority-v0.9.5.2",
        )

    def test_part_order_contract_follows_vocabulary_declaration_order(self) -> None:
        evidence = SmartPartEvidence(
            SmartPartEvidenceKind.MATERIAL,
            0,
            "material.local_name:exact_alias:face",
        )
        reversed_parts = tuple(
            SmartPart(kind, (evidence,)) for kind in reversed(tuple(SmartPartKind))
        )
        ordered = tuple(
            sorted(reversed_parts, key=detection._smart_part_sort_key)
        )
        self.assertEqual(tuple(part.kind for part in ordered), tuple(SmartPartKind))

    def test_alias_mechanism_is_not_public_api(self) -> None:
        self.assertEqual(detection.__all__, ("detect_smart_parts",))
        self.assertFalse(any("alias" in name.lower() for name in detection.__all__))
        self.assertFalse(hasattr(mmd_registry, "_GENERIC_EXACT_ALIASES"))

    def test_no_execution_or_inference_authority(self) -> None:
        module_path = Path(detection.__file__)
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        imported_modules: set[str] = set()
        defined_names: set[str] = set()

        for node in tree.body:
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported_modules.add(node.module or "")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                defined_names.add(node.name.lower())

        forbidden_import_fragments = (
            "transaction",
            "preview",
            "apply",
            "writer",
            "remap",
            "cli",
            "bone_semantic_resolver",
            "bone_semantic_inference",
        )
        for module_name in imported_modules:
            with self.subTest(module_name=module_name):
                self.assertFalse(
                    any(
                        fragment in module_name.lower()
                        for fragment in forbidden_import_fragments
                    )
                )

        forbidden_name_fragments = (
            "confidence",
            "score",
            "fuzzy",
            "levenshtein",
            "classifier",
            "language_model",
            "transaction",
            "preview",
            "apply",
            "writer",
            "remap",
            "cli",
        )
        for name in defined_names:
            with self.subTest(name=name):
                self.assertFalse(
                    any(fragment in name for fragment in forbidden_name_fragments)
                )

    def test_detector_source_has_no_forbidden_semantic_mechanisms(self) -> None:
        source = Path(detection.__file__).read_text(encoding="utf-8").lower()
        forbidden = (
            "levenshtein",
            "difflib",
            "rapidfuzz",
            "fuzzywuzzy",
            "tensorflow",
            "torch",
            "sklearn",
            "openai",
        )
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
