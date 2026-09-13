"""CP27 distribution and capability contract for structural transactions."""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path
import tomllib
import unittest

import mmd_registry
import mmd_registry.capabilities as capabilities
import mmd_registry.pmx as pmx
import mmd_registry.services as services
from mmd_registry.constants import LATEST_SCHEMA_VERSION, SUPPORTED_SCHEMA_VERSIONS
from mmd_registry.pmx.editing.plan import PMX_EDIT_PLAN_SCHEMA_VERSION
from mmd_registry.services import structural_transaction as transactions
from tools.verify_clean_install import PROBE_SOURCE


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RELEASED_CAPABILITY_FIELDS = (
    "pmx_versions",
    "text_encodings",
    "index_sizes",
    "deform_types",
    "morph_types",
    "soft_body_support",
    "roundtrip_contract",
    "edit_operation_types",
    "texture_portability",
    "private_runtime_required",
    "structural_preview",
    "structural_write",
    "structural_target_kinds",
    "structural_contract",
    "structural_insert",
)
TRANSACTION_EXPORTS = (
    "PmxStructuralTransactionOperation",
    "PmxStructuralTransactionRequest",
    "PmxStructuralTransactionPreviewResult",
    "preview_structural_transaction",
    "apply_structural_transaction",
)


def _legacy_manifest() -> capabilities.PmxCapabilityManifest:
    return capabilities.PmxCapabilityManifest(
        pmx_versions=(2.0, 2.1),
        text_encodings=("utf-16-le", "utf-8"),
        index_sizes=(1, 2, 4),
        deform_types=(0, 1, 2, 3, 4),
        morph_types=tuple(range(11)),
        soft_body_support=True,
        roundtrip_contract="validated_semantic_roundtrip",
        edit_operation_types=(
            "set_model_info",
            "set_texture_path",
            "update_material",
        ),
        texture_portability=True,
        private_runtime_required=False,
    )


class V093StructuralTransactionDistributionCapabilityTests(unittest.TestCase):
    """Freeze the installed-wheel claim without expanding mutation authority."""

    def test_capability_promotion_is_one_trailing_default_false_field(self) -> None:
        field_names = tuple(
            field.name for field in fields(capabilities.PmxCapabilityManifest)
        )

        self.assertEqual(
            field_names,
            (*RELEASED_CAPABILITY_FIELDS, "structural_transaction"),
        )
        self.assertFalse(_legacy_manifest().structural_transaction)
        self.assertTrue(capabilities.get_capabilities().structural_transaction)

    def test_canonical_payload_appends_transaction_capability(self) -> None:
        payload = capabilities.get_capabilities().to_dict()

        self.assertEqual(
            tuple(payload)[:-1],
            RELEASED_CAPABILITY_FIELDS,
        )
        self.assertEqual(tuple(payload)[-1], "structural_transaction")
        self.assertIs(payload["structural_transaction"], True)
        self.assertEqual(
            capabilities.get_pmx_capability_manifest().to_dict(),
            payload,
        )

    def test_transaction_api_remains_in_its_explicit_submodule(self) -> None:
        self.assertEqual(transactions.__all__, TRANSACTION_EXPORTS)
        for name in TRANSACTION_EXPORTS:
            with self.subTest(name=name):
                self.assertTrue(hasattr(transactions, name))
                self.assertNotIn(name, mmd_registry.__all__)
                self.assertNotIn(name, pmx.__all__)
                self.assertNotIn(name, services.__all__)
                self.assertFalse(hasattr(services, name))
        self.assertNotIn("structural_transaction", services.__all__)

    def test_final_version_promotion_keeps_schemas_frozen(self) -> None:
        self.assertEqual(mmd_registry.__version__, "0.9.5.7")
        self.assertEqual(LATEST_SCHEMA_VERSION, "0.3")
        self.assertEqual(SUPPORTED_SCHEMA_VERSIONS, frozenset(("0.2", "0.3")))
        self.assertEqual(PMX_EDIT_PLAN_SCHEMA_VERSION, 1)

    def test_clean_install_probe_executes_installed_transaction(self) -> None:
        compile(PROBE_SOURCE, "probe_installed_package.py", "exec")
        for marker in (
            "capability_manifest.structural_transaction is True",
            "installed_transactions.PmxStructuralTransactionRequest",
            "installed_transactions.preview_structural_transaction",
            "installed_transactions.apply_structural_transaction",
            "installed structural transaction changed source",
            "installed structural transaction reparse mismatch",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, PROBE_SOURCE)

    def test_distribution_configuration_excludes_private_runtime_data(self) -> None:
        pyproject = tomllib.loads(
            (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )
        manifest = (PROJECT_ROOT / "MANIFEST.in").read_text(encoding="utf-8")

        self.assertEqual(pyproject["project"]["dynamic"], ["version"])
        self.assertEqual(
            pyproject["tool"]["setuptools"]["dynamic"]["version"]["attr"],
            "mmd_registry.__version__",
        )
        self.assertEqual(
            pyproject["tool"]["setuptools"]["packages"]["find"]["include"],
            ["mmd_registry*"],
        )
        self.assertEqual(
            pyproject["tool"]["setuptools"]["packages"]["find"]["exclude"],
            ["tests*"],
        )
        self.assertNotIn("*.pmx", manifest.casefold())
        self.assertNotIn("private", manifest.casefold())

    def test_ci_runs_capability_and_clean_distribution_gates(self) -> None:
        workflow = (PROJECT_ROOT / ".github/workflows/validate.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "tests.test_v093_structural_transaction_distribution_capability",
            workflow,
        )
        self.assertIn("python -m build --sdist --wheel", workflow)
        self.assertIn("python tools/inspect_distribution_artifacts.py dist", workflow)
        self.assertIn("python tools/verify_clean_install.py dist", workflow)
        self.assertNotIn("pypi", workflow.casefold())
        self.assertNotIn("upload-artifact", workflow.casefold())


if __name__ == "__main__":
    unittest.main()
