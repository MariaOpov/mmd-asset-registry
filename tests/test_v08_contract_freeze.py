"""Executable freeze tests for the stable public v0.8 contract."""

from __future__ import annotations

import argparse
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from mmd_registry.cli import COMMAND_NAMES, build_argument_parser, normalize_arguments, run
from mmd_registry.pmx.editing.catalog import get_pmx_edit_operation_catalog


EXPECTED_COMMAND_ORDER = (
    "validate",
    "hash",
    "inspect",
    "scan",
    "roundtrip",
    "edit",
    "edit-plan",
    "texture-portability",
    "doctor",
    "bones",
    "rig",
)

EXPECTED_COMMAND_SURFACES = {
    "validate": ((), frozenset(("--registry", "--mode", "--report", "--no-report", "--credits"))),
    "hash": (("path",), frozenset(("--expected", "--json"))),
    "inspect": (("path",), frozenset(("--json",))),
    "scan": (("path",), frozenset(("--json",))),
    "roundtrip": (("input", "output"), frozenset(("--overwrite", "--json"))),
    "edit": (("input", "output"), frozenset(("--plan", "--dry-run", "--overwrite", "--json"))),
    "edit-plan": ((), frozenset()),
    "texture-portability": (("path",), frozenset(("--plan-out", "--json"))),
    "doctor": (("path",), frozenset(("--json",))),
    "bones": (("path",), frozenset(("--tree", "--details", "--search", "--ik-only", "--json"))),
    "rig": (("path",), frozenset(("--unmapped", "--role", "--export-map", "--json"))),
}

EXPECTED_EDIT_PLAN_ACTION_SURFACES = {
    "catalog": ((), frozenset(("--json",))),
    "template": (("operation_type",), frozenset()),
    "explain": (("plan",), frozenset(("--json",))),
}


def _subparser_choices(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    actions = [
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    ]
    if len(actions) != 1:
        raise AssertionError(
            f"expected exactly one subparser action, found {len(actions)}"
        )
    return actions[0].choices


def _parser_surface(
    parser: argparse.ArgumentParser,
) -> tuple[tuple[str, ...], frozenset[str]]:
    positionals: list[str] = []
    options: set[str] = set()

    for action in parser._actions:
        if isinstance(action, (argparse._HelpAction, argparse._SubParsersAction)):
            continue
        if action.option_strings:
            options.update(action.option_strings)
        else:
            positionals.append(action.dest)

    return tuple(positionals), frozenset(options)


def _action_by_dest(
    parser: argparse.ArgumentParser,
    dest: str,
) -> argparse.Action:
    for action in parser._actions:
        if action.dest == dest:
            return action
    raise AssertionError(f"parser action {dest!r} was not found")


class V08ContractFreezeTests(unittest.TestCase):
    """Freeze machine-facing v0.8 contracts without snapshotting help prose."""

    def test_command_namespace_and_legacy_normalization_are_frozen(self) -> None:
        self.assertEqual(COMMAND_NAMES, frozenset(EXPECTED_COMMAND_ORDER))
        self.assertEqual(normalize_arguments([]), ["validate"])
        self.assertEqual(
            normalize_arguments(["--mode", "publish"]),
            ["validate", "--mode", "publish"],
        )
        explicit = ["hash", "asset.bin", "--json"]
        self.assertEqual(normalize_arguments(explicit), explicit)

    def test_top_level_command_parser_surface_is_frozen(self) -> None:
        parser = build_argument_parser()
        command_parsers = _subparser_choices(parser)

        self.assertEqual(tuple(command_parsers), EXPECTED_COMMAND_ORDER)
        for command, expected_surface in EXPECTED_COMMAND_SURFACES.items():
            with self.subTest(command=command):
                self.assertEqual(
                    _parser_surface(command_parsers[command]),
                    expected_surface,
                )

    def test_selected_parser_semantics_are_frozen(self) -> None:
        command_parsers = _subparser_choices(build_argument_parser())

        validate_mode = _action_by_dest(command_parsers["validate"], "mode")
        self.assertEqual(
            tuple(validate_mode.choices),
            ("commercial", "private", "publish"),
        )

        edit_output = _action_by_dest(command_parsers["edit"], "output")
        self.assertEqual(edit_output.nargs, "?")
        self.assertIsNone(edit_output.default)

        edit_plan = _action_by_dest(command_parsers["edit"], "plan")
        self.assertTrue(edit_plan.required)

        edit_plan_actions = _subparser_choices(command_parsers["edit-plan"])
        template_operation = _action_by_dest(
            edit_plan_actions["template"],
            "operation_type",
        )
        self.assertEqual(
            tuple(template_operation.choices),
            ("set_model_info", "set_texture_path", "update_material"),
        )

    def test_edit_plan_action_parser_surface_is_frozen(self) -> None:
        command_parsers = _subparser_choices(build_argument_parser())
        action_parsers = _subparser_choices(command_parsers["edit-plan"])

        self.assertEqual(
            tuple(action_parsers),
            ("catalog", "template", "explain"),
        )
        for action, expected_surface in EXPECTED_EDIT_PLAN_ACTION_SURFACES.items():
            with self.subTest(action=action):
                self.assertEqual(
                    _parser_surface(action_parsers[action]),
                    expected_surface,
                )

    def test_edit_operation_catalog_contract_is_frozen(self) -> None:
        catalog = get_pmx_edit_operation_catalog().to_dict()
        operations = {
            entry["type"]: entry
            for entry in catalog["operations"]
        }

        self.assertEqual(
            tuple(operations),
            ("set_model_info", "set_texture_path", "update_material"),
        )

        expected = {
            "set_model_info": {
                "target_kind": "model",
                "effect_kind": "model_metadata",
                "required_fields": (),
                "optional_fields": (
                    "local_name",
                    "universal_name",
                    "local_comments",
                    "universal_comments",
                ),
                "constraints": ("at_least_one_update_field",),
            },
            "set_texture_path": {
                "target_kind": "texture",
                "effect_kind": "texture_path",
                "required_fields": ("texture_index", "path"),
                "optional_fields": (),
                "constraints": (
                    "target_index_range_checked_when_applied",
                    "texture_path_policy_checked_when_applied",
                ),
            },
            "update_material": {
                "target_kind": "material",
                "effect_kind": "material_state",
                "required_fields": ("material_index",),
                "optional_fields": (
                    "local_name",
                    "universal_name",
                    "memo",
                    "texture_index",
                    "sphere_texture_index",
                    "sphere_mode",
                    "toon_reference_mode",
                    "toon_reference_index",
                    "diffuse",
                    "specular",
                    "specular_strength",
                    "ambient",
                    "drawing_flags",
                    "edge_color",
                    "edge_scale",
                ),
                "constraints": (
                    "at_least_one_update_field",
                    "target_index_range_checked_when_applied",
                    "reference_ranges_checked_when_applied",
                    "shared_toon_reference_index_must_be_0_through_9",
                ),
            },
        }

        for operation_type, expected_contract in expected.items():
            entry = operations[operation_type]
            with self.subTest(operation=operation_type):
                self.assertEqual(entry["target_kind"], expected_contract["target_kind"])
                self.assertEqual(entry["effect_kind"], expected_contract["effect_kind"])
                self.assertEqual(
                    tuple(entry["required_fields"]),
                    expected_contract["required_fields"],
                )
                self.assertEqual(
                    tuple(entry["optional_fields"]),
                    expected_contract["optional_fields"],
                )
                self.assertEqual(
                    tuple(entry["constraints"]),
                    expected_contract["constraints"],
                )

        update_fields = {
            field["name"]: field
            for field in operations["update_material"]["fields"]
        }
        self.assertEqual(update_fields["drawing_flags"]["minimum"], 0)
        self.assertEqual(update_fields["drawing_flags"]["maximum"], 255)
        self.assertEqual(update_fields["sphere_mode"]["choices"], [0, 1, 2, 3])
        self.assertEqual(
            update_fields["toon_reference_mode"]["choices"],
            ["texture", "shared"],
        )
        self.assertEqual(update_fields["diffuse"]["array_length"], 4)
        self.assertTrue(update_fields["diffuse"]["finite"])
        self.assertEqual(update_fields["edge_scale"]["json_type"], "float")
        self.assertTrue(update_fields["edge_scale"]["finite"])

    def test_explain_success_json_shape_and_boolean_source_binding_are_frozen(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            plan_path = Path(temporary_directory) / "plan.json"
            plan_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "operations": [
                            {
                                "op": "set_model_info",
                                "local_name": "X",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            output = io.StringIO()
            error_output = io.StringIO()
            with redirect_stdout(output), redirect_stderr(error_output):
                exit_code = run(
                    ["edit-plan", "explain", str(plan_path), "--json"]
                )

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(error_output.getvalue(), "")
        self.assertEqual(
            set(payload),
            {
                "status",
                "schema_version",
                "expected_source_sha256",
                "operation_count",
                "operations",
            },
        )
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["schema_version"], 1)
        self.assertIs(payload["expected_source_sha256"], False)
        self.assertEqual(payload["operation_count"], 1)
        self.assertEqual(
            set(payload["operations"][0]),
            {"index", "type", "target", "fields"},
        )
        self.assertEqual(
            payload["operations"][0],
            {
                "index": 0,
                "type": "set_model_info",
                "target": "model",
                "fields": ["local_name"],
            },
        )


if __name__ == "__main__":
    unittest.main()
