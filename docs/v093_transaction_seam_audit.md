# v0.9.3 reference, remap, and insertion transaction-seam audit

Status: **CP04 architecture-recovery audit**

Source evidence:

- branch: `feature/v0.9.3-safe-structural-transactions`
- repository commit: `0003657194cff25fd05df6753e9107b0e31a286d`
- production/test source snapshot: `323f31f1baa986d1a36f3300fc9fe6acc23a632f`
- released base: `6247529c9091b00a1a0305462a0c81a1ac099e48` (`v0.9.2`)
- snapshot reuse proof: the repository changes between the source snapshot and
  the CP04 baseline contain only
  `docs/v093_structural_pipeline_architecture.md`

This document audits the seams that v0.9.3 transaction design must use. It is
descriptive and advisory for CP05; it does not freeze a new public contract.
CP04 adds no transaction implementation, public export, schema, capability,
diagnostic, or filesystem behavior.

## 1. Direct answers

| CP04 question | Source-backed answer |
| --- | --- |
| Which layer owns old-index remap? | `mmd_registry/pmx/index_remap.py::PmxIndexRemap` is the sole complete old-index mapping authority. Its `targets[old_index]` maps to one final index or `None`; PMX field sentinel `-1` remains a separate concept. |
| Which layer owns new-to-new references? | The public DTO only names a request-local entity. The private service adapters and `PmxCoordinatedReferencePlan` own resolution from `new_id` to a planned final index. Target kernels receive resolved integer payloads. |
| What are the exact `PmxStructuralNewReference` semantics? | It is an immutable, request-local `(target_kind, new_id)` reference to an entity inserted by the same request. It is not a PMX index, transaction ID, persistent model ID, or cross-request reference. |
| Where do inserted entities receive final indices? | `plan_collection_reference_shift` derives `new_indices_in_request_order`; `plan_pmx_coordinated_insertion_references` then binds each declared `new_id` to the corresponding final index before any stage materializes records. |
| What ordering dependencies exist? | The current stage order is one deterministic topological order: `texture -> material -> bone -> vertex -> rigid_body -> morph`. Only some adjacent orderings are semantic; the exact dependency graph is recorded below. |
| Where does capacity preflight occur? | Generic declared-width and signed-32-bit count preflight occurs in `plan_collection_reference_shift`, and the coordinator invokes it for every changed collection against the original source. Target kernels additionally enforce reader and payload limits before their own materialization. |
| Which combinations work? | Multi-kind legacy delete/reorder, batched single-target insertion, and insertion across any two or more target families work subject to validation. A bounded cross-target new-reference matrix works in coordinated insertion. |
| Which combinations are unsupported? | Legacy delete/reorder mixed with any insertion, same-target new references, retargeting existing records to new entities, automatic width expansion, and multiple public requests treated as one atomic structural transaction are unsupported. |
| Can existing primitives compose without intermediate serialization? | Yes for insertion: the released coordinator composes immutable certified documents entirely in memory and the output layer serializes only the final intended document. The current APIs do not yet compose delete/reorder with insertion under one plan. |
| Where should transaction identity live? | CP05 should place a deterministic source-bound identity on one internal whole-transaction plan between public DTO translation and materialization. It must not live in `new_id`, a per-target payload, `PmxIndexRemap`, the writer, or process-global state. |
| What must remain internal? | Remaps, collection plans, final index assignments, coordinator payloads, target kernels, stage ordering, certificates, serializers, and publication hooks remain behind the service boundary. |

## 2. The three current index domains

The released insertion path separates three domains:

| Domain | Current representation | Authority |
| --- | --- | --- |
| Captured source index | Plain integer fields and `source_index` | The typed source document captured for preview or parsed from the execution byte snapshot |
| Request-local new identity | Insertion `new_id` and `PmxStructuralNewReference` | Public bounded DTO vocabulary; meaningful only inside one request |
| Final result index | `new_indices_in_request_order` and `PmxCoordinatedNewIdentity.final_index` | Internal deterministic planning evidence |

Integers in public insertion DTOs refer to the captured source domain. They do
not silently change meaning when another target collection is also inserted.
`PmxCoordinatedReferencePlan.resolve_source_reference` maps such integers
through the target collection shift and preserves `-1` only for fields that
explicitly allow that sentinel.

Callers do not provide final insertion indices. Final indices are derived from
source-domain positions and request order, then request-local references are
resolved to those indices.

## 3. Old-index mapping seam

`PmxIndexRemap` already has the mathematical shape required by a future
combined transaction:

- `targets` completely covers the old domain;
- a target is one final index or `None` for removal;
- `new_indices_without_old_source` owns final positions introduced without an
  old record;
- mapped and new-only indices must densely cover `range(new_size)` exactly
  once.

The current restriction is in the wrappers, not the base mapping:

| Wrapper | Authorized operations | Deliberate restriction |
| --- | --- | --- |
| `PmxCollectionTransform` | Keep, delete, reorder, no-op | Rejects every remap with new-only indices |
| `PmxCollectionReferenceShiftPlan` | Insertion into an otherwise preserved old collection | Its planner never removes or reorders old records |

Relationship modules consequently expose parallel transform and insertion
entry points, but both ultimately read `transform.remap` or `shift.remap`.
Transaction work must not introduce a second old-index map. A future internal
combined collection plan can carry one validated `PmxIndexRemap` plus insertion
placement evidence and adapt it to the established relationship owners.

`new_indices_without_old_source` is sorted final-range evidence. It does not
preserve caller order. `new_indices_in_request_order` is the separate placement
vector that binds each insertion ordinal to its derived final index.

## 4. Exact request-local new-reference semantics

`mmd_registry.services.structural_reference.PmxStructuralNewReference` is a
frozen, slotted DTO with two fields:

```text
target_kind: one of vertex, texture, material, bone, morph, rigid_body
new_id: 1..64 ASCII characters matching [A-Za-z][A-Za-z0-9_.-]{0,63}
```

Every optional insertion `new_id` uses the same bounded syntax. Within one
`PmxStructuralPreviewRequest`, non-`None` IDs are globally unique across all
six insertion families; uniqueness is by `new_id`, not by
`(target_kind, new_id)`.

Resolution is fail-closed:

1. the target-scoped DTO rejects a reference with the wrong target kind;
2. the request rejects duplicate declared IDs;
3. the coordinator plans every changed collection before resolution;
4. an unknown ID fails;
5. an ID declared for another target kind fails;
6. a successful lookup returns the planner-derived final index.

Forward declaration across request fields works because all identities are
planned before payloads are resolved. The textual order of target-family
fields does not decide dependency order.

The successful resolution path is owned by coordinated insertion, selected
only when at least two insertion target families are non-empty. Single-target
payload builders do not resolve `PmxStructuralNewReference`; a new reference
therefore cannot successfully name an undeclared entity or escape the same
request.

The DTO is public only from its explicit
`mmd_registry.services.structural_reference` submodule. It is intentionally not
exported from `mmd_registry`, `mmd_registry.pmx`, or the root
`mmd_registry.services` namespace. Public reports expose bounded counts and
resolved collection evidence, not raw request-local names.

## 5. Supported new-to-new reference matrix

| Inserted source record/field | May reference newly inserted target |
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

The following same-target edges remain integer source-domain fields and cannot
name new entities:

- inserted bone parent, tail, inherit-parent, IK target, and IK-link bone
  references;
- inserted group-morph and flip-morph references to morphs.

Textures have no structural target references. No current inserted target
accepts a new-morph reference. The supported new-to-new graph is therefore
acyclic by construction; the released code does not need a general dependency
cycle detector. If CP05 expands this vocabulary, it must define cycle behavior
explicitly rather than inheriting accidental stage recursion.

## 6. Current operation-combination matrix

| Combination | Current status | Boundary |
| --- | --- | --- |
| Empty structural request | Supported | Legacy no-op path returns a certified unchanged document |
| Delete/reorder one target collection | Supported | One `PmxStructuralCollectionEdit` translated to one `PmxCollectionTransform` |
| Delete/reorder multiple target collections | Supported | Unique kinds are sorted canonically and coordinated by `structural_orchestrator.py` |
| Multiple insertions in one target family | Supported | Same-anchor and append groups preserve tuple request order |
| One insertion target family | Supported | Routed directly to one target-specific kernel |
| Any subset of two through six insertion families | Supported | Routed through coordinated insertion, subject to payload, reference, capacity, version, and invariant validation |
| Source-domain reference from an inserted payload | Supported for explicit DTO fields | Mapped through a changed target shift or preserved when that target is unchanged |
| New-to-new cross-target reference | Supported only by the matrix in section 5 | Requires a declared globally unique `new_id` in the same coordinated request |
| Legacy delete/reorder plus any insertion | Rejected | `PmxStructuralPreviewRequest.__post_init__` rejects the mixed request |
| Same-target new-to-new bone or morph reference | Rejected by DTO type validation | No same-target dependency/cycle semantics exist |
| Change an existing source record to point at a new entity | Unsupported | No public structural DTO represents such a mutation |
| Chain multiple public requests as one transaction | Unsupported | Each request has a fresh source domain and each execution owns a separate publication boundary |
| Automatic PMX index-width expansion | Unsupported | Capacity fails closed under the declared header widths |

Legacy deletion remains reference-safe, not cascading: relationship owners
remove outbound references only when their owning source record is itself
removed by the same coordinated transform. A surviving record may not retain a
dangling reference to a deleted target, and no general repair policy is
invented.

## 7. Three distinct deterministic orderings

The source currently uses three orderings that must not be conflated.

### 7.1 Planning order

`PmxStructuralInsertionIntent` follows `PmxReferenceTargetKind` declaration
order:

```text
vertex, texture, material, bone, morph, rigid_body
```

This order stabilizes equality, hashing, shifts, and identity enumeration. It
is not the materialization dependency order.

### 7.2 Materialization order

`PmxCoordinatedInsertionPreview` uses:

```text
texture, material, bone, vertex, rigid_body, morph
```

This is a stable topological sort of the released dependency graph:

| Required edge | Why it is semantic |
| --- | --- |
| `texture -> material` | Inserted material texture fields are resolved to final texture indices and must be valid when the material is materialized. The texture kernel remaps only materials already present. |
| `bone -> vertex` | Inserted vertex deforms may point to new/final bone indices. The bone kernel remaps only vertices already present. |
| `bone -> rigid_body` | Inserted rigid bodies may point to new/final bone indices. The bone kernel remaps only rigid bodies already present. |
| `material -> morph` | Inserted material-morph offsets may use final material indices; the material kernel remaps only morphs already present. |
| `bone -> morph` | Inserted bone-morph offsets may use final bone indices; the bone kernel remaps only morphs already present. |
| `vertex -> morph` | Inserted vertex/UV morph offsets may use final vertex indices; the vertex kernel remaps only morphs already present. |
| `rigid_body -> morph` | Inserted impulse-morph offsets may use final rigid-body indices; the rigid-body kernel remaps only morphs already present. |

Orders such as material before bone and vertex before rigid body are stable
choices in the current implementation, not direct reference dependencies.
CP05 should freeze the dependency graph and a deterministic topological
tie-breaker, not merely copy an unexplained linear list.

### 7.3 Within-collection request order

For each target family, the insertion tuple is authoritative:

- before each old source index, insert every request anchored there in request
  order;
- then emit that old record;
- after the old domain, emit append requests in request order.

This rule assigns final indices before payload materialization.

## 8. Capacity-preflight seam

Current generic preflight is performed by
`plan_collection_reference_shift`:

1. validate each `insert_before` anchor against the captured source count;
2. calculate `current_count + insert_count`;
3. prove the declared target index width can address the result;
4. prove the PMX signed 32-bit section-count field can hold the result;
5. fail before allocating the complete old-domain mapping when impossible;
6. build the insertion-capable `PmxIndexRemap` only after success.

`plan_pmx_coordinated_insertion_references` invokes that planner for every
changed target collection against the original document before resolving any
new reference or running a target stage.

Each target kernel then repeats its own shift planning and adds narrower
preflight for reader limits and payload constraints, including applicable name
or path byte lengths, PMX version rules, float32 encodability, per-record
counts, and aggregate IK or morph-offset counts. Complete validation and the
reference graph remain the final certificate.

The coordinator therefore has whole-request generic width/count preflight, but
not one aggregate pass over every target-specific reader/payload limit before
the first in-memory stage. This is safe today because documents are immutable
and publication occurs only after all stages and final verification, but it is
a transaction-planning seam.

A combined delete/reorder/insertion planner cannot reuse the present capacity
formula unchanged. Its result count is:

```text
surviving_old_count + insert_count
```

CP05 must require all changed collections and target-specific aggregate limits
to be preflighted from one source-bound transaction plan before any
materialization. Declared index widths must remain unchanged unless a separate
future contract explicitly authorizes width migration.

## 9. Why delete/reorder plus insertion is not yet composable

Although `PmxIndexRemap` can represent removed, reordered, and new-only final
positions together, no current planner defines the combined semantics.
Important unresolved cases are:

- whether `insert_before(source_index)` follows the named source record after
  a reorder or denotes its original source slot;
- what happens when the insertion anchor is deleted;
- whether append means the end of the final reordered collection;
- how insertions at several anchors interleave with an explicit
  `old_indices_in_new_order` sequence;
- when deletion of a referenced target rejects the transaction versus removal
  of the owning source record;
- how a new entity references a source entity that the same transaction
  deletes;
- how final indices and missing-reference diagnostics are computed before any
  section changes.

`PmxCollectionTransform` cannot carry insertion payloads and rejects new-only
indices. `PmxCollectionReferenceShiftPlan` assumes every old record survives
in source order. Sequentially invoking the existing public operations would
change the meaning of source-domain integers and create multiple certification
or publication boundaries. It is not a valid transaction implementation.

## 10. In-memory composition and certification

The released coordinator proves that target primitives can compose without
intermediate serialization:

1. all shifts and request-local identities are planned from the original typed
   document;
2. service adapters resolve supported references to final integers;
3. target-specific preview kernels consume and return immutable typed
   documents;
4. each stage currently performs a complete invariant certificate;
5. one final independent certificate covers the coordinated result;
6. execution serializes that final intended document once, reparses it once,
   certifies it again, compares whole-document equality, then publishes once.

The per-stage certificates and repeated per-target shift planning are safe but
redundant seams. A future implementation can initially reuse them for the
smallest risk. Any later optimization that exposes pure materializers must keep
one authoritative preflighted plan and a mandatory complete final certificate;
it cannot weaken the output reparse/equality/publication gates.

## 11. Placement of whole-transaction identity

The code already has several distinct identifiers that must remain distinct:

| Value | Meaning |
| --- | --- |
| `new_id` | Request-local symbolic name for one inserted entity |
| Preview `intent_sha256` | Route-specific hash of current canonical preview payload evidence |
| Source SHA-256 | Identity of execution input bytes used for race protection and reporting |
| Output SHA-256 | Identity of verified serialized output bytes |

None is automatically the v0.9.3 whole-transaction identity.

The source-backed placement recommendation for CP05 is one immutable internal
whole-transaction plan created at the service/orchestration seam:

```text
public bounded transaction DTO
  -> validation and canonicalization against captured source
  -> internal source-bound transaction plan + deterministic identity
  -> reference resolution and materialization
  -> complete certificate
  -> existing verified output pipeline
```

That plan should own operation categories, one remap per changed target,
request-local identity bindings, dependency order, preflight evidence, and a
canonical digest. Preview and execution must derive the same plan semantics.

The identity must not be caller-selected, persisted into PMX bytes, stored in
mutable process-global state, or derived from destination paths. CP05 must
freeze the exact canonical inputs and decide whether the digest is public
evidence or remains internal; CP04 does not pre-authorize a schema field.

## 12. Public and internal boundary

### Existing public boundary that must remain compatible

- root service request/result and preview/execution functions;
- alias identity of `PmxStructuralEditRequest` and
  `PmxStructuralPreviewRequest`;
- `PmxReferenceTargetKind` and released reference-analysis types;
- insertion DTOs and `PmxStructuralNewReference` in their explicit service
  submodules;
- released capability fields and values.

### Implementation details that must remain internal

- `PmxIndexRemap`, collection transforms, insertion intents, shift plans, and
  capacity-analysis objects;
- coordinated collection specs, identity bindings, reference plan, resolved
  payloads, and stage previews;
- target-specific insertion payloads, materializers, remap adapters, and stage
  order;
- invariant certificate construction and intermediate reference graphs;
- structural serialization result types and private output transaction entry
  points;
- source/destination identity checks, temporary-file mechanics, and atomic
  publication hooks.

If CP05 introduces public transaction DTOs, they should use an explicit service
submodule and bounded semantic fields. Raw remaps, caller-selected final
indices, serializers, writer results, and filesystem hooks must not become a
parallel public mutation authority.

## 13. Decisions reserved for CP05

CP04 establishes the evidence but does not freeze these contract choices:

1. exact transaction terminology and public request shape;
2. operation categories and whether the existing request remains the
   compatibility facade;
3. combined delete/reorder/insertion anchor semantics;
4. exact request-local identity and reference vocabulary;
5. dependency graph, deterministic topological tie-breaker, and cycle policy;
6. duplicate, missing, wrong-target, and reference-to-deleted behavior;
7. whole-transaction capacity and target-specific preflight contract;
8. transaction identity digest inputs and reporting boundary;
9. intermediate versus final certification requirements;
10. capability, diagnostic, preview schema, and execution-stage changes, if
    any.

## 14. CP04 conclusion

The released architecture already contains the necessary mathematical remap,
request-local identity resolution, in-memory target composition, complete
certification, and single-publication safety foundations.

The missing seam is one source-bound whole-transaction plan that combines
delete/reorder/insertion semantics, owns one remap per target, resolves all
source/new references once, preflights the complete transaction, and drives a
deterministic dependency order. CP05 must specify that contract before any
production implementation begins.
