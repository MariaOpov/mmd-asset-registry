"""Streaming SHA-256 utilities for registered asset files."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal


DEFAULT_HASH_CHUNK_SIZE: Final[int] = 1024 * 1024

SHA256_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[0-9a-fA-F]{64}$"
)

Sha256Status = Literal[
    "matched",
    "mismatched",
    "not_recorded",
    "invalid_expected",
]


@dataclass(frozen=True, slots=True)
class Sha256CheckResult:
    """Result of hashing a file and comparing it with an expected digest."""

    expected: str | None
    actual: str
    status: Sha256Status
    size_bytes: int

    @property
    def algorithm(self) -> str:
        """Return the integrity algorithm used for this result."""

        return "sha256"


def is_valid_sha256(value: object) -> bool:
    """Return True when a value is a valid SHA-256 hexadecimal digest."""

    if not isinstance(value, str):
        return False

    return SHA256_PATTERN.fullmatch(value.strip()) is not None


def hash_file_sha256(
    file_path: str | Path,
    chunk_size: int = DEFAULT_HASH_CHUNK_SIZE,
) -> tuple[str, int]:
    """Calculate a file's SHA-256 digest using bounded streaming reads.

    Returns:
        A tuple containing the lowercase hexadecimal digest and file size.

    Raises:
        ValueError: If chunk_size is not a positive integer.
        OSError: If the file cannot be opened or read.
    """

    if not isinstance(chunk_size, int) or isinstance(chunk_size, bool):
        raise ValueError("chunk_size must be a positive integer.")

    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer.")

    path = Path(file_path)
    digest = hashlib.sha256()
    size_bytes = 0

    with path.open("rb") as file:
        while True:
            chunk = file.read(chunk_size)

            if not chunk:
                break

            digest.update(chunk)
            size_bytes += len(chunk)

    return digest.hexdigest(), size_bytes


def check_file_sha256(
    file_path: str | Path,
    expected_sha256: object = None,
    chunk_size: int = DEFAULT_HASH_CHUNK_SIZE,
) -> Sha256CheckResult:
    """Hash a file and compare it with an optional expected SHA-256 value.

    The file is hashed even when no expected digest has been recorded. This
    allows callers to report the actual digest without modifying the registry.
    """

    actual_sha256, size_bytes = hash_file_sha256(
        file_path=file_path,
        chunk_size=chunk_size,
    )

    if expected_sha256 is None:
        return Sha256CheckResult(
            expected=None,
            actual=actual_sha256,
            status="not_recorded",
            size_bytes=size_bytes,
        )

    if not isinstance(expected_sha256, str):
        return Sha256CheckResult(
            expected=None,
            actual=actual_sha256,
            status="invalid_expected",
            size_bytes=size_bytes,
        )

    expected_text = expected_sha256.strip()

    if not is_valid_sha256(expected_text):
        return Sha256CheckResult(
            expected=expected_text,
            actual=actual_sha256,
            status="invalid_expected",
            size_bytes=size_bytes,
        )

    normalized_expected = expected_text.lower()

    if normalized_expected == actual_sha256:
        status: Sha256Status = "matched"
    else:
        status = "mismatched"

    return Sha256CheckResult(
        expected=normalized_expected,
        actual=actual_sha256,
        status=status,
        size_bytes=size_bytes,
    )