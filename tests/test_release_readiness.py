"""Release-readiness checks for version 0.7.0."""

from __future__ import annotations

import unittest
from pathlib import Path

from mmd_registry import __version__


PROJECT_ROOT = Path(__file__).resolve().parents[1]
README_PATH = PROJECT_ROOT / "README.md"
CHANGELOG_PATH = PROJECT_ROOT / "CHANGELOG.md"
WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "validate.yml"
RELEASE_CHECKLIST_PATH = PROJECT_ROOT / "RELEASE_CHECKLIST.md"


class ReleaseReadinessTests(unittest.TestCase):
    """Keep release metadata, documentation, and CI expectations aligned."""

    def test_package_version_is_0_7_0(self) -> None:
        self.assertEqual(__version__, "0.7.0")

    def test_readme_documents_current_version_and_schema(self) -> None:
        readme = README_PATH.read_text(encoding="utf-8")

        self.assertIn("Tool version: 0.7.0", readme)
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
        self.assertIn("never writes in place", readme)
        self.assertIn(
            "rename, reposition, reparent, or write any bone",
            readme,
        )
        self.assertIn("0 = Command completed successfully", readme)
        self.assertIn("1 = Validation failed", readme)
        self.assertIn("2 = Required input path", readme)
        self.assertIn("3 = Unexpected internal error", readme)

    def test_changelog_documents_0_7_0_capabilities(self) -> None:
        changelog = CHANGELOG_PATH.read_text(encoding="utf-8")

        self.assertIn("## 0.7.0 - 2026-08-09", changelog)
        self.assertIn("immutable `PmxDocument`", changelog)
        self.assertIn("deterministic PMX writer", changelog)
        self.assertIn("generated round-trip matrix", changelog)
        self.assertIn("`roundtrip` CLI command", changelog)
        self.assertIn("byte-identical", changelog)
        self.assertIn("563 automated tests", changelog)

    def test_workflow_checks_release_version_and_commands(self) -> None:
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

        self.assertIn("assert __version__ == '0.7.0'", workflow)
        self.assertIn("ubuntu-latest", workflow)
        self.assertIn("windows-latest", workflow)
        self.assertIn("python check_assets.py --version", workflow)
        self.assertIn("python check_assets.py scan --help", workflow)
        self.assertIn("python check_assets.py roundtrip --help", workflow)
        self.assertIn("python check_assets.py doctor --help", workflow)
        self.assertIn("python check_assets.py bones --help", workflow)
        self.assertIn("python check_assets.py rig --help", workflow)

    def test_release_checklist_covers_safe_publication_flow(self) -> None:
        checklist = RELEASE_CHECKLIST_PATH.read_text(encoding="utf-8")

        self.assertIn("MMD Asset Registry v0.7.0", checklist)
        self.assertIn("python -m unittest discover -s tests -q", checklist)
        self.assertIn("git diff --check", checklist)
        self.assertIn("Private real-model validation", checklist)
        self.assertIn("No third-party PMX", checklist)
        self.assertIn("gh pr checks", checklist)
        self.assertIn("git tag -a v0.7.0", checklist)
        self.assertIn("gh release create v0.7.0", checklist)


if __name__ == "__main__":
    unittest.main()
