"""Release-readiness checks for version 0.4.0."""

from __future__ import annotations

import unittest
from pathlib import Path

from mmd_registry import __version__


PROJECT_ROOT = Path(__file__).resolve().parents[1]
README_PATH = PROJECT_ROOT / "README.md"
CHANGELOG_PATH = PROJECT_ROOT / "CHANGELOG.md"
WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "validate.yml"


class ReleaseReadinessTests(unittest.TestCase):
    """Keep release metadata, documentation, and CI expectations aligned."""

    def test_package_version_is_0_4_0(self) -> None:
        self.assertEqual(__version__, "0.4.0")

    def test_readme_documents_current_version_and_schema(self) -> None:
        readme = README_PATH.read_text(encoding="utf-8")

        self.assertIn("Tool version: 0.4.0", readme)
        self.assertIn("Latest registry schema: 0.3", readme)
        self.assertIn("Supported registry schemas: 0.2, 0.3", readme)

    def test_readme_documents_all_cli_commands(self) -> None:
        readme = README_PATH.read_text(encoding="utf-8")

        for command in ("validate", "hash", "inspect", "scan", "doctor"):
            with self.subTest(command=command):
                self.assertIn(f"python check_assets.py {command}", readme)

    def test_readme_documents_format_support_boundaries(self) -> None:
        readme = README_PATH.read_text(encoding="utf-8")

        self.assertIn("PMX 2.0", readme)
        self.assertIn("PMX 2.1", readme)
        self.assertIn("PMD 1.0", readme)
        self.assertIn(
            "PMD 1.0 is currently supported for header inspection only",
            readme,
        )

    def test_readme_documents_read_only_safety_and_exit_codes(self) -> None:
        readme = README_PATH.read_text(encoding="utf-8")

        self.assertIn("The tool is read-only", readme)
        self.assertIn("0 = Command completed successfully", readme)
        self.assertIn("1 = Validation failed", readme)
        self.assertIn("2 = Required input path", readme)
        self.assertIn("3 = Unexpected internal error", readme)

    def test_changelog_documents_0_4_0_capabilities(self) -> None:
        changelog = CHANGELOG_PATH.read_text(encoding="utf-8")

        self.assertIn("## 0.4.0 - 2026-08-06", changelog)
        self.assertIn(
            "Complete read-only PMX 2.0 structural scanning",
            changelog,
        )
        self.assertIn("`scan` CLI command", changelog)
        self.assertIn("`doctor` CLI command", changelog)
        self.assertIn("UTF-8 standard-stream configuration", changelog)

    def test_workflow_checks_release_version_and_commands(self) -> None:
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

        self.assertIn("assert __version__ == '0.4.0'", workflow)
        self.assertIn("python check_assets.py --version", workflow)
        self.assertIn("python check_assets.py scan --help", workflow)
        self.assertIn("python check_assets.py doctor --help", workflow)


if __name__ == "__main__":
    unittest.main()
