"""Tests for PMX texture dependency filesystem diagnostics."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from mmd_registry.dependency_diagnostics import (
    DependencyIssue,
    diagnose_texture_dependencies,
)


class TextureDependencyDiagnosticsTests(unittest.TestCase):
    """Tests for portable, read-only texture path diagnostics."""

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_directory.name)
        self.model_directory = self.project_root / "model"
        self.model_directory.mkdir()
        self.model_path = self.model_directory / "character.pmx"
        self.model_path.write_bytes(b"PMX fixture placeholder")

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def issue_codes(self, dependency_index: int, result: object) -> set[str]:
        """Return issue codes for one dependency result."""

        dependency = result.dependencies[dependency_index]
        return {issue.code for issue in dependency.issues}

    def write_texture(self, relative_path: str, data: bytes = b"texture") -> Path:
        """Create one texture file below the model directory."""

        texture = self.model_directory.joinpath(*relative_path.split("/"))
        texture.parent.mkdir(parents=True, exist_ok=True)
        texture.write_bytes(data)
        return texture

    def test_handles_zero_declared_textures(self) -> None:
        result = diagnose_texture_dependencies(self.model_path, ())

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.declared_texture_count, 0)
        self.assertEqual(result.dependencies, ())
        self.assertEqual(result.warning_count, 0)
        self.assertEqual(result.error_count, 0)

    def test_resolves_existing_relative_texture(self) -> None:
        texture = self.write_texture("textures/diffuse.png")

        result = diagnose_texture_dependencies(
            self.model_path,
            ("textures/diffuse.png",),
            (0,),
        )
        dependency = result.dependencies[0]

        self.assertEqual(result.status, "ok")
        self.assertTrue(dependency.is_referenced)
        self.assertTrue(dependency.exists)
        self.assertTrue(dependency.is_file)
        self.assertTrue(dependency.is_portable)
        self.assertEqual(dependency.resolved_path, texture.resolve().as_posix())
        self.assertEqual(dependency.issues, ())

    def test_normalizes_backslash_separators(self) -> None:
        self.write_texture("textures/body.png")

        result = diagnose_texture_dependencies(
            self.model_path,
            (r"textures\body.png",),
            (0,),
        )
        dependency = result.dependencies[0]

        self.assertEqual(dependency.normalized_path, "textures/body.png")
        self.assertTrue(dependency.exists)
        self.assertEqual(dependency.status, "ok")

    def test_missing_referenced_texture_is_error(self) -> None:
        result = diagnose_texture_dependencies(
            self.model_path,
            ("textures/missing.png",),
            (0,),
        )

        self.assertEqual(result.status, "error")
        self.assertEqual(result.missing_file_count, 1)
        self.assertEqual(result.error_count, 1)
        self.assertIn("missing_file", self.issue_codes(0, result))

    def test_missing_unreferenced_texture_is_warning(self) -> None:
        result = diagnose_texture_dependencies(
            self.model_path,
            ("textures/unused-missing.png",),
        )

        self.assertEqual(result.status, "warning")
        self.assertEqual(result.warning_count, 1)
        self.assertEqual(result.error_count, 0)
        issue = result.dependencies[0].issues[0]
        self.assertEqual(issue.code, "missing_file")
        self.assertEqual(issue.severity, "warning")

    def test_existing_unreferenced_texture_is_not_an_issue(self) -> None:
        self.write_texture("textures/unused.png")

        result = diagnose_texture_dependencies(
            self.model_path,
            ("textures/unused.png",),
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.referenced_texture_count, 0)
        self.assertEqual(result.unreferenced_texture_count, 1)
        self.assertFalse(result.dependencies[0].is_referenced)

    def test_preserves_duplicate_texture_declarations(self) -> None:
        self.write_texture("textures/shared.png")

        result = diagnose_texture_dependencies(
            self.model_path,
            (
                "textures/shared.png",
                "textures/shared.png",
            ),
            (1,),
        )

        self.assertEqual(result.declared_texture_count, 2)
        self.assertEqual(len(result.dependencies), 2)
        self.assertFalse(result.dependencies[0].is_referenced)
        self.assertTrue(result.dependencies[1].is_referenced)
        self.assertEqual(result.existing_file_count, 2)

    def test_counts_referenced_and_unreferenced_indices(self) -> None:
        for name in ("a.png", "b.png", "c.png"):
            self.write_texture(f"textures/{name}")

        result = diagnose_texture_dependencies(
            self.model_path,
            (
                "textures/a.png",
                "textures/b.png",
                "textures/c.png",
            ),
            (0, 0, 2),
        )

        self.assertEqual(result.referenced_texture_count, 2)
        self.assertEqual(result.unreferenced_texture_count, 1)

    def test_absolute_native_path_is_non_portable(self) -> None:
        texture = self.project_root / "absolute.png"
        texture.write_bytes(b"texture")

        result = diagnose_texture_dependencies(
            self.model_path,
            (str(texture.resolve()),),
            (0,),
        )
        dependency = result.dependencies[0]

        self.assertTrue(dependency.is_absolute)
        self.assertFalse(dependency.is_portable)
        self.assertEqual(result.absolute_path_count, 1)
        self.assertIn("absolute_path", self.issue_codes(0, result))

    def test_windows_absolute_path_is_recognized_cross_platform(self) -> None:
        result = diagnose_texture_dependencies(
            self.model_path,
            (r"C:\MMD\textures\body.png",),
            (0,),
        )
        dependency = result.dependencies[0]

        self.assertTrue(dependency.is_absolute)
        self.assertFalse(dependency.is_portable)
        self.assertEqual(
            dependency.normalized_path,
            "C:/MMD/textures/body.png",
        )
        self.assertIn("absolute_path", self.issue_codes(0, result))

    def test_unc_path_is_recognized_as_absolute(self) -> None:
        result = diagnose_texture_dependencies(
            self.model_path,
            (r"\\server\share\toon.bmp",),
        )

        self.assertTrue(result.dependencies[0].is_absolute)
        self.assertFalse(result.dependencies[0].is_portable)
        self.assertIn("absolute_path", self.issue_codes(0, result))

    def test_parent_reference_that_stays_inside_is_portable(self) -> None:
        self.write_texture("textures/body.png")

        result = diagnose_texture_dependencies(
            self.model_path,
            ("textures/sub/../body.png",),
            (0,),
        )
        dependency = result.dependencies[0]

        self.assertTrue(dependency.contains_parent_reference)
        self.assertFalse(dependency.outside_model_directory)
        self.assertTrue(dependency.is_portable)
        self.assertTrue(dependency.exists)

    def test_parent_reference_escape_is_reported(self) -> None:
        outside_texture = self.project_root / "shared.png"
        outside_texture.write_bytes(b"texture")

        result = diagnose_texture_dependencies(
            self.model_path,
            ("../shared.png",),
            (0,),
        )
        dependency = result.dependencies[0]

        self.assertTrue(dependency.contains_parent_reference)
        self.assertTrue(dependency.outside_model_directory)
        self.assertFalse(dependency.is_portable)
        self.assertTrue(dependency.exists)
        self.assertIn(
            "outside_model_directory",
            self.issue_codes(0, result),
        )

    def test_empty_referenced_path_is_error(self) -> None:
        result = diagnose_texture_dependencies(
            self.model_path,
            ("",),
            (0,),
        )
        dependency = result.dependencies[0]

        self.assertEqual(result.status, "error")
        self.assertIsNone(dependency.resolved_path)
        self.assertIsNone(dependency.exists)
        self.assertFalse(dependency.is_portable)
        self.assertIn("empty_path", self.issue_codes(0, result))

    def test_existing_directory_is_rejected_as_texture_file(self) -> None:
        texture_directory = self.model_directory / "textures"
        texture_directory.mkdir()

        result = diagnose_texture_dependencies(
            self.model_path,
            ("textures",),
            (0,),
        )
        dependency = result.dependencies[0]

        self.assertTrue(dependency.exists)
        self.assertFalse(dependency.is_file)
        self.assertEqual(dependency.status, "error")
        self.assertIn("not_a_file", self.issue_codes(0, result))

    def test_supports_unicode_texture_paths(self) -> None:
        self.write_texture("テクスチャ/体.png")

        result = diagnose_texture_dependencies(
            self.model_path,
            ("テクスチャ/体.png",),
            (0,),
        )

        self.assertEqual(result.status, "ok")
        self.assertTrue(result.dependencies[0].exists)

    def test_result_is_json_serializable(self) -> None:
        self.write_texture("textures/body.png")
        result = diagnose_texture_dependencies(
            self.model_path,
            ("textures/body.png", "textures/missing.png"),
            (0, 1),
        )

        payload = result.to_dict()
        encoded = json.dumps(payload, ensure_ascii=False)
        decoded = json.loads(encoded)

        self.assertEqual(decoded["declared_texture_count"], 2)
        self.assertEqual(decoded["dependencies"][0]["status"], "ok")
        self.assertEqual(decoded["dependencies"][1]["status"], "error")

    def test_rejects_negative_reference_index(self) -> None:
        with self.assertRaisesRegex(ValueError, "outside"):
            diagnose_texture_dependencies(
                self.model_path,
                ("texture.png",),
                (-1,),
            )

    def test_rejects_reference_index_past_declared_range(self) -> None:
        with self.assertRaisesRegex(ValueError, "outside"):
            diagnose_texture_dependencies(
                self.model_path,
                ("texture.png",),
                (1,),
            )

    def test_rejects_non_integer_reference_index(self) -> None:
        with self.assertRaisesRegex(TypeError, "integers"):
            diagnose_texture_dependencies(
                self.model_path,
                ("texture.png",),
                (True,),
            )

    def test_rejects_non_string_texture_path(self) -> None:
        with self.assertRaisesRegex(TypeError, "strings"):
            diagnose_texture_dependencies(
                self.model_path,
                (123,),  # type: ignore[arg-type]
            )

    def test_issue_rejects_unknown_severity(self) -> None:
        with self.assertRaisesRegex(ValueError, "severity"):
            DependencyIssue(
                code="test",
                severity="info",
                message="Unsupported severity",
            )


if __name__ == "__main__":
    unittest.main()
