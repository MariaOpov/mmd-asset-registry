from __future__ import annotations

import itertools
import unittest

import mmd_registry.smart_part_detection as detection
import mmd_registry.smart_part_explainability as explainability
from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringBoneCatalogEntry,
    PmxStructuralAuthoringMaterialCatalogEntry,
    PmxStructuralAuthoringMorphCatalogEntry,
    PmxStructuralAuthoringRigidBodyCatalogEntry,
    PmxStructuralAuthoringTextureCatalogEntry,
    PmxStructuralAuthoringVertexCatalogEntry,
)
from mmd_registry.smart_parts import SmartPartKind


class SmartPartExplainabilityParityAdversarialTests(unittest.TestCase):
    def material(
        self,
        *,
        source_index: int,
        local_name: str = "",
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

    def bone(
        self,
        *,
        source_index: int,
        local_name: str = "",
        universal_name: str = "",
    ) -> PmxStructuralAuthoringBoneCatalogEntry:
        return PmxStructuralAuthoringBoneCatalogEntry(
            source_index=source_index,
            local_name=local_name,
            universal_name=universal_name,
            parent_bone_index=-1,
            position=(0.0, 0.0, 0.0),
            flag_names=(),
        )

    def morph(
        self,
        *,
        source_index: int,
        local_name: str = "",
        universal_name: str = "",
    ) -> PmxStructuralAuthoringMorphCatalogEntry:
        return PmxStructuralAuthoringMorphCatalogEntry(
            source_index=source_index,
            local_name=local_name,
            universal_name=universal_name,
            panel_name="OTHER",
            morph_type_name="VERTEX",
            offset_count=0,
        )

    def texture(
        self,
        *,
        source_index: int,
        path: str,
    ) -> PmxStructuralAuthoringTextureCatalogEntry:
        return PmxStructuralAuthoringTextureCatalogEntry(
            source_index=source_index,
            path=path,
        )

    def parity_signature(
        self,
        entries: tuple[object, ...],
    ) -> tuple[
        tuple[SmartPartKind, tuple[object, ...]],
        ...,
    ]:
        explanations = explainability.explain_smart_parts(entries)
        detected = detection.detect_smart_parts(entries)

        explanation_signature = tuple(
            (
                item.kind,
                tuple(
                    evidence.evidence
                    for evidence in item.evidence
                ),
            )
            for item in explanations
        )
        detector_signature = tuple(
            (item.kind, item.evidence)
            for item in detected
        )
        self.assertEqual(explanation_signature, detector_signature)
        return explanation_signature

    def test_every_material_alias_has_exact_detector_explanation_parity(self) -> None:
        for index, (alias, expected_kind) in enumerate(
            detection._MATERIAL_ALIAS_INDEX
        ):
            with self.subTest(alias=alias, kind=expected_kind):
                entries = (
                    self.material(
                        source_index=index,
                        local_name=alias,
                    ),
                )
                signature = self.parity_signature(entries)
                self.assertEqual(signature[0][0], expected_kind)
                explanation = explainability.explain_smart_parts(entries)[0]
                self.assertEqual(
                    explanation.evidence[0].normalized_value,
                    alias,
                )
                self.assertEqual(
                    explanation.evidence[0].matched_alias,
                    alias,
                )

    def test_every_bone_alias_has_exact_detector_explanation_parity(self) -> None:
        for index, (alias, expected_kind) in enumerate(
            detection._BONE_ALIAS_INDEX
        ):
            with self.subTest(alias=alias, kind=expected_kind):
                entries = (
                    self.bone(
                        source_index=index,
                        universal_name=alias,
                    ),
                )
                signature = self.parity_signature(entries)
                self.assertEqual(signature[0][0], expected_kind)

    def test_every_morph_alias_has_exact_detector_explanation_parity(self) -> None:
        for index, (alias, expected_kind) in enumerate(
            detection._MORPH_ALIAS_INDEX
        ):
            with self.subTest(alias=alias, kind=expected_kind):
                entries = (
                    self.morph(
                        source_index=index,
                        local_name=alias,
                    ),
                )
                signature = self.parity_signature(entries)
                self.assertEqual(signature[0][0], expected_kind)

    def test_every_texture_alias_has_exact_detector_explanation_parity(self) -> None:
        for index, (alias, expected_kind) in enumerate(
            detection._TEXTURE_ALIAS_INDEX
        ):
            with self.subTest(alias=alias, kind=expected_kind):
                entries = (
                    self.texture(
                        source_index=index,
                        path=f"textures/{alias}.png",
                    ),
                )
                signature = self.parity_signature(entries)
                self.assertEqual(signature[0][0], expected_kind)

    def test_all_generic_aliases_still_match_detector_helper(self) -> None:
        for alias, expected_kind in detection._NORMALIZED_ALIAS_INDEX:
            with self.subTest(alias=alias, kind=expected_kind):
                self.assertIs(
                    detection._exact_alias_kind(alias),
                    expected_kind,
                )

    def test_mixed_entity_families_preserve_exact_evidence_parity(self) -> None:
        entries = (
            self.material(
                source_index=11,
                local_name="顔",
                universal_name="Face",
            ),
            self.bone(
                source_index=12,
                universal_name="Right Arm",
            ),
            self.morph(
                source_index=13,
                local_name="まばたき",
            ),
            self.texture(
                source_index=14,
                path=r"textures\hair.png",
            ),
            PmxStructuralAuthoringVertexCatalogEntry(
                source_index=15,
                position=(0.0, 0.0, 0.0),
                deform_type=0,
            ),
            PmxStructuralAuthoringRigidBodyCatalogEntry(
                source_index=16,
                local_name="Face",
                universal_name="Face",
                bone_index=-1,
                shape_name="SPHERE",
                physics_mode_name="BONE_FOLLOW",
            ),
        )

        signature = self.parity_signature(entries)

        self.assertEqual(
            tuple(kind for kind, _ in signature),
            (
                SmartPartKind.EYES,
                SmartPartKind.HAIR,
                SmartPartKind.FACE,
                SmartPartKind.ARMS,
            ),
        )

    def test_same_source_same_kind_dual_name_evidence_remains_two_records(self) -> None:
        entries = (
            self.material(
                source_index=20,
                local_name="顔",
                universal_name="Face",
            ),
        )

        signature = self.parity_signature(entries)

        self.assertEqual(len(signature), 1)
        self.assertEqual(len(signature[0][1]), 2)
        explanations = explainability.explain_smart_parts(entries)
        self.assertEqual(
            tuple(item.source_field for item in explanations[0].evidence),
            ("local_name", "universal_name"),
        )

    def test_same_source_conflict_is_suppressed_everywhere(self) -> None:
        entries = (
            self.material(
                source_index=21,
                local_name="Face",
                universal_name="Hair",
            ),
            self.bone(
                source_index=22,
                local_name="Right Arm",
                universal_name="Right Hand",
            ),
            self.morph(
                source_index=23,
                local_name="Blink",
                universal_name="Smile",
            ),
        )

        self.assertEqual(detection._match_smart_part_traces(entries), ())
        self.assertEqual(detection.detect_smart_parts(entries), ())
        self.assertEqual(explainability.explain_smart_parts(entries), ())

    def test_unknown_name_does_not_block_known_name_or_fabricate_evidence(self) -> None:
        entries = (
            self.material(
                source_index=24,
                local_name="unknown-material-label",
                universal_name="Face",
            ),
            self.bone(
                source_index=25,
                local_name="Right Arm",
                universal_name="unknown-bone-label",
            ),
            self.morph(
                source_index=26,
                local_name="unknown-morph-label",
                universal_name="Blink",
            ),
        )

        self.parity_signature(entries)
        explanations = explainability.explain_smart_parts(entries)
        source_values = tuple(
            evidence.source_value
            for part in explanations
            for evidence in part.evidence
        )
        self.assertNotIn("unknown-material-label", source_values)
        self.assertNotIn("unknown-bone-label", source_values)
        self.assertNotIn("unknown-morph-label", source_values)

    def test_nfkc_unicode_whitespace_and_case_are_deterministic(self) -> None:
        entries = (
            self.material(
                source_index=30,
                local_name="  Ｆａｃｅ　 ",
            ),
            self.bone(
                source_index=31,
                universal_name=" RIGHT\tARM ",
            ),
            self.morph(
                source_index=32,
                universal_name=" BLINK ",
            ),
            self.texture(
                source_index=33,
                path="textures/  ＨＡＩＲ　.PNG",
            ),
        )

        forward = explainability.explain_smart_parts(entries)
        reverse = explainability.explain_smart_parts(
            tuple(reversed(entries))
        )

        self.assertEqual(forward, reverse)
        self.parity_signature(entries)

        normalized = {
            item.normalized_value
            for part in forward
            for item in part.evidence
        }
        self.assertEqual(
            normalized,
            {"face", "right arm", "blink", "hair"},
        )

    def test_duplicate_canonical_evidence_selects_one_stable_explanation(self) -> None:
        entries = (
            self.material(
                source_index=40,
                local_name="Face",
            ),
            self.material(
                source_index=40,
                local_name="FACE",
            ),
            self.material(
                source_index=40,
                local_name="  Ｆａｃｅ　 ",
            ),
        )

        explanation = explainability.explain_smart_parts(entries)
        detector = detection.detect_smart_parts(entries)

        self.assertEqual(len(explanation), 1)
        self.assertEqual(len(explanation[0].evidence), 1)
        self.assertEqual(len(detector[0].evidence), 1)
        self.assertEqual(
            explanation[0].evidence[0].evidence,
            detector[0].evidence[0],
        )

        expected = explanation
        for permuted in itertools.permutations(entries):
            self.assertEqual(
                explainability.explain_smart_parts(permuted),
                expected,
            )

    def test_texture_parent_directory_never_becomes_semantic_evidence(self) -> None:
        entries = (
            self.texture(
                source_index=50,
                path="face/unknown.png",
            ),
            self.texture(
                source_index=51,
                path=r"hair\unknown.png",
            ),
            self.texture(
                source_index=52,
                path="eyes/not-an-alias.texture.png",
            ),
        )

        self.assertEqual(detection._match_smart_part_traces(entries), ())
        self.assertEqual(detection.detect_smart_parts(entries), ())
        self.assertEqual(explainability.explain_smart_parts(entries), ())

    def test_texture_final_extension_rule_is_preserved(self) -> None:
        entries = (
            self.texture(
                source_index=53,
                path="textures/Face.diffuse.png",
            ),
            self.texture(
                source_index=54,
                path="textures/hair",
            ),
        )

        signature = self.parity_signature(entries)
        self.assertEqual(
            tuple(kind for kind, _ in signature),
            (SmartPartKind.HAIR,),
        )
        explanation = explainability.explain_smart_parts(entries)[0]
        self.assertEqual(
            explanation.evidence[0].derivation,
            (("basename", "hair"), ("basename_stem", "hair")),
        )

    def test_representative_mixed_input_permutations_are_identical(self) -> None:
        entries = (
            self.material(
                source_index=60,
                universal_name="Face",
            ),
            self.bone(
                source_index=61,
                universal_name="Right Arm",
            ),
            self.morph(
                source_index=62,
                universal_name="Blink",
            ),
            self.texture(
                source_index=63,
                path="hair.png",
            ),
        )

        expected_explanation = explainability.explain_smart_parts(entries)
        expected_detection = detection.detect_smart_parts(entries)

        for permuted in itertools.permutations(entries):
            self.assertEqual(
                explainability.explain_smart_parts(permuted),
                expected_explanation,
            )
            self.assertEqual(
                detection.detect_smart_parts(permuted),
                expected_detection,
            )

    def test_repeated_calls_are_value_identical_and_input_immutable(self) -> None:
        entries = (
            self.material(
                source_index=70,
                local_name="顔",
                universal_name="Face",
            ),
            self.texture(
                source_index=71,
                path=r"textures\eye.png",
            ),
        )
        before = repr(entries)

        first = explainability.explain_smart_parts(entries)
        for _ in range(20):
            self.assertEqual(
                explainability.explain_smart_parts(entries),
                first,
            )
            self.assertEqual(
                tuple(
                    (
                        part.kind,
                        tuple(
                            evidence.evidence
                            for evidence in part.evidence
                        ),
                    )
                    for part in first
                ),
                tuple(
                    (part.kind, part.evidence)
                    for part in detection.detect_smart_parts(entries)
                ),
            )

        self.assertEqual(repr(entries), before)

    def test_invalid_boundary_inputs_fail_consistently(self) -> None:
        invalid_containers = (
            [],
            {},
            "Face",
            None,
        )
        for value in invalid_containers:
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(TypeError):
                    detection.detect_smart_parts(value)  # type: ignore[arg-type]
                with self.assertRaises(TypeError):
                    explainability.explain_smart_parts(value)  # type: ignore[arg-type]

        invalid_entries = (
            ("Face",),
            (object(),),
        )
        for value in invalid_entries:
            with self.subTest(value=repr(value)):
                with self.assertRaises(TypeError):
                    detection.detect_smart_parts(value)  # type: ignore[arg-type]
                with self.assertRaises(TypeError):
                    explainability.explain_smart_parts(value)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
