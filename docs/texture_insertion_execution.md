# Texture Insertion Execution — v0.9.2 CP08

## Purpose

CP08 enables filesystem execution for the texture insertion request introduced by
CP07 while preserving the single public structural mutation authority:

- `mmd_registry.services.apply_structural_edit(...)`

CP08 does **not** create a public texture writer, a second mutation service, or a
new `PmxCollectionTransform` insertion mode.

The execution contract is:

```text
public typed request
    -> capture one source snapshot
    -> build the existing CP07 texture insertion preview
    -> certify the intended immutable document
    -> serialize deterministically
    -> reparse serialized bytes
    -> independently re-certify the reparsed document
    -> require exact semantic equality with the intended document
    -> reverify source identity and SHA-256
    -> reverify destination safety
    -> atomically publish verified bytes
```

Any failure before the final publication leaves no successful output result.

## Public request surface

The request shape remains the CP07 additive request:

```python
from mmd_registry.services import PmxStructuralEditRequest
from mmd_registry.services.structural_texture import (
    PmxStructuralTextureInsertion,
)

request = PmxStructuralEditRequest(
    texture_insertions=(
        PmxStructuralTextureInsertion("textures/new.png"),
    ),
)
```

Supported insertion positions remain:

- `append`
- `insert_before(source_index)`

`source_index` remains source-domain. `insert_before(current_count)` is not an
alias for append and remains invalid.

The root `mmd_registry.services.__all__` surface is not expanded by CP08.

## Preview and execution parity

CP08 reuses `PmxTextureInsertionPreview` as the only source of the intended
texture insertion document.

Execution does not reconstruct texture ordering independently.

This means the same request and the same source snapshot must produce the same
intended document through:

```python
preview_structural_edit(document, request).document
```

and:

```python
apply_structural_edit(source_path, output_path, request).document
```

The insertion ordering, reference shift, path validation, parser limits, index
capacity rules, and material texture-reference rewriting therefore remain owned
by the CP07 preview kernel and CP06 reference-shift planner.

## Shared verified serialization kernel

`mmd_registry.pmx.structural_output` remains the internal structural output
authority.

CP08 factors the already-existing serialization verification sequence so both
legacy structural transforms and texture insertion use the same steps:

1. certified preview construction;
2. deterministic `serialize_pmx(...)`;
3. reparse from the serialized byte payload;
4. independent `PmxStructuralInvariantCertificate`;
5. exact reparsed-document equality with the certified intended document;
6. output SHA-256 derivation.

The existing `PmxStructuralSerializationResult` retains its legacy constructor
and behavior.

Texture insertion uses a private serialization-evidence type. It is not exported
from `mmd_registry.pmx`, `mmd_registry.services`, or `structural_output.__all__`.

## Shared filesystem transaction

CP08 does not copy the atomic output implementation.

Both legacy structural execution and texture insertion execution use one private
transaction kernel around the existing v0.8 safe-output primitives:

- `_resolve_edit_paths(...)`
- `_file_identity(...)`
- `_commit_verified_bytes(...)`

The transaction captures:

- resolved source identity;
- source bytes;
- source SHA-256;
- one parsed source document.

Verified output bytes are published only after the safe-output kernel confirms
that the source path, identity, and SHA-256 still match the captured snapshot.

Destination state is checked before work and again immediately before
publication.

## Atomicity and destination policy

Input and output must remain distinct files.

Without `overwrite=True`, an existing destination is refused.

With `overwrite=True`, only a distinct safe destination may be replaced.

A destination that appears or changes during execution is detected during the
pre-publication destination recheck.

The safe-output kernel writes verified bytes to a temporary file in the
destination directory, verifies the temporary payload hash, and then performs
atomic publication.

Temporary output residue is removed when publication fails.

No non-atomic fallback is authorized.

## Texture insertion safety retained from CP07

Before serialization, CP07 still enforces:

- portable texture path policy;
- strict source-PMX text encoding;
- encoded texture-path byte limit;
- texture parser count limit;
- current PMX texture-index width capacity;
- source-domain anchor validity;
- immutable texture-path materialization;
- material texture/sphere/toon reference shift;
- full structural invariant certification.

CP08 does not resize PMX index widths.

CP08 does not normalize or silently repair inserted paths.

## Execution result

Texture insertion continues to return the existing public:

```python
PmxStructuralExecutionResult
```

A successful insertion execution reports:

- `status == "written"`
- `dry_run == False`
- `output.written == True`
- output SHA-256 and byte size
- `verification.invariants == "passed"`
- `verification.reference_model == "passed"`
- `verification.serialization == "passed"`
- `verification.semantic == "passed"`
- `verification.input_unchanged == True`

The CP07 preview schema remains the basis of insertion audit evidence.

Raw inserted texture paths are not added to the JSON-ready audit report.
Insertion payload evidence continues to use `path_sha256`.

## Failure provenance

CP08 retains the existing structural execution stage vocabulary:

- `service_validation`
- `path_resolution`
- `source_snapshot`
- `source_parse`
- `intent_resolution`
- `structural_certification`
- `serialization`
- `reparse`
- `reparse_certification`
- `semantic_compare`
- `output_commit`

No new public diagnostic operation or diagnostic code is introduced.

Examples:

- invalid inserted path or anchor -> `structural_certification`
- serialization failure -> `serialization`
- reparsing failure -> `reparse`
- invalid reparsed document -> `reparse_certification`
- reparsed semantic mismatch -> `semantic_compare`
- source/destination race at publication -> `output_commit`

## Capability policy

CP08 does not promote a new capability-manifest field.

In particular, CP08 must not add:

```text
structural_insert
```

Capability promotion remains deferred to the later release capability checkpoint.

Existing fields remain the compatibility contract:

- `structural_preview=True`
- `structural_write=True`
- `structural_contract="reference_safe_execution"`

## Compatibility requirements

CP08 must preserve:

- legacy v0.9.1 structural preview behavior;
- legacy v0.9.1 structural serialization behavior;
- legacy `PmxStructuralSerializationResult` construction;
- legacy `write_pmx_structural_transform(...)`;
- existing `PmxStructuralWriteResult`;
- existing service request alias;
- exact root service public surface;
- existing diagnostic vocabulary;
- lazy structural-output import from the service layer;
- v0.8 safe-output race and atomicity behavior.

## Non-goals

CP08 does not authorize:

- texture deletion/reorder plus insertion in one request;
- mixed legacy collection edits and texture insertions;
- insertion of materials, bones, morphs, rigid bodies, or vertices;
- automatic PMX index-width expansion;
- in-place PMX mutation;
- silent path rewriting;
- arbitrary record payloads;
- CLI insertion commands;
- GUI behavior;
- capability promotion;
- Smart Tools;
- model generation;
- physics generation or simulation.

## Required regression evidence

CP08 tests must cover at least:

- append execution;
- `insert_before` execution;
- material texture-reference shifting;
- request-order preservation;
- preview/execute intended-document parity;
- deterministic output bytes;
- source byte preservation;
- source SHA/identity race refusal;
- destination no-clobber behavior;
- safe explicit overwrite;
- in-place refusal;
- temporary-residue cleanup;
- serialization failure;
- reparse failure;
- reparse certification failure;
- semantic mismatch;
- malformed path/anchor failure before publication;
- exact public-service boundary;
- no `structural_insert` capability promotion;
- legacy structural execution regression.

The full repository unit suite and Ruff gate remain mandatory before commit.
