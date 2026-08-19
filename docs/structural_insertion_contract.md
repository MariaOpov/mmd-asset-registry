# v0.9.2 Structural Insertion Threat Model & Architecture Contract

Status: **CP02 contract freeze** for v0.9.2.

This document freezes the safety and compatibility rules for bounded PMX structural
insertion before production insertion code is introduced. CP02 does **not** promote
structural insertion as a supported public capability.

## 1. Compatibility boundary

The released v0.9.1 public authority remains authoritative:

- `mmd_registry.services.preview_structural_edit(document, request)`
- `mmd_registry.services.apply_structural_edit(input_path, output_path, request, *, overwrite=False)`

`PmxStructuralEditRequest` remains the same request type as
`PmxStructuralPreviewRequest`. Existing callers using
`PmxStructuralPreviewRequest(collection_edits=())` must remain valid.

`PmxStructuralCollectionEdit` keeps its released delete/reorder meaning. Its
`old_indices_in_new_order` field is not repurposed to smuggle inserted records,
negative sentinels, raw PMX objects, or new-only placeholders.

Any future public insertion vocabulary must be additive, immutable/effectively
immutable, deterministic, default-empty when attached to an existing request, and
shared by preview and execution. CP02 does not freeze the exact names or constructor
signatures of future insertion DTOs.

No new parallel mutation authority is authorized. In particular, CP02 does not
authorize a public `insert_structural_edit`, `apply_structural_insert`, raw writer,
raw transform, or raw remap entry point.

## 2. Position semantics

v0.9.2 insertion planning supports exactly two semantic position modes:

- **append**: insert after the complete source collection;
- **insert_before(source_index)**: insert immediately before an existing record in
  the original source index domain.

`insert_before` anchors are always interpreted against the captured source snapshot,
not against a progressively mutated collection. This prevents earlier insertions from
changing the meaning of later insertion requests.

For `insert_before(source_index)`:

- `source_index` must be a plain `int`; `bool` is refused;
- negative values are refused;
- `source_index >= current_count` is refused;
- an empty collection therefore supports append only.

`insert_before(current_count)` is not a synonym for append. Callers must request
append explicitly.

Multiple insertions at the same valid source anchor are deterministic and retain
their request order. Multiple append operations also retain request order. A single
descriptor may not specify competing position modes.

Until a later checkpoint explicitly authorizes composition, one target kind may not
simultaneously be governed by a legacy delete/reorder `PmxStructuralCollectionEdit`
and an insertion plan. This avoids ambiguous interaction between source-domain
anchors and reordered/deleted source records.

## 3. Reference-shift authority

`PmxIndexRemap` remains the internal source of truth for old-index to new-index
identity changes.

For insertion-only planning, every old record survives. If an insertion occurs
before source index `j`, every old index `i >= j` shifts by the number of insertions
anchored at or before `i`. Append operations do not shift old indices.

The derived `PmxIndexRemap` must:

- retain a complete `targets` entry for every old index;
- place inserted positions in `new_indices_without_old_source`;
- densely cover `range(new_size)` exactly once;
- remain deterministic for identical source state and request.

Inserted PMX payloads are **not** stored inside `PmxIndexRemap`. A separate typed
insertion-plan/payload layer owns new records and materializes them into the new-only
positions.

Existing relationship-specific remap owners remain authoritative for shifting
references to surviving old records. Insertion does not create a second reference
taxonomy.

References embedded inside newly inserted payloads must not guess post-shift final
indices. Until explicit new-to-new dependency semantics are introduced, references
to existing records are interpreted in the captured source domain and are resolved
through the insertion shift plan. References from one new record to another new
record are not implicitly authorized by CP02.

## 4. Capacity policy

Capacity analysis is mandatory before insertion execution.

For each affected target kind, bounded evidence is derived from:

- `target_kind`
- `current_count`
- `insert_count`
- `result_count`
- declared PMX `index_width`
- signed/unsigned index encoding
- `representable`
- `expansion_required`

`result_count = current_count + insert_count`.

The existing whole-document validator remains the final PMX validity authority.
Capacity preflight must use the same representability rule and must not create a
competing definition.

For an index width of `size` bytes, the maximum addressable index is:

`(1 << (size * 8 - (1 if signed else 0))) - 1`

and the maximum addressable record count is one greater than that maximum index.

Vertex indices use unsigned encoding. Texture, material, bone, morph, and rigid-body
indices use signed encoding.

If `result_count` is not representable by the already-declared width:

- `representable = False`;
- `expansion_required = True`;
- execution refuses before publication;
- the header width is not changed automatically.

Automatic PMX index-width expansion is out of scope for v0.9.2.

The PMX signed 32-bit section-count limit remains independently authoritative.

## 5. Insert payload boundary

Public insertion requests must never accept:

- arbitrary raw PMX section objects as an unbounded mutation surface;
- raw bytes for section injection;
- callables;
- serializer/writer hooks;
- filesystem commit hooks;
- raw `PmxIndexRemap` or raw transform objects.

Future payload DTOs must be typed, bounded, deterministic, immutable/effectively
immutable, and translated at the service/internal boundary into the existing typed
PMX document model.

Exact per-section payload DTOs are deferred to the checkpoints that introduce those
targets. Texture is intentionally first because it carries no PMX index references
inside the inserted record.

## 6. Source and output safety

All existing v0.9.1 structural execution safety remains mandatory for insertion:

1. validate source/destination path policy;
2. require a destination distinct from the source;
3. capture one source identity and byte snapshot;
4. compute source SHA-256 from that snapshot;
5. parse from those captured bytes;
6. resolve insertion intent against that exact parsed snapshot;
7. perform capacity and structural planning;
8. transform and certify;
9. serialize deterministically;
10. reparse;
11. independently re-certify;
12. compare reparsed semantics with the intended certified document;
13. re-check source identity/content before publication;
14. re-check destination safety;
15. atomically publish verified bytes.

The caller's source PMX must remain byte-for-byte unchanged. No partial destination,
false-success destination, or temporary residue may remain after a failed transaction.

## 7. Fail-closed threat model

Insertion must fail closed for at least:

- malformed insertion position;
- `bool` masquerading as an integer;
- negative or out-of-range source anchor;
- incompatible legacy edit plus insertion on the same target kind;
- malformed or unbounded payload;
- invalid source-domain payload reference;
- unsupported new-to-new reference dependency;
- non-representable resulting target count;
- any attempted automatic width expansion;
- opaque/non-empty trailing data where structural certification cannot prove safety;
- invalid or unsupported reference state;
- stale/incomplete/non-dense shift evidence;
- serialization or reparse failure;
- re-certification failure;
- semantic mismatch;
- source identity/content race;
- destination race or unsafe destination state;
- publication failure.

A failure may not trigger silent repair, sentinel substitution for a removed target,
index-width widening, or source mutation.

## 8. Determinism and state isolation

For identical source bytes, request, and environment contract, insertion planning
must produce identical:

- normalized position semantics;
- capacity result;
- old-to-new shift mapping;
- new-only positions;
- target-kind ordering;
- structural intent;
- preview semantics.

No mutable module-global registry/cache may control insertion semantics. Repeated
A/B/A execution must leave A1 equal to A2.

## 9. Diagnostic privacy

Insertion failures must cross the existing structured service diagnostic boundary.
Diagnostics may expose only bounded stable fields such as code, operation, stage,
provenance, and reviewed details.

They must not expose private filesystem paths, arbitrary exception repr/text,
private model-identifying metadata, secrets, environment-specific values, raw writer
objects, Python implementation type names, or internal module names.

Exact insertion-specific diagnostic codes/stages are not promoted by CP02; later
diagnostic checkpoints may add them additively.

## 10. Explicit non-goals

CP02 and v0.9.2 do not authorize:

- arbitrary structural CRUD;
- automatic 1->2 or 2->4 byte index-width expansion;
- in-place PMX mutation;
- silent repair/normalization;
- raw binary section injection;
- mesh generation or sculpting;
- UV editing or weight painting;
- arbitrary geometry generation;
- physics simulation or automatic physics generation;
- full PMX Editor GUI;
- Smart Tools, plugins, telemetry, cloud mutation, or AI editing;
- model creation.

## 11. Capability promotion

CP02 does not add or imply `structural_insert=True`.

Until the later capability promotion gate, the canonical released claim remains the
v0.9.1 structural preview/write contract. Individual insertion targets must be
described narrowly as they pass their own preview/execution gates.

## 12. CP02 exit contract

CP02 is complete when:

- this threat/safety contract is version-controlled;
- released v0.9.1 public signatures and request aliasing remain consumable;
- `PmxStructuralCollectionEdit` remains delete/reorder-only;
- `PmxIndexRemap` may represent new-only positions without those positions becoming
  public execution authority;
- no production insertion path is enabled by CP02;
- targeted contract tests and the required regression gates pass.

CP03 may then implement read-only structural capacity evidence without mutating PMX
documents or promoting insertion execution.
