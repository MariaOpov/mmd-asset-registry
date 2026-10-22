"""Independent adversarial contract tests for the v0.9.5.11 read-only morph slice.

FROZEN-CP02-R2. Synthetic PMX only; no private models, writes, or apply calls.
QA-owned; tests intentionally RED until the A-owned inspection API exists.
Use only the approved B interpreter after its separate environment approval.
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib
import unittest

from mmd_registry.smart_parts import SmartPartKind
from tests.mmd_fixtures import (
    build_pmx_bone,
    build_pmx_bone_morph_offset,
    build_pmx_material_morph_offset,
    build_pmx_morph,
    build_pmx_structure,
    build_pmx_vertex_morph_offset,
)


# The proposed private service is A-owned. If A exposes this frozen callable
# from a different one of its two owned modules, coordinate that module seam;
# do not add an alternative API or alter a protected service initializer.
_INSPECTION_MODULE = "mmd_registry.services._smart_morph_inspection"


def _record(
    local: str,
    universal: str = "",
    *,
    morph_type: int = 1,
    with_offsets: bool = True,
    panel: int = 4,
    encoding_flag: int = 1,
) -> bytes:
    offsets: tuple[bytes, ...] = ()
    if with_offsets:
        if morph_type == 1:
            offsets = (build_pmx_vertex_morph_offset(),)
        elif morph_type == 2:
            offsets = (build_pmx_bone_morph_offset(),)
        elif morph_type == 8:
            offsets = (build_pmx_material_morph_offset(),)
        else:
            raise ValueError("Synthetic nonempty offset only defined for types 1, 2, 8")
    return build_pmx_morph(
        local_name=local,
        universal_name=universal,
        panel=panel,
        morph_type=morph_type,
        offsets=offsets,
        encoding_flag=encoding_flag,
    )


def _source(*morphs: bytes, encoding_flag: int = 1) -> bytes:
    return build_pmx_structure(
        version=2.1,
        encoding_flag=encoding_flag,
        additional_uv_count=4,
        bones=(build_pmx_bone(encoding_flag=encoding_flag),),
        morphs=morphs,
    )


def _inspect(source_bytes: bytes):
    module = importlib.import_module(_INSPECTION_MODULE)
    return module.inspect_smart_morphs(source_bytes)


def _slots(result):
    slots = tuple(result.capabilities)
    if tuple(slot.capability_kind for slot in slots) != ("smile", "blink"):
        raise AssertionError("Capabilities must be in frozen smile/blink order")
    return {slot.capability_kind: slot for slot in slots}


def _status(capability):
    value = capability.status
    return getattr(value, "value", value)


def _assert_capability(test, slot, status, reason, indices):
    test.assertEqual(_status(slot), status)
    test.assertEqual(slot.reason, reason)
    test.assertEqual(slot.candidate_indices, tuple(indices))


def _trace_details(record):
    """Support frozen nested source evidence or flattened explanation DTOs."""
    identity = getattr(record, "evidence", record)
    source_kind = identity.source_kind
    return (
        getattr(source_kind, "value", source_kind),
        identity.source_index,
        record.source_field,
        record.source_value,
        record.matched_alias,
        record.match_rule,
        getattr(record, "kind", getattr(record, "part_kind", None)),
    )


class SmartMorphAdversarialTests(unittest.TestCase):
    def test_positive_smile_vertex_blink_bone_are_descriptors_only(self):
        raw = _source(_record("Smile"), _record("まばたき", morph_type=2))
        before = raw[:]
        result = _inspect(raw)
        slots = _slots(result)
        _assert_capability(self, slots["smile"], "supported", "exact_morph_evidence", (0,))
        _assert_capability(self, slots["blink"], "supported", "exact_morph_evidence", (1,))
        self.assertIs(slots["smile"].part_kind, SmartPartKind.FACE)
        self.assertIs(slots["blink"].part_kind, SmartPartKind.EYES)
        self.assertEqual(raw, before)
        self.assertEqual(result.source_sha256, hashlib.sha256(raw).hexdigest())
        for forbidden in ("operations", "weights", "edit_plan", "pmx_output", "apply"):
            self.assertFalse(hasattr(result, forbidden), msg=forbidden)

    def test_same_source_local_smile_universal_blink_blocks_both(self):
        result = _inspect(_source(_record("smile", "blink")))
        for name in ("smile", "blink"):
            capability = _slots(result)[name]
            _assert_capability(self, capability, "blocked", "same_source_exact_conflict", (0,))
            traces = tuple(_trace_details(trace) for trace in capability.evidence)
            self.assertEqual({t[2] for t in traces}, {"local_name", "universal_name"})
            self.assertEqual({t[6] for t in traces}, {SmartPartKind.FACE, SmartPartKind.EYES})
            self.assertEqual({t[1] for t in traces}, {0})
            self.assertTrue(all(t[0] == "morph" and t[5] == "exact_alias" for t in traces))

    def test_source_conflict_precedes_other_valid_candidate(self):
        raw = _source(_record("smile", "blink"), _record("smile"))
        slots = _slots(_inspect(raw))
        _assert_capability(self, slots["smile"], "blocked", "same_source_exact_conflict", (0, 1))
        _assert_capability(self, slots["blink"], "blocked", "same_source_exact_conflict", (0,))

    def test_valid_and_out_of_scope_candidates_block_before_eligibility(self):
        raw = _source(_record("smile"), _record("smile", morph_type=8, with_offsets=False))
        _assert_capability(
            self, _slots(_inspect(raw))["smile"],
            "blocked", "multiple_exact_morph_candidates", (0, 1),
        )

    def test_valid_and_zero_offset_candidates_block_before_eligibility(self):
        raw = _source(_record("blink", morph_type=2), _record("blink", morph_type=2, with_offsets=False))
        _assert_capability(
            self, _slots(_inspect(raw))["blink"],
            "blocked", "multiple_exact_morph_candidates", (0, 1),
        )

    def test_two_ineligible_candidates_still_block(self):
        raw = _source(_record("smile", morph_type=8, with_offsets=False),
                      _record("smile", morph_type=3, with_offsets=False))
        _assert_capability(
            self, _slots(_inspect(raw))["smile"],
            "blocked", "multiple_exact_morph_candidates", (0, 1),
        )

    def test_type_out_of_scope_precedes_zero_offsets(self):
        raw = _source(_record("smile", morph_type=8, with_offsets=False))
        _assert_capability(
            self, _slots(_inspect(raw))["smile"],
            "unsupported", "morph_type_out_of_scope", (0,),
        )

    def test_one_zero_offset_eligible_is_unsupported(self):
        raw = _source(_record("blink", morph_type=2, with_offsets=False))
        _assert_capability(
            self, _slots(_inspect(raw))["blink"],
            "unsupported", "empty_morph_offsets", (0,),
        )

    def test_no_morphs_and_generic_names_have_no_exact_slot(self):
        for raw in (
            _source(),
            _source(_record("face"), _record("eyes"), _record("wink")),
            _source(_record("smiling"), _record("blink.001")),
        ):
            with self.subTest(size=len(raw)):
                for capability in _slots(_inspect(raw)).values():
                    _assert_capability(self, capability, "unsupported", "no_exact_morph_evidence", ())
                    self.assertEqual(capability.evidence, ())

    def test_nfkc_casefold_whitespace_and_japanese_exact_aliases(self):
        cases = (
            ("  ＳＭＩＬＥ  ", "smile"),
            ("笑顔", "smile"),
            ("笑い", "smile"),
            ("  ＢＬＩＮＫ ", "blink"),
            ("まばたき", "blink"),
        )
        for alias, expected_slot in cases:
            with self.subTest(slot=expected_slot, alias=alias):
                raw = _source(_record(alias))
                slot = _slots(_inspect(raw))[expected_slot]
                _assert_capability(self, slot, "supported", "exact_morph_evidence", (0,))
                self.assertTrue(any(t[3] == alias for t in map(_trace_details, slot.evidence)))

    def test_same_kind_different_name_fields_are_not_conflict(self):
        raw = _source(_record("smile", "ＳＭＩＬＥ"))
        slot = _slots(_inspect(raw))["smile"]
        _assert_capability(self, slot, "supported", "exact_morph_evidence", (0,))
        details = tuple(_trace_details(trace) for trace in slot.evidence)
        self.assertEqual({t[2] for t in details}, {"local_name", "universal_name"})
        self.assertEqual(len(details), len(set(details)))

    def test_model_source_digest_prevents_cross_model_index_collision(self):
        first = _source(_record("smile"))
        second = _source(_record("笑顔"))
        a, b = _inspect(first), _inspect(second)
        self.assertNotEqual(a.source_sha256, b.source_sha256)
        self.assertEqual(a.source_sha256, hashlib.sha256(first).hexdigest())
        self.assertEqual(b.source_sha256, hashlib.sha256(second).hexdigest())
        self.assertEqual(_slots(a)["smile"].candidate_indices, (0,))
        self.assertEqual(_slots(b)["smile"].candidate_indices, (0,))

    def test_complete_inventory_all_types_and_stable_indices(self):
        raw = _source(*(
            _record("unrelated", morph_type=k, with_offsets=k in (1, 2))
            for k in range(11)
        ))
        result = _inspect(raw)
        self.assertEqual(tuple(item.source_index for item in result.morphs), tuple(range(11)))
        self.assertEqual(tuple(item.morph_type for item in result.morphs), tuple(range(11)))
        self.assertEqual(tuple(item.offset_count for item in result.morphs),
                         tuple(1 if k in (1, 2) else 0 for k in range(11)))
        self.assertEqual(tuple(item.local_name for item in result.morphs), ("unrelated",) * 11)
        self.assertEqual(tuple(item.panel for item in result.morphs), (4,) * 11)

    def test_output_is_repeatable_and_immutable(self):
        raw = _source(_record("smile", "blink"), _record("smile", morph_type=8, with_offsets=False))
        first, second = _inspect(raw), _inspect(raw)
        self.assertEqual(first, second)
        self.assertTrue(dataclasses.is_dataclass(first))
        self.assertTrue(first.__dataclass_params__.frozen)
        self.assertIs(type(first.morphs), tuple)
        self.assertIs(type(first.capabilities), tuple)
        for capability in first.capabilities:
            self.assertEqual(capability.candidate_indices, tuple(sorted(set(capability.candidate_indices))))
            self.assertIs(type(capability.evidence), tuple)

    def test_rejects_wrong_input_type(self):
        for bad in ("PMX", bytearray(b"PMX "), None):
            with self.subTest(type=type(bad).__name__):
                with self.assertRaises(TypeError):
                    _inspect(bad)

    def test_invalid_pmx_fails_closed_without_capability_dto(self):
        for invalid in (b"", b"PMX ", b"bad-not-pmx"):
            with self.subTest(length=len(invalid)):
                with self.assertRaises(Exception) as caught:
                    _inspect(invalid)
                self.assertNotIsInstance(caught.exception, (AssertionError, ImportError))


if __name__ == "__main__":
    unittest.main()
