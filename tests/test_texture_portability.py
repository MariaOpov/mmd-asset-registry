from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mmd_registry.texture_portability import (
    TexturePortabilityIssueCode,
    analyze_texture_portability,
)


class TexturePortabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_directory.name)
        self.model_directory = self.project_root / "model"
        self.model_directory.mkdir()
        self.model_path = self.model_directory / "character.pmx"
        self.model_bytes = b"PMX portability sentinel"
        self.model_path.write_bytes(self.model_bytes)

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def write_texture(self, relative_path: str, data: bytes = b"texture") -> Path:
        path = self.model_directory.joinpath(*relative_path.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def issue_codes(self, entry_index: int, report: object) -> tuple[str, ...]:
        return report.entries[entry_index].issue_codes

    def test_existing_relative_path_has_deterministic_candidate(self) -> None:
        texture = self.write_texture("textures/body.png")
        before = texture.read_bytes()

        report = analyze_texture_portability(
            self.model_path,
            ("textures/body.png",),
            (0,),
        )
        entry = report.entries[0]

        self.assertTrue(entry.portable)
        self.assertEqual(entry.candidate_path, "textures/body.png")
        self.assertEqual(entry.declared_path, "textures/body.png")
        self.assertTrue(entry.is_referenced)
        self.assertEqual(entry.issue_codes, ())
        self.assertEqual(texture.read_bytes(), before)
        self.assertEqual(self.model_path.read_bytes(), self.model_bytes)

    def test_backslash_mixed_dot_and_repeated_separators_normalize_separately(self) -> None:
        self.write_texture("textures/body.png")
        declarations = (
            r"textures\body.png",
            r"textures\./body.png",
            "textures//body.png",
        )
        report = analyze_texture_portability(self.model_path, declarations)

        self.assertEqual(
            tuple(entry.declared_path for entry in report.entries),
            declarations,
        )
        self.assertEqual(
            tuple(entry.candidate_path for entry in report.entries),
            ("textures/body.png", "textures/body.png", "textures/body.png"),
        )

    def test_parent_reference_is_not_a_candidate_even_when_target_stays_inside(self) -> None:
        self.write_texture("textures/body.png")
        report = analyze_texture_portability(
            self.model_path,
            ("textures/sub/../body.png",),
        )
        entry = report.entries[0]

        self.assertFalse(entry.portable)
        self.assertIsNone(entry.candidate_path)
        self.assertIn(
            TexturePortabilityIssueCode.PARENT_REFERENCE.value,
            entry.issue_codes,
        )
        self.assertFalse(entry.filesystem.outside_model_directory)

    def test_parent_escape_is_reported_without_candidate(self) -> None:
        outside = self.project_root / "outside.png"
        outside.write_bytes(b"outside")
        report = analyze_texture_portability(self.model_path, ("../outside.png",))
        entry = report.entries[0]

        self.assertFalse(entry.portable)
        self.assertIsNone(entry.candidate_path)
        self.assertIn("parent_reference", entry.issue_codes)
        self.assertIn("outside_model_directory", entry.issue_codes)

    def test_missing_and_directory_targets_have_no_candidate(self) -> None:
        (self.model_directory / "textures").mkdir()

        report = analyze_texture_portability(
            self.model_path,
            ("textures/missing.png", "textures"),
        )

        self.assertIn("missing_file", report.entries[0].issue_codes)
        self.assertIsNone(report.entries[0].candidate_path)
        self.assertIn("not_a_file", report.entries[1].issue_codes)
        self.assertIsNone(report.entries[1].candidate_path)

    def test_exact_component_spelling_is_required_even_if_host_lookup_succeeds(self) -> None:
        self.write_texture("textures/body.png")

        with (
            mock.patch.object(Path, "exists", return_value=True),
            mock.patch.object(Path, "is_file", return_value=True),
        ):
            report = analyze_texture_portability(
                self.model_path,
                ("textures/BODY.PNG",),
            )

        entry = report.entries[0]
        self.assertFalse(entry.filesystem.exists)
        self.assertFalse(entry.filesystem.is_file)
        self.assertIn("missing_file", entry.issue_codes)
        self.assertIsNone(entry.candidate_path)

    def test_exact_spelling_check_collapses_bounded_parent_components(self) -> None:
        self.write_texture("textures/body.png")

        report = analyze_texture_portability(
            self.model_path,
            ("textures/sub/../body.png",),
        )

        entry = report.entries[0]
        self.assertTrue(entry.filesystem.exists)
        self.assertTrue(entry.filesystem.is_file)
        self.assertFalse(entry.filesystem.outside_model_directory)
        self.assertIn("parent_reference", entry.issue_codes)
        self.assertIsNone(entry.candidate_path)

    def test_absolute_rooted_unc_drive_empty_nul_are_lexically_stable(self) -> None:
        declarations = (
            "",
            "textures/body\x00.png",
            r"C:\models\body.png",
            r"C:models\body.png",
            r"\textures\body.png",
            r"\\server\share\body.png",
            "/opt/models/body.png",
        )
        report = analyze_texture_portability(self.model_path, declarations)

        self.assertIn("empty_path", report.entries[0].issue_codes)
        self.assertIn("nul_character", report.entries[1].issue_codes)
        self.assertIn("absolute_path", report.entries[2].issue_codes)
        self.assertIn("rooted_path", report.entries[3].issue_codes)
        self.assertIn("rooted_path", report.entries[4].issue_codes)
        self.assertIn("absolute_path", report.entries[5].issue_codes)
        self.assertIn("absolute_path", report.entries[6].issue_codes)

        for entry in report.entries:
            self.assertIsNone(entry.candidate_path)

    def test_unicode_spaces_and_json_shape_are_stable(self) -> None:
        self.write_texture("テクスチャ/顔 01.png")
        report = analyze_texture_portability(
            self.model_path,
            ("テクスチャ/顔 01.png",),
        )
        encoded = json.dumps(report.to_dict(), ensure_ascii=False, allow_nan=False)
        decoded = json.loads(encoded)

        self.assertEqual(decoded["entries"][0]["declared_path"], "テクスチャ/顔 01.png")
        self.assertEqual(decoded["entries"][0]["candidate_path"], "テクスチャ/顔 01.png")

    def test_rejects_invalid_reference_indices_and_texture_types(self) -> None:
        with self.assertRaisesRegex(ValueError, "outside"):
            analyze_texture_portability(self.model_path, ("a.png",), (-1,))
        with self.assertRaisesRegex(TypeError, "integers"):
            analyze_texture_portability(self.model_path, ("a.png",), (True,))
        with self.assertRaisesRegex(TypeError, "strings"):
            analyze_texture_portability(
                self.model_path,
                (123,),  # type: ignore[arg-type]
            )


if __name__ == "__main__":
    unittest.main()
