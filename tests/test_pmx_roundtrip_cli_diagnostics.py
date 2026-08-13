"""RED contracts for roundtrip CLI diagnostic taxonomy and JSON failures."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from mmd_registry.cli import run
from mmd_registry.pmx.roundtrip import PmxRoundTripVerificationError
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


class PmxRoundTripCliDiagnosticTests(unittest.TestCase):
    """Lock expected roundtrip error taxonomy across human and JSON modes."""

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_directory.name)
        self.input_path = self.root / "input.pmx"
        self.output_path = self.root / "output.pmx"
        self.input_path.write_bytes(build_pmx_roundtrip_fixture())

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    @staticmethod
    def _capture(arguments: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = run(arguments)
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def _assert_json_error(
        self,
        *,
        expected_exit: int,
        expected_type: str,
        stdout: str,
        stderr: str,
    ) -> dict[str, object]:
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error_type"], expected_type)
        self.assertIsInstance(payload["errors"], list)
        self.assertEqual(len(payload["errors"]), 1)
        self.assertIsInstance(payload["errors"][0], str)
        self.assertNotEqual(payload["errors"][0], "")
        return payload

    def test_invalid_pmx_json_preserves_data_error_taxonomy_and_exit_one(self) -> None:
        self.input_path.write_bytes(b"not a PMX")

        exit_code, stdout, stderr = self._capture(
            [
                "roundtrip",
                str(self.input_path),
                str(self.output_path),
                "--json",
            ]
        )

        self.assertEqual(exit_code, 1)
        payload = self._assert_json_error(
            expected_exit=1,
            expected_type="invalid_pmx",
            stdout=stdout,
            stderr=stderr,
        )
        self.assertNotIn("internal", str(payload).lower())
        self.assertFalse(self.output_path.exists())

    def test_path_policy_json_preserves_path_exit_two(self) -> None:
        missing = self.root / "missing.pmx"

        exit_code, stdout, stderr = self._capture(
            [
                "roundtrip",
                str(missing),
                str(self.output_path),
                "--json",
            ]
        )

        self.assertEqual(exit_code, 2)
        self._assert_json_error(
            expected_exit=2,
            expected_type="path_policy",
            stdout=stdout,
            stderr=stderr,
        )
        self.assertFalse(self.output_path.exists())

    def test_verification_json_preserves_verification_exit_three(self) -> None:
        with patch(
            "mmd_registry.cli.roundtrip_pmx",
            side_effect=PmxRoundTripVerificationError(
                "simulated semantic verification mismatch"
            ),
        ):
            exit_code, stdout, stderr = self._capture(
                [
                    "roundtrip",
                    str(self.input_path),
                    str(self.output_path),
                    "--json",
                ]
            )

        self.assertEqual(exit_code, 3)
        self._assert_json_error(
            expected_exit=3,
            expected_type="verification",
            stdout=stdout,
            stderr=stderr,
        )
        self.assertFalse(self.output_path.exists())

    def test_io_json_preserves_io_exit_two_without_traceback(self) -> None:
        with patch(
            "mmd_registry.cli.roundtrip_pmx",
            side_effect=OSError("simulated roundtrip I/O failure"),
        ):
            exit_code, stdout, stderr = self._capture(
                [
                    "roundtrip",
                    str(self.input_path),
                    str(self.output_path),
                    "--json",
                ]
            )

        self.assertEqual(exit_code, 2)
        payload = self._assert_json_error(
            expected_exit=2,
            expected_type="io",
            stdout=stdout,
            stderr=stderr,
        )
        self.assertNotIn("traceback", str(payload).lower())
        self.assertFalse(self.output_path.exists())

    def test_human_error_exit_codes_remain_unchanged(self) -> None:
        cases = (
            (
                "invalid_pmx",
                lambda: self.input_path.write_bytes(b"not a PMX"),
                None,
                1,
            ),
            (
                "path_policy",
                None,
                None,
                2,
            ),
            (
                "verification",
                None,
                PmxRoundTripVerificationError("simulated verification failure"),
                3,
            ),
            (
                "io",
                None,
                OSError("simulated I/O failure"),
                2,
            ),
        )

        for name, prepare, injected, expected_exit in cases:
            with self.subTest(name=name):
                self.input_path.write_bytes(build_pmx_roundtrip_fixture())
                if prepare is not None:
                    prepare()

                input_path = (
                    self.root / "missing.pmx"
                    if name == "path_policy"
                    else self.input_path
                )
                arguments = [
                    "roundtrip",
                    str(input_path),
                    str(self.output_path),
                ]

                if injected is None:
                    exit_code, stdout, stderr = self._capture(arguments)
                else:
                    with patch(
                        "mmd_registry.cli.roundtrip_pmx",
                        side_effect=injected,
                    ):
                        exit_code, stdout, stderr = self._capture(arguments)

                self.assertEqual(exit_code, expected_exit)
                self.assertEqual(stdout, "")
                self.assertIn("[ERROR] roundtrip:", stderr)
                self.assertNotIn("Traceback", stderr)
                self.output_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
