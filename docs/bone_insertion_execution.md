# Bone insertion execution — v0.9.2 CP12

## Scope

CP12 enables execution of the CP11 bounded semantic PMX bone insertion request
through the existing public structural mutation authority:

```python
apply_structural_edit(...)
```

CP12 does not add another public writer, another request vocabulary, or another
filesystem transaction. The canonical public DTOs remain in
`mmd_registry.services.structural_bone`, and the request alias remains:

```python
PmxStructuralEditRequest is PmxStructuralPreviewRequest
```

## Shared verified execution authority

Bone insertion reuses the same private structural-output transaction already
used by legacy v0.9.1 structural execution, CP08 texture insertion, and CP10
material insertion:

```text
typed bone request
    ↓
one captured source snapshot
    ↓
existing CP11 bone payload builder
    ↓
preview_pmx_bone_insertions(...)
    ↓
certified intended PmxDocument
    ↓
deterministic serialize_pmx(...)
    ↓
load_pmx(...) reparse
    ↓
fresh PmxStructuralInvariantCertificate
    ↓
exact reparsed_document == intended_document
    ↓
source identity / SHA-256 recheck
    ↓
destination-state recheck
    ↓
atomic distinct-destination publication
```

The CP12 insertion-specific helpers are private implementation details:

```text
_PmxBoneInsertionSerializationResult
_verify_pmx_bone_insertion_serialization(...)
_write_pmx_bone_insertion_transaction(...)
```

They are not exported through `mmd_registry.pmx`,
`mmd_registry.services`, or `mmd_registry.pmx.structural_output.__all__`.

## Preview remains authoritative

CP12 does not reimplement bone insertion semantics. It calls the existing CP11
preview kernel against the single parsed source snapshot. Therefore execution
inherits the already-certified CP11 rules for:

- source-domain insertion anchors;
- stable same-anchor and append ordering;
- source-domain outgoing parent/tail/inherit/IK references;
- refusal of new-bone -> new-bone references;
- vertex deform -> bone shifts;
- existing bone parent/tail/inherit/IK shifts;
- bone morph -> bone shifts;
- display-frame -> bone shifts;
- rigid-body -> bone shifts;
- optional `-1` preservation;
- reader count limits;
- current bone-index-width capacity;
- strict source text encoding;
- semantic PMX flag/payload pairing.

Mixed texture/material/bone insertion and legacy reorder/delete plus bone
insertion remain refused by the shared request contract.

## Exact PMX float32 semantics

CP11 canonicalizes every bone/IK numeric field serialized as PMX binary32
before the intended document is certified:

- bone position;
- offset tail;
- inherit weight;
- fixed axis;
- local X/Z axes;
- IK angle limit;
- IK link lower/upper vectors.

CP12 does not weaken that contract. It keeps exact semantic verification:

```python
reparsed_document == intended_document
```

No epsilon comparison, clamping, vector normalization, or silent repair is
authorized.

## Reader/writer contract

The existing deterministic PMX writer is authoritative for `PmxBone`,
`PmxIk`, and `PmxIkLink`. The existing bone reader reconstructs the same
flag-controlled payload shape. CP12 adds no bone-specific binary writer or
parser.

Supported execution therefore remains bounded by the existing PMX 2.0/2.1,
UTF-8/UTF-16LE, parser-count, and index-width compatibility rules.

## Atomic output policy

CP12 reuses the mature safe-output primitives through the existing shared
structural transaction. The transaction preserves:

- input/output distinct-path enforcement;
- symlink/hardlink alias refusal;
- no-clobber by default;
- explicit overwrite only for a distinct safe destination;
- captured source filesystem identity;
- captured source SHA-256;
- immediate pre-publication source identity/SHA revalidation;
- destination-state recheck immediately before publication;
- temporary-file `flush` + `fsync`;
- temporary payload SHA-256 verification;
- atomic publication;
- temporary-residue cleanup on failure;
- no non-atomic fallback.

Source files are never mutated in place by CP12.

## Execution result and privacy

Successful bone insertion returns the existing public:

```python
PmxStructuralExecutionResult
```

with:

- `status == "written"`;
- `dry_run == False`;
- `output.written == True`;
- output SHA-256 and byte size;
- invariant/reference/serialization/semantic verification marked `passed`;
- `verification.input_unchanged == True`.

The CP11 preview evidence remains the basis of the execution audit. Raw bone
names, vectors, IK values, and other insertion payload text remain absent from
JSON-ready audit output; payload evidence remains SHA-256 bounded.

## Failure provenance

CP12 reuses the frozen structural execution stage vocabulary:

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

Typical mapping:

- invalid anchor/reference/count/index-width/float32 -> `structural_certification`;
- serialization failure -> `serialization`;
- reparse failure -> `reparse`;
- invalid reparsed document -> `reparse_certification`;
- exact semantic mismatch -> `semantic_compare`;
- source/destination race -> `output_commit`.

CP12 adds no diagnostic operation or diagnostic code.

## Compatibility and capability policy

CP12 preserves:

- CP11 bone preview behavior;
- CP10 material insertion execution;
- CP08 texture insertion execution;
- v0.9.1 legacy structural execution;
- the existing public request alias;
- the existing `PmxStructuralExecutionResult`;
- the exact root `mmd_registry.services.__all__` surface;
- lazy import of structural-output mutation internals;
- the existing safe-output transaction semantics.

Capability promotion remains deferred:

```text
structural_preview = True
structural_write   = True
structural_insert  = absent
```

## Non-goals

CP12 does not authorize:

- new-bone -> new-bone references;
- raw PMX flag words or raw section records as public inputs;
- mixed texture/material/bone insertion;
- legacy bone reorder/delete plus insertion in one request;
- automatic bone-index-width expansion;
- approximate semantic comparison;
- silent repair, clamping, or vector normalization;
- in-place mutation;
- a public raw bone writer;
- CLI insertion commands;
- GUI/Smart Tools/plugin/model-generation/physics-generation behavior;
- capability promotion.

## Required regression evidence

Before commit, CP12 must cover:

- append execution;
- `insert_before` execution;
- full semantic flag-controlled bone/IK payload execution;
- source-domain outgoing reference mapping;
- CP11 incoming reference-owner shift parity;
- same-anchor and append order;
- PMX float32 exact preview/execute parity;
- PMX 2.0 and PMX 2.1;
- UTF-8 and UTF-16LE;
- supported bone index widths 1/2/4;
- index-width expansion refusal;
- opaque trailing-data refusal;
- deterministic output bytes;
- privacy-bounded execution reports;
- source byte preservation;
- default no-clobber;
- explicit safe overwrite;
- in-place refusal;
- serialization/reparse/re-certification/semantic mismatch failures;
- source and destination race refusal;
- temporary-residue cleanup;
- private writer boundary;
- no `structural_insert` capability promotion;
- CP08 texture execution regression;
- CP10 material execution regression;
- v0.9.1 structural execution regression;
- CP11 preview regression;
- full repository unit suite, Ruff, and compileall.
