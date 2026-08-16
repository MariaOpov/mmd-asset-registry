from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from unittest.mock import patch

import mmd_registry.pmx as pmx_public
import mmd_registry.services as services_public
from mmd_registry.pmx.collection_transform import (
    PmxCollectionTransform,
    PmxStructuralTransformIntent,
)
from mmd_registry.pmx.editing import output as edit_output
from mmd_registry.pmx.editing.errors import PmxEditVerificationError
from mmd_registry.pmx.index_remap import PmxIndexRemap
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.pmx.structural_invariants import PmxStructuralInvariantError
from mmd_registry.pmx.structural_output import (
    PMX_STRUCTURAL_PREVIEW_SCHEMA_VERSION,
    PmxStructuralOutputPathError,
    PmxStructuralOutputVerificationError,
    PmxStructuralSerializationResult,
    PmxStructuralWriteResult,
    verify_pmx_structural_serialization,
    write_pmx_structural_transform,
)
from mmd_registry.pmx.structural_preview import (
    preview_pmx_structural_transform,
)
from mmd_registry.pmx.writer import serialize_pmx
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


def _clean_document(*, version: float = 2.1):
    return replace(
        load_pmx(io.BytesIO(build_pmx_roundtrip_fixture(version=version))),
        trailing_data=b"",
    )


def _clean_source_bytes(*, version: float = 2.1) -> bytes:
    return serialize_pmx(_clean_document(version=version))


def _transform(
    kind: PmxReferenceTargetKind,
    targets: tuple[int | None, ...],
    new_size: int,
) -> PmxCollectionTransform:
    return PmxCollectionTransform(
        kind=kind,
        remap=PmxIndexRemap(targets=targets, new_size=new_size),
    )


def _reverse(
    kind: PmxReferenceTargetKind,
    size: int,
) -> PmxCollectionTransform:
    return _transform(
        kind,
        tuple(reversed(range(size))),
        size,
    )


def _full_reverse_intent(document) -> PmxStructuralTransformIntent:
    return PmxStructuralTransformIntent(
        transforms=(
            _reverse(PmxReferenceTargetKind.VERTEX, len(document.vertices)),
            _reverse(PmxReferenceTargetKind.TEXTURE, len(document.texture_paths)),
            _reverse(PmxReferenceTargetKind.MATERIAL, len(document.materials)),
            _reverse(PmxReferenceTargetKind.BONE, len(document.bones)),
            _reverse(PmxReferenceTargetKind.MORPH, len(document.morphs)),
            _reverse(
                PmxReferenceTargetKind.RIGID_BODY,
                len(document.rigid_bodies),
            ),
        )
    )


class StructuralSerializationContractTests(unittest.TestCase):
    def test_direct_result_self_derives_all_verification_evidence(self) -> None:
        source = _clean_document()
        result = PmxStructuralSerializationResult(
            source_document=source,
            intent=PmxStructuralTransformIntent(),
        )

        self.assertIs(result.source_document, source)
        self.assertIs(result.preview.certificate.document, source)
        self.assertEqual(
            result.reparsed_certificate.document,
            result.preview.certificate.document,
        )
        self.assertRegex(result.output_sha256, r"\A[0-9a-f]{64}\Z")

    def test_helper_matches_direct_result(self) -> None:
        source = _clean_document()
        intent = _full_reverse_intent(source)

        direct = PmxStructuralSerializationResult(
            source_document=source,
            intent=intent,
        )
        helper = verify_pmx_structural_serialization(source, intent)

        self.assertEqual(direct.serialized_bytes, helper.serialized_bytes)
        self.assertEqual(direct.to_dict(), helper.to_dict())

    def test_derived_fields_cannot_be_supplied_by_caller(self) -> None:
        source = _clean_document()
        valid = verify_pmx_structural_serialization(
            source,
            PmxStructuralTransformIntent(),
        )

        with self.assertRaises(TypeError):
            PmxStructuralSerializationResult(  # type: ignore[call-arg]
                source_document=source,
                intent=PmxStructuralTransformIntent(),
                preview=valid.preview,
            )

    def test_result_is_immutable(self) -> None:
        source = _clean_document()
        result = verify_pmx_structural_serialization(
            source,
            PmxStructuralTransformIntent(),
        )

        with self.assertRaises(FrozenInstanceError):
            result.output_sha256 = "0" * 64  # type: ignore[misc]

    def test_wrong_argument_types_fail_before_work(self) -> None:
        source = _clean_document()

        with self.assertRaisesRegex(TypeError, "source_document"):
            PmxStructuralSerializationResult(  # type: ignore[arg-type]
                source_document=object(),
                intent=PmxStructuralTransformIntent(),
            )
        with self.assertRaisesRegex(TypeError, "PmxStructuralTransformIntent"):
            PmxStructuralSerializationResult(  # type: ignore[arg-type]
                source_document=source,
                intent=object(),
            )

    def test_serialized_bytes_reparse_exactly_to_intended_document(self) -> None:
        source = _clean_document()
        result = verify_pmx_structural_serialization(
            source,
            _full_reverse_intent(source),
        )

        reparsed = load_pmx(io.BytesIO(result.serialized_bytes))
        self.assertEqual(reparsed, result.preview.certificate.document)

    def test_output_hash_and_size_are_exact(self) -> None:
        source = _clean_document()
        result = verify_pmx_structural_serialization(
            source,
            _full_reverse_intent(source),
        )

        self.assertEqual(
            result.output_sha256,
            hashlib.sha256(result.serialized_bytes).hexdigest(),
        )
        self.assertEqual(result.output_size_bytes, len(result.serialized_bytes))

    def test_verified_serialization_report_closes_cp17_boundary(self) -> None:
        source = _clean_document()
        result = verify_pmx_structural_serialization(
            source,
            _full_reverse_intent(source),
        )
        report = result.to_dict()

        self.assertEqual(
            report["preview_schema_version"],
            PMX_STRUCTURAL_PREVIEW_SCHEMA_VERSION,
        )
        self.assertTrue(report["dry_run"])
        self.assertIs(report["output"]["written"], False)
        self.assertEqual(report["output"]["sha256"], result.output_sha256)
        self.assertEqual(
            report["verification"],
            {
                "invariants": "passed",
                "reference_model": "passed",
                "serialization": "passed",
                "semantic": "passed",
            },
        )

    def test_serialization_report_is_deterministic_and_json_ready(self) -> None:
        source = _clean_document()
        intent = _full_reverse_intent(source)

        first = verify_pmx_structural_serialization(source, intent)
        second = verify_pmx_structural_serialization(source, intent)

        self.assertEqual(first.serialized_bytes, second.serialized_bytes)
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(
            json.dumps(
                first.to_dict(),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            json.dumps(
                second.to_dict(),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )

    def test_noop_still_performs_full_serialization_verification(self) -> None:
        source = _clean_document()
        result = verify_pmx_structural_serialization(
            source,
            PmxStructuralTransformIntent(),
        )

        self.assertEqual(result.status, "no_changes")
        self.assertGreater(result.output_size_bytes, 0)
        self.assertEqual(
            load_pmx(io.BytesIO(result.serialized_bytes)),
            source,
        )
        self.assertEqual(result.to_dict()["verification"]["semantic"], "passed")

    def test_reparse_semantic_mismatch_fails_closed(self) -> None:
        source = _clean_document()
        changed_info = replace(
            source.model_info,
            local_name=source.model_info.local_name + " mismatch",
        )
        mismatch = replace(source, model_info=changed_info)

        with patch(
            "mmd_registry.pmx.structural_output.load_pmx",
            return_value=mismatch,
        ):
            with self.assertRaisesRegex(
                PmxStructuralOutputVerificationError,
                "does not match",
            ):
                verify_pmx_structural_serialization(
                    source,
                    PmxStructuralTransformIntent(),
                )

    def test_reparsed_invalid_document_fails_closed(self) -> None:
        source = _clean_document()
        invalid_body = replace(source.rigid_bodies[0], mass=-1.0)
        invalid = replace(
            source,
            rigid_bodies=(invalid_body, *source.rigid_bodies[1:]),
        )

        with patch(
            "mmd_registry.pmx.structural_output.load_pmx",
            return_value=invalid,
        ):
            with self.assertRaisesRegex(
                PmxStructuralOutputVerificationError,
                "invariant certification",
            ):
                verify_pmx_structural_serialization(
                    source,
                    PmxStructuralTransformIntent(),
                )

    def test_reparse_exception_is_wrapped_as_verification_failure(self) -> None:
        source = _clean_document()

        with patch(
            "mmd_registry.pmx.structural_output.load_pmx",
            side_effect=ValueError("simulated reparse failure"),
        ):
            with self.assertRaisesRegex(
                PmxStructuralOutputVerificationError,
                "could not be reparsed",
            ):
                verify_pmx_structural_serialization(
                    source,
                    PmxStructuralTransformIntent(),
                )

    def test_noop_with_trailing_data_is_not_serializable_structurally(self) -> None:
        source = load_pmx(io.BytesIO(build_pmx_roundtrip_fixture()))

        with self.assertRaisesRegex(PmxStructuralInvariantError, "trailing_data"):
            verify_pmx_structural_serialization(
                source,
                PmxStructuralTransformIntent(),
            )

    def test_pmx20_verified_serialization_is_supported(self) -> None:
        source = _clean_document(version=2.0)
        result = verify_pmx_structural_serialization(
            source,
            PmxStructuralTransformIntent(
                transforms=(
                    _reverse(
                        PmxReferenceTargetKind.TEXTURE,
                        len(source.texture_paths),
                    ),
                )
            ),
        )

        self.assertEqual(result.reparsed_certificate.document.header.version, 2.0)
        self.assertEqual(result.reparsed_certificate.document.soft_bodies, ())

    def test_extra_global_data_survives_verified_serialization(self) -> None:
        source = _clean_document()
        source = replace(
            source,
            header=replace(source.header, extra_global_data=b"\xaa\x55"),
        )

        result = verify_pmx_structural_serialization(
            source,
            PmxStructuralTransformIntent(),
        )

        self.assertEqual(
            result.reparsed_certificate.document.header.extra_global_data,
            b"\xaa\x55",
        )


class StructuralWriteResultContractTests(unittest.TestCase):
    def test_write_result_direct_construction_is_blocked_for_supported_api(self) -> None:
        with self.assertRaisesRegex(TypeError, "cannot be constructed directly"):
            PmxStructuralWriteResult()  # type: ignore[call-arg]


class StructuralFilesystemOutputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.input_path = self.root / "source.pmx"
        self.source_bytes = _clean_source_bytes()
        self.input_path.write_bytes(self.source_bytes)
        self.source_document = load_pmx(io.BytesIO(self.source_bytes))
        self.changed_intent = _full_reverse_intent(self.source_document)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def temporary_outputs(self, destination: Path) -> list[Path]:
        return list(
            destination.parent.glob(f".{destination.name}.*.tmp")
        )

    def test_changed_transform_writes_verified_distinct_output(self) -> None:
        output = self.root / "changed.pmx"

        result = write_pmx_structural_transform(
            self.input_path,
            output,
            self.changed_intent,
        )

        self.assertEqual(result.status, "written")
        self.assertTrue(output.is_file())
        self.assertEqual(output.read_bytes(), result.serialization.serialized_bytes)
        self.assertEqual(
            load_pmx(output),
            result.serialization.preview.certificate.document,
        )
        self.assertEqual(self.input_path.read_bytes(), self.source_bytes)
        self.assertEqual(self.temporary_outputs(output), [])

    def test_committed_write_result_is_immutable(self) -> None:
        output = self.root / "immutable-result.pmx"
        result = write_pmx_structural_transform(
            self.input_path,
            output,
            self.changed_intent,
        )

        with self.assertRaises(FrozenInstanceError):
            result.source_sha256 = "0" * 64  # type: ignore[misc]

    def test_write_hash_size_and_paths_match_committed_output(self) -> None:
        output = self.root / "hashes.pmx"

        result = write_pmx_structural_transform(
            self.input_path,
            output,
            self.changed_intent,
        )

        self.assertEqual(
            result.source_sha256,
            hashlib.sha256(self.source_bytes).hexdigest(),
        )
        self.assertEqual(result.source_size_bytes, len(self.source_bytes))
        self.assertEqual(
            result.output_sha256,
            hashlib.sha256(output.read_bytes()).hexdigest(),
        )
        self.assertEqual(result.output_size_bytes, output.stat().st_size)
        self.assertEqual(result.input_path, self.input_path.resolve())
        self.assertEqual(result.output_path, output.resolve())

    def test_write_report_has_semantic_and_input_unchanged_guarantees(self) -> None:
        output = self.root / "report.pmx"

        result = write_pmx_structural_transform(
            self.input_path,
            output,
            self.changed_intent,
        )
        report = result.to_dict()

        self.assertFalse(report["dry_run"])
        self.assertEqual(report["status"], "written")
        self.assertTrue(report["output"]["written"])
        self.assertEqual(report["source"]["sha256"], result.source_sha256)
        self.assertEqual(report["output"]["sha256"], result.output_sha256)
        self.assertEqual(report["verification"]["semantic"], "passed")
        self.assertEqual(report["verification"]["serialization"], "passed")
        self.assertIs(report["verification"]["input_unchanged"], True)

    def test_noop_still_writes_distinct_verified_output(self) -> None:
        output = self.root / "noop.pmx"

        result = write_pmx_structural_transform(
            self.input_path,
            output,
            PmxStructuralTransformIntent(),
        )

        self.assertEqual(result.status, "no_changes")
        self.assertTrue(output.is_file())
        self.assertEqual(
            load_pmx(output),
            self.source_document,
        )
        self.assertTrue(result.to_dict()["output"]["written"])

    def test_write_matches_independent_cp17_preview_intent(self) -> None:
        output = self.root / "parity.pmx"
        expected_preview = preview_pmx_structural_transform(
            self.source_document,
            self.changed_intent,
        )

        result = write_pmx_structural_transform(
            self.input_path,
            output,
            self.changed_intent,
        )

        self.assertEqual(
            result.serialization.preview.to_dict(),
            expected_preview.to_dict(),
        )
        self.assertEqual(
            result.serialization.preview.certificate.document,
            expected_preview.certificate.document,
        )

    def test_write_reuses_v08_atomic_commit_kernel(self) -> None:
        output = self.root / "reuse.pmx"
        original = edit_output._commit_verified_bytes

        with patch(
            "mmd_registry.pmx.structural_output._edit_output._commit_verified_bytes",
            wraps=original,
        ) as commit:
            result = write_pmx_structural_transform(
                self.input_path,
                output,
                self.changed_intent,
            )

        commit.assert_called_once()
        self.assertEqual(output.read_bytes(), result.serialization.serialized_bytes)

    def test_same_input_output_is_refused_even_with_overwrite(self) -> None:
        for overwrite in (False, True):
            with self.subTest(overwrite=overwrite):
                with self.assertRaisesRegex(
                    PmxStructuralOutputPathError,
                    "different files",
                ):
                    write_pmx_structural_transform(
                        self.input_path,
                        self.input_path,
                        self.changed_intent,
                        overwrite=overwrite,
                    )
        self.assertEqual(self.input_path.read_bytes(), self.source_bytes)

    def test_existing_output_requires_overwrite(self) -> None:
        output = self.root / "exists.pmx"
        original_output = b"existing"
        output.write_bytes(original_output)

        with self.assertRaisesRegex(
            PmxStructuralOutputPathError,
            "already exists",
        ):
            write_pmx_structural_transform(
                self.input_path,
                output,
                self.changed_intent,
            )

        self.assertEqual(output.read_bytes(), original_output)
        self.assertEqual(self.input_path.read_bytes(), self.source_bytes)

    def test_overwrite_replaces_only_separate_destination(self) -> None:
        output = self.root / "overwrite.pmx"
        output.write_bytes(b"old output")

        result = write_pmx_structural_transform(
            self.input_path,
            output,
            self.changed_intent,
            overwrite=True,
        )

        self.assertEqual(output.read_bytes(), result.serialization.serialized_bytes)
        self.assertEqual(self.input_path.read_bytes(), self.source_bytes)

    def test_hardlink_alias_of_source_is_refused(self) -> None:
        output = self.root / "hardlink.pmx"
        try:
            os.link(self.input_path, output)
        except OSError as error:
            self.skipTest(f"hardlinks unavailable: {error}")

        with self.assertRaisesRegex(
            PmxStructuralOutputPathError,
            "same file",
        ):
            write_pmx_structural_transform(
                self.input_path,
                output,
                self.changed_intent,
                overwrite=True,
            )

        self.assertEqual(self.input_path.read_bytes(), self.source_bytes)

    def test_symlink_alias_of_source_is_refused(self) -> None:
        output = self.root / "symlink.pmx"
        try:
            output.symlink_to(self.input_path)
        except OSError as error:
            self.skipTest(f"symlinks unavailable: {error}")

        with self.assertRaises(PmxStructuralOutputPathError):
            write_pmx_structural_transform(
                self.input_path,
                output,
                self.changed_intent,
                overwrite=True,
            )

        self.assertEqual(self.input_path.read_bytes(), self.source_bytes)

    def test_temp_hash_mismatch_fails_without_partial_output(self) -> None:
        output = self.root / "hash-mismatch.pmx"
        original_hash = edit_output._hash_file

        def mismatching_temp_hash(path: Path) -> str:
            if path.name.startswith(f".{output.name}.") and path.suffix == ".tmp":
                return "0" * 64
            return original_hash(path)

        with patch(
            "mmd_registry.pmx.editing.output._hash_file",
            side_effect=mismatching_temp_hash,
        ):
            with self.assertRaisesRegex(
                PmxStructuralOutputVerificationError,
                "temporary PMX",
            ):
                write_pmx_structural_transform(
                    self.input_path,
                    output,
                    self.changed_intent,
                )

        self.assertFalse(output.exists())
        self.assertEqual(self.input_path.read_bytes(), self.source_bytes)
        self.assertEqual(self.temporary_outputs(output), [])

    def test_source_precommit_verification_failure_is_translated(self) -> None:
        output = self.root / "source-race.pmx"

        with patch(
            "mmd_registry.pmx.editing.output._verify_source_unchanged",
            side_effect=PmxEditVerificationError(
                "source SHA-256 changed before output commit."
            ),
        ):
            with self.assertRaisesRegex(
                PmxStructuralOutputVerificationError,
                "source SHA-256",
            ):
                write_pmx_structural_transform(
                    self.input_path,
                    output,
                    self.changed_intent,
                )

        self.assertFalse(output.exists())
        self.assertEqual(self.temporary_outputs(output), [])

    def test_fsync_failure_cleans_temporary_output(self) -> None:
        output = self.root / "fsync-failure.pmx"

        with patch(
            "mmd_registry.pmx.editing.output.os.fsync",
            side_effect=OSError("simulated fsync failure"),
        ):
            with self.assertRaisesRegex(OSError, "fsync failure"):
                write_pmx_structural_transform(
                    self.input_path,
                    output,
                    self.changed_intent,
                )

        self.assertFalse(output.exists())
        self.assertEqual(self.input_path.read_bytes(), self.source_bytes)
        self.assertEqual(self.temporary_outputs(output), [])

    def test_wrong_overwrite_type_is_rejected(self) -> None:
        with self.assertRaisesRegex(TypeError, "overwrite"):
            write_pmx_structural_transform(
                self.input_path,
                self.root / "bad-overwrite.pmx",
                self.changed_intent,
                overwrite=1,  # type: ignore[arg-type]
            )

    def test_wrong_intent_type_is_rejected(self) -> None:
        with self.assertRaisesRegex(TypeError, "PmxStructuralTransformIntent"):
            write_pmx_structural_transform(  # type: ignore[arg-type]
                self.input_path,
                self.root / "bad-intent.pmx",
                object(),
            )

    def test_structural_trailing_data_blocks_before_output_commit(self) -> None:
        output = self.root / "trailing.pmx"
        unsafe = build_pmx_roundtrip_fixture()
        self.input_path.write_bytes(unsafe)

        with self.assertRaisesRegex(PmxStructuralInvariantError, "trailing_data"):
            write_pmx_structural_transform(
                self.input_path,
                output,
                PmxStructuralTransformIntent(),
            )

        self.assertFalse(output.exists())
        self.assertEqual(self.input_path.read_bytes(), unsafe)


class StructuralOutputPublicBoundaryTests(unittest.TestCase):
    def test_cp18_symbols_are_not_publicly_exported(self) -> None:
        forbidden = (
            "PmxStructuralOutputPathError",
            "PmxStructuralOutputVerificationError",
            "PmxStructuralSerializationResult",
            "PmxStructuralWriteResult",
            "verify_pmx_structural_serialization",
            "write_pmx_structural_transform",
        )
        for name in forbidden:
            with self.subTest(name=name):
                self.assertFalse(hasattr(pmx_public, name))
                self.assertFalse(hasattr(services_public, name))


if __name__ == "__main__":
    unittest.main()
