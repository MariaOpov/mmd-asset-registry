"""Tests for v0.9.5.5 additive Smart CLI routing."""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import io
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import mmd_registry.cli as cli
import mmd_registry.smart_cli as smart_cli


EXPECTED_LEGACY_COMMANDS = (
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


def _subparser_choices(
    parser: argparse.ArgumentParser,
) -> dict[str, argparse.ArgumentParser]:
    actions = [
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    ]
    if len(actions) != 1:
        raise AssertionError(
            f"expected one subparser action, found {len(actions)}"
        )
    return actions[0].choices


class SmartCliRoutingTests(unittest.TestCase):
    def test_legacy_parser_and_command_names_remain_frozen(self) -> None:
        parser = cli.build_argument_parser()
        self.assertEqual(tuple(_subparser_choices(parser)), EXPECTED_LEGACY_COMMANDS)
        self.assertEqual(cli.COMMAND_NAMES, frozenset(EXPECTED_LEGACY_COMMANDS))
        self.assertEqual(
            cli.normalize_arguments(["smart", "inspect", "model.pmx"]),
            ["validate", "smart", "inspect", "model.pmx"],
        )

    def test_application_parser_adds_smart_after_frozen_transaction_runtime_layer(self) -> None:
        transaction_runtime = cli._build_runtime_argument_parser()
        self.assertEqual(
            tuple(_subparser_choices(transaction_runtime)),
            (*EXPECTED_LEGACY_COMMANDS, "transaction-plan"),
        )

        parser = cli._build_application_argument_parser()
        commands = _subparser_choices(parser)
        self.assertEqual(
            tuple(commands),
            (*EXPECTED_LEGACY_COMMANDS, "transaction-plan", "smart"),
        )
        smart_actions = _subparser_choices(commands["smart"])
        self.assertEqual(tuple(smart_actions), ("inspect",))

        arguments = parser.parse_args(["smart", "inspect", "モデル.pmx"])
        self.assertEqual(arguments.command, "smart")
        self.assertEqual(arguments.smart_action, "inspect")
        self.assertEqual(arguments.source, "モデル.pmx")
        self.assertEqual(
            cli._normalize_runtime_arguments(["smart", "inspect", "モデル.pmx"]),
            ["validate", "smart", "inspect", "モデル.pmx"],
        )
        self.assertEqual(
            cli._normalize_application_arguments(["smart", "inspect", "モデル.pmx"]),
            ["smart", "inspect", "モデル.pmx"],
        )

    def test_cli_run_dispatches_smart_without_touching_legacy_dispatch(self) -> None:
        with patch.object(
            cli._smart_cli,
            "run_smart_command",
            return_value=7,
        ) as run_smart:
            exit_code = cli.run(["smart", "inspect", "model.pmx"])

        self.assertEqual(exit_code, 7)
        run_smart.assert_called_once()
        arguments = run_smart.call_args.args[0]
        self.assertEqual(arguments.command, "smart")
        self.assertEqual(arguments.smart_action, "inspect")
        self.assertEqual(arguments.source, "model.pmx")

    def test_smart_adapter_calls_read_only_service_and_writes_stdout(self) -> None:
        sentinel = object()
        arguments = SimpleNamespace(
            smart_action="inspect",
            source="モデル.pmx",
        )
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch.object(smart_cli, "inspect_smart_parts", return_value=sentinel) as inspect,
            patch.object(
                smart_cli,
                "_render_basic_text",
                return_value="SMART PART INSPECTION\n",
            ) as render,
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            exit_code = smart_cli.run_smart_command(arguments)

        self.assertEqual(exit_code, 0)
        inspect.assert_called_once_with("モデル.pmx")
        render.assert_called_once_with(sentinel)
        self.assertEqual(stdout.getvalue(), "SMART PART INSPECTION\n")
        self.assertEqual(stderr.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
