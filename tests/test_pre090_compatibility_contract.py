"""Freeze representative v0.8.5 contracts before architecture refactors."""

from __future__ import annotations

import importlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import check_assets
import mmd_registry.pmx as pmx
import mmd_registry.pmx.editing as editing
from mmd_registry import __version__, cli
from mmd_registry.pmx.document import PmxDocument
from mmd_registry.pmx.editing.diagnostics import PmxEditDiagnostic
from mmd_registry.pmx.editing.engine import (
    PmxEditResult,
    apply_pmx_edit_plan,
)
from mmd_registry.pmx.editing.json_loader import (
    load_pmx_edit_plan,
    parse_pmx_edit_plan_json,
)
from mmd_registry.pmx.editing.operations import (
    SetModelInfo,
    SetTexturePath,
    UpdateMaterial,
)
from mmd_registry.pmx.editing.output import (
    PmxEditWriteResult,
    write_pmx_edit,
)
from mmd_registry.pmx.editing.plan import PmxEditPlan
from mmd_registry.pmx.editing.preview import (
    PmxEditPreview,
    dry_run_pmx_edit,
)
from mmd_registry.pmx.editing.validation import validate_pmx_edit_plan
from mmd_registry.pmx.errors import PmxValidationError, PmxValidationIssue
from mmd_registry.pmx.reader import load_pmx, read_pmx_document
from mmd_registry.pmx.roundtrip import (
    PmxRoundTripResult,
    roundtrip_pmx,
)
from mmd_registry.pmx.validation import validate_pmx_document
from mmd_registry.pmx.writer import serialize_pmx, write_pmx


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Pre090CompatibilityContractTests(unittest.TestCase):
    """Protect v0.8.5 callers while public/service boundaries are introduced."""

    def test_representative_pmx_namespace_exports_keep_identity(self) -> None:
        expected_exports = {
            "PmxDocument": PmxDocument,
            "PmxRoundTripResult": PmxRoundTripResult,
            "PmxValidationError": PmxValidationError,
            "PmxValidationIssue": PmxValidationIssue,
            "load_pmx": load_pmx,
            "read_pmx_document": read_pmx_document,
            "roundtrip_pmx": roundtrip_pmx,
            "serialize_pmx": serialize_pmx,
            "validate_pmx_document": validate_pmx_document,
            "write_pmx": write_pmx,
        }

        for name, expected in expected_exports.items():
            with self.subTest(name=name):
                self.assertIn(name, pmx.__all__)
                self.assertIs(getattr(pmx, name), expected)

    def test_representative_editing_namespace_exports_keep_identity(self) -> None:
        expected_exports = {
            "PmxEditDiagnostic": PmxEditDiagnostic,
            "PmxEditPlan": PmxEditPlan,
            "PmxEditPreview": PmxEditPreview,
            "PmxEditResult": PmxEditResult,
            "PmxEditWriteResult": PmxEditWriteResult,
            "SetModelInfo": SetModelInfo,
            "SetTexturePath": SetTexturePath,
            "UpdateMaterial": UpdateMaterial,
            "apply_pmx_edit_plan": apply_pmx_edit_plan,
            "dry_run_pmx_edit": dry_run_pmx_edit,
            "load_pmx_edit_plan": load_pmx_edit_plan,
            "parse_pmx_edit_plan_json": parse_pmx_edit_plan_json,
            "validate_pmx_edit_plan": validate_pmx_edit_plan,
            "write_pmx_edit": write_pmx_edit,
        }

        for name, expected in expected_exports.items():
            with self.subTest(name=name):
                self.assertIn(name, editing.__all__)
                self.assertIs(getattr(editing, name), expected)

    def test_registry_and_capability_entrypoints_remain_importable(self) -> None:
        expected_members = {
            "mmd_registry.capabilities": (
                "PmxCapabilityManifest",
                "get_pmx_capability_manifest",
            ),
            "mmd_registry.reporting": (
                "build_json_report",
                "generate_credits_markdown",
                "write_credits_file",
                "write_json_report",
            ),
            "mmd_registry.validator": (
                "AssetValidationResult",
                "RegistryValidationResult",
                "validate_asset",
                "validate_registry",
            ),
        }

        for module_name, member_names in expected_members.items():
            module = importlib.import_module(module_name)
            for member_name in member_names:
                with self.subTest(
                    module=module_name,
                    member=member_name,
                ):
                    self.assertTrue(hasattr(module, member_name))

    def test_legacy_script_still_delegates_to_cli_main(self) -> None:
        self.assertIs(check_assets.main, cli.main)

    def test_module_and_script_version_invocations_remain_compatible(self) -> None:
        expected_output = f"mmd-asset-registry {__version__}\n"
        invocations = (
            (
                "module",
                [sys.executable, "-m", "mmd_registry.cli", "--version"],
                PROJECT_ROOT,
            ),
            (
                "script",
                [
                    sys.executable,
                    str(PROJECT_ROOT / "check_assets.py"),
                    "--version",
                ],
                None,
            ),
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            for label, command, fixed_cwd in invocations:
                with self.subTest(invocation=label):
                    result = subprocess.run(
                        command,
                        cwd=fixed_cwd or temporary_directory,
                        check=False,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout, expected_output)
                    self.assertEqual(result.stderr, "")

    def test_core_imports_do_not_load_cli_or_emit_output(self) -> None:
        code = "\n".join(
            (
                "import sys",
                "import mmd_registry.pmx",
                "import mmd_registry.pmx.editing",
                "import mmd_registry.capabilities",
                "assert 'mmd_registry.cli' not in sys.modules",
            )
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
