"""v0.9.1 post-write reparse and reference-certification regression gates."""

from __future__ import annotations

import hashlib
import io
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from mmd_registry.pmx.collection_transform import (
    PmxCollectionTransform,
    PmxStructuralTransformIntent,
)
from mmd_registry.pmx.index_remap import PmxIndexRemap
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.pmx.structural_invariants import PmxStructuralInvariantCertificate
from mmd_registry.pmx.structural_orchestrator import PmxStructuralTransformError
from mmd_registry.pmx.structural_output import (
    PmxStructuralOutputVerificationError,
    PmxStructuralWriteResult,
    verify_pmx_structural_serialization,
    write_pmx_structural_transform,
)
from mmd_registry.pmx.writer import serialize_pmx
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


TARGET_KINDS = tuple(PmxReferenceTargetKind)


def _clean_document():
    return replace(
        load_pmx(io.BytesIO(build_pmx_roundtrip_fixture(version=2.1))),
        trailing_data=b"",
    )


def _target_size(document, kind: PmxReferenceTargetKind) -> int:
    if kind is PmxReferenceTargetKind.VERTEX:
        return len(document.vertices)
    if kind is PmxReferenceTargetKind.TEXTURE:
        return len(document.texture_paths)
    if kind is PmxReferenceTargetKind.MATERIAL:
        return len(document.materials)
    if kind is PmxReferenceTargetKind.BONE:
        return len(document.bones)
    if kind is PmxReferenceTargetKind.MORPH:
        return len(document.morphs)
    if kind is PmxReferenceTargetKind.RIGID_BODY:
        return len(document.rigid_bodies)
    raise AssertionError(f"unhandled target kind {kind!r}")


def _reverse(document, kind: PmxReferenceTargetKind) -> PmxCollectionTransform:
    size = _target_size(document, kind)
    return PmxCollectionTransform(
        kind=kind,
        remap=PmxIndexRemap(
            targets=tuple(reversed(range(size))),
            new_size=size,
        ),
    )


def _full_reverse_intent(document) -> PmxStructuralTransformIntent:
    return PmxStructuralTransformIntent(
        transforms=tuple(_reverse(document, kind) for kind in TARGET_KINDS)
    )


class V091PostWriteReparseCertificationTests(unittest.TestCase):
    """Freeze the post-serialization trust boundary before filesystem publication."""

    def test_reparsed_certificate_is_fresh_and_semantically_equal(self) -> None:
        source = _clean_document()
        result = verify_pmx_structural_serialization(
            source,
            _full_reverse_intent(source),
        )

        self.assertIsInstance(
            result.reparsed_certificate,
            PmxStructuralInvariantCertificate,
        )
        self.assertIsNot(
            result.reparsed_certificate,
            result.preview.certificate,
        )
        self.assertIsNot(
            result.reparsed_certificate.document,
            result.preview.certificate.document,
        )
        self.assertEqual(
            result.reparsed_certificate.document,
            result.preview.certificate.document,
        )

    def test_reparsed_reference_graph_is_fresh_clean_and_matches_target_counts(self) -> None:
        source = _clean_document()
        result = verify_pmx_structural_serialization(
            source,
            _full_reverse_intent(source),
        )

        reparsed = result.reparsed_certificate
        preview = result.preview.certificate

        self.assertIsNot(reparsed.reference_graph, preview.reference_graph)
        self.assertEqual(reparsed.reference_graph.invalid_targets, ())
        self.assertEqual(reparsed.reference_graph.unsupported_states, ())
        self.assertEqual(
            reparsed.reference_graph.target_counts,
            preview.reference_graph.target_counts,
        )
        self.assertEqual(
            reparsed.relationship_counts,
            preview.relationship_counts,
        )

    def test_full_reverse_verified_bytes_are_deterministic_and_hash_exact(self) -> None:
        source = _clean_document()
        intent = _full_reverse_intent(source)

        first = verify_pmx_structural_serialization(source, intent)
        second = verify_pmx_structural_serialization(source, intent)

        self.assertEqual(first.serialized_bytes, second.serialized_bytes)
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(
            first.output_sha256,
            hashlib.sha256(first.serialized_bytes).hexdigest(),
        )
        self.assertEqual(first.output_size_bytes, len(first.serialized_bytes))

    def test_noop_still_reparses_and_receives_fresh_certificate(self) -> None:
        source = _clean_document()

        result = verify_pmx_structural_serialization(
            source,
            PmxStructuralTransformIntent(),
        )

        self.assertEqual(result.status, "no_changes")
        self.assertIs(result.preview.certificate.document, source)
        self.assertIsNot(result.reparsed_certificate.document, source)
        self.assertEqual(result.reparsed_certificate.document, source)
        self.assertEqual(result.reparsed_certificate.reference_graph.invalid_targets, ())
        self.assertEqual(
            result.reparsed_certificate.reference_graph.unsupported_states,
            (),
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
                    _full_reverse_intent(source),
                )

    def test_semantic_mismatch_after_reparse_fails_closed(self) -> None:
        source = _clean_document()
        mismatched = replace(
            source,
            model_info=replace(
                source.model_info,
                local_name=source.model_info.local_name + " mismatch",
            ),
        )

        with patch(
            "mmd_registry.pmx.structural_output.load_pmx",
            return_value=mismatched,
        ):
            with self.assertRaisesRegex(
                PmxStructuralOutputVerificationError,
                "does not match the intended certified document",
            ):
                verify_pmx_structural_serialization(
                    source,
                    PmxStructuralTransformIntent(),
                )

    def test_invalid_reparsed_document_fails_complete_certification(self) -> None:
        source = _clean_document()
        invalid = replace(
            source,
            rigid_bodies=(
                replace(source.rigid_bodies[0], mass=-1.0),
                *source.rigid_bodies[1:],
            ),
        )

        with patch(
            "mmd_registry.pmx.structural_output.load_pmx",
            return_value=invalid,
        ):
            with self.assertRaisesRegex(
                PmxStructuralOutputVerificationError,
                "failed complete invariant certification",
            ):
                verify_pmx_structural_serialization(
                    source,
                    PmxStructuralTransformIntent(),
                )

    def test_verification_failure_prevents_atomic_commit_and_preserves_source(self) -> None:
        source = _clean_document()
        source_bytes = serialize_pmx(source)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "source.pmx"
            output_path = root / "must-not-exist.pmx"
            input_path.write_bytes(source_bytes)

            failure = PmxStructuralOutputVerificationError(
                "simulated pre-publication verification failure"
            )
            with patch(
                "mmd_registry.pmx.structural_output.verify_pmx_structural_serialization",
                side_effect=failure,
            ), patch(
                "mmd_registry.pmx.structural_output._edit_output._commit_verified_bytes"
            ) as commit:
                with self.assertRaisesRegex(
                    PmxStructuralOutputVerificationError,
                    "pre-publication verification failure",
                ):
                    write_pmx_structural_transform(
                        input_path,
                        output_path,
                        _full_reverse_intent(source),
                    )

            commit.assert_not_called()
            self.assertFalse(output_path.exists())
            self.assertEqual(input_path.read_bytes(), source_bytes)
            self.assertEqual(
                list(root.glob(f".{output_path.name}.*.tmp")),
                [],
            )

    def test_successful_write_publishes_exact_post_reparse_verified_bytes(self) -> None:
        source = _clean_document()
        source_bytes = serialize_pmx(source)
        intent = _full_reverse_intent(source)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "source.pmx"
            output_path = root / "verified-output.pmx"
            input_path.write_bytes(source_bytes)

            result = write_pmx_structural_transform(
                input_path,
                output_path,
                intent,
            )

            self.assertEqual(
                output_path.read_bytes(),
                result.serialization.serialized_bytes,
            )
            self.assertEqual(
                load_pmx(output_path),
                result.serialization.reparsed_certificate.document,
            )
            self.assertEqual(
                result.serialization.reparsed_certificate.document,
                result.serialization.preview.certificate.document,
            )
            self.assertEqual(input_path.read_bytes(), source_bytes)

    def test_direct_write_result_construction_is_blocked(self) -> None:
        with self.assertRaisesRegex(
            TypeError,
            r"cannot be constructed directly",
        ):
            PmxStructuralWriteResult()

    def test_opaque_trailing_data_fails_before_serialization(self) -> None:
        unsafe = load_pmx(io.BytesIO(build_pmx_roundtrip_fixture(version=2.1)))
        self.assertTrue(unsafe.trailing_data)

        with patch("mmd_registry.pmx.structural_output.serialize_pmx") as serializer:
            with self.assertRaisesRegex(
                PmxStructuralTransformError,
                "trailing_data",
            ):
                verify_pmx_structural_serialization(
                    unsafe,
                    _full_reverse_intent(unsafe),
                )

        serializer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
