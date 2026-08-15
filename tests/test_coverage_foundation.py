"""Contracts for full-suite coverage measurement and baseline reporting."""

from __future__ import annotations

import tomllib
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CoverageFoundationTests(unittest.TestCase):
    """Keep coverage complete, deterministic, descriptive, and dev-only."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.metadata = tomllib.loads(
            (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )

    def test_coverage_version_is_pinned_and_development_only(self) -> None:
        requirements = [
            line.strip()
            for line in (PROJECT_ROOT / "requirements-dev.txt")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        project = self.metadata["project"]
        build_system = self.metadata["build-system"]

        self.assertEqual(
            requirements,
            ["ruff==0.16.3", "coverage==7.15.4"],
        )
        self.assertNotIn("coverage", " ".join(project["dependencies"]).lower())
        self.assertNotIn("coverage", " ".join(build_system["requires"]).lower())
        self.assertNotIn("optional-dependencies", project)

    def test_run_configuration_measures_package_and_branches(self) -> None:
        run = self.metadata["tool"]["coverage"]["run"]

        self.assertEqual(
            run,
            {
                "branch": True,
                "relative_files": True,
                "source": ["mmd_registry"],
            },
        )

    def test_report_is_descriptive_without_a_threshold(self) -> None:
        report = self.metadata["tool"]["coverage"]["report"]

        self.assertEqual(
            report,
            {
                "precision": 2,
                "show_missing": True,
                "skip_covered": False,
            },
        )
        self.assertNotIn("fail_under", report)

    def test_json_report_path_and_format_are_explicit(self) -> None:
        json_report = self.metadata["tool"]["coverage"]["json"]

        self.assertEqual(
            json_report,
            {"output": "coverage.json", "pretty_print": True},
        )

    def test_ci_measures_the_complete_unittest_suite(self) -> None:
        workflow = (PROJECT_ROOT / ".github" / "workflows" / "validate.yml")
        source = workflow.read_text(encoding="utf-8")

        commands = (
            "python -m coverage erase",
            "python -m coverage run -m unittest discover -s tests -q",
            "python -m coverage report",
            "python -m coverage json",
        )
        positions = [source.index(command) for command in commands]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("fail-under", source)

    def test_baseline_is_recorded_as_measurement_not_threshold(self) -> None:
        quality = (PROJECT_ROOT / "docs" / "quality.md").read_text(
            encoding="utf-8"
        )
        normalized_quality = " ".join(quality.split())

        for expected in (
            "8,311",
            "7,568",
            "91.06%",
            "2,982",
            "2,404",
            "80.62%",
            "11,293",
            "9,972",
            "88.30%",
            "not a release threshold",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, normalized_quality)

    def test_generated_coverage_outputs_are_ignored(self) -> None:
        ignored = {
            line.strip()
            for line in (PROJECT_ROOT / ".gitignore")
            .read_text(encoding="utf-8")
            .splitlines()
        }

        self.assertTrue({".coverage", "coverage.json", "htmlcov/"} <= ignored)

    def test_sdist_requires_quality_contract_tests(self) -> None:
        inspector = (
            PROJECT_ROOT / "tools" / "inspect_distribution_artifacts.py"
        ).read_text(encoding="utf-8")

        self.assertIn('"tests/test_coverage_foundation.py"', inspector)
        self.assertIn('"tests/test_lint_foundation.py"', inspector)


if __name__ == "__main__":
    unittest.main()
