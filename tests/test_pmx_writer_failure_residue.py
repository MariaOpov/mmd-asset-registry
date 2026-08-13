"""Failure-residue contracts for generic PMX writer and roundtrip output."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mmd_registry.pmx import load_pmx, roundtrip_pmx, write_pmx
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


class _PartialWriteFailure:
    """Wrap one newly created file, persist a prefix, then fail the write."""

    def __init__(self, file) -> None:
        self._file = file

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        self._file.close()
        return False

    def write(self, data: bytes) -> int:
        prefix_size = min(32, len(data))
        self._file.write(data[:prefix_size])
        self._file.flush()
        raise OSError("simulated partial PMX write failure")


def _partial_write_open(destination: Path):
    """Return a Path.open replacement that fails only for destination create."""

    real_open = Path.open

    def failing_open(path: Path, mode: str = "r", *args, **kwargs):
        file = real_open(path, mode, *args, **kwargs)
        if Path(path) == destination and mode == "xb":
            return _PartialWriteFailure(file)
        return file

    return failing_open


class PmxWriterFailureResidueTests(unittest.TestCase):
    """Require write failures to preserve the no-partial-output postcondition."""

    def setUp(self) -> None:
        self.source_bytes = build_pmx_roundtrip_fixture()
        self.document = load_pmx_bytes(self.source_bytes)

    def test_create_new_partial_write_failure_leaves_no_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory, "partial.pmx")

            with patch.object(
                Path,
                "open",
                new=_partial_write_open(destination),
            ):
                with self.assertRaisesRegex(
                    OSError,
                    "simulated partial PMX write failure",
                ):
                    write_pmx(self.document, destination)

            self.assertFalse(
                destination.exists(),
                "failed create-new write must remove its partial destination",
            )

    def test_overwrite_replace_failure_preserves_existing_and_cleans_temp(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory, "existing.pmx")
            original = b"existing destination bytes"
            destination.write_bytes(original)

            with patch(
                "mmd_registry.pmx.writer.os.replace",
                side_effect=OSError("simulated replace failure"),
            ):
                with self.assertRaisesRegex(OSError, "simulated replace failure"):
                    write_pmx(
                        self.document,
                        destination,
                        overwrite=True,
                    )

            self.assertEqual(destination.read_bytes(), original)
            self.assertEqual(
                list(destination.parent.glob(f".{destination.name}.*.tmp")),
                [],
            )

    def test_roundtrip_partial_write_failure_leaves_no_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.pmx"
            destination = root / "output.pmx"
            source.write_bytes(self.source_bytes)

            with patch.object(
                Path,
                "open",
                new=_partial_write_open(destination),
            ):
                with self.assertRaisesRegex(
                    OSError,
                    "simulated partial PMX write failure",
                ):
                    roundtrip_pmx(source, destination)

            self.assertEqual(source.read_bytes(), self.source_bytes)
            self.assertFalse(
                destination.exists(),
                "failed roundtrip write must not leave output residue",
            )


def load_pmx_bytes(data: bytes):
    """Load generated PMX bytes without introducing a filesystem source."""

    import io

    return load_pmx(io.BytesIO(data))


if __name__ == "__main__":
    unittest.main()
