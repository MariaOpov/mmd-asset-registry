"""Tests for bounded binary reading of untrusted model data."""

from __future__ import annotations

import io
import struct
import unittest

from mmd_registry.binary_reader import (
    BinaryParseError,
    BinaryReader,
)


class BinaryReaderTests(unittest.TestCase):
    """Tests for safe reads, skips, counts, lengths, and indices."""

    def test_tracks_size_offset_and_remaining(self) -> None:
        stream = io.BytesIO(b"abcd")
        stream.seek(1)

        reader = BinaryReader(stream, format_name="TEST")

        self.assertEqual(reader.size, 4)
        self.assertEqual(reader.offset, 1)
        self.assertEqual(reader.remaining, 3)

    def test_reads_little_endian_numeric_values(self) -> None:
        stream = io.BytesIO(
            struct.pack(
                "<BbHhIif",
                255,
                -2,
                65535,
                -3,
                4294967295,
                -4,
                1.5,
            )
        )
        reader = BinaryReader(stream, format_name="TEST")

        self.assertEqual(reader.read_uint8("uint8"), 255)
        self.assertEqual(reader.read_int8("int8"), -2)
        self.assertEqual(reader.read_uint16("uint16"), 65535)
        self.assertEqual(reader.read_int16("int16"), -3)
        self.assertEqual(reader.read_uint32("uint32"), 4294967295)
        self.assertEqual(reader.read_int32("int32"), -4)
        self.assertAlmostEqual(reader.read_float32("float32"), 1.5)
        self.assertEqual(reader.remaining, 0)

    def test_read_exact_reports_truncation_with_context(self) -> None:
        reader = BinaryReader(
            io.BytesIO(b"\x01"),
            format_name="PMX",
        )

        with reader.context("vertices", record_index=3):
            with self.assertRaises(BinaryParseError) as captured:
                reader.read_exact(2, "vertex data")

        error = captured.exception

        self.assertEqual(error.format_name, "PMX")
        self.assertEqual(error.section, "vertices")
        self.assertEqual(error.record_index, 3)
        self.assertEqual(error.offset, 0)
        self.assertIn("only 1 bytes remain", str(error))
        self.assertIn("vertices[3]", str(error))
        self.assertIn("offset 0x00000000", str(error))

    def test_context_restores_previous_location(self) -> None:
        reader = BinaryReader(
            io.BytesIO(b"\x00"),
            format_name="TEST",
        )

        with reader.context("materials", record_index=2):
            with self.assertRaises(BinaryParseError) as first_capture:
                reader.read_exact(2, "material")

        with self.assertRaises(BinaryParseError) as second_capture:
            reader.read_exact(2, "file data")

        self.assertEqual(
            first_capture.exception.section,
            "materials",
        )
        self.assertEqual(
            first_capture.exception.record_index,
            2,
        )
        self.assertEqual(
            second_capture.exception.section,
            "file",
        )
        self.assertIsNone(
            second_capture.exception.record_index,
        )

    def test_safe_skip_and_skip_items(self) -> None:
        reader = BinaryReader(
            io.BytesIO(bytes(range(10))),
            format_name="TEST",
        )

        reader.skip(2, "prefix")
        reader.skip_items(2, 3, "records")

        self.assertEqual(reader.offset, 8)
        self.assertEqual(reader.remaining, 2)
        self.assertEqual(reader.read_uint8("next byte"), 8)

    def test_skip_past_end_is_rejected(self) -> None:
        reader = BinaryReader(
            io.BytesIO(b"abc"),
            format_name="TEST",
        )

        with self.assertRaises(BinaryParseError) as captured:
            reader.skip(4, "oversized section")

        self.assertEqual(captured.exception.offset, 0)
        self.assertEqual(reader.offset, 0)
        self.assertIn("only 3 bytes remain", str(captured.exception))

    def test_bounded_count_accepts_valid_value(self) -> None:
        reader = BinaryReader(
            io.BytesIO(struct.pack("<i", 3) + b"abc"),
            format_name="TEST",
        )

        count = reader.read_bounded_count(
            "vertex count",
            max_count=10,
            minimum_item_size=1,
        )

        self.assertEqual(count, 3)
        self.assertEqual(reader.remaining, 3)

    def test_bounded_count_rejects_negative_value(self) -> None:
        reader = BinaryReader(
            io.BytesIO(struct.pack("<i", -1)),
            format_name="TEST",
        )

        with self.assertRaises(BinaryParseError) as captured:
            reader.read_bounded_count(
                "vertex count",
                max_count=10,
            )

        self.assertEqual(captured.exception.offset, 0)
        self.assertIn(
            "count cannot be negative: -1",
            str(captured.exception),
        )

    def test_bounded_count_rejects_oversized_value(self) -> None:
        reader = BinaryReader(
            io.BytesIO(struct.pack("<i", 11)),
            format_name="TEST",
        )

        with self.assertRaises(BinaryParseError) as captured:
            reader.read_bounded_count(
                "vertex count",
                max_count=10,
            )

        self.assertEqual(captured.exception.offset, 0)
        self.assertIn(
            "exceeds the safety limit of 10",
            str(captured.exception),
        )

    def test_bounded_count_rejects_impossible_remaining_size(self) -> None:
        reader = BinaryReader(
            io.BytesIO(struct.pack("<i", 3) + b"ab"),
            format_name="TEST",
        )

        with self.assertRaises(BinaryParseError) as captured:
            reader.read_bounded_count(
                "vertex count",
                max_count=10,
                minimum_item_size=1,
            )

        self.assertEqual(captured.exception.offset, 0)
        self.assertIn(
            "requires at least 3 bytes",
            str(captured.exception),
        )
        self.assertIn(
            "only 2 bytes remain",
            str(captured.exception),
        )

    def test_length_prefixed_bytes_and_text(self) -> None:
        data = b"".join(
            [
                struct.pack("<i", 3),
                b"abc",
                struct.pack("<i", 5),
                b"hello",
            ]
        )
        reader = BinaryReader(
            io.BytesIO(data),
            format_name="TEST",
        )

        raw_value = reader.read_length_prefixed_bytes(
            "raw value",
            max_length=10,
        )
        text_value = reader.read_length_prefixed_text(
            "text value",
            encoding="utf-8",
            max_length=10,
        )

        self.assertEqual(raw_value, b"abc")
        self.assertEqual(text_value, "hello")
        self.assertEqual(reader.remaining, 0)

    def test_length_prefixed_text_rejects_odd_utf16_length(
        self,
    ) -> None:
        reader = BinaryReader(
            io.BytesIO(struct.pack("<i", 3) + b"a\x00b"),
            format_name="PMX",
        )

        with self.assertRaises(BinaryParseError) as captured:
            reader.read_length_prefixed_text(
                "model name",
                encoding="utf-16-le",
                max_length=100,
                require_even_length=True,
            )

        self.assertEqual(captured.exception.offset, 0)
        self.assertIn(
            "must be an even number of bytes",
            str(captured.exception),
        )

    def test_length_prefixed_text_reports_decode_error(self) -> None:
        reader = BinaryReader(
            io.BytesIO(struct.pack("<i", 1) + b"\xff"),
            format_name="PMX",
        )

        with self.assertRaises(BinaryParseError) as captured:
            reader.read_length_prefixed_text(
                "model name",
                encoding="utf-8",
                max_length=100,
            )

        self.assertEqual(captured.exception.offset, 4)
        self.assertIn(
            "invalid utf-8 data",
            str(captured.exception),
        )

    def test_read_index_supports_signed_and_unsigned_values(
        self,
    ) -> None:
        data = b"".join(
            [
                struct.pack("<b", -1),
                struct.pack("<B", 255),
                struct.pack("<h", -1),
                struct.pack("<H", 65535),
                struct.pack("<i", -1),
                struct.pack("<I", 4294967295),
            ]
        )
        reader = BinaryReader(
            io.BytesIO(data),
            format_name="PMX",
        )

        self.assertEqual(
            reader.read_index(
                1,
                signed=True,
                label="signed byte index",
            ),
            -1,
        )
        self.assertEqual(
            reader.read_index(
                1,
                signed=False,
                label="unsigned byte index",
            ),
            255,
        )
        self.assertEqual(
            reader.read_index(
                2,
                signed=True,
                label="signed short index",
            ),
            -1,
        )
        self.assertEqual(
            reader.read_index(
                2,
                signed=False,
                label="unsigned short index",
            ),
            65535,
        )
        self.assertEqual(
            reader.read_index(
                4,
                signed=True,
                label="signed integer index",
            ),
            -1,
        )
        self.assertEqual(
            reader.read_index(
                4,
                signed=False,
                label="unsigned integer index",
            ),
            4294967295,
        )

    def test_read_index_rejects_invalid_size(self) -> None:
        reader = BinaryReader(
            io.BytesIO(b""),
            format_name="PMX",
        )

        with self.assertRaises(BinaryParseError) as captured:
            reader.read_index(
                3,
                signed=True,
                label="bone index",
            )

        self.assertEqual(captured.exception.offset, 0)
        self.assertIn(
            "invalid index size 3",
            str(captured.exception),
        )
        self.assertIn(
            "[1, 2, 4]",
            str(captured.exception),
        )


if __name__ == "__main__":
    unittest.main()
