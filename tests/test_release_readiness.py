"""Release-readiness checks for final v0.9.0."""

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


class ReleaseReadinessTests(unittest.TestCase):
    """Keep release metadata, documentation, and CI expectations aligned."""

    def test_package_version_is_0_9_0(self) -> None:
        self.assertEqual(__version__, "0.9.0")

    def test_readme_documents_current_version_and_schema(self) -> None:
        readme = README_PATH.read_text(encoding="utf-8")

        self.assertIn("Tool version: 0.9.0", readme)
        self.assertIn("Release label: v0.9.0", readme)
        self.assertIn("PEP 440 Python package version", readme)
        self.assertIn("Latest registry schema: 0.3", readme)
        self.assertIn("Supported registry schemas: 0.2, 0.3", readme)

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

    def test_changelog_documents_v09_release_and_0_8_5_stabilization(self) -> None:
        changelog = CHANGELOG_PATH.read_text(encoding="utf-8")

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

        self.assertIn("assert __version__ == '0.9.0'", workflow)
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
        self.assertIn("tests.test_pmx_cross_feature_state_isolation", workflow)
        self.assertIn("tests.test_v08_backward_compatibility", workflow)
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

        self.assertIn("MMD Asset Registry v0.9.0", checklist)
        self.assertIn("distribution version is `0.9.0`", checklist)
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
        self.assertIn("1495 tests", checklist)
        self.assertIn("88.86", checklist)
        self.assertIn("wheel=85, sdist=220", checklist)
        self.assertIn("structural_write=False", checklist)
        self.assertIn("both `ubuntu-latest` and `windows-latest` jobs pass", checklist)
        self.assertIn("Verify merged main", checklist)
        self.assertIn("Never tag the feature", checklist)
        self.assertIn("git tag -a v0.9.0", checklist)
        self.assertIn("gh release create v0.9.0", checklist)
        self.assertIn("isPrerelease` is `false", checklist)
        self.assertNotIn("--prerelease", checklist)
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
