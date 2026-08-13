"""Representative backward-compatibility contracts for the v0.8 release line."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from mmd_registry.cli import COMMAND_NAMES, run
from mmd_registry.constants import LATEST_SCHEMA_VERSION, SUPPORTED_SCHEMA_VERSIONS
from mmd_registry.pmx import load_pmx, roundtrip_pmx
from mmd_registry.pmx.editing.errors import PmxEditPlanError
from mmd_registry.pmx.editing.json_loader import (
    load_pmx_edit_plan,
    parse_pmx_edit_plan_json,
)
from mmd_registry.pmx.editing.output import write_pmx_edit
from mmd_registry.pmx.editing.plan import PMX_EDIT_PLAN_SCHEMA_VERSION
from mmd_registry.pmx.editing.preview import dry_run_pmx_edit
from tests.mmd_fixtures import (
    build_pmx_bone,
    build_pmx_material,
    build_pmx_structure,
)


LEGACY_V080_COMMANDS = frozenset(
    (
        "validate",
        "hash",
        "inspect",
        "scan",
        "roundtrip",
        "edit",
        "doctor",
        "bones",
        "rig",
    )
)

V080_PLAN_TOP_LEVEL_KEYS = {
    "schema_version",
    "expected_source_sha256",
    "operations",
}

EDIT_REPORT_KEYS = {
    "preview_schema_version",
    "status",
    "dry_run",
    "source",
    "plan",
    "output",
    "verification",
    "audit",
}

ROUNDTRIP_REPORT_KEYS = {
    "status",
    "input_path",
    "output_path",
    "version",
    "encoding",
    "model_name",
    "section_counts",
    "semantic_equal",
    "byte_identical",
    "input_size",
    "output_size",
    "input_sha256",
    "output_sha256",
}


class V08BackwardCompatibilityTests(unittest.TestCase):
    """Freeze representative machine contracts from v0.8.0 through v0.8.4."""

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_directory.name)
        self.texture_path = self.root / "textures" / "body.png"
        self.texture_path.parent.mkdir(parents=True)
        self.texture_path.write_bytes(b"generated texture fixture")
        self.model_path = self.root / "compat-source.pmx"
        self.source_bytes = self._build_model("textures/body.png")
        self.model_path.write_bytes(self.source_bytes)
        self.source_sha256 = hashlib.sha256(self.source_bytes).hexdigest()

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
    def _build_model(texture_path: str) -> bytes:
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
            vertex_index_size=index_size,
            texture_index_size=index_size,
            material_index_size=index_size,
            bone_index_size=index_size,
            morph_index_size=index_size,
            rigid_body_index_size=index_size,
            texture_paths=(texture_path,),
            materials=(material,),
            bones=(
                build_pmx_bone(
                    local_name="Center",
                    universal_name="Center",
                    parent_bone_index=-1,
                    encoding_flag=1,
                    bone_index_size=index_size,
                ),
            ),
        )

    def _historical_v080_payload(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "expected_source_sha256": self.source_sha256,
            "operations": [
                {
                    "op": "set_model_info",
                    "local_name": "Historical v0.8 Model",
                },
                {
                    "op": "set_texture_path",
                    "texture_index": 0,
                    "path": "textures/body-alt.png",
                },
                {
                    "op": "update_material",
                    "material_index": 0,
                    "memo": "Historical v0.8 material memo",
                },
            ],
        }

    def test_v080_valid_plan_still_loads_and_roundtrips_without_translation(self) -> None:
        """A representative v0.8.0 plan must remain directly consumable."""

        payload = self._historical_v080_payload()
        self.assertEqual(set(payload), V080_PLAN_TOP_LEVEL_KEYS)

        plan = parse_pmx_edit_plan_json(
            json.dumps(payload, ensure_ascii=False)
        )

        self.assertEqual(plan.schema_version, 1)
        self.assertEqual(plan.expected_source_sha256, self.source_sha256)
        self.assertEqual(plan.to_dict(), payload)
        self.assertEqual(
            tuple(operation["op"] for operation in plan.to_dict()["operations"]),
            ("set_model_info", "set_texture_path", "update_material"),
        )

    def test_strict_loader_and_schema_contracts_remain_version_independent(self) -> None:
        """Tool releases must not silently renumber registry or edit-plan schemas."""

        self.assertEqual(PMX_EDIT_PLAN_SCHEMA_VERSION, 1)
        self.assertEqual(LATEST_SCHEMA_VERSION, "0.3")
        self.assertEqual(SUPPORTED_SCHEMA_VERSIONS, frozenset(("0.2", "0.3")))

        future_schema = {
            "schema_version": 2,
            "operations": [{"op": "set_model_info", "local_name": "X"}],
        }
        with self.assertRaisesRegex(
            PmxEditPlanError,
            "unsupported schema version 2",
        ):
            parse_pmx_edit_plan_json(json.dumps(future_schema))

        unknown_top_level = {
            "schema_version": 1,
            "registry_schema": "0.3",
            "operations": [{"op": "set_model_info", "local_name": "X"}],
        }
        with self.assertRaisesRegex(PmxEditPlanError, "unknown field"):
            parse_pmx_edit_plan_json(json.dumps(unknown_top_level))

    def test_v080_cli_namespace_remains_present_with_additive_later_commands(self) -> None:
        """v0.8.2/v0.8.3 additions must not remove the original v0.8 commands."""

        self.assertTrue(LEGACY_V080_COMMANDS.issubset(COMMAND_NAMES))
        self.assertIn("edit-plan", COMMAND_NAMES)
        self.assertIn("texture-portability", COMMAND_NAMES)

    def test_v081_structured_diagnostic_preserves_legacy_json_error_fields(self) -> None:
        """Structured diagnostics remain additive to the original edit JSON shape."""

        plan_path = self.root / "invalid-plan.json"
        plan_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "operations": [
                        {
                            "op": "rename_model",
                            "local_name": "unsupported",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        exit_code, output, error_output = self._capture_run(
            [
                "edit",
                str(self.model_path),
                "--plan",
                str(plan_path),
                "--dry-run",
                "--json",
            ]
        )
        payload = json.loads(output)

        self.assertEqual(exit_code, 1)
        self.assertEqual(error_output, "")
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error_type"], "invalid_plan")
        self.assertIsInstance(payload["errors"], list)
        self.assertEqual(len(payload["errors"]), 1)
        self.assertIn("unsupported operation", payload["errors"][0])
        self.assertEqual(payload["error"]["code"], "edit_plan_invalid")
        self.assertEqual(payload["error"]["phase"], "plan_validate")
        self.assertEqual(payload["error"]["message"], payload["errors"][0])

    def test_v080_preview_and_write_machine_fields_remain_compatible(self) -> None:
        """Successful edit reports retain their stable semantic field structure."""

        plan = parse_pmx_edit_plan_json(
            json.dumps(self._historical_v080_payload())
        )
        preview = dry_run_pmx_edit(self.source_bytes, plan)
        preview_payload = preview.to_dict()

        output_path = self.root / "edited-output.pmx"
        write_result = write_pmx_edit(self.model_path, output_path, plan)
        write_payload = write_result.to_dict()

        self.assertEqual(set(preview_payload), EDIT_REPORT_KEYS)
        self.assertEqual(set(write_payload), EDIT_REPORT_KEYS)
        self.assertEqual(
            set(preview_payload["source"]),
            {"sha256", "size_bytes"},
        )
        self.assertEqual(
            set(write_payload["source"]),
            {"path", "sha256", "size_bytes"},
        )
        for payload in (preview_payload, write_payload):
            self.assertEqual(
                set(payload["plan"]),
                {"sha256", "schema_version", "operation_count"},
            )
            self.assertEqual(
                set(payload["verification"]),
                {"semantic", "input_unchanged"},
            )
            self.assertEqual(payload["verification"]["semantic"], "passed")
            self.assertIs(payload["verification"]["input_unchanged"], True)

        self.assertTrue(preview_payload["dry_run"])
        self.assertFalse(write_payload["dry_run"])
        self.assertEqual(preview_payload["plan"], write_payload["plan"])
        self.assertEqual(preview_payload["audit"], write_payload["audit"])
        self.assertEqual(self.model_path.read_bytes(), self.source_bytes)
        self.assertTrue(output_path.is_file())

    def test_v083_portability_json_still_emits_a_strict_v080_edit_plan(self) -> None:
        """The portability bridge must target the existing schema-one edit surface."""

        portability_model = self.root / "portability-source.pmx"
        portability_bytes = self._build_model(r"textures\body.png")
        portability_model.write_bytes(portability_bytes)
        portability_sha256 = hashlib.sha256(portability_bytes).hexdigest()
        plan_path = self.root / "portability-plan.json"

        exit_code, output, error_output = self._capture_run(
            [
                "texture-portability",
                str(portability_model),
                "--plan-out",
                str(plan_path),
                "--json",
            ]
        )
        payload = json.loads(output)

        self.assertEqual(exit_code, 0)
        self.assertEqual(error_output, "")
        self.assertEqual(payload["status"], "rewrite_available")
        self.assertIn("rewrite_report", payload)
        self.assertIn("plan", payload)
        self.assertEqual(
            payload["rewrite_report"]["safe_rewrite_count"],
            1,
        )
        proposal = payload["rewrite_report"]["proposals"][0]
        self.assertEqual(proposal["disposition"], "safe_rewrite")
        self.assertTrue(payload["plan"]["written"])
        self.assertEqual(payload["plan"]["operation_count"], 1)

        plan = load_pmx_edit_plan(plan_path)
        self.assertEqual(plan.schema_version, 1)
        self.assertEqual(plan.expected_source_sha256, portability_sha256)
        self.assertEqual(
            plan.to_dict()["operations"],
            [
                {
                    "op": "set_texture_path",
                    "texture_index": 0,
                    "path": "textures/body.png",
                }
            ],
        )
        self.assertEqual(portability_model.read_bytes(), portability_bytes)

    def test_roundtrip_machine_report_and_source_contract_remain_compatible(self) -> None:
        """Later v0.8 stabilization must preserve the pre-existing roundtrip contract."""

        output_path = self.root / "roundtrip-output.pmx"
        result = roundtrip_pmx(self.model_path, output_path)
        payload = result.to_dict()

        self.assertEqual(set(payload), ROUNDTRIP_REPORT_KEYS)
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["semantic_equal"])
        self.assertEqual(payload["input_sha256"], self.source_sha256)
        self.assertEqual(self.model_path.read_bytes(), self.source_bytes)
        self.assertEqual(load_pmx(output_path), load_pmx(self.model_path))


if __name__ == "__main__":
    unittest.main()
