"""CP11 backward-compatibility and authority-immutability tests."""

from __future__ import annotations

import argparse
import ast
import inspect
import unittest
from pathlib import Path

import mmd_registry
import mmd_registry.cli as cli
import mmd_registry.services as services
import mmd_registry.smart_part_confidence as confidence
import mmd_registry.smart_part_detection as detection
import mmd_registry.smart_part_explainability as explainability
import mmd_registry.smart_parts as smart_parts


_LEGACY_COMMANDS = frozenset(
    {
        "validate",
        "hash",
        "inspect",
        "scan",
        "roundtrip",
        "doctor",
        "texture-portability",
        "bones",
        "rig",
        "edit",
        "edit-plan",
    }
)


def _command_choices(parser: argparse.ArgumentParser) -> frozenset[str]:
    subparsers = [
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    ]
    if len(subparsers) != 1:
        raise AssertionError(
            f"expected exactly one top-level subparser action, got {len(subparsers)}"
        )
    return frozenset(subparsers[0].choices)


class SmartCliBackwardCompatibilityAuthorityTests(unittest.TestCase):
    def test_legacy_cli_contract_is_unchanged(self) -> None:
        self.assertEqual(cli.COMMAND_NAMES, _LEGACY_COMMANDS)
        self.assertEqual(_command_choices(cli.build_argument_parser()), _LEGACY_COMMANDS)
        self.assertEqual(
            _command_choices(cli._build_runtime_argument_parser()),
            _LEGACY_COMMANDS | {"transaction-plan"},
        )
        self.assertEqual(
            _command_choices(cli._build_application_argument_parser()),
            _LEGACY_COMMANDS | {"transaction-plan", "smart"},
        )

    def test_root_package_public_surface_is_unchanged(self) -> None:
        self.assertEqual(mmd_registry.__all__, ("__version__",))
        for name in (
            "SmartPart",
            "SmartPartKind",
            "SmartPartConfidence",
            "SmartPartExplanation",
            "inspect_smart_parts",
        ):
            self.assertFalse(hasattr(mmd_registry, name), name)

    def test_smart_semantic_public_contracts_are_unchanged(self) -> None:
        self.assertEqual(
            smart_parts.__all__,
            (
                "SmartPartKind",
                "SmartPartEvidenceKind",
                "SmartPartEvidence",
                "SmartPart",
            ),
        )
        self.assertEqual(detection.__all__, ("detect_smart_parts",))
        self.assertEqual(
            explainability.__all__,
            (
                "SmartPartEvidenceExplanation",
                "SmartPartExplanation",
                "explain_smart_parts",
            ),
        )
        self.assertEqual(
            confidence.__all__,
            (
                "SmartPartConfidence",
                "SmartPartConfidenceCandidate",
                "SmartPartConfidenceAssessment",
                "assess_smart_parts",
            ),
        )

    def test_private_smart_inspection_service_is_not_promoted(self) -> None:
        self.assertFalse(hasattr(services, "inspect_smart_parts"))
        self.assertNotIn("inspect_smart_parts", getattr(services, "__all__", ()))

    def test_new_smart_modules_have_no_mutation_authority(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        paths = (
            project_root / "mmd_registry" / "smart_cli.py",
            project_root / "mmd_registry" / "services" / "_smart_inspection.py",
        )

        forbidden_import_fragments = (
            "structural_output",
            "structural_transaction",
            "transaction_plan",
            "pmx.editing",
            "remap",
            "writer",
        )
        forbidden_identifiers = {
            "apply_edit",
            "apply_structural_edit",
            "apply_structural_transaction",
            "preview_edit",
            "preview_structural_edit",
            "preview_structural_transaction",
            "write_pmx",
            "write_pmx_edit",
            "remap",
            "remapper",
        }

        for path in paths:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imports: list[str] = []
            identifiers: set[str] = set()

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.append(node.module or "")
                    identifiers.update(alias.name for alias in node.names)
                elif isinstance(node, ast.Name):
                    identifiers.add(node.id)
                elif isinstance(node, ast.Attribute):
                    identifiers.add(node.attr)

            with self.subTest(path=path.name):
                self.assertFalse(
                    any(
                        fragment in imported
                        for imported in imports
                        for fragment in forbidden_import_fragments
                    ),
                    imports,
                )
                self.assertTrue(
                    forbidden_identifiers.isdisjoint(identifiers),
                    sorted(forbidden_identifiers & identifiers),
                )

    def test_smart_inspection_service_remains_read_only_orchestration(self) -> None:
        import mmd_registry.services._smart_inspection as smart_inspection

        source = inspect.getsource(smart_inspection)
        self.assertIn("load_document", source)
        self.assertIn("inspect_structural_authoring_catalog", source)
        self.assertIn("detect_smart_parts", source)
        self.assertIn("explain_smart_parts", source)
        self.assertIn("assess_smart_parts", source)


if __name__ == "__main__":
    unittest.main()
