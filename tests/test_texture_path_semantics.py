from __future__ import annotations

import unittest

from mmd_registry.texture_path_semantics import TexturePathKind, analyze_texture_path


class TexturePathSemanticsTests(unittest.TestCase):
    def test_host_independent_classification_matrix(self) -> None:
        cases = (
            ("", TexturePathKind.EMPTY, ""),
            ("textures/body.png", TexturePathKind.RELATIVE, "textures/body.png"),
            (r"textures\body.png", TexturePathKind.RELATIVE, "textures/body.png"),
            (r"textures\characters/body.png", TexturePathKind.RELATIVE, "textures/characters/body.png"),
            ("textures/./body.png", TexturePathKind.RELATIVE, "textures/body.png"),
            ("../body.png", TexturePathKind.RELATIVE, "../body.png"),
            (r"C:\models\body.png", TexturePathKind.WINDOWS_ABSOLUTE, "C:/models/body.png"),
            (r"C:models\body.png", TexturePathKind.WINDOWS_DRIVE_RELATIVE, "C:models/body.png"),
            (r"\textures\body.png", TexturePathKind.WINDOWS_ROOTED, "/textures/body.png"),
            (r"\\server\share\body.png", TexturePathKind.WINDOWS_UNC, "//server/share/body.png"),
            ("/opt/models/body.png", TexturePathKind.POSIX_ABSOLUTE, "/opt/models/body.png"),
            ("テクスチャ/顔 01.png", TexturePathKind.RELATIVE, "テクスチャ/顔 01.png"),
            ("textures//body.png", TexturePathKind.RELATIVE, "textures/body.png"),
        )
        for declared, expected_kind, expected_normalized in cases:
            with self.subTest(declared=declared):
                analysis = analyze_texture_path(declared)
                self.assertEqual(analysis.declared_path, declared)
                self.assertEqual(analysis.kind, expected_kind)
                self.assertEqual(analysis.normalized_path, expected_normalized)

    def test_parent_current_and_separator_facts_are_independent(self) -> None:
        parent = analyze_texture_path(r"textures\sub/../body.png")
        self.assertTrue(parent.contains_parent_reference)
        self.assertTrue(parent.mixed_separators)

        current = analyze_texture_path("textures/./body.png")
        self.assertTrue(current.contains_current_reference)
        self.assertFalse(current.contains_parent_reference)

    def test_nul_is_lexical_fact_without_filesystem_access(self) -> None:
        analysis = analyze_texture_path("textures/body\x00.png")
        self.assertTrue(analysis.contains_nul)
        self.assertEqual(analysis.declared_path, "textures/body\x00.png")

    def test_rejects_non_string_without_coercion(self) -> None:
        with self.assertRaisesRegex(TypeError, "must be a string"):
            analyze_texture_path(123)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
