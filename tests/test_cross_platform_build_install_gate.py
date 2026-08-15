"""Contracts for the Ubuntu and Windows distribution validation gate."""

from __future__ import annotations

import tomllib
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "validate.yml"


class CrossPlatformBuildInstallGateTests(unittest.TestCase):
    """Keep both CI platforms on one complete non-publishing package gate."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        cls.metadata = tomllib.loads(
            (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )

    def test_validation_job_targets_ubuntu_and_windows(self) -> None:
        source = self.workflow

        self.assertIn("runs-on: ${{ matrix.os }}", source)
        self.assertIn("fail-fast: false", source)
        matrix_position = source.index("matrix:")
        setup_position = source.index("steps:", matrix_position)
        matrix = source[matrix_position:setup_position]
        self.assertEqual(matrix.count("ubuntu-latest"), 1)
        self.assertEqual(matrix.count("windows-latest"), 1)

    def test_each_matrix_job_builds_inspects_and_clean_installs(self) -> None:
        commands = (
            "python -m build --sdist --wheel",
            "python tools/inspect_distribution_artifacts.py dist",
            "python tools/verify_clean_install.py dist",
        )
        positions = [self.workflow.index(command) for command in commands]

        self.assertEqual(positions, sorted(positions))
        self.assertEqual(
            self.workflow.count(
                "python -c \"import shutil; "
                "shutil.rmtree('dist', ignore_errors=True)\""
            ),
            1,
        )

    def test_build_frontend_is_pinned_and_development_only(self) -> None:
        requirements = [
            line.strip()
            for line in (PROJECT_ROOT / "requirements-dev.txt")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        project = self.metadata["project"]
        build_system = self.metadata["build-system"]

        self.assertEqual(requirements.count("build==1.5.0"), 1)
        self.assertNotIn("build", " ".join(project["dependencies"]).lower())
        self.assertNotIn(
            "build",
            " ".join(build_system["requires"]).lower(),
        )

    def test_gate_has_no_artifact_publication_step(self) -> None:
        lowered = self.workflow.lower()

        for forbidden in (
            "pypa/gh-action-pypi-publish",
            "python -m twine upload",
            "gh release create",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, lowered)

    def test_packaging_policy_records_the_two_platform_gate(self) -> None:
        policy = (PROJECT_ROOT / "docs" / "packaging.md").read_text(
            encoding="utf-8"
        )

        for expected in (
            "ubuntu-latest",
            "windows-latest",
            "python -m build --sdist --wheel",
            "python tools/inspect_distribution_artifacts.py dist",
            "python tools/verify_clean_install.py dist",
            "does not upload or publish artifacts",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, policy)


if __name__ == "__main__":
    unittest.main()
