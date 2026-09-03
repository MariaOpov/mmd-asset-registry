"""v0.9.5 contracts for the read-only structural authoring catalog."""

from __future__ import annotations

import inspect
import io
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import patch

import mmd_registry.services as services
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.services import structural_authoring_catalog as catalog
from tests.mmd_fixtures import (
    build_pmx_bone,
    build_pmx_material,
    build_pmx_morph,
    build_pmx_rigid_body,
    build_pmx_structure,
)


def _document():
    source = build_pmx_structure(
        deform_types=(0, 1),
        surface_indices=(),
        texture_paths=(r"textures\Face.png", "テクスチャ/目.png"),
        materials=(
            build_pmx_material(
                local_name="顔",
                universal_name="Face",
                texture_index=0,
                surface_index_count=0,
            ),
        ),
        bones=(
            build_pmx_bone(
                local_name="右腕",
                universal_name="Right Arm",
                parent_bone_index=-1,
            ),
        ),
        morphs=(
            build_pmx_morph(
                local_name="まばたき",
                universal_name="Blink",
                panel=1,
                morph_type=1,
                offsets=(),
            ),
        ),
        rigid_bodies=(
            build_pmx_rigid_body(
                local_name="右腕剛体",
                universal_name="Right Arm Body",
                bone_index=0,
                shape=1,
                physics_mode=0,
            ),
        ),
    )
    return services.load_document(io.BytesIO(source))


class StructuralAuthoringCatalogTests(unittest.TestCase):
    def test_summary_is_exact_and_canonically_ordered(self) -> None:
        summary = catalog.summarize_structural_authoring_catalog(_document())
        self.assertEqual(
            summary.to_dict(),
            {
                "counts": {
                    "vertex": 2,
                    "texture": 2,
                    "material": 1,
                    "bone": 1,
                    "morph": 1,
                    "rigid_body": 1,
                }
            },
        )
        self.assertEqual(
            tuple(kind for kind, _count in summary.counts),
            tuple(PmxReferenceTargetKind),
        )

    def test_texture_paths_and_names_are_preserved_exactly(self) -> None:
        document = _document()
        textures = catalog.inspect_structural_authoring_catalog(
            document,
            PmxReferenceTargetKind.TEXTURE,
        )
        self.assertEqual(
            [entry.to_dict() for entry in textures.entries],
            [
                {"source_index": 0, "path": r"textures\Face.png"},
                {"source_index": 1, "path": "テクスチャ/目.png"},
            ],
        )

        expected = {
            PmxReferenceTargetKind.MATERIAL: ("顔", "Face"),
            PmxReferenceTargetKind.BONE: ("右腕", "Right Arm"),
            PmxReferenceTargetKind.MORPH: ("まばたき", "Blink"),
            PmxReferenceTargetKind.RIGID_BODY: ("右腕剛体", "Right Arm Body"),
        }
        for target_kind, names in expected.items():
            page = catalog.inspect_structural_authoring_catalog(
                document,
                target_kind,
            )
            self.assertEqual(
                (page.entries[0].local_name, page.entries[0].universal_name),
                names,
            )

    def test_vertex_projection_is_source_index_based_and_bounded(self) -> None:
        page = catalog.inspect_structural_authoring_catalog(
            _document(),
            PmxReferenceTargetKind.VERTEX,
            offset=1,
            limit=1,
        )
        self.assertEqual(page.total_count, 2)
        self.assertEqual(page.returned_count, 1)
        self.assertEqual(page.entries[0].source_index, 1)
        self.assertEqual(page.entries[0].deform_type, 1)

    def test_offset_past_end_returns_empty_page(self) -> None:
        page = catalog.inspect_structural_authoring_catalog(
            _document(),
            PmxReferenceTargetKind.BONE,
            offset=50,
            limit=10,
        )
        self.assertEqual(page.total_count, 1)
        self.assertEqual(page.entries, ())

    def test_limits_are_strict_and_bool_is_not_integer(self) -> None:
        invalid = (
            {"offset": True},
            {"offset": -1},
            {"limit": False},
            {"limit": 0},
            {"limit": catalog.PMX_STRUCTURAL_AUTHORING_CATALOG_MAX_LIMIT + 1},
        )
        for kwargs in invalid:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(
                    catalog.PmxStructuralAuthoringCatalogServiceError
                ) as raised:
                    catalog.inspect_structural_authoring_catalog(
                        _document(),
                        PmxReferenceTargetKind.BONE,
                        **kwargs,
                    )
                self.assertEqual(
                    raised.exception.to_dict()["code"],
                    "invalid_argument",
                )

    def test_invalid_inputs_are_redacted(self) -> None:
        with self.assertRaises(
            catalog.PmxStructuralAuthoringCatalogServiceError
        ) as raised:
            catalog.summarize_structural_authoring_catalog(object())
        self.assertEqual(
            raised.exception.to_dict(),
            {
                "code": "invalid_argument",
                "operation": "summarize_structural_authoring_catalog",
                "message": "Invalid structural authoring catalog input.",
            },
        )

        with self.assertRaises(
            catalog.PmxStructuralAuthoringCatalogServiceError
        ) as raised:
            catalog.inspect_structural_authoring_catalog(
                _document(),
                "bone",  # type: ignore[arg-type]
            )
        self.assertEqual(
            raised.exception.to_dict()["operation"],
            "inspect_structural_authoring_catalog",
        )

    def test_results_are_frozen_and_repeatable(self) -> None:
        document = _document()
        first = catalog.inspect_structural_authoring_catalog(
            document,
            PmxReferenceTargetKind.BONE,
        )
        second = catalog.inspect_structural_authoring_catalog(
            document,
            PmxReferenceTargetKind.BONE,
        )
        self.assertEqual(first, second)
        with self.assertRaises(FrozenInstanceError):
            first.offset = 9  # type: ignore[misc]

    def test_service_is_cli_independent_and_does_not_import_execution(self) -> None:
        source = inspect.getsource(catalog)
        for forbidden in (
            "transaction_plan_cli",
            "structural_output",
            "index_remap",
            "apply_structural_transaction",
            "apply_structural_edit",
        ):
            self.assertNotIn(forbidden, source)

        self.assertNotIn(
            "summarize_structural_authoring_catalog",
            services.__all__,
        )
        self.assertNotIn(
            "inspect_structural_authoring_catalog",
            services.__all__,
        )

    def test_process_control_exceptions_escape(self) -> None:
        with patch.object(catalog, "_summary", side_effect=KeyboardInterrupt()):
            with self.assertRaises(KeyboardInterrupt):
                catalog.summarize_structural_authoring_catalog(_document())


if __name__ == "__main__":
    unittest.main()
