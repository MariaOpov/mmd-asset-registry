"""Contract tests for the pre-0.9.0 public package boundary."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType

import mmd_registry
import mmd_registry._internal as internal
import mmd_registry.capabilities as capabilities
import mmd_registry.pmx as pmx
import mmd_registry.pmx.editing as editing


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class PublicPackageArchitectureTests(unittest.TestCase):
    """Keep public, compatibility, and internal surfaces distinct."""

    def test_package_root_has_one_explicit_export(self) -> None:
        self.assertEqual(mmd_registry.__all__, ("__version__",))
        self.assertEqual(mmd_registry.__version__, "0.8.5")

        namespace: dict[str, object] = {}
        exec("from mmd_registry import *", namespace)
        exported_names = {name for name in namespace if name != "__builtins__"}
        self.assertEqual(exported_names, {"__version__"})

    def test_public_namespaces_have_complete_explicit_exports(self) -> None:
        for module in (capabilities, pmx, editing):
            with self.subTest(module=module.__name__):
                self._assert_explicit_exports(module)

    def test_internal_namespace_exports_nothing(self) -> None:
        self.assertEqual(internal.__all__, ())

        namespace: dict[str, object] = {}
        exec("from mmd_registry._internal import *", namespace)
        exported_names = {name for name in namespace if name != "__builtins__"}
        self.assertEqual(exported_names, set())

    def test_public_and_internal_imports_are_cli_independent(self) -> None:
        code = "\n".join(
            (
                "import sys",
                "import mmd_registry",
                "import mmd_registry._internal",
                "import mmd_registry.capabilities",
                "import mmd_registry.pmx",
                "import mmd_registry.pmx.editing",
                "assert 'mmd_registry.cli' not in sys.modules",
            )
        )
        environment = os.environ.copy()
        python_path = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = os.pathsep.join(
            part for part in (str(PROJECT_ROOT), python_path) if part
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            result = subprocess.run(
                [sys.executable, "-c", code],
                cwd=temporary_directory,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_legacy_modules_remain_outside_root_exports(self) -> None:
        legacy_names = {
            "capabilities",
            "cli",
            "reporting",
            "validator",
        }
        self.assertTrue(legacy_names.isdisjoint(mmd_registry.__all__))

    def _assert_explicit_exports(self, module: ModuleType) -> None:
        exports = tuple(module.__all__)
        self.assertTrue(exports)
        self.assertEqual(len(exports), len(set(exports)))

        for name in exports:
            with self.subTest(module=module.__name__, export=name):
                self.assertIsInstance(name, str)
                self.assertFalse(name.startswith("_"))
                self.assertTrue(hasattr(module, name))


if __name__ == "__main__":
    unittest.main()
