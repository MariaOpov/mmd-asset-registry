"""Integration contracts for the reusable pre-0.9.0 service boundary."""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import mmd_registry.services as services
from mmd_registry.pmx import load_pmx
from mmd_registry.pmx.editing import PmxEditPlan, SetModelInfo
from mmd_registry.pmx.editing.errors import PmxEditPathError
from tests.mmd_fixtures import build_pmx_bone, build_pmx_structure


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def build_service_source_bytes() -> bytes:
    """Build one complete semantically valid PMX service fixture."""

    return build_pmx_structure(bones=(build_pmx_bone(),))


class ServiceBoundaryFoundationTests(unittest.TestCase):
    """Exercise service use cases without CLI or presentation coupling."""

    def test_service_namespace_has_one_explicit_surface(self) -> None:
        self.assertEqual(
            services.__all__,
            (
                "PmxDocumentMetadata",
                "PmxDocumentValidationResult",
                "apply_edit",
                "get_capabilities",
                "inspect_document",
                "load_document",
                "preview_edit",
                "validate_document",
            ),
        )
        for name in services.__all__:
            with self.subTest(name=name):
                self.assertTrue(hasattr(services, name))

    def test_document_service_loads_and_inspects_path_or_stream(self) -> None:
        source_bytes = build_service_source_bytes()
        stream_document = services.load_document(io.BytesIO(source_bytes))
        stream_metadata = services.inspect_document(stream_document)

        self.assertEqual(stream_metadata.version, 2.0)
        self.assertEqual(stream_metadata.encoding, "utf-8")
        self.assertEqual(stream_metadata.local_name, "Test PMX Model")
        self.assertEqual(stream_metadata.universal_name, "Test PMX Model")

        with tempfile.TemporaryDirectory() as temporary_directory:
            source_path = Path(temporary_directory) / "fixture.pmx"
            source_path.write_bytes(source_bytes)
            path_document = services.load_document(source_path)

        self.assertEqual(path_document, stream_document)
        with self.assertRaises(FrozenInstanceError):
            stream_metadata.local_name = "Changed"  # type: ignore[misc]

    def test_validation_service_returns_repeatable_structured_issues(self) -> None:
        document = services.load_document(io.BytesIO(build_service_source_bytes()))
        valid_result = services.validate_document(document)

        self.assertTrue(valid_result.is_valid)
        self.assertEqual(valid_result.issues, ())

        invalid_document = replace(
            document,
            model_info=replace(document.model_info, local_name="\ud800"),
        )
        first = services.validate_document(invalid_document)
        second = services.validate_document(invalid_document)

        self.assertFalse(first.is_valid)
        self.assertEqual(first, second)
        self.assertEqual(len(first.issues), 1)
        self.assertEqual(first.issues[0].section, "model_info")
        self.assertEqual(first.issues[0].field, "local_name")
        with self.assertRaises(FrozenInstanceError):
            first.issues = ()  # type: ignore[misc]

    def test_edit_preview_is_verified_and_has_no_filesystem_side_effect(self) -> None:
        source_bytes = build_service_source_bytes()
        plan = PmxEditPlan(
            operations=(SetModelInfo(local_name="Service Preview"),)
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            sentinel = Path(temporary_directory) / "sentinel.pmx"
            sentinel.write_bytes(source_bytes)
            preview = services.preview_edit(source_bytes, plan)

            self.assertEqual(sentinel.read_bytes(), source_bytes)
            self.assertEqual(tuple(Path(temporary_directory).iterdir()), (sentinel,))

        self.assertEqual(preview.document.model_info.local_name, "Service Preview")
        self.assertEqual(preview.audit.changed_fields, 1)
        self.assertEqual(preview.status, "changes_pending")

    def test_edit_apply_reuses_distinct_verified_output_pipeline(self) -> None:
        source_bytes = build_service_source_bytes()
        plan = PmxEditPlan(
            operations=(SetModelInfo(local_name="Service Apply"),)
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)

            result = services.apply_edit(source, output, plan)

            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertTrue(output.is_file())
            self.assertEqual(result.input_path, source.resolve())
            self.assertEqual(result.output_path, output.resolve())
            self.assertEqual(result.preview.audit.changed_fields, 1)
            self.assertEqual(
                load_pmx(output).model_info.local_name,
                "Service Apply",
            )

            with self.assertRaises(PmxEditPathError):
                services.apply_edit(source, source, plan)
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_capability_service_reuses_immutable_authoritative_manifest(self) -> None:
        first = services.get_capabilities()
        second = services.get_capabilities()

        self.assertEqual(first, second)
        self.assertEqual(
            first.edit_operation_types,
            ("set_model_info", "set_texture_path", "update_material"),
        )
        self.assertFalse(first.private_runtime_required)
        with self.assertRaises(FrozenInstanceError):
            first.private_runtime_required = True  # type: ignore[misc]

    def test_service_import_is_cli_independent_outside_repository_cwd(self) -> None:
        code = "\n".join(
            (
                "import sys",
                "import mmd_registry.services as services",
                "assert services.__all__",
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
