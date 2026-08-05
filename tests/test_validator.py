"""Tests for supported registry schemas and asset validation."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from typing import Any

from mmd_registry.validator import validate_registry
from tests.mmd_fixtures import build_minimal_pmx_header


class RegistryValidatorTests(unittest.TestCase):
    """Tests for registry and usage-mode validation."""

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_directory.name)

        model_file = self.project_root / "model.pmx"
        model_file.write_bytes(build_minimal_pmx_header("Validator Fixture"))

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
        registry_version: str = "0.2",
    ) -> dict[str, Any]:
        return {
            "registry_version": registry_version,
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

    def test_schema_0_2_remains_supported(self) -> None:
        registry = self.make_registry([self.make_asset()])

        result = validate_registry(
            registry,
            self.project_root,
            mode="private",
        )

        self.assertEqual(result.status, "passed")
        self.assertIn(
            (
                "Registry schema 0.2 is supported for backward "
                "compatibility; latest is 0.3."
            ),
            result.registry_infos,
        )

    def test_schema_0_3_is_supported(self) -> None:
        registry = self.make_registry(
            [self.make_asset()],
            registry_version="0.3",
        )

        result = validate_registry(
            registry,
            self.project_root,
            mode="private",
        )

        self.assertEqual(result.status, "passed")
        self.assertEqual(result.error_count, 0)
        self.assertFalse(
            any(
                "backward compatibility" in message for message in result.registry_infos
            )
        )

    def test_unknown_schema_version_is_error(self) -> None:
        registry = self.make_registry(
            [self.make_asset()],
            registry_version="9.9",
        )

        result = validate_registry(
            registry,
            self.project_root,
            mode="private",
        )

        self.assertEqual(result.status, "failed")
        self.assertIn(
            ("Unsupported registry_version '9.9'. Supported versions: 0.2, 0.3."),
            result.registry_errors,
        )

    def test_schema_0_3_matching_sha256_passes(self) -> None:
        asset = self.make_asset()
        model_file = self.project_root / "model.pmx"
        expected_sha256 = hashlib.sha256(model_file.read_bytes()).hexdigest()
        asset["integrity"] = {"sha256": expected_sha256.upper()}

        result = validate_registry(
            self.make_registry([asset], registry_version="0.3"),
            self.project_root,
        )

        asset_result = result.assets[0]
        self.assertEqual(result.status, "passed")
        self.assertIsNotNone(asset_result.integrity)
        assert asset_result.integrity is not None
        self.assertEqual(asset_result.integrity.status, "matched")
        self.assertEqual(asset_result.integrity.expected, expected_sha256)
        self.assertEqual(asset_result.integrity.actual, expected_sha256)
        self.assertEqual(
            asset_result.integrity.size_bytes,
            model_file.stat().st_size,
        )
        self.assertIsNotNone(asset_result.inspection)
        assert asset_result.inspection is not None
        self.assertEqual(asset_result.inspection.status, "ok")
        self.assertEqual(asset_result.inspection.detected_format, "pmx")
        self.assertEqual(
            asset_result.inspection.model_name,
            "Validator Fixture",
        )

    def test_schema_0_3_mismatched_sha256_is_error(self) -> None:
        asset = self.make_asset()
        asset["integrity"] = {"sha256": "0" * 64}

        result = validate_registry(
            self.make_registry([asset], registry_version="0.3"),
            self.project_root,
        )

        asset_result = result.assets[0]
        self.assertEqual(result.status, "failed")
        self.assertIsNotNone(asset_result.integrity)
        assert asset_result.integrity is not None
        self.assertEqual(asset_result.integrity.status, "mismatched")
        self.assertIn(
            "SHA-256 mismatch: registered hash does not match the source file.",
            asset_result.errors,
        )

    def test_schema_0_3_invalid_sha256_is_error(self) -> None:
        asset = self.make_asset()
        asset["integrity"] = {"sha256": "invalid-hash"}

        result = validate_registry(
            self.make_registry([asset], registry_version="0.3"),
            self.project_root,
        )

        asset_result = result.assets[0]
        self.assertEqual(result.status, "failed")
        self.assertIsNotNone(asset_result.integrity)
        assert asset_result.integrity is not None
        self.assertEqual(asset_result.integrity.status, "invalid_expected")
        self.assertIn(
            ("integrity.sha256 must be a 64-character hexadecimal string or null."),
            asset_result.errors,
        )

    def test_schema_0_3_missing_sha256_is_informational(self) -> None:
        asset = self.make_asset()

        result = validate_registry(
            self.make_registry([asset], registry_version="0.3"),
            self.project_root,
        )

        asset_result = result.assets[0]
        self.assertEqual(result.status, "passed")
        self.assertIsNotNone(asset_result.integrity)
        assert asset_result.integrity is not None
        self.assertEqual(asset_result.integrity.status, "not_recorded")
        self.assertIn(
            "SHA-256 hash has not been recorded.",
            asset_result.infos,
        )

    def test_schema_0_3_integrity_must_be_mapping(self) -> None:
        asset = self.make_asset()
        asset["integrity"] = "not-a-mapping"

        result = validate_registry(
            self.make_registry([asset], registry_version="0.3"),
            self.project_root,
        )

        asset_result = result.assets[0]
        self.assertEqual(result.status, "failed")
        self.assertIsNotNone(asset_result.integrity)
        assert asset_result.integrity is not None
        self.assertEqual(asset_result.integrity.status, "invalid_expected")
        self.assertIn("integrity must be a YAML object.", asset_result.errors)

    def test_schema_0_2_does_not_apply_integrity_rules(self) -> None:
        asset = self.make_asset()
        asset["integrity"] = {"sha256": "invalid-hash"}

        result = validate_registry(
            self.make_registry([asset], registry_version="0.2"),
            self.project_root,
        )

        self.assertEqual(result.status, "passed")
        self.assertIsNone(result.assets[0].integrity)
        self.assertIsNone(result.assets[0].inspection)

    def test_private_zero_byte_placeholder_is_warning(self) -> None:
        model_file = self.project_root / "model.pmx"
        model_file.write_bytes(b"")
        asset = self.make_asset()
        asset["tags"].append("placeholder")
        asset["integrity"] = {
            "sha256": hashlib.sha256(b"").hexdigest(),
        }

        result = validate_registry(
            self.make_registry([asset], registry_version="0.3"),
            self.project_root,
            mode="private",
        )

        asset_result = result.assets[0]
        self.assertEqual(result.status, "passed_with_warnings")
        self.assertEqual(asset_result.errors, [])
        self.assertIsNotNone(asset_result.inspection)
        assert asset_result.inspection is not None
        self.assertEqual(asset_result.inspection.status, "error")
        self.assertTrue(
            any(
                message.startswith("Placeholder model header inspection failed:")
                for message in asset_result.warnings
            )
        )

    def test_publish_zero_byte_placeholder_is_error(self) -> None:
        model_file = self.project_root / "model.pmx"
        model_file.write_bytes(b"")
        asset = self.make_asset()
        asset["tags"].append("placeholder")
        asset["integrity"] = {
            "sha256": hashlib.sha256(b"").hexdigest(),
        }

        result = validate_registry(
            self.make_registry([asset], registry_version="0.3"),
            self.project_root,
            mode="publish",
        )

        asset_result = result.assets[0]
        self.assertEqual(result.status, "failed")
        self.assertTrue(
            any(
                message.startswith("Model header inspection failed:")
                for message in asset_result.errors
            )
        )

    def test_private_invalid_non_placeholder_model_is_error(self) -> None:
        model_file = self.project_root / "model.pmx"
        model_file.write_bytes(b"not a PMX model")
        asset = self.make_asset()
        asset["integrity"] = {
            "sha256": hashlib.sha256(model_file.read_bytes()).hexdigest(),
        }

        result = validate_registry(
            self.make_registry([asset], registry_version="0.3"),
            self.project_root,
            mode="private",
        )

        asset_result = result.assets[0]
        self.assertEqual(result.status, "failed")
        self.assertTrue(
            any(
                message.startswith("Model header inspection failed:")
                for message in asset_result.errors
            )
        )


if __name__ == "__main__":
    unittest.main()
