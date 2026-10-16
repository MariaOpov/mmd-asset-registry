"""v0.9.5.10 CP11: source drift and output race hardening (synthetic PMX only).

Contract: SHA-bound draft -> preview -> explicit confirmation -> Smart apply.
Only existing editing/output authority may publish. No user/private PMX read.
"""
from __future__ import annotations

import ast
from dataclasses import replace
import hashlib
import inspect
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import mmd_registry.services as services
import mmd_registry.pmx.editing.output as edit_output
from mmd_registry.diagnostics import PmxServiceError
from mmd_registry.pmx import load_pmx
from mmd_registry.pmx.editing import (
    PMX_EDIT_PREVIEW_SCHEMA_VERSION,
    calculate_pmx_edit_plan_sha256,
)
import mmd_registry.services._smart_material_apply as smart_apply
import mmd_registry.services._smart_material_draft as smart_draft
from mmd_registry.services._smart_material_preview import (
    preview_smart_material_color_draft,
)
from mmd_registry.smart_parts import SmartPartKind
from tests.test_v0956_smart_material_draft import build_source_bytes


def _approved(source_bytes: bytes):
    draft = smart_draft.build_smart_material_color_draft(
        source_bytes, SmartPartKind.EYES, "red"
    )
    preview = preview_smart_material_color_draft(source_bytes, draft)
    confirmation = smart_apply.SmartMaterialApplyConfirmation(
        preview_schema_version=PMX_EDIT_PREVIEW_SCHEMA_VERSION,
        source_sha256=preview.source_sha256,
        plan_sha256=calculate_pmx_edit_plan_sha256(draft),
    )
    assert draft.expected_source_sha256 == hashlib.sha256(source_bytes).hexdigest()
    return draft, preview, confirmation


class V09510SourceDriftRaceHardeningTests(unittest.TestCase):
    """One adversarial test per CP11 frozen 12-row scenario matrix."""

    def test_cp11_01_content_change_after_draft_invalidates_preview(self):
        source_a = build_source_bytes()
        source_b = build_source_bytes(eye_rgb=(0.21, 0.31, 0.41))
        self.assertNotEqual(hashlib.sha256(source_a).digest(), hashlib.sha256(source_b).digest())
        draft = smart_draft.build_smart_material_color_draft(
            source_a, SmartPartKind.EYES, "red"
        )
        with self.assertRaises(PmxServiceError):
            preview_smart_material_color_draft(source_b, draft)
        self.assertEqual(draft.expected_source_sha256, hashlib.sha256(source_a).hexdigest())

    def test_cp11_02_source_changed_after_preview_blocks_before_apply(self):
        source_a = build_source_bytes()
        source_b = build_source_bytes(eye_rgb=(0.22, 0.32, 0.42))
        draft, preview, confirmation = _approved(source_a)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            destination = root / "destination.pmx"
            source.write_bytes(source_a)
            source.write_bytes(source_b)
            with (
                patch.object(services, "preview_edit", side_effect=AssertionError("stale replay")) as replay,
                patch.object(services, "apply_edit", side_effect=AssertionError("unsafe apply")) as apply,
            ):
                with self.assertRaises(smart_apply.SmartMaterialApplyError) as caught:
                    smart_apply.apply_smart_material_color_draft(
                        source, destination, draft, preview, confirmation=confirmation
                    )
            self.assertEqual(caught.exception.reason, "source_evidence_mismatch")
            replay.assert_not_called()
            apply.assert_not_called()
            self.assertFalse(destination.exists())
            self.assertEqual(source.read_bytes(), source_b)

    def test_cp11_03_same_path_replaced_with_different_bytes_is_not_authority(self):
        source_a = build_source_bytes()
        source_b = build_source_bytes(eye_rgb=(0.23, 0.33, 0.43))
        draft, preview, confirmation = _approved(source_a)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            replacement = root / "replacement.pmx"
            destination = root / "destination.pmx"
            source.write_bytes(source_a)
            replacement.write_bytes(source_b)
            os.replace(replacement, source)
            with self.assertRaises(smart_apply.SmartMaterialApplyError) as caught:
                smart_apply.apply_smart_material_color_draft(
                    source, destination, draft, preview, confirmation=confirmation
                )
            self.assertEqual(caught.exception.reason, "source_evidence_mismatch")
            self.assertEqual(source.read_bytes(), source_b)
            self.assertFalse(destination.exists())

    def test_cp11_04_same_bytes_at_different_source_path_remain_valid(self):
        source_bytes = build_source_bytes()
        draft, preview, confirmation = _approved(source_bytes)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "original.pmx"
            copied = root / "copy.pmx"
            destination = root / "output.pmx"
            original.write_bytes(source_bytes)
            copied.write_bytes(source_bytes)
            self.assertNotEqual(original.resolve(), copied.resolve())
            result = smart_apply.apply_smart_material_color_draft(
                copied, destination, draft, preview, confirmation=confirmation
            )
            self.assertEqual(result.preview, preview)
            self.assertTrue(destination.is_file())
            self.assertEqual(original.read_bytes(), source_bytes)
            self.assertEqual(copied.read_bytes(), source_bytes)

    def test_cp11_05_foreign_confirmation_cannot_authorize_other_source(self):
        source_a = build_source_bytes()
        source_b = build_source_bytes(eye_rgb=(0.24, 0.34, 0.44))
        _, _, confirmation_a = _approved(source_a)
        draft_b, preview_b, _ = _approved(source_b)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            destination = root / "destination.pmx"
            source.write_bytes(source_b)
            with self.assertRaises(smart_apply.SmartMaterialApplyError) as caught:
                smart_apply.apply_smart_material_color_draft(
                    source, destination, draft_b, preview_b, confirmation=confirmation_a
                )
            self.assertEqual(caught.exception.reason, "confirmation_mismatch")
            self.assertFalse(destination.exists())
            self.assertEqual(source.read_bytes(), source_b)

    def test_cp11_06_missing_wrong_type_or_stale_confirmation_fails_closed(self):
        source_bytes = build_source_bytes()
        draft, preview, confirmation = _approved(source_bytes)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            destination = root / "destination.pmx"
            source.write_bytes(source_bytes)
            with self.assertRaises(smart_apply.SmartMaterialApplyError) as missing:
                smart_apply.apply_smart_material_color_draft(
                    source, destination, draft, preview, confirmation=None
                )
            self.assertEqual(missing.exception.reason, "confirmation_required")
            with self.assertRaises(TypeError):
                smart_apply.apply_smart_material_color_draft(
                    source, destination, draft, preview, confirmation=object()
                )
            stale = replace(confirmation, plan_sha256="0" * 64)
            self.assertNotEqual(stale.plan_sha256, confirmation.plan_sha256)
            with self.assertRaises(smart_apply.SmartMaterialApplyError) as mismatch:
                smart_apply.apply_smart_material_color_draft(
                    source, destination, draft, preview, confirmation=stale
                )
            self.assertEqual(mismatch.exception.reason, "confirmation_mismatch")
            self.assertFalse(destination.exists())
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_cp11_07_mtime_only_change_does_not_supersede_source_sha(self):
        source_bytes = build_source_bytes()
        draft, preview, confirmation = _approved(source_bytes)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            destination = root / "destination.pmx"
            source.write_bytes(source_bytes)
            old = source.stat()
            os.utime(source, (old.st_atime, old.st_mtime + 60))
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), preview.source_sha256)
            result = smart_apply.apply_smart_material_color_draft(
                source, destination, draft, preview, confirmation=confirmation
            )
            self.assertEqual(result.preview.source_sha256, preview.source_sha256)
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertTrue(destination.is_file())

    def test_cp11_08_existing_destination_is_never_clobbered(self):
        source_bytes = build_source_bytes()
        draft, preview, confirmation = _approved(source_bytes)
        sentinel = b"already-existing-output-do-not-clobber"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            destination = root / "destination.pmx"
            source.write_bytes(source_bytes)
            destination.write_bytes(sentinel)
            with self.assertRaises(PmxServiceError):
                smart_apply.apply_smart_material_color_draft(
                    source, destination, draft, preview, confirmation=confirmation
                )
            self.assertEqual(destination.read_bytes(), sentinel)
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_cp11_09_destination_publication_race_preserves_racer_and_cleans_temp(self):
        source_bytes = build_source_bytes()
        draft, preview, confirmation = _approved(source_bytes)
        racer_bytes = b"racer-created-during-publication"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            destination = root / "destination.pmx"
            source.write_bytes(source_bytes)
            calls = []
            def _racer(temp_path, target_path):
                calls.append(1)
                self.assertTrue(Path(temp_path).is_file())
                self.assertFalse(Path(target_path).exists())
                Path(target_path).write_bytes(racer_bytes)
                raise FileExistsError("synthetic no-clobber racer")
            with patch.object(edit_output, "_publish_no_clobber", side_effect=_racer):
                with self.assertRaises(PmxServiceError):
                    smart_apply.apply_smart_material_color_draft(
                        source, destination, draft, preview, confirmation=confirmation
                    )
            self.assertEqual(len(calls), 1)
            self.assertEqual(destination.read_bytes(), racer_bytes)
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(list(root.glob(".destination.pmx.*.tmp")), [])

    def test_cp11_10_identical_source_and_output_path_is_rejected(self):
        source_bytes = build_source_bytes()
        draft, preview, confirmation = _approved(source_bytes)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.pmx"
            source.write_bytes(source_bytes)
            with self.assertRaises(PmxServiceError):
                smart_apply.apply_smart_material_color_draft(
                    source, source, draft, preview, confirmation=confirmation
                )
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_cp11_11_success_preserves_source_and_certifies_distinct_output(self):
        source_bytes = build_source_bytes()
        before_sha = hashlib.sha256(source_bytes).hexdigest()
        draft, preview, confirmation = _approved(source_bytes)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            destination = root / "destination.pmx"
            source.write_bytes(source_bytes)
            result = smart_apply.apply_smart_material_color_draft(
                source, destination, draft, preview, confirmation=confirmation
            )
            output_bytes = destination.read_bytes()
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before_sha)
            self.assertEqual(result.preview, preview)
            self.assertEqual(hashlib.sha256(output_bytes).hexdigest(), result.output_sha256)
            self.assertEqual(load_pmx(io.BytesIO(output_bytes)), preview.document)

    def test_cp11_12_smart_apply_has_only_existing_publication_authority(self):
        module_tree = ast.parse(inspect.getsource(smart_apply))
        calls = [n for n in ast.walk(module_tree) if isinstance(n, ast.Call)]
        delegates = [n for n in calls if isinstance(n.func, ast.Attribute)
                     and isinstance(n.func.value, ast.Name)
                     and n.func.value.id == "services" and n.func.attr == "apply_edit"]
        self.assertEqual(len(delegates), 1)
        self.assertEqual(
            [(kw.arg, isinstance(kw.value, ast.Constant) and kw.value.value)
             for kw in delegates[0].keywords],
            [("overwrite", False)],
        )
        forbidden = {"write_pmx_edit", "serialize_pmx", "_publish_no_clobber", "os.replace"}
        symbols = {n.id for n in ast.walk(module_tree) if isinstance(n, ast.Name)}
        self.assertFalse(symbols & forbidden)
        self.assertFalse(hasattr(smart_apply, "write_pmx_edit"))


if __name__ == "__main__":
    unittest.main()
