"""v0.9.5.10 CP10 malformed evidence hardening -- frozen, test-only coverage.

All PMX inputs are synthetic in-memory fixtures; no model file is written.
Do not broaden v0.9.5.9 Smart authoring authority.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import io
import unittest
import tempfile
from pathlib import Path

from mmd_registry.pmx import load_pmx
from mmd_registry.pmx.editing import (
    PMX_EDIT_PREVIEW_SCHEMA_VERSION,
    calculate_pmx_edit_plan_sha256,
)
from mmd_registry.services import preview_edit
from mmd_registry.services._smart_material_apply import (
    SmartMaterialApplyConfirmation,
    SmartMaterialApplyError,
    apply_smart_material_color_draft,
)
import mmd_registry.services._smart_inspection as smart_inspection
import mmd_registry.services._smart_material_draft as smart_draft
from mmd_registry.services._smart_material_appearance import (
    SmartMaterialAppearanceCapabilityKind,
    resolve_smart_material_appearance_capability,
)
from mmd_registry.services._smart_material_draft import (
    SmartMaterialCapabilityStatus,
    SmartMaterialDraftError,
    SmartMaterialGroup,
)
from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringMaterialCatalogEntry,
)
from mmd_registry.smart_parts import (
    SmartPart,
    SmartPartEvidence,
    SmartPartEvidenceKind,
    SmartPartKind,
)
from tests.test_v0956_smart_material_draft import (
    build_ambiguous_source,
    build_source_bytes,
)


def _material(
    index: int, name: str = "Eyes", universal_name: str = "",
) -> PmxStructuralAuthoringMaterialCatalogEntry:
    return PmxStructuralAuthoringMaterialCatalogEntry(
        source_index=index,
        local_name=name,
        universal_name=universal_name,
        texture_index=-1,
        sphere_texture_index=-1,
        surface_index_count=3,
    )


def _evidence(
    index: int = 0, kind: SmartPartEvidenceKind = SmartPartEvidenceKind.MATERIAL,
) -> SmartPartEvidence:
    return SmartPartEvidence(
        source_kind=kind,
        source_index=index,
        reason="material.local_name:exact_alias:eyes",
    )


class V09510MalformedEvidenceHardeningTests(unittest.TestCase):
    """One focused test per CP04/CP10 malformed-evidence matrix row."""

    def assert_fail_closed(self, callback) -> None:
        """A malformed Smart preview must never silently succeed or leak lookup errors."""
        with self.assertRaises(Exception) as raised:
            callback()
        self.assertNotIsInstance(
            raised.exception, (IndexError, KeyError, AttributeError),
            "Malformed evidence leaked an accidental lookup/attribute error.",
        )

    def test_cp10_01_wrong_evidence_entity_kind_cannot_grant_material_permission(self):
        with self.assertRaises(TypeError):
            SmartPartEvidence(source_kind="material", source_index=1, reason="exact")
        foreign = _evidence(1, SmartPartEvidenceKind.BONE)
        with self.assertRaises(ValueError):
            SmartMaterialGroup(
                part_kind=SmartPartKind.EYES,
                material_indices=(1,),
                evidence=(foreign,),
            )

    def test_cp10_02_missing_smart_source_identity_cannot_authorize_apply(self):
        source = build_source_bytes()
        source_sha = hashlib.sha256(source).hexdigest()
        draft = smart_draft.build_smart_material_color_draft(
            source, SmartPartKind.EYES, "blue"
        )
        self.assertEqual(draft.expected_source_sha256, source_sha)

        # The shared PmxEditPlan/preview contract permits an unbound plan.
        # This legacy preview is NOT authorization for a Smart confirmed apply.
        missing = replace(draft, expected_source_sha256=None)
        self.assertIsNone(missing.expected_source_sha256)
        preview = preview_edit(source, missing)
        self.assertEqual(preview.source_sha256, source_sha)
        confirmation = SmartMaterialApplyConfirmation(
            preview_schema_version=PMX_EDIT_PREVIEW_SCHEMA_VERSION,
            source_sha256=preview.source_sha256,
            plan_sha256=calculate_pmx_edit_plan_sha256(missing),
        )

        # Confirmed Smart apply must fail before any output is published.
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source_path = root / "synthetic_source.pmx"
            destination_path = root / "would_be_output.pmx"
            source_path.write_bytes(source)
            with self.assertRaises(SmartMaterialApplyError) as raised:
                apply_smart_material_color_draft(
                    source_path,
                    destination_path,
                    missing,
                    preview,
                    confirmation=confirmation,
                )
            self.assertEqual(raised.exception.reason, "source_evidence_mismatch")
            self.assertFalse(destination_path.exists())
            self.assertEqual(source_path.read_bytes(), source)

    def test_cp10_03_conflicting_smart_source_hash_rejected_before_preview(self):
        source = build_source_bytes()
        draft = smart_draft.build_smart_material_color_draft(source, SmartPartKind.EYES, "blue")
        wrong_sha = "0" * 64
        self.assertNotEqual(draft.expected_source_sha256, wrong_sha)
        try:
            mismatched = replace(draft, expected_source_sha256=wrong_sha)
        except (TypeError, ValueError):
            return  # Frozen DTO checks prevent mismatch from being constructed.
        self.assert_fail_closed(lambda: preview_edit(source, mismatched))

    def test_cp10_04_out_of_range_material_index_rejected_by_document_binding(self):
        source = build_source_bytes()
        document = load_pmx(io.BytesIO(source))
        result = smart_inspection._analyze_entries((_material(9999),))
        group = smart_draft.group_smart_materials(result, SmartPartKind.EYES)
        with self.assertRaises(SmartMaterialDraftError) as raised:
            smart_draft._validate_material_group_against_document(document, result, group)
        self.assertEqual(raised.exception.reason, "source_evidence_mismatch")

    def test_cp10_05_negative_or_boolean_source_indices_rejected(self):
        for bad, expected in ((-1, ValueError), (True, TypeError)):
            with self.subTest(bad=bad):
                with self.assertRaises(expected):
                    SmartPartEvidence(
                        source_kind=SmartPartEvidenceKind.MATERIAL,
                        source_index=bad,
                        reason="material.local_name:exact_alias:eyes",
                    )
                with self.assertRaises(expected):
                    _material(bad)

    def test_cp10_06_duplicate_equivalent_evidence_cannot_multiply_targets(self):
        entry = _material(7)
        result = smart_inspection._analyze_entries((entry, entry, entry))
        group = smart_draft.group_smart_materials(result, SmartPartKind.EYES)
        self.assertEqual(group.material_indices, (7,))
        self.assertEqual(len(group.evidence), 1)
        self.assertEqual(
            smart_draft.discover_smart_material_capability(result, SmartPartKind.EYES).material_indices,
            (7,),
        )

    def test_cp10_07_conflicting_catalog_identity_rejected_without_partial_plan(self):
        source = build_source_bytes()
        document = load_pmx(io.BytesIO(source))
        result = smart_inspection._analyze_entries((_material(1),))
        group = smart_draft.group_smart_materials(result, SmartPartKind.EYES)
        conflicting = replace(result, entries=(_material(1), _material(1, "Hair")))
        with self.assertRaises(SmartMaterialDraftError) as raised:
            smart_draft._validate_material_group_against_document(document, conflicting, group)
        self.assertEqual(raised.exception.reason, "source_evidence_mismatch")

    def test_cp10_08_wrong_evidence_field_types_rejected_without_coercion(self):
        bad_cases = (
            lambda: SmartPartEvidence(source_kind=SmartPartEvidenceKind.MATERIAL, source_index=1.0, reason="x"),
            lambda: SmartPartEvidence(source_kind=SmartPartEvidenceKind.MATERIAL, source_index=0, reason=2),
            lambda: _material(0, name=None),
            lambda: SmartPart(kind=SmartPartKind.EYES, evidence=[_evidence()]),
            lambda: SmartPart(kind="eyes", evidence=(_evidence(),)),
        )
        for bad in bad_cases:
            with self.subTest(case=str(bad)):
                with self.assertRaises((TypeError, ValueError)):
                    bad()

    def test_cp10_09_malformed_semantic_label_cannot_infer_edit_authority(self):
        with self.assertRaises(TypeError):
            _material(0, name=123)
        # Cyrillic capital IE looks like Latin E, but exact-alias matching must not infer.
        result = smart_inspection._analyze_entries((_material(0, "\u0415yes"),))
        capability = smart_draft.discover_smart_material_capability(result, SmartPartKind.EYES)
        self.assertIs(capability.status, SmartMaterialCapabilityStatus.UNSUPPORTED)
        self.assertEqual(capability.material_indices, ())

    def test_cp10_10_empty_evidence_cannot_grant_supported_capability(self):
        with self.assertRaises(ValueError):
            SmartPart(kind=SmartPartKind.EYES, evidence=())
        result = smart_inspection._analyze_entries(())
        capability = smart_draft.discover_smart_material_capability(result, SmartPartKind.EYES)
        self.assertIs(capability.status, SmartMaterialCapabilityStatus.UNSUPPORTED)
        self.assertEqual(capability.reason, "no_exact_material_evidence")
        self.assertEqual(capability.material_indices, ())
        self.assertEqual(capability.evidence, ())

    def test_cp10_11_reordered_evidence_has_identical_canonical_material_targets(self):
        entries = (_material(7, "Eyes"), _material(2, "\u77b3"))
        forward = smart_inspection._analyze_entries(entries)
        reverse = smart_inspection._analyze_entries(tuple(reversed(entries)))
        g1 = smart_draft.group_smart_materials(forward, SmartPartKind.EYES)
        g2 = smart_draft.group_smart_materials(reverse, SmartPartKind.EYES)
        self.assertEqual(g1, g2)
        self.assertEqual(g1.material_indices, (2, 7))
        for kind in SmartMaterialAppearanceCapabilityKind:
            with self.subTest(kind=kind):
                self.assertEqual(
                    resolve_smart_material_appearance_capability(forward, SmartPartKind.EYES, kind),
                    resolve_smart_material_appearance_capability(reverse, SmartPartKind.EYES, kind),
                )

    def test_cp10_12_cross_source_catalog_evidence_rejected_before_plan(self):
        source = build_source_bytes()
        document = load_pmx(io.BytesIO(source))
        foreign = _material(1, "Eyes", "FORGED_OTHER_PMX_IDENTITY")
        result = smart_inspection._analyze_entries((foreign,))
        group = smart_draft.group_smart_materials(result, SmartPartKind.EYES)
        with self.assertRaises(SmartMaterialDraftError) as raised:
            smart_draft._validate_material_group_against_document(document, result, group)
        self.assertEqual(raised.exception.reason, "source_evidence_mismatch")

    def test_cp10_13_stale_draft_from_another_pmx_cannot_preview(self):
        source_a = build_source_bytes()
        source_b = build_ambiguous_source()
        self.assertNotEqual(hashlib.sha256(source_a).digest(), hashlib.sha256(source_b).digest())
        draft_a = smart_draft.build_smart_material_color_draft(source_a, SmartPartKind.EYES, "blue")
        self.assert_fail_closed(lambda: preview_edit(source_b, draft_a))

    def test_cp10_14_contradictory_semantic_labels_block_without_partial_selection(self):
        result = smart_inspection._analyze_entries(
            (_material(0, "Eyes", "Hair"), _material(1, "Eyes"))
        )
        capability = smart_draft.discover_smart_material_capability(result, SmartPartKind.EYES)
        self.assertIs(capability.status, SmartMaterialCapabilityStatus.BLOCKED)
        self.assertEqual(capability.reason, "ambiguous_semantic_selection")
        self.assertEqual(capability.material_indices, (1,))


if __name__ == "__main__":
    unittest.main()
