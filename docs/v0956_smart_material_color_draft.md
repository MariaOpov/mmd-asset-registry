# v0.9.5.6 Smart Material Color Draft

Version 0.9.5.6 adds a deterministic private authoring bridge from resolved
Smart Part semantics to the existing safe material edit-plan authority. It does
not create a second detector, writer, remapper, preview engine, apply engine, or
transaction schema.

## Semantic material grouping

A target group is derived only from exact `MATERIAL` evidence carried by the
requested resolved Smart Part. Identity is the exact material `source_index`.
Duplicate equivalent evidence collapses to one identity and output is sorted by
ascending source index.

Texture, bone, morph, vertex, and rigid-body evidence never becomes a material
target by adjacency, naming proximity, confidence, or guesswork.

## Capability

The only v0.9.5.6 capability is `material_color`.

It is supported only when the requested semantic part has exact MATERIAL
evidence and the confidence authority does not report that requested part as
ambiguous. Stable reasons are:

- `exact_material_evidence`
- `no_exact_material_evidence`
- `ambiguous_semantic_selection`

Confidence is not permission. HIGH, MEDIUM, or LOW presentation state never
overrides the exact-evidence and ambiguity rules.

## Color contract

Preset names are exact lowercase values:

- `blue` -> `(0.0, 0.0, 1.0)`
- `red` -> `(1.0, 0.0, 0.0)`
- `green` -> `(0.0, 1.0, 0.0)`
- `purple` -> `(0.5, 0.0, 0.5)`

Custom RGB is exactly a three-item tuple of Python floats. Every component must
be finite and within `[0.0, 1.0]`. Integers, booleans, strings, lists,
wrong-length tuples, NaN, infinity, and out-of-range values are rejected.

The implementation reuses the existing PMX float32 canonicalization contract.
There is no 0-255 inference, clamping, gamma conversion, or preset case folding.

## Draft composition

Drafting consumes exact source bytes, parses them through the existing PMX
reader, validates the exact catalog/material identity, and returns the existing
`PmxEditPlan` schema-one representation containing one `UpdateMaterial` per
target material in ascending source-index order.

Each operation updates diffuse RGB only and preserves source alpha exactly.
The plan binds `expected_source_sha256` to the exact source bytes. A requested
RGB that already equals source RGB still produces the deterministic reviewed
operation.

The draft service performs no apply, no source write, no direct writer call, no
remapper call, no publication, and no structural transaction-plan widening.

## Fail-closed behavior

Automatic draft composition is blocked when:

- requested semantics are ambiguous;
- no exact material evidence exists;
- material evidence is out of range;
- catalog identity conflicts with the parsed document;
- duplicate catalog identity conflicts;
- source-bound evidence does not match the document.

The private error reasons remain bounded to the frozen contract:
`ambiguous_semantic_selection`, `unsupported_material_color`, and
`source_evidence_mismatch`.

## Determinism

Grouping, capability results, color normalization, operation ordering, plan
serialization, and plan hash are certified across repeated calls,
reversed-equivalent inputs, duplicate-equivalent evidence, and
`PYTHONHASHSEED=0,1,2,42,31337`.

## Public and execution boundaries

`mmd_registry/_smart_material_color.py` and
`mmd_registry/services/_smart_material_draft.py` are private implementation
modules. They are not promoted through `mmd_registry.__all__` or
`mmd_registry.services.__all__`.

The package root remains exactly `('__version__',)`. The Smart CLI remains
inspect-only. Existing detector, explainability, confidence, schema-one edit
plan, preview/apply, writer, remapper, and atomic publication authorities remain
the sole owners of their released behavior.
