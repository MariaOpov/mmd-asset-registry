"""v0.9.5.6 compatibility and authority immutability certification."""

from __future__ import annotations

import argparse
import inspect
import subprocess
import unittest
from pathlib import Path
from typing import get_args

import mmd_registry
import mmd_registry.cli as cli
import mmd_registry.services as services
from mmd_registry.pmx.transaction_plan import (
    PmxStructuralTransactionOperationType,
    get_pmx_structural_transaction_operation_catalog,
)
from mmd_registry.services.structural_transaction import (
    PmxStructuralTransactionOperation,
)


ROOT = Path(__file__).resolve().parents[1]

_PROTECTED_GIT_BLOBS = {
    "mmd_registry/smart_parts.py": "004fcc5d5b701447842615fb158743c87e57fa99",
    "mmd_registry/smart_part_detection.py": "d0c9d6a6882340e22803c1c978860197ed7bb30e",
    "mmd_registry/smart_part_explainability.py": "7b62e97f2b7393f6a160e57ba8fd937aad4f8c12",
    "mmd_registry/_smart_part_confidence.py": "1016c83b249fa753ff846b501b32958ecc2a0cdb",
    "mmd_registry/smart_part_confidence.py": "3d8f6f3b8076b94473b8376762fa59d099ad0a52",
    "mmd_registry/services/_smart_inspection.py": "2f8453403940c4aa376b77d953c5d83ad3d8c77a",
    "mmd_registry/smart_cli.py": "5b6001d7e9c6dbf521faf50989c538e41a29de4f",
    "mmd_registry/services/structural_authoring_catalog.py": "43500b61cbce1f93096248c54d9901f3f3494026",
    "mmd_registry/pmx/editing/operations.py": "146a12724ca5b17c6bca329cf3b50f67500bf215",
    "mmd_registry/pmx/editing/plan.py": "4063ab6897b82cf679afae8cfaf838ca3d7d1710",
    "mmd_registry/pmx/editing/engine.py": "feab452e49de38e89175425845ba21aecd019730",
    "mmd_registry/pmx/editing/preview.py": "d8770e9f16060508179de807a49a3dac06689a62",
    "mmd_registry/pmx/editing/output.py": "69f7de6ae92e15b7115045a3b0f75f15162b6452",
    "mmd_registry/pmx/transaction_plan.py": "66406278260ef345d48059f7583105a6586b7371",
    "mmd_registry/services/structural_transaction.py": "70bd0a5a7f8c73718c0e1f4ea5390766aec01145",
    "mmd_registry/pmx/writer.py": "a3a6fa4252c24678b76d650810b47d6c5757f2b4",
    "mmd_registry/pmx/index_remap.py": "86c3e2b4982f908bfa54db29a94fdbf298448a5f",
    "mmd_registry/cli.py": "f50d7d811432ef1599d2bd29c0e15787c45a1c5d",
}

_EXPECTED_STRUCTURAL_OPS = (
    "transform_collection",
    "insert_texture",
    "insert_material",
    "insert_bone",
    "insert_morph",
    "insert_rigid_body",
    "insert_vertex",
)


def _subparser_choices(parser: argparse.ArgumentParser) -> dict[str, object]:
    actions = [
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    ]
    if len(actions) != 1:
        raise AssertionError("parser must have exactly one subparser action")
    return dict(actions[0].choices)


class SmartMaterialAuthorityBoundaryTests(unittest.TestCase):
    def test_protected_authorities_are_byte_identical_to_cp02_baseline(self) -> None:
        for relative_path, expected_blob in _PROTECTED_GIT_BLOBS.items():
            with self.subTest(path=relative_path):
                completed = subprocess.run(
                    ["git", "hash-object", relative_path],
                    cwd=ROOT,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                self.assertEqual(
                    completed.returncode,
                    0,
                    msg=completed.stderr,
                )
                self.assertEqual(completed.stdout.strip(), expected_blob)

    def test_package_root_and_service_public_surfaces_remain_frozen(self) -> None:
        self.assertEqual(mmd_registry.__all__, ("__version__",))
        service_all = tuple(getattr(services, "__all__", ()))
        for forbidden in (
            "group_smart_materials",
            "discover_smart_material_capability",
            "build_smart_material_color_draft",
            "SmartMaterialCapability",
            "SmartMaterialGroup",
            "SmartMaterialDraftError",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, service_all)

    def test_existing_smart_cli_remains_inspect_only(self) -> None:
        parser = cli._build_application_argument_parser()
        top = _subparser_choices(parser)
        self.assertIn("smart", top)
        smart = _subparser_choices(top["smart"])
        self.assertEqual(tuple(smart), ("inspect",))

    def test_structural_schema_one_vocabulary_is_unchanged(self) -> None:
        enum_ops = tuple(item.value for item in PmxStructuralTransactionOperationType)
        catalog_ops = tuple(
            item.operation_type.value
            for item in get_pmx_structural_transaction_operation_catalog().operations
        )
        self.assertEqual(enum_ops, _EXPECTED_STRUCTURAL_OPS)
        self.assertEqual(catalog_ops, _EXPECTED_STRUCTURAL_OPS)
        self.assertNotIn("update_material", enum_ops)

        union_names = tuple(
            item.__name__ for item in get_args(PmxStructuralTransactionOperation)
        )
        self.assertNotIn("UpdateMaterial", union_names)

    def test_existing_preview_and_apply_service_signatures_are_unchanged(self) -> None:
        self.assertEqual(
            str(inspect.signature(services.preview_edit)),
            "(source_bytes: 'bytes', plan: 'PmxEditPlan') -> 'PmxEditPreview'",
        )
        self.assertEqual(
            str(inspect.signature(services.apply_edit)),
            (
                "(input_path: 'str | Path', output_path: 'str | Path', "
                "plan: 'PmxEditPlan', *, overwrite: 'bool' = False) "
                "-> 'PmxEditWriteResult'"
            ),
        )


if __name__ == "__main__":
    unittest.main()
