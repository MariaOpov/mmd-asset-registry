from __future__ import annotations

import ast
import inspect
import subprocess
import sys
import unittest
from dataclasses import fields
from pathlib import Path

import mmd_registry
import mmd_registry._smart_part_confidence as private_confidence
import mmd_registry.smart_part_confidence as confidence
import mmd_registry.smart_part_detection as detection
import mmd_registry.smart_part_explainability as explainability
from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringBoneCatalogEntry,
    PmxStructuralAuthoringMaterialCatalogEntry,
    PmxStructuralAuthoringTextureCatalogEntry,
)
from mmd_registry.smart_parts import (
    SmartPartEvidenceKind,
    SmartPartKind,
)


class SmartPartV0954CompatibilityAuthorityTests(unittest.TestCase):
    def material(self, source_index: int, local_name: str = "", universal_name: str = ""):
        return PmxStructuralAuthoringMaterialCatalogEntry(
            source_index=source_index,
            local_name=local_name,
            universal_name=universal_name,
            texture_index=-1,
            sphere_texture_index=-1,
            surface_index_count=0,
        )

    def bone(self, source_index: int, local_name: str = "", universal_name: str = ""):
        return PmxStructuralAuthoringBoneCatalogEntry(
            source_index=source_index,
            local_name=local_name,
            universal_name=universal_name,
            parent_bone_index=-1,
            position=(0.0, 0.0, 0.0),
            flag_names=(),
        )

    def texture(self, source_index: int, path: str):
        return PmxStructuralAuthoringTextureCatalogEntry(
            source_index=source_index,
            path=path,
        )

    def test_root_public_surface_is_not_expanded(self) -> None:
        self.assertEqual(mmd_registry.__all__, ("__version__",))
        self.assertFalse(hasattr(mmd_registry, "SmartPartConfidence"))
        self.assertFalse(hasattr(mmd_registry, "SmartPartConfidenceCandidate"))
        self.assertFalse(hasattr(mmd_registry, "SmartPartConfidenceAssessment"))
        self.assertFalse(hasattr(mmd_registry, "assess_smart_parts"))

    def test_detector_public_surface_is_unchanged(self) -> None:
        self.assertEqual(detection.__all__, ("detect_smart_parts",))

    def test_explainer_public_surface_is_unchanged(self) -> None:
        self.assertEqual(
            explainability.__all__,
            (
                "SmartPartEvidenceExplanation",
                "SmartPartExplanation",
                "explain_smart_parts",
            ),
        )

    def test_confidence_public_surface_is_exact(self) -> None:
        self.assertEqual(
            confidence.__all__,
            (
                "SmartPartConfidence",
                "SmartPartConfidenceCandidate",
                "SmartPartConfidenceAssessment",
                "assess_smart_parts",
            ),
        )

    def test_existing_smart_part_enum_orders_are_unchanged(self) -> None:
        self.assertEqual(
            tuple(item.value for item in SmartPartKind),
            (
                "eyes",
                "hair",
                "face",
                "skin",
                "chest",
                "upper_body",
                "lower_body",
                "arms",
                "hands",
                "legs",
                "feet",
                "clothing",
                "shoes",
                "accessories",
                "materials",
            ),
        )
        self.assertEqual(
            tuple(item.value for item in SmartPartEvidenceKind),
            (
                "vertex",
                "texture",
                "material",
                "bone",
                "morph",
                "rigid_body",
            ),
        )

    def test_confidence_dto_shapes_match_frozen_contract(self) -> None:
        self.assertEqual(
            tuple(field.name for field in fields(confidence.SmartPartConfidenceCandidate)),
            ("kind", "evidence"),
        )
        self.assertEqual(
            tuple(field.name for field in fields(confidence.SmartPartConfidenceAssessment)),
            ("confidence", "candidates", "reason"),
        )
        self.assertEqual(
            tuple(item.value for item in confidence.SmartPartConfidence),
            ("high", "medium", "low", "ambiguous"),
        )

    def test_assess_signature_has_no_authority_options(self) -> None:
        signature = inspect.signature(confidence.assess_smart_parts)
        self.assertEqual(tuple(signature.parameters), ("entries",))
        parameter = signature.parameters["entries"]
        self.assertIs(parameter.default, inspect.Parameter.empty)

    def test_assessment_does_not_change_released_detector_or_explainer(self) -> None:
        entries = (
            self.material(1, "Face", "FACE"),
            self.bone(2, "Right Arm"),
            self.texture(3, "hair.png"),
        )
        detector_before = detection.detect_smart_parts(entries)
        explainer_before = explainability.explain_smart_parts(entries)
        for _ in range(20):
            confidence.assess_smart_parts(entries)
        self.assertEqual(detection.detect_smart_parts(entries), detector_before)
        self.assertEqual(explainability.explain_smart_parts(entries), explainer_before)

    def test_ambiguity_does_not_change_released_conflict_filter(self) -> None:
        entries = (self.material(10, "Face", "Hair"),)
        assessed = confidence.assess_smart_parts(entries)
        self.assertEqual(len(assessed), 1)
        self.assertIs(
            assessed[0].confidence,
            confidence.SmartPartConfidence.AMBIGUOUS,
        )
        self.assertEqual(detection.detect_smart_parts(entries), ())
        self.assertEqual(explainability.explain_smart_parts(entries), ())

    def _module_imports(self, module) -> set[str]:
        source = inspect.getsource(module)
        tree = ast.parse(source)
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        return imports

    def test_public_confidence_has_no_forbidden_authority_imports(self) -> None:
        imports = self._module_imports(confidence)
        forbidden_fragments = (
            "transaction_plan",
            "structural_transaction",
            "preview",
            "apply",
            "writer",
            "remap",
            "transaction_plan_cli",
            "subprocess",
            "pathlib",
        )
        self.assertFalse(
            any(
                fragment in imported
                for imported in imports
                for fragment in forbidden_fragments
            ),
            imports,
        )

    def test_private_confidence_has_no_forbidden_authority_imports(self) -> None:
        imports = self._module_imports(private_confidence)
        forbidden_fragments = (
            "transaction_plan",
            "structural_transaction",
            "preview",
            "apply",
            "writer",
            "remap",
            "transaction_plan_cli",
            "subprocess",
            "pathlib",
        )
        self.assertFalse(
            any(
                fragment in imported
                for imported in imports
                for fragment in forbidden_fragments
            ),
            imports,
        )

    def test_public_confidence_source_has_no_cli_or_mutation_symbols(self) -> None:
        source = inspect.getsource(confidence)
        forbidden_tokens = (
            "argparse",
            "click.",
            "typer.",
            "write_bytes(",
            "write_text(",
            "open(",
            "os.replace",
            "os.remove",
            "unlink(",
            "rename(",
            "git ",
        )
        self.assertFalse(any(token in source for token in forbidden_tokens))

    def test_private_confidence_source_has_no_cli_or_mutation_symbols(self) -> None:
        source = inspect.getsource(private_confidence)
        forbidden_tokens = (
            "argparse",
            "click.",
            "typer.",
            "write_bytes(",
            "write_text(",
            "open(",
            "os.replace",
            "os.remove",
            "unlink(",
            "rename(",
            "git ",
        )
        self.assertFalse(any(token in source for token in forbidden_tokens))

    def test_fresh_import_does_not_pull_transaction_authority_modules(self) -> None:
        script = r"""
import sys
import mmd_registry.smart_part_confidence
forbidden = (
    "mmd_registry.pmx.transaction_plan",
    "mmd_registry.services.structural_transaction",
    "mmd_registry.services.structural_transaction_plan_preview",
    "mmd_registry.services.structural_transaction_plan_apply",
    "mmd_registry.transaction_plan_cli",
)
loaded = tuple(name for name in forbidden if name in sys.modules)
assert loaded == (), loaded
print("FRESH_IMPORT_AUTHORITY_ISOLATION=PASS")
"""
        cp = subprocess.run(
            [sys.executable, "-c", script],
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertIn("FRESH_IMPORT_AUTHORITY_ISOLATION=PASS", cp.stdout)

    def test_private_module_exports_nothing_public(self) -> None:
        self.assertEqual(private_confidence.__all__, ())


if __name__ == "__main__":
    unittest.main()
