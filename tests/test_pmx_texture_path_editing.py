"""Tests for safe pure indexed PMX texture-path editing."""

from __future__ import annotations

import io
import unittest
from dataclasses import replace

from mmd_registry.pmx import load_pmx, serialize_pmx, validate_pmx_document
from mmd_registry.pmx.editing import (
    PmxEditAudit,
    PmxEditPlanError,
    SetModelInfo,
    SetTexturePath,
    apply_set_model_info,
    apply_set_texture_path,
    validate_portable_texture_path,
)
from tests.mmd_fixtures import build_pmx_bone, build_pmx_structure


def load_document(
    *,
    encoding_flag: int = 1,
    texture_paths: tuple[str, ...] = (
        "textures/body.png",
        "textures/face.png",
        "textures/toon.bmp",
    ),
):
    """Return one complete generated PMX with indexed texture entries."""

    return load_pmx(
        io.BytesIO(
            build_pmx_structure(
                encoding_flag=encoding_flag,
                texture_paths=texture_paths,
                bones=(build_pmx_bone(encoding_flag=encoding_flag),),
            )
        )
    )


class TexturePathPolicyTests(unittest.TestCase):
    """Validate portable policy without path rewriting or filesystem access."""

    def test_accepts_relative_separator_forms_without_normalizing(self) -> None:
        paths = (
            "textures/body.png",
            r"textures\body.png",
            r"textures\characters/body.png",
            "テクスチャ/顔.png",
        )

        for path in paths:
            with self.subTest(path=path):
                self.assertIsNone(validate_portable_texture_path(path))

    def test_rejects_empty_and_nul_paths(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot be empty"):
            validate_portable_texture_path("")
        with self.assertRaisesRegex(ValueError, "NUL"):
            validate_portable_texture_path("textures/body\x00.png")

    def test_rejects_absolute_rooted_and_drive_qualified_paths(self) -> None:
        paths = (
            "/opt/models/body.png",
            r"\textures\body.png",
            r"C:\models\body.png",
            r"C:models\body.png",
            r"\\server\share\body.png",
        )

        for path in paths:
            with self.subTest(path=path):
                with self.assertRaisesRegex(ValueError, "portable and relative"):
                    validate_portable_texture_path(path)

    def test_rejects_parent_directory_components_for_both_separators(self) -> None:
        paths = (
            "../body.png",
            "textures/../body.png",
            r"..\body.png",
            r"textures\..\body.png",
        )

        for path in paths:
            with self.subTest(path=path):
                with self.assertRaisesRegex(ValueError, "parent-directory"):
                    validate_portable_texture_path(path)

    def test_policy_rejects_non_string_without_coercion(self) -> None:
        with self.assertRaisesRegex(TypeError, "must be a string"):
            validate_portable_texture_path(123)  # type: ignore[arg-type]


class PmxTexturePathEditingTests(unittest.TestCase):
    """Validate indexed immutable replacement, auditing, and PMX encoding."""

    def test_replaces_one_existing_path_with_exact_audit(self) -> None:
        source = load_document()

        result = apply_set_texture_path(
            source,
            SetTexturePath(texture_index=1, path="textures/new-face.png"),
            operation_index=4,
        )

        self.assertEqual(
            result.document.texture_paths,
            (
                "textures/body.png",
                "textures/new-face.png",
                "textures/toon.bmp",
            ),
        )
        self.assertEqual(result.audit.changed_fields, 1)
        change = result.audit.changes[0]
        self.assertEqual(change.category, "texture")
        self.assertEqual(change.target_index, 1)
        self.assertEqual(change.target_name, "textures/face.png")
        self.assertEqual(change.field_path, "textures[1].path")
        self.assertEqual(change.before, "textures/face.png")
        self.assertEqual(change.after, "textures/new-face.png")
        self.assertEqual(change.operation_index, 4)

    def test_source_order_count_and_material_references_remain_unchanged(self) -> None:
        source = load_document()
        source_bytes = serialize_pmx(source)

        result = apply_set_texture_path(
            source,
            SetTexturePath(texture_index=1, path=r"textures\new-face.png"),
        )

        self.assertEqual(serialize_pmx(source), source_bytes)
        self.assertEqual(
            source.texture_paths,
            (
                "textures/body.png",
                "textures/face.png",
                "textures/toon.bmp",
            ),
        )
        self.assertEqual(len(result.document.texture_paths), len(source.texture_paths))
        self.assertEqual(result.document.texture_paths[0], source.texture_paths[0])
        self.assertEqual(result.document.texture_paths[2], source.texture_paths[2])
        self.assertIs(result.document.materials, source.materials)
        self.assertEqual(result.document.materials, source.materials)
        validate_pmx_document(result.document)

    def test_noop_returns_source_without_fake_change(self) -> None:
        source = load_document()

        result = apply_set_texture_path(
            source,
            SetTexturePath(texture_index=0, path=source.texture_paths[0]),
        )

        self.assertIs(result.document, source)
        self.assertEqual(result.audit, PmxEditAudit())

    def test_invalid_texture_index_has_operation_context(self) -> None:
        source = load_document()

        with self.assertRaisesRegex(
            PmxEditPlanError,
            r"operations\[3\]\.texture_index.*index 3 is out of range.*3 textures",
        ) as context:
            apply_set_texture_path(
                source,
                SetTexturePath(texture_index=3, path="textures/new.png"),
                operation_index=3,
            )

        self.assertEqual(context.exception.operation_index, 3)
        self.assertEqual(context.exception.field, "texture_index")

    def test_path_policy_failure_has_operation_context(self) -> None:
        source = load_document()

        for invalid_path in (
            "",
            "textures/body\x00.png",
            r"C:\models\body.png",
            "../body.png",
        ):
            with self.subTest(invalid_path=invalid_path):
                with self.assertRaisesRegex(
                    PmxEditPlanError,
                    r"operations\[2\]\.path",
                ):
                    apply_set_texture_path(
                        source,
                        SetTexturePath(texture_index=0, path=invalid_path),
                        operation_index=2,
                    )

        self.assertEqual(source.texture_paths[0], "textures/body.png")

    def test_unicode_paths_roundtrip_in_utf8_and_utf16(self) -> None:
        for encoding_flag in (0, 1):
            with self.subTest(encoding_flag=encoding_flag):
                source = load_document(encoding_flag=encoding_flag)
                result = apply_set_texture_path(
                    source,
                    SetTexturePath(
                        texture_index=0,
                        path="テクスチャ/顔🌸.png",
                    ),
                )

                reparsed = load_pmx(io.BytesIO(serialize_pmx(result.document)))
                self.assertEqual(reparsed, result.document)

    def test_unencodable_path_has_operation_context(self) -> None:
        source = load_document()

        with self.assertRaisesRegex(
            PmxEditPlanError,
            r"operations\[5\]\.path.*cannot be encoded",
        ):
            apply_set_texture_path(
                source,
                SetTexturePath(texture_index=0, path="textures/\ud800.png"),
                operation_index=5,
            )

    def test_existing_unsafe_path_is_not_rewritten_by_other_edits(self) -> None:
        source = load_document()
        unsafe_paths = (r"C:\private\body.png", *source.texture_paths[1:])
        source_with_unsafe_path = replace(source, texture_paths=unsafe_paths)

        result = apply_set_model_info(
            source_with_unsafe_path,
            SetModelInfo(local_comments="Metadata only"),
        )

        self.assertEqual(result.document.texture_paths, unsafe_paths)
        self.assertIs(
            result.document.texture_paths,
            source_with_unsafe_path.texture_paths,
        )

    def test_explicit_noop_of_existing_unsafe_path_is_rejected(self) -> None:
        source = load_document()
        unsafe_path = r"C:\private\body.png"
        source = replace(
            source,
            texture_paths=(unsafe_path, *source.texture_paths[1:]),
        )

        with self.assertRaisesRegex(PmxEditPlanError, r"operations\[0\]\.path"):
            apply_set_texture_path(
                source,
                SetTexturePath(texture_index=0, path=unsafe_path),
            )

    def test_rejects_wrong_argument_types_and_operation_index(self) -> None:
        source = load_document()
        operation = SetTexturePath(texture_index=0, path="textures/new.png")

        with self.assertRaisesRegex(TypeError, "PmxDocument"):
            apply_set_texture_path(object(), operation)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "SetTexturePath"):
            apply_set_texture_path(
                source,
                SetModelInfo(local_name="Wrong operation"),  # type: ignore[arg-type]
            )
        with self.assertRaisesRegex(TypeError, "operation_index"):
            apply_set_texture_path(
                source,
                operation,
                operation_index=True,  # type: ignore[arg-type]
            )
        with self.assertRaisesRegex(ValueError, "cannot be negative"):
            apply_set_texture_path(source, operation, operation_index=-1)


if __name__ == "__main__":
    unittest.main()
