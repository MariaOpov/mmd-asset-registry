"""Contracts for the minimal correctness-focused lint foundation."""

from __future__ import annotations

import tomllib
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class LintFoundationTests(unittest.TestCase):
    """Keep lint deterministic, narrow, and development-only."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.metadata = tomllib.loads(
            (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )

    def test_ruff_version_and_python_target_are_explicit(self) -> None:
        ruff = self.metadata["tool"]["ruff"]

        self.assertEqual(ruff["required-version"], "==0.16.3")
        self.assertEqual(ruff["target-version"], "py312")

    def test_lint_rule_set_is_minimal_and_exact(self) -> None:
        lint = self.metadata["tool"]["ruff"]["lint"]

        self.assertEqual(lint, {"select": ["E9", "F63", "F7", "F82"]})

    def test_ruff_is_development_only(self) -> None:
        development_requirements = [
            line.strip()
            for line in (PROJECT_ROOT / "requirements-dev.txt")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        project = self.metadata["project"]
        build_system = self.metadata["build-system"]

        self.assertIn("ruff==0.16.3", development_requirements)
        self.assertNotIn("ruff", " ".join(project["dependencies"]).lower())
        self.assertNotIn("ruff", " ".join(build_system["requires"]).lower())
        self.assertNotIn("optional-dependencies", project)

    def test_ci_installs_and_runs_the_exact_gate(self) -> None:
        workflow = (PROJECT_ROOT / ".github" / "workflows" / "validate.yml")
        source = workflow.read_text(encoding="utf-8")

        self.assertIn(
            "python -m pip install -r requirements-dev.txt",
            source,
        )
        self.assertIn(
            "python -m ruff check mmd_registry tests tools check_assets.py",
            source,
        )
        self.assertNotIn("ruff format", source)
        self.assertNotIn("ruff check --fix", source)

    def test_sdist_carries_the_lint_requirement(self) -> None:
        manifest = {
            line.strip()
            for line in (PROJECT_ROOT / "MANIFEST.in")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        }

        self.assertIn("include requirements-dev.txt", manifest)

    def test_generated_cache_is_ignored(self) -> None:
        ignored = {
            line.strip()
            for line in (PROJECT_ROOT / ".gitignore")
            .read_text(encoding="utf-8")
            .splitlines()
        }

        self.assertIn(".ruff_cache/", ignored)


if __name__ == "__main__":
    unittest.main()
