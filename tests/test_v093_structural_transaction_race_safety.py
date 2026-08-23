"""CP23 source/destination race-safety regression gates."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import mmd_registry.pmx.editing.output as edit_output
from mmd_registry.diagnostics import (
    PmxServiceDiagnosticCode,
    PmxServiceError,
)
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.writer import serialize_pmx
from mmd_registry.services.structural_transaction import (
    PmxStructuralTransactionRequest,
    apply_structural_transaction,
)
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


def _clean_source_bytes() -> bytes:
    document = replace(
        load_pmx(io.BytesIO(build_pmx_roundtrip_fixture(version=2.1))),
        trailing_data=b"",
    )
    return serialize_pmx(document)


def _details(error: PmxServiceError) -> dict[str, object]:
    details = error.to_dict()["details"]
    assert isinstance(details, dict)
    return details


class V093StructuralTransactionRaceSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source.pmx"
        self.source_bytes = _clean_source_bytes()
        self.source.write_bytes(self.source_bytes)
        self.request = PmxStructuralTransactionRequest()

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def _temporary_outputs(destination: Path) -> list[Path]:
        return list(destination.parent.glob(f".{destination.name}.*.tmp"))

    def _assert_failure(
        self,
        error: PmxServiceError,
        *,
        code: PmxServiceDiagnosticCode,
        stage: str,
    ) -> None:
        self.assertEqual(error.diagnostic.code, code)
        self.assertEqual(
            _details(error),
            {
                "destination_published": False,
                "provenance": "safe_output",
                "source_bytes_read": True,
                "source_modified": False,
                "stage": stage,
            },
        )

    def _require_hardlinks(self) -> None:
        probe = self.root / "hardlink-probe.pmx"
        try:
            os.link(self.source, probe)
        except OSError as error:
            self.skipTest(f"hardlinks unavailable: {error}")
        probe.unlink()

    def test_same_identity_same_size_and_mtime_source_change_is_rejected(
        self,
    ) -> None:
        destination = self.root / "same-identity-source-race.pmx"
        original_verify = edit_output._verify_source_unchanged
        original_stat = self.source.stat()
        original_identity = edit_output._file_identity(self.source)
        racer_bytes = bytearray(self.source_bytes)
        racer_bytes[-1] ^= 1
        racer = bytes(racer_bytes)

        def mutate_then_verify(*args, **kwargs) -> None:
            self.source.write_bytes(racer)
            os.utime(
                self.source,
                ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
            )
            self.assertEqual(
                edit_output._file_identity(self.source),
                original_identity,
            )
            self.assertEqual(self.source.stat().st_size, original_stat.st_size)
            self.assertEqual(
                self.source.stat().st_mtime_ns,
                original_stat.st_mtime_ns,
            )
            return original_verify(*args, **kwargs)

        with (
            patch.object(
                edit_output,
                "_verify_source_unchanged",
                side_effect=mutate_then_verify,
            ),
            patch.object(edit_output, "_publish_no_clobber") as publish,
        ):
            with self.assertRaises(PmxServiceError) as raised:
                apply_structural_transaction(
                    self.source,
                    destination,
                    self.request,
                )

        self._assert_failure(
            raised.exception,
            code=PmxServiceDiagnosticCode.STRUCTURAL_VERIFICATION_FAILED,
            stage="source_reverify",
        )
        publish.assert_not_called()
        self.assertEqual(self.source.read_bytes(), racer)
        self.assertFalse(destination.exists())
        self.assertEqual(self._temporary_outputs(destination), [])

    def test_atomic_source_path_replacement_with_same_bytes_is_rejected(
        self,
    ) -> None:
        destination = self.root / "replaced-source-race.pmx"
        displaced = self.root / "displaced-source.pmx"
        replacement = self.root / "replacement-source.pmx"
        replacement.write_bytes(self.source_bytes)
        original_identity = edit_output._file_identity(self.source)
        original_verify = edit_output._verify_source_unchanged

        def replace_then_verify(*args, **kwargs) -> None:
            self.source.replace(displaced)
            replacement.replace(self.source)
            self.assertNotEqual(
                edit_output._file_identity(self.source),
                original_identity,
            )
            return original_verify(*args, **kwargs)

        with patch.object(
            edit_output,
            "_verify_source_unchanged",
            side_effect=replace_then_verify,
        ):
            with self.assertRaises(PmxServiceError) as raised:
                apply_structural_transaction(
                    self.source,
                    destination,
                    self.request,
                )

        self._assert_failure(
            raised.exception,
            code=PmxServiceDiagnosticCode.STRUCTURAL_VERIFICATION_FAILED,
            stage="source_reverify",
        )
        self.assertEqual(self.source.read_bytes(), self.source_bytes)
        self.assertEqual(displaced.read_bytes(), self.source_bytes)
        self.assertFalse(destination.exists())
        self.assertEqual(self._temporary_outputs(destination), [])

    def test_source_removal_before_reverification_is_rejected(self) -> None:
        destination = self.root / "removed-source-race.pmx"
        original_verify = edit_output._verify_source_unchanged

        def remove_then_verify(*args, **kwargs) -> None:
            self.source.unlink()
            return original_verify(*args, **kwargs)

        with patch.object(
            edit_output,
            "_verify_source_unchanged",
            side_effect=remove_then_verify,
        ):
            with self.assertRaises(PmxServiceError) as raised:
                apply_structural_transaction(
                    self.source,
                    destination,
                    self.request,
                )

        self._assert_failure(
            raised.exception,
            code=PmxServiceDiagnosticCode.STRUCTURAL_VERIFICATION_FAILED,
            stage="source_reverify",
        )
        self.assertFalse(self.source.exists())
        self.assertFalse(destination.exists())
        self.assertEqual(self._temporary_outputs(destination), [])

    def test_source_race_wins_before_later_destination_race(self) -> None:
        destination = self.root / "ordered-races.pmx"
        racer = b"destination race must never be created"
        original_verify = edit_output._verify_source_unchanged
        original_validate = edit_output._validate_destination_state
        validate_calls = 0

        def mutate_then_verify(*args, **kwargs) -> None:
            self.source.write_bytes(b"external source racer")
            return original_verify(*args, **kwargs)

        def create_on_second_validation(
            source: Path,
            output: Path,
            *,
            overwrite: bool,
        ) -> None:
            nonlocal validate_calls
            validate_calls += 1
            if validate_calls == 2:
                output.write_bytes(racer)
            return original_validate(source, output, overwrite=overwrite)

        with (
            patch.object(
                edit_output,
                "_verify_source_unchanged",
                side_effect=mutate_then_verify,
            ),
            patch.object(
                edit_output,
                "_validate_destination_state",
                side_effect=create_on_second_validation,
            ),
            patch.object(edit_output, "_publish_no_clobber") as publish,
        ):
            with self.assertRaises(PmxServiceError) as raised:
                apply_structural_transaction(
                    self.source,
                    destination,
                    self.request,
                )

        self._assert_failure(
            raised.exception,
            code=PmxServiceDiagnosticCode.STRUCTURAL_VERIFICATION_FAILED,
            stage="source_reverify",
        )
        self.assertEqual(validate_calls, 1)
        publish.assert_not_called()
        self.assertFalse(destination.exists())
        self.assertEqual(self._temporary_outputs(destination), [])

    def test_no_clobber_atomic_collision_preserves_destination_racer(
        self,
    ) -> None:
        destination = self.root / "no-clobber-race.pmx"
        racer = b"external destination racer"
        original_publish = edit_output._publish_no_clobber

        def collide_then_publish(source: Path, output: Path) -> None:
            self.assertFalse(output.exists())
            output.write_bytes(racer)
            return original_publish(source, output)

        with patch.object(
            edit_output,
            "_publish_no_clobber",
            side_effect=collide_then_publish,
        ) as publish:
            with self.assertRaises(PmxServiceError) as raised:
                apply_structural_transaction(
                    self.source,
                    destination,
                    self.request,
                )

        self._assert_failure(
            raised.exception,
            code=PmxServiceDiagnosticCode.STRUCTURAL_PATH_UNSAFE,
            stage="output_commit",
        )
        publish.assert_called_once()
        self.assertEqual(destination.read_bytes(), racer)
        self.assertEqual(self.source.read_bytes(), self.source_bytes)
        self.assertEqual(self._temporary_outputs(destination), [])

    def test_final_destination_check_rejects_source_hardlink_race(self) -> None:
        self._require_hardlinks()
        destination = self.root / "hardlink-before-validation.pmx"
        original_validate = edit_output._validate_destination_state
        validate_calls = 0

        def race_then_validate(
            source: Path,
            output: Path,
            *,
            overwrite: bool,
        ) -> None:
            nonlocal validate_calls
            validate_calls += 1
            if validate_calls == 2:
                os.link(source, output)
            return original_validate(source, output, overwrite=overwrite)

        with patch.object(
            edit_output,
            "_validate_destination_state",
            side_effect=race_then_validate,
        ):
            with self.assertRaises(PmxServiceError) as raised:
                apply_structural_transaction(
                    self.source,
                    destination,
                    self.request,
                    overwrite=True,
                )

        self._assert_failure(
            raised.exception,
            code=PmxServiceDiagnosticCode.STRUCTURAL_PATH_UNSAFE,
            stage="output_commit",
        )
        self.assertEqual(validate_calls, 2)
        self.assertTrue(self.source.samefile(destination))
        self.assertEqual(self.source.read_bytes(), self.source_bytes)
        self.assertEqual(self._temporary_outputs(destination), [])

    def test_overwrite_revalidates_current_separate_destination_racer(
        self,
    ) -> None:
        destination = self.root / "overwrite-current-racer.pmx"
        destination.write_bytes(b"initial destination")
        racer = b"separate destination racer"
        original_validate = edit_output._validate_destination_state
        original_replace = edit_output.os.replace
        validate_calls = 0
        observed_racer = False

        def race_then_validate(
            source: Path,
            output: Path,
            *,
            overwrite: bool,
        ) -> None:
            nonlocal validate_calls
            validate_calls += 1
            if validate_calls == 2:
                output.write_bytes(racer)
            return original_validate(source, output, overwrite=overwrite)

        def inspect_then_replace(source, output, *args, **kwargs):
            nonlocal observed_racer
            self.assertEqual(Path(output).read_bytes(), racer)
            observed_racer = True
            return original_replace(source, output, *args, **kwargs)

        with (
            patch.object(
                edit_output,
                "_validate_destination_state",
                side_effect=race_then_validate,
            ),
            patch.object(
                edit_output.os,
                "replace",
                side_effect=inspect_then_replace,
            ) as replace_call,
        ):
            result = apply_structural_transaction(
                self.source,
                destination,
                self.request,
                overwrite=True,
            )

        self.assertEqual(validate_calls, 2)
        replace_call.assert_called_once()
        self.assertTrue(observed_racer)
        published = destination.read_bytes()
        self.assertEqual(hashlib.sha256(published).hexdigest(), result.output_sha256)
        self.assertEqual(len(published), result.output_size_bytes)
        self.assertEqual(self.source.read_bytes(), self.source_bytes)
        self.assertEqual(self._temporary_outputs(destination), [])

    def test_overwrite_publication_cannot_modify_late_source_hardlink(
        self,
    ) -> None:
        self._require_hardlinks()
        destination = self.root / "hardlink-after-validation.pmx"
        original_source_identity = edit_output._file_identity(self.source)
        original_replace = edit_output.os.replace
        observed_alias = False

        def link_then_replace(source, output, *args, **kwargs):
            nonlocal observed_alias
            os.link(self.source, output)
            self.assertTrue(self.source.samefile(output))
            observed_alias = True
            return original_replace(source, output, *args, **kwargs)

        with patch.object(
            edit_output.os,
            "replace",
            side_effect=link_then_replace,
        ) as replace_call:
            result = apply_structural_transaction(
                self.source,
                destination,
                self.request,
                overwrite=True,
            )

        replace_call.assert_called_once()
        self.assertTrue(observed_alias)
        self.assertEqual(
            edit_output._file_identity(self.source),
            original_source_identity,
        )
        self.assertFalse(self.source.samefile(destination))
        self.assertEqual(self.source.read_bytes(), self.source_bytes)
        published = destination.read_bytes()
        self.assertEqual(hashlib.sha256(published).hexdigest(), result.output_sha256)
        self.assertEqual(len(published), result.output_size_bytes)
        self.assertEqual(self._temporary_outputs(destination), [])


if __name__ == "__main__":
    unittest.main()
