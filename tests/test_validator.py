"""Tests for the schema 0.2 registry validator."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from mmd_registry.validator import validate_registry


class RegistryValidatorTests(unittest.TestCase):
    """Tests for registry and usage-mode validation."""

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_directory.name)

        model_file = self.project_root / "model.pmx"
        model_file.write_bytes(b"placeholder")

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def make_asset(self) -> dict[str, Any]:
        return {
            "id": "test_character",
            "display_name": "Test Character",
            "asset_type": "character_model",
            "pipeline_character": "TestCharacter",
            "source_path": "model.pmx",
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

    def make_registry(
        self,
        assets: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "registry_version": "0.2",
            "assets": assets,
        }

    def test_valid_private_registry_passes(self) -> None:
        registry = self.make_registry([self.make_asset()])

        result = validate_registry(
            registry,
            self.project_root,
            mode="private",
        )

        self.assertEqual(result.status, "passed")
        self.assertEqual(result.error_count, 0)
        self.assertEqual(result.warning_count, 0)

    def test_missing_source_file_is_error(self) -> None:
        asset = self.make_asset()
        asset["source_path"] = "missing.pmx"

        result = validate_registry(
            self.make_registry([asset]),
            self.project_root,
        )

        self.assertEqual(result.status, "failed")
        self.assertTrue(
            any("Source file not found" in error for error in result.assets[0].errors)
        )

    def test_publish_mode_requires_credit_text(self) -> None:
        asset = self.make_asset()
        asset["credit"]["text"] = None

        result = validate_registry(
            self.make_registry([asset]),
            self.project_root,
            mode="publish",
        )

        self.assertEqual(result.status, "failed")
        self.assertIn(
            "Credit is required, but credit.text is missing.",
            result.assets[0].errors,
        )

    def test_commercial_mode_rejects_unclear_permission(self) -> None:
        asset = self.make_asset()
        asset["usage_rules"]["commercial_use"] = "unclear"

        result = validate_registry(
            self.make_registry([asset]),
            self.project_root,
            mode="commercial",
        )

        self.assertEqual(result.status, "failed")
        self.assertIn(
            "Commercial-use rule has not been recorded.",
            result.assets[0].errors,
        )

    def test_duplicate_asset_id_is_error(self) -> None:
        first_asset = self.make_asset()
        second_asset = self.make_asset()

        result = validate_registry(
            self.make_registry(
                [
                    first_asset,
                    second_asset,
                ]
            ),
            self.project_root,
        )

        self.assertEqual(result.status, "failed")
        self.assertIn(
            "Duplicate asset id: test_character",
            result.assets[1].errors,
        )


if __name__ == "__main__":
    unittest.main()
