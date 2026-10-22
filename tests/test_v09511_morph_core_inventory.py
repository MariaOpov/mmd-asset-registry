"""v0.9.5.11 synthetic PMX Smart Morph inventory/source-binding tests."""

from __future__ import annotations

import dataclasses
import hashlib
import io
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from mmd_registry.pmx import load_pmx
from mmd_registry.services._smart_morph_inspection import inspect_smart_morphs
from mmd_registry._smart_morph_readonly import SmartMorphCapabilityStatus
from tests.mmd_fixtures import (
    build_pmx_bone,
    build_pmx_bone_morph_offset,
    build_pmx_morph,
    build_pmx_structure,
    build_pmx_vertex_morph_offset,
)


def synthetic_morph(
    name: str,
    *,
    universal: str = "",
    morph_type: int = 1,
    offsets: tuple[bytes, ...] = (),
    panel: int = 4,
) -> bytes:
    return build_pmx_morph(
        local_name=name, universal_name=universal, morph_type=morph_type,
        offsets=offsets, panel=panel,
    )


def synthetic_source(*morphs: bytes, version: float = 2.0) -> bytes:
    return build_pmx_structure(
        version=version,
        additional_uv_count=(4 if version == 2.1 else 0),
        bones=(build_pmx_bone(),),
        morphs=tuple(morphs),
    )


class SmartMorphInventoryTests(unittest.TestCase):
    def test_empty_morph_catalog_yields_two_unsupported_slots(self) -> None:
        result = inspect_smart_morphs(synthetic_source())
        self.assertEqual(result.morphs, ())
        self.assertEqual(tuple(c.capability_kind for c in result.capabilities), ("smile", "blink"))
        self.assertEqual(tuple(c.reason for c in result.capabilities),
                         ("no_exact_morph_evidence", "no_exact_morph_evidence"))

    def test_full_type_0_through_10_inventory_without_eligibility_guess(self) -> None:
        source = synthetic_source(*(
            synthetic_morph(f"synthetic_{kind}", morph_type=kind, panel=(kind % 5))
            for kind in range(11)
        ), version=2.1)
        result = inspect_smart_morphs(source)
        self.assertEqual(len(result.morphs), 11)
        self.assertEqual(tuple(m.source_index for m in result.morphs), tuple(range(11)))
        self.assertEqual(tuple(m.morph_type for m in result.morphs), tuple(range(11)))
        self.assertEqual(tuple(m.panel for m in result.morphs), tuple(kind % 5 for kind in range(11)))
        self.assertEqual(tuple(m.offset_count for m in result.morphs), (0,) * 11)
        self.assertTrue(all(c.status is SmartMorphCapabilityStatus.UNSUPPORTED for c in result.capabilities))

    def test_original_names_preserved_including_unnamed_unicode(self) -> None:
        source = synthetic_source(
            synthetic_morph("", universal=""),
            synthetic_morph("試験 ほほえみ", universal="FULL Unicode"),
        )
        result = inspect_smart_morphs(source)
        self.assertEqual(result.morphs[0].local_name, "")
        self.assertEqual(result.morphs[1].universal_name, "FULL Unicode")
        self.assertEqual(result.morphs[1].local_name, "試験 ほほえみ")

    def test_binary_source_sha256_is_exact_and_model_bound(self) -> None:
        source_one = synthetic_source(synthetic_morph("smile", offsets=(build_pmx_vertex_morph_offset(),)))
        source_two = synthetic_source(synthetic_morph("smile", offsets=(build_pmx_vertex_morph_offset(),)),
                                      synthetic_morph("unknown"))
        result_one = inspect_smart_morphs(source_one)
        result_two = inspect_smart_morphs(source_two)
        self.assertEqual(result_one.source_sha256, hashlib.sha256(source_one).hexdigest())
        self.assertEqual(result_two.source_sha256, hashlib.sha256(source_two).hexdigest())
        self.assertNotEqual(result_one.source_sha256, result_two.source_sha256)
        self.assertEqual(result_one.morphs[0].source_index, result_two.morphs[0].source_index)
        self.assertEqual(result_one.capabilities[0].candidate_indices, (0,))
        self.assertEqual(result_two.capabilities[0].candidate_indices, (0,))

    def test_inventory_is_immutable(self) -> None:
        result = inspect_smart_morphs(synthetic_source(synthetic_morph("test")))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.morphs[0].source_index = 6  # type: ignore[misc]
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.source_sha256 = "wrong"  # type: ignore[misc]

    def test_parser_called_once_through_existing_reader(self) -> None:
        source = synthetic_source(synthetic_morph("smile"))
        with patch("mmd_registry.services._smart_morph_inspection.load_pmx", wraps=load_pmx) as loader:
            inspect_smart_morphs(source)
        loader.assert_called_once()
        args, kwargs = loader.call_args
        self.assertIsInstance(args[0], io.BytesIO)
        self.assertEqual(args[0].getvalue(), source)
        self.assertEqual(kwargs, {})

    def test_morph_catalog_paginates_beyond_1000_without_shortcut(self) -> None:
        from mmd_registry.services import _smart_morph_inspection as inspection
        from mmd_registry.services.structural_authoring_catalog import (
            PmxStructuralAuthoringMorphCatalogEntry,
        )
        synthetic_entries = tuple(
            PmxStructuralAuthoringMorphCatalogEntry(i, "", "", "other", "vertex", 0)
            for i in range(1002)
        )
        calls: list[int] = []
        def fake_page(document, target_kind, *, offset, limit):
            calls.append(offset)
            slice_ = synthetic_entries[offset:offset+limit]
            return SimpleNamespace(entries=slice_, returned_count=len(slice_), total_count=len(synthetic_entries))
        with patch.object(inspection, "inspect_structural_authoring_catalog", side_effect=fake_page):
            result = inspection._collect_morph_catalog(object())
        self.assertEqual(tuple(e.source_index for e in result), tuple(range(1002)))
        self.assertEqual(calls, [0, 1000])

    def test_invalid_pmx_propagates_parser_failure_without_success_dto(self) -> None:
        for payload in (b"", b"NOT PMX", b"PMX "):
            with self.subTest(payload=payload), self.assertRaises(Exception):
                inspect_smart_morphs(payload)

    def test_rejects_non_bytes_without_filesystem_read(self) -> None:
        for value in ("model.pmx", bytearray(b"abc"), None, memoryview(b"abc")):
            with self.subTest(value=type(value).__name__), self.assertRaises(TypeError):
                inspect_smart_morphs(value)  # type: ignore[arg-type]

    def test_repeated_inspection_is_deterministic(self) -> None:
        source = synthetic_source(synthetic_morph("smile", offsets=(build_pmx_vertex_morph_offset(),)))
        self.assertEqual(inspect_smart_morphs(source), inspect_smart_morphs(source))

    def test_bone_type_two_structural_presence(self) -> None:
        source = synthetic_source(synthetic_morph("blink", morph_type=2, offsets=(build_pmx_bone_morph_offset(),)))
        result = inspect_smart_morphs(source)
        self.assertEqual(result.morphs[0].morph_type, 2)
        self.assertEqual(result.morphs[0].offset_count, 1)
        self.assertEqual(result.capabilities[1].reason, "exact_morph_evidence")


if __name__ == "__main__":
    unittest.main()
