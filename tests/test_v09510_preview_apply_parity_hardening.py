"""v0.9.5.10 CP12: Smart Material preview-to-confirmed-apply semantic parity.

Only synthetic PMX fixtures in OS temporary directories. No private PMX, no
second writer/preview/remapper, no new mutation authority or reason tokens.
"""
from __future__ import annotations

import ast
from dataclasses import replace
import hashlib
import inspect
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import mmd_registry.services as services
from mmd_registry.diagnostics import PmxServiceError
from mmd_registry.pmx import load_pmx, validate_pmx_document
from mmd_registry.pmx.editing import (
    PMX_EDIT_PREVIEW_SCHEMA_VERSION,
    calculate_pmx_edit_plan_sha256,
)
from mmd_registry.services import _smart_material_apply as smart_apply
from mmd_registry.services import _smart_material_draft as smart_draft
from mmd_registry.services import _smart_material_appearance as appearance
from mmd_registry.services._smart_material_preview import preview_smart_material_color_draft
from mmd_registry.smart_parts import SmartPartKind
from tests.mmd_fixtures import build_pmx_bone, build_pmx_material, build_pmx_structure
from tests.test_v0959_smart_material_appearance import build_appearance_source_bytes


INTENTS = {
    "material_color": "red",
    "transparency": appearance.SmartMaterialTransparencyIntent(alpha=0.25),
    "material_specular": appearance.SmartMaterialSpecularIntent(
        specular=(0.25, 0.5, 0.75), strength=1.25,
    ),
    "material_edge": appearance.SmartMaterialEdgeIntent(
        color=(0.5, 0.4, 0.3, 0.2), scale=1.25,
    ),
}
EXPECTED_FIELDS = {
    "material_color": {"diffuse"},
    "transparency": {"diffuse"},
    "material_specular": {"specular", "specular_strength"},
    "material_edge": {"edge_color", "edge_scale"},
}


def _single_source():
    return build_pmx_structure(
        surface_indices=(0, 0, 0),
        texture_paths=(),
        materials=(
            build_pmx_material(
                local_name="Eyes", universal_name="",
                diffuse=(0.2, 0.3, 0.4, 0.35),
                specular=(0.11, 0.12, 0.13), specular_strength=0.45,
                edge_color=(0.21, 0.22, 0.23, 0.24), edge_scale=1.2,
                texture_index=-1, sphere_texture_index=-1, sphere_mode=0,
                toon_reference_mode=1, toon_reference_index=0,
                memo="eyes", surface_index_count=3,
            ),
        ),
        bones=(build_pmx_bone(),),
    )


def _source(mode):
    return _single_source() if mode == "single" else build_appearance_source_bytes()


def _build(source_bytes, capability, *, intent=None):
    if intent is None:
        intent = INTENTS[capability]
    if capability == "material_color":
        draft = smart_draft.build_smart_material_color_draft(
            source_bytes, SmartPartKind.EYES, intent,
        )
        preview = preview_smart_material_color_draft(source_bytes, draft)
    else:
        draft = appearance.build_smart_material_appearance_draft(
            source_bytes, SmartPartKind.EYES, intent,
        )
        preview = appearance.preview_smart_material_appearance_draft(
            source_bytes, draft,
        )
    confirmation = smart_apply.SmartMaterialApplyConfirmation(
        preview_schema_version=PMX_EDIT_PREVIEW_SCHEMA_VERSION,
        source_sha256=preview.source_sha256,
        plan_sha256=calculate_pmx_edit_plan_sha256(draft),
    )
    return draft, preview, confirmation


class V09510PreviewApplyParityHardeningTests(unittest.TestCase):
    """Exactly one test for each case in CP12's frozen 14-case matrix."""

    def _run(self, capability, mode, *, intent=None):
        source_bytes = _source(mode)
        source_before = load_pmx(io.BytesIO(source_bytes))
        source_sha = hashlib.sha256(source_bytes).hexdigest()
        expected_indices = (0,) if mode == "single" else (1, 2)
        draft, preview, confirmation = _build(source_bytes, capability, intent=intent)
        self.assertEqual(tuple(op.material_index for op in draft.operations), expected_indices)
        self.assertEqual(draft.expected_source_sha256, source_sha)
        self.assertEqual(preview.source_sha256, source_sha)
        self.assertEqual(preview.plan_sha256, confirmation.plan_sha256)
        self.assertEqual(preview, services.preview_edit(source_bytes, draft))
        self.assertTrue(preview.to_dict()["dry_run"])
        self.assertFalse(preview.to_dict()["output"]["written"])
        self.assertEqual(hashlib.sha256(source_bytes).hexdigest(), source_sha)
        with tempfile.TemporaryDirectory(prefix="mmd_cp12_parity_") as directory:
            root = Path(directory)
            source_path = root / "source.pmx"
            output_path = root / "output.pmx"
            source_path.write_bytes(source_bytes)
            self.assertFalse(output_path.exists())
            result = smart_apply.apply_smart_material_color_draft(
                source_path, output_path, draft, preview, confirmation=confirmation,
            )
            self.assertTrue(output_path.is_file())
            output_bytes = output_path.read_bytes()
            output_document = load_pmx(io.BytesIO(output_bytes))
            validate_pmx_document(output_document)
            self.assertEqual(output_document, preview.document)
            self.assertEqual(result.preview, preview)
            self.assertEqual(result.preview.audit, preview.audit)
            self.assertEqual(result.output_sha256, hashlib.sha256(output_bytes).hexdigest())
            self.assertEqual(result.output_size_bytes, len(output_bytes))
            self.assertEqual(source_path.read_bytes(), source_bytes)
        self.assertEqual(hashlib.sha256(source_bytes).hexdigest(), source_sha)
        self.assertEqual(replace(output_document, materials=source_before.materials), source_before)
        for i, (old, new) in enumerate(zip(source_before.materials, output_document.materials)):
            if i not in expected_indices:
                self.assertEqual(new, old)
                continue
            fields_changed = set(EXPECTED_FIELDS[capability])
            self.assertEqual(
                replace(new, **{field: getattr(old, field) for field in fields_changed}), old,
            )
            if capability == "material_color":
                self.assertEqual(new.diffuse[3], old.diffuse[3])
                self.assertEqual(new.diffuse, draft.operations[expected_indices.index(i)].diffuse)
            elif capability == "transparency":
                self.assertEqual(new.diffuse[:3], old.diffuse[:3])
                self.assertEqual(new.diffuse, draft.operations[expected_indices.index(i)].diffuse)
            elif capability == "material_specular":
                op = draft.operations[expected_indices.index(i)]
                self.assertEqual(new.specular, op.specular)
                self.assertEqual(new.specular_strength, op.specular_strength)
            elif capability == "material_edge":
                op = draft.operations[expected_indices.index(i)]
                self.assertEqual(new.edge_color, op.edge_color)
                self.assertEqual(new.edge_scale, op.edge_scale)
                self.assertEqual(new.drawing_flags, old.drawing_flags)
        changed = tuple(c for c in preview.audit.changes if c.category == "material")
        for change in changed:
            self.assertIn(change.target_index, expected_indices)
            self.assertIn(change.field_path.rsplit(".", 1)[-1], EXPECTED_FIELDS[capability])
        return source_before, output_document, draft, preview, result, changed

    def test_cp12_01_color_single_target_preview_apply_equal(self):
        _, _, _, _, _, changes = self._run("material_color", "single")
        self.assertEqual({c.target_index for c in changes}, {0})
        self.assertEqual({c.field_path.rsplit(".", 1)[-1] for c in changes}, {"diffuse"})

    def test_cp12_02_color_multi_target_alpha_and_order_preserved(self):
        src, out, plan, _, _, changes = self._run("material_color", "multi")
        self.assertEqual(tuple(op.material_index for op in plan.operations), (1, 2))
        self.assertEqual({c.target_index for c in changes}, {1, 2})
        self.assertEqual(src.materials[0], out.materials[0])
        for i in (1, 2):
            self.assertEqual(out.materials[i].diffuse[3], src.materials[i].diffuse[3])

    def test_cp12_03_transparency_single_target_alpha_only(self):
        src, out, _, _, _, changes = self._run("transparency", "single")
        self.assertEqual(src.materials[0].diffuse[:3], out.materials[0].diffuse[:3])
        self.assertNotEqual(src.materials[0].diffuse[3], out.materials[0].diffuse[3])
        self.assertEqual({c.field_path.rsplit(".", 1)[-1] for c in changes}, {"diffuse"})

    def test_cp12_04_transparency_multi_target_preserves_each_rgb(self):
        src, out, _, _, _, changes = self._run("transparency", "multi")
        for i in (1, 2):
            self.assertEqual(src.materials[i].diffuse[:3], out.materials[i].diffuse[:3])
            self.assertNotEqual(src.materials[i].diffuse[3], out.materials[i].diffuse[3])
        self.assertEqual({c.target_index for c in changes}, {1, 2})

    def test_cp12_05_specular_single_target_only_requested_fields(self):
        src, out, _, _, _, changes = self._run("material_specular", "single")
        self.assertEqual(src.materials[0].diffuse, out.materials[0].diffuse)
        self.assertEqual(src.materials[0].edge_color, out.materials[0].edge_color)
        self.assertEqual({c.field_path.rsplit(".", 1)[-1] for c in changes}, EXPECTED_FIELDS["material_specular"])

    def test_cp12_06_specular_multi_target_field_and_target_parity(self):
        src, out, _, _, _, changes = self._run("material_specular", "multi")
        self.assertEqual(src.materials[0], out.materials[0])
        self.assertEqual({c.target_index for c in changes}, {1, 2})
        self.assertEqual({c.field_path.rsplit(".", 1)[-1] for c in changes}, EXPECTED_FIELDS["material_specular"])

    def test_cp12_07_edge_single_target_never_touches_drawing_flags(self):
        src, out, _, _, _, changes = self._run("material_edge", "single")
        self.assertEqual(src.materials[0].drawing_flags, out.materials[0].drawing_flags)
        self.assertEqual({c.field_path.rsplit(".", 1)[-1] for c in changes}, EXPECTED_FIELDS["material_edge"])

    def test_cp12_08_edge_multi_target_never_touches_drawing_flags(self):
        src, out, _, _, _, changes = self._run("material_edge", "multi")
        self.assertEqual(src.materials[0], out.materials[0])
        for i in (1, 2):
            self.assertEqual(src.materials[i].drawing_flags, out.materials[i].drawing_flags)
        self.assertEqual({c.target_index for c in changes}, {1, 2})
        self.assertEqual({c.field_path.rsplit(".", 1)[-1] for c in changes}, EXPECTED_FIELDS["material_edge"])

    def test_cp12_09_noop_equal_value_has_consistent_audit(self):
        source_bytes = _single_source()
        parsed = load_pmx(io.BytesIO(source_bytes))
        equal_rgb = parsed.materials[0].diffuse[:3]
        before, after, _, preview, result, changes = self._run(
            "material_color", "single", intent=equal_rgb,
        )
        self.assertEqual(before, after)
        self.assertEqual(changes, ())
        self.assertEqual(preview.audit.changed_fields, 0)
        self.assertEqual(preview.status, "no_changes")
        self.assertEqual(result.status, "no_changes")

    def test_cp12_10_untouched_materials_and_non_target_fields(self):
        for capability in INTENTS:
            with self.subTest(capability=capability):
                before, after, _, _, _, _ = self._run(capability, "multi")
                self.assertEqual(before.materials[0], after.materials[0])
                self.assertEqual(replace(after, materials=before.materials), before)

    def test_cp12_11_preview_dry_run_never_writes_and_preserves_source(self):
        source_bytes = _single_source()
        before_hash = hashlib.sha256(source_bytes).hexdigest()
        with tempfile.TemporaryDirectory(prefix="mmd_cp12_preview_") as directory:
            output = Path(directory) / "must-not-exist.pmx"
            with (
                patch.object(services, "apply_edit", side_effect=AssertionError("preview cannot apply")) as apply_mock,
                patch.object(services, "write_pmx_edit", side_effect=AssertionError("preview cannot write")) as write_mock,
            ):
                for capability in INTENTS:
                    draft, preview, _ = _build(source_bytes, capability)
                    self.assertEqual(preview.plan_sha256, calculate_pmx_edit_plan_sha256(draft))
                    self.assertTrue(preview.to_dict()["dry_run"])
                    self.assertFalse(preview.to_dict()["output"]["written"])
            self.assertFalse(output.exists())
            apply_mock.assert_not_called()
            write_mock.assert_not_called()
        self.assertEqual(hashlib.sha256(source_bytes).hexdigest(), before_hash)

    def test_cp12_12_post_write_semantic_and_hash_certification(self):
        for capability in INTENTS:
            with self.subTest(capability=capability):
                _, after, _, preview, result, _ = self._run(capability, "single")
                self.assertEqual(after, preview.document)
                self.assertEqual(result.preview, preview)
                self.assertEqual(result.preview.audit, preview.audit)
                self.assertEqual(result.output_size_bytes > 0, True)

    def test_cp12_13_stale_cross_source_confirmation_cannot_apply(self):
        source_a = _single_source()
        source_b = build_appearance_source_bytes()
        plan_a, preview_a, confirmation_a = _build(source_a, "material_color")
        plan_b, preview_b, _ = _build(source_b, "material_color")
        with tempfile.TemporaryDirectory(prefix="mmd_cp12_stale_") as directory:
            root = Path(directory)
            source_path = root / "source.pmx"
            output = root / "output.pmx"
            source_path.write_bytes(source_b)
            with self.assertRaises(smart_apply.SmartMaterialApplyError) as caught:
                smart_apply.apply_smart_material_color_draft(
                    source_path, output, plan_b, preview_b, confirmation=confirmation_a,
                )
            self.assertEqual(caught.exception.reason, "confirmation_mismatch")
            with self.assertRaises(smart_apply.SmartMaterialApplyError) as drift:
                smart_apply.apply_smart_material_color_draft(
                    source_path, output, plan_a, preview_a, confirmation=confirmation_a,
                )
            self.assertEqual(drift.exception.reason, "source_evidence_mismatch")
            self.assertFalse(output.exists())
            self.assertEqual(source_path.read_bytes(), source_b)

    def test_cp12_14_one_apply_writer_no_overwrite_authority(self):
        source_bytes = _single_source()
        plan, preview, confirmation = _build(source_bytes, "material_color")
        with tempfile.TemporaryDirectory(prefix="mmd_cp12_authority_") as directory:
            root = Path(directory)
            source_path = root / "source.pmx"
            output = root / "output.pmx"
            source_path.write_bytes(source_bytes)
            real_apply = services.apply_edit
            with patch.object(services, "apply_edit", wraps=real_apply) as apply_mock:
                result = smart_apply.apply_smart_material_color_draft(
                    source_path, output, plan, preview, confirmation=confirmation,
                )
            self.assertEqual(result.preview, preview)
            apply_mock.assert_called_once_with(source_path, output, plan, overwrite=False)
            sentinel = output.read_bytes()
            with self.assertRaises(PmxServiceError):
                smart_apply.apply_smart_material_color_draft(
                    source_path, output, plan, preview, confirmation=confirmation,
                )
            self.assertEqual(output.read_bytes(), sentinel)
        code = ast.parse(inspect.getsource(smart_apply))
        delegates = [node for node in ast.walk(code) if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Attribute)
                     and isinstance(node.func.value, ast.Name)
                     and node.func.value.id == "services" and node.func.attr == "apply_edit"]
        self.assertEqual(len(delegates), 1)
        self.assertEqual([(kw.arg, isinstance(kw.value, ast.Constant) and kw.value.value)
                          for kw in delegates[0].keywords], [("overwrite", False)])


if __name__ == "__main__":
    unittest.main()
