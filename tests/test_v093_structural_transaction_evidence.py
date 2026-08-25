"""Freeze CP17 deterministic structural transaction plan evidence."""

from __future__ import annotations

import builtins
from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import mmd_registry.services as services
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.writer import serialize_pmx
from mmd_registry.services.structural_material import (
    PmxStructuralMaterialInsertion,
)
from mmd_registry.services.structural_reference import (
    PmxStructuralNewReference,
)
from mmd_registry.services.structural_texture import (
    PmxStructuralTextureInsertion,
)
from mmd_registry.services.structural_transaction import (
    PmxStructuralTransactionRequest,
    preview_structural_transaction,
)
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


PLAN_SCHEMA = "mmd_registry.structural_transaction.plan.v1"


def _clean_document(*, index_size: int = 1):
    return replace(
        load_pmx(
            io.BytesIO(
                build_pmx_roundtrip_fixture(
                    version=2.1,
                    index_size=index_size,
                )
            )
        ),
        trailing_data=b"",
    )


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


class V093StructuralTransactionEvidenceTests(unittest.TestCase):
    def test_noop_plan_schema_digest_and_source_binding_are_exact(self) -> None:
        document = _clean_document()
        result = preview_structural_transaction(
            document,
            PmxStructuralTransactionRequest(),
        )
        report = result.to_dict()
        plan = report["plan"]

        self.assertEqual(
            tuple(plan),
            (
                "schema",
                "source",
                "operations",
                "collections",
                "identities",
                "references",
                "dependencies",
                "counts",
                "preflight",
                "sha256",
            ),
        )
        self.assertEqual(plan["schema"], PLAN_SCHEMA)
        self.assertEqual(plan["sha256"], result.plan_sha256)
        self.assertRegex(result.plan_sha256, r"\A[0-9a-f]{64}\Z")
        self.assertEqual(
            result.plan_sha256,
            "9640b9df4b009c6f5e6688cdf7ea6385a56446abcdd6964e6783b7387441d77b",
        )

        digest_input = dict(plan)
        digest = digest_input.pop("sha256")
        self.assertEqual(
            digest,
            hashlib.sha256(_canonical_json_bytes(digest_input)).hexdigest(),
        )
        self.assertEqual(
            plan["source"],
            {
                "semantic_sha256": hashlib.sha256(
                    serialize_pmx(document)
                ).hexdigest(),
                "pmx_version": 2.1,
                "declared_index_widths": {
                    "vertex": 1,
                    "texture": 1,
                    "material": 1,
                    "bone": 1,
                    "morph": 1,
                    "rigid_body": 1,
                },
                "captured_counts": report["counts"]["captured"],
            },
        )
        self.assertEqual(
            plan["operations"],
            {"original_count": 0, "normalized": []},
        )
        self.assertEqual(plan["collections"], [])
        self.assertEqual(plan["identities"], [])
        self.assertEqual(
            plan["references"],
            {"resolved_local": [], "remapped_existing": []},
        )
        self.assertEqual(
            plan["dependencies"],
            {"nodes": [], "edges": [], "materialization_order": []},
        )
        self.assertEqual(plan["counts"]["final"], report["counts"]["final"])
        self.assertEqual(plan["preflight"]["status"], "passed")
        self.assertTrue(plan["preflight"]["all_representable"])
        self.assertEqual(len(plan["preflight"]["targets"]), 6)

    def test_equivalent_typed_sources_share_digest_and_semantic_change_does_not(
        self,
    ) -> None:
        document = _clean_document()
        equivalent = load_pmx(io.BytesIO(serialize_pmx(document)))
        request = PmxStructuralTransactionRequest()

        first = preview_structural_transaction(document, request)
        second = preview_structural_transaction(equivalent, request)

        self.assertIsNot(document, equivalent)
        self.assertEqual(document, equivalent)
        self.assertEqual(first.plan_sha256, second.plan_sha256)
        self.assertEqual(first.to_dict(), second.to_dict())

        changed_source = replace(
            document,
            model_info=replace(
                document.model_info,
                local_name="semantic source change",
            ),
        )
        changed = preview_structural_transaction(changed_source, request)
        self.assertNotEqual(first.plan_sha256, changed.plan_sha256)
        self.assertEqual(
            first.to_dict()["plan"]["source"]["captured_counts"],
            changed.to_dict()["plan"]["source"]["captured_counts"],
        )

    def test_internal_plan_refuses_mismatched_captured_source_environment(
        self,
    ) -> None:
        result = preview_structural_transaction(
            _clean_document(),
            PmxStructuralTransactionRequest(),
        )
        internal = result._preview
        counts = list(internal.composition.source_counts)
        target_kind, count = counts[0]
        counts[0] = (target_kind, count + 1)
        mismatched_composition = replace(
            internal.composition,
            source_counts=tuple(counts),
        )

        with self.assertRaisesRegex(
            ValueError,
            "source counts must match the captured document",
        ):
            replace(internal, composition=mismatched_composition)

        widths = list(internal.composition.index_widths)
        width_target, _ = widths[0]
        widths[0] = (width_target, 2)
        mismatched_widths = replace(
            internal.composition,
            index_widths=tuple(widths),
        )
        with self.assertRaisesRegex(
            ValueError,
            "index widths must match the captured document",
        ):
            replace(internal, composition=mismatched_widths)

    def test_plan_digest_is_process_hash_seed_independent(self) -> None:
        script = """
import json
from mmd_registry.services.structural_transaction import (
    PmxStructuralTransactionRequest,
    preview_structural_transaction,
)
from tests.test_v093_structural_transaction_evidence import _clean_document

result = preview_structural_transaction(
    _clean_document(),
    PmxStructuralTransactionRequest(),
)
print(json.dumps(result.to_dict()["plan"], sort_keys=True, separators=(",", ":")))
"""
        outputs = []
        repository_root = Path(__file__).resolve().parents[1]
        for seed in ("1", "2", "random"):
            environment = os.environ.copy()
            environment["PYTHONHASHSEED"] = seed
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            outputs.append(
                subprocess.check_output(
                    (sys.executable, "-c", script),
                    cwd=repository_root,
                    env=environment,
                    text=True,
                    encoding="utf-8",
                )
            )
        self.assertEqual(outputs, [outputs[0]] * len(outputs))

    def test_payload_is_hashed_not_exposed_and_changes_plan_digest(self) -> None:
        document = _clean_document()
        private_marker = "textures/非公開/private-model-secret.png"
        first_request = PmxStructuralTransactionRequest(
            (
                PmxStructuralTextureInsertion(
                    private_marker,
                    new_id="private.texture",
                ),
            )
        )
        second_request = PmxStructuralTransactionRequest(
            (
                PmxStructuralTextureInsertion(
                    "textures/public-replacement.png",
                    new_id="private.texture",
                ),
            )
        )

        with patch.object(
            builtins,
            "open",
            side_effect=AssertionError("preview must not access files"),
        ):
            first = preview_structural_transaction(document, first_request)
            second = preview_structural_transaction(document, second_request)

        first_report = first.to_dict()
        rendered = json.dumps(first_report, ensure_ascii=False, sort_keys=True)
        self.assertNotIn(private_marker, rendered)
        self.assertNotIn("private-model-secret", rendered)
        operation = first_report["plan"]["operations"]["normalized"][0]
        self.assertEqual(
            tuple(operation),
            (
                "request_ordinal",
                "category",
                "target_kind",
                "position",
                "source_index",
                "new_id",
                "payload_sha256",
            ),
        )
        self.assertEqual(operation["request_ordinal"], 0)
        self.assertEqual(operation["target_kind"], "texture")
        self.assertRegex(operation["payload_sha256"], r"\A[0-9a-f]{64}\Z")
        self.assertNotEqual(first.plan_sha256, second.plan_sha256)

    def test_remaps_identity_references_and_dependency_order_are_canonical(
        self,
    ) -> None:
        document = _clean_document()
        request = PmxStructuralTransactionRequest(
            (
                PmxStructuralMaterialInsertion(
                    local_name="transaction material",
                    texture_index=PmxStructuralNewReference(
                        "texture",
                        "texture.new",
                    ),
                ),
                PmxStructuralTextureInsertion(
                    "textures/transaction.png",
                    position="insert_before",
                    source_index=0,
                    new_id="texture.new",
                ),
                services.PmxStructuralCollectionEdit(
                    services.PmxReferenceTargetKind.TEXTURE,
                    (2, 0, 1),
                ),
            )
        )

        result = preview_structural_transaction(document, request)
        plan = result.to_dict()["plan"]

        self.assertEqual(
            tuple(
                item["request_ordinal"]
                for item in plan["operations"]["normalized"]
            ),
            (2, 1, 0),
        )
        self.assertEqual(
            tuple(item["target_kind"] for item in plan["collections"]),
            ("texture", "material"),
        )
        texture = plan["collections"][0]
        self.assertEqual(texture["survivor_old_indices"], [2, 0, 1])
        self.assertEqual(texture["combined_remap"], [2, 3, 0])
        self.assertEqual(texture["new_only_positions"], [1])
        self.assertEqual(
            texture["insertions"],
            [
                {
                    "request_ordinal": 1,
                    "position": "insert_before",
                    "source_index": 0,
                    "final_index": 1,
                    "new_id": "texture.new",
                }
            ],
        )
        self.assertEqual(
            plan["identities"],
            [
                {
                    "target_kind": "texture",
                    "new_id": "texture.new",
                    "request_ordinal": 1,
                    "final_index": 1,
                }
            ],
        )
        self.assertEqual(
            plan["references"]["resolved_local"],
            [
                {
                    "request_ordinal": 0,
                    "field": "material.texture_index",
                    "relationship_id": "material.texture",
                    "target_kind": "texture",
                    "new_id": "texture.new",
                    "final_index": 1,
                }
            ],
        )
        self.assertEqual(
            plan["dependencies"],
            {
                "nodes": ["texture", "material"],
                "edges": [{"provider": "texture", "consumer": "material"}],
                "materialization_order": ["texture", "material"],
            },
        )


if __name__ == "__main__":
    unittest.main()
