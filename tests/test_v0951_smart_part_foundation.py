from __future__ import annotations

import ast
import dataclasses
import unittest
from pathlib import Path

import mmd_registry
import mmd_registry.smart_parts as smart_parts
from mmd_registry.smart_parts import (
    SmartPart,
    SmartPartEvidence,
    SmartPartEvidenceKind,
    SmartPartKind,
)


class SmartPartFoundationTests(unittest.TestCase):
    def evidence(
        self,
        source_kind: SmartPartEvidenceKind = SmartPartEvidenceKind.MATERIAL,
        source_index: int = 4,
        reason: str = "known semantic reason",
    ) -> SmartPartEvidence:
        return SmartPartEvidence(source_kind, source_index, reason)

    def test_module_all_is_exact(self) -> None:
        self.assertEqual(
            smart_parts.__all__,
            (
                "SmartPartKind",
                "SmartPartEvidenceKind",
                "SmartPartEvidence",
                "SmartPart",
            ),
        )

    def test_smart_part_kind_values_are_exact(self) -> None:
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

    def test_smart_part_evidence_kind_values_are_exact(self) -> None:
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

    def test_valid_smart_part_evidence(self) -> None:
        evidence = self.evidence()
        self.assertIs(evidence.source_kind, SmartPartEvidenceKind.MATERIAL)
        self.assertEqual(evidence.source_index, 4)
        self.assertEqual(evidence.reason, "known semantic reason")

    def test_source_kind_must_be_enum(self) -> None:
        with self.assertRaises(TypeError):
            SmartPartEvidence("material", 0, "reason")  # type: ignore[arg-type]

    def test_bool_source_index_rejected(self) -> None:
        with self.assertRaises(TypeError):
            SmartPartEvidence(SmartPartEvidenceKind.BONE, True, "reason")

    def test_non_int_source_index_rejected(self) -> None:
        with self.assertRaises(TypeError):
            SmartPartEvidence(SmartPartEvidenceKind.BONE, 1.0, "reason")  # type: ignore[arg-type]

    def test_negative_source_index_rejected(self) -> None:
        with self.assertRaises(ValueError):
            SmartPartEvidence(SmartPartEvidenceKind.BONE, -1, "reason")

    def test_reason_must_be_string(self) -> None:
        with self.assertRaises(TypeError):
            SmartPartEvidence(SmartPartEvidenceKind.BONE, 0, 1)  # type: ignore[arg-type]

    def test_empty_or_whitespace_reason_rejected(self) -> None:
        for reason in ("", " ", "\t\r\n"):
            with self.subTest(reason=repr(reason)):
                with self.assertRaises(ValueError):
                    SmartPartEvidence(SmartPartEvidenceKind.BONE, 0, reason)

    def test_reason_text_is_not_normalized(self) -> None:
        evidence = self.evidence(reason="  Exact Reason  ")
        self.assertEqual(evidence.reason, "  Exact Reason  ")

    def test_valid_smart_part(self) -> None:
        evidence = self.evidence()
        part = SmartPart(SmartPartKind.EYES, (evidence,))
        self.assertIs(part.kind, SmartPartKind.EYES)
        self.assertEqual(part.evidence, (evidence,))

    def test_kind_must_be_enum(self) -> None:
        with self.assertRaises(TypeError):
            SmartPart("eyes", (self.evidence(),))  # type: ignore[arg-type]

    def test_evidence_must_be_tuple(self) -> None:
        with self.assertRaises(TypeError):
            SmartPart(SmartPartKind.EYES, [self.evidence()])  # type: ignore[arg-type]

    def test_evidence_must_not_be_empty(self) -> None:
        with self.assertRaises(ValueError):
            SmartPart(SmartPartKind.EYES, ())

    def test_evidence_items_must_be_typed(self) -> None:
        with self.assertRaises(TypeError):
            SmartPart(SmartPartKind.EYES, ("evidence",))  # type: ignore[arg-type]

    def test_exact_duplicate_evidence_rejected(self) -> None:
        evidence = self.evidence()
        with self.assertRaises(ValueError):
            SmartPart(SmartPartKind.EYES, (evidence, evidence))

    def test_same_source_with_different_reasons_allowed(self) -> None:
        first = self.evidence(reason="material name")
        second = self.evidence(reason="texture relationship")
        part = SmartPart(SmartPartKind.EYES, (first, second))
        self.assertEqual(len(part.evidence), 2)
        self.assertEqual(set(part.evidence), {first, second})

    def test_evidence_order_is_canonical(self) -> None:
        material_b = self.evidence(
            SmartPartEvidenceKind.MATERIAL, 5, "z reason"
        )
        bone = self.evidence(SmartPartEvidenceKind.BONE, 8, "bone reason")
        material_a = self.evidence(
            SmartPartEvidenceKind.MATERIAL, 5, "a reason"
        )
        texture = self.evidence(
            SmartPartEvidenceKind.TEXTURE, 1, "texture reason"
        )
        part = SmartPart(
            SmartPartKind.EYES,
            (texture, material_b, bone, material_a),
        )
        self.assertEqual(
            part.evidence,
            (bone, material_a, material_b, texture),
        )

    def test_input_order_does_not_affect_equality(self) -> None:
        first = self.evidence(SmartPartEvidenceKind.BONE, 2, "bone")
        second = self.evidence(SmartPartEvidenceKind.MATERIAL, 1, "material")
        self.assertEqual(
            SmartPart(SmartPartKind.CHEST, (first, second)),
            SmartPart(SmartPartKind.CHEST, (second, first)),
        )

    def test_input_order_does_not_affect_hash(self) -> None:
        first = self.evidence(SmartPartEvidenceKind.BONE, 2, "bone")
        second = self.evidence(SmartPartEvidenceKind.MATERIAL, 1, "material")
        self.assertEqual(
            hash(SmartPart(SmartPartKind.CHEST, (first, second))),
            hash(SmartPart(SmartPartKind.CHEST, (second, first))),
        )

    def test_smart_part_evidence_is_hashable(self) -> None:
        evidence = self.evidence()
        self.assertIn(evidence, {evidence})

    def test_smart_part_is_hashable(self) -> None:
        part = SmartPart(SmartPartKind.EYES, (self.evidence(),))
        self.assertIn(part, {part})

    def test_smart_part_evidence_is_frozen(self) -> None:
        evidence = self.evidence()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            evidence.reason = "changed"  # type: ignore[misc]

    def test_smart_part_is_frozen(self) -> None:
        part = SmartPart(SmartPartKind.EYES, (self.evidence(),))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            part.kind = SmartPartKind.HAIR  # type: ignore[misc]

    def test_root_public_surface_unchanged(self) -> None:
        self.assertEqual(mmd_registry.__all__, ("__version__",))
        self.assertEqual(mmd_registry.__version__, "0.9.5.1")

    def test_smart_symbols_not_root_promoted(self) -> None:
        for name in smart_parts.__all__:
            with self.subTest(name=name):
                self.assertFalse(hasattr(mmd_registry, name))

    def test_module_has_no_forbidden_authority_imports_or_names(self) -> None:
        module_path = Path(smart_parts.__file__)
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

        self.assertEqual(
            imported_modules,
            {"__future__", "dataclasses", "enum"},
        )
        forbidden_fragments = (
            "detect",
            "classif",
            "preview",
            "apply",
            "mutat",
            "writer",
            "remap",
            "transaction",
            "cli",
        )
        for name in defined_names:
            with self.subTest(name=name):
                self.assertFalse(any(fragment in name for fragment in forbidden_fragments))

    def test_no_serialization_contract(self) -> None:
        for cls in (SmartPartEvidence, SmartPart):
            with self.subTest(cls=cls.__name__):
                self.assertFalse(hasattr(cls, "to_dict"))
                self.assertFalse(hasattr(cls, "from_dict"))
                self.assertFalse(hasattr(cls, "to_json"))

    def test_dataclass_fields_are_exact(self) -> None:
        self.assertEqual(
            tuple(field.name for field in dataclasses.fields(SmartPartEvidence)),
            ("source_kind", "source_index", "reason"),
        )
        self.assertEqual(
            tuple(field.name for field in dataclasses.fields(SmartPart)),
            ("kind", "evidence"),
        )


if __name__ == "__main__":
    unittest.main()
