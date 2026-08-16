"""Contracts for the v0.9.0 packaging metadata foundation."""

from __future__ import annotations

import re
import tomllib
import unittest
from pathlib import Path

from mmd_registry import __version__


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"


class PackagingMetadataTests(unittest.TestCase):
    """Keep build metadata narrow, deterministic, and version-safe."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.metadata = tomllib.loads(
            PYPROJECT_PATH.read_text(encoding="utf-8")
        )

    def test_build_backend_is_explicit_and_build_only(self) -> None:
        build_system = self.metadata["build-system"]

        self.assertEqual(build_system["build-backend"], "setuptools.build_meta")
        self.assertEqual(
            build_system["requires"],
            ["setuptools>=68", "wheel>=0.41"],
        )

    def test_project_identity_and_python_floor_are_explicit(self) -> None:
        project = self.metadata["project"]

        self.assertEqual(project["name"], "mmd-asset-registry")
        self.assertEqual(project["requires-python"], ">=3.12")
        self.assertEqual(project["readme"], "README.md")
        self.assertTrue((PROJECT_ROOT / project["readme"]).is_file())
        self.assertEqual(
            project["urls"]["Repository"],
            "https://github.com/MariaOpov/mmd-asset-registry",
        )

    def test_distribution_version_has_one_runtime_source(self) -> None:
        project = self.metadata["project"]
        dynamic = self.metadata["tool"]["setuptools"]["dynamic"]

        self.assertNotIn("version", project)
        self.assertEqual(project["dynamic"], ["version"])
        self.assertEqual(
            dynamic["version"],
            {"attr": "mmd_registry.__version__"},
        )
        self.assertEqual(__version__, "0.9.0")
        self.assertRegex(
            __version__,
            re.compile(r"^[0-9]+(?:\.[0-9]+){2}$"),
        )

    def test_runtime_dependencies_match_legacy_requirements(self) -> None:
        requirement_lines = [
            line.strip()
            for line in (PROJECT_ROOT / "requirements.txt")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]

        self.assertEqual(
            self.metadata["project"]["dependencies"],
            requirement_lines,
        )
        self.assertEqual(requirement_lines, ["PyYAML>=6.0"])

    def test_package_discovery_excludes_repository_only_packages(self) -> None:
        setuptools = self.metadata["tool"]["setuptools"]
        discovery = setuptools["packages"]["find"]

        self.assertFalse(setuptools["include-package-data"])
        self.assertEqual(discovery["where"], ["."])
        self.assertEqual(discovery["include"], ["mmd_registry*"])
        self.assertEqual(discovery["exclude"], ["tests*"])
        self.assertFalse(discovery["namespaces"])

    def test_console_script_is_explicit_and_later_metadata_is_deferred(self) -> None:
        project = self.metadata["project"]

        self.assertEqual(
            project["scripts"],
            {"mmd-asset-registry": "mmd_registry.cli:main"},
        )
        self.assertNotIn("optional-dependencies", project)
        self.assertNotIn("license", project)
        self.assertNotIn("license-files", project)

    def test_build_outputs_are_ignored_without_hiding_source(self) -> None:
        ignored = set(
            (PROJECT_ROOT / ".gitignore")
            .read_text(encoding="utf-8")
            .splitlines()
        )

        self.assertTrue({"build/", "dist/", "*.egg-info/"} <= ignored)
        self.assertNotIn("pyproject.toml", ignored)


if __name__ == "__main__":
    unittest.main()
