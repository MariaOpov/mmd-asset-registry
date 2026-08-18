"""v0.9.1 texture structural-execution regression gates."""

from __future__ import annotations

import io
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from mmd_registry.pmx.collection_transform import (
    PmxCollectionTransform,
    PmxStructuralTransformIntent,
)
from mmd_registry.pmx.geometry_material_remap import PmxReferenceRemapError
from mmd_registry.pmx.index_remap import PmxIndexRemap
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.pmx.structural_orchestrator import PmxStructuralTransformError
from mmd_registry.pmx.structural_output import (
    verify_pmx_structural_serialization,
    write_pmx_structural_transform,
)
from mmd_registry.pmx.structural_preview import preview_pmx_structural_transform
from mmd_registry.pmx.writer import serialize_pmx
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


def _clean_document():
    return replace(
        load_pmx(io.BytesIO(build_pmx_roundtrip_fixture(version=2.1))),
        trailing_data=b"",
    )


def _texture_transform(
    targets: tuple[int | None, ...],
    new_size: int,
) -> PmxCollectionTransform:
    return PmxCollectionTransform(
        kind=PmxReferenceTargetKind.TEXTURE,
        remap=PmxIndexRemap(targets=targets, new_size=new_size),
    )


def _texture_reverse_intent(document) -> PmxStructuralTransformIntent:
    size = len(document.texture_paths)
    return PmxStructuralTransformIntent(
        transforms=(
            _texture_transform(tuple(reversed(range(size))), size),
        )
    )


def _texture_delete_intent(document, deleted_index: int) -> PmxStructuralTransformIntent:
    size = len(document.texture_paths)
    if not 0 <= deleted_index < size:
        raise AssertionError("deleted texture index must be inside the fixture domain")
    targets = tuple(
        None
        if old_index == deleted_index
        else old_index
        if old_index < deleted_index
        else old_index - 1
        for old_index in range(size)
    )
    return PmxStructuralTransformIntent(
        transforms=(
            _texture_transform(targets, size - 1),
        )
    )


def _mapped_optional(index: int, transform: PmxCollectionTransform) -> int:
    if index == -1:
        return -1
    mapped = transform.remap.target_for(index)
    if mapped is None:
        raise AssertionError("test expected a surviving referenced texture")
    return mapped


def _texture_references(material) -> tuple[int, ...]:
    values = [material.texture_index, material.sphere_texture_index]
    if material.toon_reference_mode == "texture":
        values.append(material.toon_reference_index)
    return tuple(index for index in values if index >= 0)


def _clear_texture_reference(material, texture_index: int):
    updates: dict[str, int] = {}
    if material.texture_index == texture_index:
        updates["texture_index"] = -1
    if material.sphere_texture_index == texture_index:
        updates["sphere_texture_index"] = -1
    if (
        material.toon_reference_mode == "texture"
        and material.toon_reference_index == texture_index
    ):
        updates["toon_reference_index"] = -1
    return replace(material, **updates) if updates else material


class V091TextureStructuralExecutionTests(unittest.TestCase):
    """Freeze end-to-end texture keep/delete/reorder execution semantics."""

    def test_explicit_texture_identity_matches_implicit_noop_preview(self) -> None:
        source = _clean_document()
        size = len(source.texture_paths)
        explicit = PmxStructuralTransformIntent(
            transforms=(
                PmxCollectionTransform.identity(
                    PmxReferenceTargetKind.TEXTURE,
                    size,
                ),
            )
        )

        implicit_preview = preview_pmx_structural_transform(
            source,
            PmxStructuralTransformIntent(),
        )
        explicit_preview = preview_pmx_structural_transform(source, explicit)

        self.assertEqual(explicit_preview.status, "no_changes")
        self.assertEqual(explicit_preview.to_dict(), implicit_preview.to_dict())
        self.assertEqual(
            explicit_preview.intent_sha256,
            implicit_preview.intent_sha256,
        )
        self.assertIs(explicit_preview.certificate.document, source)

    def test_texture_reorder_reorders_paths_and_remaps_all_material_texture_refs(self) -> None:
        source = _clean_document()
        intent = _texture_reverse_intent(source)
        transform = intent.transforms[0]
        preview = preview_pmx_structural_transform(source, intent)
        result = preview.certificate.document

        self.assertEqual(
            result.texture_paths,
            tuple(reversed(source.texture_paths)),
        )
        self.assertEqual(len(result.materials), len(source.materials))

        saw_real_texture_reference = False
        for original, rewritten in zip(
            source.materials,
            result.materials,
            strict=True,
        ):
            self.assertEqual(
                rewritten.texture_index,
                _mapped_optional(original.texture_index, transform),
            )
            self.assertEqual(
                rewritten.sphere_texture_index,
                _mapped_optional(original.sphere_texture_index, transform),
            )
            saw_real_texture_reference = saw_real_texture_reference or any(
                index >= 0
                for index in (
                    original.texture_index,
                    original.sphere_texture_index,
                )
            )

            if original.toon_reference_mode == "texture":
                self.assertEqual(
                    rewritten.toon_reference_index,
                    _mapped_optional(original.toon_reference_index, transform),
                )
                saw_real_texture_reference = (
                    saw_real_texture_reference
                    or original.toon_reference_index >= 0
                )
            else:
                self.assertEqual(original.toon_reference_mode, "shared")
                self.assertEqual(
                    rewritten.toon_reference_index,
                    original.toon_reference_index,
                )

            self.assertEqual(
                replace(
                    rewritten,
                    texture_index=original.texture_index,
                    sphere_texture_index=original.sphere_texture_index,
                    toon_reference_index=original.toon_reference_index,
                ),
                original,
            )

        self.assertTrue(saw_real_texture_reference)

    def test_texture_reorder_changes_only_texture_target_kind(self) -> None:
        source = _clean_document()
        preview = preview_pmx_structural_transform(
            source,
            _texture_reverse_intent(source),
        )

        self.assertEqual(
            preview.audit.changed_kinds,
            (PmxReferenceTargetKind.TEXTURE,),
        )
        self.assertEqual(len(preview.audit.collections), 6)
        texture_audit = preview.audit.collections[1]
        self.assertIs(texture_audit.kind, PmxReferenceTargetKind.TEXTURE)
        self.assertTrue(texture_audit.transform.has_reorder)
        self.assertFalse(texture_audit.transform.has_deletions)

    def test_texture_reorder_serialization_reparses_to_certified_preview(self) -> None:
        source = _clean_document()
        intent = _texture_reverse_intent(source)
        independent = preview_pmx_structural_transform(source, intent)
        serialization = verify_pmx_structural_serialization(source, intent)

        self.assertEqual(
            serialization.preview.to_dict(),
            independent.to_dict(),
        )
        self.assertEqual(
            serialization.reparsed_certificate.document,
            independent.certificate.document,
        )
        self.assertEqual(
            serialization.reparsed_certificate.reference_graph.invalid_targets,
            (),
        )
        self.assertEqual(
            serialization.reparsed_certificate.reference_graph.unsupported_states,
            (),
        )

    def test_texture_reorder_write_is_distinct_verified_and_source_immutable(self) -> None:
        source = _clean_document()
        source_bytes = serialize_pmx(source)
        intent = _texture_reverse_intent(source)
        independent = preview_pmx_structural_transform(source, intent)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "source.pmx"
            output_path = root / "texture-reorder.pmx"
            input_path.write_bytes(source_bytes)

            result = write_pmx_structural_transform(
                input_path,
                output_path,
                intent,
            )

            self.assertEqual(result.status, "written")
            self.assertEqual(load_pmx(output_path), independent.certificate.document)
            self.assertEqual(
                output_path.read_bytes(),
                result.serialization.serialized_bytes,
            )
            self.assertEqual(input_path.read_bytes(), source_bytes)
            self.assertNotEqual(input_path.resolve(), output_path.resolve())

    def test_safe_unreferenced_texture_deletion_executes_without_width_resize(self) -> None:
        source = _clean_document()
        self.assertGreaterEqual(len(source.texture_paths), 1)
        deleted_index = len(source.texture_paths) - 1
        materials = tuple(
            _clear_texture_reference(material, deleted_index)
            for material in source.materials
        )
        source = replace(source, materials=materials)
        self.assertTrue(
            all(
                deleted_index not in _texture_references(material)
                for material in source.materials
            )
        )

        source_bytes = serialize_pmx(source)
        intent = _texture_delete_intent(source, deleted_index)
        independent = preview_pmx_structural_transform(source, intent)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "source.pmx"
            output_path = root / "texture-delete.pmx"
            input_path.write_bytes(source_bytes)

            result = write_pmx_structural_transform(
                input_path,
                output_path,
                intent,
            )
            written = load_pmx(output_path)

            self.assertEqual(written, independent.certificate.document)
            self.assertEqual(
                len(written.texture_paths),
                len(source.texture_paths) - 1,
            )
            self.assertEqual(
                written.header.index_sizes.texture,
                source.header.index_sizes.texture,
            )
            self.assertEqual(
                result.serialization.reparsed_certificate.reference_graph.invalid_targets,
                (),
            )
            self.assertEqual(input_path.read_bytes(), source_bytes)

    def test_deleting_referenced_texture_fails_closed_before_output(self) -> None:
        source = _clean_document()
        referenced = sorted(
            {
                index
                for material in source.materials
                for index in _texture_references(material)
            }
        )
        self.assertTrue(referenced)
        deleted_index = referenced[0]
        source_bytes = serialize_pmx(source)
        intent = _texture_delete_intent(source, deleted_index)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "source.pmx"
            output_path = root / "must-not-exist.pmx"
            input_path.write_bytes(source_bytes)

            with self.assertRaisesRegex(
                PmxReferenceRemapError,
                rf"references removed texture index {deleted_index}",
            ):
                write_pmx_structural_transform(
                    input_path,
                    output_path,
                    intent,
                )

            self.assertFalse(output_path.exists())
            self.assertEqual(input_path.read_bytes(), source_bytes)
            self.assertEqual(
                list(root.glob(f".{output_path.name}.*.tmp")),
                [],
            )

    def test_sentinels_and_shared_toon_stay_outside_texture_remap_domain(self) -> None:
        source = _clean_document()
        self.assertTrue(source.materials)
        first = replace(
            source.materials[0],
            texture_index=-1,
            sphere_texture_index=-1,
            toon_reference_mode="shared",
            toon_reference_index=9,
        )
        source = replace(
            source,
            materials=(first, *source.materials[1:]),
        )

        preview = preview_pmx_structural_transform(
            source,
            _texture_reverse_intent(source),
        )
        rewritten = preview.certificate.document.materials[0]

        self.assertEqual(rewritten.texture_index, -1)
        self.assertEqual(rewritten.sphere_texture_index, -1)
        self.assertEqual(rewritten.toon_reference_mode, "shared")
        self.assertEqual(rewritten.toon_reference_index, 9)

    def test_texture_transform_old_size_mismatch_fails_closed(self) -> None:
        source = _clean_document()
        size = len(source.texture_paths)
        bad_intent = PmxStructuralTransformIntent(
            transforms=(
                PmxCollectionTransform.identity(
                    PmxReferenceTargetKind.TEXTURE,
                    size + 1,
                ),
            )
        )

        with self.assertRaisesRegex(
            PmxStructuralTransformError,
            r"texture transform old_size .* does not match source collection size",
        ):
            preview_pmx_structural_transform(source, bad_intent)

    def test_texture_insertion_mapping_is_not_authorized(self) -> None:
        source = _clean_document()
        size = len(source.texture_paths)
        insertion_capable = PmxIndexRemap(
            targets=tuple(range(size)),
            new_size=size + 1,
            new_indices_without_old_source=(size,),
        )

        with self.assertRaisesRegex(
            ValueError,
            r"do not authorize new indices without old sources",
        ):
            PmxCollectionTransform(
                PmxReferenceTargetKind.TEXTURE,
                insertion_capable,
            )

    def test_texture_execution_fails_closed_on_opaque_trailing_data(self) -> None:
        unsafe = load_pmx(io.BytesIO(build_pmx_roundtrip_fixture(version=2.1)))
        self.assertTrue(unsafe.trailing_data)
        intent = _texture_reverse_intent(unsafe)

        with self.assertRaisesRegex(
            PmxStructuralTransformError,
            "trailing_data",
        ):
            verify_pmx_structural_serialization(unsafe, intent)


if __name__ == "__main__":
    unittest.main()
