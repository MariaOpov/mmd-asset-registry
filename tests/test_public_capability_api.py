"""Public contracts for the pre-0.9.0 immutable capability API."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import get_args
from unittest.mock import patch

import mmd_registry.capabilities as capabilities
import mmd_registry.services as services


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class PublicCapabilityApiTests(unittest.TestCase):
    """Expose current support without promising unavailable future features."""

    def test_namespace_has_one_explicit_canonical_surface(self) -> None:
        self.assertEqual(
            capabilities.__all__,
            (
                "PmxCapabilityManifest",
                "PmxRoundTripContract",
                "get_capabilities",
            ),
        )

        namespace: dict[str, object] = {}
        exec("from mmd_registry.capabilities import *", namespace)
        exported_names = {name for name in namespace if name != "__builtins__"}
        self.assertEqual(exported_names, set(capabilities.__all__))
        self.assertNotIn("get_pmx_capability_manifest", exported_names)

    def test_service_and_legacy_entry_points_reuse_public_manifest(self) -> None:
        public_manifest = capabilities.get_capabilities()

        self.assertIs(services.get_capabilities, capabilities.get_capabilities)
        self.assertEqual(
            capabilities.get_pmx_capability_manifest(),
            public_manifest,
        )

    def test_manifest_reports_only_authoritative_current_support(self) -> None:
        manifest = capabilities.get_capabilities()

        self.assertEqual(
            get_args(capabilities.PmxRoundTripContract),
            ("validated_semantic_roundtrip",),
        )
        self.assertEqual(
            manifest.to_dict(),
            {
                "pmx_versions": [2.0, 2.1],
                "text_encodings": ["utf-16-le", "utf-8"],
                "index_sizes": [1, 2, 4],
                "deform_types": [0, 1, 2, 3, 4],
                "morph_types": list(range(11)),
                "soft_body_support": True,
                "roundtrip_contract": "validated_semantic_roundtrip",
                "edit_operation_types": [
                    "set_model_info",
                    "set_texture_path",
                    "update_material",
                ],
                "texture_portability": True,
                "private_runtime_required": False,
            },
        )

    def test_manifest_does_not_advertise_future_authority(self) -> None:
        serialized = json.dumps(
            capabilities.get_capabilities().to_dict(),
            sort_keys=True,
        )

        for unsupported in (
            "create_model",
            "plugin_loading",
            "unrestricted_physics_editing",
            "vmd_editing",
        ):
            with self.subTest(unsupported=unsupported):
                self.assertNotIn(unsupported, serialized)

    def test_manifest_and_nested_support_collections_are_immutable(self) -> None:
        manifest = capabilities.get_capabilities()

        for value in (
            manifest.pmx_versions,
            manifest.text_encodings,
            manifest.index_sizes,
            manifest.deform_types,
            manifest.morph_types,
            manifest.edit_operation_types,
        ):
            with self.subTest(value=value):
                self.assertIsInstance(value, tuple)
        with self.assertRaises(FrozenInstanceError):
            manifest.texture_portability = False  # type: ignore[misc]

    def test_json_ready_copy_cannot_mutate_the_manifest(self) -> None:
        manifest = capabilities.get_capabilities()
        payload = manifest.to_dict()
        operation_types = payload["edit_operation_types"]

        self.assertIsInstance(operation_types, list)
        operation_types.append("unsupported")  # type: ignore[union-attr]

        self.assertEqual(
            manifest.edit_operation_types,
            ("set_model_info", "set_texture_path", "update_material"),
        )
        self.assertNotIn("unsupported", manifest.to_dict()["edit_operation_types"])

    def test_manifest_is_repeatable_and_private_runtime_independent(self) -> None:
        baseline = capabilities.get_capabilities()

        with patch.dict(
            os.environ,
            {"MMD_REGISTRY_PRIVATE_PMX": r"C:\private\fixture.pmx"},
            clear=False,
        ):
            enabled_environment = capabilities.get_capabilities()

        self.assertEqual(enabled_environment, baseline)
        self.assertFalse(enabled_environment.private_runtime_required)

    def test_public_import_is_quiet_cli_independent_and_cwd_independent(self) -> None:
        code = "\n".join(
            (
                "import sys",
                "import mmd_registry.capabilities as capabilities",
                "assert capabilities.__all__",
                "assert capabilities.get_capabilities().edit_operation_types",
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


if __name__ == "__main__":
    unittest.main()
