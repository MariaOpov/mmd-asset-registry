"""Tests for JSON reports and generated credits."""

from __future__ import annotations

import hashlib
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
    validate_registry,
)
from tests.mmd_fixtures import build_minimal_pmx_header


class ReportingTests(unittest.TestCase):
    """Tests for report and credit generation."""

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_directory.name)

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def make_asset(
        self,
        source_path: str,
        expected_sha256: str,
    ) -> dict[str, Any]:
        """Return a valid schema 0.3 asset for report tests."""

        return {
            "id": "test_character",
            "display_name": "Test Character",
            "asset_type": "character_model",
            "pipeline_character": "TestCharacter",
            "source_path": source_path,
            "integrity": {
                "sha256": expected_sha256,
            },
            "creator": {
                "name": "Example Creator",
                "profile_url": "https://example.com/creator",
            },
            "source": {
                "page_url": "https://example.com/model",
                "downloaded_at": "2026-08-05",
            },
            "credit": {
                "required": True,
                "text": "Model by Example Creator",
                "url": "https://example.com/creator",
            },
            "usage_rules": {
                "editing": "allowed",
                "redistribution": "prohibited",
                "commercial_use": "allowed",
                "notes": "Credit the original creator.",
            },
            "status": "ready",
            "tags": [
                "character",
                "test",
            ],
            "notes": "Test fixture.",
        }

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

        self.assertEqual(report["tool_version"], "0.8.5")
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

    def test_json_report_includes_integrity_and_file_size(self) -> None:
        payload = build_minimal_pmx_header("Report Fixture")
        model_file = self.project_root / "models" / "model.pmx"
        model_file.parent.mkdir()
        model_file.write_bytes(payload)

        expected_sha256 = hashlib.sha256(payload).hexdigest()
        registry = {
            "registry_version": "0.3",
            "assets": [
                self.make_asset(
                    source_path="models/model.pmx",
                    expected_sha256=expected_sha256,
                )
            ],
        }

        result = validate_registry(
            registry=registry,
            project_root=self.project_root,
            mode="private",
        )

        report = build_json_report(
            result=result,
            registry_file=self.project_root / "assets.yaml",
            project_root=self.project_root,
            generated_at="2026-08-05T21:00:00+07:00",
        )

        asset_report = report["assets"][0]

        self.assertEqual(asset_report["source_path"], "models/model.pmx")
        self.assertEqual(asset_report["file"]["size_bytes"], len(payload))
        self.assertEqual(
            asset_report["integrity"],
            {
                "algorithm": "sha256",
                "expected": expected_sha256,
                "actual": expected_sha256,
                "status": "matched",
            },
        )
        self.assertEqual(
            asset_report["inspection"],
            {
                "status": "ok",
                "detected_format": "pmx",
                "magic": "PMX ",
                "version": 2.0,
                "model_name": "Report Fixture",
                "encoding": "utf-8",
                "errors": [],
                "warnings": [],
            },
        )

    def test_json_report_makes_absolute_asset_path_portable(self) -> None:
        payload = build_minimal_pmx_header("Absolute Report Fixture")
        model_file = self.project_root / "models" / "absolute.pmx"
        model_file.parent.mkdir()
        model_file.write_bytes(payload)

        expected_sha256 = hashlib.sha256(payload).hexdigest()
        registry = {
            "registry_version": "0.3",
            "assets": [
                self.make_asset(
                    source_path=str(model_file.resolve()),
                    expected_sha256=expected_sha256,
                )
            ],
        }

        result = validate_registry(
            registry=registry,
            project_root=self.project_root,
            mode="private",
        )

        report = build_json_report(
            result=result,
            registry_file=self.project_root / "assets.yaml",
            project_root=self.project_root,
            generated_at="2026-08-05T21:00:00+07:00",
        )

        self.assertEqual(
            report["assets"][0]["source_path"],
            "models/absolute.pmx",
        )

    def test_schema_0_2_asset_report_has_no_integrity_result(self) -> None:
        result = RegistryValidationResult(
            mode="private",
            registry_version="0.2",
            assets=[
                AssetValidationResult(
                    asset_id="legacy_asset",
                    source_path="models/legacy.pmx",
                )
            ],
        )

        report = build_json_report(
            result=result,
            registry_file=self.project_root / "assets.yaml",
            project_root=self.project_root,
            generated_at="2026-08-05T21:00:00+07:00",
        )

        asset_report = report["assets"][0]

        self.assertEqual(asset_report["source_path"], "models/legacy.pmx")
        self.assertEqual(asset_report["file"]["size_bytes"], None)
        self.assertIsNone(asset_report["integrity"])
        self.assertIsNone(asset_report["inspection"])

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
