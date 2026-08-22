# v0.9.3 structural transaction contract and architecture freeze

Status: normative architecture contract for CP05. This document freezes the
transaction semantics that later v0.9.3 checkpoints must implement. It does
not itself add, promote, or imply production capability.

The source authority for this contract is the released v0.9.2 tree at
`6247529c9091b00a1a0305462a0c81a1ac099e48`, the v0.9.3 compatibility
contract, the recovered structural-pipeline architecture, and the CP04
transaction-seam audit.

## 1. Checkpoint freeze record

| Gate-B item | Frozen CP05 decision |
| --- | --- |
| Checkpoint | CP05 — Transaction Contract Specification & Architecture Freeze |
| Phase | Phase A — Architecture Recovery |
| Objective | Define one deterministic, reference-safe, capacity-safe, previewable, executable, all-or-nothing structural transaction before production implementation starts. |
| Current authority | `mmd_registry.services` owns the released public facade; `PmxIndexRemap` owns old-to-final mapping; the coordinated insertion planner owns request-local ID resolution; target kernels own typed materialization; the existing structural output path owns verified serialization and atomic publication. |
| In scope | The terminology, request and operation model, local identity, existing/new references, mixed placement, ordering, dependency and cycle rules, deletion, whole-plan preflight, preview/execute parity, atomicity, provenance, and public/private boundary defined below. |
| Out of scope | Production code, tests, schemas, CLI changes, capability promotion, serialization-format changes, and release engineering. |
| Files expected | This document only. |
| Public API impact in CP05 | None. The eventual additive transaction boundary is specified, not implemented. |
| Schema impact | None. Registry schema `0.3` and edit-plan schema `1` remain unchanged. |
| Capability impact | None. No structural-transaction capability claim is authorized before CP27 distribution proof. |
| Safety invariant | One source-bound plan produces one certified intended document and at most one verified publication; every failure publishes nothing and leaves the source unchanged. |
| Failure behavior | Fail closed with bounded deterministic stage, operation/identity/relationship context where applicable, and no raw exception representation or private path/model leakage. |
| Expected implementation tests | Focused model, identity, reference, graph, mixed-operation, capacity, preview-parity, execution, certification, race, compatibility, installed-wheel, and cross-platform gates in CP06–CP27. |
| Expected CP05 evidence | Docs-only diff, source/test/tooling identity, UTF-8/LF validation, Markdown structure checks, exact SHA-256, independent cached-diff review, and a clean commit. |

CP05 requires no production code. Any later implementation that contradicts
this document must stop at a new explicit architecture decision; it must not
silently redefine the contract in code.

## 2. Normative vocabulary

The words **must**, **must not**, **should**, and **may** are normative within
the v0.9.3 campaign.

| Term | Meaning |
| --- | --- |
| Structural transaction | One immutable bounded request evaluated against one captured typed PMX source, resolved as one semantic unit, producing at most one intended document and at most one publication. It is not a loop over public edit calls. |
| Captured source | The immutable `PmxDocument` from which all source-domain indices, counts, relationships, and declared index widths are read. Execution additionally binds this document to one exact input-byte snapshot. |
| Source-domain index | A non-boolean integer naming one record in a captured source collection. It never means a final result index. |
| Transaction-local identity | A bounded caller-declared `new_id` naming one inserted entity only inside one request. |
| Final result index | An internal planner-derived index in the transaction result. Callers never supply one. |
| Collection transform | One complete final order of surviving old records for a target kind. Omitted old records are deletions; changed survivor order is reorder. |
| Insertion operation | One existing target-specific insertion DTO, including its source-anchored position, payload, and optional `new_id`. |
| Combined remap | The one authoritative `PmxIndexRemap` per changed target that represents deletion, reorder, and new-only final positions together. |
| Reference binding | Evidence that a source-domain or transaction-local reference resolves to one final result index, or to a relationship-specific sentinel. |
| Dependency edge | A materialization-order requirement derived from PMX relationship ownership. A reference and a dependency are related evidence but are not the same object. |
| Transaction plan | One immutable internal source-bound value containing normalized operations, combined remaps, insertion placements, identity bindings, dependency order, preflight evidence, and a canonical digest. |
| Blocker | A deterministic reason why no complete safe plan/result/publication can be produced. A blocker is never partial success. |
| Publication | The existing verified safe-output commit of final bytes to the destination. In-memory immutable intermediate documents are not publications. |

Display names, Python object identities, destination paths, temporary names,
and PMX final indices are not transaction identities.

## 3. Additive public request model

The eventual public transaction vocabulary must live in the explicit module
`mmd_registry.services.structural_transaction`. CP06 introduces only the
smallest immutable data-model foundation; later checkpoints add preview and
execution behavior.

The request shape is conceptually:

```python
PmxStructuralTransactionOperation = (
    PmxStructuralCollectionEdit
    | PmxStructuralTextureInsertion
    | PmxStructuralMaterialInsertion
    | PmxStructuralBoneInsertion
    | PmxStructuralMorphInsertion
    | PmxStructuralRigidBodyInsertion
    | PmxStructuralVertexInsertion
)

@dataclass(frozen=True, slots=True)
class PmxStructuralTransactionRequest:
    operations: tuple[PmxStructuralTransactionOperation, ...] = ()
```

This is a typed union, not `Any`, `dict[str, Any]`, a string operation tag, a
JSON mutation DSL, or a generic property path. The concrete public class of
each tuple member is the explicit operation type. The request must reject a
list or any non-tuple container and must reject every value outside the union.
No mutable default is allowed.

The union deliberately reuses the released `PmxStructuralCollectionEdit` and
the six released insertion DTO families by identity. A caller does not need a
second insertion vocabulary merely to compose a transaction.

The empty tuple is a valid no-op request. Multiple insertion members of the
same or different target kinds are valid subject to the rules below. At most
one `PmxStructuralCollectionEdit` may name any target kind. Repeating a
collection-transform target is request validation failure; the engine must not
guess how to merge competing survivor orders.

The eventual public calls are additive explicit-submodule services:

```text
preview_structural_transaction(document, request)
apply_structural_transaction(input_path, output_path, request, *, overwrite=False)
```

They must use the established public preview/execution result vocabulary and
the established structured `PmxServiceError` boundary rather than expose a raw
writer result or an internal plan. Their exact stable report schema is frozen
at CP17 after CP16 implements the semantic fields required by section 13.

### 3.1 Released compatibility facade remains unchanged

The following v0.9.2 contracts remain intact:

- `PmxStructuralEditRequest is PmxStructuralPreviewRequest`;
- the first seven released request fields and constructor defaults;
- rejection of `collection_edits` mixed with insertion fields in that released
  request;
- the call shapes and behavior of `preview_structural_edit` and
  `apply_structural_edit`;
- explicit insertion DTO submodules and the non-root
  `PmxStructuralNewReference` namespace;
- existing root-package, service, PMX, diagnostic, CLI, schema, and capability
  contracts.

The new transaction request is not an alias, subclass, flag, or extra mutable
mode on the old request. Existing requests continue through their released
routes. Transaction services translate both reused operation DTO families into
one new internal plan without changing the DTOs' released standalone meaning.

## 4. Exactly two operation categories

v0.9.3 authorizes two bounded structural operation categories.

### 4.1 Collection transform

`PmxStructuralCollectionEdit(target_kind, old_indices_in_new_order)` is a
complete captured-source survivor sequence for one target collection:

- each listed index names one old source record;
- every listed index must be in range, non-boolean, non-negative, and unique;
- an omitted old index is deleted;
- list order is final survivor order before insertions are interleaved;
- the full natural source order is an explicit identity/no-op transform;
- an empty sequence deletes the entire old collection, subject to reference
  safety and PMX invariants.

Delete and reorder are therefore effects of one complete collection transform,
not competing imperative operation types. This preserves the established
old-index authority and prevents contradictory delete/reorder instructions.

When no collection transform exists for a target, its implicit survivor
sequence is every captured-source index in natural ascending order.

### 4.2 Insertion

Each released target-specific insertion DTO is one insertion operation. Its
concrete type fixes the target kind. Its payload remains bounded by the
released target vocabulary. Its position is captured-source `append` or
`insert_before(source_index)`; it is never a caller-supplied final index.

The request tuple ordinal is retained as deterministic evidence and is the
tie-breaker for multiple insertions in the same placement group. Two otherwise
equal insertion DTOs without IDs are still two operations. An insertion with a
`new_id` participates in the one transaction-local identity namespace.

No v0.9.3 operation directly edits an arbitrary field of an existing record,
supplies a remap, supplies a final index, invokes a serializer, or controls a
filesystem hook.

## 5. Combined delete, reorder, and insertion placement

Every position is interpreted against the captured source, then interleaved
with the final survivor sequence. The planner must apply this exact rule for
each target kind:

1. derive the survivor sequence from the target's collection transform, or use
   the natural old sequence when no transform exists;
2. validate every `insert_before(source_index)` anchor against the captured
   source count;
3. reject an insertion whose anchor is not in the survivor sequence;
4. walk the survivor sequence in its final order;
5. immediately before each survivor, emit all insertion operations anchored to
   that old record in original transaction-request tuple order;
6. emit the survivor;
7. after every survivor, emit all `append` operations for that target in
   original transaction-request tuple order.

Consequences are frozen:

- `insert_before(old_index)` follows that named source record through reorder;
- it does not mean the old numeric slot after reorder;
- an anchor deleted by the same transaction is a blocker, not append and not a
  nearest-survivor guess;
- append means the end of the final reordered survivor collection;
- insertions at different anchors follow final survivor order;
- insertions at the same anchor preserve request order;
- a target whose survivors are empty may receive append insertions, but no
  `insert_before` anchor can survive;
- a no-op transform does not change standalone v0.9.2 insertion placement.

This walk derives the complete final sequence, all old-to-final entries, every
new-only final position, and `new_indices_in_request_order` before any payload
is materialized. There is exactly one combined `PmxIndexRemap` for the target;
the transaction layer must not maintain separate delete/reorder and insertion
maps.

## 6. Transaction-local identity

The released `PmxStructuralNewReference` vocabulary and `new_id` syntax are
retained:

```text
target_kind: vertex | texture | material | bone | morph | rigid_body
new_id: [A-Za-z][A-Za-z0-9_.-]{0,63}
```

The exact ASCII string is the identity. It is case-sensitive and is not
trimmed, case-folded, Unicode-normalized, inferred from a display name, or
rewritten. Empty, whitespace-containing, non-ASCII, overlength, and otherwise
nonmatching strings are rejected by the DTO boundary.

Within one transaction, every non-`None` insertion `new_id` is globally unique
by string across all six target kinds. Reusing one ID for a different kind is
also a duplicate, not a separate namespace. Duplicate detection must happen
before dependency construction, reference resolution, materialization, or
serialization. There is no shadowing and no last-write-wins behavior.

An insertion may omit `new_id` when nothing needs to name it. `None` does not
declare an anonymous referenceable identity. A local ID has no meaning across
requests, documents, processes, preview calls, executions, or PMX files. It is
not persisted in output bytes.

Forward declaration is valid: a reference may appear earlier in the request
tuple than the insertion that declares its ID because the planner collects and
validates every identity before resolving any reference.

## 7. Existing and new reference semantics

Every public reference-bearing insertion field has a fixed target kind in its
DTO contract and accepts one of the explicitly authorized forms:

| Form | Public representation | Meaning |
| --- | --- | --- |
| Existing | A non-boolean integer in the field's fixed captured-source target domain | Resolve through that target's combined remap to its final index. It is never already-final. |
| New | `PmxStructuralNewReference(target_kind, new_id)` where that DTO field authorizes the target kind | Resolve through the transaction's validated identity bindings to the insertion's planned final index. |
| Sentinel | Integer `-1` only for relationships whose released PMX/DTO contract explicitly permits it | Preserve relationship-specific absence. It is not an existing or new identity. |

A separate public `ExistingReference` wrapper is intentionally not introduced
in v0.9.3: the concrete DTO field already fixes the target kind, and its integer
is normatively source-domain only. This keeps the model additive and prevents
an integer from ambiguously meaning a future/final index. `bool` must never be
accepted as an integer index.

### 7.1 Authorized new-to-new matrix

The v0.9.2 audited matrix remains the complete v0.9.3 public matrix:

| Inserted record/field | May name a new target |
| --- | --- |
| Material `texture_index` | Texture |
| Material `sphere_texture_index` | Texture |
| Material texture-mode `toon_reference_index` | Texture |
| Vertex deform bone index/indices | Bone |
| Rigid-body `bone_index` | Bone |
| Vertex morph offset | Vertex |
| UV/additional-UV morph offset | Vertex |
| Bone morph offset | Bone |
| Material morph offset | Material |
| Impulse morph offset | Rigid body |

Inserted bone parent/tail/inherit/IK references and group/flip morph references
remain captured-source integer fields. Same-target new-to-new references,
new-morph targets, arbitrary cross-kind references, and retargeting a surviving
existing record to a new entity are not authorized in v0.9.3.

### 7.2 Resolution failures

Before materialization, the plan must reject:

- an existing index outside the captured source domain;
- an existing reference whose target old record is deleted by the transaction;
- a new reference whose ID is missing;
- a new reference whose declared target kind differs from the identity owner;
- a new reference in a DTO field that does not authorize that target kind;
- a sentinel in a required relationship;
- any caller attempt to supply a final index as such.

Resolution uses one final-state map. It must not observe an intermediate
document or re-interpret a source integer after an earlier operation.

## 8. Conservative deletion semantics

Deletion is reference-safe, not cascading and not repairing.

For every reference owned by a record that survives the transaction:

- if its target survives, remap it to the final target index;
- if it is a valid relationship-specific sentinel, preserve it;
- if its target is deleted, the transaction is blocked unless an explicitly
  authorized operation vocabulary supplies a replacement.

v0.9.3 has no operation for retargeting an existing surviving record, so such
a required inbound reference is a blocker. The engine must not silently:

- choose another index or same-named record;
- substitute `-1`;
- delete the dependent owner;
- reparent a bone;
- remove an offset from a surviving morph;
- rewrite a payload by heuristic.

When the owning source record is itself deleted, its outbound references cease
to exist and do not block solely on their old targets. This does not authorize
dependent deletion; both removals must already be explicit in the request's
collection transforms.

An inserted record that references a source entity deleted by the same
transaction is blocked under the same rule. Optional/sentinel semantics remain
relationship-specific and are never generalized.

## 9. One source-bound transaction plan

Public DTO translation must produce exactly one immutable internal plan before
materialization. The plan owns:

- the captured source binding and source structural evidence;
- validated public operation ordinals and categories;
- one effective survivor sequence per target;
- one combined remap and insertion-placement vector per changed target;
- every declared local identity and final index binding;
- resolved existing/new/sentinel reference evidence;
- dependency edges and deterministic topological order;
- final collection counts and complete preflight evidence;
- normalized operation/effect evidence for preview;
- one canonical `plan_sha256`.

The plan is an implementation detail. It cannot be supplied, modified,
persisted, or executed by callers. It is valid only for the immutable source
value from which it was derived. Execution rebuilds it from the exact captured
input-byte snapshot; it does not trust a caller-provided preview or digest.

### 9.1 Canonical plan digest

`plan_sha256` is lowercase SHA-256 over UTF-8 canonical JSON with sorted object
keys, compact separators, ordered arrays, and an explicit schema discriminator.
Its canonical inputs are exactly:

1. the literal plan schema identifier
   `mmd_registry.structural_transaction.plan.v1`;
2. a semantic source SHA-256 derived by deterministic in-memory PMX
   serialization of the captured typed source, plus PMX version, declared index
   widths, and six captured source counts;
3. normalized typed operation payload evidence, including original insertion
   request ordinals but excluding object representations and paths unrelated to
   PMX payload semantics;
4. final survivor sequences, combined remaps, new-only positions, and local ID
   bindings;
5. resolved reference and dependency evidence;
6. final counts and preflight outcomes;
7. the canonical materialization order.

The in-memory source serialization is binding evidence only; preview performs
no filesystem I/O and does not expose a raw writer. CP17 must freeze the exact
JSON report representation and test identical-plan repeatability before this
digest becomes stable public preview evidence.

The digest may be exposed as bounded preview/execution parity evidence after
CP17. It is not a security authorization token, a caller-selected transaction
ID, a persistent model ID, a PMX field, a destination-derived value, or a
replacement for execution's exact input `source_sha256` and verified
`output_sha256`.

## 10. Deterministic normalization and ordering

Transaction semantics use three distinct deterministic orders.

### 10.1 Canonical evidence order

Target-scoped plan evidence is ordered by the released
`PmxReferenceTargetKind` order:

```text
vertex, texture, material, bone, morph, rigid_body
```

Within each target, the collection transform precedes insertion evidence.
Insertion evidence follows final placement-group order; original request tuple
ordinal breaks ties inside a group. Identity bindings are ordered by final
target kind rank, final index, then exact `new_id`. No Python set/dict/hash
iteration order may affect output.

### 10.2 Final collection order

Final records follow the placement algorithm in section 5. This is semantic
result order, not stage execution order.

### 10.3 Materialization dependency order

The planner creates target-stage nodes for changed collections and separates
reference-binding evidence from dependency edges. The frozen semantic edges
are:

```text
texture -> material
bone -> vertex
bone -> rigid_body
material -> morph
bone -> morph
vertex -> morph
rigid_body -> morph
```

Edges are included when the corresponding target stages are present and when
required by the established remap/materialization ownership. Concrete
new-reference bindings must agree with this matrix; they do not create an
unauthorized relationship type.

The canonical topological tie-break rank is:

```text
texture, material, bone, vertex, rigid_body, morph
```

Kahn-style selection must choose the lowest fixed rank among all ready nodes.
This produces the released safe order for six changed targets while explaining
which edges are semantic and which placements are stable tie choices. Request
tuple order never overrides a dependency.

Planning of all collection maps, identities, references, and capacity occurs
before this order is used. Materialization order is not an imperative
interpretation of the request tuple.

## 11. Dependency graph and cycle behavior

The dependency graph is internal evidence, not a public graph-mutation API. It
must use immutable ordered nodes/edges and must reject duplicate nodes,
wrong-target bindings, unsupported relationship types, and any defensively
observed missing provider node before sorting. Public duplicate identities and
unknown local references fail earlier during normalization/reference binding;
they must never be silently converted into graph nodes.

Every dependency edge means the provider target stage must precede the
consumer stage so that one existing relationship owner can safely remap and
materialize the final document. A local reference is recorded separately with
its source operation, field/relationship identifier, provider identity, and
resolved final index.

Any directed cycle is unsupported in v0.9.3. Cycle detection must fail at the
dependency-resolution stage before capacity approval, materialization,
serialization, or publication. The failure must report a deterministic
canonical cycle witness ordered by the fixed target rank, not an arbitrary
set traversal or recursive exception. There is no SCC co-materialization,
fixed-point resolution, or caller-selected cycle breaker.

The authorized public new-reference matrix is acyclic and excludes same-target
new references. The explicit cycle rule remains mandatory so internal defects
or a future vocabulary expansion cannot inherit accidental recursion. Any
future support for a currently forbidden edge requires a separately reviewed
contract change.

## 12. Whole-transaction capacity and payload preflight

For each target kind, the final count is:

```text
surviving_old_count + insertion_count
```

The transaction plan must compute every final count from the captured source
and prove all preflight obligations before the first target materialization:

1. every source index and insertion anchor is valid;
2. every final target count fits the source header's declared PMX index width;
3. every final section count fits the PMX signed 32-bit count field;
4. every target-specific reader limit and aggregate payload count fits;
5. every applicable string/path byte length, float32, PMX-version, per-record,
   IK, morph-offset, and related payload constraint is valid;
6. every existing/new/sentinel reference is resolvable in the final state;
7. the final complete reference graph and document invariants are capable of
   certification under the authorized vocabulary.

The existing target kernels may initially repeat local checks as defensive
verification, but they must consume or agree with the one authoritative plan.
A repeated target planner must not derive a different map.

No target may be materialized while another target still has an unchecked
count, capacity, aggregate, reference, or payload constraint. In-memory
immutability prevents partial publication, but it does not weaken this
whole-plan preflight requirement.

v0.9.3 must not automatically widen index fields, migrate schema, rewrite PMX
version, or retry under a different header. Boundary-plus-one is a blocker.

## 13. Preview contract

`preview_structural_transaction` is pure with respect to caller-visible state:
it accepts one typed immutable source document and one immutable request,
performs no filesystem I/O, leaves both values unchanged, and uses the same
normalization/resolution/plan authority as execution.

A successful preview must represent a complete certified intended document,
not an unverified partial stage. Its deterministic evidence must distinguish:

- original operation count and canonical normalized operation list;
- collection-transform, delete, reorder, insertion, and no-op effects;
- captured counts, final counts, final insertion indices, and changed targets;
- declared local identities and resolved local references;
- remapped surviving existing references;
- dependency edges and canonical materialization order;
- capacity/payload preflight outcome;
- `plan_sha256` after CP17 freezes its public representation;
- dry-run status and complete invariant-certificate status;
- the fact that source and destination were not touched.

An empty request successfully previews an unchanged certified document with
zero operations. Identity/no-op collection transforms remain visible as no-op
evidence but do not create false changes.

A type, identity, reference, dependency, deletion, capacity, payload, or
invariant blocker does not return a partly successful preview or a partly
materialized document. It raises the established structured public service
failure with the deterministic provenance required by section 16. That failure
is the preview's blocker evidence. CP16/CP17 may add bounded ordered details,
but must not change a blocker into partial success or expose raw internals.

## 14. Execution contract and preview parity

`apply_structural_transaction` accepts the established safe input/output path
shape and `overwrite` policy. It must:

1. validate the public request and safe paths;
2. capture exact source bytes, size, file identity, and `source_sha256` once;
3. parse and certify the source snapshot;
4. build the same semantic transaction plan used by preview against that
   captured typed source;
5. complete whole-plan dependency/reference/capacity/payload preflight;
6. materialize one intended immutable document in deterministic dependency
   order without intermediate serialization or publication;
7. independently certify the complete intended document;
8. serialize only that final intended document;
9. reparse the exact serialized bytes;
10. independently certify the reparsed document;
11. prove whole-document canonical semantic equality between intended and
    reparsed documents;
12. reverify source identity/hash and destination safety immediately before
    commit;
13. atomically publish the exact verified bytes once;
14. return bounded execution evidence including exact `source_sha256`, verified
    `output_sha256`, sizes, and the same `plan_sha256` semantics as preview.

Preview and execution must not contain separate interpreters. For the same
typed source semantics, request, and policy, their normalized operations,
combined maps, identity bindings, dependencies, final counts, intended
document, and `plan_sha256` must agree. Execution additionally owns exact
input-byte identity, path/race checks, serialization evidence, and publication.

The execution call does not accept an internal plan, caller digest, final
indices, serialized bytes, destination callback, or filesystem hook. A prior
preview is advisory evidence, not authority; execution safely rebuilds the
plan from the exact source snapshot it will protect.

## 15. All-or-nothing invariant

The transaction state machine has only these externally meaningful outcomes:

| Outcome | Source | Destination | Temporary output | Result |
| --- | --- | --- | --- | --- |
| Preview success | Unchanged | Untouched | None | One complete certified intended document and deterministic audit evidence |
| Preview blocker | Unchanged | Untouched | None | One bounded structured failure; no partial result |
| Execution success | Unchanged and reverified | Exactly one atomic verified publication | Cleaned/consumed | One verified execution result |
| Execution failure at any stage | Unchanged | No new/partial transaction output; pre-existing destination preserved under overwrite policy | Removed | One bounded structured failure |

No operation, target, dependency component, or in-memory stage can be committed
independently. A successful in-memory stage is not partial transaction success.
There is no continue-on-error, best-effort target, per-operation rollback, or
fallback to sequential public calls.

## 16. Failure provenance

Transaction failures must preserve the existing public `PmxServiceError`
discipline and add only bounded deterministic details. The semantic stage order
is frozen as follows; legacy request stage strings remain compatible and are
not renamed by this contract.

| Transaction stage | Provenance class | Required meaning |
| --- | --- | --- |
| `service_validation` | `service_boundary` | Public type/call-shape/request validation failed. |
| `path_resolution` | `safe_output` | Execution paths or overwrite policy failed before source capture. |
| `source_snapshot` | `source_input` | Exact input bytes/identity could not be captured. |
| `source_parse` | `source_input` | Captured source could not be parsed/certified. |
| `transaction_normalization` | `transaction_plan` | Operation/category/anchor/local-ID normalization failed. |
| `reference_resolution` | `transaction_plan` | Existing/new/sentinel final-state binding failed. |
| `dependency_resolution` | `transaction_plan` | Dependency graph or cycle validation failed after reference binding. |
| `capacity_preflight` | `transaction_plan` | Whole-plan width/count/payload preflight failed. |
| `transform` | `structural_pipeline` | Deterministic materialization failed after approved preflight. |
| `structural_certification` | `structural_pipeline` | Complete intended-document invariant certification failed. |
| `serialization` | `structural_pipeline` | Final intended document could not be serialized. |
| `reparse` | `structural_pipeline` | Serialized output could not be reparsed. |
| `reparse_certification` | `structural_pipeline` | Reparsed output failed independent certification. |
| `semantic_compare` | `structural_pipeline` | Intended and reparsed documents were not canonically equal. |
| `source_reverify` | `safe_output` | Source identity/hash changed before publication. |
| `output_commit` | `safe_output` | Destination race or atomic publication failed. |

Where applicable, public details should identify a canonical operation ordinal,
target kind, bounded `new_id`, and stable relationship identifier. They must
also state whether source bytes were merely read and whether a destination was
published. They must not include raw exception `repr`, arbitrary object
representations, raw private model content, absolute private paths, temporary
names, process-global counters, or nondeterministic set/dict order.

One failure reports the earliest authoritative stage that can establish the
blocker. Later stages must not run merely to collect more errors. Exact
diagnostic codes/messages and stable report keys are frozen in CP22 with
compatibility tests; CP05 freezes their semantic information boundary.

## 17. Public and private boundary

### Public and additive

- the explicit `mmd_registry.services.structural_transaction` request,
  operation union, preview/apply functions when their checkpoints authorize
  them, and bounded deterministic result/failure evidence;
- the reused released `PmxStructuralCollectionEdit` and six target-specific
  insertion DTO families;
- the reused explicit-submodule `PmxStructuralNewReference`;
- existing `PmxReferenceTargetKind` values and established service result/error
  vocabulary.

The root `mmd_registry` namespace remains unchanged. No raw transaction engine
is exported from `mmd_registry.pmx`. Root `mmd_registry.services` legacy exports
remain compatible; transaction-specific names stay in the explicit submodule
unless a later separately audited compatibility decision authorizes a root
re-export.

### Internal only

- the source-bound transaction plan and plan-schema implementation;
- `PmxIndexRemap`, combined collection plans, insertion placements, final
  indices, capacity-analysis objects, local-ID binding tables, and dependency
  graph/sort implementation;
- normalized/resolved target payloads, target kernels, materializers, per-stage
  preview objects, intermediate immutable documents, and certificates;
- canonical hashing helpers, source semantic serialization, raw writer results,
  serializers, reparsers, semantic equality internals, publication functions,
  stage callbacks, source/destination identities, and temporary-file mechanics.

Internal types may be refactored while preserving this contract. They must not
appear in public constructor fields, public `__all__`, arbitrary JSON input, or
caller-controlled execution hooks.

## 18. Explicit v0.9.3 non-goals

This contract does not authorize:

- a GUI, TUI, viewport, renderer, mesh/topology/UV editor, complete model
  creator, rigging/physics generator, simulation, or IK authoring workflow;
- arbitrary existing-record field updates or general CRUD;
- raw PMX mutation, byte editing, writer exposure, caller remaps/final indices,
  arbitrary JSON/string-path operations, or plugins;
- silent repair, dependent deletion, retargeting, reparenting, sentinel
  substitution, or name-based inference;
- same-target new references or reference kinds outside section 7.1;
- automatic PMX index-width widening, PMX-version migration, registry/edit-plan
  schema bump, or capability promotion;
- a giant CLI transaction command, persistence format, cloud/account/telemetry
  system, AI direct write path, PyPI publication, broad dependency, repository
  cleanup, mass rename, or style refactor.

Future GUI or Smart Tool proposals may only produce the bounded typed request,
preview it, obtain any required user confirmation, and call the same safe
execution service. They may not bypass planning or publication gates.

## 19. Downstream implementation obligations

This freeze opens production work only in the roadmap order:

| Checkpoint | Contract obligation |
| --- | --- |
| CP06 | Add only the immutable typed operation union/request foundation from section 3; no filesystem write or capability claim. |
| CP07 | Enforce the exact global, case-sensitive, non-normalizing local-ID namespace from section 6. |
| CP08 | Resolve only section 7's existing/new/sentinel forms and authorized matrix against planned final indices. |
| CP09 | Produce immutable deterministic dependency evidence, fixed tie ordering, missing-node failure, and canonical cycle failure from sections 10–11. |
| CP10 | Compose multiple insertion operations under one plan, including same-kind and cross-kind cases. |
| CP11 | Prove insertion anchors follow surviving source records through reorder. |
| CP12 | Prove deleted anchors and references to deleted targets fail without silent repair. |
| CP13 | Preserve existing delete/reorder semantics within the combined map. |
| CP14 | Prove a supported mixed six-target transaction without expanding the operation/reference vocabulary. |
| CP15 | Complete all-target final-count and target-specific preflight before materialization. |
| CP16 | Implement the successful preview and blocker semantics in section 13. |
| CP17 | Freeze exact deterministic public evidence and `plan_sha256` representation. |
| CP18 | Execute from the shared plan rather than independently interpreting operations. |
| CP19–CP21 | Preserve serialize/reparse/certify/equality/race-safe single-publication guarantees. |
| CP22–CP25 | Freeze provenance and prove adversarial isolation and backward compatibility. |
| CP26–CP27 | Optionally validate private real PMX, then prove installed distribution before any capability promotion decision. |

Every checkpoint remains subject to Gates A–J. Passing CP05 authorizes the next
implementation checkpoint; it does not pre-authorize later code, push, PR,
merge, tag, release, or publication gates.

## 20. Frozen decision summary

| Question | Frozen answer |
| --- | --- |
| What is the public request? | One additive immutable `operations` tuple in an explicit service submodule, reusing the seven released operation DTO classes. |
| What are operation categories? | Complete collection transform and insertion only. Delete/reorder are transform effects. |
| How do mixed anchors work? | A source anchor follows its surviving old record through reorder; deleted anchor fails; append is final end; request ordinal breaks same-group ties. |
| Who owns remap? | One internal combined `PmxIndexRemap` per changed target, derived before materialization. |
| What is local identity? | Exact case-sensitive globally unique request-local ASCII `new_id`; optional to declare, never persisted. |
| What does an integer reference mean? | Captured-source index in the DTO field's fixed target domain, never final; bool rejected. |
| Which new references work? | Exactly the audited cross-target matrix in section 7.1; same-target expansion is out of scope. |
| What happens to deleted references? | Surviving required owner blocks unless explicit authorized replacement exists; v0.9.3 has no such retarget operation. |
| How is order deterministic? | Canonical target evidence order, source-anchor final collection order, and dependency topological order are distinct and fixed. |
| What happens on a cycle? | Deterministic dependency-resolution failure before materialization; no cycle solving. |
| When is capacity checked? | All changed targets and all target-specific aggregate/payload limits before any target materialization; no width widening. |
| How do preview and execute agree? | Both derive the same immutable source-bound plan; execution adds exact bytes, output verification, races, and one publication. |
| What is transaction identity evidence? | Internal canonical `plan_sha256`, source-semantic-bound and later public only after CP17 freezes representation; distinct from local/source/output hashes. |
| What is atomicity? | Complete certified preview or structured blocker; exactly one verified execution publication or none. |
| What remains private? | Plans, maps, final indices, graphs, payloads, kernels, serializers, certificates, hashing, and filesystem machinery. |
| Are schemas/capabilities changed? | No. Capability promotion can be considered only at CP27 after installed-wheel proof. |

## 21. Architecture recovery closure condition

This contract, once independently verified and committed with the CP02
compatibility contract and CP03–CP04 recovery documents intact, satisfies the
final docs-only architecture checkpoint:

```text
ARCHITECTURE RECOVERY PHASE = CLOSED
TRANSACTION PRODUCTION IMPLEMENTATION = AUTHORIZED
NEXT CHECKPOINT = CP06
```

This authorization means only that CP06 may begin under its own baseline,
scope, tests, review, and commit gates.
