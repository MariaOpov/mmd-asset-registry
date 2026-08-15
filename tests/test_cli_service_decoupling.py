"""Architecture contracts for CLI delegation through the service boundary."""

from __future__ import annotations

import ast
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import mmd_registry.cli as cli
import mmd_registry.services as services
from mmd_registry.pmx.editing import PmxEditPlan
from tests.mmd_fixtures import build_pmx_bone, build_pmx_structure


class CliServiceDecouplingTests(unittest.TestCase):
    """Keep CLI presentation separate from reusable edit execution."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.source_bytes = build_pmx_structure(
            bones=(build_pmx_bone(),),
        )
        self.source_path = self.root / "source.pmx"
        self.source_path.write_bytes(self.source_bytes)
        self.plan_path = self.root / "plan.json"
        self.plan_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "operations": [
                        {
                            "op": "set_model_info",
                            "local_name": "Service-routed CLI",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def capture_run(self, arguments: list[str]) -> tuple[int, str, str]:
        """Run the CLI while capturing both presentation streams."""

        output = io.StringIO()
        error_output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(error_output):
            exit_code = cli.run(arguments)
        return exit_code, output.getvalue(), error_output.getvalue()

    def test_edit_execution_bindings_are_public_service_exports(self) -> None:
        self.assertIs(cli.dry_run_pmx_edit, services.preview_edit)
        self.assertIs(cli.write_pmx_edit, services.apply_edit)

    def test_cli_imports_edit_execution_only_from_service_boundary(self) -> None:
        source = Path(cli.__file__).read_text(encoding="utf-8")
        imports = {
            (node.module, alias.name, alias.asname)
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }

        self.assertIn(
            ("mmd_registry.services", "preview_edit", "dry_run_pmx_edit"),
            imports,
        )
        self.assertIn(
            ("mmd_registry.services", "apply_edit", "write_pmx_edit"),
            imports,
        )
        self.assertNotIn(
            ("mmd_registry.pmx.editing", "dry_run_pmx_edit", None),
            imports,
        )
        self.assertNotIn(
            ("mmd_registry.pmx.editing", "write_pmx_edit", None),
            imports,
        )

    def test_dry_run_delegates_typed_plan_to_preview_service(self) -> None:
        with patch(
            "mmd_registry.cli.dry_run_pmx_edit",
            wraps=services.preview_edit,
        ) as preview_edit:
            exit_code, output, error_output = self.capture_run(
                [
                    "edit",
                    str(self.source_path),
                    "--plan",
                    str(self.plan_path),
                    "--dry-run",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(error_output, "")
        self.assertIn("PMX EDIT PREVIEW", output)
        preview_edit.assert_called_once()
        source_bytes, plan = preview_edit.call_args.args
        self.assertEqual(source_bytes, self.source_bytes)
        self.assertIsInstance(plan, PmxEditPlan)

    def test_apply_delegates_paths_plan_and_overwrite_to_service(self) -> None:
        output_path = self.root / "output.pmx"
        with patch(
            "mmd_registry.cli.write_pmx_edit",
            wraps=services.apply_edit,
        ) as apply_edit:
            exit_code, output, error_output = self.capture_run(
                [
                    "edit",
                    str(self.source_path),
                    str(output_path),
                    "--plan",
                    str(self.plan_path),
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(error_output, "")
        self.assertIn("PMX EDIT RESULT", output)
        self.assertTrue(output_path.is_file())
        apply_edit.assert_called_once()
        input_argument, output_argument, plan = apply_edit.call_args.args
        self.assertEqual(input_argument, self.source_path)
        self.assertEqual(output_argument, output_path)
        self.assertIsInstance(plan, PmxEditPlan)
        self.assertEqual(apply_edit.call_args.kwargs, {"overwrite": False})


if __name__ == "__main__":
    unittest.main()
