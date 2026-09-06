# v0.9.5.4 Smart Part confidence and ambiguity

Version 0.9.5.4 adds a deterministic, read-only presentation layer for the
exact Smart Part evidence already produced by the released detector and
explainability trace.

The patch does not create a second classifier. Confidence and ambiguity are
derived only from the shared private exact-match trace used by
`detect_smart_parts()` and `explain_smart_parts()`.

## Public surface

The explicit public submodule is `mmd_registry.smart_part_confidence`.

Its `__all__` is exactly:

```text
SmartPartConfidence
SmartPartConfidenceCandidate
SmartPartConfidenceAssessment
assess_smart_parts
```

None of these names is promoted through the package root. The package root
continues to export only `__version__`.

`SmartPartConfidence` has exactly four presentation states:

```text
HIGH
MEDIUM
LOW
AMBIGUOUS
```

These values are not probabilities, scores, edit permissions, or mutation
authority.

## Evidence independence

Source identity is exactly the pair of existing evidence fields:

```text
(source_kind, source_index)
```

Material, bone, and morph are direct named evidence sources. Texture is derived
evidence. Vertex and rigid-body catalog entries have no semantic classification
authority in this release.

Texture evidence never becomes an independent direct source. A material plus
its referenced texture therefore cannot upgrade one direct source into HIGH.

## Resolved confidence

A resolved assessment contains exactly one candidate.

- `HIGH` / `multiple_independent_direct_exact_sources` requires at least two
  distinct direct named source identities supporting the same Smart Part kind.
- `MEDIUM` / `single_direct_exact_source` requires direct exact evidence but
  fewer than two distinct direct identities.
- `LOW` / `derived_texture_only` requires recognized exact texture-basename
  evidence with no direct named support.

Repeated fields, duplicate entries, or multiple recognized textures do not
upgrade evidence independence.

No evidence produces no assessment. It is not represented as LOW.

## Ambiguity

`AMBIGUOUS` / `same_source_exact_conflict` is emitted when one source identity
contains recognized exact fields for incompatible Smart Part kinds and there is
no deterministic winner.

All conflicting candidates remain visible. Unrelated support from other source
entities does not silently resolve the same-source conflict.

Resolved assessments follow `SmartPartKind` declaration order. Ambiguous
assessments follow `SmartPartEvidenceKind` declaration order and source index.
Candidate order follows `SmartPartKind` declaration order. Evidence remains
canonical and duplicate-free.

## Texture-path behavior

Texture semantics continue to use only the final basename stem. Both slash and
backslash separators classify through the same semantic basename rule while raw
path provenance remains preserved for explainability. Parent directory names
never provide semantic authority.

Matching remains normalized exact-alias only: Unicode NFKC, Unicode-whitespace
collapse, and case folding. There is no substring, fuzzy, edit-distance,
statistical, probabilistic, or AI classifier.

## Authority and safety

The confidence layer is read-only. It does not parse or write PMX files, mutate
documents, generate or execute transaction plans, call preview/apply, remap
references, access a writer, publish files, add a CLI command, or alter the
capability manifest.

The released transaction-plan schema and structural execution authorities remain
unchanged.

## PMX joint compatibility repair

During primary private real-model certification, v0.9.5.4 also identified and
repaired an over-strict PMX joint reader check. Bullet 6DOF uses lower > upper
to represent a free axis, lower == upper for a locked axis, and lower < upper
for a limited axis. The reader now preserves all finite limit vectors instead of
rejecting the free-axis ordering. No limit value is swapped or normalized.

This compatibility repair changes parsing acceptance only. It does not add
physics generation, simulation, mutation, or writer authority.

## Certification

Feature-branch certification before version promotion records:

- 3,022 full serial unit tests with 2 optional skips;
- 87.01% combined statement/branch coverage;
- 91.28% coverage for `mmd_registry.smart_part_detection`;
- 72.09% coverage for `mmd_registry.smart_part_explainability`;
- 98.83% coverage for `mmd_registry._smart_part_confidence`;
- 100.00% coverage for `mmd_registry.smart_part_confidence`;
- 91.58% coverage for `mmd_registry.pmx.sections.joints`;
- deterministic primary and secondary private real-model read-only
  certification;
- Ruff 0.16.3 and isolated compilation gates.

Wheel/sdist inspection and clean-installed-package certification are rerun after
version and release-facing documentation promotion. Feature-branch artifact
digests are not final release digests.

The Smart CLI remains deferred to v0.9.5.5.
