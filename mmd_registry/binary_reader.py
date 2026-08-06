"""Bounded little-endian binary reading for untrusted model files."""

from __future__ import annotations

import os
import struct
from contextlib import contextmanager
from typing import BinaryIO, Final, Iterator, NoReturn


VALID_INDEX_SIZES: Final[frozenset[int]] = frozenset({1, 2, 4})


class BinaryParseError(Exception):
    """Expected failure while parsing malformed or truncated binary data."""

    def __init__(
        self,
        *,
        format_name: str,
        section: str,
        record_index: int | None,
        offset: int,
        operation: str,
        reason: str,
    ) -> None:
        self.format_name = format_name
        self.section = section
        self.record_index = record_index
        self.offset = offset
        self.operation = operation
        self.reason = reason

        location = section

        if record_index is not None:
            location = f"{section}[{record_index}]"

        message = (
            f"{format_name} parse error in {location} "
            f"at offset 0x{offset:08X} while {operation}: {reason}"
        )

        super().__init__(message)


class BinaryReader:
    """Read little-endian binary data using strict size and offset checks."""

    def __init__(
        self,
        file: BinaryIO,
        *,
        format_name: str = "Binary",
    ) -> None:
        if not isinstance(format_name, str) or not format_name.strip():
            raise ValueError("format_name must be a non-empty string.")

        self._file = file
        self._format_name = format_name.strip()
        self._section = "file"
        self._record_index: int | None = None

        try:
            if not file.seekable():
                raise ValueError("BinaryReader requires a seekable binary stream.")

            original_offset = file.tell()
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            file.seek(original_offset, os.SEEK_SET)
        except (AttributeError, OSError) as error:
            raise ValueError(
                "BinaryReader requires a seekable binary stream."
            ) from error

        if original_offset < 0:
            raise ValueError("Binary stream offset cannot be negative.")

        if file_size < 0:
            raise ValueError("Binary stream size cannot be negative.")

        if original_offset > file_size:
            raise ValueError(
                "Binary stream offset cannot be beyond the end of the stream."
            )

        self._size = file_size

    @property
    def size(self) -> int:
        """Return the total stream size in bytes."""

        return self._size

    @property
    def offset(self) -> int:
        """Return the current stream offset."""

        return self._file.tell()

    @property
    def remaining(self) -> int:
        """Return the number of unread bytes remaining in the stream."""

        return self._size - self.offset

    @contextmanager
    def context(
        self,
        section: str,
        record_index: int | None = None,
    ) -> Iterator[None]:
        """Temporarily attach section and record information to parse errors."""

        if not isinstance(section, str) or not section.strip():
            raise ValueError("section must be a non-empty string.")

        if record_index is not None:
            self._require_non_negative_integer(
                record_index,
                "record_index",
            )

        previous_section = self._section
        previous_record_index = self._record_index

        self._section = section.strip()
        self._record_index = record_index

        try:
            yield
        finally:
            self._section = previous_section
            self._record_index = previous_record_index

    def read_exact(
        self,
        size: int,
        label: str,
    ) -> bytes:
        """Read exactly size bytes without permitting a partial result."""

        self._require_non_negative_integer(size, "size")
        self._require_label(label)

        start_offset = self.offset
        available = self.remaining

        if size > available:
            self._fail(
                operation=f"reading {label}",
                reason=(f"requested {size} bytes, but only {available} bytes remain."),
                offset=start_offset,
            )

        try:
            data = self._file.read(size)
        except OSError as error:
            self._fail(
                operation=f"reading {label}",
                reason=f"I/O failure: {error}",
                offset=start_offset,
            )

        if len(data) != size:
            self._fail(
                operation=f"reading {label}",
                reason=(f"expected {size} bytes, but received {len(data)} bytes."),
                offset=start_offset,
            )

        return data

    def skip(
        self,
        size: int,
        label: str,
    ) -> None:
        """Move forward by size bytes without permitting movement past EOF."""

        self._require_non_negative_integer(size, "size")
        self._require_label(label)

        start_offset = self.offset
        available = self.remaining

        if size > available:
            self._fail(
                operation=f"skipping {label}",
                reason=(f"requested {size} bytes, but only {available} bytes remain."),
                offset=start_offset,
            )

        target_offset = start_offset + size

        try:
            resulting_offset = self._file.seek(
                target_offset,
                os.SEEK_SET,
            )
        except OSError as error:
            self._fail(
                operation=f"skipping {label}",
                reason=f"I/O failure: {error}",
                offset=start_offset,
            )

        if resulting_offset != target_offset:
            self._fail(
                operation=f"skipping {label}",
                reason=(
                    f"expected offset {target_offset}, but the stream "
                    f"reported offset {resulting_offset}."
                ),
                offset=start_offset,
            )

    def skip_items(
        self,
        count: int,
        item_size: int,
        label: str,
    ) -> None:
        """Safely skip a fixed-size sequence without unchecked multiplication."""

        self._require_non_negative_integer(count, "count")
        self._require_non_negative_integer(item_size, "item_size")
        self._require_label(label)

        total_size = count * item_size

        self.skip(
            total_size,
            f"{label} ({count} items x {item_size} bytes)",
        )

    def read_uint8(self, label: str) -> int:
        """Read one unsigned 8-bit integer."""

        return self._read_number("<B", 1, label)

    def read_int8(self, label: str) -> int:
        """Read one signed 8-bit integer."""

        return self._read_number("<b", 1, label)

    def read_uint16(self, label: str) -> int:
        """Read one unsigned little-endian 16-bit integer."""

        return self._read_number("<H", 2, label)

    def read_int16(self, label: str) -> int:
        """Read one signed little-endian 16-bit integer."""

        return self._read_number("<h", 2, label)

    def read_uint32(self, label: str) -> int:
        """Read one unsigned little-endian 32-bit integer."""

        return self._read_number("<I", 4, label)

    def read_int32(self, label: str) -> int:
        """Read one signed little-endian 32-bit integer."""

        return self._read_number("<i", 4, label)

    def read_float32(self, label: str) -> float:
        """Read one little-endian 32-bit floating-point number."""

        return self._read_number("<f", 4, label)

    def read_index(
        self,
        size: int,
        *,
        signed: bool,
        label: str,
    ) -> int:
        """Read a signed or unsigned PMX-style index of size 1, 2, or 4."""

        self._require_label(label)

        if not isinstance(signed, bool):
            raise ValueError("signed must be true or false.")

        if size not in VALID_INDEX_SIZES:
            self._fail(
                operation=f"reading {label}",
                reason=(
                    f"invalid index size {size}; expected one of "
                    f"{sorted(VALID_INDEX_SIZES)}."
                ),
            )

        format_codes = {
            (1, False): "<B",
            (1, True): "<b",
            (2, False): "<H",
            (2, True): "<h",
            (4, False): "<I",
            (4, True): "<i",
        }

        return self._read_number(
            format_codes[(size, signed)],
            size,
            label,
        )

    def read_bounded_count(
        self,
        label: str,
        *,
        max_count: int,
        minimum_item_size: int = 0,
    ) -> int:
        """Read a non-negative int32 count subject to safety limits."""

        self._require_label(label)
        self._require_non_negative_integer(max_count, "max_count")
        self._require_non_negative_integer(
            minimum_item_size,
            "minimum_item_size",
        )

        count_offset = self.offset
        count = self.read_int32(label)

        if count < 0:
            self._fail(
                operation=f"validating {label}",
                reason=f"count cannot be negative: {count}.",
                offset=count_offset,
            )

        if count > max_count:
            self._fail(
                operation=f"validating {label}",
                reason=(f"count {count} exceeds the safety limit of {max_count}."),
                offset=count_offset,
            )

        if minimum_item_size:
            minimum_required = count * minimum_item_size

            if minimum_required > self.remaining:
                self._fail(
                    operation=f"validating {label}",
                    reason=(
                        f"count {count} requires at least "
                        f"{minimum_required} bytes, but only "
                        f"{self.remaining} bytes remain."
                    ),
                    offset=count_offset,
                )

        return count

    def read_bounded_length(
        self,
        label: str,
        *,
        max_length: int,
    ) -> int:
        """Read a non-negative int32 byte length subject to a safety limit."""

        self._require_label(label)
        self._require_non_negative_integer(max_length, "max_length")

        length_offset = self.offset
        length = self.read_int32(label)

        if length < 0:
            self._fail(
                operation=f"validating {label}",
                reason=f"length cannot be negative: {length}.",
                offset=length_offset,
            )

        if length > max_length:
            self._fail(
                operation=f"validating {label}",
                reason=(
                    f"length {length} exceeds the safety limit of {max_length} bytes."
                ),
                offset=length_offset,
            )

        if length > self.remaining:
            self._fail(
                operation=f"validating {label}",
                reason=(
                    f"length {length} exceeds the {self.remaining} bytes remaining."
                ),
                offset=length_offset,
            )

        return length

    def read_length_prefixed_bytes(
        self,
        label: str,
        *,
        max_length: int,
    ) -> bytes:
        """Read int32-length-prefixed bytes using a bounded allocation."""

        length = self.read_bounded_length(
            f"{label} length",
            max_length=max_length,
        )

        return self.read_exact(
            length,
            label,
        )

    def read_length_prefixed_text(
        self,
        label: str,
        *,
        encoding: str,
        max_length: int,
        require_even_length: bool = False,
    ) -> str:
        """Read and strictly decode a bounded int32-length-prefixed string."""

        self._require_label(label)

        if not isinstance(encoding, str) or not encoding.strip():
            raise ValueError("encoding must be a non-empty string.")

        if not isinstance(require_even_length, bool):
            raise ValueError("require_even_length must be true or false.")

        length_offset = self.offset
        length = self.read_bounded_length(
            f"{label} length",
            max_length=max_length,
        )

        if require_even_length and length % 2 != 0:
            self._fail(
                operation=f"validating {label} length",
                reason=(
                    f"length {length} must be an even number of bytes for {encoding}."
                ),
                offset=length_offset,
            )

        data_offset = self.offset
        data = self.read_exact(length, label)

        try:
            return data.decode(encoding)
        except UnicodeDecodeError as error:
            self._fail(
                operation=f"decoding {label}",
                reason=f"invalid {encoding} data: {error}.",
                offset=data_offset,
            )

    def _read_number(
        self,
        format_code: str,
        size: int,
        label: str,
    ) -> int | float:
        """Read and unpack one fixed-size numeric value."""

        self._require_label(label)
        data = self.read_exact(size, label)
        return struct.unpack(format_code, data)[0]

    def _fail(
        self,
        *,
        operation: str,
        reason: str,
        offset: int | None = None,
    ) -> NoReturn:
        """Raise an offset-aware malformed-binary error."""

        raise BinaryParseError(
            format_name=self._format_name,
            section=self._section,
            record_index=self._record_index,
            offset=self.offset if offset is None else offset,
            operation=operation,
            reason=reason,
        )

    @staticmethod
    def _require_non_negative_integer(
        value: int,
        name: str,
    ) -> None:
        """Reject invalid API arguments supplied by parser code."""

        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{name} must be a non-negative integer.")

    @staticmethod
    def _require_label(label: str) -> None:
        """Reject missing diagnostic labels supplied by parser code."""

        if not isinstance(label, str) or not label.strip():
            raise ValueError("label must be a non-empty string.")
