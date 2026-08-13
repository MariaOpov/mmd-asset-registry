"""Deterministic full-document adversarial PMX corpus contracts."""

from __future__ import annotations

import hashlib
import io
import unittest
from dataclasses import dataclass

from mmd_registry.binary_reader import BinaryParseError
from mmd_registry.pmx import load_pmx
from mmd_registry.pmx.sections.joints import MAX_PMX_JOINT_COUNT
from mmd_registry.pmx.sections.textures import MAX_PMX_TEXTURE_COUNT
from tests.mmd_fixtures import build_pmx_structure


@dataclass(frozen=True, slots=True)
class MalformedPmxCase:
    """One synthetic malformed PMX byte stream and its expected failure site."""

    name: str
    data: bytes
    section: str
    record_index: int | None
    reason_fragment: str


def _minimal_structure(
    *,
    version: float = 2.0,
    **overrides: object,
) -> bytes:
    """Build the smallest complete PMX structure with selected hostile overrides."""

    return build_pmx_structure(
        version=version,
        deform_types=(),
        surface_indices=(),
        materials=(),
        **overrides,
    )


def build_adversarial_pmx_corpus() -> tuple[MalformedPmxCase, ...]:
    """Return deterministic synthetic malformed full-document PMX cases."""

    clean20 = _minimal_structure()
    clean21 = _minimal_structure(version=2.1)

    return (
        MalformedPmxCase(
            name="truncated_signature",
            data=clean20[:2],
            section="signature",
            record_index=None,
            reason_fragment="requested 4 bytes, but only 2 bytes remain",
        ),
        MalformedPmxCase(
            name="negative_vertex_count",
            data=_minimal_structure(vertex_count_override=-1),
            section="vertices",
            record_index=None,
            reason_fragment="count cannot be negative: -1",
        ),
        MalformedPmxCase(
            name="vertex_count_payload_contradiction",
            data=_minimal_structure(vertex_count_override=1),
            section="vertices",
            record_index=None,
            reason_fragment="requires at least",
        ),
        MalformedPmxCase(
            name="invalid_vertex_deform_discriminator",
            data=build_pmx_structure(
                version=2.0,
                deform_types=(5,),
                surface_indices=(),
                materials=(),
            ),
            section="vertices",
            record_index=0,
            reason_fragment="invalid PMX vertex deform type: 5",
        ),
        MalformedPmxCase(
            name="oversized_texture_count",
            data=_minimal_structure(
                texture_count_override=MAX_PMX_TEXTURE_COUNT + 1,
            ),
            section="textures",
            record_index=None,
            reason_fragment="exceeds the safety limit",
        ),
        MalformedPmxCase(
            name="negative_morph_count",
            data=_minimal_structure(morph_count_override=-1),
            section="morphs",
            record_index=None,
            reason_fragment="count cannot be negative: -1",
        ),
        MalformedPmxCase(
            name="oversized_joint_count",
            data=_minimal_structure(
                joint_count_override=MAX_PMX_JOINT_COUNT + 1,
            ),
            section="joints",
            record_index=None,
            reason_fragment="exceeds the safety limit",
        ),
        MalformedPmxCase(
            name="truncated_soft_body_count",
            data=clean21[:-1],
            section="soft_bodies",
            record_index=None,
            reason_fragment="requested 4 bytes, but only 3 bytes remain",
        ),
    )


def _error_fingerprint(error: BinaryParseError) -> tuple[object, ...]:
    """Return the complete stable parse-error identity used by this checkpoint."""

    return (
        error.format_name,
        error.section,
        error.record_index,
        error.offset,
        error.operation,
        error.reason,
        str(error),
    )


class PmxAdversarialCorpusTests(unittest.TestCase):
    """Require malformed full-document loads to fail closed and deterministically."""

    def assert_deterministic_failure(self, case: MalformedPmxCase) -> None:
        fingerprints: list[tuple[object, ...]] = []

        for _ in range(3):
            with self.assertRaises(BinaryParseError) as context:
                load_pmx(io.BytesIO(case.data))

            error = context.exception
            self.assertEqual(error.format_name, "PMX")
            self.assertEqual(error.section, case.section)
            self.assertEqual(error.record_index, case.record_index)
            self.assertIsInstance(error.offset, int)
            self.assertGreaterEqual(error.offset, 0)
            self.assertTrue(error.operation)
            self.assertIn(case.reason_fragment, error.reason)
            self.assertIn(case.reason_fragment, str(error))
            fingerprints.append(_error_fingerprint(error))

        self.assertEqual(fingerprints[0], fingerprints[1])
        self.assertEqual(fingerprints[1], fingerprints[2])

    def case_named(self, name: str) -> MalformedPmxCase:
        for case in build_adversarial_pmx_corpus():
            if case.name == name:
                return case
        self.fail(f"missing adversarial corpus case: {name}")

    def test_corpus_generation_is_deterministic_and_payloads_are_distinct(
        self,
    ) -> None:
        first = build_adversarial_pmx_corpus()
        second = build_adversarial_pmx_corpus()

        self.assertEqual(first, second)
        self.assertEqual(len(first), 8)

        names = [case.name for case in first]
        self.assertEqual(len(names), len(set(names)))

        payload_hashes = [
            hashlib.sha256(case.data).hexdigest()
            for case in first
        ]
        self.assertEqual(len(payload_hashes), len(set(payload_hashes)))
        self.assertTrue(all(case.data for case in first))

    def test_truncated_signature_fails_deterministically(self) -> None:
        self.assert_deterministic_failure(
            self.case_named("truncated_signature")
        )

    def test_negative_vertex_count_fails_deterministically(self) -> None:
        self.assert_deterministic_failure(
            self.case_named("negative_vertex_count")
        )

    def test_vertex_count_payload_contradiction_fails_deterministically(
        self,
    ) -> None:
        self.assert_deterministic_failure(
            self.case_named("vertex_count_payload_contradiction")
        )

    def test_invalid_vertex_deform_discriminator_fails_deterministically(
        self,
    ) -> None:
        self.assert_deterministic_failure(
            self.case_named("invalid_vertex_deform_discriminator")
        )

    def test_oversized_texture_count_fails_deterministically(self) -> None:
        self.assert_deterministic_failure(
            self.case_named("oversized_texture_count")
        )

    def test_negative_morph_count_fails_deterministically(self) -> None:
        self.assert_deterministic_failure(
            self.case_named("negative_morph_count")
        )

    def test_oversized_joint_count_fails_deterministically(self) -> None:
        self.assert_deterministic_failure(
            self.case_named("oversized_joint_count")
        )

    def test_truncated_soft_body_count_fails_deterministically(self) -> None:
        self.assert_deterministic_failure(
            self.case_named("truncated_soft_body_count")
        )


if __name__ == "__main__":
    unittest.main()
