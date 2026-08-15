"""Tests for stable structured PMX reference diagnostics."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
import unittest

import mmd_registry.pmx as pmx
import mmd_registry.services as services
from mmd_registry.pmx.reference_diagnostics import (
    PmxReferenceDiagnostic,
    PmxReferenceDiagnosticCode,
    diagnose_reference_graph,
)
from mmd_registry.pmx.reference_graph import (
    PmxReferenceGraph,
    PmxReferenceInvalidTarget,
    PmxReferenceTargetCounts,
    PmxReferenceUnsupportedState,
    PmxReferenceUnsupportedStateKind,
)
from mmd_registry.pmx.reference_model import (
    PmxReferenceSourceLocation,
    PmxReferenceSourceSection,
    PmxReferenceTargetKind,
)


EXPECTED_CODES = (
    "invalid_target",
    "active_payload_missing",
    "inactive_payload_present",
    "morph_offset_type_mismatch",
    "version_condition_mismatch",
    "uv_layer_condition_mismatch",
)

EXPECTED_MESSAGES = {
    "invalid_target": "Reference target index is invalid.",
    "active_payload_missing": "Active reference payload is missing.",
    "inactive_payload_present": "Inactive reference payload is present.",
    "morph_offset_type_mismatch":
        "Morph offset type does not match the reference relationship.",
    "version_condition_mismatch":
        "Reference relationship is not supported by the PMX version.",
    "uv_layer_condition_mismatch":
        "UV reference relationship exceeds available additional UV layers.",
}


def _source(
    section: PmxReferenceSourceSection,
    record_index: int,
    suffix: str,
) -> PmxReferenceSourceLocation:
    prefix = f"{section.value}[{record_index}]"
    return PmxReferenceSourceLocation(
        section,
        record_index,
        f"{prefix}.{suffix}" if suffix else prefix,
    )


def _graph(
    *,
    invalid_targets: tuple[PmxReferenceInvalidTarget, ...] = (),
    unsupported_states: tuple[PmxReferenceUnsupportedState, ...] = (),
) -> PmxReferenceGraph:
    return PmxReferenceGraph(
        target_counts=PmxReferenceTargetCounts(
            vertex=2,
            texture=1,
            material=1,
            bone=2,
            morph=1,
            rigid_body=1,
        ),
        edges=(),
        invalid_targets=invalid_targets,
        unsupported_states=unsupported_states,
    )


class PmxReferenceDiagnosticTests(unittest.TestCase):
    """Freeze CP07 diagnostic codes, messages, payloads, and ordering."""

    def test_code_and_message_contract_is_exact(self) -> None:
        self.assertEqual(
            tuple(code.value for code in PmxReferenceDiagnosticCode),
            EXPECTED_CODES,
        )
        for code in PmxReferenceDiagnosticCode:
            with self.subTest(code=code):
                self.assertEqual(EXPECTED_MESSAGES[code.value], {
                    PmxReferenceDiagnosticCode.INVALID_TARGET:
                        "Reference target index is invalid.",
                    PmxReferenceDiagnosticCode.ACTIVE_PAYLOAD_MISSING:
                        "Active reference payload is missing.",
                    PmxReferenceDiagnosticCode.INACTIVE_PAYLOAD_PRESENT:
                        "Inactive reference payload is present.",
                    PmxReferenceDiagnosticCode.MORPH_OFFSET_TYPE_MISMATCH:
                        "Morph offset type does not match the reference relationship.",
                    PmxReferenceDiagnosticCode.VERSION_CONDITION_MISMATCH:
                        "Reference relationship is not supported by the PMX version.",
                    PmxReferenceDiagnosticCode.UV_LAYER_CONDITION_MISMATCH:
                        "UV reference relationship exceeds available additional UV layers.",
                }[code])

    def test_invalid_target_maps_without_normalization(self) -> None:
        evidence = PmxReferenceInvalidTarget(
            "display_frame.bone",
            _source(
                PmxReferenceSourceSection.DISPLAY_FRAMES,
                0,
                "elements[0].target_index",
            ),
            PmxReferenceTargetKind.BONE,
            -1,
            2,
        )

        (diagnostic,) = diagnose_reference_graph(
            _graph(invalid_targets=(evidence,))
        )

        self.assertEqual(
            diagnostic,
            PmxReferenceDiagnostic(
                code=PmxReferenceDiagnosticCode.INVALID_TARGET,
                message=EXPECTED_MESSAGES["invalid_target"],
                relationship_id="display_frame.bone",
                source=evidence.source,
                target_kind=PmxReferenceTargetKind.BONE,
                raw_index=-1,
                target_count=2,
            ),
        )
        self.assertEqual(
            diagnostic.to_dict(),
            {
                "code": "invalid_target",
                "message": "Reference target index is invalid.",
                "relationship_id": "display_frame.bone",
                "source": {
                    "section": "display_frames",
                    "record_index": 0,
                    "path": "display_frames[0].elements[0].target_index",
                },
                "target": {
                    "kind": "bone",
                    "raw_index": -1,
                    "target_count": 2,
                },
            },
        )

    def test_all_unsupported_state_kinds_map_one_to_one(self) -> None:
        cases = (
            (
                PmxReferenceUnsupportedStateKind.ACTIVE_PAYLOAD_MISSING,
                PmxReferenceDiagnosticCode.ACTIVE_PAYLOAD_MISSING,
                "bone.ik_target",
                "ik_flag_enabled;ik=None",
            ),
            (
                PmxReferenceUnsupportedStateKind.INACTIVE_PAYLOAD_PRESENT,
                PmxReferenceDiagnosticCode.INACTIVE_PAYLOAD_PRESENT,
                "bone.tail",
                "tail_index_flag_disabled;tail_bone_index_present",
            ),
            (
                PmxReferenceUnsupportedStateKind.MORPH_OFFSET_TYPE_MISMATCH,
                PmxReferenceDiagnosticCode.MORPH_OFFSET_TYPE_MISMATCH,
                "morph.vertex.vertex",
                "PmxBoneMorphOffset",
            ),
            (
                PmxReferenceUnsupportedStateKind.VERSION_CONDITION_MISMATCH,
                PmxReferenceDiagnosticCode.VERSION_CONDITION_MISMATCH,
                "joint.rigid_body_a",
                "pmx_version=2.0;joint_type=1",
            ),
            (
                PmxReferenceUnsupportedStateKind.UV_LAYER_CONDITION_MISMATCH,
                PmxReferenceDiagnosticCode.UV_LAYER_CONDITION_MISMATCH,
                "morph.uv.vertex",
                "additional_uv_count=0;required_layer=1",
            ),
        )
        states = tuple(
            PmxReferenceUnsupportedState(
                kind,
                relationship_id,
                _source(PmxReferenceSourceSection.BONES, index, "field"),
                observed,
            )
            for index, (kind, _, relationship_id, observed) in enumerate(cases)
        )

        diagnostics = diagnose_reference_graph(
            _graph(unsupported_states=states)
        )

        self.assertEqual(
            tuple(item.code for item in diagnostics),
            tuple(expected_code for _, expected_code, _, _ in cases),
        )
        self.assertEqual(
            tuple(item.relationship_id for item in diagnostics),
            tuple(relationship_id for _, _, relationship_id, _ in cases),
        )
        self.assertEqual(
            tuple(item.observed for item in diagnostics),
            tuple(observed for _, _, _, observed in cases),
        )
        self.assertEqual(
            tuple(item.message for item in diagnostics),
            tuple(EXPECTED_MESSAGES[item.code.value] for item in diagnostics),
        )

    def test_diagnostic_order_is_invalid_then_unsupported_without_deduplication(
        self,
    ) -> None:
        invalid_a = PmxReferenceInvalidTarget(
            "surface.vertex",
            _source(PmxReferenceSourceSection.SURFACE_INDICES, 0, ""),
            PmxReferenceTargetKind.VERTEX,
            9,
            2,
        )
        invalid_b = PmxReferenceInvalidTarget(
            "bone.ik_link",
            _source(PmxReferenceSourceSection.BONES, 1, "ik.links[0].bone_index"),
            PmxReferenceTargetKind.BONE,
            9,
            2,
        )
        state_a = PmxReferenceUnsupportedState(
            PmxReferenceUnsupportedStateKind.ACTIVE_PAYLOAD_MISSING,
            "bone.ik_target",
            _source(PmxReferenceSourceSection.BONES, 0, "ik"),
            "ik_flag_enabled;ik=None",
        )
        state_b = PmxReferenceUnsupportedState(
            PmxReferenceUnsupportedStateKind.ACTIVE_PAYLOAD_MISSING,
            "bone.ik_target",
            _source(PmxReferenceSourceSection.BONES, 0, "ik"),
            "ik_flag_enabled;ik=None",
        )

        diagnostics = diagnose_reference_graph(
            _graph(
                invalid_targets=(invalid_a, invalid_b),
                unsupported_states=(state_a, state_b),
            )
        )

        self.assertEqual(
            tuple(item.relationship_id for item in diagnostics),
            (
                "surface.vertex",
                "bone.ik_link",
                "bone.ik_target",
                "bone.ik_target",
            ),
        )
        self.assertEqual(len(diagnostics), 4)

    def test_empty_graph_produces_no_diagnostics(self) -> None:
        self.assertEqual(diagnose_reference_graph(_graph()), ())

    def test_diagnostic_is_immutable_hashable_and_payload_is_fresh(self) -> None:
        evidence = PmxReferenceInvalidTarget(
            "surface.vertex",
            _source(PmxReferenceSourceSection.SURFACE_INDICES, 0, ""),
            PmxReferenceTargetKind.VERTEX,
            3,
            2,
        )
        diagnostic = diagnose_reference_graph(
            _graph(invalid_targets=(evidence,))
        )[0]

        self.assertEqual(hash(diagnostic), hash(diagnostic))
        with self.assertRaises(FrozenInstanceError):
            diagnostic.message = "changed"  # type: ignore[misc]

        first = diagnostic.to_dict()
        second = diagnostic.to_dict()
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        self.assertIsNot(first["source"], second["source"])

    def test_constructor_rejects_code_message_and_shape_mismatches(self) -> None:
        source = _source(PmxReferenceSourceSection.SURFACE_INDICES, 0, "")

        with self.assertRaises(ValueError):
            PmxReferenceDiagnostic(
                code=PmxReferenceDiagnosticCode.INVALID_TARGET,
                message="Different message.",
                relationship_id="surface.vertex",
                source=source,
                target_kind=PmxReferenceTargetKind.VERTEX,
                raw_index=2,
                target_count=2,
            )

        with self.assertRaises(TypeError):
            PmxReferenceDiagnostic(
                code=PmxReferenceDiagnosticCode.INVALID_TARGET,
                message=EXPECTED_MESSAGES["invalid_target"],
                relationship_id="surface.vertex",
                source=source,
            )

        with self.assertRaises(ValueError):
            PmxReferenceDiagnostic(
                code=PmxReferenceDiagnosticCode.ACTIVE_PAYLOAD_MISSING,
                message=EXPECTED_MESSAGES["active_payload_missing"],
                relationship_id="bone.ik_target",
                source=source,
                target_kind=PmxReferenceTargetKind.BONE,
                observed="ik=None",
            )

    def test_constructor_validation_branches_are_fail_closed(self) -> None:
        source = _source(PmxReferenceSourceSection.SURFACE_INDICES, 0, "")
        valid_invalid_target = {
            "code": PmxReferenceDiagnosticCode.INVALID_TARGET,
            "message": EXPECTED_MESSAGES["invalid_target"],
            "relationship_id": "surface.vertex",
            "source": source,
            "target_kind": PmxReferenceTargetKind.VERTEX,
            "raw_index": 2,
            "target_count": 2,
        }

        cases = (
            (
                TypeError,
                {**valid_invalid_target, "code": "invalid_target"},
            ),
            (
                ValueError,
                {**valid_invalid_target, "message": ""},
            ),
            (
                ValueError,
                {**valid_invalid_target, "relationship_id": ""},
            ),
            (
                TypeError,
                {**valid_invalid_target, "source": object()},
            ),
            (
                TypeError,
                {**valid_invalid_target, "raw_index": True},
            ),
            (
                TypeError,
                {**valid_invalid_target, "target_count": True},
            ),
            (
                ValueError,
                {**valid_invalid_target, "target_count": -1},
            ),
            (
                ValueError,
                {**valid_invalid_target, "observed": "unexpected"},
            ),
        )

        for expected_error, kwargs in cases:
            with self.subTest(expected_error=expected_error, kwargs=kwargs):
                with self.assertRaises(expected_error):
                    PmxReferenceDiagnostic(**kwargs)  # type: ignore[arg-type]

        unsupported_base = {
            "code": PmxReferenceDiagnosticCode.ACTIVE_PAYLOAD_MISSING,
            "message": EXPECTED_MESSAGES["active_payload_missing"],
            "relationship_id": "bone.ik_target",
            "source": source,
            "observed": "ik_flag_enabled;ik=None",
        }
        for kwargs in (
            {**unsupported_base, "raw_index": 1},
            {**unsupported_base, "target_count": 2},
            {**unsupported_base, "observed": ""},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    PmxReferenceDiagnostic(**kwargs)

    def test_unsupported_state_payload_is_json_ready_and_preserves_observed(
        self,
    ) -> None:
        state = PmxReferenceUnsupportedState(
            PmxReferenceUnsupportedStateKind.VERSION_CONDITION_MISMATCH,
            "joint.rigid_body_a",
            _source(
                PmxReferenceSourceSection.JOINTS,
                0,
                "rigid_body_a_index",
            ),
            "pmx_version=2.0;joint_type=1",
        )

        (diagnostic,) = diagnose_reference_graph(
            _graph(unsupported_states=(state,))
        )

        self.assertEqual(
            diagnostic.to_dict(),
            {
                "code": "version_condition_mismatch",
                "message": (
                    "Reference relationship is not supported by the PMX version."
                ),
                "relationship_id": "joint.rigid_body_a",
                "source": {
                    "section": "joints",
                    "record_index": 0,
                    "path": "joints[0].rigid_body_a_index",
                },
                "observed": "pmx_version=2.0;joint_type=1",
            },
        )

    def test_diagnose_rejects_untyped_graph(self) -> None:
        with self.assertRaises(TypeError):
            diagnose_reference_graph(object())  # type: ignore[arg-type]

    def test_cp07_does_not_expand_public_surfaces_or_cross_checkpoint_boundaries(
        self,
    ) -> None:
        self.assertNotIn("diagnose_reference_graph", pmx.__all__)
        self.assertNotIn("PmxReferenceDiagnostic", pmx.__all__)
        self.assertNotIn("diagnose_reference_graph", services.__all__)
        self.assertNotIn("PmxReferenceDiagnostic", services.__all__)

        source = (
            Path(__file__).resolve().parents[1]
            / "mmd_registry"
            / "pmx"
            / "reference_diagnostics.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("PmxDocument", source)
        self.assertNotIn("extract_pmx_reference_graph", source)
        self.assertNotIn("validate_pmx_document", source)
        self.assertNotIn("reference_queries", source)
        self.assertNotIn("PmxServiceDiagnostic", source)
        self.assertNotIn("Path(", source)
        self.assertNotIn(".open(", source)
        self.assertNotIn("remap", source.lower())
        self.assertNotIn("repair", source.lower())


if __name__ == "__main__":
    unittest.main()
