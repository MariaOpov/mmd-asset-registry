"""v0.9.1 structural execution contract regression gates."""

from __future__ import annotations

import io
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import mmd_registry.pmx as pmx_public
import mmd_registry.services as services_public
from mmd_registry.pmx.collection_transform import (
    PmxCollectionTransform,
    PmxStructuralTransformIntent,
)
from mmd_registry.pmx.index_remap import PmxIndexRemap
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.pmx.structural_invariants import PmxStructuralInvariantError
from mmd_registry.pmx.structural_output import (
    PmxStructuralOutputPathError,
    verify_pmx_structural_serialization,
    write_pmx_structural_transform,
)
from mmd_registry.pmx.structural_preview import preview_pmx_structural_transform
from mmd_registry.pmx.writer import serialize_pmx
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _clean_document():
    return replace(
        load_pmx(io.BytesIO(build_pmx_roundtrip_fixture(version=2.1))),
        trailing_data=b"",
    )


def _texture_reverse_intent(document) -> PmxStructuralTransformIntent:
    size = len(document.texture_paths)
    return PmxStructuralTransformIntent(
        transforms=(
            PmxCollectionTransform(
                kind=PmxReferenceTargetKind.TEXTURE,
                remap=PmxIndexRemap(
                    targets=tuple(reversed(range(size))),
                    new_size=size,
                ),
            ),
        )
    )


class V091StructuralExecutionContractTests(unittest.TestCase):
    """Freeze safety semantics around the reviewed public execution service."""

    def test_threat_model_tracks_all_frozen_threat_ids(self) -> None:
        text = (
            PROJECT_ROOT / "docs" / "structural_execution_contract.md"
        ).read_text(encoding="utf-8")

        for number in range(1, 19):
            with self.subTest(threat_id=number):
                self.assertIn(f"T{number:02d}", text)

    def test_raw_structural_writer_is_not_in_canonical_public_namespaces(self) -> None:
        forbidden = (
            "PmxStructuralWriteResult",
            "verify_pmx_structural_serialization",
            "write_pmx_structural_transform",
        )
        for name in forbidden:
            with self.subTest(name=name):
                self.assertFalse(hasattr(pmx_public, name))
                self.assertFalse(hasattr(services_public, name))


    def test_reviewed_service_is_public_but_raw_kernel_remains_private(self) -> None:
        self.assertIn("apply_structural_edit", services_public.__all__)
        self.assertIn("PmxStructuralExecutionResult", services_public.__all__)
        self.assertFalse(hasattr(services_public, "write_pmx_structural_transform"))
        self.assertFalse(hasattr(services_public, "PmxStructuralWriteResult"))
        self.assertTrue(services_public.get_capabilities().structural_write)

    def test_insertion_capable_collection_transform_is_out_of_contract(self) -> None:
        remap = PmxIndexRemap(
            targets=(0,),
            new_size=2,
            new_indices_without_old_source=(1,),
        )
        with self.assertRaisesRegex(ValueError, "do not authorize new indices"):
            PmxCollectionTransform(
                kind=PmxReferenceTargetKind.TEXTURE,
                remap=remap,
            )

    def test_preview_serialization_and_execution_share_one_intended_document(
        self,
    ) -> None:
        document = _clean_document()
        intent = _texture_reverse_intent(document)
        preview = preview_pmx_structural_transform(document, intent)
        serialization = verify_pmx_structural_serialization(document, intent)

        self.assertEqual(serialization.preview.to_dict(), preview.to_dict())
        self.assertEqual(
            serialization.reparsed_certificate.document,
            preview.certificate.document,
        )

        source_bytes = serialize_pmx(document)
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(source_bytes)

            result = write_pmx_structural_transform(source, output, intent)

            self.assertEqual(
                result.serialization.preview.to_dict(),
                preview.to_dict(),
            )
            self.assertEqual(
                load_pmx(output),
                preview.certificate.document,
            )
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_in_place_execution_is_refused_even_with_overwrite(self) -> None:
        document = _clean_document()
        intent = _texture_reverse_intent(document)

        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "source.pmx"
            original = serialize_pmx(document)
            source.write_bytes(original)

            with self.assertRaisesRegex(
                PmxStructuralOutputPathError,
                "different files",
            ):
                write_pmx_structural_transform(
                    source,
                    source,
                    intent,
                    overwrite=True,
                )

            self.assertEqual(source.read_bytes(), original)

    def test_opaque_trailing_data_fails_closed_even_for_noop_execution(self) -> None:
        unsafe_bytes = build_pmx_roundtrip_fixture()
        unsafe = load_pmx(io.BytesIO(unsafe_bytes))
        self.assertTrue(unsafe.trailing_data)

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source.pmx"
            output = root / "output.pmx"
            source.write_bytes(unsafe_bytes)

            with self.assertRaisesRegex(
                PmxStructuralInvariantError,
                "trailing_data",
            ):
                write_pmx_structural_transform(
                    source,
                    output,
                    PmxStructuralTransformIntent(),
                )

            self.assertEqual(source.read_bytes(), unsafe_bytes)
            self.assertFalse(output.exists())

    def test_existing_destination_is_preserved_without_overwrite(self) -> None:
        document = _clean_document()
        intent = _texture_reverse_intent(document)

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source.pmx"
            output = root / "existing.pmx"
            source_bytes = serialize_pmx(document)
            existing_bytes = b"existing-destination"
            source.write_bytes(source_bytes)
            output.write_bytes(existing_bytes)

            with self.assertRaisesRegex(
                PmxStructuralOutputPathError,
                "already exists",
            ):
                write_pmx_structural_transform(source, output, intent)

            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(output.read_bytes(), existing_bytes)


if __name__ == "__main__":
    unittest.main()
