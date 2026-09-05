# v0.9.5.3 Smart Part detection evidence and explainability

Version 0.9.5.3 adds a deterministic, read-only explanation layer for the
exact-match Smart Part detector released in v0.9.5.2. It explains existing
detector decisions; it does not make new or smarter decisions.

## Public entry point

The public submodule is `mmd_registry.smart_part_explainability`. Its explicit
`__all__` is exactly `SmartPartEvidenceExplanation`, `SmartPartExplanation`, and
`explain_smart_parts`. These names are submodule-only; the package root remains
exactly `mmd_registry.__all__ == ("__version__",)`.

`explain_smart_parts(entries)` accepts the same tuple of immutable structural
authoring catalog DTOs as `detect_smart_parts(entries)` and returns a tuple of
`SmartPartExplanation` values. Empty input returns `()`.

## Shared semantic authority

Detector and explainer consume one shared private deterministic match trace.
The explainer must not independently classify an entry, maintain a second alias
table, or reinterpret detector evidence. The explanation kind/evidence
projection must equal the detector kind/evidence projection exactly.

## Explanation DTOs

`SmartPartEvidenceExplanation` is frozen and slotted with fields, in order:
`evidence`, `source_field`, `source_value`, `comparison_value`,
`normalized_value`, `matched_alias`, `match_rule`, and `derivation`.
`SmartPartExplanation` is frozen and slotted with fields `kind` and `evidence`.

## Named-source provenance

Material, bone, and morph evidence uses `source_field` equal to `local_name` or
`universal_name`. `source_value` and `comparison_value` preserve the original
field value before normalization. `normalized_value` uses detector NFKC,
Unicode whitespace collapse, and case folding. `matched_alias` is the canonical
normalized alias key, `match_rule` is exactly `exact_alias`, and named evidence
uses `derivation == ()`.

Recognized local/universal conflicts on one source keep the v0.9.5.2 rule: that
source contributes zero detector evidence and zero explanation evidence.

## Texture provenance

Texture matching remains basename-stem-only. `source_field` is `path`,
`source_value` is the raw original path, and `comparison_value` is the final
basename stem before normalization. Derivation is exactly the basename and
basename-stem pair. Parent directories are non-semantic and no filesystem read
is required.

## Determinism and parity

Outer ordering follows `SmartPartKind` declaration order and inner ordering uses
canonical `SmartPartEvidence` order. Duplicate evidence is deduplicated exactly
as detector output is deduplicated. Certification covers repeated calls,
reversed input, permutations, duplicate entries, equality/repr stability,
Japanese/English/mixed-name input, and PYTHONHASHSEED 0, 1, and 42. The three
hash-seed runs produce identical semantic and provenance output.

## Read-only authority boundary

Explainability writes no files, mutates no PMX document or caller catalog entry,
generates no transaction plan, invokes no preview/apply authority, remaps no
reference, accesses no writer, publishes no output, adds no CLI command, changes
no schema, changes no capability manifest, and promotes no Smart symbol through
the package root.

## Explicit non-goals

Confidence is not part of v0.9.5.3. Ambiguity presentation remains deferred to
v0.9.5.4. The Smart CLI remains deferred to v0.9.5.5. Fuzzy or AI-assisted
classification, alias/kind expansion, automatic repair, editing, GUI work, and
mutation authority are outside this release.

## Certification snapshot

Before final version promotion, the behavior-frozen source passed 2,820 tests
with 2 optional skips, 86.76% combined coverage, 87.45% detector coverage,
72.09% explainability coverage, Ruff 0.16.3, compileall, isolated wheel/sdist
build, canonical artifact inspection, clean install, and installed
detector/explainer parity/source-byte probes. Final v0.9.5.3 artifact hashes are
recomputed from the final reviewed source tree.
