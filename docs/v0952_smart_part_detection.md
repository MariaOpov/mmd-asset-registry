# v0.9.5.2 deterministic Smart Part detection

Version 0.9.5.2 adds the first deterministic semantic detection layer on top of
the immutable Smart Part vocabulary introduced in v0.9.5.1.

## Public entry point

The public detector surface is intentionally narrow:

```python
from mmd_registry.smart_part_detection import detect_smart_parts
```

`mmd_registry.smart_part_detection.__all__` contains only
`detect_smart_parts`. The detector is not promoted through the package root or
the root service namespace.

The function accepts one tuple containing immutable structural-authoring catalog
DTOs and returns a tuple of existing `SmartPart` values. It does not accept a PMX
path, does not parse or write a file, and does not create or execute a
transaction plan.

## Deterministic lexical contract

The detector uses controlled exact aliases only. Semantic text normalization is:

1. Unicode NFKC normalization;
2. Unicode whitespace collapse;
3. Unicode case folding.

Matching is exact after that normalization. There is no token scoring,
substring containment, edit distance, fuzzy matching, statistical model,
language model, or learned classifier.

Material, bone, morph, and texture catalog entries can contribute lexical
evidence. Texture matching uses only the normalized basename stem, never parent
directory names. Vertex and rigid-body entries remain accepted catalog inputs
but have no lexical classification authority in v0.9.5.2.

## Conflict and aggregation rules

For named source entities, recognized local and universal names must agree on
one `SmartPartKind`. If recognized fields point to different kinds, that source
entity contributes zero evidence. An unknown field does not block one unique
recognized kind, and neither local nor universal name has priority.

Evidence from independently classified source entities is additive. Exact
duplicate `SmartPartEvidence` values are removed, one `SmartPart` is emitted per
detected kind, outer parts follow `SmartPartKind` declaration order, and each
part retains the canonical evidence order defined by the v0.9.5.1 immutable
domain model.

These rules make results independent from input ordering, repeated calls,
duplicate input entities, and Python hash randomization.

## Authority boundary

The detector is read-only semantic understanding. It does not:

- mutate a PMX document;
- resolve or guess mutable PMX indices;
- remap references;
- generate, preview, apply, or execute transaction plans;
- call writers or filesystem publication paths;
- expose confidence scoring or ambiguity UI;
- add a CLI command or capability-manifest field.

The released structural transaction, preview, apply, serialization, remap, and
writer authorities remain unchanged. Semantic detection may describe existing
catalog evidence, but it cannot bypass or replace those authorities.

## Validation evidence

The v0.9.5.2 feature branch passed the following local gates before the release
metadata update:

- 2,755 unit tests with 2 optional skips;
- deterministic permutation, repeatability, duplicate-input, and
  `PYTHONHASHSEED` checks;
- 86.85% combined project statement/branch coverage;
- 93.12% combined coverage for `smart_part_detection.py`;
- Ruff 0.16.3 with the repository's current E9/F63/F7/F82 boundary;
- isolated wheel/sdist build, canonical artifact inspection, clean-install
  verification, and installed detector execution.

These are feature-branch validation results. Final release artifact digests and
merged-main release evidence remain separate release gates.
