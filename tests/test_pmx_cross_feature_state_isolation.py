"""Cross-feature state-isolation and deterministic composition regressions."""

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
from mmd_registry.model_scanning import scan_pmx_structure
from mmd_registry.pmx import load_pmx, roundtrip_pmx, validate_pmx_document
from mmd_registry.pmx.editing.explain import explain_pmx_edit_plan
from mmd_registry.pmx.editing.json_loader import load_pmx_edit_plan
from mmd_registry.pmx.editing.output import write_pmx_edit
from mmd_registry.pmx.editing.preview import dry_run_pmx_edit
from tests.mmd_fixtures import (
    build_pmx_bone,
    build_pmx_material,
    build_pmx_structure,
)


def _sha256_bytes(data: bytes) -> str:
    """Return one deterministic SHA-256 digest."""

    return hashlib.sha256(data).hexdigest()


class PmxCrossFeatureStateIsolationTests(unittest.TestCase):
    """Freeze repeated composition without shared state or source mutation."""

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_directory.name)
        self.texture_path = self.root / "textures" / "body.png"
        self.texture_path.parent.mkdir(parents=True)
        self.texture_path.write_bytes(b"generated texture fixture")
        self.model_path = self.root / "state-isolation-source.pmx"
        self.source_bytes = self._build_representative_model()
        self.model_path.write_bytes(self.source_bytes)
        self.source_sha256 = _sha256_bytes(self.source_bytes)

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    @staticmethod
    def _capture_run(arguments: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = run(arguments)
        return exit_code, stdout.getvalue(), stderr.getvalue()

    @staticmethod
    def _build_rig_bones(*, bone_index_size: int = 2) -> tuple[bytes, ...]:
        return (
            build_pmx_bone(
                local_name="Center",
                universal_name="Center",
                parent_bone_index=-1,
                encoding_flag=1,
                bone_index_size=bone_index_size,
            ),
            build_pmx_bone(
                local_name="Lower Body",
                universal_name="Lower Body",
                parent_bone_index=0,
                encoding_flag=1,
                bone_index_size=bone_index_size,
            ),
            build_pmx_bone(
                local_name="Upper Body",
                universal_name="Upper Body",
                parent_bone_index=0,
                encoding_flag=1,
                bone_index_size=bone_index_size,
            ),
            build_pmx_bone(
                local_name="Neck",
                universal_name="Neck",
                parent_bone_index=2,
                encoding_flag=1,
                bone_index_size=bone_index_size,
            ),
            build_pmx_bone(
                local_name="Head",
                universal_name="Head",
                parent_bone_index=3,
                encoding_flag=1,
                bone_index_size=bone_index_size,
            ),
        )

    @classmethod
    def _build_representative_model(
        cls,
        *,
        texture_path: str = "textures/body.png",
    ) -> bytes:
        index_size = 2
        material = build_pmx_material(
            local_name="Body",
            universal_name="Body Material",
            texture_index=0,
            surface_index_count=3,
            encoding_flag=1,
            texture_index_size=index_size,
        )
        return build_pmx_structure(
            version=2.1,
            encoding_flag=1,
            additional_uv_count=1,
            vertex_index_size=index_size,
            texture_index_size=index_size,
            material_index_size=index_size,
            bone_index_size=index_size,
            morph_index_size=index_size,
            rigid_body_index_size=index_size,
            texture_paths=(texture_path,),
            materials=(material,),
            bones=cls._build_rig_bones(bone_index_size=index_size),
        )

    def _read_only_sequence(self) -> tuple[dict[str, object], ...]:
        payloads: list[dict[str, object]] = []
        for command in ("scan", "doctor", "bones", "rig"):
            code, output, error = self._capture_run(
                [command, str(self.model_path), "--json"]
            )
            self.assertEqual(code, 0, msg=f"{command} failed: {error}")
            self.assertEqual(error, "")
            payload = json.loads(output)
            self.assertEqual(payload["status"], "ok")
            payloads.append(payload)
        return tuple(payloads)

    def test_repeated_read_only_sequence_is_identical_and_source_pure(self) -> None:
        """scan -> doctor -> bones -> rig must not leak state across calls."""

        before_files = {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in self.root.rglob("*")
            if path.is_file()
        }

        first = self._read_only_sequence()
        second = self._read_only_sequence()

        after_files = {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in self.root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(second, first)
        self.assertEqual(after_files, before_files)
        self.assertEqual(self.model_path.read_bytes(), self.source_bytes)

    def test_portability_plan_explain_preview_repeats_without_source_mutation(self) -> None:
        """Portability -> strict plan -> explain -> dry-run must compose purely."""

        portable_source = self.root / "portable-source.pmx"
        portable_bytes = self._build_representative_model(
            texture_path=r"textures\body.png"
        )
        portable_source.write_bytes(portable_bytes)
        portable_sha256 = _sha256_bytes(portable_bytes)
        first_plan_path = self.root / "rewrite-first.json"
        second_plan_path = self.root / "rewrite-second.json"

        generated_plans = []
        for plan_path in (first_plan_path, second_plan_path):
            code, output, error = self._capture_run(
                [
                    "texture-portability",
                    str(portable_source),
                    "--plan-out",
                    str(plan_path),
                    "--json",
                ]
            )
            self.assertEqual(code, 0, msg=error)
            self.assertEqual(error, "")
            payload = json.loads(output)
            self.assertEqual(payload["status"], "rewrite_available")
            self.assertTrue(payload["plan"]["written"])
            generated_plans.append(load_pmx_edit_plan(plan_path))

        first_plan, second_plan = generated_plans
        self.assertEqual(first_plan, second_plan)
        self.assertEqual(first_plan_path.read_bytes(), second_plan_path.read_bytes())

        first_explanation = explain_pmx_edit_plan(first_plan)
        second_explanation = explain_pmx_edit_plan(second_plan)
        self.assertEqual(first_explanation, second_explanation)

        first_preview = dry_run_pmx_edit(portable_bytes, first_plan)
        second_preview = dry_run_pmx_edit(portable_bytes, second_plan)
        self.assertEqual(first_preview, second_preview)
        self.assertEqual(first_preview.source_sha256, portable_sha256)
        self.assertEqual(portable_source.read_bytes(), portable_bytes)

    def test_dry_run_apply_reread_validate_has_no_temp_residue(self) -> None:
        """Strict plan -> dry-run -> apply -> reread -> validate stays isolated."""

        plan_path = self.root / "strict-plan.json"
        plan_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "expected_source_sha256": self.source_sha256,
                    "operations": [
                        {
                            "op": "set_model_info",
                            "local_name": "State Isolation Edited",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        plan_snapshot = plan_path.read_bytes()
        plan = load_pmx_edit_plan(plan_path)
        preview = dry_run_pmx_edit(self.source_bytes, plan)

        first_output = self.root / "edited-first.pmx"
        second_output = self.root / "edited-second.pmx"
        first_result = write_pmx_edit(self.model_path, first_output, plan)
        second_result = write_pmx_edit(self.model_path, second_output, plan)

        self.assertEqual(first_result.output_sha256, second_result.output_sha256)
        self.assertEqual(first_output.read_bytes(), second_output.read_bytes())
        self.assertEqual(load_pmx(first_output), preview.document)
        self.assertEqual(load_pmx(second_output), preview.document)
        validate_pmx_document(load_pmx(first_output))
        validate_pmx_document(load_pmx(second_output))

        self.assertEqual(self.model_path.read_bytes(), self.source_bytes)
        self.assertEqual(plan_path.read_bytes(), plan_snapshot)
        self.assertEqual(list(self.root.glob(".*.tmp")), [])

    def test_roundtrip_reread_scan_is_cwd_independent_for_explicit_paths(self) -> None:
        """Explicit-path roundtrip and scan must not depend on process CWD."""

        first_cwd = self.root / "cwd-first"
        second_cwd = self.root / "cwd-second"
        first_cwd.mkdir()
        second_cwd.mkdir()
        first_output = self.root / "roundtrip-first.pmx"
        second_output = self.root / "roundtrip-second.pmx"
        original_cwd = Path.cwd()

        try:
            os.chdir(first_cwd)
            roundtrip_pmx(self.model_path, first_output)
            first_scan = scan_pmx_structure(first_output)

            os.chdir(second_cwd)
            roundtrip_pmx(self.model_path, second_output)
            second_scan = scan_pmx_structure(second_output)
        finally:
            os.chdir(original_cwd)

        self.assertEqual(first_output.read_bytes(), second_output.read_bytes())
        self.assertEqual(load_pmx(first_output), load_pmx(second_output))
        self.assertEqual(first_scan, second_scan)
        self.assertEqual(self.model_path.read_bytes(), self.source_bytes)
        self.assertEqual(list(self.root.glob(".*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
