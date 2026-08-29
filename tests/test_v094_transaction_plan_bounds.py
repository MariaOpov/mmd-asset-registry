"""Tests for CP14 transaction-plan identity and resource-bound hardening."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
from types import MappingProxyType
import unittest
from unittest.mock import patch

from mmd_registry.pmx.sections.bones import (
    MAX_PMX_BONE_COUNT,
    MAX_PMX_IK_LINK_COUNT,
)
from mmd_registry.pmx.sections.geometry import MAX_PMX_VERTEX_COUNT
from mmd_registry.pmx.sections.header import MAX_PMX_COMMENT_BYTES
from mmd_registry.pmx.sections.materials import MAX_PMX_MATERIAL_COUNT
from mmd_registry.pmx.sections.morphs import (
    MAX_PMX_MORPH_COUNT,
    MAX_PMX_MORPH_OFFSET_COUNT,
)
from mmd_registry.pmx.sections.rigid_bodies import MAX_PMX_RIGID_BODY_COUNT
from mmd_registry.pmx.sections.textures import (
    MAX_PMX_TEXTURE_COUNT,
    MAX_PMX_TEXTURE_PATH_BYTES,
)
import mmd_registry.pmx.transaction_plan as transaction_plan
from mmd_registry.pmx.transaction_plan import (
    PmxStructuralTransactionPlan,
    PmxStructuralTransactionPlanDecodeError,
    PmxStructuralTransactionPlanError,
    load_pmx_structural_transaction_plan,
    parse_pmx_structural_transaction_plan_json,
)


CP13_PUBLIC_EXPORTS = (
    "PMX_STRUCTURAL_TRANSACTION_PLAN_SCHEMA_VERSION",
    "PmxStructuralTransactionOperationType",
    "PmxStructuralTransactionOperationCatalogEntry",
    "PmxStructuralTransactionOperationCatalog",
    "get_pmx_structural_transaction_operation_catalog",
    "PmxStructuralTransactionPlanError",
    "PmxStructuralTransactionPlanDecodeError",
    "parse_pmx_structural_transaction_plan_json",
    "load_pmx_structural_transaction_plan",
    "render_pmx_structural_transaction_plan_json",
    "PmxStructuralTransactionPlan",
    "get_pmx_structural_transaction_plan_template",
    "PmxStructuralTransactionOperationExplanation",
    "PmxStructuralTransactionPlanExplanation",
    "explain_pmx_structural_transaction_plan",
)


def _dump(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class _Sha256Subclass(str):
    pass


class V094TransactionPlanBoundsTests(unittest.TestCase):
    def test_cp14_preserves_exact_cp13_public_namespace(self) -> None:
        self.assertEqual(transaction_plan.__all__, CP13_PUBLIC_EXPORTS)

    def test_resource_limits_align_with_existing_pmx_scanner_safety_ceilings(self) -> None:
        self.assertEqual(
            transaction_plan._MAX_TRANSACTION_PLAN_OPERATION_COUNT,
            MAX_PMX_VERTEX_COUNT,
        )
        self.assertEqual(
            transaction_plan._MAX_TRANSACTION_PLAN_IK_LINK_COUNT,
            MAX_PMX_IK_LINK_COUNT,
        )
        self.assertEqual(
            transaction_plan._MAX_TRANSACTION_PLAN_MORPH_OFFSET_COUNT,
            MAX_PMX_MORPH_OFFSET_COUNT,
        )
        self.assertEqual(
            transaction_plan._MAX_TRANSACTION_PLAN_TEXTURE_PATH_UTF8_BYTES,
            MAX_PMX_TEXTURE_PATH_BYTES,
        )
        self.assertEqual(
            transaction_plan._MAX_TRANSACTION_PLAN_STRING_UTF8_BYTES,
            MAX_PMX_COMMENT_BYTES,
        )
        self.assertEqual(
            dict(transaction_plan._COLLECTION_SOURCE_INDEX_LIMIT_BY_TARGET),
            {
                "vertex": MAX_PMX_VERTEX_COUNT,
                "texture": MAX_PMX_TEXTURE_COUNT,
                "material": MAX_PMX_MATERIAL_COUNT,
                "bone": MAX_PMX_BONE_COUNT,
                "morph": MAX_PMX_MORPH_COUNT,
                "rigid_body": MAX_PMX_RIGID_BODY_COUNT,
            },
        )
        self.assertIsInstance(
            transaction_plan._COLLECTION_SOURCE_INDEX_LIMIT_BY_TARGET,
            MappingProxyType,
        )
        self.assertEqual(transaction_plan._MAX_TRANSACTION_PLAN_JSON_DEPTH, 16)
        self.assertEqual(
            transaction_plan._MAX_TRANSACTION_PLAN_JSON_BYTES,
            256 * 1024 * 1024,
        )

    def test_json_text_byte_limit_is_exact_and_utf8_based(self) -> None:
        raw = _dump({"schema_version": 1, "operations": []})
        encoded_size = len(raw.encode("utf-8"))
        with patch.object(
            transaction_plan,
            "_MAX_TRANSACTION_PLAN_JSON_BYTES",
            encoded_size,
        ):
            self.assertEqual(
                parse_pmx_structural_transaction_plan_json(raw).operations,
                (),
            )

        with patch.object(
            transaction_plan,
            "_MAX_TRANSACTION_PLAN_JSON_BYTES",
            encoded_size - 1,
        ):
            with self.assertRaisesRegex(
                PmxStructuralTransactionPlanDecodeError,
                "JSON text exceeds the safety limit",
            ):
                parse_pmx_structural_transaction_plan_json(raw)

    def test_file_loader_reads_at_most_limit_plus_one_before_rejecting(self) -> None:
        raw = _dump({"schema_version": 1, "operations": []}).encode("utf-8")
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "plan.json"
            path.write_bytes(raw)
            with patch.object(
                transaction_plan,
                "_MAX_TRANSACTION_PLAN_JSON_BYTES",
                len(raw) - 1,
            ):
                with self.assertRaisesRegex(
                    PmxStructuralTransactionPlanDecodeError,
                    "transaction-plan file exceeds the safety limit",
                ):
                    load_pmx_structural_transaction_plan(path)

    def test_pathological_json_nesting_has_deterministic_decode_error(self) -> None:
        raw = '{"schema_version":1,"operations":[],"extra":[[[[]]]]}'
        with patch.object(transaction_plan, "_MAX_TRANSACTION_PLAN_JSON_DEPTH", 3):
            messages = []
            for _ in range(2):
                with self.assertRaises(PmxStructuralTransactionPlanDecodeError) as cm:
                    parse_pmx_structural_transaction_plan_json(raw)
                messages.append(str(cm.exception))
            self.assertEqual(messages[0], messages[1])
            self.assertIn("JSON nesting exceeds the safety limit of 3", messages[0])

    def test_operations_array_is_bounded_before_operation_materialization(self) -> None:
        payload = {
            "schema_version": 1,
            "operations": [
                {"op": "insert_texture", "path": "a.png"},
                {"op": "insert_texture", "path": "b.png"},
                {"op": "insert_texture", "path": "c.png"},
            ],
        }
        with patch.object(transaction_plan, "_MAX_TRANSACTION_PLAN_OPERATION_COUNT", 2):
            with self.assertRaisesRegex(
                PmxStructuralTransactionPlanError,
                r"operations: array exceeds the safety limit of 2 items",
            ):
                parse_pmx_structural_transaction_plan_json(_dump(payload))

    def test_collection_reorder_uses_target_specific_existing_safety_bound(self) -> None:
        limits = dict(transaction_plan._COLLECTION_SOURCE_INDEX_LIMIT_BY_TARGET)
        limits["texture"] = 2
        payload = {
            "schema_version": 1,
            "operations": [
                {
                    "op": "transform_collection",
                    "target_kind": "texture",
                    "old_indices_in_new_order": [0, 1, 2],
                }
            ],
        }
        with patch.object(
            transaction_plan,
            "_COLLECTION_SOURCE_INDEX_LIMIT_BY_TARGET",
            MappingProxyType(limits),
        ):
            with self.assertRaisesRegex(
                PmxStructuralTransactionPlanError,
                r"old_indices_in_new_order: array exceeds the safety limit of 2 items",
            ):
                parse_pmx_structural_transaction_plan_json(_dump(payload))

    def test_ik_link_array_is_bounded(self) -> None:
        payload = {
            "schema_version": 1,
            "operations": [
                {
                    "op": "insert_bone",
                    "local_name": "B",
                    "ik": {
                        "target_bone_index": 0,
                        "links": [
                            {"bone_index": 0},
                            {"bone_index": 1},
                            {"bone_index": 2},
                        ],
                    },
                }
            ],
        }
        with patch.object(transaction_plan, "_MAX_TRANSACTION_PLAN_IK_LINK_COUNT", 2):
            with self.assertRaisesRegex(
                PmxStructuralTransactionPlanError,
                r"ik\.links: array exceeds the safety limit of 2 items",
            ):
                parse_pmx_structural_transaction_plan_json(_dump(payload))

    def test_morph_offset_array_is_bounded(self) -> None:
        payload = {
            "schema_version": 1,
            "operations": [
                {
                    "op": "insert_morph",
                    "local_name": "M",
                    "morph_type": "group",
                    "offsets": [
                        {"type": "group", "morph_index": 0, "weight": 0.5},
                        {"type": "group", "morph_index": 1, "weight": 0.5},
                        {"type": "group", "morph_index": 2, "weight": 0.5},
                    ],
                }
            ],
        }
        with patch.object(
            transaction_plan,
            "_MAX_TRANSACTION_PLAN_MORPH_OFFSET_COUNT",
            2,
        ):
            with self.assertRaisesRegex(
                PmxStructuralTransactionPlanError,
                r"offsets: array exceeds the safety limit of 2 items",
            ):
                parse_pmx_structural_transaction_plan_json(_dump(payload))

    def test_generic_strings_and_texture_paths_are_utf8_byte_bounded(self) -> None:
        oversized_name = "x" * (
            transaction_plan._MAX_TRANSACTION_PLAN_STRING_UTF8_BYTES + 1
        )
        with self.assertRaisesRegex(
            PmxStructuralTransactionPlanError,
            "UTF-8 value exceeds the safety limit",
        ):
            parse_pmx_structural_transaction_plan_json(
                _dump(
                    {
                        "schema_version": 1,
                        "operations": [
                            {"op": "insert_bone", "local_name": oversized_name}
                        ],
                    }
                )
            )

        path = "é" * (
            transaction_plan._MAX_TRANSACTION_PLAN_TEXTURE_PATH_UTF8_BYTES // 2 + 1
        )
        self.assertLess(
            len(path),
            transaction_plan._MAX_TRANSACTION_PLAN_TEXTURE_PATH_UTF8_BYTES,
        )
        with self.assertRaisesRegex(
            PmxStructuralTransactionPlanError,
            "UTF-8 value exceeds the safety limit",
        ):
            parse_pmx_structural_transaction_plan_json(
                _dump(
                    {
                        "schema_version": 1,
                        "operations": [{"op": "insert_texture", "path": path}],
                    }
                )
            )

    def test_all_authored_captured_source_indices_fit_signed_int32(self) -> None:
        too_large = 1 << 31
        payloads = (
            {
                "schema_version": 1,
                "operations": [
                    {
                        "op": "insert_texture",
                        "path": "a.png",
                        "position": "insert_before",
                        "source_index": too_large,
                    }
                ],
            },
            {
                "schema_version": 1,
                "operations": [
                    {
                        "op": "insert_bone",
                        "local_name": "B",
                        "parent_bone_index": too_large,
                    }
                ],
            },
            {
                "schema_version": 1,
                "operations": [
                    {
                        "op": "insert_rigid_body",
                        "local_name": "R",
                        "bone_index": too_large,
                    }
                ],
            },
            {
                "schema_version": 1,
                "operations": [
                    {
                        "op": "insert_morph",
                        "local_name": "M",
                        "morph_type": "group",
                        "offsets": [
                            {
                                "type": "group",
                                "morph_index": too_large,
                                "weight": 0.5,
                            }
                        ],
                    }
                ],
            },
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(
                    PmxStructuralTransactionPlanError,
                    "signed 32-bit integer",
                ):
                    parse_pmx_structural_transaction_plan_json(_dump(payload))

    def test_int32_max_is_only_representability_bound_not_source_membership_check(self) -> None:
        plan = parse_pmx_structural_transaction_plan_json(
            _dump(
                {
                    "schema_version": 1,
                    "operations": [
                        {
                            "op": "insert_texture",
                            "path": "a.png",
                            "position": "insert_before",
                            "source_index": (1 << 31) - 1,
                        }
                    ],
                }
            )
        )
        self.assertEqual(plan.operations[0].source_index, (1 << 31) - 1)

    def test_expected_source_sha256_requires_exact_builtin_string_in_typed_plan(self) -> None:
        digest = "a" * 64
        self.assertEqual(
            PmxStructuralTransactionPlan(
                operations=(),
                expected_source_sha256=digest,
            ).expected_source_sha256,
            digest,
        )
        with self.assertRaisesRegex(TypeError, "exact string"):
            PmxStructuralTransactionPlan(
                operations=(),
                expected_source_sha256=_Sha256Subclass(digest),
            )

    def test_expected_source_identity_is_declared_only_and_never_opens_source_pmx(self) -> None:
        source = Path(transaction_plan.__file__).read_text(encoding="utf-8")
        self.assertNotIn("hash_file_sha256", source)
        self.assertNotIn("preview_structural_transaction", source)
        self.assertNotIn("apply_structural_transaction", source)
        self.assertNotIn("load_pmx(", source)
        self.assertNotIn("read_pmx", source)


if __name__ == "__main__":
    unittest.main()
