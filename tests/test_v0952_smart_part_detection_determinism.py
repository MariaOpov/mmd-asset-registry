from __future__ import annotations

import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

import mmd_registry.smart_part_detection as detection
from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringBoneCatalogEntry,
    PmxStructuralAuthoringMaterialCatalogEntry,
    PmxStructuralAuthoringMorphCatalogEntry,
    PmxStructuralAuthoringTextureCatalogEntry,
)
from mmd_registry.smart_parts import SmartPartKind


class SmartPartDetectionDeterminismTests(unittest.TestCase):
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
            panel_name="",
            morph_type_name="VERTEX",
            offset_count=0,
        )

    def fixture_entries(self) -> tuple[object, ...]:
        return (
            self.material(
                source_index=8,
                local_name="  Ｆａｃｅ  ",
                universal_name="Face",
            ),
            PmxStructuralAuthoringTextureCatalogEntry(
                source_index=1,
                path=r"textures\Face.png",
            ),
            self.morph(
                source_index=4,
                local_name="まばたき",
                universal_name="Blink",
            ),
            self.bone(
                source_index=3,
                local_name="右腕",
                universal_name="Right Arm",
            ),
            self.material(
                source_index=20,
                local_name="Face",
                universal_name="Hair",
            ),
        )

    def semantic_snapshot(self, entries: tuple[object, ...]) -> tuple[object, ...]:
        parts = detection.detect_smart_parts(entries)  # type: ignore[arg-type]
        return tuple(
            (
                part.kind.value,
                tuple(
                    (
                        evidence.source_kind.value,
                        evidence.source_index,
                        evidence.reason,
                    )
                    for evidence in part.evidence
                ),
            )
            for part in parts
        )

    def test_every_permutation_produces_identical_semantic_snapshot(self) -> None:
        entries = self.fixture_entries()
        expected = self.semantic_snapshot(entries)
        for permutation in itertools.permutations(entries):
            with self.subTest(
                order=tuple(getattr(item, "source_index") for item in permutation)
            ):
                self.assertEqual(
                    self.semantic_snapshot(tuple(permutation)),
                    expected,
                )

    def test_repeated_calls_are_equal_hash_equal_and_repr_equal(self) -> None:
        entries = self.fixture_entries()
        first = detection.detect_smart_parts(entries)  # type: ignore[arg-type]
        first_hashes = tuple(hash(part) for part in first)
        first_repr = repr(first)
        for _ in range(100):
            current = detection.detect_smart_parts(entries)  # type: ignore[arg-type]
            self.assertEqual(current, first)
            self.assertEqual(tuple(hash(part) for part in current), first_hashes)
            self.assertEqual(repr(current), first_repr)

    def test_duplicate_input_entities_do_not_change_semantic_result(self) -> None:
        entries = self.fixture_entries()
        base = detection.detect_smart_parts(entries)  # type: ignore[arg-type]
        duplicated = detection.detect_smart_parts(
            entries + entries + (entries[0], entries[1])  # type: ignore[arg-type]
        )
        self.assertEqual(duplicated, base)

    def test_output_part_order_is_smart_part_declaration_order(self) -> None:
        result = detection.detect_smart_parts(self.fixture_entries())  # type: ignore[arg-type]
        actual = tuple(part.kind for part in result)
        rank = {kind: index for index, kind in enumerate(SmartPartKind)}
        self.assertEqual(
            actual,
            tuple(sorted(actual, key=rank.__getitem__)),
        )

    def test_evidence_order_is_canonical_for_every_part(self) -> None:
        result = detection.detect_smart_parts(self.fixture_entries())  # type: ignore[arg-type]
        for part in result:
            with self.subTest(kind=part.kind):
                expected = tuple(
                    sorted(
                        part.evidence,
                        key=lambda item: (
                            item.source_kind.value,
                            item.source_index,
                            item.reason,
                        ),
                    )
                )
                self.assertEqual(part.evidence, expected)

    def test_alias_indexes_are_sorted_and_repeatable(self) -> None:
        for name in (
            "_NORMALIZED_ALIAS_INDEX",
            "_MATERIAL_ALIAS_INDEX",
            "_BONE_ALIAS_INDEX",
            "_MORPH_ALIAS_INDEX",
            "_TEXTURE_ALIAS_INDEX",
        ):
            with self.subTest(index=name):
                index = getattr(detection, name)
                self.assertIs(type(index), tuple)
                self.assertEqual(
                    index,
                    tuple(sorted(index, key=lambda item: item[0])),
                )
                self.assertEqual(index, getattr(detection, name))

    def test_windows_and_forward_slash_texture_paths_are_semantically_equal(self) -> None:
        windows = PmxStructuralAuthoringTextureCatalogEntry(
            source_index=7,
            path=r"textures\Face.png",
        )
        forward = PmxStructuralAuthoringTextureCatalogEntry(
            source_index=7,
            path="textures/Face.png",
        )
        self.assertEqual(
            detection.detect_smart_parts((windows,)),
            detection.detect_smart_parts((forward,)),
        )

    def test_unknown_and_conflicted_entities_do_not_change_valid_result_order(self) -> None:
        valid = (
            self.morph(source_index=2, universal_name="Blink"),
            self.material(source_index=3, local_name="Face"),
            self.bone(source_index=4, universal_name="Right Arm"),
        )
        noise = (
            self.material(source_index=5, local_name="Unknown"),
            self.material(
                source_index=6,
                local_name="Face",
                universal_name="Hair",
            ),
        )
        expected = detection.detect_smart_parts(valid)
        for permutation in itertools.permutations(valid + noise):
            self.assertEqual(
                detection.detect_smart_parts(tuple(permutation)),
                expected,
            )

    def test_hash_seed_does_not_change_serialized_semantic_snapshot(self) -> None:
        script = r"""
import json
import mmd_registry.smart_part_detection as d
from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringMaterialCatalogEntry as M,
    PmxStructuralAuthoringTextureCatalogEntry as T,
    PmxStructuralAuthoringMorphCatalogEntry as O,
    PmxStructuralAuthoringBoneCatalogEntry as B,
)

entries = (
    M(8, "  Ｆａｃｅ  ", "Face", -1, -1, 0),
    T(1, r"textures\Face.png"),
    O(4, "まばたき", "Blink", "", "VERTEX", 0),
    B(3, "右腕", "Right Arm", -1, (0.0, 0.0, 0.0), ()),
    M(20, "Face", "Hair", -1, -1, 0),
)
parts = d.detect_smart_parts(entries)
snapshot = [
    [
        part.kind.value,
        [
            [
                evidence.source_kind.value,
                evidence.source_index,
                evidence.reason,
            ]
            for evidence in part.evidence
        ],
    ]
    for part in parts
]
print(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")))
"""
        outputs: list[str] = []
        repo_root = Path(__file__).resolve().parents[1]
        for seed in ("0", "1", "2", "7", "42", "123456"):
            env = {
                **os.environ,
                "PYTHONHASHSEED": seed,
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=repo_root,
                env=env,
                text=True,
                encoding="utf-8",
                errors="strict",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            with self.subTest(seed=seed, stderr=result.stderr):
                self.assertEqual(result.returncode, 0)
                outputs.append(result.stdout.strip())

        self.assertTrue(outputs)
        self.assertEqual(len(set(outputs)), 1)
        decoded = json.loads(outputs[0])
        self.assertEqual(
            [item[0] for item in decoded],
            ["eyes", "face", "arms"],
        )

    def test_source_inputs_remain_unchanged_across_permutations(self) -> None:
        entries = self.fixture_entries()
        before = tuple(repr(item) for item in entries)
        for permutation in itertools.permutations(entries):
            detection.detect_smart_parts(tuple(permutation))  # type: ignore[arg-type]
        self.assertEqual(tuple(repr(item) for item in entries), before)


if __name__ == "__main__":
    unittest.main()
