"""Contracts for the disposable clean-install verification gate."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.verify_clean_install import (
    PROBE_RESULT_PREFIX,
    PROBE_SOURCE,
    CleanInstallVerificationError,
    _parse_probe_result,
    _validate_help,
    _validate_work_parent,
    clean_subprocess_environment,
    environment_paths,
    install_arguments,
)


class CleanInstallTests(unittest.TestCase):
    """Keep the installation gate isolated, dependency-aware, and portable."""

    def test_subprocess_environment_removes_source_and_venv_injection(self) -> None:
        environment = clean_subprocess_environment(
            {
                "MMD_REGISTRY_PRIVATE_PMX": "private.pmx",
                "PATH": "original-path",
                "PYTHONHOME": "python-home",
                "PYTHONPATH": "repository-root",
                "VIRTUAL_ENV": "development-venv",
                "__PYVENV_LAUNCHER__": "launcher",
            }
        )

        self.assertEqual(environment["PATH"], "original-path")
        self.assertEqual(environment["PIP_DISABLE_PIP_VERSION_CHECK"], "1")
        self.assertEqual(environment["PYTHONDONTWRITEBYTECODE"], "1")
        self.assertEqual(environment["PYTHONNOUSERSITE"], "1")
        for name in (
            "MMD_REGISTRY_PRIVATE_PMX",
            "PYTHONHOME",
            "PYTHONPATH",
            "VIRTUAL_ENV",
            "__PYVENV_LAUNCHER__",
        ):
            with self.subTest(name=name):
                self.assertNotIn(name, environment)

    def test_environment_paths_cover_windows_and_posix_launchers(self) -> None:
        root = Path("clean-environment")

        windows = environment_paths(root, windows=True)
        posix = environment_paths(root, windows=False)

        self.assertEqual(windows.python, root / "Scripts" / "python.exe")
        self.assertEqual(
            windows.console,
            root / "Scripts" / "mmd-asset-registry.exe",
        )
        self.assertEqual(posix.python, root / "bin" / "python")
        self.assertEqual(
            posix.console,
            root / "bin" / "mmd-asset-registry",
        )

    def test_default_install_resolves_dependencies_from_the_local_wheel(self) -> None:
        python = Path("venv") / "python"
        wheel = Path("dist") / "package.whl"
        arguments = install_arguments(
            python,
            wheel,
        )

        self.assertEqual(
            arguments[:6],
            [str(python), "-I", "-m", "pip", "--isolated", "install"],
        )
        self.assertIn("--no-input", arguments)
        self.assertNotIn("--no-deps", arguments)
        self.assertNotIn("--no-index", arguments)
        self.assertEqual(Path(arguments[-1]), wheel.resolve())

    def test_offline_install_requires_explicit_no_index_and_wheelhouse(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            wheelhouse = Path(temporary_directory)
            python = Path("venv") / "python"
            wheel = Path("dist") / "package.whl"
            arguments = install_arguments(
                python,
                wheel,
                no_index=True,
                find_links=(wheelhouse,),
            )

        self.assertIn("--no-index", arguments)
        index = arguments.index("--find-links")
        self.assertEqual(arguments[index + 1], str(wheelhouse.resolve()))
        self.assertNotIn("--no-deps", arguments)

    def test_workspace_parent_must_be_external_and_existing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            inside = root / "inside"
            outside = root.parent
            inside.mkdir()

            with self.assertRaisesRegex(
                CleanInstallVerificationError,
                "outside the repository",
            ):
                _validate_work_parent(inside, root)

            _validate_work_parent(outside, root)

            with self.assertRaisesRegex(
                CleanInstallVerificationError,
                "does not exist",
            ):
                _validate_work_parent(root / "missing", root)

    def test_probe_is_valid_python_and_checks_installed_origins(self) -> None:
        compile(PROBE_SOURCE, "probe_installed_package.py", "exec")

        self.assertIn("sys.prefix != sys.base_prefix", PROBE_SOURCE)
        self.assertIn("repository path leaked into sys.path", PROBE_SOURCE)
        self.assertIn("package did not load from clean venv", PROBE_SOURCE)
        self.assertIn("dependency did not load from clean venv", PROBE_SOURCE)
        self.assertIn("runtime version mismatch", PROBE_SOURCE)
        self.assertIn("public capability exports mismatch", PROBE_SOURCE)
        self.assertIn("installed capability manifest mismatch", PROBE_SOURCE)
        self.assertIn("public diagnostic exports mismatch", PROBE_SOURCE)
        self.assertIn("installed diagnostic redaction mismatch", PROBE_SOURCE)
        self.assertIn("installed document service mismatch", PROBE_SOURCE)
        self.assertIn("installed document diagnostic mismatch", PROBE_SOURCE)
        self.assertIn("installed valid-document validation mismatch", PROBE_SOURCE)
        self.assertIn("installed invalid-document validation mismatch", PROBE_SOURCE)
        self.assertIn("installed validation diagnostic mismatch", PROBE_SOURCE)
        self.assertIn("installed reference analysis mismatch", PROBE_SOURCE)
        self.assertIn("installed reference-node diagnostic mismatch", PROBE_SOURCE)
        self.assertIn("installed structural preview status mismatch", PROBE_SOURCE)
        self.assertIn("installed structural preview output mismatch", PROBE_SOURCE)
        self.assertIn("installed structural preview verification mismatch", PROBE_SOURCE)
        self.assertIn("installed edit preview verification mismatch", PROBE_SOURCE)
        self.assertIn("installed edit apply verification mismatch", PROBE_SOURCE)
        self.assertIn("installed edit diagnostic mismatch", PROBE_SOURCE)
        self.assertIn("installed entry-point metadata mismatch", PROBE_SOURCE)
        self.assertIn("next(iter(distribution.entry_points)).load()", PROBE_SOURCE)
        self.assertNotIn("distribution.entry_points[0]", PROBE_SOURCE)

    def test_probe_result_requires_one_exact_typed_payload(self) -> None:
        payload = {
            "dependency_path": "/tmp/venv/site-packages/yaml/__init__.py",
            "environment_root": "/tmp/venv",
            "package_path": "/tmp/venv/site-packages/mmd_registry/__init__.py",
            "version": "0.9.0",
            "working_directory": "/tmp/work",
        }
        output = PROBE_RESULT_PREFIX + json.dumps(payload, sort_keys=True)

        self.assertEqual(_parse_probe_result(output), payload)

        with self.assertRaisesRegex(
            CleanInstallVerificationError,
            "exactly one result",
        ):
            _parse_probe_result("")

        invalid_payload = dict(payload, unexpected="value")
        with self.assertRaisesRegex(
            CleanInstallVerificationError,
            "unexpected schema",
        ):
            _parse_probe_result(
                PROBE_RESULT_PREFIX + json.dumps(invalid_payload)
            )

    def test_console_help_must_preserve_public_command_identity(self) -> None:
        _validate_help(
            "usage: mmd-asset-registry [-h] [--version] COMMAND ...\n"
        )

        with self.assertRaisesRegex(
            CleanInstallVerificationError,
            "public CLI contract",
        ):
            _validate_help("usage: renamed-command [-h]\n")


if __name__ == "__main__":
    unittest.main()
