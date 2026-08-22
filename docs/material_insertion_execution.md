# Material insertion execution — v0.9.2 CP10

## Scope

CP10 enables execution of the CP09 zero-surface material insertion request through
the existing public structural mutation authority:

```python
apply_structural_edit(...)
```

CP10 does not introduce a second public writer. The canonical public material DTO
remains:

```python
from mmd_registry.services.structural_material import (
    PmxStructuralMaterialInsertion,
)
```

The root `mmd_registry.services.__all__` surface remains unchanged.

## Shared execution authority

Material insertion reuses the same private verified structural output pipeline that
already executes legacy structural transforms and CP08 texture insertion:

```text
typed request
    ↓
single captured source snapshot
    ↓
CP09 certified material preview
    ↓
deterministic serialize_pmx(...)
    ↓
reparse serialized bytes
    ↓
independent PmxStructuralInvariantCertificate
    ↓
exact reparsed-document == intended-document comparison
    ↓
source identity / SHA-256 recheck
    ↓
atomic distinct-destination publication
```

The insertion-specific adapters remain private implementation details:

```text
_PmxMaterialInsertionSerializationResult
_verify_pmx_material_insertion_serialization(...)
_write_pmx_material_insertion_transaction(...)
```

They are not exported through `mmd_registry.pmx`, `mmd_registry.services`, or
`mmd_registry.pmx.structural_output.__all__`.

## Zero-surface ownership remains mandatory

Every inserted material continues to materialize with:

```text
surface_index_count = 0
```

The geometry surface-index stream is unchanged. CP10 does not assign triangles,
split material surface ranges, or authorize cross-section material/geometry edits.

The CP09 certificate remains responsible for proving the material insertion intended
document before serialization.

## PMX float32 representation contract

PMX serializes material visual numeric values as IEEE-754 binary32 values.

Python request values are therefore validated for finite float32 representability
before the CP06 reference-shift planner runs. Valid values are materialized as their
exact binary32 round-trip value:

```text
Python float
    ↓
finite validation
    ↓
struct.pack("<f", value)
    ↓
struct.unpack("<f", bytes)
    ↓
exact preview material value
```

This is format canonicalization, not numeric clamping or semantic repair. Values
outside finite PMX float32 range fail closed.

Keeping the certified preview in PMX-representable values allows the existing exact
semantic comparison:

```text
reparsed_document == intended_document
```

to remain unchanged.

## Source-domain references

CP10 does not change CP09 reference rules.

Inserted material texture references continue to use only the existing source
texture domain:

- `texture_index`;
- `sphere_texture_index`;
- `toon_reference_index` when toon mode is `texture`.

Existing morph -> material and soft-body -> material references are shifted exactly
once by the established CP13 and CP14 owner adapters from the CP09 preview kernel.

No material + texture insertion composition is enabled.

## Atomic output policy

CP10 reuses the existing structural transaction and the mature v0.8 safe-output
primitives. It does not copy or replace their implementation.

The transaction preserves:

- input/output distinct-path enforcement;
- no-clobber by default;
- explicit overwrite only for a distinct safe destination;
- source identity and SHA-256 revalidation;
- destination-state recheck immediately before publication;
- temporary-file hash verification;
- atomic publication;
- temporary-residue cleanup after failure;
- no non-atomic fallback.

The source file is never modified in place.

## Execution result

Successful material insertion returns the existing public:

```python
PmxStructuralExecutionResult
```

with:

- `status == "written"`;
- `dry_run == False`;
- `output.written == True`;
- output SHA-256 and size;
- invariant/reference/serialization/semantic verification marked `passed`;
- `verification.input_unchanged == True`.

The CP09 preview evidence remains the basis of the execution report. Raw inserted
material names and memo text are not emitted; insertion audit payloads retain only
their SHA-256 evidence and assigned indices.

## Failure provenance

CP10 retains the frozen structural execution stage vocabulary:

- `service_validation`;
- `path_resolution`;
- `source_snapshot`;
- `source_parse`;
- `intent_resolution`;
- `structural_certification`;
- `serialization`;
- `reparse`;
- `reparse_certification`;
- `semantic_compare`;
- `output_commit`.

Examples:

- invalid anchor, reference, parser bound, or float32 value -> `structural_certification`;
- serialization failure -> `serialization`;
- reparse failure -> `reparse`;
- invalid reparsed document -> `reparse_certification`;
- semantic mismatch -> `semantic_compare`;
- source/destination race -> `output_commit`.

No new public diagnostic operation or code is added.

## Compatibility and capability policy

CP10 must preserve:

- CP09 material preview behavior;
- CP08 texture insertion execution;
- v0.9.1 structural execution;
- the request alias `PmxStructuralEditRequest is PmxStructuralPreviewRequest`;
- the existing `PmxStructuralExecutionResult`;
- the exact root service public surface;
- lazy import of the structural output implementation;
- existing safe-output race/atomicity behavior.

CP10 does not add a `structural_insert` capability field. Capability promotion
remains deferred to CP24.

## Non-goals

CP10 does not authorize:

- non-zero inserted material surface ownership;
- material + texture insertion composition;
- legacy material reorder/delete plus insertion in one request;
- automatic PMX index-width resizing;
- in-place mutation;
- approximate semantic comparison;
- silent repair, clamping, or path rewriting;
- a public raw material writer;
- CLI insertion commands;
- GUI, Smart Tools, plugins, model generation, or physics generation.

## Required regression evidence

Before commit, CP10 must cover:

- append execution;
- `insert_before` execution;
- exact CP13/CP14 incoming material-reference shifts;
- zero-surface preservation;
- source-domain texture references;
- same-anchor and append request ordering;
- PMX float32 preview/execute parity;
- float32 overflow refusal;
- deterministic output bytes;
- execution-report privacy;
- source byte preservation;
- existing-destination no-clobber;
- safe explicit overwrite;
- in-place refusal;
- serialization/reparse/re-certification/semantic mismatch failures;
- source and destination race refusal;
- temporary-residue cleanup;
- private writer boundary;
- no `structural_insert` capability promotion;
- CP08 texture execution regression;
- legacy structural execution regression;
- full repository unit suite, Ruff, and compileall.
