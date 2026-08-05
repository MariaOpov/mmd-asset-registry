"""Tests for JSON reports and generated credits."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from mmd_registry.reporting import (
    build_json_report,
    generate_credits_markdown,
    write_json_report,
)
from mmd_registry.validator import (
    AssetValidationResult,
    RegistryValidationResult,
)


class ReportingTests(unittest.TestCase):
    """Tests for report and credit generation."""

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_directory.name)

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def test_json_report_uses_portable_registry_path(self) -> None:
        registry_file = self.project_root / "assets.yaml"
        result = RegistryValidationResult(
            mode="private",
            registry_version="0.2",
        )

        report = build_json_report(
            result=result,
            registry_file=registry_file,
            project_root=self.project_root,
            generated_at="2026-08-05T21:00:00+07:00",
        )

        self.assertEqual(report["tool_version"], "0.2.0")
        self.assertEqual(report["registry_file"], "assets.yaml")
        self.assertEqual(report["status"], "passed")

    def test_json_report_can_be_written(self) -> None:
        result = RegistryValidationResult(
            mode="private",
            registry_version="0.2",
            assets=[AssetValidationResult(asset_id="demo_asset")],
        )

        report = build_json_report(
            result=result,
            registry_file=self.project_root / "assets.yaml",
            project_root=self.project_root,
            generated_at="2026-08-05T21:00:00+07:00",
        )

        report_file = self.project_root / "reports" / "validation_report.json"

        write_json_report(report, report_file)

        loaded_report = json.loads(report_file.read_text(encoding="utf-8"))

        self.assertEqual(
            loaded_report["summary"]["assets"],
            1,
        )

    def test_credit_markdown_contains_credit_text(self) -> None:
        registry: dict[str, Any] = {
            "assets": [
                {
                    "id": "test_character",
                    "display_name": "Test Character",
                    "credit": {
                        "required": True,
                        "text": "Model by Example Creator",
                        "url": "https://example.com/creator",
                    },
                }
            ]
        }

        markdown = generate_credits_markdown(registry)

        self.assertIn("Test Character", markdown)
        self.assertIn("Model by Example Creator", markdown)
        self.assertIn(
            "https://example.com/creator",
            markdown,
        )

    def test_missing_required_credit_is_listed(self) -> None:
        registry: dict[str, Any] = {
            "assets": [
                {
                    "id": "unknown_model",
                    "display_name": "Unknown Model",
                    "credit": {
                        "required": True,
                        "text": None,
                        "url": None,
                    },
                }
            ]
        }

        markdown = generate_credits_markdown(registry)

        self.assertIn(
            "Incomplete Credit Information",
            markdown,
        )
        self.assertIn("Unknown Model", markdown)


if __name__ == "__main__":
    unittest.main()
