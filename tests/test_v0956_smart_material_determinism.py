"""v0.9.5.6 Smart material determinism certification."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

import mmd_registry.services._smart_inspection as smart_inspection
from mmd_registry._smart_material_color import normalize_smart_material_color
from mmd_registry.pmx.editing.preview import calculate_pmx_edit_plan_sha256
from mmd_registry.services._smart_material_draft import (
    build_smart_material_color_draft,
    discover_smart_material_capability,
    group_smart_materials,
)
from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringMaterialCatalogEntry,
)
from mmd_registry.smart_parts import SmartPartKind
from tests.test_v0956_smart_material_draft import build_source_bytes


ROOT = Path(__file__).resolve().parents[1]
_HASH_SEEDS = ("0", "1", "2", "42", "31337")


def material(
    source_index: int,
    local_name: str,
) -> PmxStructuralAuthoringMaterialCatalogEntry:
    return PmxStructuralAuthoringMaterialCatalogEntry(
        source_index=source_index,
        local_name=local_name,
        universal_name="",
        texture_index=-1,
        sphere_texture_index=-1,
        surface_index_count=0,
    )


def snapshot(entries) -> dict[str, object]:
    result = smart_inspection._analyze_entries(tuple(entries))
    group = group_smart_materials(result, SmartPartKind.EYES)
    capability = discover_smart_material_capability(result, SmartPartKind.EYES)
    source_bytes = build_source_bytes()
    plan = build_smart_material_color_draft(
        source_bytes,
        SmartPartKind.EYES,
        (0.1, 0.2, 0.3),
    )
    return {
        "group": {
            "indices": list(group.material_indices),
            "evidence": [
                [
                    item.source_kind.value,
                    item.source_index,
                    item.reason,
                ]
                for item in group.evidence
            ],
        },
        "capability": {
            "status": capability.status.value,
            "reason": capability.reason,
            "indices": list(capability.material_indices),
        },
        "color": list(normalize_smart_material_color((0.1, 0.2, 0.3)).rgb),
        "plan": plan.to_dict(),
        "plan_sha256": calculate_pmx_edit_plan_sha256(plan),
    }


class SmartMaterialDeterminismTests(unittest.TestCase):
    def test_repeat_calls_are_equal(self) -> None:
        entries = (material(2, "瞳"), material(1, "Eyes"))
        self.assertEqual(snapshot(entries), snapshot(entries))

    def test_reversed_equivalent_input_has_equal_canonical_projection(self) -> None:
        entries = (material(2, "瞳"), material(1, "Eyes"))
        self.assertEqual(snapshot(entries), snapshot(tuple(reversed(entries))))

    def test_duplicate_equivalent_evidence_has_equal_canonical_projection(self) -> None:
        unique = (material(2, "瞳"), material(1, "Eyes"))
        duplicated = (
            material(2, "瞳"),
            material(1, "Eyes"),
            material(2, "瞳"),
            material(1, "Eyes"),
        )
        self.assertEqual(snapshot(unique), snapshot(duplicated))

    def test_repeated_color_normalization_is_equal(self) -> None:
        first = normalize_smart_material_color((0.1, 0.2, 0.3))
        second = normalize_smart_material_color((0.1, 0.2, 0.3))
        self.assertEqual(first, second)

    def test_repeated_draft_output_and_hash_are_equal(self) -> None:
        source_bytes = build_source_bytes()
        first = build_smart_material_color_draft(
            source_bytes,
            SmartPartKind.EYES,
            "purple",
        )
        second = build_smart_material_color_draft(
            source_bytes,
            SmartPartKind.EYES,
            "purple",
        )
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(
            calculate_pmx_edit_plan_sha256(first),
            calculate_pmx_edit_plan_sha256(second),
        )

    def test_pythonhashseed_matrix_is_byte_identical(self) -> None:
        probe = r"""
import json
import mmd_registry.services._smart_inspection as smart_inspection
from mmd_registry._smart_material_color import normalize_smart_material_color
from mmd_registry.pmx.editing.preview import calculate_pmx_edit_plan_sha256
from mmd_registry.services._smart_material_draft import (
    build_smart_material_color_draft,
    discover_smart_material_capability,
    group_smart_materials,
)
from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringMaterialCatalogEntry,
)
from mmd_registry.smart_parts import SmartPartKind
from tests.test_v0956_smart_material_draft import build_source_bytes

def material(index, name):
    return PmxStructuralAuthoringMaterialCatalogEntry(
        source_index=index,
        local_name=name,
        universal_name="",
        texture_index=-1,
        sphere_texture_index=-1,
        surface_index_count=0,
    )

result = smart_inspection._analyze_entries(
    (material(2, "瞳"), material(1, "Eyes"), material(2, "瞳"))
)
group = group_smart_materials(result, SmartPartKind.EYES)
capability = discover_smart_material_capability(result, SmartPartKind.EYES)
source_bytes = build_source_bytes()
plan = build_smart_material_color_draft(
    source_bytes,
    SmartPartKind.EYES,
    (0.1, 0.2, 0.3),
)
payload = {
    "group": {
        "indices": list(group.material_indices),
        "evidence": [
            [item.source_kind.value, item.source_index, item.reason]
            for item in group.evidence
        ],
    },
    "capability": {
        "status": capability.status.value,
        "reason": capability.reason,
        "indices": list(capability.material_indices),
    },
    "color": list(normalize_smart_material_color((0.1, 0.2, 0.3)).rgb),
    "plan": plan.to_dict(),
    "plan_sha256": calculate_pmx_edit_plan_sha256(plan),
}
print(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
"""
        outputs: list[str] = []
        for seed in _HASH_SEEDS:
            environment = os.environ.copy()
            environment["PYTHONHASHSEED"] = seed
            completed = subprocess.run(
                [sys.executable, "-c", probe],
                cwd=ROOT,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(
                completed.returncode,
                0,
                msg=f"seed={seed}\n{completed.stderr}",
            )
            json.loads(completed.stdout)
            outputs.append(completed.stdout)

        self.assertEqual(len(set(outputs)), 1)


if __name__ == "__main__":
    unittest.main()
