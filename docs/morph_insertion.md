# CP13 Morph Insertion

CP13 adds bounded semantic morph insertion to the existing v0.9.2 structural
preview/execution authority.

Public mutation authority remains:

```python
preview_structural_edit(...)
apply_structural_edit(...)
```

`PmxStructuralEditRequest is PmxStructuralPreviewRequest` remains unchanged.

## Scope

CP13 owns insertion of semantic morph types 0 through 9:

| PMX type | Semantic type | Offset target |
| --- | --- | --- |
| 0 | `group` | source morph |
| 1 | `vertex` | source vertex |
| 2 | `bone` | source bone |
| 3 | `uv` | source vertex |
| 4 | `additional_uv_1` | source vertex |
| 5 | `additional_uv_2` | source vertex |
| 6 | `additional_uv_3` | source vertex |
| 7 | `additional_uv_4` | source vertex |
| 8 | `material` | source material or `-1` |
| 9 | `flip` | source morph |

Type 10 `impulse` insertion is deliberately not part of CP13. The repository
reference taxonomy assigns `impulse morph -> rigid body` to CP14.

Existing impulse morph records in the source document are preserved by CP13.

## Public semantic DTOs

Morph insertion DTOs live in:

```python
mmd_registry.services.structural_morph
```

The root `mmd_registry.services.__all__` surface is not expanded.

The public request does not accept:

- raw `PmxMorph`;
- raw PMX morph type integers;
- raw panel integers;
- caller-supplied `morph_type_name`;
- caller-supplied `panel_name`;
- raw serialized offset bytes.

Panels use the semantic vocabulary:

```text
system
eyebrow
eye
mouth
other
```

Morph types use the semantic vocabulary shown in the scope table.

## Source-domain reference policy

Every reference carried by a new morph payload is expressed against the
captured source document.

For group and flip morph offsets:

```text
new morph -> existing source morph
```

is allowed.

```text
new morph -> new morph
```

is refused in CP13.

After the insertion positions are planned, accepted source-domain morph
references are mapped through the same certified insertion shift plan used to
place the new records.

Vertex, bone, UV, and material references likewise must target existing source
records. Material morph index `-1` keeps its standard all-materials sentinel
meaning.

## Incoming morph-reference shifts

Insertion of a morph changes the numeric index of source morphs after an
insertion anchor. CP13 therefore rewrites all existing incoming morph-index
owners:

- group morph -> morph;
- flip morph -> morph;
- display-frame element -> morph.

Bone display-frame targets are preserved.

Impulse morph -> rigid body references are not morph-index relationships and
remain unchanged.

## Ordering

Positions reuse the shared CP05/CP06 insertion vocabulary:

```text
append
insert_before(source_index)
```

Anchors are source-domain indices.

For multiple requests at one anchor, request order is stable. Appended requests
also preserve request order.

Insertion is additive only: source morph records are not deleted or reordered.

## PMX version and additional-UV restrictions

Flip morph insertion requires PMX 2.1.

Additional-UV morph requirements are:

```text
type 4 -> additional UV layer 1
type 5 -> additional UV layer 2
type 6 -> additional UV layer 3
type 7 -> additional UV layer 4
```

A source whose header does not expose the required layer fails closed.

CP13 does not modify `additional_uv_count`.

## Exact binary32 semantics

All values serialized by PMX as binary32 are canonicalized to their exact
finite float32 value before the intended document is certified.

This includes:

- group weight;
- vertex translation;
- bone translation;
- bone quaternion rotation;
- UV/additional-UV offset;
- all material morph vectors/scalars;
- flip weight.

Values that cannot be represented as finite PMX float32 fail before reference
shift allocation.

No epsilon comparison, clamping, quaternion normalization, color repair, or
silent numeric rewriting is authorized.

## Parser and capacity bounds

CP13 keeps the existing morph parser safety limits:

```text
MAX_PMX_MORPH_COUNT              = 200000
MAX_PMX_MORPH_OFFSET_COUNT       = 2000000
MAX_PMX_TOTAL_MORPH_OFFSET_COUNT = 5000000
```

Morph index widths remain the source header width: 1, 2, or 4 bytes, signed.

The shared structural capacity model must certify the resulting morph count.
Automatic index-width widening is not allowed.

## Preview certification

The morph preview path is:

```text
typed service DTO
    -> private semantic payload
    -> source/version/count/float validation
    -> morph insertion shift plan
    -> existing group/flip reference remap
    -> existing display-frame morph remap
    -> materialize new PmxMorph records
    -> whole-document invariant/reference certificate
    -> bounded preview evidence
```

Preview never writes to the filesystem.

Raw names and numeric payload values are not copied into JSON-ready audit
reports. Payload evidence is SHA-256 bounded.

## Execution

Execution reuses the existing shared verified structural transaction:

```text
certified morph preview
    -> deterministic serialize_pmx
    -> reparse
    -> independent invariant/reference certificate
    -> exact document equality
    -> source identity/SHA revalidation
    -> safe atomic publication
```

No morph-specific filesystem writer is introduced.

The same transaction continues to enforce:

- source/output distinct paths;
- symlink/hardlink alias refusal;
- no-clobber by default;
- explicit overwrite only for a distinct safe destination;
- source identity capture;
- source SHA-256 capture;
- immediate pre-publication source revalidation;
- destination-state recheck;
- temporary-file flush/fsync;
- temporary payload hash verification;
- atomic publication;
- temporary residue cleanup;
- no non-atomic fallback.

## Failure provenance

CP13 reuses the existing structural execution stage vocabulary:

```text
service_validation
path_resolution
source_snapshot
source_parse
intent_resolution
structural_certification
serialization
reparse
reparse_certification
semantic_compare
output_commit
```

No diagnostic operation or diagnostic code is added.

## Compatibility boundary

CP13 must preserve:

- CP12 bone insertion preview/execution;
- CP10 material insertion preview/execution;
- CP08 texture insertion preview/execution;
- v0.9.1 legacy morph delete/reorder execution;
- v0.9.1 general structural execution;
- existing PMX reader/writer behavior;
- root service API boundary;
- capability manifest shape.

`structural_insert` remains absent from the capability manifest.

## Non-goals

CP13 does not authorize:

- impulse morph insertion;
- new-morph -> new-morph references;
- mixed texture/material/bone/morph insertion;
- legacy reorder/delete plus morph insertion in one request;
- vertex insertion;
- rigid-body insertion;
- physics generation or simulation;
- raw `PmxMorph` public input;
- raw binary payload hooks;
- index-width widening;
- in-place source mutation;
- approximate semantic comparison;
- silent repair or normalization;
- CLI insertion commands;
- root DTO export;
- capability promotion.

## Required evidence before commit

CP13 validation must cover at least:

- append and insert-before;
- same-anchor and append ordering;
- semantic morph types 0 through 9;
- source-domain group/flip mapping;
- refusal of new-to-new morph references;
- existing group/flip incoming shifts;
- existing display-frame morph shifts;
- material `-1` preservation;
- PMX 2.0/2.1 behavior;
- additional UV layer requirements;
- UTF-8 and UTF-16LE;
- morph index widths 1/2/4;
- no automatic widening;
- parser morph/offset limits;
- exact float32 preview/execute parity;
- deterministic output bytes;
- exact reparse semantic equality;
- source-byte preservation;
- opaque trailing-data refusal;
- no-clobber and explicit overwrite;
- in-place refusal;
- serialization/reparse/re-certification/semantic failures;
- source and destination race refusal;
- temporary-file cleanup;
- privacy-bounded reporting;
- private writer boundary;
- no capability promotion;
- CP08/CP10/CP12 regressions;
- v0.9.1 morph structural regression;
- full v0.9.2 and v0.9.1 suites;
- Ruff;
- compileall;
- full repository suite.
