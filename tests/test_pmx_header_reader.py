"""Tests for the standalone typed PMX header reader."""

from __future__ import annotations

import io
import math
import struct
import unittest
from dataclasses import FrozenInstanceError

from mmd_registry.binary_reader import BinaryParseError, BinaryReader
from mmd_registry.pmx.sections.header import (
    PmxHeaderReadResult,
    PmxHeaderReadState,
    read_pmx_header,
    read_pmx_header_body,
    read_pmx_magic,
    validate_pmx_magic,
)
from tests.mmd_fixtures import build_pmx_model_info


def read_header(data: bytes) -> tuple[PmxHeaderReadResult, int]:
    """Read one generated header and return its result and final offset."""

    stream = io.BytesIO(data)
    reader = BinaryReader(
        stream,
        format_name="PMX",
    )
    result = read_pmx_header(reader)
    return result, reader.offset


class PmxHeaderReaderTests(unittest.TestCase):
    """Validate typed header parsing independently from legacy scanning."""

    def test_reads_complete_utf8_header_and_preserves_extra_globals(self) -> None:
        data = build_pmx_model_info(
            local_name="モデル",
            universal_name="Model",
            local_comments="説明",
            universal_comments="Description",
            version=2.1,
            additional_uv_count=3,
            vertex_index_size=4,
            texture_index_size=1,
            material_index_size=2,
            bone_index_size=4,
            morph_index_size=1,
            rigid_body_index_size=2,
            extra_globals=b"\xAA\x55",
        )

        result, offset = read_header(data)

        self.assertEqual(result.magic, b"PMX ")
        self.assertEqual(result.header.version, 2.1)
        self.assertEqual(result.header.encoding, "utf-8")
        self.assertEqual(result.header.additional_uv_count, 3)
        self.assertEqual(result.header.index_sizes.vertex, 4)
        self.assertEqual(result.header.index_sizes.material, 2)
        self.assertEqual(result.header.extra_global_data, b"\xAA\x55")
        self.assertEqual(result.header.global_count, 10)
        self.assertEqual(result.model_info.local_name, "モデル")
        self.assertEqual(offset, len(data))
        self.assertEqual(
            result.warnings,
            (
                "PMX header contains 2 unrecognized extra "
                "global-setting bytes.",
            ),
        )

    def test_reads_utf16_model_information(self) -> None:
        data = build_pmx_model_info(
            local_name="ローカル",
            local_comments="コメント",
            encoding_flag=0,
        )

        result, _ = read_header(data)

        self.assertEqual(result.header.encoding, "utf-16-le")
        self.assertEqual(result.header.encoding_flag, 0)
        self.assertEqual(result.model_info.local_name, "ローカル")
        self.assertEqual(result.model_info.local_comments, "コメント")

    def test_empty_local_name_produces_the_legacy_warning(self) -> None:
        result, _ = read_header(
            build_pmx_model_info(
                local_name="",
            )
        )

        self.assertEqual(
            result.warnings,
            ("PMX local model name is empty.",),
        )

    def test_rejects_invalid_signature_with_context(self) -> None:
        data = b"BAD!" + build_pmx_model_info()[4:]

        with self.assertRaisesRegex(
            BinaryParseError,
            "invalid PMX magic/signature",
        ):
            read_header(data)

    def test_rejects_non_finite_and_unsupported_versions(self) -> None:
        for version, expected in (
            (math.inf, "finite floating-point number"),
            (3.0, "unsupported PMX version"),
        ):
            with self.subTest(version=version):
                data = bytearray(build_pmx_model_info())
                data[4:8] = struct.pack("<f", version)

                with self.assertRaisesRegex(BinaryParseError, expected):
                    read_header(bytes(data))

    def test_rejects_invalid_global_settings_with_legacy_wording(self) -> None:
        cases = (
            (
                {"encoding_flag": 9},
                "invalid PMX text-encoding flag: 9",
            ),
            (
                {"additional_uv_count": 5},
                "expected a value from 0 through 4",
            ),
            (
                {"vertex_index_size": 3},
                "invalid index size 3",
            ),
        )

        for kwargs, expected in cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaisesRegex(BinaryParseError, expected):
                    read_header(build_pmx_model_info(**kwargs))

    def test_read_state_preserves_partial_progress_after_an_error(self) -> None:
        stream = io.BytesIO(
            build_pmx_model_info(
                encoding_flag=9,
            )
        )
        reader = BinaryReader(
            stream,
            format_name="PMX",
        )
        magic, magic_offset = read_pmx_magic(reader)
        validate_pmx_magic(
            magic,
            offset=magic_offset,
        )
        state = PmxHeaderReadState()

        with self.assertRaises(BinaryParseError):
            read_pmx_header_body(
                reader,
                magic=magic,
                state=state,
            )

        self.assertEqual(state.version, 2.0)
        self.assertEqual(state.global_count, 8)
        self.assertIsNone(state.encoding)
        self.assertIsNone(state.additional_uv_count)
        self.assertIsNone(state.index_sizes)
        self.assertIsNone(state.model_info)

    def test_read_result_and_document_types_are_immutable(self) -> None:
        result, _ = read_header(build_pmx_model_info())

        with self.assertRaises(FrozenInstanceError):
            result.magic = b"BAD!"  # type: ignore[misc]

        with self.assertRaises(FrozenInstanceError):
            result.header.extra_global_data = b"changed"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
