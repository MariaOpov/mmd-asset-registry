"""Optional runtime-only compatibility checks for one private PMX model."""

from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from mmd_registry.cli import run
from mmd_registry.pmx import load_pmx


_PRIVATE_PMX_ENV = "MMD_REGISTRY_PRIVATE_PMX"
_DRY_RUN_MARKER = "[mmd-asset-registry v0.8.4 private compatibility dry-run]"


def _sha256_file(path: Path) -> str:
    """Return a streaming SHA-256 digest without copying the private asset."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class PmxCompatibilityPrivateRuntimeTests(unittest.TestCase):
    """Run only when a local private PMX path is supplied at runtime."""

    @classmethod
    def setUpClass(cls) -> None:
        raw_path = os.environ.get(_PRIVATE_PMX_ENV)
        if not raw_path:
            raise unittest.SkipTest(
                f"set {_PRIVATE_PMX_ENV} to enable private-model validation"
            )

        candidate = Path(raw_path).expanduser()
        if not candidate.exists():
            raise AssertionError("private PMX runtime path does not exist")
        if not candidate.is_file():
            raise AssertionError("private PMX runtime path is not a file")
        if candidate.suffix.lower() != ".pmx":
            raise AssertionError("private PMX runtime path must use the .pmx extension")

        cls.source_path = candidate.resolve(strict=True)

    def setUp(self) -> None:
        self.source_size_before = self.source_path.stat().st_size
        self.source_sha256_before = _sha256_file(self.source_path)

    @staticmethod
    def _capture_run(arguments: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = run(arguments)
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def _assert_source_unchanged(self) -> None:
        self.assertEqual(
            self.source_path.stat().st_size,
            self.source_size_before,
            "private source size changed during compatibility validation",
        )
        self.assertEqual(
            _sha256_file(self.source_path),
            self.source_sha256_before,
            "private source SHA-256 changed during compatibility validation",
        )

    def test_read_only_workflows_accept_private_model_without_internal_failure(self) -> None:
        """Exercise typed loading plus scan/doctor/bones/rig/texture portability."""

        source_document = load_pmx(self.source_path)

        scan_code, scan_output, scan_error = self._capture_run(
            ["scan", str(self.source_path), "--json"]
        )
        scan = json.loads(scan_output)
        self.assertEqual(scan_code, 0)
        self.assertEqual(scan_error, "")
        self.assertTrue(scan["scan_complete"])
        self.assertEqual(scan["version"], source_document.header.version)
        self.assertEqual(
            scan["section_summary"]["bone_count"],
            len(source_document.bones),
        )
        self.assertEqual(
            scan["section_summary"]["material_count"],
            len(source_document.materials),
        )

        doctor_code, doctor_output, doctor_error = self._capture_run(
            ["doctor", str(self.source_path), "--json"]
        )
        doctor = json.loads(doctor_output)
        self.assertIn(doctor_code, (0, 1))
        self.assertEqual(doctor_error, "")
        self.assertFalse(doctor.get("internal_error", False))
        self.assertIsNotNone(doctor["scan"])
        self.assertTrue(doctor["scan"]["scan_complete"])

        bones_code, bones_output, bones_error = self._capture_run(
            ["bones", str(self.source_path), "--json"]
        )
        bones = json.loads(bones_output)
        self.assertEqual(bones_code, 0)
        self.assertEqual(bones_error, "")
        self.assertEqual(bones["status"], "ok")
        self.assertEqual(bones["bone_count"], len(source_document.bones))

        rig_code, rig_output, rig_error = self._capture_run(
            ["rig", str(self.source_path), "--json"]
        )
        rig = json.loads(rig_output)
        self.assertIn(rig_code, (0, 1))
        self.assertEqual(rig_error, "")
        self.assertFalse(rig.get("internal_error", False))

        portability_code, portability_output, portability_error = self._capture_run(
            ["texture-portability", str(self.source_path), "--json"]
        )
        portability = json.loads(portability_output)
        self.assertIn(portability_code, (0, 1))
        self.assertEqual(portability_error, "")
        self.assertFalse(portability.get("internal_error", False))

        self._assert_source_unchanged()

    def test_roundtrip_private_model_uses_distinct_temporary_output_and_cleans_it(self) -> None:
        """Roundtrip the private model without persisting any generated PMX output."""

        source_document = load_pmx(self.source_path)
        temporary_root_path: Path | None = None

        with tempfile.TemporaryDirectory(
            prefix="mmd-v084-private-roundtrip-"
        ) as temporary_root:
            temporary_root_path = Path(temporary_root)
            output_path = temporary_root_path / "roundtrip-output.pmx"

            exit_code, output, error_output = self._capture_run(
                [
                    "roundtrip",
                    str(self.source_path),
                    str(output_path),
                    "--json",
                ]
            )
            payload = json.loads(output)

            self.assertEqual(exit_code, 0)
            self.assertEqual(error_output, "")
            self.assertEqual(payload["status"], "ok")
            self.assertTrue(payload["semantic_equal"])
            self.assertTrue(output_path.is_file())
            self.assertNotEqual(
                self.source_path.resolve(),
                output_path.resolve(),
            )
            self.assertEqual(load_pmx(output_path), source_document)
            self._assert_source_unchanged()

        assert temporary_root_path is not None
        self.assertFalse(
            temporary_root_path.exists(),
            "temporary roundtrip output was not cleaned up",
        )
        self._assert_source_unchanged()

    def test_strict_edit_plan_explain_and_dry_run_leave_private_model_unchanged(self) -> None:
        """Exercise strict plan authoring and edit preview without writing PMX output."""

        source_document = load_pmx(self.source_path)
        expected_comments = (
            f"{source_document.model_info.local_comments}\n{_DRY_RUN_MARKER}"
        )
        temporary_root_path: Path | None = None

        with tempfile.TemporaryDirectory(
            prefix="mmd-v084-private-edit-plan-"
        ) as temporary_root:
            temporary_root_path = Path(temporary_root)
            plan_path = temporary_root_path / "validation-plan.json"
            plan_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "expected_source_sha256": self.source_sha256_before,
                        "operations": [
                            {
                                "op": "set_model_info",
                                "local_comments": expected_comments,
                            }
                        ],
                    },
                    ensure_ascii=False,
                    allow_nan=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            plan_snapshot = plan_path.read_bytes()

            explain_code, explain_output, explain_error = self._capture_run(
                ["edit-plan", "explain", str(plan_path), "--json"]
            )
            explanation = json.loads(explain_output)
            self.assertEqual(explain_code, 0)
            self.assertEqual(explain_error, "")
            self.assertEqual(explanation["status"], "ok")
            self.assertEqual(explanation["operation_count"], 1)

            edit_code, edit_output, edit_error = self._capture_run(
                [
                    "edit",
                    str(self.source_path),
                    "--plan",
                    str(plan_path),
                    "--dry-run",
                    "--json",
                ]
            )
            preview = json.loads(edit_output)
            self.assertEqual(edit_code, 0)
            self.assertEqual(edit_error, "")
            self.assertEqual(preview["status"], "changes_pending")
            self.assertTrue(preview["dry_run"])
            self.assertEqual(
                preview["output"],
                {"written": False, "sha256": None},
            )
            self.assertEqual(preview["verification"]["semantic"], "passed")
            self.assertEqual(plan_path.read_bytes(), plan_snapshot)
            self._assert_source_unchanged()

        assert temporary_root_path is not None
        self.assertFalse(
            temporary_root_path.exists(),
            "temporary edit-plan directory was not cleaned up",
        )
        self._assert_source_unchanged()


if __name__ == "__main__":
    unittest.main()
