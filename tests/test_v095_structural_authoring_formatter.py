"""v0.9.5 canonical formatter contracts for structural authoring."""

from __future__ import annotations

import inspect
import json
import unittest
from unittest.mock import patch

import mmd_registry.services as services
from mmd_registry.pmx.transaction_plan import (
    parse_pmx_structural_transaction_plan_json,
    render_pmx_structural_transaction_plan_json,
)
from mmd_registry.services import structural_authoring_formatter as formatter


class StructuralAuthoringFormatterTests(unittest.TestCase):
    def test_whitespace_and_member_format_normalize_to_existing_canonical_json(
        self,
    ) -> None:
        source = """
        {
          "operations": [
            {
              "path": "textures/example.png",
              "op": "insert_texture"
            }
          ],
          "schema_version": 1
        }
        """
        normalized = formatter.normalize_structural_authoring_plan_json(source)
        plan = parse_pmx_structural_transaction_plan_json(source)

        self.assertEqual(
            normalized,
            render_pmx_structural_transaction_plan_json(plan),
        )
        self.assertEqual(
            normalized,
            (
                '{"schema_version":1,"operations":'
                '[{"op":"insert_texture","path":"textures/example.png"}]}\n'
            ),
        )

    def test_unicode_is_preserved_without_ascii_escaping(self) -> None:
        source = json.dumps(
            {
                "schema_version": 1,
                "operations": [
                    {
                        "op": "insert_texture",
                        "path": "テクスチャ/目.png",
                    }
                ],
            },
            ensure_ascii=False,
            indent=4,
        )

        normalized = formatter.normalize_structural_authoring_plan_json(source)

        self.assertIn("テクスチャ/目.png", normalized)
        self.assertNotIn(r"\u30c6", normalized)

    def test_normalization_is_idempotent(self) -> None:
        source = (
            '{ "schema_version" : 1, "operations" : [], '
            '"expected_source_sha256" : "'
            + ("a" * 64)
            + '" }'
        )

        first = formatter.normalize_structural_authoring_plan_json(source)
        second = formatter.normalize_structural_authoring_plan_json(first)

        self.assertEqual(first, second)
        self.assertEqual(
            parse_pmx_structural_transaction_plan_json(first),
            parse_pmx_structural_transaction_plan_json(second),
        )

    def test_operation_order_is_preserved(self) -> None:
        source = json.dumps(
            {
                "schema_version": 1,
                "operations": [
                    {"op": "insert_texture", "path": "a.png"},
                    {"op": "insert_texture", "path": "b.png"},
                ],
            }
        )

        normalized = formatter.normalize_structural_authoring_plan_json(source)
        payload = json.loads(normalized)

        self.assertEqual(
            [item["path"] for item in payload["operations"]],
            ["a.png", "b.png"],
        )

    def test_invalid_json_is_plan_invalid_without_value_disclosure(self) -> None:
        secret = "SECRET-FORMATTER-CONTENT"
        source = '{"schema_version":1,"operations":[],"secret":"' + secret

        with self.assertRaises(
            formatter.PmxStructuralAuthoringFormatterServiceError
        ) as raised:
            formatter.normalize_structural_authoring_plan_json(source)

        self.assertEqual(
            raised.exception.to_dict(),
            {
                "code": "structural_authoring_plan_invalid",
                "operation": "normalize_structural_authoring_plan_json",
                "message": "Structural authoring plan JSON is invalid.",
            },
        )
        self.assertNotIn(secret, str(raised.exception.to_dict()))

    def test_duplicate_members_remain_rejected_by_existing_strict_parser(self) -> None:
        source = (
            '{"schema_version":1,"schema_version":1,"operations":[]}'
        )

        with self.assertRaises(
            formatter.PmxStructuralAuthoringFormatterServiceError
        ) as raised:
            formatter.normalize_structural_authoring_plan_json(source)

        self.assertEqual(
            raised.exception.to_dict()["code"],
            "structural_authoring_plan_invalid",
        )

    def test_unknown_fields_remain_rejected(self) -> None:
        source = '{"schema_version":1,"operations":[],"unknown":true}'

        with self.assertRaises(
            formatter.PmxStructuralAuthoringFormatterServiceError
        ) as raised:
            formatter.normalize_structural_authoring_plan_json(source)

        self.assertEqual(
            raised.exception.to_dict()["code"],
            "structural_authoring_plan_invalid",
        )

    def test_non_string_argument_is_invalid_argument(self) -> None:
        with self.assertRaises(
            formatter.PmxStructuralAuthoringFormatterServiceError
        ) as raised:
            formatter.normalize_structural_authoring_plan_json(
                object(),  # type: ignore[arg-type]
            )

        self.assertEqual(
            raised.exception.to_dict(),
            {
                "code": "invalid_argument",
                "operation": "normalize_structural_authoring_plan_json",
                "message": "Invalid structural authoring formatter input.",
            },
        )

    def test_service_is_only_parser_renderer_adapter(self) -> None:
        source = inspect.getsource(formatter)

        self.assertIn("parse_pmx_structural_transaction_plan_json", source)
        self.assertIn("render_pmx_structural_transaction_plan_json", source)

        for forbidden in (
            "transaction_plan_cli",
            "load_document",
            "Path(",
            ".open(",
            "hashlib",
            "preview_structural",
            "apply_structural",
            "structural_transaction import",
            "structural_output",
            "index_remap",
            "write_pmx",
            "json.loads",
            "json.dumps",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

        self.assertNotIn(
            "normalize_structural_authoring_plan_json",
            services.__all__,
        )

    def test_formatter_does_not_mutate_or_reimplement_plan_model(self) -> None:
        source = inspect.getsource(formatter)
        self.assertNotIn("PmxStructuralTransactionPlan(", source)
        self.assertNotIn("schema_version =", source)
        self.assertNotIn("operations =", source)

    def test_process_control_exceptions_escape(self) -> None:
        with patch.object(
            formatter,
            "parse_pmx_structural_transaction_plan_json",
            side_effect=KeyboardInterrupt(),
        ):
            with self.assertRaises(KeyboardInterrupt):
                formatter.normalize_structural_authoring_plan_json(
                    '{"schema_version":1,"operations":[]}'
                )


if __name__ == "__main__":
    unittest.main()
