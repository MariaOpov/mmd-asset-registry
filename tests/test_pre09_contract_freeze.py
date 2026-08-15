"""Aggregate pre-0.9.0 public, installed, and compatibility contract freeze."""

from __future__ import annotations

import importlib
import inspect
import json
import os
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

import mmd_registry
import mmd_registry.capabilities as capabilities
import mmd_registry.diagnostics as diagnostics
import mmd_registry.pmx as pmx
import mmd_registry.pmx.editing as editing
import mmd_registry.services as services
from mmd_registry.pmx.editing.errors import PmxEditPlanError
from mmd_registry.pmx.editing.json_loader import parse_pmx_edit_plan_json
from mmd_registry.pmx.editing.plan import PMX_EDIT_PLAN_SCHEMA_VERSION
from tools.verify_clean_install import COMMAND_NAME, ENTRY_POINT_VALUE


PROJECT_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_SERVICE_EXPORTS = (
    "PmxDocumentMetadata",
    "PmxDocumentValidationResult",
    "apply_edit",
    "get_capabilities",
    "inspect_document",
    "load_document",
    "preview_edit",
    "validate_document",
)

REQUIRED_PMX_EXPORTS = frozenset(
    (
        "PmxDocument",
        "PmxHeader",
        "PmxIndexSizes",
        "PmxMaterial",
        "PmxBone",
        "PmxMorph",
        "PmxDisplayFrame",
        "PmxRigidBody",
        "PmxJoint",
        "PmxSoftBody",
        "PmxValidationError",
        "PmxValidationIssue",
        "load_pmx",
        "read_pmx_document",
        "validate_pmx_document",
        "serialize_pmx",
        "write_pmx",
        "roundtrip_pmx",
    )
)

REQUIRED_EDITING_EXPORTS = frozenset(
    (
        "PMX_EDIT_PLAN_SCHEMA_VERSION",
        "PmxEditPlan",
        "PmxEditResult",
        "PmxEditPreview",
        "PmxEditWriteResult",
        "PmxEditDiagnostic",
        "SetModelInfo",
        "SetTexturePath",
        "UpdateMaterial",
        "apply_pmx_edit_plan",
        "dry_run_pmx_edit",
        "write_pmx_edit",
        "get_pmx_edit_operation_catalog",
        "parse_pmx_edit_plan_json",
        "load_pmx_edit_plan",
    )
)

LEGACY_IMPORT_PATHS = (
    "check_assets",
    "mmd_registry.cli",
    "mmd_registry.reporting",
    "mmd_registry.validator",
    "mmd_registry.pmx.reader",
    "mmd_registry.pmx.validation",
    "mmd_registry.pmx.writer",
    "mmd_registry.pmx.roundtrip",
    "mmd_registry.pmx.editing.json_loader",
    "mmd_registry.pmx.editing.output",
    "mmd_registry.pmx.editing.preview",
)


def _parameter_shape(function: object) -> tuple[tuple[str, inspect._ParameterKind, object], ...]:
    """Return only call-shape details that are part of the service contract."""

    signature = inspect.signature(function)
    shape: list[tuple[str, inspect._ParameterKind, object]] = []
    for parameter in signature.parameters.values():
        default = (
            "<required>"
            if parameter.default is inspect.Parameter.empty
            else parameter.default
        )
        shape.append((parameter.name, parameter.kind, default))
    return tuple(shape)


class Pre09ContractFreezeTests(unittest.TestCase):
    """Make pre-0.9 boundaries explicit before structural refactoring begins."""

    def test_canonical_public_namespace_boundaries_are_frozen(self) -> None:
        self.assertEqual(mmd_registry.__all__, ("__version__",))
        self.assertEqual(
            capabilities.__all__,
            (
                "PmxCapabilityManifest",
                "PmxRoundTripContract",
                "get_capabilities",
            ),
        )
        self.assertEqual(
            diagnostics.__all__,
            (
                "PmxServiceDiagnostic",
                "PmxServiceDiagnosticCode",
                "PmxServiceError",
                "PmxServiceOperation",
                "diagnostic_from_service_error",
            ),
        )
        self.assertEqual(services.__all__, EXPECTED_SERVICE_EXPORTS)
        self.assertTrue(REQUIRED_PMX_EXPORTS.issubset(pmx.__all__))
        self.assertTrue(REQUIRED_EDITING_EXPORTS.issubset(editing.__all__))

    def test_public_imports_are_quiet_cli_independent_and_cwd_independent(self) -> None:
        code = "\n".join(
            (
                "import sys",
                "import mmd_registry",
                "import mmd_registry.capabilities",
                "import mmd_registry.diagnostics",
                "import mmd_registry.pmx",
                "import mmd_registry.pmx.editing",
                "import mmd_registry.services",
                "assert 'mmd_registry.cli' not in sys.modules",
                "assert 'argparse' not in sys.modules",
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

    def test_legacy_compatibility_import_paths_remain_available(self) -> None:
        for module_name in LEGACY_IMPORT_PATHS:
            with self.subTest(module=module_name):
                self.assertIsNotNone(importlib.import_module(module_name))

        self.assertTrue(callable(capabilities.get_pmx_capability_manifest))

    def test_public_service_call_shapes_are_frozen(self) -> None:
        positional = inspect.Parameter.POSITIONAL_OR_KEYWORD
        keyword_only = inspect.Parameter.KEYWORD_ONLY

        expected = {
            "load_document": (("source", positional, "<required>"),),
            "inspect_document": (("document", positional, "<required>"),),
            "validate_document": (("document", positional, "<required>"),),
            "preview_edit": (
                ("source_bytes", positional, "<required>"),
                ("plan", positional, "<required>"),
            ),
            "apply_edit": (
                ("input_path", positional, "<required>"),
                ("output_path", positional, "<required>"),
                ("plan", positional, "<required>"),
                ("overwrite", keyword_only, False),
            ),
        }

        for name, expected_shape in expected.items():
            with self.subTest(service=name):
                self.assertEqual(
                    _parameter_shape(getattr(services, name)),
                    expected_shape,
                )

    def test_edit_plan_schema_and_operation_authority_are_frozen(self) -> None:
        self.assertEqual(PMX_EDIT_PLAN_SCHEMA_VERSION, 1)
        self.assertEqual(
            tuple(
                entry.operation_type
                for entry in editing.get_pmx_edit_operation_catalog().operations
            ),
            ("set_model_info", "set_texture_path", "update_material"),
        )

        with self.assertRaisesRegex(PmxEditPlanError, "unsupported operation"):
            parse_pmx_edit_plan_json(
                json.dumps(
                    {
                        "schema_version": 1,
                        "operations": [
                            {
                                "op": "delete_bone",
                                "bone_index": 0,
                            }
                        ],
                    }
                )
            )

    def test_packaging_and_console_entry_point_metadata_are_frozen(self) -> None:
        metadata = tomllib.loads(
            (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )

        self.assertEqual(metadata["project"]["name"], "mmd-asset-registry")
        self.assertEqual(metadata["project"]["dynamic"], ["version"])
        self.assertEqual(metadata["project"]["dependencies"], ["PyYAML>=6.0"])
        self.assertEqual(
            metadata["project"]["scripts"],
            {"mmd-asset-registry": "mmd_registry.cli:main"},
        )
        self.assertEqual(
            metadata["tool"]["setuptools"]["dynamic"]["version"],
            {"attr": "mmd_registry.__version__"},
        )
        self.assertEqual(COMMAND_NAME, "mmd-asset-registry")
        self.assertEqual(ENTRY_POINT_VALUE, "mmd_registry.cli:main")

    def test_clean_install_gate_still_executes_installed_console_contract(self) -> None:
        verifier = (
            PROJECT_ROOT / "tools" / "verify_clean_install.py"
        ).read_text(encoding="utf-8")

        for required_stage in (
            'stage="probe installed package outside repository"',
            'stage="run installed console version"',
            'stage="run installed console help"',
            'stage="run installed module version"',
        ):
            with self.subTest(stage=required_stage):
                self.assertIn(required_stage, verifier)

        self.assertIn(
            "Installed console launcher does not exist",
            verifier,
        )
        self.assertIn(
            "Installed console version was",
            verifier,
        )


if __name__ == "__main__":
    unittest.main()
