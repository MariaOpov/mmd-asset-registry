"""Tests for stable structured PMX edit diagnostics."""

from __future__ import annotations

import json
import unittest

from mmd_registry.pmx.editing.errors import PmxEditPlanError
from mmd_registry.pmx.editing.diagnostics import (
    PmxEditDiagnostic,
    PmxEditDiagnosticCode,
    PmxEditPhase,
    build_edit_plan_json_path,
    default_diagnostic_code,
    diagnostic_from_plan_error,
    render_pmx_edit_diagnostic_json,
    render_pmx_edit_diagnostic_text,
)


class PmxEditDiagnosticTests(unittest.TestCase):
    """Validate stable codes, phases, context, and serialization."""

    def test_phase_and_default_code_contract_is_stable(self) -> None:
        expected = {
            PmxEditPhase.PLAN_READ: "edit_plan_read_failed",
            PmxEditPhase.PLAN_DECODE: "edit_plan_decode_failed",
            PmxEditPhase.PLAN_VALIDATE: "edit_plan_invalid",
            PmxEditPhase.SOURCE_READ: "source_read_failed",
            PmxEditPhase.SOURCE_PARSE: "source_invalid",
            PmxEditPhase.PREFLIGHT: "edit_preflight_failed",
            PmxEditPhase.APPLY: "edit_apply_failed",
            PmxEditPhase.DOCUMENT_VALIDATE: "edited_document_invalid",
            PmxEditPhase.SERIALIZE: "edit_serialize_failed",
            PmxEditPhase.REPARSE: "edit_reparse_failed",
            PmxEditPhase.SEMANTIC_VERIFY: "edit_verification_failed",
            PmxEditPhase.OUTPUT_COMMIT: "output_commit_failed",
        }

        self.assertEqual(
            {phase: default_diagnostic_code(phase).value for phase in PmxEditPhase},
            expected,
        )

    def test_diagnostic_serialization_has_deterministic_optional_context(self) -> None:
        diagnostic = PmxEditDiagnostic(
            code=PmxEditDiagnosticCode.PLAN_INVALID,
            phase=PmxEditPhase.PLAN_VALIDATE,
            message="value must be a JSON float.",
            operation_index=2,
            operation_type="update_material",
            path="$.operations[2].diffuse[1]",
            details=(("received_type", "integer"), ("expected_type", "float")),
        )

        self.assertEqual(
            diagnostic.to_dict(),
            {
                "code": "edit_plan_invalid",
                "phase": "plan_validate",
                "message": "value must be a JSON float.",
                "operation_index": 2,
                "operation_type": "update_material",
                "path": "$.operations[2].diffuse[1]",
                "details": {
                    "expected_type": "float",
                    "received_type": "integer",
                },
            },
        )
        self.assertEqual(diagnostic.to_dict(), diagnostic.to_dict())

    def test_unicode_text_and_json_rendering_are_deterministic(self) -> None:
        diagnostic = PmxEditDiagnostic(
            code=PmxEditDiagnosticCode.APPLY_FAILED,
            phase=PmxEditPhase.APPLY,
            message="材質の参照が無効です 🌸",
            operation_index=1,
            operation_type="update_material",
            path="$.operations[1].texture_index",
        )

        first_text = render_pmx_edit_diagnostic_text(diagnostic)
        second_text = render_pmx_edit_diagnostic_text(diagnostic)
        first_json = render_pmx_edit_diagnostic_json(diagnostic)
        second_json = render_pmx_edit_diagnostic_json(diagnostic)

        self.assertEqual(first_text, second_text)
        self.assertEqual(first_json, second_json)
        self.assertIn("材質の参照が無効です 🌸", first_text)
        self.assertIn("材質の参照が無効です 🌸", first_json)
        self.assertNotIn("\\u6750", first_json)
        self.assertEqual(json.loads(first_json), diagnostic.to_dict())

    def test_json_path_builder_preserves_operation_and_component_context(self) -> None:
        self.assertEqual(build_edit_plan_json_path(), "$")
        self.assertEqual(
            build_edit_plan_json_path(field="schema_version"),
            "$.schema_version",
        )
        self.assertEqual(
            build_edit_plan_json_path(operation_index=2),
            "$.operations[2]",
        )
        self.assertEqual(
            build_edit_plan_json_path(
                operation_index=2,
                field="diffuse[1]",
            ),
            "$.operations[2].diffuse[1]",
        )
        self.assertEqual(
            build_edit_plan_json_path(
                operation_index=0,
                field="unknown field 🌸",
            ),
            '$.operations[0]["unknown field 🌸"]',
        )

    def test_plan_error_adapter_uses_stable_fields_without_exception_repr(self) -> None:
        error = PmxEditPlanError(
            "value must be a JSON string.",
            operation_index=3,
            field="memo",
        )
        error.unstable_debug_value = object()  # type: ignore[attr-defined]

        diagnostic = diagnostic_from_plan_error(
            error,
            phase=PmxEditPhase.PLAN_VALIDATE,
            operation_type="update_material",
        )
        rendered = render_pmx_edit_diagnostic_json(diagnostic)

        self.assertEqual(diagnostic.message, error.reason)
        self.assertEqual(diagnostic.operation_index, 3)
        self.assertEqual(diagnostic.path, "$.operations[3].memo")
        self.assertNotIn("unstable_debug_value", rendered)
        self.assertNotIn("object at", rendered)

    def test_plan_error_without_field_context_omits_json_path(self) -> None:
        diagnostic = diagnostic_from_plan_error(
            PmxEditPlanError("invalid JSON at line 1, column 1."),
            phase=PmxEditPhase.PLAN_DECODE,
        )

        self.assertIsNone(diagnostic.path)
        self.assertNotIn("path", diagnostic.to_dict())

    def test_optional_fields_are_omitted_instead_of_serialized_as_noise(self) -> None:
        diagnostic = PmxEditDiagnostic(
            code=PmxEditDiagnosticCode.SOURCE_INVALID,
            phase=PmxEditPhase.SOURCE_PARSE,
            message="PMX header is invalid.",
        )

        self.assertEqual(
            diagnostic.to_dict(),
            {
                "code": "source_invalid",
                "phase": "source_parse",
                "message": "PMX header is invalid.",
            },
        )

    def test_detail_values_reject_arbitrary_objects_and_floats(self) -> None:
        for value in (object(), 1.5):
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(TypeError):
                    PmxEditDiagnostic(
                        code=PmxEditDiagnosticCode.PREFLIGHT_FAILED,
                        phase=PmxEditPhase.PREFLIGHT,
                        message="unsafe detail rejected",
                        details=(("value", value),),  # type: ignore[arg-type]
                    )

    def test_invalid_operation_and_path_context_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            PmxEditDiagnostic(
                code=PmxEditDiagnosticCode.PLAN_INVALID,
                phase=PmxEditPhase.PLAN_VALIDATE,
                message="invalid",
                operation_index=-1,
            )
        with self.assertRaises(ValueError):
            PmxEditDiagnostic(
                code=PmxEditDiagnosticCode.PLAN_INVALID,
                phase=PmxEditPhase.PLAN_VALIDATE,
                message="invalid",
                operation_type="UpdateMaterial",
            )
        with self.assertRaises(ValueError):
            PmxEditDiagnostic(
                code=PmxEditDiagnosticCode.PLAN_INVALID,
                phase=PmxEditPhase.PLAN_VALIDATE,
                message="invalid",
                path="operations[0].memo",
            )


if __name__ == "__main__":
    unittest.main()
