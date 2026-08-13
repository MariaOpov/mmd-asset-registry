"""Contracts for structured PMX semantic-validation issues."""

from __future__ import annotations

import io
import unittest
from dataclasses import FrozenInstanceError, replace

from mmd_registry.pmx import (
    PmxValidationError,
    PmxValidationIssue,
    load_pmx,
    validate_pmx_document,
)
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


class PmxValidationIssueTests(unittest.TestCase):
    """Keep structured issues deterministic without changing fail-first validation."""

    def test_issue_is_immutable_and_json_ready(self) -> None:
        issue = PmxValidationIssue(
            section="bones",
            record_index=2,
            field="parent_index",
            reason="index 9 is invalid.",
        )

        self.assertEqual(issue.location, "bones[2]")
        self.assertEqual(
            issue.message,
            (
                "Invalid PMX document in bones[2].parent_index: "
                "index 9 is invalid."
            ),
        )
        self.assertEqual(
            issue.to_dict(),
            {
                "section": "bones",
                "record_index": 2,
                "field": "parent_index",
                "reason": "index 9 is invalid.",
            },
        )
        with self.assertRaises(FrozenInstanceError):
            issue.field = "tail_index"  # type: ignore[misc]

    def test_issue_location_without_record_index_matches_legacy_text(self) -> None:
        issue = PmxValidationIssue(
            section="index_sizes",
            field="bone",
            reason="1-byte index cannot address 129 records.",
        )

        self.assertEqual(issue.location, "index_sizes")
        self.assertEqual(
            issue.message,
            (
                "Invalid PMX document in index_sizes.bone: "
                "1-byte index cannot address 129 records."
            ),
        )

    def test_validation_error_preserves_legacy_contract_and_exposes_issue(
        self,
    ) -> None:
        error = PmxValidationError(
            section="materials",
            record_index=4,
            field="texture_index",
            reason="index 8 is invalid.",
        )

        self.assertEqual(error.section, "materials")
        self.assertEqual(error.record_index, 4)
        self.assertEqual(error.field, "texture_index")
        self.assertEqual(error.reason, "index 8 is invalid.")
        self.assertEqual(
            str(error),
            (
                "Invalid PMX document in materials[4].texture_index: "
                "index 8 is invalid."
            ),
        )
        self.assertEqual(
            error.issue,
            PmxValidationIssue(
                section="materials",
                record_index=4,
                field="texture_index",
                reason="index 8 is invalid.",
            ),
        )

    def test_validator_keeps_first_failure_order_and_structured_context(
        self,
    ) -> None:
        document = load_pmx(io.BytesIO(build_pmx_roundtrip_fixture()))
        invalid_geometry = replace(
            document.geometry,
            surface_indices=(len(document.vertices), 1, 2),
        )
        invalid_body = replace(document.rigid_bodies[0], mass=-1.0)
        invalid_document = replace(
            document,
            geometry=invalid_geometry,
            rigid_bodies=(invalid_body, *document.rigid_bodies[1:]),
        )

        issues = []
        messages = []
        for _ in range(2):
            with self.assertRaises(PmxValidationError) as context:
                validate_pmx_document(invalid_document)
            issues.append(context.exception.issue)
            messages.append(str(context.exception))

        self.assertEqual(issues[0], issues[1])
        self.assertEqual(messages[0], messages[1])
        self.assertEqual(issues[0].section, "surface_indices")
        self.assertEqual(issues[0].record_index, 0)
        self.assertEqual(issues[0].field, "vertex_index")
        self.assertIn("index 5 is invalid", issues[0].reason)

    def test_validator_type_error_contract_is_unchanged(self) -> None:
        with self.assertRaisesRegex(
            TypeError,
            r"document must be a PmxDocument instance\.",
        ):
            validate_pmx_document(object())  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
