"""v0.9.1 atomic structural-output transaction regression gates."""

from __future__ import annotations

import io
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import mmd_registry.pmx.editing.output as edit_output
from mmd_registry.pmx.collection_transform import PmxStructuralTransformIntent
from mmd_registry.pmx.editing.errors import (
    PmxEditPathError,
    PmxEditVerificationError,
)
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.structural_output import (
    PmxStructuralOutputPathError,
    PmxStructuralOutputVerificationError,
    PmxStructuralWriteResult,
    verify_pmx_structural_serialization,
    write_pmx_structural_transform,
)
from mmd_registry.pmx.writer import serialize_pmx
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


def _clean_document():
    return replace(
        load_pmx(io.BytesIO(build_pmx_roundtrip_fixture(version=2.1))),
        trailing_data=b"",
    )


class V091AtomicStructuralTransactionTests(unittest.TestCase):
    """Freeze structural publication ordering and failure-residue semantics."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source.pmx"
        self.document = _clean_document()
        self.source_bytes = serialize_pmx(self.document)
        self.source.write_bytes(self.source_bytes)
        self.intent = PmxStructuralTransformIntent()
        self.verified = verify_pmx_structural_serialization(
            self.document,
            self.intent,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def _temporary_outputs(destination: Path) -> list[Path]:
        return list(
            destination.parent.glob(f".{destination.name}.*.tmp")
        )

    def test_temp_file_is_created_in_destination_directory(self) -> None:
        destination_dir = self.root / "destination"
        destination_dir.mkdir()
        destination = destination_dir / "output.pmx"
        original_named_temp = edit_output.tempfile.NamedTemporaryFile

        with patch(
            "mmd_registry.pmx.editing.output.tempfile.NamedTemporaryFile",
            wraps=original_named_temp,
        ) as named_temp:
            write_pmx_structural_transform(
                self.source,
                destination,
                self.intent,
            )

        named_temp.assert_called_once()
        kwargs = named_temp.call_args.kwargs
        self.assertEqual(Path(kwargs["dir"]), destination_dir.resolve())
        self.assertEqual(kwargs["prefix"], f".{destination.name}.")
        self.assertEqual(kwargs["suffix"], ".tmp")
        self.assertIs(kwargs["delete"], False)
        self.assertEqual(self._temporary_outputs(destination), [])

    def test_no_clobber_publication_sees_complete_verified_payload(self) -> None:
        destination = self.root / "complete-before-link.pmx"
        original_link = edit_output.os.link
        observed = False

        def inspect_then_link(source, target, *args, **kwargs):
            nonlocal observed
            temporary = Path(source)
            publish_target = Path(target)
            self.assertFalse(publish_target.exists())
            self.assertEqual(
                temporary.read_bytes(),
                self.verified.serialized_bytes,
            )
            observed = True
            return original_link(source, target, *args, **kwargs)

        with patch(
            "mmd_registry.pmx.editing.output.os.link",
            side_effect=inspect_then_link,
        ):
            write_pmx_structural_transform(
                self.source,
                destination,
                self.intent,
            )

        self.assertTrue(observed)
        self.assertEqual(destination.read_bytes(), self.verified.serialized_bytes)
        self.assertEqual(self._temporary_outputs(destination), [])

    def test_no_clobber_transaction_order_is_fail_closed(self) -> None:
        destination = self.root / "ordered-link.pmx"
        events: list[str] = []
        original_fsync = edit_output.os.fsync
        original_hash = edit_output._hash_file
        original_verify_source = edit_output._verify_source_unchanged
        original_validate = edit_output._validate_destination_state
        original_link = edit_output.os.link
        validate_calls = 0

        def record_fsync(fd: int) -> None:
            events.append("fsync")
            return original_fsync(fd)

        def record_hash(path: Path) -> str:
            if path.name.startswith(f".{destination.name}.") and path.suffix == ".tmp":
                events.append("temp_hash")
            return original_hash(path)

        def record_verify_source(*args, **kwargs) -> None:
            events.append("source_verify")
            return original_verify_source(*args, **kwargs)

        def record_validate(
            source: Path,
            output: Path,
            *,
            overwrite: bool,
        ) -> None:
            nonlocal validate_calls
            validate_calls += 1
            if validate_calls == 2:
                events.append("destination_revalidate")
            return original_validate(source, output, overwrite=overwrite)

        def record_link(source, target, *args, **kwargs):
            events.append("publish")
            return original_link(source, target, *args, **kwargs)

        with patch(
            "mmd_registry.pmx.editing.output.os.fsync",
            side_effect=record_fsync,
        ), patch(
            "mmd_registry.pmx.editing.output._hash_file",
            side_effect=record_hash,
        ), patch(
            "mmd_registry.pmx.editing.output._verify_source_unchanged",
            side_effect=record_verify_source,
        ), patch(
            "mmd_registry.pmx.editing.output._validate_destination_state",
            side_effect=record_validate,
        ), patch(
            "mmd_registry.pmx.editing.output.os.link",
            side_effect=record_link,
        ):
            write_pmx_structural_transform(
                self.source,
                destination,
                self.intent,
            )

        self.assertEqual(validate_calls, 2)
        self.assertLess(events.index("fsync"), events.index("temp_hash"))
        self.assertLess(events.index("temp_hash"), events.index("source_verify"))
        self.assertLess(
            events.index("source_verify"),
            events.index("destination_revalidate"),
        )
        self.assertLess(
            events.index("destination_revalidate"),
            events.index("publish"),
        )

    def test_overwrite_transaction_preserves_old_bytes_until_replace(self) -> None:
        destination = self.root / "ordered-replace.pmx"
        old_bytes = b"existing destination must survive until replace"
        destination.write_bytes(old_bytes)
        events: list[str] = []
        original_fsync = edit_output.os.fsync
        original_hash = edit_output._hash_file
        original_verify_source = edit_output._verify_source_unchanged
        original_validate = edit_output._validate_destination_state
        original_replace = edit_output.os.replace
        validate_calls = 0

        def record_fsync(fd: int) -> None:
            events.append("fsync")
            return original_fsync(fd)

        def record_hash(path: Path) -> str:
            if path.name.startswith(f".{destination.name}.") and path.suffix == ".tmp":
                events.append("temp_hash")
            return original_hash(path)

        def record_verify_source(*args, **kwargs) -> None:
            events.append("source_verify")
            return original_verify_source(*args, **kwargs)

        def record_validate(
            source: Path,
            output: Path,
            *,
            overwrite: bool,
        ) -> None:
            nonlocal validate_calls
            validate_calls += 1
            if validate_calls == 2:
                events.append("destination_revalidate")
            return original_validate(source, output, overwrite=overwrite)

        def record_replace(source, target, *args, **kwargs):
            self.assertEqual(Path(target).read_bytes(), old_bytes)
            events.append("publish")
            return original_replace(source, target, *args, **kwargs)

        with patch(
            "mmd_registry.pmx.editing.output.os.fsync",
            side_effect=record_fsync,
        ), patch(
            "mmd_registry.pmx.editing.output._hash_file",
            side_effect=record_hash,
        ), patch(
            "mmd_registry.pmx.editing.output._verify_source_unchanged",
            side_effect=record_verify_source,
        ), patch(
            "mmd_registry.pmx.editing.output._validate_destination_state",
            side_effect=record_validate,
        ), patch(
            "mmd_registry.pmx.editing.output.os.replace",
            side_effect=record_replace,
        ):
            write_pmx_structural_transform(
                self.source,
                destination,
                self.intent,
                overwrite=True,
            )

        self.assertEqual(validate_calls, 2)
        self.assertLess(events.index("fsync"), events.index("temp_hash"))
        self.assertLess(events.index("temp_hash"), events.index("source_verify"))
        self.assertLess(
            events.index("source_verify"),
            events.index("destination_revalidate"),
        )
        self.assertLess(
            events.index("destination_revalidate"),
            events.index("publish"),
        )
        self.assertEqual(destination.read_bytes(), self.verified.serialized_bytes)
        self.assertEqual(self._temporary_outputs(destination), [])

    def test_structural_link_failure_leaves_no_partial_output(self) -> None:
        destination = self.root / "link-failure.pmx"

        with patch(
            "mmd_registry.pmx.editing.output.os.link",
            side_effect=OSError("simulated structural link failure"),
        ):
            with self.assertRaisesRegex(OSError, "structural link failure"):
                write_pmx_structural_transform(
                    self.source,
                    destination,
                    self.intent,
                )

        self.assertFalse(destination.exists())
        self.assertEqual(self.source.read_bytes(), self.source_bytes)
        self.assertEqual(self._temporary_outputs(destination), [])

    def test_structural_replace_failure_preserves_existing_output(self) -> None:
        destination = self.root / "replace-failure.pmx"
        old_bytes = b"existing structural destination"
        destination.write_bytes(old_bytes)

        with patch(
            "mmd_registry.pmx.editing.output.os.replace",
            side_effect=OSError("simulated structural replace failure"),
        ):
            with self.assertRaisesRegex(OSError, "structural replace failure"):
                write_pmx_structural_transform(
                    self.source,
                    destination,
                    self.intent,
                    overwrite=True,
                )

        self.assertEqual(destination.read_bytes(), old_bytes)
        self.assertEqual(self.source.read_bytes(), self.source_bytes)
        self.assertEqual(self._temporary_outputs(destination), [])

    def test_destination_revalidation_failure_prevents_publication(self) -> None:
        destination = self.root / "revalidation-failure.pmx"
        original_validate = edit_output._validate_destination_state
        validate_calls = 0

        def fail_second_validation(
            source: Path,
            output: Path,
            *,
            overwrite: bool,
        ) -> None:
            nonlocal validate_calls
            validate_calls += 1
            if validate_calls == 2:
                raise PmxEditPathError(
                    "simulated destination revalidation failure"
                )
            return original_validate(source, output, overwrite=overwrite)

        with patch(
            "mmd_registry.pmx.editing.output._validate_destination_state",
            side_effect=fail_second_validation,
        ), patch(
            "mmd_registry.pmx.editing.output.os.link",
        ) as publish:
            with self.assertRaisesRegex(
                PmxStructuralOutputPathError,
                "destination revalidation failure",
            ):
                write_pmx_structural_transform(
                    self.source,
                    destination,
                    self.intent,
                )

        self.assertEqual(validate_calls, 2)
        publish.assert_not_called()
        self.assertFalse(destination.exists())
        self.assertEqual(self.source.read_bytes(), self.source_bytes)
        self.assertEqual(self._temporary_outputs(destination), [])

    def test_temp_hash_failure_prevents_later_commit_stages(self) -> None:
        destination = self.root / "temp-hash-failure.pmx"
        original_hash = edit_output._hash_file

        def fail_temp_hash(path: Path) -> str:
            if path.name.startswith(f".{destination.name}.") and path.suffix == ".tmp":
                return "0" * 64
            return original_hash(path)

        with patch(
            "mmd_registry.pmx.editing.output._hash_file",
            side_effect=fail_temp_hash,
        ), patch(
            "mmd_registry.pmx.editing.output._verify_source_unchanged",
        ) as source_verify, patch(
            "mmd_registry.pmx.editing.output.os.link",
        ) as publish:
            with self.assertRaisesRegex(
                PmxStructuralOutputVerificationError,
                "temporary PMX",
            ):
                write_pmx_structural_transform(
                    self.source,
                    destination,
                    self.intent,
                )

        source_verify.assert_not_called()
        publish.assert_not_called()
        self.assertFalse(destination.exists())
        self.assertEqual(self._temporary_outputs(destination), [])

    def test_source_verification_failure_prevents_publication(self) -> None:
        destination = self.root / "source-verification-failure.pmx"

        with patch(
            "mmd_registry.pmx.editing.output._verify_source_unchanged",
            side_effect=PmxEditVerificationError(
                "simulated source verification failure"
            ),
        ), patch(
            "mmd_registry.pmx.editing.output.os.link",
        ) as publish:
            with self.assertRaisesRegex(
                PmxStructuralOutputVerificationError,
                "source verification failure",
            ):
                write_pmx_structural_transform(
                    self.source,
                    destination,
                    self.intent,
                )

        publish.assert_not_called()
        self.assertFalse(destination.exists())
        self.assertEqual(self._temporary_outputs(destination), [])

    def test_failed_commit_never_constructs_success_result(self) -> None:
        destination = self.root / "commit-failure.pmx"

        with patch(
            "mmd_registry.pmx.structural_output._edit_output._commit_verified_bytes",
            side_effect=OSError("simulated commit failure"),
        ), patch.object(
            PmxStructuralWriteResult,
            "_from_committed",
        ) as from_committed:
            with self.assertRaisesRegex(OSError, "simulated commit failure"):
                write_pmx_structural_transform(
                    self.source,
                    destination,
                    self.intent,
                )

        from_committed.assert_not_called()
        self.assertFalse(destination.exists())

    def test_success_result_is_constructed_only_after_publication(self) -> None:
        destination = self.root / "result-after-publication.pmx"
        original_from_committed = PmxStructuralWriteResult._from_committed
        observed_destination = False

        def inspect_then_construct(**kwargs):
            nonlocal observed_destination
            output_path = kwargs["output_path"]
            self.assertTrue(output_path.is_file())
            self.assertEqual(
                output_path.read_bytes(),
                kwargs["serialization"].serialized_bytes,
            )
            observed_destination = True
            return original_from_committed(**kwargs)

        with patch.object(
            PmxStructuralWriteResult,
            "_from_committed",
            side_effect=inspect_then_construct,
        ):
            result = write_pmx_structural_transform(
                self.source,
                destination,
                self.intent,
            )

        self.assertTrue(observed_destination)
        self.assertEqual(result.output_path, destination.resolve())
        self.assertEqual(self._temporary_outputs(destination), [])

    def test_success_paths_leave_no_temporary_residue(self) -> None:
        create_destination = self.root / "create-success.pmx"
        replace_destination = self.root / "replace-success.pmx"
        replace_destination.write_bytes(b"old destination")

        write_pmx_structural_transform(
            self.source,
            create_destination,
            self.intent,
        )
        write_pmx_structural_transform(
            self.source,
            replace_destination,
            self.intent,
            overwrite=True,
        )

        self.assertEqual(self._temporary_outputs(create_destination), [])
        self.assertEqual(self._temporary_outputs(replace_destination), [])
        self.assertEqual(self.source.read_bytes(), self.source_bytes)


if __name__ == "__main__":
    unittest.main()
