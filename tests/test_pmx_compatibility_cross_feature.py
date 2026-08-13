"""Cross-feature compatibility regression matrix for generated PMX models."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from mmd_registry.cli import run
from mmd_registry.pmx import load_pmx
from mmd_registry.pmx.editing import load_pmx_edit_plan
from tests.mmd_fixtures import (
    build_pmx_bone,
    build_pmx_material,
    build_pmx_structure,
)


def _sha256(path: Path) -> str:
    """Return a SHA-256 digest for one generated test file."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


class PmxCompatibilityCrossFeatureTests(unittest.TestCase):
    """Exercise representative generated PMX data through public workflows."""

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_directory.name)
        self.texture_path = self.root / "textures" / "body.png"
        self.texture_path.parent.mkdir(parents=True)
        self.texture_path.write_bytes(b"generated texture fixture")
        self.model_path = self.root / "互換モデル.pmx"
        self.model_path.write_bytes(self._build_representative_model())

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
        """Build the bounded standard roles expected by the default rig profile."""

        return (
            build_pmx_bone(
                local_name="センター",
                universal_name="Center",
                parent_bone_index=-1,
                encoding_flag=1,
                bone_index_size=bone_index_size,
            ),
            build_pmx_bone(
                local_name="下半身",
                universal_name="Lower Body",
                parent_bone_index=0,
                encoding_flag=1,
                bone_index_size=bone_index_size,
            ),
            build_pmx_bone(
                local_name="上半身",
                universal_name="Upper Body",
                parent_bone_index=0,
                encoding_flag=1,
                bone_index_size=bone_index_size,
            ),
            build_pmx_bone(
                local_name="首",
                universal_name="Neck",
                parent_bone_index=2,
                encoding_flag=1,
                bone_index_size=bone_index_size,
            ),
            build_pmx_bone(
                local_name="頭",
                universal_name="Head",
                parent_bone_index=3,
                encoding_flag=1,
                bone_index_size=bone_index_size,
            ),
        )

    @classmethod
    def _build_representative_model(cls) -> bytes:
        """Build one Unicode PMX 2.1 fixture usable by all selected features."""

        index_size = 2
        material = build_pmx_material(
            local_name="材質",
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
            texture_paths=("textures/body.png",),
            materials=(material,),
            bones=cls._build_rig_bones(bone_index_size=index_size),
        )

    def test_scan_doctor_bones_and_rig_accept_representative_model(self) -> None:
        """Require read-only public workflows to agree on one real-shaped fixture."""

        source_sha256 = _sha256(self.model_path)

        scan_code, scan_output, scan_error = self._capture_run(
            ["scan", str(self.model_path), "--json"]
        )
        scan = json.loads(scan_output)
        self.assertEqual(scan_code, 0)
        self.assertEqual(scan_error, "")
        self.assertEqual(scan["status"], "ok")
        self.assertTrue(scan["scan_complete"])
        self.assertEqual(scan["version"], 2.1)
        self.assertEqual(scan["section_summary"]["bone_count"], 5)
        self.assertEqual(scan["dependency_summary"]["declared_texture_path_count"], 1)

        doctor_code, doctor_output, doctor_error = self._capture_run(
            ["doctor", str(self.model_path), "--json"]
        )
        doctor = json.loads(doctor_output)
        self.assertEqual(doctor_code, 0)
        self.assertEqual(doctor_error, "")
        self.assertEqual(doctor["status"], "ok")
        self.assertTrue(doctor["scan"]["scan_complete"])
        self.assertEqual(
            doctor["texture_diagnostics"]["existing_file_count"],
            1,
        )

        bones_code, bones_output, bones_error = self._capture_run(
            ["bones", str(self.model_path), "--json"]
        )
        bones = json.loads(bones_output)
        self.assertEqual(bones_code, 0)
        self.assertEqual(bones_error, "")
        self.assertEqual(bones["status"], "ok")
        self.assertEqual(bones["bone_count"], 5)
        self.assertEqual(bones["match_count"], 5)

        rig_code, rig_output, rig_error = self._capture_run(
            ["rig", str(self.model_path), "--json"]
        )
        rig = json.loads(rig_output)
        self.assertEqual(rig_code, 0)
        self.assertEqual(rig_error, "")
        self.assertEqual(rig["status"], "ok")
        self.assertEqual(rig["analysis"]["summary"]["bone_count"], 5)
        self.assertEqual(rig["analysis"]["bone_map"]["roles"]["head"], [4])

        self.assertEqual(_sha256(self.model_path), source_sha256)

    def test_roundtrip_cli_writes_distinct_copy_and_preserves_source(self) -> None:
        """Require the public roundtrip command to preserve the generated source."""

        output_path = self.root / "roundtrip-output.pmx"
        source_bytes = self.model_path.read_bytes()
        source_sha256 = _sha256(self.model_path)

        exit_code, output, error_output = self._capture_run(
            [
                "roundtrip",
                str(self.model_path),
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
            self.model_path.resolve(),
            output_path.resolve(),
        )
        self.assertEqual(self.model_path.read_bytes(), source_bytes)
        self.assertEqual(_sha256(self.model_path), source_sha256)
        self.assertEqual(load_pmx(output_path), load_pmx(self.model_path))

    def test_strict_edit_plan_and_dry_run_preserve_source_and_plan(self) -> None:
        """Require strict plan loading, edit-plan UX, and dry-run to compose."""

        source_sha256 = _sha256(self.model_path)
        plan_path = self.root / "strict-plan.json"
        plan_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "expected_source_sha256": source_sha256,
                    "operations": [
                        {
                            "op": "set_model_info",
                            "local_name": "互換性 編集プレビュー",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        plan_snapshot = plan_path.read_bytes()

        plan = load_pmx_edit_plan(plan_path)
        self.assertEqual(plan.expected_source_sha256, source_sha256)
        self.assertEqual(len(plan.operations), 1)

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
                str(self.model_path),
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
        self.assertEqual(_sha256(self.model_path), source_sha256)
        self.assertEqual(plan_path.read_bytes(), plan_snapshot)

    def test_texture_portability_plan_flows_into_strict_edit_dry_run(self) -> None:
        """Require a generated rewrite plan to remain strict and executable as preview."""

        index_size = 2
        material = build_pmx_material(
            local_name="材質",
            universal_name="Body Material",
            texture_index=0,
            surface_index_count=3,
            encoding_flag=1,
            texture_index_size=index_size,
        )
        portability_model = self.root / "portable-source.pmx"
        portability_model.write_bytes(
            build_pmx_structure(
                version=2.1,
                encoding_flag=1,
                vertex_index_size=index_size,
                texture_index_size=index_size,
                material_index_size=index_size,
                bone_index_size=index_size,
                morph_index_size=index_size,
                rigid_body_index_size=index_size,
                texture_paths=(r"textures\body.png",),
                materials=(material,),
                bones=self._build_rig_bones(bone_index_size=index_size),
            )
        )
        source_sha256 = _sha256(portability_model)
        plan_path = self.root / "texture-rewrite-plan.json"

        portability_code, portability_output, portability_error = self._capture_run(
            [
                "texture-portability",
                str(portability_model),
                "--plan-out",
                str(plan_path),
                "--json",
            ]
        )
        portability = json.loads(portability_output)
        self.assertEqual(portability_code, 0)
        self.assertEqual(portability_error, "")
        self.assertEqual(portability["status"], "rewrite_available")
        self.assertTrue(portability["plan"]["written"])
        self.assertEqual(portability["plan"]["operation_count"], 1)

        plan = load_pmx_edit_plan(plan_path)
        self.assertEqual(plan.expected_source_sha256, source_sha256)
        self.assertEqual(len(plan.operations), 1)
        self.assertEqual(plan.operations[0].texture_index, 0)
        self.assertEqual(plan.operations[0].path, "textures/body.png")
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
                str(portability_model),
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
        self.assertEqual(preview["verification"]["semantic"], "passed")
        self.assertEqual(_sha256(portability_model), source_sha256)
        self.assertEqual(plan_path.read_bytes(), plan_snapshot)


if __name__ == "__main__":
    unittest.main()
