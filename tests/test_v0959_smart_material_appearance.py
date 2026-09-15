"""v0.9.5.9 Smart Material Appearance capability-model contract tests."""

from __future__ import annotations

import dataclasses
import hashlib
import inspect
import io
import unittest
from unittest.mock import patch

from mmd_registry.pmx import load_pmx
from mmd_registry.pmx.editing.numeric import canonicalize_pmx_float32
from mmd_registry.pmx.editing.operations import UpdateMaterial
from mmd_registry.pmx.editing.preview import (
    PmxEditPreview,
    calculate_pmx_edit_plan_sha256,
)
import mmd_registry.services as services
import mmd_registry.services._smart_material_preview as smart_material_preview
import mmd_registry.services._smart_inspection as smart_inspection
from mmd_registry.services._smart_material_appearance import (
    SmartMaterialAppearanceCapability,
    SmartMaterialAppearanceCapabilityKind,
    SmartMaterialEdgeIntent,
    SmartMaterialSpecularIntent,
    SmartMaterialTransparencyIntent,
    build_smart_material_appearance_draft,
    preview_smart_material_appearance_draft,
    resolve_smart_material_appearance_capability,
)
from mmd_registry.services._smart_material_draft import (
    SmartMaterialCapabilityStatus,
    SmartMaterialDraftError,
)
from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringBoneCatalogEntry,
    PmxStructuralAuthoringMaterialCatalogEntry,
    PmxStructuralAuthoringMorphCatalogEntry,
    PmxStructuralAuthoringTextureCatalogEntry,
)
from mmd_registry.smart_part_confidence import SmartPartConfidence
from tests.mmd_fixtures import (
    build_pmx_bone,
    build_pmx_material,
    build_pmx_structure,
)
from mmd_registry.smart_parts import (
    SmartPartEvidence,
    SmartPartEvidenceKind,
    SmartPartKind,
)


def material_evidence(
    source_index: int,
    reason: str = "exact_name_alias:eyes",
) -> SmartPartEvidence:
    return SmartPartEvidence(
        source_kind=SmartPartEvidenceKind.MATERIAL,
        source_index=source_index,
        reason=reason,
    )


def material_entry(
    source_index: int,
    local_name: str,
    universal_name: str = "",
) -> PmxStructuralAuthoringMaterialCatalogEntry:
    return PmxStructuralAuthoringMaterialCatalogEntry(
        source_index=source_index,
        local_name=local_name,
        universal_name=universal_name,
        texture_index=-1,
        sphere_texture_index=-1,
        surface_index_count=0,
    )


def bone_entry(
    source_index: int,
    local_name: str,
) -> PmxStructuralAuthoringBoneCatalogEntry:
    return PmxStructuralAuthoringBoneCatalogEntry(
        source_index=source_index,
        local_name=local_name,
        universal_name="",
        parent_bone_index=-1,
        position=(0.0, 0.0, 0.0),
        flag_names=(),
    )


def morph_entry(
    source_index: int,
    local_name: str,
) -> PmxStructuralAuthoringMorphCatalogEntry:
    return PmxStructuralAuthoringMorphCatalogEntry(
        source_index=source_index,
        local_name=local_name,
        universal_name="",
        panel_name="eye",
        morph_type_name="vertex",
        offset_count=0,
    )


class SmartMaterialAppearanceCapabilityKindTests(unittest.TestCase):
    def test_exact_frozen_capability_vocabulary(self) -> None:
        self.assertEqual(
            tuple(item.value for item in SmartMaterialAppearanceCapabilityKind),
            ("transparency", "material_specular", "material_edge"),
        )

    def test_capability_kind_rejects_out_of_scope_candidate(self) -> None:
        with self.assertRaises(ValueError):
            SmartMaterialAppearanceCapabilityKind("material_texture")


class SmartMaterialAppearanceCapabilityTests(unittest.TestCase):
    def test_supported_exact_material_capability(self) -> None:
        evidence = (material_evidence(2),)
        capability = SmartMaterialAppearanceCapability(
            part_kind=SmartPartKind.EYES,
            capability_kind=SmartMaterialAppearanceCapabilityKind.TRANSPARENCY,
            status=SmartMaterialCapabilityStatus.SUPPORTED,
            reason="exact_material_evidence",
            material_indices=(2,),
            evidence=evidence,
        )

        self.assertTrue(capability.supported)
        self.assertFalse(capability.blocked)
        self.assertEqual(capability.material_indices, (2,))
        self.assertEqual(capability.evidence, evidence)

    def test_unsupported_requires_no_exact_material_evidence(self) -> None:
        capability = SmartMaterialAppearanceCapability(
            part_kind=SmartPartKind.EYES,
            capability_kind=SmartMaterialAppearanceCapabilityKind.MATERIAL_SPECULAR,
            status=SmartMaterialCapabilityStatus.UNSUPPORTED,
            reason="no_exact_material_evidence",
            material_indices=(),
            evidence=(),
        )

        self.assertFalse(capability.supported)
        self.assertFalse(capability.blocked)

        with self.assertRaises(ValueError):
            SmartMaterialAppearanceCapability(
                part_kind=SmartPartKind.EYES,
                capability_kind=SmartMaterialAppearanceCapabilityKind.MATERIAL_SPECULAR,
                status=SmartMaterialCapabilityStatus.UNSUPPORTED,
                reason="no_exact_material_evidence",
                material_indices=(2,),
                evidence=(material_evidence(2),),
            )

    def test_blocked_can_retain_safe_exact_material_provenance(self) -> None:
        evidence = (material_evidence(4),)
        capability = SmartMaterialAppearanceCapability(
            part_kind=SmartPartKind.EYES,
            capability_kind=SmartMaterialAppearanceCapabilityKind.MATERIAL_EDGE,
            status=SmartMaterialCapabilityStatus.BLOCKED,
            reason="ambiguous_semantic_selection",
            material_indices=(4,),
            evidence=evidence,
        )

        self.assertTrue(capability.blocked)
        self.assertFalse(capability.supported)
        self.assertEqual(capability.material_indices, (4,))
        self.assertEqual(capability.evidence, evidence)

    def test_status_reason_mapping_is_exact(self) -> None:
        cases = (
            (
                SmartMaterialCapabilityStatus.SUPPORTED,
                "ambiguous_semantic_selection",
                (0,),
                (material_evidence(0),),
            ),
            (
                SmartMaterialCapabilityStatus.UNSUPPORTED,
                "exact_material_evidence",
                (),
                (),
            ),
            (
                SmartMaterialCapabilityStatus.BLOCKED,
                "no_exact_material_evidence",
                (),
                (),
            ),
        )
        for status, reason, indices, evidence in cases:
            with self.subTest(status=status, reason=reason):
                with self.assertRaises(ValueError):
                    SmartMaterialAppearanceCapability(
                        part_kind=SmartPartKind.EYES,
                        capability_kind=SmartMaterialAppearanceCapabilityKind.TRANSPARENCY,
                        status=status,
                        reason=reason,
                        material_indices=indices,
                        evidence=evidence,
                    )

    def test_material_indices_are_exact_unique_ascending_nonnegative_ints(self) -> None:
        invalid = (
            ((1, 0), (material_evidence(0), material_evidence(1))),
            ((0, 0), (material_evidence(0),)),
            ((-1,), (material_evidence(0),)),
            ((True,), (material_evidence(0),)),
        )
        for indices, evidence in invalid:
            with self.subTest(indices=indices):
                with self.assertRaises(ValueError):
                    SmartMaterialAppearanceCapability(
                        part_kind=SmartPartKind.EYES,
                        capability_kind=SmartMaterialAppearanceCapabilityKind.TRANSPARENCY,
                        status=SmartMaterialCapabilityStatus.SUPPORTED,
                        reason="exact_material_evidence",
                        material_indices=indices,
                        evidence=evidence,
                    )

    def test_evidence_must_be_exact_material_evidence(self) -> None:
        non_material = SmartPartEvidence(
            source_kind=SmartPartEvidenceKind.BONE,
            source_index=0,
            reason="exact_name_alias:eyes",
        )
        with self.assertRaises(ValueError):
            SmartMaterialAppearanceCapability(
                part_kind=SmartPartKind.EYES,
                capability_kind=SmartMaterialAppearanceCapabilityKind.TRANSPARENCY,
                status=SmartMaterialCapabilityStatus.SUPPORTED,
                reason="exact_material_evidence",
                material_indices=(0,),
                evidence=(non_material,),
            )

    def test_evidence_identity_must_match_material_indices(self) -> None:
        with self.assertRaises(ValueError):
            SmartMaterialAppearanceCapability(
                part_kind=SmartPartKind.EYES,
                capability_kind=SmartMaterialAppearanceCapabilityKind.TRANSPARENCY,
                status=SmartMaterialCapabilityStatus.SUPPORTED,
                reason="exact_material_evidence",
                material_indices=(2,),
                evidence=(material_evidence(3),),
            )

    def test_evidence_must_be_duplicate_free_and_canonical(self) -> None:
        first = material_evidence(1, "a:eyes")
        second = material_evidence(2, "b:eyes")

        with self.assertRaises(ValueError):
            SmartMaterialAppearanceCapability(
                part_kind=SmartPartKind.EYES,
                capability_kind=SmartMaterialAppearanceCapabilityKind.TRANSPARENCY,
                status=SmartMaterialCapabilityStatus.SUPPORTED,
                reason="exact_material_evidence",
                material_indices=(1,),
                evidence=(first, first),
            )

        with self.assertRaises(ValueError):
            SmartMaterialAppearanceCapability(
                part_kind=SmartPartKind.EYES,
                capability_kind=SmartMaterialAppearanceCapabilityKind.TRANSPARENCY,
                status=SmartMaterialCapabilityStatus.SUPPORTED,
                reason="exact_material_evidence",
                material_indices=(1, 2),
                evidence=(second, first),
            )

    def test_supported_requires_nonempty_exact_material_identity(self) -> None:
        with self.assertRaises(ValueError):
            SmartMaterialAppearanceCapability(
                part_kind=SmartPartKind.EYES,
                capability_kind=SmartMaterialAppearanceCapabilityKind.TRANSPARENCY,
                status=SmartMaterialCapabilityStatus.SUPPORTED,
                reason="exact_material_evidence",
                material_indices=(),
                evidence=(),
            )

    def test_capability_model_is_frozen_and_slotted(self) -> None:
        capability = SmartMaterialAppearanceCapability(
            part_kind=SmartPartKind.EYES,
            capability_kind=SmartMaterialAppearanceCapabilityKind.TRANSPARENCY,
            status=SmartMaterialCapabilityStatus.SUPPORTED,
            reason="exact_material_evidence",
            material_indices=(0,),
            evidence=(material_evidence(0),),
        )

        self.assertFalse(hasattr(capability, "__dict__"))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            capability.reason = "changed"  # type: ignore[misc]

    def test_capability_model_reuses_existing_status_authority(self) -> None:
        capability = SmartMaterialAppearanceCapability(
            part_kind=SmartPartKind.EYES,
            capability_kind=SmartMaterialAppearanceCapabilityKind.TRANSPARENCY,
            status=SmartMaterialCapabilityStatus.SUPPORTED,
            reason="exact_material_evidence",
            material_indices=(0,),
            evidence=(material_evidence(0),),
        )
        self.assertIs(
            capability.status.__class__,
            SmartMaterialCapabilityStatus,
        )


class SmartMaterialTransparencyIntentTests(unittest.TestCase):
    def test_alpha_is_canonicalized_to_pmx_float32(self) -> None:
        intent = SmartMaterialTransparencyIntent(alpha=0.1)

        self.assertEqual(intent.alpha, canonicalize_pmx_float32(0.1))
        self.assertEqual(
            intent,
            SmartMaterialTransparencyIntent(
                alpha=canonicalize_pmx_float32(0.1),
            ),
        )

    def test_alpha_accepts_exact_bounds(self) -> None:
        self.assertEqual(SmartMaterialTransparencyIntent(alpha=0.0).alpha, 0.0)
        self.assertEqual(SmartMaterialTransparencyIntent(alpha=1.0).alpha, 1.0)

    def test_alpha_rejects_non_float_and_bool(self) -> None:
        for value in (0, 1, True, False, "0.5", None):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    SmartMaterialTransparencyIntent(alpha=value)  # type: ignore[arg-type]

    def test_alpha_rejects_nonfinite_float32_overflow_and_out_of_range(self) -> None:
        for value in (
            float("nan"),
            float("inf"),
            float("-inf"),
            1e40,
            -0.0001,
            1.0001,
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    SmartMaterialTransparencyIntent(alpha=value)

    def test_transparency_intent_is_frozen_and_slotted(self) -> None:
        intent = SmartMaterialTransparencyIntent(alpha=0.5)

        self.assertFalse(hasattr(intent, "__dict__"))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            intent.alpha = 0.25  # type: ignore[misc]


class SmartMaterialSpecularIntentTests(unittest.TestCase):
    def test_specular_and_strength_are_independently_optional_but_not_both_missing(self) -> None:
        specular_only = SmartMaterialSpecularIntent(
            specular=(0.1, 0.2, 0.3),
        )
        strength_only = SmartMaterialSpecularIntent(strength=2.5)

        self.assertEqual(
            specular_only.specular,
            tuple(
                canonicalize_pmx_float32(value)
                for value in (0.1, 0.2, 0.3)
            ),
        )
        self.assertIsNone(specular_only.strength)
        self.assertIsNone(strength_only.specular)
        self.assertEqual(
            strength_only.strength,
            canonicalize_pmx_float32(2.5),
        )

        with self.assertRaises(ValueError):
            SmartMaterialSpecularIntent()

    def test_specular_rejects_wrong_tuple_shape_or_component_types(self) -> None:
        invalid = (
            [0.1, 0.2, 0.3],
            (0.1, 0.2),
            (0.1, 0.2, 0.3, 0.4),
            (0.1, 0.2, 1),
            (0.1, 0.2, True),
        )
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises((TypeError, ValueError)):
                    SmartMaterialSpecularIntent(specular=value)  # type: ignore[arg-type]

    def test_strength_requires_exact_float(self) -> None:
        for value in (1, True, "1.0"):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    SmartMaterialSpecularIntent(strength=value)  # type: ignore[arg-type]

    def test_specular_numeric_values_reject_nonfinite_and_float32_overflow(self) -> None:
        for value in (float("nan"), float("inf"), float("-inf"), 1e40):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    SmartMaterialSpecularIntent(
                        specular=(0.1, value, 0.3),
                    )
                with self.assertRaises(ValueError):
                    SmartMaterialSpecularIntent(strength=value)

    def test_specular_has_no_invented_visual_clamp(self) -> None:
        intent = SmartMaterialSpecularIntent(
            specular=(-2.0, 1.5, 9.0),
            strength=-3.25,
        )

        self.assertEqual(
            intent.specular,
            (
                canonicalize_pmx_float32(-2.0),
                canonicalize_pmx_float32(1.5),
                canonicalize_pmx_float32(9.0),
            ),
        )
        self.assertEqual(
            intent.strength,
            canonicalize_pmx_float32(-3.25),
        )

    def test_specular_intent_is_frozen_and_slotted(self) -> None:
        intent = SmartMaterialSpecularIntent(strength=1.0)

        self.assertFalse(hasattr(intent, "__dict__"))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            intent.strength = 2.0  # type: ignore[misc]


class SmartMaterialEdgeIntentTests(unittest.TestCase):
    def test_color_and_scale_are_independently_optional_but_not_both_missing(self) -> None:
        color_only = SmartMaterialEdgeIntent(
            color=(0.1, 0.2, 0.3, 0.4),
        )
        scale_only = SmartMaterialEdgeIntent(scale=1.25)

        self.assertEqual(
            color_only.color,
            tuple(
                canonicalize_pmx_float32(value)
                for value in (0.1, 0.2, 0.3, 0.4)
            ),
        )
        self.assertIsNone(color_only.scale)
        self.assertIsNone(scale_only.color)
        self.assertEqual(
            scale_only.scale,
            canonicalize_pmx_float32(1.25),
        )

        with self.assertRaises(ValueError):
            SmartMaterialEdgeIntent()

    def test_edge_color_rejects_wrong_tuple_shape_or_component_types(self) -> None:
        invalid = (
            [0.1, 0.2, 0.3, 0.4],
            (0.1, 0.2, 0.3),
            (0.1, 0.2, 0.3, 0.4, 0.5),
            (0.1, 0.2, 0.3, 1),
            (0.1, 0.2, 0.3, False),
        )
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises((TypeError, ValueError)):
                    SmartMaterialEdgeIntent(color=value)  # type: ignore[arg-type]

    def test_edge_scale_requires_exact_float(self) -> None:
        for value in (1, True, "1.0"):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    SmartMaterialEdgeIntent(scale=value)  # type: ignore[arg-type]

    def test_edge_numeric_values_reject_nonfinite_and_float32_overflow(self) -> None:
        for value in (float("nan"), float("inf"), float("-inf"), 1e40):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    SmartMaterialEdgeIntent(
                        color=(0.1, 0.2, value, 0.4),
                    )
                with self.assertRaises(ValueError):
                    SmartMaterialEdgeIntent(scale=value)

    def test_edge_has_no_invented_visual_clamp(self) -> None:
        intent = SmartMaterialEdgeIntent(
            color=(-1.0, 2.0, 3.5, 8.0),
            scale=-2.5,
        )

        self.assertEqual(
            intent.color,
            (
                canonicalize_pmx_float32(-1.0),
                canonicalize_pmx_float32(2.0),
                canonicalize_pmx_float32(3.5),
                canonicalize_pmx_float32(8.0),
            ),
        )
        self.assertEqual(
            intent.scale,
            canonicalize_pmx_float32(-2.5),
        )

    def test_edge_intent_is_frozen_and_slotted(self) -> None:
        intent = SmartMaterialEdgeIntent(scale=1.0)

        self.assertFalse(hasattr(intent, "__dict__"))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            intent.scale = 2.0  # type: ignore[misc]


class SmartMaterialAppearanceIntentDeterminismTests(unittest.TestCase):
    def test_canonicalized_intents_have_deterministic_equality(self) -> None:
        transparency_a = SmartMaterialTransparencyIntent(alpha=0.1)
        transparency_b = SmartMaterialTransparencyIntent(
            alpha=canonicalize_pmx_float32(0.1),
        )
        specular_a = SmartMaterialSpecularIntent(
            specular=(0.1, 0.2, 0.3),
            strength=0.4,
        )
        specular_b = SmartMaterialSpecularIntent(
            specular=tuple(
                canonicalize_pmx_float32(value)
                for value in (0.1, 0.2, 0.3)
            ),
            strength=canonicalize_pmx_float32(0.4),
        )
        edge_a = SmartMaterialEdgeIntent(
            color=(0.1, 0.2, 0.3, 0.4),
            scale=0.5,
        )
        edge_b = SmartMaterialEdgeIntent(
            color=tuple(
                canonicalize_pmx_float32(value)
                for value in (0.1, 0.2, 0.3, 0.4)
            ),
            scale=canonicalize_pmx_float32(0.5),
        )

        self.assertEqual(transparency_a, transparency_b)
        self.assertEqual(specular_a, specular_b)
        self.assertEqual(edge_a, edge_b)

    def test_dataclass_serialization_is_stable_after_canonicalization(self) -> None:
        intent = SmartMaterialSpecularIntent(
            specular=(0.1, 0.2, 0.3),
            strength=0.4,
        )

        first = dataclasses.asdict(intent)
        second = dataclasses.asdict(
            SmartMaterialSpecularIntent(
                specular=tuple(first["specular"]),
                strength=first["strength"],
            )
        )
        self.assertEqual(first, second)


class SmartMaterialAppearanceTargetResolutionTests(unittest.TestCase):
    def test_exact_material_evidence_supports_each_scoped_capability(self) -> None:
        result = smart_inspection._analyze_entries((material_entry(2, "Eyes"),))

        for capability_kind in SmartMaterialAppearanceCapabilityKind:
            with self.subTest(capability_kind=capability_kind):
                capability = resolve_smart_material_appearance_capability(
                    result,
                    SmartPartKind.EYES,
                    capability_kind,
                )
                self.assertIs(
                    capability.status,
                    SmartMaterialCapabilityStatus.SUPPORTED,
                )
                self.assertEqual(capability.reason, "exact_material_evidence")
                self.assertEqual(capability.material_indices, (2,))
                self.assertTrue(capability.evidence)
                self.assertTrue(
                    all(
                        item.source_kind is SmartPartEvidenceKind.MATERIAL
                        for item in capability.evidence
                    )
                )

    def test_texture_only_evidence_never_grants_appearance_permission(self) -> None:
        result = smart_inspection._analyze_entries(
            (
                PmxStructuralAuthoringTextureCatalogEntry(
                    source_index=0,
                    path="eyes.png",
                ),
            )
        )
        capability = resolve_smart_material_appearance_capability(
            result,
            SmartPartKind.EYES,
            SmartMaterialAppearanceCapabilityKind.TRANSPARENCY,
        )
        self.assertIs(
            capability.status,
            SmartMaterialCapabilityStatus.UNSUPPORTED,
        )
        self.assertEqual(capability.reason, "no_exact_material_evidence")
        self.assertEqual(capability.material_indices, ())
        self.assertEqual(capability.evidence, ())

    def test_high_confidence_non_material_evidence_is_not_permission(self) -> None:
        result = smart_inspection._analyze_entries(
            (
                bone_entry(0, "左目"),
                morph_entry(1, "blink"),
            )
        )
        self.assertIs(result.assessments[0].confidence, SmartPartConfidence.HIGH)

        capability = resolve_smart_material_appearance_capability(
            result,
            SmartPartKind.EYES,
            SmartMaterialAppearanceCapabilityKind.MATERIAL_SPECULAR,
        )
        self.assertIs(
            capability.status,
            SmartMaterialCapabilityStatus.UNSUPPORTED,
        )
        self.assertEqual(capability.reason, "no_exact_material_evidence")
        self.assertEqual(capability.material_indices, ())

    def test_ambiguity_blocks_without_silent_candidate_tiebreak(self) -> None:
        result = smart_inspection._analyze_entries(
            (
                material_entry(0, "Eyes", "Hair"),
                material_entry(1, "Eyes"),
            )
        )
        capability = resolve_smart_material_appearance_capability(
            result,
            SmartPartKind.EYES,
            SmartMaterialAppearanceCapabilityKind.MATERIAL_EDGE,
        )
        self.assertIs(
            capability.status,
            SmartMaterialCapabilityStatus.BLOCKED,
        )
        self.assertEqual(capability.reason, "ambiguous_semantic_selection")
        self.assertEqual(capability.material_indices, (1,))
        self.assertTrue(
            all(item.source_index != 0 for item in capability.evidence)
        )

    def test_multiple_exact_material_targets_are_all_retained_in_canonical_order(self) -> None:
        result = smart_inspection._analyze_entries(
            (
                material_entry(5, "Eyes"),
                material_entry(2, "瞳"),
            )
        )
        capability = resolve_smart_material_appearance_capability(
            result,
            SmartPartKind.EYES,
            SmartMaterialAppearanceCapabilityKind.TRANSPARENCY,
        )
        self.assertIs(
            capability.status,
            SmartMaterialCapabilityStatus.SUPPORTED,
        )
        self.assertEqual(capability.material_indices, (2, 5))
        self.assertEqual(
            tuple(item.source_index for item in capability.evidence),
            (2, 5),
        )

    def test_reversed_equivalent_material_input_resolves_identically(self) -> None:
        forward = smart_inspection._analyze_entries(
            (
                material_entry(2, "瞳"),
                material_entry(5, "Eyes"),
            )
        )
        reversed_result = smart_inspection._analyze_entries(
            (
                material_entry(5, "Eyes"),
                material_entry(2, "瞳"),
            )
        )

        forward_capability = resolve_smart_material_appearance_capability(
            forward,
            SmartPartKind.EYES,
            SmartMaterialAppearanceCapabilityKind.MATERIAL_SPECULAR,
        )
        reversed_capability = resolve_smart_material_appearance_capability(
            reversed_result,
            SmartPartKind.EYES,
            SmartMaterialAppearanceCapabilityKind.MATERIAL_SPECULAR,
        )
        self.assertEqual(forward_capability, reversed_capability)

    def test_capability_kind_changes_only_requested_appearance_primitive(self) -> None:
        result = smart_inspection._analyze_entries((material_entry(3, "Eyes"),))

        transparency = resolve_smart_material_appearance_capability(
            result,
            SmartPartKind.EYES,
            SmartMaterialAppearanceCapabilityKind.TRANSPARENCY,
        )
        edge = resolve_smart_material_appearance_capability(
            result,
            SmartPartKind.EYES,
            SmartMaterialAppearanceCapabilityKind.MATERIAL_EDGE,
        )

        self.assertEqual(
            (
                transparency.status,
                transparency.reason,
                transparency.material_indices,
                transparency.evidence,
            ),
            (
                edge.status,
                edge.reason,
                edge.material_indices,
                edge.evidence,
            ),
        )
        self.assertIs(
            transparency.capability_kind,
            SmartMaterialAppearanceCapabilityKind.TRANSPARENCY,
        )
        self.assertIs(
            edge.capability_kind,
            SmartMaterialAppearanceCapabilityKind.MATERIAL_EDGE,
        )

    def test_resolver_rejects_non_enum_capability_kind(self) -> None:
        result = smart_inspection._analyze_entries((material_entry(0, "Eyes"),))

        with self.assertRaises(TypeError):
            resolve_smart_material_appearance_capability(
                result,
                SmartPartKind.EYES,
                "transparency",  # type: ignore[arg-type]
            )


def build_appearance_source_bytes() -> bytes:
    materials = (
        build_pmx_material(
            local_name="Hair",
            universal_name="",
            diffuse=(0.8, 0.7, 0.6, 0.9),
            specular=(0.01, 0.02, 0.03),
            specular_strength=0.4,
            edge_color=(0.1, 0.2, 0.3, 0.4),
            edge_scale=1.1,
            texture_index=-1,
            sphere_texture_index=-1,
            sphere_mode=0,
            toon_reference_mode=1,
            toon_reference_index=0,
            memo="hair",
            surface_index_count=3,
        ),
        build_pmx_material(
            local_name="Eyes",
            universal_name="",
            diffuse=(0.2, 0.3, 0.4, 0.35),
            specular=(0.11, 0.12, 0.13),
            specular_strength=0.45,
            edge_color=(0.21, 0.22, 0.23, 0.24),
            edge_scale=1.2,
            texture_index=-1,
            sphere_texture_index=-1,
            sphere_mode=0,
            toon_reference_mode=1,
            toon_reference_index=0,
            memo="eyes",
            surface_index_count=3,
        ),
        build_pmx_material(
            local_name="瞳",
            universal_name="",
            diffuse=(0.6, 0.5, 0.4, 0.65),
            specular=(0.31, 0.32, 0.33),
            specular_strength=0.55,
            edge_color=(0.41, 0.42, 0.43, 0.44),
            edge_scale=1.3,
            texture_index=-1,
            sphere_texture_index=-1,
            sphere_mode=0,
            toon_reference_mode=1,
            toon_reference_index=0,
            memo="iris",
            surface_index_count=3,
        ),
    )
    return build_pmx_structure(
        surface_indices=(0, 0, 0, 0, 0, 0, 0, 0, 0),
        texture_paths=(),
        materials=materials,
        bones=(build_pmx_bone(),),
    )


def build_appearance_texture_only_source() -> bytes:
    return build_pmx_structure(
        surface_indices=(0, 0, 0),
        texture_paths=("eyes.png",),
        materials=(
            build_pmx_material(
                local_name="Body",
                universal_name="",
                texture_index=0,
                sphere_texture_index=-1,
                sphere_mode=0,
                toon_reference_mode=1,
                toon_reference_index=0,
                memo="",
                surface_index_count=3,
            ),
        ),
        bones=(build_pmx_bone(),),
    )


def build_appearance_ambiguous_source() -> bytes:
    return build_pmx_structure(
        surface_indices=(0, 0, 0),
        texture_paths=(),
        materials=(
            build_pmx_material(
                local_name="Eyes",
                universal_name="Hair",
                texture_index=-1,
                sphere_texture_index=-1,
                sphere_mode=0,
                toon_reference_mode=1,
                toon_reference_index=0,
                memo="",
                surface_index_count=3,
            ),
        ),
        bones=(build_pmx_bone(),),
    )


class SmartMaterialAppearanceDraftCompositionTests(unittest.TestCase):
    def test_transparency_draft_preserves_source_rgb_and_updates_only_diffuse(self) -> None:
        source_bytes = build_appearance_source_bytes()
        source = load_pmx(io.BytesIO(source_bytes))

        plan = build_smart_material_appearance_draft(
            source_bytes,
            SmartPartKind.EYES,
            SmartMaterialTransparencyIntent(alpha=0.25),
        )

        self.assertEqual(plan.schema_version, 1)
        self.assertEqual(
            plan.expected_source_sha256,
            hashlib.sha256(source_bytes).hexdigest(),
        )
        self.assertEqual(
            tuple(operation.material_index for operation in plan.operations),
            (1, 2),
        )
        self.assertTrue(
            all(isinstance(operation, UpdateMaterial) for operation in plan.operations)
        )
        for operation, material_index in zip(plan.operations, (1, 2)):
            source_diffuse = source.materials[material_index].diffuse
            self.assertEqual(
                operation.diffuse,
                (
                    source_diffuse[0],
                    source_diffuse[1],
                    source_diffuse[2],
                    canonicalize_pmx_float32(0.25),
                ),
            )
            self.assertEqual(
                tuple(
                    key
                    for key in operation.to_dict()
                    if key not in {"op", "material_index"}
                ),
                ("diffuse",),
            )

    def test_specular_draft_populates_only_requested_fields(self) -> None:
        source_bytes = build_appearance_source_bytes()

        specular_plan = build_smart_material_appearance_draft(
            source_bytes,
            SmartPartKind.EYES,
            SmartMaterialSpecularIntent(
                specular=(0.7, 0.8, 0.9),
            ),
        )
        strength_plan = build_smart_material_appearance_draft(
            source_bytes,
            SmartPartKind.EYES,
            SmartMaterialSpecularIntent(
                strength=1.75,
            ),
        )

        for operation in specular_plan.operations:
            self.assertEqual(
                operation.specular,
                tuple(
                    canonicalize_pmx_float32(value)
                    for value in (0.7, 0.8, 0.9)
                ),
            )
            self.assertIsNone(operation.specular_strength)
            self.assertEqual(
                tuple(
                    key
                    for key in operation.to_dict()
                    if key not in {"op", "material_index"}
                ),
                ("specular",),
            )

        for operation in strength_plan.operations:
            self.assertIsNone(operation.specular)
            self.assertEqual(
                operation.specular_strength,
                canonicalize_pmx_float32(1.75),
            )
            self.assertEqual(
                tuple(
                    key
                    for key in operation.to_dict()
                    if key not in {"op", "material_index"}
                ),
                ("specular_strength",),
            )

    def test_edge_draft_populates_only_requested_fields_and_preserves_drawing_flags(self) -> None:
        source_bytes = build_appearance_source_bytes()

        color_plan = build_smart_material_appearance_draft(
            source_bytes,
            SmartPartKind.EYES,
            SmartMaterialEdgeIntent(
                color=(0.8, 0.7, 0.6, 0.5),
            ),
        )
        scale_plan = build_smart_material_appearance_draft(
            source_bytes,
            SmartPartKind.EYES,
            SmartMaterialEdgeIntent(
                scale=2.25,
            ),
        )

        for operation in color_plan.operations:
            self.assertEqual(
                operation.edge_color,
                tuple(
                    canonicalize_pmx_float32(value)
                    for value in (0.8, 0.7, 0.6, 0.5)
                ),
            )
            self.assertIsNone(operation.edge_scale)
            self.assertIsNone(operation.drawing_flags)
            self.assertEqual(
                tuple(
                    key
                    for key in operation.to_dict()
                    if key not in {"op", "material_index"}
                ),
                ("edge_color",),
            )

        for operation in scale_plan.operations:
            self.assertIsNone(operation.edge_color)
            self.assertEqual(
                operation.edge_scale,
                canonicalize_pmx_float32(2.25),
            )
            self.assertIsNone(operation.drawing_flags)
            self.assertEqual(
                tuple(
                    key
                    for key in operation.to_dict()
                    if key not in {"op", "material_index"}
                ),
                ("edge_scale",),
            )

    def test_multi_field_single_primitive_draft_uses_one_operation_per_material(self) -> None:
        source_bytes = build_appearance_source_bytes()

        plan = build_smart_material_appearance_draft(
            source_bytes,
            SmartPartKind.EYES,
            SmartMaterialSpecularIntent(
                specular=(0.2, 0.4, 0.6),
                strength=3.5,
            ),
        )

        self.assertEqual(len(plan.operations), 2)
        self.assertEqual(
            tuple(operation.material_index for operation in plan.operations),
            (1, 2),
        )
        for operation in plan.operations:
            self.assertEqual(
                tuple(
                    key
                    for key in operation.to_dict()
                    if key not in {"op", "material_index"}
                ),
                ("specular", "specular_strength"),
            )

    def test_draft_is_source_bound_deterministic_and_does_not_mutate_source_bytes(self) -> None:
        source_bytes = build_appearance_source_bytes()
        before = hashlib.sha256(source_bytes).hexdigest()
        intent = SmartMaterialEdgeIntent(
            color=(0.2, 0.3, 0.4, 0.5),
            scale=1.5,
        )

        first = build_smart_material_appearance_draft(
            source_bytes,
            SmartPartKind.EYES,
            intent,
        )
        second = build_smart_material_appearance_draft(
            source_bytes,
            SmartPartKind.EYES,
            intent,
        )

        self.assertEqual(first, second)
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(
            first.expected_source_sha256,
            before,
        )
        self.assertEqual(hashlib.sha256(source_bytes).hexdigest(), before)

    def test_texture_only_source_is_unsupported_fail_closed(self) -> None:
        with self.assertRaises(SmartMaterialDraftError) as raised:
            build_smart_material_appearance_draft(
                build_appearance_texture_only_source(),
                SmartPartKind.EYES,
                SmartMaterialTransparencyIntent(alpha=0.5),
            )

        self.assertEqual(
            raised.exception.reason,
            "unsupported_appearance_capability",
        )

    def test_ambiguous_source_is_blocked_fail_closed(self) -> None:
        with self.assertRaises(SmartMaterialDraftError) as raised:
            build_smart_material_appearance_draft(
                build_appearance_ambiguous_source(),
                SmartPartKind.EYES,
                SmartMaterialEdgeIntent(scale=1.0),
            )

        self.assertEqual(
            raised.exception.reason,
            "ambiguous_semantic_selection",
        )

    def test_draft_rejects_non_scoped_intent_type(self) -> None:
        with self.assertRaises(TypeError):
            build_smart_material_appearance_draft(
                build_appearance_source_bytes(),
                SmartPartKind.EYES,
                object(),  # type: ignore[arg-type]
            )

    def test_builder_has_no_apply_preview_writer_or_publication_authority(self) -> None:
        source = inspect.getsource(build_smart_material_appearance_draft)

        for forbidden in (
            "apply_edit",
            "preview_edit",
            "write_pmx_edit",
            "serialize_pmx",
            "writer",
            "index_remap",
            "os.replace",
            "Path(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


def material_changes_for_suffix(
    preview: PmxEditPreview,
    suffix: str,
):
    return tuple(
        change
        for change in preview.audit.changes
        if change.category == "material"
        and change.field_path.endswith(suffix)
    )


class SmartMaterialAppearancePreviewIntegrationTests(unittest.TestCase):
    def test_all_scoped_appearance_drafts_replay_through_existing_smart_preview_authority(self) -> None:
        source_bytes = build_appearance_source_bytes()
        cases = (
            SmartMaterialTransparencyIntent(alpha=0.25),
            SmartMaterialSpecularIntent(
                specular=(0.7, 0.8, 0.9),
                strength=1.75,
            ),
            SmartMaterialEdgeIntent(
                color=(0.8, 0.7, 0.6, 0.5),
                scale=2.25,
            ),
        )

        for intent in cases:
            with self.subTest(intent=type(intent).__name__):
                draft = build_smart_material_appearance_draft(
                    source_bytes,
                    SmartPartKind.EYES,
                    intent,
                )
                expected = (
                    smart_material_preview.preview_smart_material_color_draft(
                        source_bytes,
                        draft,
                    )
                )
                actual = preview_smart_material_appearance_draft(
                    source_bytes,
                    draft,
                )

                self.assertIsInstance(actual, PmxEditPreview)
                self.assertEqual(actual, expected)
                self.assertEqual(
                    actual.source_sha256,
                    hashlib.sha256(source_bytes).hexdigest(),
                )
                self.assertEqual(
                    actual.plan_sha256,
                    calculate_pmx_edit_plan_sha256(draft),
                )
                self.assertEqual(actual.plan_schema_version, 1)
                self.assertEqual(
                    actual.operation_count,
                    len(draft.operations),
                )
                self.assertEqual(
                    actual.to_dict()["output"],
                    {"written": False, "sha256": None},
                )
                self.assertEqual(
                    actual.to_dict()["verification"],
                    {
                        "semantic": "passed",
                        "input_unchanged": True,
                    },
                )

    def test_transparency_preview_exposes_exact_targets_and_diffuse_after_values(self) -> None:
        source_bytes = build_appearance_source_bytes()
        draft = build_smart_material_appearance_draft(
            source_bytes,
            SmartPartKind.EYES,
            SmartMaterialTransparencyIntent(alpha=0.25),
        )

        preview = preview_smart_material_appearance_draft(
            source_bytes,
            draft,
        )
        changes = material_changes_for_suffix(preview, ".diffuse")

        self.assertEqual(
            tuple(change.target_index for change in changes),
            tuple(operation.material_index for operation in draft.operations),
        )
        self.assertEqual(
            tuple(change.after for change in changes),
            tuple(operation.diffuse for operation in draft.operations),
        )
        self.assertEqual(
            tuple(
                change.field_path
                for change in preview.audit.changes
                if change.category == "material"
            ),
            tuple(change.field_path for change in changes),
        )

    def test_specular_preview_exposes_only_requested_specular_fields(self) -> None:
        source_bytes = build_appearance_source_bytes()
        draft = build_smart_material_appearance_draft(
            source_bytes,
            SmartPartKind.EYES,
            SmartMaterialSpecularIntent(
                specular=(0.2, 0.4, 0.6),
                strength=3.5,
            ),
        )

        preview = preview_smart_material_appearance_draft(
            source_bytes,
            draft,
        )
        specular_changes = material_changes_for_suffix(
            preview,
            ".specular",
        )
        strength_changes = material_changes_for_suffix(
            preview,
            ".specular_strength",
        )
        expected_indices = tuple(
            operation.material_index
            for operation in draft.operations
        )

        self.assertEqual(
            tuple(change.target_index for change in specular_changes),
            expected_indices,
        )
        self.assertEqual(
            tuple(change.after for change in specular_changes),
            tuple(operation.specular for operation in draft.operations),
        )
        self.assertEqual(
            tuple(change.target_index for change in strength_changes),
            expected_indices,
        )
        self.assertEqual(
            tuple(change.after for change in strength_changes),
            tuple(
                operation.specular_strength
                for operation in draft.operations
            ),
        )
        self.assertEqual(
            {
                change.field_path.rsplit(".", 1)[-1]
                for change in preview.audit.changes
                if change.category == "material"
            },
            {"specular", "specular_strength"},
        )

    def test_edge_preview_exposes_only_edge_fields_and_never_drawing_flags(self) -> None:
        source_bytes = build_appearance_source_bytes()
        draft = build_smart_material_appearance_draft(
            source_bytes,
            SmartPartKind.EYES,
            SmartMaterialEdgeIntent(
                color=(0.2, 0.3, 0.4, 0.5),
                scale=1.5,
            ),
        )

        preview = preview_smart_material_appearance_draft(
            source_bytes,
            draft,
        )
        color_changes = material_changes_for_suffix(
            preview,
            ".edge_color",
        )
        scale_changes = material_changes_for_suffix(
            preview,
            ".edge_scale",
        )
        expected_indices = tuple(
            operation.material_index
            for operation in draft.operations
        )

        self.assertEqual(
            tuple(change.target_index for change in color_changes),
            expected_indices,
        )
        self.assertEqual(
            tuple(change.after for change in color_changes),
            tuple(operation.edge_color for operation in draft.operations),
        )
        self.assertEqual(
            tuple(change.target_index for change in scale_changes),
            expected_indices,
        )
        self.assertEqual(
            tuple(change.after for change in scale_changes),
            tuple(operation.edge_scale for operation in draft.operations),
        )
        material_fields = {
            change.field_path.rsplit(".", 1)[-1]
            for change in preview.audit.changes
            if change.category == "material"
        }
        self.assertEqual(material_fields, {"edge_color", "edge_scale"})
        self.assertNotIn("drawing_flags", material_fields)

    def test_preview_is_deterministic_and_source_bytes_remain_unchanged(self) -> None:
        source_bytes = build_appearance_source_bytes()
        before_bytes = bytes(source_bytes)
        before_sha = hashlib.sha256(source_bytes).hexdigest()
        draft = build_smart_material_appearance_draft(
            source_bytes,
            SmartPartKind.EYES,
            SmartMaterialEdgeIntent(
                color=(0.2, 0.3, 0.4, 0.5),
                scale=1.5,
            ),
        )

        first = preview_smart_material_appearance_draft(
            source_bytes,
            draft,
        )
        second = preview_smart_material_appearance_draft(
            source_bytes,
            draft,
        )

        self.assertEqual(first, second)
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(source_bytes, before_bytes)
        self.assertEqual(
            hashlib.sha256(source_bytes).hexdigest(),
            before_sha,
        )

    def test_wrapper_forwards_exact_inputs_to_existing_smart_preview_bridge(self) -> None:
        source_bytes = build_appearance_source_bytes()
        draft = build_smart_material_appearance_draft(
            source_bytes,
            SmartPartKind.EYES,
            SmartMaterialTransparencyIntent(alpha=0.5),
        )
        sentinel = object()

        with patch.object(
            smart_material_preview,
            "preview_smart_material_color_draft",
            return_value=sentinel,
        ) as preview_mock:
            result = preview_smart_material_appearance_draft(
                source_bytes,
                draft,
            )

        self.assertIs(result, sentinel)
        preview_mock.assert_called_once_with(source_bytes, draft)

    def test_preview_wrapper_never_invokes_apply_or_write_authority(self) -> None:
        source_bytes = build_appearance_source_bytes()
        draft = build_smart_material_appearance_draft(
            source_bytes,
            SmartPartKind.EYES,
            SmartMaterialSpecularIntent(strength=1.25),
        )

        with (
            patch.object(
                services,
                "apply_edit",
                side_effect=AssertionError("apply_edit must not run"),
            ) as apply_mock,
            patch.object(
                services,
                "write_pmx_edit",
                side_effect=AssertionError("write_pmx_edit must not run"),
            ) as write_mock,
        ):
            result = preview_smart_material_appearance_draft(
                source_bytes,
                draft,
            )

        self.assertIsInstance(result, PmxEditPreview)
        apply_mock.assert_not_called()
        write_mock.assert_not_called()

    def test_wrapper_is_only_a_bridge_not_a_second_preview_simulator(self) -> None:
        source = inspect.getsource(
            preview_smart_material_appearance_draft
        )

        self.assertIn(
            "smart_material_preview.preview_smart_material_color_draft",
            source,
        )
        for forbidden in (
            "preview_edit(",
            "dry_run_pmx_edit",
            "apply_pmx_edit_plan",
            "serialize_pmx",
            "load_pmx",
            "apply_edit",
            "write_pmx_edit",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
