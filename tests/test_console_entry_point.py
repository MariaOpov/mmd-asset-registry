"""Contracts for the installed pre-0.9.0 console entry point."""

from __future__ import annotations

import io
import re
import sys
import tomllib
import unittest
from contextlib import redirect_stderr, redirect_stdout
from importlib.metadata import EntryPoint
from pathlib import Path
from unittest.mock import patch

import check_assets
from mmd_registry import __version__, cli


PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMMAND_NAME = "mmd-asset-registry"
ENTRY_POINT_VALUE = "mmd_registry.cli:main"


class ConsoleEntryPointTests(unittest.TestCase):
    """Keep the installed command thin, portable, and backward compatible."""

    def test_pyproject_declares_one_console_script(self) -> None:
        metadata = tomllib.loads(
            (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )

        self.assertEqual(
            metadata["project"]["scripts"],
            {COMMAND_NAME: ENTRY_POINT_VALUE},
        )

    def test_entry_point_loads_the_existing_cli_main(self) -> None:
        entry_point = EntryPoint(
            name=COMMAND_NAME,
            value=ENTRY_POINT_VALUE,
            group="console_scripts",
        )

        self.assertIs(entry_point.load(), cli.main)

    def test_parser_program_name_matches_the_installed_command(self) -> None:
        self.assertEqual(cli.build_argument_parser().prog, COMMAND_NAME)

    def test_legacy_launcher_uses_the_same_process_boundary(self) -> None:
        self.assertIs(check_assets.main, cli.main)

    def test_console_name_is_safe_for_windows_and_posix_shells(self) -> None:
        self.assertRegex(COMMAND_NAME, re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$"))

    def test_no_argument_callable_supports_version(self) -> None:
        output = io.StringIO()
        error_output = io.StringIO()
        with (
            patch.object(sys, "argv", [COMMAND_NAME, "--version"]),
            redirect_stdout(output),
            redirect_stderr(error_output),
            self.assertRaises(SystemExit) as exit_context,
        ):
            cli.main()

        self.assertEqual(exit_context.exception.code, 0)
        self.assertEqual(output.getvalue(), f"{COMMAND_NAME} {__version__}\n")
        self.assertEqual(error_output.getvalue(), "")

    def test_no_argument_callable_supports_help(self) -> None:
        output = io.StringIO()
        error_output = io.StringIO()
        with (
            patch.object(sys, "argv", [COMMAND_NAME, "--help"]),
            redirect_stdout(output),
            redirect_stderr(error_output),
            self.assertRaises(SystemExit) as exit_context,
        ):
            cli.main()

        self.assertEqual(exit_context.exception.code, 0)
        self.assertIn(f"usage: {COMMAND_NAME}", output.getvalue())
        self.assertIn("--version", output.getvalue())
        self.assertEqual(error_output.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
