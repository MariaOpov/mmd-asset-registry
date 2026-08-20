"""CP09 public and internal contracts for preview-only material insertion."""

from __future__ import annotations

import io
import json
import math
import tempfile
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from unittest.mock import patch

import mmd_registry.pmx as pmx_public
import mmd_registry.services as services
import mmd_registry.services.structural_material as structural_material_service
from mmd_registry.diagnostics import PmxServiceError, PmxServiceOperation
from mmd_registry.pmx.document import PmxMaterialMorphOffset
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.structural_insert_intent import PmxStructuralInsertPosition
from mmd_registry.pmx.structural_material_insertion import (
    PmxMaterialInsertionPayload,
    PmxStructuralMaterialInsertionError,
    preview_pmx_material_insertions,
)
from mmd_registry.services.structural_material import PmxStructuralMaterialInsertion
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


def _material_payload(
    name: str = "Inserted",
    *,
    position: PmxStructuralInsertPosition | None = None,
) -> PmxMaterialInsertionPayload:
    return PmxMaterialInsertionPayload(
        local_name=name,
        universal_name="",
        memo="",
        texture_index=-1,
        sphere_texture_index=-1,
        sphere_mode=0,
        toon_reference_mode="texture",
        toon_reference_index=-1,
        diffuse=(1.0, 1.0, 1.0, 1.0),
        specular=(0.0, 0.0, 0.0),
        specular_strength=0.0,
        ambient=(0.5, 0.5, 0.5),
        drawing_flags=0,
        edge_color=(0.0, 0.0, 0.0, 1.0),
        edge_scale=1.0,
        position=position or PmxStructuralInsertPosition.append(),
    )


def _clear_incoming_material_references(document):
    morphs = []
    for morph in document.morphs:
        if morph.morph_type != 8:
            morphs.append(morph)
            continue
        offsets = tuple(
            replace(offset, material_index=-1)
            if isinstance(offset, PmxMaterialMorphOffset)
            else offset
            for offset in morph.offsets
        )
        morphs.append(
            morph if offsets == morph.offsets else replace(morph, offsets=offsets)
        )

    soft_bodies = tuple(
        replace(body, material_index=-1)
        for body in document.soft_bodies
    )
    return replace(document, morphs=tuple(morphs), soft_bodies=soft_bodies)


class MaterialInsertionPublicContractTests(unittest.TestCase):
    def test_public_dto_is_additive_immutable_hashable_and_request_alias_survives(
        self,
    ) -> None:
        insertion = PmxStructuralMaterialInsertion(local_name="CP09")
        request = services.PmxStructuralPreviewRequest(
            material_insertions=(insertion,),
        )

        self.assertEqual(
            structural_material_service.__all__,
            ("PmxStructuralMaterialInsertion",),
        )
        self.assertFalse(hasattr(services, "PmxStructuralMaterialInsertion"))
        self.assertIs(
            services.PmxStructuralEditRequest,
            services.PmxStructuralPreviewRequest,
        )
        self.assertEqual(request.collection_edits, ())
        self.assertEqual(request.texture_insertions, ())
        self.assertEqual(request.material_insertions, (insertion,))
        self.assertEqual(hash(insertion), hash(insertion))
        self.assertEqual(hash(request), hash(request))

        with self.assertRaises(FrozenInstanceError):
            insertion.local_name = "changed"  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            request.material_insertions = ()  # type: ignore[misc]

        self.assertFalse(hasattr(pmx_public, "PmxStructuralMaterialInsertion"))
        self.assertFalse(hasattr(services, "PmxMaterialInsertionPayload"))
        self.assertFalse(hasattr(services, "PmxMaterialInsertionPreview"))
        self.assertFalse(hasattr(services, "preview_pmx_material_insertions"))
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

    def test_public_dto_rejects_raw_surface_ownership_and_malformed_values(self) -> None:
        with self.assertRaises(TypeError):
            PmxStructuralMaterialInsertion(123)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            PmxStructuralMaterialInsertion(
                local_name="A",
                surface_index_count=0,  # type: ignore[call-arg]
            )
        with self.assertRaises(TypeError):
            PmxStructuralMaterialInsertion(
                local_name="A",
                texture_index=True,  # type: ignore[arg-type]
            )
        with self.assertRaises(ValueError):
            PmxStructuralMaterialInsertion(
                local_name="A",
                toon_reference_mode="shared",
                toon_reference_index=10,
            )
        with self.assertRaises(ValueError):
            PmxStructuralMaterialInsertion(
                local_name="A",
                edge_scale=math.nan,
            )
        with self.assertRaises(ValueError):
            PmxStructuralMaterialInsertion(
                local_name="A",
                position="append",
                source_index=0,
            )
        with self.assertRaises(TypeError):
            PmxStructuralMaterialInsertion(
                local_name="A",
                position="insert_before",
            )
        with self.assertRaises(TypeError):
            PmxStructuralMaterialInsertion(
                local_name="A",
                position="insert_before",
                source_index=True,  # type: ignore[arg-type]
            )
        with self.assertRaises(ValueError):
            PmxStructuralMaterialInsertion(
                local_name="A",
                position="insert_before",
                source_index=-1,
            )

    def test_request_rejects_wrong_container_and_mixed_mutation_vocabularies(self) -> None:
        insertion = PmxStructuralMaterialInsertion(local_name="A")
        with self.assertRaises(TypeError):
            services.PmxStructuralPreviewRequest(
                material_insertions=[insertion],  # type: ignore[arg-type]
            )
        with self.assertRaises(TypeError):
            services.PmxStructuralPreviewRequest(
                material_insertions=(object(),),  # type: ignore[arg-type]
            )

        edit = services.PmxStructuralCollectionEdit(
            services.PmxReferenceTargetKind.MATERIAL,
            (),
        )
        with self.assertRaisesRegex(ValueError, "cannot be combined"):
            services.PmxStructuralPreviewRequest(
                collection_edits=(edit,),
                material_insertions=(insertion,),
            )

        from mmd_registry.services.structural_texture import (
            PmxStructuralTextureInsertion,
        )

        with self.assertRaisesRegex(ValueError, "cannot be combined"):
            services.PmxStructuralPreviewRequest(
                texture_insertions=(
                    PmxStructuralTextureInsertion("textures/a.png"),
                ),
                material_insertions=(insertion,),
            )

    def test_capability_manifest_is_not_promoted_to_structural_insert(self) -> None:
        payload = services.get_capabilities().to_dict()

        self.assertTrue(payload["structural_preview"])
        self.assertTrue(payload["structural_write"])
        self.assertNotIn("structural_insert", payload)
        self.assertNotIn("PmxStructuralMaterialInsertion", json.dumps(payload))


class MaterialInsertionPreviewTests(unittest.TestCase):
    def test_append_adds_zero_surface_material_without_changing_geometry(self) -> None:
        source = _clean_document()
        insertion = PmxStructuralMaterialInsertion(
            local_name="CP09 append",
            universal_name="Material",
            memo="private memo marker",
        )
        request = services.PmxStructuralPreviewRequest(
            material_insertions=(insertion,),
        )

        first = services.preview_structural_edit(source, request)
        second = services.preview_structural_edit(source, request)
        output = first.document

        self.assertEqual(first.status, "changes_pending")
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(output.materials[:-1], source.materials)
        self.assertEqual(output.materials[-1].local_name, insertion.local_name)
        self.assertEqual(output.materials[-1].surface_index_count, 0)
        self.assertEqual(output.surface_indices, source.surface_indices)
        self.assertIs(output.geometry, source.geometry)

        evidence = first.to_dict()
        self.assertEqual(evidence["preview_schema_version"], 1)
        self.assertFalse(evidence["output"]["written"])
        self.assertEqual(evidence["verification"]["serialization"], "not_performed")
        self.assertEqual(
            evidence["output"]["target_counts"]["material"],
            len(source.materials) + 1,
        )
        material_audit = evidence["audit"]["material_insertion"]
        self.assertFalse(material_audit["surface_stream_changed"])
        self.assertEqual(material_audit["inserted_surface_index_count"], 0)
        self.assertNotIn(insertion.local_name, json.dumps(evidence))
        self.assertNotIn(insertion.memo, json.dumps(evidence))

    def test_insert_before_shifts_existing_incoming_material_references(self) -> None:
        source = _clean_document()
        self.assertGreater(len(source.materials), 0)
        anchor = 0

        result = services.preview_structural_edit(
            source,
            services.PmxStructuralPreviewRequest(
                material_insertions=(
                    PmxStructuralMaterialInsertion(
                        local_name="Before zero",
                        position="insert_before",
                        source_index=anchor,
                    ),
                ),
            ),
        )
        output = result.document

        self.assertEqual(output.materials[0].local_name, "Before zero")
        self.assertEqual(output.materials[0].surface_index_count, 0)
        self.assertEqual(output.materials[1:], source.materials)
        self.assertEqual(output.surface_indices, source.surface_indices)

        saw_incoming_reference = False
        for source_morph, output_morph in zip(
            source.morphs,
            output.morphs,
            strict=True,
        ):
            self.assertEqual(source_morph.morph_type, output_morph.morph_type)
            for source_offset, output_offset in zip(
                source_morph.offsets,
                output_morph.offsets,
                strict=True,
            ):
                if isinstance(source_offset, PmxMaterialMorphOffset):
                    self.assertIsInstance(output_offset, PmxMaterialMorphOffset)
                    self.assertEqual(
                        output_offset.material_index,
                        _shift_optional(source_offset.material_index, anchor),
                    )
                    saw_incoming_reference = (
                        saw_incoming_reference or source_offset.material_index >= 0
                    )

        self.assertEqual(len(source.soft_bodies), len(output.soft_bodies))
        for source_body, output_body in zip(
            source.soft_bodies,
            output.soft_bodies,
            strict=True,
        ):
            self.assertEqual(
                output_body.material_index,
                _shift_optional(source_body.material_index, anchor),
            )
            self.assertEqual(output_body.anchors, source_body.anchors)
            self.assertEqual(
                output_body.pinned_vertex_indices,
                source_body.pinned_vertex_indices,
            )
            saw_incoming_reference = (
                saw_incoming_reference or source_body.material_index >= 0
            )

        self.assertTrue(
            saw_incoming_reference,
            "fixture must expose a material morph or soft-body material reference",
        )

    def test_same_anchor_and_append_preserve_request_order(self) -> None:
        source = _clean_document()
        self.assertGreaterEqual(len(source.materials), 1)
        anchor = 0
        names = ("First", "Second", "Append")

        result = services.preview_structural_edit(
            source,
            services.PmxStructuralPreviewRequest(
                material_insertions=(
                    PmxStructuralMaterialInsertion(
                        local_name=names[0],
                        position="insert_before",
                        source_index=anchor,
                    ),
                    PmxStructuralMaterialInsertion(
                        local_name=names[1],
                        position="insert_before",
                        source_index=anchor,
                    ),
                    PmxStructuralMaterialInsertion(local_name=names[2]),
                ),
            ),
        )

        self.assertEqual(
            tuple(material.local_name for material in result.document.materials[:2]),
            names[:2],
        )
        self.assertEqual(result.document.materials[2:-1], source.materials)
        self.assertEqual(result.document.materials[-1].local_name, names[2])
        shift = result.to_dict()["audit"]["material_insertion"]
        self.assertEqual(
            shift["new_indices_in_request_order"],
            [0, 1, len(result.document.materials) - 1],
        )

    def test_inserted_material_texture_references_use_existing_source_domain(self) -> None:
        source = _clean_document()
        self.assertGreater(len(source.texture_paths), 0)

        result = services.preview_structural_edit(
            source,
            services.PmxStructuralPreviewRequest(
                material_insertions=(
                    PmxStructuralMaterialInsertion(
                        local_name="Textured",
                        texture_index=0,
                        sphere_texture_index=0,
                        sphere_mode=1,
                        toon_reference_mode="texture",
                        toon_reference_index=0,
                    ),
                ),
            ),
        )
        inserted = result.document.materials[-1]

        self.assertEqual(inserted.texture_index, 0)
        self.assertEqual(inserted.sphere_texture_index, 0)
        self.assertEqual(inserted.toon_reference_index, 0)
        self.assertEqual(result.document.texture_paths, source.texture_paths)

        invalid = services.PmxStructuralPreviewRequest(
            material_insertions=(
                PmxStructuralMaterialInsertion(
                    local_name="Bad ref",
                    texture_index=len(source.texture_paths),
                ),
            ),
        )
        with self.assertRaises(PmxServiceError) as raised:
            services.preview_structural_edit(source, invalid)
        self.assertNotIn("Bad ref", repr(raised.exception.to_dict()))

    def test_text_encoding_and_reader_byte_limits_fail_closed_without_payload_leak(
        self,
    ) -> None:
        source = _clean_document()

        request = services.PmxStructuralPreviewRequest(
            material_insertions=(
                PmxStructuralMaterialInsertion(local_name="\ud800private"),
            ),
        )
        with self.assertRaises(PmxServiceError) as raised:
            services.preview_structural_edit(source, request)
        self.assertNotIn("\\ud800", repr(raised.exception.to_dict()))

        payload = _material_payload("Long name")
        with patch(
            "mmd_registry.pmx.structural_material_insertion.MAX_PMX_NAME_BYTES",
            2,
        ):
            with self.assertRaisesRegex(
                PmxStructuralMaterialInsertionError,
                "parser safety limit",
            ):
                preview_pmx_material_insertions(source, (payload,))

        memo_payload = replace(payload, local_name="A", memo="memo too long")
        with patch(
            "mmd_registry.pmx.structural_material_insertion."
            "MAX_PMX_MATERIAL_MEMO_BYTES",
            2,
        ):
            with self.assertRaisesRegex(
                PmxStructuralMaterialInsertionError,
                "parser safety limit",
            ):
                preview_pmx_material_insertions(source, (memo_payload,))

    def test_parser_material_count_limit_fails_before_reference_shift_allocation(
        self,
    ) -> None:
        source = _clean_document()
        payload = _material_payload("Count limit")

        with (
            patch(
                "mmd_registry.pmx.structural_material_insertion.MAX_PMX_MATERIAL_COUNT",
                len(source.materials),
            ),
            patch(
                "mmd_registry.pmx.structural_material_insertion."
                "plan_collection_reference_shift",
                side_effect=AssertionError("planner must not run"),
            ) as planner,
        ):
            with self.assertRaisesRegex(
                PmxStructuralMaterialInsertionError,
                "material parser safety limit",
            ):
                preview_pmx_material_insertions(source, (payload,))
        planner.assert_not_called()

    def test_declared_material_index_width_capacity_is_enforced(self) -> None:
        source = _clean_document()
        template = source.materials[0]
        constrained = replace(
            source,
            header=replace(
                source.header,
                index_sizes=replace(source.header.index_sizes, material=1),
            ),
            materials=tuple(
                replace(
                    template,
                    local_name=f"M{index}",
                    surface_index_count=0,
                )
                for index in range(128)
            ),
        )

        with self.assertRaises(PmxServiceError):
            services.preview_structural_edit(
                constrained,
                services.PmxStructuralPreviewRequest(
                    material_insertions=(
                        PmxStructuralMaterialInsertion(local_name="Overflow"),
                    ),
                ),
            )

    def test_empty_material_source_supports_append_but_not_insert_before(self) -> None:
        source = _clear_incoming_material_references(_clean_document())
        empty = replace(
            source,
            geometry=replace(source.geometry, surface_indices=()),
            materials=(),
        )

        appended = services.preview_structural_edit(
            empty,
            services.PmxStructuralPreviewRequest(
                material_insertions=(
                    PmxStructuralMaterialInsertion(local_name="First"),
                ),
            ),
        )
        self.assertEqual(len(appended.document.materials), 1)
        self.assertEqual(appended.document.materials[0].surface_index_count, 0)
        self.assertEqual(appended.document.surface_indices, ())

        invalid = services.PmxStructuralPreviewRequest(
            material_insertions=(
                PmxStructuralMaterialInsertion(
                    local_name="First",
                    position="insert_before",
                    source_index=0,
                ),
            ),
        )
        with self.assertRaises(PmxServiceError):
            services.preview_structural_edit(empty, invalid)

    def test_apply_refuses_material_insertion_before_structural_writer_io(self) -> None:
        request = services.PmxStructuralPreviewRequest(
            material_insertions=(
                PmxStructuralMaterialInsertion(local_name="Preview only"),
            ),
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing_source = root / "missing-source.pmx"
            output = root / "must-not-exist.pmx"

            with (
                patch(
                    "mmd_registry.pmx.structural_output."
                    "_write_pmx_structural_transaction",
                    side_effect=AssertionError("legacy writer must not run"),
                ) as legacy_writer,
                patch(
                    "mmd_registry.pmx.structural_output."
                    "_write_pmx_texture_insertion_transaction",
                    side_effect=AssertionError("texture writer must not run"),
                ) as texture_writer,
            ):
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
            legacy_writer.assert_not_called()
            texture_writer.assert_not_called()
            self.assertFalse(output.exists())
            self.assertFalse(missing_source.exists())

    def test_material_insertion_preview_has_no_filesystem_side_effects(self) -> None:
        source = _clean_document()
        request = services.PmxStructuralPreviewRequest(
            material_insertions=(
                PmxStructuralMaterialInsertion(local_name="No IO"),
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

    def test_direct_internal_preview_is_immutable_and_does_not_mutate_source(self) -> None:
        source = _clean_document()
        before_materials = source.materials
        before_morphs = source.morphs
        before_soft_bodies = source.soft_bodies
        payload = _material_payload(
            "Internal",
            position=PmxStructuralInsertPosition.insert_before(0),
        )

        preview = preview_pmx_material_insertions(source, (payload,))

        self.assertIs(preview.source_document, source)
        self.assertEqual(source.materials, before_materials)
        self.assertEqual(source.morphs, before_morphs)
        self.assertEqual(source.soft_bodies, before_soft_bodies)
        self.assertEqual(preview.certificate.document.materials[0].local_name, "Internal")


if __name__ == "__main__":
    unittest.main()
