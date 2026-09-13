"""Release-readiness checks for v0.9.5.7."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

from mmd_registry import __version__
from mmd_registry.constants import (
    LATEST_SCHEMA_VERSION,
    SUPPORTED_SCHEMA_VERSIONS,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
README_PATH = PROJECT_ROOT / "README.md"
CHANGELOG_PATH = PROJECT_ROOT / "CHANGELOG.md"
WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "validate.yml"
RELEASE_CHECKLIST_PATH = PROJECT_ROOT / "RELEASE_CHECKLIST.md"
PUBLIC_API_PATH = PROJECT_ROOT / "docs" / "public_api.md"
PACKAGING_PATH = PROJECT_ROOT / "docs" / "packaging.md"
EXPLAINABILITY_DOC_PATH = PROJECT_ROOT / "docs" / "v0953_smart_part_explainability.md"
CONFIDENCE_DOC_PATH = PROJECT_ROOT / "docs" / "v0954_smart_part_confidence.md"
SMART_INSPECT_DOC_PATH = PROJECT_ROOT / "docs" / "v0955_smart_inspect_cli.md"
SMART_MATERIAL_DOC_PATH = PROJECT_ROOT / "docs" / "v0956_smart_material_color_draft.md"
SMART_PREVIEW_DOC_PATH = PROJECT_ROOT / "docs" / "v0957_smart_material_preview_bridge.md"


class ReleaseReadinessTests(unittest.TestCase):
    """Keep release metadata, documentation, and CI expectations aligned."""

    def test_package_version_is_0_9_5_7(self) -> None:
        self.assertEqual(__version__, "0.9.5.7")

    def test_readme_documents_current_version_and_schema(self) -> None:
        readme = README_PATH.read_text(encoding="utf-8")

        self.assertIn("Tool version: 0.9.5.7", readme)
        self.assertIn("Release label: v0.9.5.7", readme)
        self.assertIn("PEP 440 Python package version", readme)
        self.assertIn("Latest registry schema: 0.3", readme)
        self.assertIn("Supported registry schemas: 0.2, 0.3", readme)
        self.assertIn("## Version 0.9.5.7 Smart Material Preview Bridge", readme)
        self.assertIn("_smart_material_preview.py", readme)
        self.assertIn("3,114 tests", readme)
        self.assertIn("## Version 0.9.5.6 Smart Material Color Draft", readme)
        self.assertIn("## Version 0.9.5.5 Smart Inspect CLI", readme)
        self.assertIn("3,106 tests", readme)
        self.assertIn("_smart_material_color.py", readme)
        self.assertIn("_smart_material_draft.py", readme)
        self.assertIn("## Version 0.9.5.4 Confidence / Ambiguity", readme)
        self.assertIn("mmd-asset-registry smart inspect model.pmx", readme)
        self.assertIn("3,060 tests", readme)
        self.assertIn("87.01496%", readme)
        self.assertIn("mmd_registry.smart_part_explainability", readme)
        self.assertIn("mmd_registry.smart_part_confidence", readme)
        self.assertIn("98.83%", readme)
        self.assertIn("100.00%", readme)
        self.assertIn("Confidence is a presentation state", readme)
        self.assertIn("3,022 tests", readme)
        self.assertIn("87.01%", readme)
        self.assertIn("91.28%", readme)
        self.assertIn("72.09%", readme)
        self.assertIn("## Version 0.9.3 safe structural transactions", readme)
        self.assertIn("## Version 0.9.2 safe structural insertion and capacity foundation", readme)
        self.assertIn("## Version 0.9.1 safe structural execution", readme)
        self.assertIn("`structural_insert=True`", readme)
        self.assertIn("`structural_transaction=True`", readme)
        self.assertIn("`structural_write=True`", readme)
        self.assertIn('`structural_contract="reference_safe_execution"`', readme)
        self.assertIn("`apply_structural_edit()`", readme)
        packaging = PACKAGING_PATH.read_text(encoding="utf-8")
        self.assertIn("`v0.9.5.7` maps", packaging)
        self.assertIn("distribution version `0.9.5.7`", packaging)
        self.assertIn("structural preview/execution services", packaging)
        self.assertIn("structural transaction capability", packaging)
        self.assertIn("85 regular", packaging)
        self.assertIn("235 regular", packaging)
        self.assertIn("final release digests", packaging)
        self.assertIn("smart_part_explainability.py", packaging)
        self.assertIn("smart_part_confidence.py", packaging)
        self.assertIn("_smart_part_confidence.py", packaging)
        self.assertIn("smart_cli.py", packaging)
        self.assertIn("_smart_inspection.py", packaging)
        self.assertIn("_smart_material_color.py", packaging)
        self.assertIn("_smart_material_draft.py", packaging)
        self.assertIn("_smart_material_preview.py", packaging)
        normalized_packaging = " ".join(packaging.split())
        self.assertIn("does not include `docs/`", normalized_packaging)
        self.assertIn("1,666 automated tests", readme)
        self.assertIn("88.57%", readme)
        self.assertIn("85-file-member wheel", readme)
        self.assertIn("235-file-member sdist", readme)

    def test_readme_documents_all_cli_commands(self) -> None:
        readme = README_PATH.read_text(encoding="utf-8")

        for command in (
            "validate",
            "hash",
            "inspect",
            "scan",
            "roundtrip",
            "edit",
            "edit-plan",
            "texture-portability",
            "doctor",
            "bones",
            "rig",
        ):
            with self.subTest(command=command):
                self.assertIn(
                    f"python check_assets.py {command}",
                    readme,
                )

        self.assertIn("python check_assets.py smart inspect model.pmx", readme)
        self.assertIn("mmd-asset-registry smart inspect model.pmx", readme)

        for option in (
            "--tree",
            "--details",
            "--search",
            "--ik-only",
            "--unmapped",
            "--role",
            "--export-map",
            "--overwrite",
            "--plan-out",
            "--json",
        ):
            with self.subTest(option=option):
                self.assertIn(option, readme)

    def test_readme_documents_format_support_boundaries(self) -> None:
        readme = README_PATH.read_text(encoding="utf-8")

        self.assertIn("PMX 2.0", readme)
        self.assertIn("PMX 2.1", readme)
        self.assertIn("PMD 1.0", readme)
        self.assertIn(
            "PMD 1.0 is currently supported for header inspection only",
            readme,
        )

    def test_readme_documents_input_safety_and_exit_codes(self) -> None:
        readme = README_PATH.read_text(encoding="utf-8")

        self.assertIn("model and texture inputs read-only", readme)
        self.assertIn("never write in place", readme)
        self.assertIn(
            "rename, reposition, reparent, or write any bone",
            readme,
        )
        self.assertIn("0 = Command completed successfully", readme)
        self.assertIn("1 = Validation failed", readme)
        self.assertIn("2 = Required input path", readme)
        self.assertIn("3 = Unexpected internal error", readme)

    def test_readme_documents_safe_edit_contract_and_non_goals(self) -> None:
        readme = README_PATH.read_text(encoding="utf-8")

        self.assertIn("## Version 0.8 features", readme)
        self.assertIn("schema_version", readme)
        self.assertIn("expected_source_sha256", readme)
        self.assertIn("## pre-0.9.0 architecture runway", readme)
        self.assertIn("CLI-independent namespaces", readme)
        self.assertIn("installed `mmd-asset-registry` console command", readme)
        self.assertIn("does not add structural PMX editing", readme)
        self.assertIn("1,095 tests", readme)
        self.assertIn("88.26%", readme)
        self.assertIn("71-member wheel", readme)
        self.assertIn("186-member sdist", readme)
        self.assertIn("## Version 0.9.0 reference-safe structural foundation", readme)
        self.assertIn("1,495 automated tests", readme)
        self.assertIn("88.86%", readme)
        self.assertIn("85-member wheel", readme)
        self.assertIn("220-member sdist", readme)
        self.assertIn("`structural_preview=True`", readme)
        self.assertIn("`structural_write=False`", readme)
        public_api = PUBLIC_API_PATH.read_text(encoding="utf-8")
        self.assertIn("## Structural preview service", public_api)
        self.assertIn("structural_write=False", public_api)
        self.assertIn("reference_safe_preview", public_api)
        self.assertIn("structural_write=True", public_api)
        self.assertIn("reference_safe_execution", public_api)
        self.assertIn("### Structural execution service (v0.9.1)", public_api)
        self.assertIn("### Structural insertion promotion (v0.9.2)", public_api)
        self.assertIn("### Structural transaction promotion (v0.9.3)", public_api)
        self.assertIn("structural_insert=True", public_api)
        self.assertIn("structural_transaction=True", public_api)
        self.assertIn("mmd_registry.smart_parts", public_api)
        self.assertIn("SmartPartEvidence", public_api)
        self.assertIn("mmd_registry.smart_part_explainability", public_api)
        self.assertIn("SmartPartEvidenceExplanation", public_api)
        self.assertIn("SmartPartExplanation", public_api)
        self.assertIn("explain_smart_parts", public_api)
        self.assertIn("mmd_registry.smart_part_confidence", public_api)
        self.assertIn("SmartPartConfidenceAssessment", public_api)
        self.assertIn("assess_smart_parts", public_api)
        smart_doc = SMART_INSPECT_DOC_PATH.read_text(encoding="utf-8")
        self.assertIn("smart inspect SOURCE", smart_doc)
        self.assertIn("deterministic", smart_doc)
        self.assertIn("read-only", smart_doc)
        self.assertIn("AMBIGUOUS", smart_doc)
        self.assertIn("No Smart Parts detected.", smart_doc)
        self.assertIn("no JSON", smart_doc)
        self.assertIn("package root", smart_doc)
        smart_material_doc = SMART_MATERIAL_DOC_PATH.read_text(encoding="utf-8")
        self.assertIn("Smart Material Color Draft", smart_material_doc)
        self.assertIn("exact `MATERIAL` evidence", smart_material_doc)
        self.assertIn("Confidence is not permission", smart_material_doc)
        self.assertIn("PmxEditPlan", smart_material_doc)
        self.assertIn("UpdateMaterial", smart_material_doc)
        self.assertIn("preserves source alpha", smart_material_doc)
        self.assertIn("no apply", smart_material_doc)
        self.assertIn("## Smart material color draft private foundation (v0.9.5.6)", public_api)
        self.assertIn("## Smart material preview bridge private foundation (v0.9.5.7)", public_api)
        smart_preview_doc = SMART_PREVIEW_DOC_PATH.read_text(encoding="utf-8")
        self.assertIn("Smart Material Preview Bridge", smart_preview_doc)
        self.assertIn("preview_smart_material_color_draft", smart_preview_doc)
        self.assertIn("preview_edit", smart_preview_doc)
        self.assertIn("source SHA-256", smart_preview_doc)
        self.assertIn("no apply", smart_preview_doc)

        confidence_doc = CONFIDENCE_DOC_PATH.read_text(encoding="utf-8")
        self.assertIn("same_source_exact_conflict", confidence_doc)
        self.assertIn("derived_texture_only", confidence_doc)
        self.assertIn("Smart CLI remains deferred to v0.9.5.5", confidence_doc)
        explainability_doc = EXPLAINABILITY_DOC_PATH.read_text(encoding="utf-8")
        self.assertIn("shared private deterministic match trace", explainability_doc)
        self.assertIn("exact_alias", explainability_doc)
        self.assertIn("Confidence is not part of v0.9.5.3", explainability_doc)
        self.assertIn("v0.9.5.4", explainability_doc)
        self.assertIn("v0.9.5.5", explainability_doc)
        self.assertIn("--dry-run", readme)
        self.assertIn("atomic", readme)
        self.assertIn("symlink and hardlink", readme)
        self.assertIn("does not add, delete, or reorder textures", readme)
        self.assertIn("does not edit vertices, bones, morphs", readme)
        self.assertIn("intentionally non-executable", readme)
        self.assertIn("edit-plan explain", readme)
        self.assertIn("without a PMX source", readme)
        self.assertIn("texture-portability", readme)
        self.assertIn("exact on-disk component spelling", readme)
        self.assertIn("Referenced blocked dependencies prevent partial plan emission", readme)
        self.assertIn("expected_source_sha256", readme)

    def test_readme_documents_generated_and_private_edit_validation(self) -> None:
        readme = README_PATH.read_text(encoding="utf-8")

        self.assertIn("all seven model/texture/material category", readme)
        self.assertIn("Version 0.8.0 was verified", readme)
        self.assertIn("Private edit fields changed: 3", readme)
        self.assertIn("Private edit source SHA-256 before/after: matched", readme)
        self.assertIn("Private texture files touched: no", readme)
        self.assertIn("915 unit tests", readme)
        self.assertIn("918 tests", readme)
        self.assertIn("MMD_REGISTRY_PRIVATE_PMX", readme)
        self.assertIn("additional UV counts 0 through 4", readme)
        self.assertIn("884 automated tests at the version 0.8.3", readme)
        self.assertIn("840 automated tests at the version 0.8.2", readme)
        self.assertIn("Version 0.8.4 adds an optional runtime-only compatibility harness", readme)

    def test_registry_schema_remains_independent_from_tool_version(self) -> None:
        self.assertEqual(LATEST_SCHEMA_VERSION, "0.3")
        self.assertEqual(SUPPORTED_SCHEMA_VERSIONS, frozenset(("0.2", "0.3")))

    def test_changelog_documents_0_8_4_compatibility(self) -> None:
        changelog = CHANGELOG_PATH.read_text(encoding="utf-8")

        self.assertIn("## 0.8.4 - 2026-08-13", changelog)
        self.assertIn("typed named compatibility-profile foundation", changelog)
        self.assertIn("Reader/scanner compatibility matrices", changelog)
        self.assertIn("Writer/round-trip compatibility coverage", changelog)
        self.assertIn("MMD_REGISTRY_PRIVATE_PMX", changelog)
        self.assertIn("915 automated tests", changelog)
        self.assertIn("918 tests", changelog)
        self.assertIn("Registry schema remains `0.3`", changelog)
        self.assertIn("## 0.8.3 - 2026-08-12", changelog)
        self.assertIn("884 automated tests", changelog)
        self.assertIn("## 0.8.2 - 2026-08-12", changelog)
        self.assertIn("840 automated tests", changelog)
        self.assertIn("## 0.8.1 - 2026-08-12", changelog)

    def test_changelog_documents_v093_and_prior_release_history(self) -> None:
        changelog = CHANGELOG_PATH.read_text(encoding="utf-8")

        self.assertIn("## 0.9.5.7 - 2026-09-13", changelog)
        self.assertIn("Smart Material Preview Bridge", changelog)
        self.assertIn("3,114 tests", changelog)
        self.assertIn("## 0.9.5.6 - 2026-09-13", changelog)
        self.assertIn("Smart Material Color Draft", changelog)
        self.assertIn("3,106 tests", changelog)
        self.assertIn("## 0.9.5.5 - 2026-09-12", changelog)
        self.assertIn("Smart Inspect CLI", changelog)
        self.assertIn("3,060 tests", changelog)
        self.assertIn("87.01496%", changelog)
        self.assertIn("## 0.9.5.4 - 2026-09-06", changelog)
        self.assertIn("Smart Part confidence and ambiguity", changelog)
        self.assertIn("3,022 tests", changelog)
        self.assertIn("87.01%", changelog)
        self.assertIn("## 0.9.5.3 - 2026-09-06", changelog)
        self.assertIn("Smart Part evidence explanations", changelog)
        self.assertIn("2,820 tests", changelog)
        self.assertIn("ambiguity presentation remains deferred", changelog)
        self.assertIn("## 0.9.5.2 - 2026-09-05", changelog)
        self.assertIn("## 0.9.5.1 - 2026-09-03", changelog)
        self.assertIn("## 0.9.5 - 2026-09-03", changelog)
        self.assertIn("## 0.9.4 - 2026-08-29", changelog)
        self.assertIn("## 0.9.3 - 2026-08-25", changelog)
        self.assertIn("structural_transaction=True", changelog)
        self.assertIn("whole-document canonical semantic equality", changelog)
        self.assertIn("source/destination", changelog)
        self.assertIn("No PyPI publication", changelog)
        self.assertIn("## 0.9.2 - 2026-08-22", changelog)
        self.assertIn("`structural_insert=True`", changelog)
        self.assertIn("coordinated six-target insertion", changelog)
        self.assertIn("## 0.9.1 - 2026-08-19", changelog)
        self.assertIn("`PmxStructuralExecutionResult`", changelog)
        self.assertIn("`apply_structural_edit()`", changelog)
        self.assertIn("`structural_write=True`", changelog)
        self.assertIn("`reference_safe_execution`", changelog)
        self.assertIn("private-real-model safe-output validation", changelog)
        self.assertIn("1,666 automated tests", changelog)
        self.assertIn("88.57%", changelog)
        self.assertIn("85 wheel file members", changelog)
        normalized_changelog = " ".join(changelog.split())
        self.assertIn("235 sdist file members", normalized_changelog)
        self.assertIn("## 0.9.0 - 2026-08-16", changelog)
        self.assertIn("Reference-safe index remapping", changelog)
        self.assertIn("`structural_write=False`", changelog)
        self.assertIn("1,495 automated tests", changelog)
        self.assertIn("88.86%", changelog)
        self.assertIn("85-member wheel", changelog)
        self.assertIn("220-member sdist", changelog)
        self.assertIn("both Ubuntu and Windows", changelog)
        self.assertIn("## pre-0.9.0 - 2026-08-15", changelog)
        self.assertIn("distribution version `0.9.0a0`", changelog)
        self.assertIn("1,095 tests", changelog)
        self.assertIn("88.26%", changelog)
        self.assertIn("71 wheel members", changelog)
        self.assertIn("186 sdist members", changelog)
        self.assertIn("Ubuntu and Windows GitHub Actions remain mandatory", changelog)
        self.assertIn("No PyPI publication", changelog)
        self.assertIn("## 0.8.5 - 2026-08-13", changelog)
        self.assertIn("immutable capability manifest", changelog)
        self.assertIn("backward-compatibility contracts", changelog)
        self.assertIn("all 983 automated tests", changelog)
        self.assertIn("Registry schema remains `0.3`", changelog)
        self.assertIn("adds no public CLI command, UI", changelog)

    def test_workflow_checks_release_version_and_commands(self) -> None:
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

        self.assertIn("assert __version__ == '0.9.5.7'", workflow)
        self.assertIn('MMD_REGISTRY_PRIVATE_PMX: ""', workflow)
        self.assertIn("ubuntu-latest", workflow)
        self.assertIn("windows-latest", workflow)
        self.assertIn("python check_assets.py --version", workflow)
        self.assertIn("python check_assets.py scan --help", workflow)
        self.assertIn("python check_assets.py roundtrip --help", workflow)
        self.assertIn("python check_assets.py edit --help", workflow)
        self.assertIn("python check_assets.py edit-plan --help", workflow)
        self.assertIn("python check_assets.py edit-plan catalog --help", workflow)
        self.assertIn("python check_assets.py edit-plan template --help", workflow)
        self.assertIn("python check_assets.py edit-plan explain --help", workflow)
        self.assertIn("python check_assets.py texture-portability --help", workflow)
        self.assertIn("python check_assets.py doctor --help", workflow)
        self.assertIn("python check_assets.py bones --help", workflow)
        self.assertIn("python check_assets.py rig --help", workflow)
        self.assertIn("python check_assets.py transaction-plan --help", workflow)
        self.assertIn("python check_assets.py transaction-plan build --help", workflow)
        self.assertIn("python check_assets.py transaction-plan build vertex --help", workflow)
        self.assertIn("python check_assets.py transaction-plan format --help", workflow)
        self.assertIn("python check_assets.py transaction-plan preview --help", workflow)
        self.assertIn("python check_assets.py smart --help", workflow)
        self.assertIn("python check_assets.py smart inspect --help", workflow)
        self.assertIn("tests.test_pmx_edit_generated_matrix", workflow)
        self.assertIn("tests.test_pmx_private_edit_validation", workflow)
        self.assertIn("tests.test_pmx_edit_cli_diagnostics", workflow)
        self.assertIn("tests.test_pmx_edit_plan_authoring_failures", workflow)
        self.assertIn("tests.test_pmx_edit_plan_cli", workflow)
        self.assertIn("tests.test_pmx_edit_negative_safety", workflow)
        self.assertIn("tests.test_pmx_private_failure_validation", workflow)
        self.assertIn("tests.test_texture_path_semantics", workflow)
        self.assertIn("tests.test_texture_portability", workflow)
        self.assertIn("tests.test_texture_rewrite", workflow)
        self.assertIn("tests.test_texture_portability_cli", workflow)
        self.assertIn("tests.test_texture_portability_generated_matrix", workflow)
        self.assertIn("tests.test_pmx_compatibility_profiles", workflow)
        self.assertIn("tests.test_pmx_compatibility_reader_scanner", workflow)
        self.assertIn("tests.test_pmx_compatibility_boundaries", workflow)
        self.assertIn("tests.test_pmx_compatibility_writer_roundtrip", workflow)
        self.assertIn("tests.test_pmx_compatibility_cross_feature", workflow)
        self.assertIn("tests.test_pmx_compatibility_private_runtime", workflow)
        self.assertIn("tests.test_v08_contract_freeze", workflow)
        self.assertIn("tests.test_pmx_roundtrip_cli_diagnostics", workflow)
        self.assertIn("tests.test_pmx_destination_safety", workflow)
        self.assertIn("tests.test_pmx_edit_replay_determinism", workflow)
        self.assertIn("tests.test_pmx_capability_manifest", workflow)
        self.assertIn("tests.test_public_capability_api", workflow)
        self.assertIn("tests.test_public_diagnostics_api", workflow)
        self.assertIn("tests.test_stable_document_service", workflow)
        self.assertIn("tests.test_stable_validation_service", workflow)
        self.assertIn("tests.test_stable_edit_service", workflow)
        self.assertIn("tests.test_cross_platform_build_install_gate", workflow)
        self.assertIn("tests.test_v092_capability_promotion", workflow)
        self.assertIn("tests.test_v092_backward_compatibility", workflow)
        self.assertIn(
            "tests.test_v093_structural_transaction_distribution_capability",
            workflow,
        )
        self.assertIn("tests.test_v095_structural_authoring_catalog", workflow)
        self.assertIn("tests.test_v0951_smart_part_foundation", workflow)
        self.assertIn("tests.test_v0953_smart_part_match_trace_foundation", workflow)
        self.assertIn("tests.test_v0953_smart_part_explainability_provenance", workflow)
        self.assertIn("tests.test_v0953_smart_part_explainability_texture_provenance", workflow)
        self.assertIn("tests.test_v0953_smart_part_explainability_aggregation", workflow)
        self.assertIn("tests.test_v0953_smart_part_explainability_parity_adversarial", workflow)
        self.assertIn("tests.test_pmx_joint_scanning", workflow)
        self.assertIn("tests.test_v0954_confidence_foundation", workflow)
        self.assertIn("tests.test_v0954_confidence_independence", workflow)
        self.assertIn("tests.test_v0954_confidence_resolved_derivation", workflow)
        self.assertIn("tests.test_v0954_confidence_ambiguity", workflow)
        self.assertIn("tests.test_v0954_detector_explainer_parity", workflow)
        self.assertIn("tests.test_v0954_public_confidence_api", workflow)
        self.assertIn("tests.test_v0954_confidence_determinism", workflow)
        self.assertIn("tests.test_v0954_compatibility_authority", workflow)
        self.assertIn("tests.test_v0954_confidence_coverage_adversarial", workflow)
        self.assertIn("tests.test_v0955_smart_inspection_service", workflow)
        self.assertIn("tests.test_v0955_smart_cli_routing", workflow)
        self.assertIn("tests.test_v0955_smart_cli_output", workflow)
        self.assertIn("tests.test_v0955_smart_cli_evidence", workflow)
        self.assertIn("tests.test_v0955_smart_cli_ambiguity", workflow)
        self.assertIn("tests.test_v0955_smart_cli_hardening", workflow)
        self.assertIn("tests.test_v0955_smart_cli_determinism", workflow)
        self.assertIn("tests.test_v0955_smart_cli_compatibility", workflow)
        self.assertIn("tests.test_v0956_smart_material_authority_boundaries", workflow)
        self.assertIn("tests.test_v0956_smart_material_capability", workflow)
        self.assertIn("tests.test_v0956_smart_material_color_contract", workflow)
        self.assertIn("tests.test_v0956_smart_material_determinism", workflow)
        self.assertIn("tests.test_v0956_smart_material_draft", workflow)
        self.assertIn("tests.test_v0956_smart_material_grouping", workflow)
        self.assertIn("tests.test_v0957_smart_material_preview_bridge", workflow)
        self.assertIn("tests.test_v095_transaction_plan_build_vertex_cli", workflow)
        self.assertIn("tests.test_release_readiness", workflow)
        self.assertIn("tests.test_pmx_cross_feature_state_isolation", workflow)
        self.assertIn("tests.test_v08_backward_compatibility", workflow)
        for module in (
            "tests.test_v091_compatibility_contract",
            "tests.test_v091_structural_execution_contract",
            "tests.test_v091_preview_execute_parity",
            "tests.test_v091_destination_safety",
            "tests.test_v091_post_write_reparse_certification",
            "tests.test_v091_vertex_structural_execution",
            "tests.test_v091_texture_structural_execution",
            "tests.test_v091_material_structural_execution",
            "tests.test_v091_bone_structural_execution",
            "tests.test_v091_morph_structural_execution",
            "tests.test_v091_rigid_body_structural_execution",
            "tests.test_v091_cross_section_coordinated_execution",
            "tests.test_v091_atomic_structural_transaction",
            "tests.test_structural_execution_failure_provenance",
            "tests.test_pmx_structural_resource_state_isolation",
        ):
            with self.subTest(module=module):
                self.assertIn(module, workflow)
        self.assertIn(
            "python -m coverage run -m unittest discover -s tests -q",
            workflow,
        )
        self.assertIn("python -m ruff check", workflow)
        self.assertIn("python -m build --sdist --wheel", workflow)
        self.assertIn("python tools/inspect_distribution_artifacts.py dist", workflow)
        self.assertIn("python tools/verify_clean_install.py dist", workflow)

    def test_release_checklist_covers_safe_publication_flow(self) -> None:
        checklist = RELEASE_CHECKLIST_PATH.read_text(encoding="utf-8")

        self.assertIn("MMD Asset Registry v0.9.5.7", checklist)
        self.assertIn("distribution version is `0.9.5.7`", checklist)
        self.assertIn("python -m coverage run -m unittest discover -s tests -q", checklist)
        self.assertIn("git --no-pager diff --check", checklist)
        self.assertIn("python -m ruff check", checklist)
        self.assertIn("python -m build --sdist --wheel", checklist)
        self.assertIn("python tools/inspect_distribution_artifacts.py dist", checklist)
        self.assertIn("python tools/verify_clean_install.py dist", checklist)
        self.assertIn("Private asset hygiene", checklist)
        self.assertIn("MMD_REGISTRY_PRIVATE_PMX", checklist)
        self.assertIn("Optional private runtime validation is read-only", checklist)
        self.assertIn("tests.test_stable_edit_service", checklist)
        self.assertIn("Record the observed v0.9.5.7 full-suite count", checklist)
        self.assertIn("Record the observed v0.9.5.7 wheel/sdist member counts", checklist)
        self.assertIn("Recompute artifact SHA-256", checklist)
        self.assertIn("pre-commit digests are not final release digests", checklist)
        self.assertIn("structural_write=True", checklist)
        self.assertIn("structural_insert=True", checklist)
        self.assertIn("structural_transaction=True", checklist)
        self.assertIn("reference_safe_execution", checklist)
        self.assertIn("apply_structural_edit()", checklist)
        self.assertIn("both `ubuntu-latest` and `windows-latest` jobs pass", checklist)
        self.assertIn("tests.test_v091_structural_execution_contract", checklist)
        self.assertIn("tests.test_v091_atomic_structural_transaction", checklist)
        self.assertIn("tests.test_pmx_structural_resource_state_isolation", checklist)
        self.assertIn("Verify merged main", checklist)
        self.assertIn("Never tag the feature", checklist)
        self.assertIn("git tag -a v0.9.5.7", checklist)
        self.assertIn("gh release create v0.9.5.7", checklist)
        self.assertIn("isPrerelease` is `false", checklist)
        self.assertNotIn("--prerelease", checklist)
        self.assertIn("explainability remains read-only", checklist)
        self.assertIn("confidence/ambiguity layer remains read-only", checklist)
        self.assertIn("Smart Inspect CLI is read-only presentation only", checklist)
        self.assertIn("Smart Material Color Draft is private draft composition only", checklist)
        self.assertIn("Smart Material Preview Bridge is private preview delegation only", checklist)
        self.assertIn("tests.test_v0957_smart_material_preview_bridge", checklist)
        self.assertIn("Do not publish the wheel or sdist to PyPI", checklist)

    def test_tracked_pmx_files_are_only_empty_placeholders(self) -> None:
        result = subprocess.run(
            ["git", "ls-files", "*.pmx"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        tracked_pmx_paths = tuple(
            PROJECT_ROOT / line
            for line in result.stdout.splitlines()
            if line
        )

        self.assertTrue(tracked_pmx_paths)
        for path in tracked_pmx_paths:
            with self.subTest(path=path.relative_to(PROJECT_ROOT)):
                self.assertEqual(path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
