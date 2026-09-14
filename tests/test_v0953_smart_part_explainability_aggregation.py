from __future__ import annotations

import ast
import dataclasses
import inspect
import unittest
from pathlib import Path

import mmd_registry
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


class SmartPartExplainabilityAggregationTests(unittest.TestCase):
    def material(
        self,
        *,
        source_index: int = 0,
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

    def bone(
        self,
        *,
        source_index: int = 0,
        local_name: str = "",
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

    def texture(
        self,
        *,
        source_index: int = 0,
        path: str = "",
    ) -> PmxStructuralAuthoringTextureCatalogEntry:
        return PmxStructuralAuthoringTextureCatalogEntry(
            source_index=source_index,
            path=path,
        )

    def test_public_submodule_contract_is_exact(self) -> None:
        self.assertEqual(
            explainability.__all__,
            (
                "SmartPartEvidenceExplanation",
                "SmartPartExplanation",
                "explain_smart_parts",
            ),
        )
        self.assertEqual(
            tuple(
                field.name
                for field in dataclasses.fields(
                    explainability.SmartPartEvidenceExplanation
                )
            ),
            (
                "evidence",
                "source_field",
                "source_value",
                "comparison_value",
                "normalized_value",
                "matched_alias",
                "match_rule",
                "derivation",
            ),
        )
        self.assertEqual(
            tuple(
                field.name
                for field in dataclasses.fields(
                    explainability.SmartPartExplanation
                )
            ),
            ("kind", "evidence"),
        )
        self.assertEqual(
            tuple(
                inspect.signature(
                    explainability.explain_smart_parts
                ).parameters
            ),
            ("entries",),
        )

    def test_root_api_and_runtime_version_are_unchanged(self) -> None:
        self.assertEqual(mmd_registry.__all__, ("__version__",))
        self.assertEqual(mmd_registry.__version__, "0.9.5.8")
        self.assertFalse(hasattr(mmd_registry, "explain_smart_parts"))
        self.assertFalse(
            hasattr(mmd_registry, "SmartPartEvidenceExplanation")
        )
        self.assertFalse(hasattr(mmd_registry, "SmartPartExplanation"))

    def test_explanation_dtos_are_frozen_and_slotted(self) -> None:
        result = explainability.explain_smart_parts(
            (self.material(source_index=1, local_name="Face"),)
        )
        explanation = result[0]
        evidence = explanation.evidence[0]

        with self.assertRaises(dataclasses.FrozenInstanceError):
            explanation.kind = SmartPartKind.HAIR  # type: ignore[misc]
        with self.assertRaises(dataclasses.FrozenInstanceError):
            evidence.source_field = "changed"  # type: ignore[misc]
        self.assertFalse(hasattr(explanation, "__dict__"))
        self.assertFalse(hasattr(evidence, "__dict__"))

    def test_empty_input_returns_empty_tuple(self) -> None:
        self.assertEqual(explainability.explain_smart_parts(()), ())

    def test_invalid_container_preserves_detector_tuple_boundary(self) -> None:
        with self.assertRaises(TypeError):
            explainability.explain_smart_parts([])  # type: ignore[arg-type]

    def test_named_and_texture_provenance_project_exactly(self) -> None:
        entries = (
            self.material(
                source_index=2,
                local_name="顔",
                universal_name="Face",
            ),
            self.texture(
                source_index=3,
                path=r"textures\Hair.png",
            ),
        )

        result = explainability.explain_smart_parts(entries)

        self.assertEqual(
            tuple(item.kind for item in result),
            (SmartPartKind.HAIR, SmartPartKind.FACE),
        )

        hair = result[0].evidence[0]
        self.assertIs(
            hair.evidence.source_kind,
            SmartPartEvidenceKind.TEXTURE,
        )
        self.assertEqual(hair.source_field, "path")
        self.assertEqual(hair.source_value, r"textures\Hair.png")
        self.assertEqual(hair.comparison_value, "Hair")
        self.assertEqual(hair.normalized_value, "hair")
        self.assertEqual(hair.matched_alias, "hair")
        self.assertEqual(
            hair.derivation,
            (("basename", "Hair.png"), ("basename_stem", "Hair")),
        )

        face_evidence = result[1].evidence
        self.assertEqual(
            tuple(item.source_field for item in face_evidence),
            ("local_name", "universal_name"),
        )
        self.assertEqual(
            tuple(item.source_value for item in face_evidence),
            ("顔", "Face"),
        )
        self.assertTrue(
            all(item.derivation == () for item in face_evidence)
        )

    def test_part_kind_order_follows_smart_part_kind_declaration_order(self) -> None:
        entries = (
            self.material(source_index=9, local_name="Face"),
            self.material(source_index=8, local_name="Hair"),
            self.texture(source_index=7, path="eye.png"),
            self.bone(source_index=6, universal_name="Right Arm"),
        )

        result = explainability.explain_smart_parts(entries)

        expected = tuple(
            kind
            for kind in SmartPartKind
            if kind
            in {
                SmartPartKind.EYES,
                SmartPartKind.HAIR,
                SmartPartKind.FACE,
                SmartPartKind.ARMS,
            }
        )
        self.assertEqual(
            tuple(item.kind for item in result),
            expected,
        )

    def test_inner_evidence_order_matches_detector_canonical_order(self) -> None:
        entries = (
            self.material(source_index=8, universal_name="Face"),
            self.material(source_index=2, local_name="Face"),
            self.material(
                source_index=5,
                local_name="顔",
                universal_name="Face",
            ),
        )

        explanations = explainability.explain_smart_parts(entries)
        detected = detection.detect_smart_parts(entries)

        self.assertEqual(len(explanations), 1)
        self.assertEqual(len(detected), 1)
        self.assertEqual(
            tuple(
                item.evidence
                for item in explanations[0].evidence
            ),
            detected[0].evidence,
        )

    def test_exact_duplicate_detector_evidence_is_deduplicated(self) -> None:
        entries = (
            self.material(source_index=5, local_name="Face"),
            self.material(source_index=5, local_name="FACE"),
            self.material(source_index=5, local_name="  Ｆａｃｅ　 "),
        )

        explanations = explainability.explain_smart_parts(entries)
        detected = detection.detect_smart_parts(entries)

        self.assertEqual(len(explanations), 1)
        self.assertEqual(len(explanations[0].evidence), 1)
        self.assertEqual(len(detected[0].evidence), 1)
        self.assertEqual(
            explanations[0].evidence[0].evidence,
            detected[0].evidence[0],
        )

    def test_duplicate_representative_is_deterministic_across_input_order(self) -> None:
        entries = (
            self.material(source_index=5, local_name="Face"),
            self.material(source_index=5, local_name="FACE"),
            self.material(source_index=5, local_name="  Ｆａｃｅ　 "),
        )

        forward = explainability.explain_smart_parts(entries)
        reverse = explainability.explain_smart_parts(
            tuple(reversed(entries))
        )

        self.assertEqual(forward, reverse)

    def test_conflict_produces_no_public_explanation(self) -> None:
        entry = self.material(
            source_index=11,
            local_name="Face",
            universal_name="Hair",
        )

        self.assertEqual(
            explainability.explain_smart_parts((entry,)),
            (),
        )
        self.assertEqual(detection.detect_smart_parts((entry,)), ())

    def test_explanation_evidence_tuple_is_exact_detector_evidence_tuple(self) -> None:
        entries = (
            self.material(
                source_index=2,
                local_name="顔",
                universal_name="Face",
            ),
            self.bone(source_index=4, universal_name="Right Arm"),
            self.texture(source_index=1, path=r"textures\eye.png"),
            self.texture(source_index=7, path="face.png"),
        )

        explanations = explainability.explain_smart_parts(entries)
        detected = detection.detect_smart_parts(entries)

        self.assertEqual(
            tuple(item.kind for item in explanations),
            tuple(item.kind for item in detected),
        )
        self.assertEqual(
            tuple(
                (
                    item.kind,
                    tuple(
                        evidence.evidence
                        for evidence in item.evidence
                    ),
                )
                for item in explanations
            ),
            tuple(
                (item.kind, item.evidence)
                for item in detected
            ),
        )

    def test_result_is_input_permutation_independent(self) -> None:
        entries = (
            self.material(source_index=3, universal_name="Face"),
            self.bone(source_index=4, universal_name="Right Arm"),
            self.texture(source_index=1, path="eye.png"),
        )

        self.assertEqual(
            explainability.explain_smart_parts(entries),
            explainability.explain_smart_parts(
                tuple(reversed(entries))
            ),
        )

    def test_core_module_has_no_cli_mutation_or_alias_authority_symbols(
        self,
    ) -> None:
        source = Path(explainability.__file__).read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)

        imported_roots = {
            alias.name.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported_roots.update(
            node.module.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module
        )
        self.assertFalse(
            imported_roots
            & {
                "argparse",
                "subprocess",
                "os",
                "pathlib",
                "shutil",
                "requests",
            }
        )

        module_symbols: set[str] = set()
        for node in tree.body:
            if isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
            ):
                module_symbols.add(node.name)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = (
                    node.targets
                    if isinstance(node, ast.Assign)
                    else (node.target,)
                )
                for target in targets:
                    if isinstance(target, ast.Name):
                        module_symbols.add(target.id)

        forbidden_fragments = (
            "confidence",
            "fuzzy",
            "score",
            "candidate",
            "transaction",
            "preview",
            "apply",
            "writer",
            "remap",
            "alias_index",
            "exact_aliases",
        )
        for symbol in module_symbols:
            lowered = symbol.casefold()
            self.assertFalse(
                any(
                    fragment in lowered
                    for fragment in forbidden_fragments
                ),
                symbol,
            )


if __name__ == "__main__":
    unittest.main()
