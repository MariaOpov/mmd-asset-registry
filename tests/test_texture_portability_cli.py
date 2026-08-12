"""Tests for the texture-portability CLI workflow."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from mmd_registry.cli import normalize_arguments, run
from mmd_registry.hashing import hash_file_sha256
from mmd_registry.pmx.editing import load_pmx_edit_plan
from tests.mmd_fixtures import build_pmx_material, build_pmx_structure


class TexturePortabilityCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_directory.name)

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def capture_run(
        self,
        arguments: list[str],
    ) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = run(arguments)
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def build_model(
        self,
        *,
        texture_paths: tuple[str, ...] = (),
        referenced_texture_indices: tuple[int, ...] = (),
    ) -> Path:
        materials = tuple(
            build_pmx_material(
                texture_index=texture_index,
                surface_index_count=3,
            )
            for texture_index in referenced_texture_indices
        )
        surface_indices = tuple(
            0
            for _ in range(3 * len(referenced_texture_indices))
        )
        model_path = self.project_root / "model.pmx"
        model_path.write_bytes(
            build_pmx_structure(
                surface_indices=surface_indices,
                texture_paths=texture_paths,
                materials=materials,
            )
        )
        return model_path

    def write_texture(
        self,
        relative_path: str,
        data: bytes = b"texture",
    ) -> Path:
        path = self.project_root.joinpath(*relative_path.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def test_texture_portability_command_is_preserved(self) -> None:
        self.assertEqual(
            normalize_arguments(
                ["texture-portability", "model.pmx"]
            ),
            ["texture-portability", "model.pmx"],
        )

    def test_canonical_model_reports_ok_in_json(self) -> None:
        self.write_texture("textures/body.png")
        model_path = self.build_model(
            texture_paths=("textures/body.png",),
            referenced_texture_indices=(0,),
        )

        exit_code, output, error_output = self.capture_run(
            ["texture-portability", str(model_path), "--json"]
        )
        payload = json.loads(output)

        self.assertEqual(exit_code, 0)
        self.assertEqual(error_output, "")
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(
            payload["rewrite_report"]["no_change_count"],
            1,
        )
        self.assertEqual(
            payload["rewrite_report"]["safe_rewrite_count"],
            0,
        )

    def test_backslash_path_reports_safe_rewrite(self) -> None:
        self.write_texture("textures/body.png")
        model_path = self.build_model(
            texture_paths=(r"textures\body.png",),
            referenced_texture_indices=(0,),
        )

        exit_code, output, _ = self.capture_run(
            ["texture-portability", str(model_path), "--json"]
        )
        payload = json.loads(output)
        proposal = payload["rewrite_report"]["proposals"][0]

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "rewrite_available")
        self.assertEqual(proposal["disposition"], "safe_rewrite")
        self.assertEqual(proposal["candidate_path"], "textures/body.png")

    def test_plan_out_writes_strict_plan_with_source_hash(self) -> None:
        self.write_texture("textures/body.png")
        model_path = self.build_model(
            texture_paths=(r"textures\body.png",),
            referenced_texture_indices=(0,),
        )
        plan_path = self.project_root / "rewrite-plan.json"

        exit_code, output, error_output = self.capture_run(
            [
                "texture-portability",
                str(model_path),
                "--plan-out",
                str(plan_path),
                "--json",
            ]
        )
        payload = json.loads(output)
        plan = load_pmx_edit_plan(plan_path)
        source_sha256, _ = hash_file_sha256(model_path)

        self.assertEqual(exit_code, 0)
        self.assertEqual(error_output, "")
        self.assertTrue(payload["plan"]["written"])
        self.assertEqual(payload["plan"]["operation_count"], 1)
        self.assertEqual(plan.expected_source_sha256, source_sha256)
        self.assertEqual(plan.operations[0].texture_index, 0)
        self.assertEqual(plan.operations[0].path, "textures/body.png")

    def test_plan_out_refuses_source_hash_change_during_analysis(self) -> None:
        self.write_texture("textures/body.png")
        model_path = self.build_model(
            texture_paths=(r"textures\body.png",),
            referenced_texture_indices=(0,),
        )
        plan_path = self.project_root / "rewrite-plan.json"
        file_size = model_path.stat().st_size

        with patch(
            "mmd_registry.texture_portability_cli.hash_file_sha256",
            side_effect=[
                ("a" * 64, file_size),
                ("b" * 64, file_size),
            ],
        ):
            exit_code, output, error_output = self.capture_run(
                [
                    "texture-portability",
                    str(model_path),
                    "--plan-out",
                    str(plan_path),
                    "--json",
                ]
            )
        payload = json.loads(output)

        self.assertEqual(exit_code, 1)
        self.assertEqual(error_output, "")
        self.assertEqual(payload["error_type"], "source_changed")
        self.assertFalse(payload["plan"]["written"])
        self.assertFalse(plan_path.exists())

    def test_referenced_blocked_dependency_prevents_partial_plan(self) -> None:
        self.write_texture("textures/body.png")
        model_path = self.build_model(
            texture_paths=(
                r"textures\body.png",
                "textures/missing.png",
            ),
            referenced_texture_indices=(0, 1),
        )
        plan_path = self.project_root / "rewrite-plan.json"

        exit_code, output, error_output = self.capture_run(
            [
                "texture-portability",
                str(model_path),
                "--plan-out",
                str(plan_path),
                "--json",
            ]
        )
        payload = json.loads(output)

        self.assertEqual(exit_code, 1)
        self.assertEqual(error_output, "")
        self.assertEqual(payload["blocked_referenced_count"], 1)
        self.assertEqual(
            payload["rewrite_report"]["safe_rewrite_count"],
            1,
        )
        self.assertFalse(payload["plan"]["written"])
        self.assertFalse(plan_path.exists())

    def test_unreferenced_blocked_dependency_is_warning_not_error(self) -> None:
        model_path = self.build_model(
            texture_paths=("textures/missing.png",),
        )

        exit_code, output, error_output = self.capture_run(
            ["texture-portability", str(model_path), "--json"]
        )
        payload = json.loads(output)

        self.assertEqual(exit_code, 0)
        self.assertEqual(error_output, "")
        self.assertEqual(payload["status"], "warning")
        self.assertEqual(payload["blocked_referenced_count"], 0)
        self.assertEqual(payload["rewrite_report"]["blocked_count"], 1)

    def test_plan_out_is_not_created_when_no_rewrite_is_needed(self) -> None:
        self.write_texture("textures/body.png")
        model_path = self.build_model(
            texture_paths=("textures/body.png",),
            referenced_texture_indices=(0,),
        )
        plan_path = self.project_root / "rewrite-plan.json"

        exit_code, output, _ = self.capture_run(
            [
                "texture-portability",
                str(model_path),
                "--plan-out",
                str(plan_path),
                "--json",
            ]
        )
        payload = json.loads(output)

        self.assertEqual(exit_code, 0)
        self.assertFalse(payload["plan"]["written"])
        self.assertEqual(payload["plan"]["operation_count"], 0)
        self.assertFalse(plan_path.exists())

    def test_existing_plan_output_is_refused_without_overwrite(self) -> None:
        self.write_texture("textures/body.png")
        model_path = self.build_model(
            texture_paths=(r"textures\body.png",),
            referenced_texture_indices=(0,),
        )
        plan_path = self.project_root / "rewrite-plan.json"
        plan_path.write_text("sentinel", encoding="utf-8")

        exit_code, output, error_output = self.capture_run(
            [
                "texture-portability",
                str(model_path),
                "--plan-out",
                str(plan_path),
                "--json",
            ]
        )
        payload = json.loads(output)

        self.assertEqual(exit_code, 2)
        self.assertEqual(error_output, "")
        self.assertEqual(payload["error_type"], "plan_output")
        self.assertEqual(plan_path.read_text(encoding="utf-8"), "sentinel")

    def test_model_path_cannot_be_used_as_plan_output(self) -> None:
        self.write_texture("textures/body.png")
        model_path = self.build_model(
            texture_paths=(r"textures\body.png",),
            referenced_texture_indices=(0,),
        )
        model_before = model_path.read_bytes()

        exit_code, output, _ = self.capture_run(
            [
                "texture-portability",
                str(model_path),
                "--plan-out",
                str(model_path),
                "--json",
            ]
        )
        payload = json.loads(output)

        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["error_type"], "plan_output")
        self.assertEqual(model_path.read_bytes(), model_before)

    def test_missing_input_returns_two(self) -> None:
        missing = self.project_root / "missing.pmx"

        exit_code, output, error_output = self.capture_run(
            ["texture-portability", str(missing), "--json"]
        )
        payload = json.loads(output)

        self.assertEqual(exit_code, 2)
        self.assertEqual(error_output, "")
        self.assertEqual(payload["error_type"], "path_policy")

    def test_malformed_model_returns_one(self) -> None:
        model_path = self.project_root / "broken.pmx"
        model_path.write_bytes(b"")

        exit_code, output, error_output = self.capture_run(
            ["texture-portability", str(model_path), "--json"]
        )
        payload = json.loads(output)

        self.assertEqual(exit_code, 1)
        self.assertEqual(error_output, "")
        self.assertEqual(payload["error_type"], "invalid_pmx")

    def test_analysis_and_plan_generation_do_not_modify_model_or_texture(self) -> None:
        texture = self.write_texture(
            "textures/body.png",
            b"texture sentinel",
        )
        model_path = self.build_model(
            texture_paths=(r"textures\body.png",),
            referenced_texture_indices=(0,),
        )
        plan_path = self.project_root / "rewrite-plan.json"
        model_before = model_path.read_bytes()
        texture_before = texture.read_bytes()

        exit_code, _, _ = self.capture_run(
            [
                "texture-portability",
                str(model_path),
                "--plan-out",
                str(plan_path),
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(model_path.read_bytes(), model_before)
        self.assertEqual(texture.read_bytes(), texture_before)
        self.assertTrue(plan_path.is_file())


if __name__ == "__main__":
    unittest.main()
