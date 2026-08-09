"""Generated compatibility matrix for complete declarative PMX editing."""

from __future__ import annotations

import hashlib
import io
import itertools
import json
import tempfile
import unittest
from pathlib import Path

from mmd_registry.pmx import PmxDocument, load_pmx, serialize_pmx
from mmd_registry.pmx.editing import (
    PmxEditPlan,
    dry_run_pmx_edit,
    parse_pmx_edit_plan_json,
    write_pmx_edit,
)
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


_CATEGORY_COMBINATIONS = (
    ("model",),
    ("texture",),
    ("material",),
    ("model", "texture"),
    ("model", "material"),
    ("texture", "material"),
    ("model", "texture", "material"),
)


def _build_matrix_plan(
    source_bytes: bytes,
    categories: tuple[str, ...],
) -> PmxEditPlan:
    """Build one strict plan for selected editable section categories."""

    operations: list[dict[str, object]] = []
    if "model" in categories:
        operations.append(
            {
                "op": "set_model_info",
                "local_name": "編集モデル 🌸",
                "universal_name": "Edited Matrix Model",
                "local_comments": "生成テストによる安全な編集",
                "universal_comments": "Generated safe edit matrix",
            }
        )
    if "texture" in categories:
        operations.append(
            {
                "op": "set_texture_path",
                "texture_index": 1,
                "path": "textures/edited_顔.spa",
            }
        )
    if "material" in categories:
        operations.append(
            {
                "op": "update_material",
                "material_index": 0,
                "local_name": "編集材質",
                "universal_name": "Edited Matrix Material",
                "memo": "Generated material edit",
                "texture_index": 2,
                "sphere_texture_index": 0,
                "sphere_mode": 1,
                "toon_reference_mode": "shared",
                "toon_reference_index": 5,
                "diffuse": [0.25, 0.5, 0.75, 0.875],
                "specular": [0.125, 0.25, 0.5],
                "specular_strength": 0.625,
                "ambient": [0.25, 0.375, 0.5],
                "drawing_flags": 17,
                "edge_color": [0.5, 0.25, 0.125, 0.75],
                "edge_scale": 1.5,
            }
        )
    return parse_pmx_edit_plan_json(
        json.dumps(
            {
                "schema_version": 1,
                "expected_source_sha256": hashlib.sha256(
                    source_bytes
                ).hexdigest(),
                "operations": operations,
            },
            ensure_ascii=False,
        )
    )


def _section_counts(document: PmxDocument) -> tuple[int, ...]:
    """Return fixed counts for every complete PMX section."""

    return (
        len(document.vertices),
        len(document.surface_indices),
        len(document.texture_paths),
        len(document.materials),
        len(document.bones),
        len(document.morphs),
        len(document.display_frames),
        len(document.rigid_bodies),
        len(document.joints),
        len(document.soft_bodies),
        len(document.trailing_data),
    )


class PmxEditGeneratedMatrixTests(unittest.TestCase):
    """Exercise safe edits across all supported PMX header dimensions."""

    def assert_uneditable_sections_unchanged(
        self,
        source: PmxDocument,
        edited: PmxDocument,
    ) -> None:
        """Require semantic identity outside v0.8 editable sections."""

        for field_name in (
            "header",
            "geometry",
            "bones",
            "morphs",
            "display_frames",
            "rigid_bodies",
            "joints",
            "soft_bodies",
            "trailing_data",
        ):
            self.assertEqual(
                getattr(edited, field_name),
                getattr(source, field_name),
                field_name,
            )
        self.assertEqual(_section_counts(edited), _section_counts(source))

    def assert_selected_categories(
        self,
        source: PmxDocument,
        edited: PmxDocument,
        categories: tuple[str, ...],
    ) -> None:
        """Require exact selected edits and identity for omitted categories."""

        if "model" in categories:
            self.assertEqual(edited.model_info.local_name, "編集モデル 🌸")
            self.assertEqual(
                edited.model_info.universal_name,
                "Edited Matrix Model",
            )
            self.assertEqual(
                edited.model_info.local_comments,
                "生成テストによる安全な編集",
            )
            self.assertEqual(
                edited.model_info.universal_comments,
                "Generated safe edit matrix",
            )
        else:
            self.assertEqual(edited.model_info, source.model_info)

        if "texture" in categories:
            self.assertEqual(edited.texture_paths[1], "textures/edited_顔.spa")
            self.assertEqual(edited.texture_paths[0], source.texture_paths[0])
            self.assertEqual(edited.texture_paths[2:], source.texture_paths[2:])
        else:
            self.assertEqual(edited.texture_paths, source.texture_paths)

        if "material" in categories:
            material = edited.materials[0]
            self.assertEqual(material.local_name, "編集材質")
            self.assertEqual(material.universal_name, "Edited Matrix Material")
            self.assertEqual(material.memo, "Generated material edit")
            self.assertEqual(material.texture_index, 2)
            self.assertEqual(material.sphere_texture_index, 0)
            self.assertEqual(material.sphere_mode, 1)
            self.assertEqual(material.toon_reference_mode, "shared")
            self.assertEqual(material.toon_reference_index, 5)
            self.assertEqual(material.diffuse, (0.25, 0.5, 0.75, 0.875))
            self.assertEqual(material.specular, (0.125, 0.25, 0.5))
            self.assertEqual(material.specular_strength, 0.625)
            self.assertEqual(material.ambient, (0.25, 0.375, 0.5))
            self.assertEqual(material.drawing_flags, 17)
            self.assertEqual(
                material.edge_color,
                (0.5, 0.25, 0.125, 0.75),
            )
            self.assertEqual(material.edge_scale, 1.5)
            self.assertEqual(
                material.surface_index_count,
                source.materials[0].surface_index_count,
            )
            self.assertEqual(edited.materials[1:], source.materials[1:])
        else:
            self.assertEqual(edited.materials, source.materials)

    def assert_matrix_case(
        self,
        source_bytes: bytes,
        categories: tuple[str, ...],
    ) -> None:
        """Require deterministic preview/write behavior for one matrix case."""

        source_document = load_pmx(io.BytesIO(source_bytes))
        plan = _build_matrix_plan(source_bytes, categories)
        first_preview = dry_run_pmx_edit(source_bytes, plan)
        second_preview = dry_run_pmx_edit(source_bytes, plan)

        self.assertEqual(second_preview.document, first_preview.document)
        self.assertEqual(second_preview.audit, first_preview.audit)
        self.assertEqual(
            serialize_pmx(second_preview.document),
            serialize_pmx(first_preview.document),
        )
        self.assert_selected_categories(
            source_document,
            first_preview.document,
            categories,
        )
        self.assert_uneditable_sections_unchanged(
            source_document,
            first_preview.document,
        )

        for category in ("model", "texture", "material"):
            expected_nonzero = category in categories
            self.assertEqual(
                first_preview.audit.category_count(category) > 0,
                expected_nonzero,
            )

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            input_path = root / "matrix-input.pmx"
            first_output = root / "matrix-first.pmx"
            second_output = root / "matrix-second.pmx"
            input_path.write_bytes(source_bytes)

            first_result = write_pmx_edit(input_path, first_output, plan)
            second_result = write_pmx_edit(input_path, second_output, plan)

            self.assertEqual(input_path.read_bytes(), source_bytes)
            self.assertEqual(first_output.read_bytes(), second_output.read_bytes())
            self.assertEqual(load_pmx(first_output), first_preview.document)
            self.assertEqual(first_result.output_sha256, second_result.output_sha256)

    def test_complete_plan_across_version_encoding_width_matrix(self) -> None:
        encodings = {0: "utf-16-le", 1: "utf-8"}
        categories = ("model", "texture", "material")

        for version, encoding_flag, index_size in itertools.product(
            (2.0, 2.1),
            (0, 1),
            (1, 2, 4),
        ):
            with self.subTest(
                version=version,
                encoding=encodings[encoding_flag],
                index_size=index_size,
            ):
                source_bytes = build_pmx_roundtrip_fixture(
                    version=version,
                    encoding_flag=encoding_flag,
                    index_size=index_size,
                )
                self.assert_matrix_case(source_bytes, categories)

    def test_complete_plan_across_mixed_index_widths(self) -> None:
        mixed_widths = (
            (1, 2, 4, 1, 2, 4),
            (2, 4, 1, 2, 4, 1),
            (4, 1, 2, 4, 1, 2),
        )
        categories = ("model", "texture", "material")

        for version, encoding_flag, index_sizes in itertools.product(
            (2.0, 2.1),
            (0, 1),
            mixed_widths,
        ):
            with self.subTest(
                version=version,
                encoding_flag=encoding_flag,
                index_sizes=index_sizes,
            ):
                source_bytes = build_pmx_roundtrip_fixture(
                    version=version,
                    encoding_flag=encoding_flag,
                    index_sizes=index_sizes,
                )
                self.assert_matrix_case(source_bytes, categories)

    def test_every_model_texture_material_category_combination(self) -> None:
        source_bytes = build_pmx_roundtrip_fixture(
            version=2.1,
            encoding_flag=0,
            index_sizes=(1, 2, 4, 1, 2, 4),
        )

        for categories in _CATEGORY_COMBINATIONS:
            with self.subTest(categories=categories):
                self.assert_matrix_case(source_bytes, categories)


if __name__ == "__main__":
    unittest.main()
