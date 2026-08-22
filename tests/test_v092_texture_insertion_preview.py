"""CP07 public and internal contracts for preview-only texture insertion."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from unittest.mock import patch

import mmd_registry.pmx as pmx_public
import mmd_registry.services as services
import mmd_registry.services.structural_texture as structural_texture_service
from mmd_registry.diagnostics import PmxServiceError, PmxServiceOperation
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.services.structural_texture import PmxStructuralTextureInsertion
from mmd_registry.pmx.structural_insert_intent import PmxStructuralInsertPosition
from mmd_registry.pmx.structural_texture_insertion import (
    PmxStructuralTextureInsertionError,
    PmxTextureInsertionPayload,
    preview_pmx_texture_insertions,
)
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


def _clean_document():
    return replace(
        load_pmx(io.BytesIO(build_pmx_roundtrip_fixture(version=2.1))),
        trailing_data=b"",
    )


def _shift_optional(index: int, anchor: int) -> int:
    if index == -1:
        return -1
    return index + 1 if index >= anchor else index


class TextureInsertionPublicContractTests(unittest.TestCase):
    def test_public_dto_is_additive_immutable_hashable_and_request_alias_survives(
        self,
    ) -> None:
        insertion = PmxStructuralTextureInsertion(
            path="textures/inserted.png",
        )
        request = services.PmxStructuralPreviewRequest(
            texture_insertions=(insertion,),
        )

        self.assertEqual(
            structural_texture_service.__all__,
            ("PmxStructuralTextureInsertion",),
        )
        self.assertFalse(hasattr(services, "PmxStructuralTextureInsertion"))
        self.assertIs(
            services.PmxStructuralEditRequest,
            services.PmxStructuralPreviewRequest,
        )
        self.assertEqual(request.collection_edits, ())
        self.assertEqual(request.texture_insertions, (insertion,))
        self.assertEqual(hash(insertion), hash(insertion))
        self.assertEqual(hash(request), hash(request))

        with self.assertRaises(FrozenInstanceError):
            insertion.path = "changed.png"  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            request.texture_insertions = ()  # type: ignore[misc]

        self.assertFalse(hasattr(pmx_public, "PmxStructuralTextureInsertion"))
        self.assertFalse(hasattr(services, "PmxTextureInsertionPayload"))
        self.assertFalse(hasattr(services, "PmxTextureInsertionPreview"))
        self.assertFalse(hasattr(services, "preview_pmx_texture_insertions"))

    def test_public_dto_and_request_reject_malformed_shapes_and_mixed_legacy_edits(
        self,
    ) -> None:
        with self.assertRaises(TypeError):
            PmxStructuralTextureInsertion(123)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            PmxStructuralTextureInsertion(
                "textures/a.png",
                position=1,  # type: ignore[arg-type]
            )
        with self.assertRaises(ValueError):
            PmxStructuralTextureInsertion(
                "textures/a.png",
                position="after",  # type: ignore[arg-type]
            )
        with self.assertRaises(ValueError):
            PmxStructuralTextureInsertion(
                "textures/a.png",
                source_index=0,
            )
        with self.assertRaises(TypeError):
            PmxStructuralTextureInsertion(
                "textures/a.png",
                position="insert_before",
            )
        with self.assertRaises(TypeError):
            PmxStructuralTextureInsertion(
                "textures/a.png",
                position="insert_before",
                source_index=True,  # type: ignore[arg-type]
            )
        with self.assertRaises(ValueError):
            PmxStructuralTextureInsertion(
                "textures/a.png",
                position="insert_before",
                source_index=-1,
            )

        insertion = PmxStructuralTextureInsertion("textures/a.png")
        with self.assertRaises(TypeError):
            services.PmxStructuralPreviewRequest(
                texture_insertions=[insertion],  # type: ignore[arg-type]
            )
        with self.assertRaises(TypeError):
            services.PmxStructuralPreviewRequest(
                texture_insertions=(object(),),  # type: ignore[arg-type]
            )

        edit = services.PmxStructuralCollectionEdit(
            services.PmxReferenceTargetKind.BONE,
            (),
        )
        with self.assertRaisesRegex(ValueError, "cannot be combined"):
            services.PmxStructuralPreviewRequest(
                collection_edits=(edit,),
                texture_insertions=(insertion,),
            )

    def test_legacy_constructor_shape_and_public_surface_suffix_remain_compatible(
        self,
    ) -> None:
        edit = services.PmxStructuralCollectionEdit(
            services.PmxReferenceTargetKind.TEXTURE,
            (),
        )
        request = services.PmxStructuralPreviewRequest((edit,))

        self.assertEqual(request.collection_edits, (edit,))
        self.assertEqual(request.texture_insertions, ())
        self.assertEqual(
            services.__all__[-7:],
            (
                "PmxStructuralCollectionEdit",
                "PmxStructuralPreviewRequest",
                "PmxStructuralPreviewResult",
                "preview_structural_edit",
                "PmxStructuralEditRequest",
                "PmxStructuralExecutionResult",
                "apply_structural_edit",
            ),
        )

    def test_capability_manifest_is_promoted_to_structural_insert(self) -> None:
        payload = services.get_capabilities().to_dict()

        self.assertTrue(payload["structural_preview"])
        self.assertTrue(payload["structural_write"])
        self.assertIs((payload)["structural_insert"], True)
        self.assertNotIn("PmxStructuralTextureInsertion", json.dumps(payload))


class TextureInsertionPreviewTests(unittest.TestCase):
    def test_append_preview_adds_path_without_reindexing_existing_material_references(
        self,
    ) -> None:
        source = _clean_document()
        insertion = PmxStructuralTextureInsertion(
            "textures/cp07-append.png",
        )
        request = services.PmxStructuralPreviewRequest(
            texture_insertions=(insertion,),
        )

        first = services.preview_structural_edit(source, request)
        second = services.preview_structural_edit(source, request)

        self.assertEqual(first.status, "changes_pending")
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(
            first.document.texture_paths,
            (*source.texture_paths, insertion.path),
        )
        self.assertEqual(first.document.materials, source.materials)
        self.assertEqual(source.texture_paths, _clean_document().texture_paths)
        self.assertIsNot(first.document, source)

        evidence = first.to_dict()
        self.assertEqual(evidence["preview_schema_version"], 2)
        self.assertEqual(evidence["verification"]["serialization"], "not_performed")
        self.assertFalse(evidence["output"]["written"])
        self.assertEqual(
            evidence["output"]["target_counts"]["texture"],
            len(source.texture_paths) + 1,
        )
        shift = evidence["audit"]["texture_insertion"]
        self.assertEqual(shift["insert_count"], 1)
        self.assertEqual(
            shift["new_indices_in_request_order"],
            [len(source.texture_paths)],
        )
        self.assertEqual(
            shift["remap"]["targets"],
            list(range(len(source.texture_paths))),
        )
        self.assertNotIn(insertion.path, json.dumps(evidence))

    def test_insert_before_zero_shifts_every_existing_material_texture_reference(
        self,
    ) -> None:
        source = _clean_document()
        anchor = 0
        path = "textures/cp07-before-zero.png"
        result = services.preview_structural_edit(
            source,
            services.PmxStructuralPreviewRequest(
                texture_insertions=(
                    PmxStructuralTextureInsertion(
                        path,
                        position="insert_before",
                        source_index=anchor,
                    ),
                ),
            ),
        )
        output = result.document

        self.assertEqual(output.texture_paths[0], path)
        self.assertEqual(output.texture_paths[1:], source.texture_paths)

        saw_reference = False
        for original, rewritten in zip(
            source.materials,
            output.materials,
            strict=True,
        ):
            self.assertEqual(
                rewritten.texture_index,
                _shift_optional(original.texture_index, anchor),
            )
            self.assertEqual(
                rewritten.sphere_texture_index,
                _shift_optional(original.sphere_texture_index, anchor),
            )
            if original.toon_reference_mode == "texture":
                self.assertEqual(
                    rewritten.toon_reference_index,
                    _shift_optional(original.toon_reference_index, anchor),
                )
                saw_reference = saw_reference or original.toon_reference_index >= 0
            else:
                self.assertEqual(
                    rewritten.toon_reference_index,
                    original.toon_reference_index,
                )
            saw_reference = saw_reference or any(
                value >= 0
                for value in (
                    original.texture_index,
                    original.sphere_texture_index,
                )
            )
        self.assertTrue(saw_reference)

    def test_same_anchor_and_append_preserve_request_association_and_order(
        self,
    ) -> None:
        source = _clean_document()
        self.assertGreaterEqual(len(source.texture_paths), 2)
        anchor = 1
        paths = (
            "textures/first.png",
            "textures/second.png",
            "textures/append.png",
        )
        request = services.PmxStructuralPreviewRequest(
            texture_insertions=(
                PmxStructuralTextureInsertion(
                    paths[0],
                    position="insert_before",
                    source_index=anchor,
                ),
                PmxStructuralTextureInsertion(
                    paths[1],
                    position="insert_before",
                    source_index=anchor,
                ),
                PmxStructuralTextureInsertion(paths[2]),
            ),
        )

        result = services.preview_structural_edit(source, request)
        expected = (
            *source.texture_paths[:anchor],
            paths[0],
            paths[1],
            *source.texture_paths[anchor:],
            paths[2],
        )
        self.assertEqual(result.document.texture_paths, expected)

        shift = result.to_dict()["audit"]["texture_insertion"]
        self.assertEqual(
            shift["new_indices_in_request_order"],
            [anchor, anchor + 1, len(expected) - 1],
        )

    def test_out_of_range_insert_before_is_structured_preview_failure(self) -> None:
        source = _clean_document()
        request = services.PmxStructuralPreviewRequest(
            texture_insertions=(
                PmxStructuralTextureInsertion(
                    "textures/oob.png",
                    position="insert_before",
                    source_index=len(source.texture_paths),
                ),
            ),
        )

        with self.assertRaises(PmxServiceError) as raised:
            services.preview_structural_edit(source, request)

        self.assertEqual(
            raised.exception.diagnostic.operation,
            PmxServiceOperation.PREVIEW_STRUCTURAL_EDIT,
        )
        self.assertNotIn("textures/oob.png", repr(raised.exception.to_dict()))

    def test_new_path_reuses_portable_policy_and_source_encoding_without_normalization(
        self,
    ) -> None:
        source = _clean_document()

        for invalid_path in (
            "",
            "textures/body\x00.png",
            r"C:\models\body.png",
            "../body.png",
        ):
            with self.subTest(invalid_path=invalid_path):
                request = services.PmxStructuralPreviewRequest(
                    texture_insertions=(
                        PmxStructuralTextureInsertion(invalid_path),
                    ),
                )
                with self.assertRaises(PmxServiceError):
                    services.preview_structural_edit(source, request)

        request = services.PmxStructuralPreviewRequest(
            texture_insertions=(
                PmxStructuralTextureInsertion("textures/\ud800.png"),
            ),
        )
        with self.assertRaises(PmxServiceError) as raised:
            services.preview_structural_edit(source, request)
        self.assertNotIn("\\ud800", repr(raised.exception.to_dict()))

        raw = r"textures\characters/new.png"
        accepted = services.preview_structural_edit(
            source,
            services.PmxStructuralPreviewRequest(
                texture_insertions=(PmxStructuralTextureInsertion(raw),),
            ),
        )
        self.assertEqual(accepted.document.texture_paths[-1], raw)

    def test_parser_path_byte_limit_is_enforced_before_materialization(self) -> None:
        source = _clean_document()
        payload = PmxTextureInsertionPayload(
            path="textures/long-name.png",
            position=PmxStructuralInsertPosition.append(),
        )

        with patch(
            "mmd_registry.pmx.structural_texture_insertion."
            "MAX_PMX_TEXTURE_PATH_BYTES",
            4,
        ):
            with self.assertRaisesRegex(
                PmxStructuralTextureInsertionError,
                "parser safety limit",
            ):
                preview_pmx_texture_insertions(source, (payload,))

    def test_parser_texture_count_limit_fails_before_reference_shift_allocation(
        self,
    ) -> None:
        source = _clean_document()
        payload = PmxTextureInsertionPayload(
            path="textures/count-limit.png",
            position=PmxStructuralInsertPosition.append(),
        )

        with (
            patch(
                "mmd_registry.pmx.structural_texture_insertion.MAX_PMX_TEXTURE_COUNT",
                len(source.texture_paths),
            ),
            patch(
                "mmd_registry.pmx.structural_texture_insertion."
                "plan_collection_reference_shift",
                side_effect=AssertionError("planner must not run"),
            ) as planner,
        ):
            with self.assertRaisesRegex(
                PmxStructuralTextureInsertionError,
                "texture parser safety limit",
            ):
                preview_pmx_texture_insertions(source, (payload,))
        planner.assert_not_called()

    def test_declared_texture_index_width_capacity_is_enforced(self) -> None:
        source = _clean_document()
        texture_paths = tuple(f"textures/{index}.png" for index in range(128))
        constrained = replace(
            source,
            header=replace(
                source.header,
                index_sizes=replace(source.header.index_sizes, texture=1),
            ),
            texture_paths=texture_paths,
        )

        request = services.PmxStructuralPreviewRequest(
            texture_insertions=(
                PmxStructuralTextureInsertion("textures/overflow.png"),
            ),
        )
        with self.assertRaises(PmxServiceError):
            services.preview_structural_edit(constrained, request)

    def test_empty_texture_source_supports_append_but_not_insert_before(self) -> None:
        source = _clean_document()
        materials = tuple(
            replace(
                material,
                texture_index=-1,
                sphere_texture_index=-1,
                toon_reference_mode="shared",
                toon_reference_index=0,
            )
            for material in source.materials
        )
        empty = replace(source, texture_paths=(), materials=materials)

        appended = services.preview_structural_edit(
            empty,
            services.PmxStructuralPreviewRequest(
                texture_insertions=(
                    PmxStructuralTextureInsertion("textures/first.png"),
                ),
            ),
        )
        self.assertEqual(appended.document.texture_paths, ("textures/first.png",))

        invalid = services.PmxStructuralPreviewRequest(
            texture_insertions=(
                PmxStructuralTextureInsertion(
                    "textures/first.png",
                    position="insert_before",
                    source_index=0,
                ),
            ),
        )
        with self.assertRaises(PmxServiceError):
            services.preview_structural_edit(empty, invalid)

    def test_apply_refuses_texture_insertion_before_source_or_destination_io(
        self,
    ) -> None:
        request = services.PmxStructuralPreviewRequest(
            texture_insertions=(
                PmxStructuralTextureInsertion("textures/preview-only.png"),
            ),
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing_source = root / "missing-source.pmx"
            output = root / "must-not-exist.pmx"

            with self.assertRaises(PmxServiceError) as raised:
                services.apply_structural_edit(
                    missing_source,
                    output,
                    request,
                )

            self.assertEqual(
                raised.exception.diagnostic.operation,
                PmxServiceOperation.APPLY_STRUCTURAL_EDIT,
            )
            self.assertFalse(output.exists())
            self.assertFalse(missing_source.exists())

    def test_insertion_preview_has_no_filesystem_side_effects(self) -> None:
        source = _clean_document()
        request = services.PmxStructuralPreviewRequest(
            texture_insertions=(
                PmxStructuralTextureInsertion("textures/no-io.png"),
            ),
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sentinel = root / "sentinel.bin"
            sentinel.write_bytes(b"unchanged")
            before = tuple(root.iterdir())

            services.preview_structural_edit(source, request)

            self.assertEqual(tuple(root.iterdir()), before)
            self.assertEqual(sentinel.read_bytes(), b"unchanged")


if __name__ == "__main__":
    unittest.main()
