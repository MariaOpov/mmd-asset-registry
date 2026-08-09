"""Tests for immutable PMX document-model foundations."""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from mmd_registry.pmx import (
    PmxHeader,
    PmxIndexSizes,
    PmxModelInfo,
)


def standard_index_sizes() -> PmxIndexSizes:
    """Return one valid mixed-width PMX index configuration."""

    return PmxIndexSizes(
        vertex=4,
        texture=1,
        material=2,
        bone=2,
        morph=1,
        rigid_body=4,
    )


class PmxDocumentFoundationTests(unittest.TestCase):
    """Validate the header-level PMX domain model."""

    def test_index_sizes_accept_every_supported_width(self) -> None:
        for size in (1, 2, 4):
            with self.subTest(size=size):
                index_sizes = PmxIndexSizes(
                    vertex=size,
                    texture=size,
                    material=size,
                    bone=size,
                    morph=size,
                    rigid_body=size,
                )

                self.assertEqual(index_sizes.vertex, size)

    def test_index_sizes_reject_invalid_widths_and_booleans(self) -> None:
        for value in (0, 3, 8, True):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "vertex index size"):
                    PmxIndexSizes(
                        vertex=value,
                        texture=1,
                        material=1,
                        bone=1,
                        morph=1,
                        rigid_body=1,
                    )

    def test_header_preserves_byte_relevant_settings(self) -> None:
        header = PmxHeader(
            version=2.1,
            encoding="utf-8",
            additional_uv_count=4,
            index_sizes=standard_index_sizes(),
            extra_global_data=b"\xAA\x55",
        )

        self.assertEqual(header.version, 2.1)
        self.assertEqual(header.encoding_flag, 1)
        self.assertEqual(header.global_count, 10)
        self.assertEqual(header.extra_global_data, b"\xAA\x55")

    def test_utf16_header_uses_zero_encoding_flag(self) -> None:
        header = PmxHeader(
            version=2.0,
            encoding="utf-16-le",
            additional_uv_count=0,
            index_sizes=standard_index_sizes(),
        )

        self.assertEqual(header.encoding_flag, 0)
        self.assertEqual(header.global_count, 8)

    def test_header_rejects_invalid_versions(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported PMX version"):
            PmxHeader(
                version=2.2,  # type: ignore[arg-type]
                encoding="utf-8",
                additional_uv_count=0,
                index_sizes=standard_index_sizes(),
            )

        with self.assertRaisesRegex(TypeError, "version must be a float"):
            PmxHeader(
                version=2,  # type: ignore[arg-type]
                encoding="utf-8",
                additional_uv_count=0,
                index_sizes=standard_index_sizes(),
            )

    def test_header_rejects_invalid_encoding(self) -> None:
        with self.assertRaisesRegex(ValueError, "text encoding"):
            PmxHeader(
                version=2.0,
                encoding="shift-jis",  # type: ignore[arg-type]
                additional_uv_count=0,
                index_sizes=standard_index_sizes(),
            )

    def test_header_rejects_invalid_additional_uv_counts(self) -> None:
        for value in (-1, 5):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "between 0 and 4"):
                    PmxHeader(
                        version=2.0,
                        encoding="utf-8",
                        additional_uv_count=value,
                        index_sizes=standard_index_sizes(),
                    )

        with self.assertRaisesRegex(TypeError, "must be an integer"):
            PmxHeader(
                version=2.0,
                encoding="utf-8",
                additional_uv_count=True,
                index_sizes=standard_index_sizes(),
            )

    def test_header_rejects_mutable_or_oversized_extra_globals(self) -> None:
        with self.assertRaisesRegex(TypeError, "immutable bytes"):
            PmxHeader(
                version=2.0,
                encoding="utf-8",
                additional_uv_count=0,
                index_sizes=standard_index_sizes(),
                extra_global_data=bytearray(b"\x00"),  # type: ignore[arg-type]
            )

        with self.assertRaisesRegex(ValueError, "global count 65"):
            PmxHeader(
                version=2.0,
                encoding="utf-8",
                additional_uv_count=0,
                index_sizes=standard_index_sizes(),
                extra_global_data=b"\x00" * 57,
            )

    def test_model_info_preserves_unicode_and_multiline_text(self) -> None:
        model_info = PmxModelInfo(
            local_name="モデル",
            universal_name="Model",
            local_comments="一行目\n二行目",
            universal_comments="Line one\nLine two",
        )

        self.assertEqual(model_info.local_name, "モデル")
        self.assertEqual(model_info.local_comments, "一行目\n二行目")

    def test_model_info_rejects_non_string_fields(self) -> None:
        with self.assertRaisesRegex(TypeError, "local_name must be a string"):
            PmxModelInfo(
                local_name=None,  # type: ignore[arg-type]
                universal_name="Model",
                local_comments="",
                universal_comments="",
            )

    def test_foundation_models_are_immutable(self) -> None:
        index_sizes = standard_index_sizes()
        header = PmxHeader(
            version=2.0,
            encoding="utf-8",
            additional_uv_count=0,
            index_sizes=index_sizes,
        )
        model_info = PmxModelInfo("Local", "Universal", "", "")

        with self.assertRaises(FrozenInstanceError):
            index_sizes.vertex = 2  # type: ignore[misc]

        with self.assertRaises(FrozenInstanceError):
            header.version = 2.1  # type: ignore[misc]

        with self.assertRaises(FrozenInstanceError):
            model_info.local_name = "Changed"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
