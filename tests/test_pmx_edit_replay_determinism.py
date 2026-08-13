"""Dedicated deterministic edit-plan replay contracts."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from mmd_registry.pmx import load_pmx, serialize_pmx
from mmd_registry.pmx.editing.engine import apply_pmx_edit_plan
from mmd_registry.pmx.editing.json_loader import parse_pmx_edit_plan_json
from mmd_registry.pmx.editing.operations import SetModelInfo
from mmd_registry.pmx.editing.output import write_pmx_edit
from mmd_registry.pmx.editing.plan import PmxEditPlan
from mmd_registry.pmx.editing.preview import (
    calculate_pmx_edit_plan_sha256,
    dry_run_pmx_edit,
)
from tests.test_pmx_edit_engine_preview import (
    build_complete_plan,
    build_source_bytes,
)


class PmxEditReplayDeterminismTests(unittest.TestCase):
    """Freeze same-source + same-plan replay as one explicit v0.8 contract."""

    def setUp(self) -> None:
        self.source_bytes = build_source_bytes()
        self.source_sha256 = hashlib.sha256(self.source_bytes).hexdigest()
        self.document = load_pmx_bytes(self.source_bytes)
        self.plan = build_complete_plan(
            expected_source_sha256=self.source_sha256,
        )

    def test_direct_engine_replay_is_pure_and_identical(self) -> None:
        source_before = serialize_pmx(self.document)
        plan_before = self.plan.to_dict()

        first = apply_pmx_edit_plan(
            self.document,
            self.plan,
            source_sha256=self.source_sha256,
        )
        second = apply_pmx_edit_plan(
            self.document,
            self.plan,
            source_sha256=self.source_sha256,
        )

        self.assertEqual(second.document, first.document)
        self.assertEqual(second.audit, first.audit)
        self.assertEqual(
            serialize_pmx(second.document),
            serialize_pmx(first.document),
        )
        self.assertEqual(serialize_pmx(self.document), source_before)
        self.assertEqual(self.plan.to_dict(), plan_before)

    def test_strict_json_member_order_does_not_change_plan_identity(self) -> None:
        first_text = json.dumps(
            {
                "schema_version": 1,
                "expected_source_sha256": self.source_sha256,
                "operations": [
                    {
                        "op": "set_model_info",
                        "local_name": "Replay モデル 🌏",
                        "universal_comments": "deterministic replay",
                    }
                ],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        second_text = (
            '{"operations":[{'
            '"universal_comments":"deterministic replay",'
            '"local_name":"Replay モデル 🌏",'
            '"op":"set_model_info"}],'
            f'"expected_source_sha256":"{self.source_sha256}",'
            '"schema_version":1}'
        )

        first = parse_pmx_edit_plan_json(first_text)
        second = parse_pmx_edit_plan_json(second_text)

        self.assertEqual(second, first)
        self.assertEqual(second.to_dict(), first.to_dict())
        self.assertEqual(
            calculate_pmx_edit_plan_sha256(second),
            calculate_pmx_edit_plan_sha256(first),
        )

    def test_preview_replay_is_byte_and_report_identical(self) -> None:
        first = dry_run_pmx_edit(self.source_bytes, self.plan)
        second = dry_run_pmx_edit(self.source_bytes, self.plan)

        self.assertEqual(second, first)
        self.assertEqual(second.to_dict(), first.to_dict())
        self.assertEqual(second.document, first.document)
        self.assertEqual(second.audit, first.audit)
        self.assertEqual(second.plan_sha256, first.plan_sha256)
        self.assertEqual(second.source_sha256, first.source_sha256)
        self.assertEqual(
            serialize_pmx(second.document),
            serialize_pmx(first.document),
        )

    def test_write_replay_produces_identical_verified_output(self) -> None:
        expected_preview = dry_run_pmx_edit(self.source_bytes, self.plan)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.pmx"
            first_output = root / "first.pmx"
            second_output = root / "second.pmx"
            source.write_bytes(self.source_bytes)

            first = write_pmx_edit(source, first_output, self.plan)
            second = write_pmx_edit(source, second_output, self.plan)

            self.assertEqual(first.preview, expected_preview)
            self.assertEqual(second.preview, expected_preview)
            self.assertEqual(second.output_sha256, first.output_sha256)
            self.assertEqual(second_output.read_bytes(), first_output.read_bytes())
            self.assertEqual(
                load_pmx(first_output),
                expected_preview.document,
            )
            self.assertEqual(
                load_pmx(second_output),
                expected_preview.document,
            )
            self.assertEqual(source.read_bytes(), self.source_bytes)

    def test_noop_replay_is_identical_and_keeps_original_document(self) -> None:
        plan = PmxEditPlan(
            operations=(
                SetModelInfo(local_name=self.document.model_info.local_name),
            ),
            expected_source_sha256=self.source_sha256,
        )

        first = apply_pmx_edit_plan(
            self.document,
            plan,
            source_sha256=self.source_sha256,
        )
        second = apply_pmx_edit_plan(
            self.document,
            plan,
            source_sha256=self.source_sha256,
        )

        self.assertIs(first.document, self.document)
        self.assertIs(second.document, self.document)
        self.assertEqual(first, second)
        self.assertEqual(first.audit.changed_fields, 0)


def load_pmx_bytes(data: bytes):
    """Load generated PMX bytes without a filesystem dependency."""

    import io

    return load_pmx(io.BytesIO(data))


if __name__ == "__main__":
    unittest.main()
