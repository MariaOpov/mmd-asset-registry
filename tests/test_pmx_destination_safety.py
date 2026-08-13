"""Destination alias, collision, and publication-race safety contracts."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mmd_registry.pmx import load_pmx, roundtrip_pmx, write_pmx
from mmd_registry.pmx.roundtrip import PmxRoundTripPathError
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


class PmxDestinationSafetyTests(unittest.TestCase):
    """Require fail-closed destination handling across writer and roundtrip APIs."""

    def setUp(self) -> None:
        self.source_bytes = build_pmx_roundtrip_fixture()
        with tempfile.NamedTemporaryFile(suffix=".pmx", delete=False) as file:
            self._document_path = Path(file.name)
            file.write(self.source_bytes)
        self.document = load_pmx(self._document_path)

    def tearDown(self) -> None:
        self._document_path.unlink(missing_ok=True)

    @staticmethod
    def _publish_collision(destination: Path, racer_bytes: bytes):
        expected_destination = destination.resolve(strict=False)

        def collide(source: str | bytes | os.PathLike[str] | os.PathLike[bytes],
                    target: str | bytes | os.PathLike[str] | os.PathLike[bytes],
                    *args,
                    **kwargs) -> None:
            source_path = Path(source)
            target_path = Path(target)
            if target_path.resolve(strict=False) != expected_destination:
                raise AssertionError(f"unexpected publish target: {target_path}")
            if not source_path.is_file():
                raise AssertionError("temporary publish source must exist")
            if target_path.exists():
                raise AssertionError("destination must still be absent before collision")
            target_path.write_bytes(racer_bytes)
            raise FileExistsError("simulated destination publish collision")

        return collide

    def test_create_new_writer_publish_collision_preserves_racer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory, "output.pmx")
            racer = b"raced-in destination"

            with patch(
                "mmd_registry.pmx.writer.os.link",
                side_effect=self._publish_collision(destination, racer),
            ):
                with self.assertRaisesRegex(
                    FileExistsError,
                    "simulated destination publish collision",
                ):
                    write_pmx(self.document, destination)

            self.assertEqual(destination.read_bytes(), racer)
            self.assertEqual(
                list(destination.parent.glob(f".{destination.name}.*.tmp")),
                [],
            )

    def test_roundtrip_publish_collision_preserves_racer_and_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.pmx"
            destination = root / "output.pmx"
            source.write_bytes(self.source_bytes)
            racer = b"raced-in roundtrip destination"

            with patch(
                "mmd_registry.pmx.writer.os.link",
                side_effect=self._publish_collision(destination, racer),
            ):
                with self.assertRaisesRegex(
                    FileExistsError,
                    "simulated destination publish collision",
                ):
                    roundtrip_pmx(source, destination)

            self.assertEqual(source.read_bytes(), self.source_bytes)
            self.assertEqual(destination.read_bytes(), racer)
            self.assertEqual(
                list(destination.parent.glob(f".{destination.name}.*.tmp")),
                [],
            )

    def test_roundtrip_refuses_separate_symlink_destination_on_overwrite(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.pmx"
            target = root / "unrelated-target.pmx"
            destination = root / "output-link.pmx"
            source.write_bytes(self.source_bytes)
            original_target = b"unrelated target must survive"
            target.write_bytes(original_target)

            try:
                destination.symlink_to(target)
            except (NotImplementedError, OSError) as error:
                self.skipTest(f"symlinks are unavailable: {error}")

            with self.assertRaisesRegex(
                PmxRoundTripPathError,
                "symbolic link",
            ):
                roundtrip_pmx(source, destination, overwrite=True)

            self.assertTrue(destination.is_symlink())
            self.assertEqual(target.read_bytes(), original_target)
            self.assertEqual(source.read_bytes(), self.source_bytes)

    def test_generic_overwrite_replaces_symlink_entry_not_its_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "unrelated-target.pmx"
            destination = root / "output-link.pmx"
            original_target = b"unrelated target must survive"
            target.write_bytes(original_target)

            try:
                destination.symlink_to(target)
            except (NotImplementedError, OSError) as error:
                self.skipTest(f"symlinks are unavailable: {error}")

            write_pmx(self.document, destination, overwrite=True)

            self.assertFalse(destination.is_symlink())
            self.assertEqual(target.read_bytes(), original_target)
            self.assertEqual(load_pmx(destination), self.document)


if __name__ == "__main__":
    unittest.main()
