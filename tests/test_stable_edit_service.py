"""Stable public contracts for the pre-0.9.0 PMX edit service."""

from __future__ import annotations

import hashlib
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

import mmd_registry.services as services
from mmd_registry.diagnostics import (
    PmxServiceDiagnosticCode,
    PmxServiceError,
    PmxServiceOperation,
)
from mmd_registry.pmx import load_pmx
from mmd_registry.pmx.editing import (
    PmxEditPathError,
    PmxEditPlan,
    PmxEditPlanError,
    PmxEditPreview,
    PmxEditVerificationError,
    PmxEditWriteResult,
    SetModelInfo,
    SetTexturePath,
    UpdateMaterial,
    dry_run_pmx_edit,
    write_pmx_edit,
)
from tests.mmd_fixtures import (
    build_pmx_bone,
    build_pmx_material,
    build_pmx_structure,
)


PRIVATE_DETAIL = r"C:\private\秘密-edit.pmx"


def build_edit_source() -> bytes:
    """Build one complete PMX supporting all three existing edit operations."""

    material = build_pmx_material(
        local_name="Body",
        universal_name="Body EN",
        texture_index=0,
        sphere_texture_index=1,
        sphere_mode=1,
        toon_reference_mode=1,
        toon_reference_index=2,
        memo="Original memo",
        surface_index_count=3,
    )
    return build_pmx_structure(
        surface_indices=(0, 0, 0),
        texture_paths=("textures/body.png", "textures/sphere.spa"),
        materials=(material,),
        bones=(build_pmx_bone(),),
    )


def build_mixed_plan(
    *,
    expected_source_sha256: str | None = None,
) -> PmxEditPlan:
    """Build one plan using exactly the three already-supported operations."""

    return PmxEditPlan(
        operations=(
            SetModelInfo(local_name="Stable service"),
            SetTexturePath(texture_index=0, path="textures/stable.png"),
            UpdateMaterial(
                material_index=0,
                memo="Reviewed through service",
                diffuse=(0.5, 0.4, 0.3, 1.0),
            ),
        ),
        expected_source_sha256=expected_source_sha256,
    )


class StableEditServiceTests(unittest.TestCase):
    """Keep editing bounded, verified, quiet, and failure-safe."""

    def test_preview_is_typed_repeatable_quiet_and_side_effect_free(self) -> None:
        source_bytes = build_edit_source()
        plan = build_mixed_plan(
            expected_source_sha256=hashlib.sha256(source_bytes).hexdigest()
        )
        output = io.StringIO()
        error_output = io.StringIO()

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            sentinel = root / "sentinel.pmx"
            sentinel.write_bytes(source_bytes)
            with redirect_stdout(output), redirect_stderr(error_output):
                first = services.preview_edit(source_bytes, plan)
                second = services.preview_edit(source_bytes, plan)

            self.assertEqual(tuple(root.iterdir()), (sentinel,))
            self.assertEqual(sentinel.read_bytes(), source_bytes)

        self.assertIsInstance(first, PmxEditPreview)
        self.assertEqual(first, second)
        self.assertEqual(first.operation_count, 3)
        self.assertEqual(first.audit.changed_fields, 4)
        self.assertEqual(first.status, "changes_pending")
        self.assertEqual(first.to_dict()["verification"]["semantic"], "passed")
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(error_output.getvalue(), "")
        with self.assertRaises(FrozenInstanceError):
            first.operation_count = 4  # type: ignore[misc]

    def test_apply_reuses_verified_distinct_output_pipeline(self) -> None:
        source_bytes = build_edit_source()
        plan = build_mixed_plan()
        expected_preview = services.preview_edit(source_bytes, plan)

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source.pmx"
            destination = root / "destination.pmx"
            source.write_bytes(source_bytes)

            result = services.apply_edit(source, destination, plan)

            self.assertIsInstance(result, PmxEditWriteResult)
            self.assertEqual(result.preview, expected_preview)
            self.assertEqual(result.status, "written")
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(
                hashlib.sha256(destination.read_bytes()).hexdigest(),
                result.output_sha256,
            )
            self.assertEqual(
                set(root.iterdir()),
                {source, destination},
            )
            document = load_pmx(destination)

        self.assertEqual(document.model_info.local_name, "Stable service")
        self.assertEqual(document.texture_paths[0], "textures/stable.png")
        self.assertEqual(document.materials[0].memo, "Reviewed through service")
        for actual, expected in zip(
            document.materials[0].diffuse,
            (0.5, 0.4, 0.3, 1.0),
            strict=True,
        ):
            self.assertAlmostEqual(actual, expected, places=6)

    def test_preview_plan_failure_is_structured_and_operation_specific(self) -> None:
        source_bytes = build_edit_source()
        plan = build_mixed_plan(expected_source_sha256="0" * 64)

        with self.assertRaises(PmxServiceError) as raised:
            services.preview_edit(source_bytes, plan)

        error = raised.exception
        self.assertEqual(
            error.diagnostic.code,
            PmxServiceDiagnosticCode.EDIT_PLAN_INVALID,
        )
        self.assertEqual(
            error.diagnostic.operation,
            PmxServiceOperation.PREVIEW_EDIT,
        )
        self.assertEqual(
            dict(error.diagnostic.details),
            {
                "operation_index": None,
                "operation_type": None,
                "field": "expected_source_sha256",
            },
        )
        self._assert_no_wrapped_failure_context(error)

    def test_preview_malformed_source_uses_safe_source_diagnostic(self) -> None:
        plan = PmxEditPlan(
            operations=(SetModelInfo(local_name="Never applied"),)
        )

        with self.assertRaises(PmxServiceError) as raised:
            services.preview_edit(b"bad", plan)

        error = raised.exception
        self.assertEqual(
            error.diagnostic.code,
            PmxServiceDiagnosticCode.SOURCE_INVALID,
        )
        self.assertEqual(
            error.diagnostic.operation,
            PmxServiceOperation.PREVIEW_EDIT,
        )
        self.assertNotIn("BinaryParseError", repr(error.to_dict()))
        self._assert_no_wrapped_failure_context(error)

    def test_apply_rejects_same_path_without_changing_source(self) -> None:
        source_bytes = build_edit_source()
        plan = build_mixed_plan()

        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "source.pmx"
            source.write_bytes(source_bytes)
            with self.assertRaises(PmxServiceError) as raised:
                services.apply_edit(source, source, plan)

            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(tuple(source.parent.iterdir()), (source,))

        error = raised.exception
        self.assertEqual(
            error.to_dict(),
            {
                "code": "edit_path_unsafe",
                "operation": "apply_edit",
                "message": "Edit path failed safety validation.",
            },
        )
        self._assert_no_wrapped_failure_context(error)

    def test_verification_and_unexpected_failures_are_redacted(self) -> None:
        source_bytes = build_edit_source()
        plan = build_mixed_plan()
        failures = (
            (
                PmxEditVerificationError(PRIVATE_DETAIL),
                PmxServiceDiagnosticCode.EDIT_VERIFICATION_FAILED,
                "PMX edit verification failed.",
            ),
            (
                RuntimeError(PRIVATE_DETAIL),
                PmxServiceDiagnosticCode.INTERNAL_ERROR,
                "Unexpected internal service failure.",
            ),
        )

        for failure, code, message in failures:
            with self.subTest(code=code.value):
                with patch(
                    "mmd_registry.services.dry_run_pmx_edit",
                    side_effect=failure,
                ):
                    with self.assertRaises(PmxServiceError) as raised:
                        services.preview_edit(source_bytes, plan)

                error = raised.exception
                self.assertEqual(error.diagnostic.code, code)
                self.assertEqual(error.diagnostic.message, message)
                self.assertNotIn(PRIVATE_DETAIL, repr(error.to_dict()))
                self.assertNotIn(type(failure).__name__, repr(error.to_dict()))
                self._assert_no_wrapped_failure_context(error)

    def test_process_control_exceptions_are_not_converted(self) -> None:
        source_bytes = build_edit_source()
        plan = build_mixed_plan()

        with patch(
            "mmd_registry.services.dry_run_pmx_edit",
            side_effect=KeyboardInterrupt(),
        ):
            with self.assertRaises(KeyboardInterrupt):
                services.preview_edit(source_bytes, plan)

        with patch(
            "mmd_registry.services.write_pmx_edit",
            side_effect=SystemExit(9),
        ):
            with self.assertRaises(SystemExit) as raised:
                services.apply_edit("source.pmx", "output.pmx", plan)
        self.assertEqual(raised.exception.code, 9)

    def test_legacy_core_edit_apis_keep_domain_exceptions(self) -> None:
        source_bytes = build_edit_source()
        mismatched_plan = build_mixed_plan(expected_source_sha256="0" * 64)

        with self.assertRaises(PmxEditPlanError):
            dry_run_pmx_edit(source_bytes, mismatched_plan)

        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "source.pmx"
            source.write_bytes(source_bytes)
            with self.assertRaises(PmxEditPathError):
                write_pmx_edit(source, source, build_mixed_plan())

    def _assert_no_wrapped_failure_context(self, error: PmxServiceError) -> None:
        self.assertIsNone(error.__cause__)
        self.assertIsNone(error.__context__)
        self.assertTrue(error.__suppress_context__)


if __name__ == "__main__":
    unittest.main()
