# v0.9.3 structural pipeline architecture rediscovery

Status: **CP03 recovered architecture map**

Source snapshot:

- branch: `feature/v0.9.3-safe-structural-transactions`
- commit: `323f31f1baa986d1a36f3300fc9fe6acc23a632f`
- released base: `6247529c9091b00a1a0305462a0c81a1ac099e48` (`v0.9.2`)

This document records the transaction-relevant architecture that exists in the
source tree before v0.9.3 transaction design begins. It is descriptive, not a
new public contract. Historical checkpoint labels in older module docstrings
refer to the releases that introduced those modules; they do not rename the
current v0.9.3 CP03 checkpoint.

CP03 adds no transaction implementation, public export, schema, capability,
diagnostic, or filesystem behavior.

## 1. Recovered authority map

| Concern | Current authority | Responsibility and boundary |
| --- | --- | --- |
| Public structural service | `mmd_registry/services/__init__.py` | Owns `preview_structural_edit`, `apply_structural_edit`, request/result wrappers, route selection, public-to-internal DTO conversion, bounded execution provenance, and the v0.9.1 request alias. |
| Public insertion DTOs | `mmd_registry/services/structural_*.py` | Own typed request vocabulary in explicit submodule namespaces. These DTOs do not mutate documents or write files. |
| Request-local new reference DTO | `mmd_registry/services/structural_reference.py` | Owns `PmxStructuralNewReference(target_kind, new_id)` and the bounded `new_id` vocabulary. It is not re-exported from the root service namespace. |
| Legacy collection edit translation | `_build_structural_preview_intent` in `mmd_registry/services/__init__.py` | Converts public keep/delete/reorder requests into `PmxIndexRemap`, `PmxCollectionTransform`, and `PmxStructuralTransformIntent`. |
| Old-index mapping | `mmd_registry/pmx/index_remap.py` | Sole complete old-index to new-index-or-removed mapping. `None` means removed; `-1` remains a PMX field sentinel. |
| Legacy collection-transform intent | `mmd_registry/pmx/collection_transform.py` | Owns keep/delete/reorder/no-op intent and deliberately rejects new-only positions. |
| Insertion position intent | `mmd_registry/pmx/structural_insert_intent.py` | Owns source-domain `append` and `insert_before(source_index)` position semantics. It does not own payloads or final indices. |
| Capacity preflight | `mmd_registry/pmx/structural_capacity.py` | Proves result counts fit the declared index width and signed 32-bit section-count limit. It never expands widths. |
| Insertion shift plan | `mmd_registry/pmx/structural_reference_shift.py` | Builds an insertion-capable `PmxIndexRemap` and assigns final insertion indices while preserving request order. |
| Coordinated source/new reference resolution | `mmd_registry/pmx/structural_coordinated_insertion.py` plus private service adapters | Plans all changed target collections against the captured source domain, resolves request-local IDs to final indices, and coordinates existing insertion kernels. |
| Target-specific insertion kernels | `mmd_registry/pmx/structural_{texture,material,bone,morph,rigid_body,vertex}_insertion.py` | Validate payloads, preflight capacity, materialize one target collection, remap that target's dependent references, and produce a certified in-memory preview. No filesystem publication occurs here. |
| Legacy coordinated document transform | `mmd_registry/pmx/structural_orchestrator.py` | Applies keep/delete/reorder transforms across the complete document in dependency-safe order. It does not serialize or publish. |
| Relationship remap kernels | `bone_reference_remap.py`, `geometry_material_remap.py`, `morph_display_remap.py`, `physics_reference_remap.py` | Each relationship family has one remap owner. These modules operate on typed records and receive an already-validated transform or shift plan. |
| Reference identity and graph | `reference_model.py` and `reference_graph.py` | Own six globally indexed target kinds, concrete source identities, the 27-relationship extraction taxonomy, invalid-target evidence, and unsupported-state evidence. |
| Reference diagnostics and queries | `reference_diagnostics.py` and `reference_queries.py` | Convert graph evidence into stable diagnostics and read-only impact queries. They do not mutate or repair. |
| Whole-document invariant certificate | `mmd_registry/pmx/structural_invariants.py` | Runs the existing PMX validator, derives a fresh reference graph, requires zero reference diagnostics, and binds the certificate to the exact document. |
| Structural preview evidence | `mmd_registry/pmx/structural_preview.py` and target insertion preview classes | Exposes deterministic in-memory audit evidence only after invariant certification. No serialization or I/O occurs. |
| PMX byte serialization | `mmd_registry/pmx/writer.py::serialize_pmx` | Existing deterministic writer authority. It validates the complete document before emitting bytes. |
| Structural serialization and output transaction | `mmd_registry/pmx/structural_output.py` | Converges every legacy/single-target/coordinated path through preview, serialize, reparse, independent certification, semantic equality, and verified output commit. |
| Filesystem safety and publication | private hooks in `mmd_registry/pmx/editing/output.py` | Existing shared authority for path resolution, alias/race checks, source re-verification, same-directory temporary files, atomic publication, and cleanup. |
| Capability reporting | `mmd_registry/capabilities.py` | Preserves the released v0.9.2 dimensions and appends the released v0.9.3 transaction capability with a legacy-safe default. |

## 2. Public boundary and route selection

The root package continues to export only `__version__`. The reusable mutation
boundary is `mmd_registry.services`:

- `PmxStructuralPreviewRequest` is the public request type;
- `PmxStructuralEditRequest` is the same class by identity;
- `preview_structural_edit(document, request)` is the public in-memory entry;
- `apply_structural_edit(input_path, output_path, request, overwrite=False)` is
  the public filesystem entry;
- `PmxStructuralPreviewResult` and `PmxStructuralExecutionResult` hide internal
  preview and writer-result types.

Insertion DTOs remain public only in their explicit service submodules. Raw
`mmd_registry.pmx.structural_*` kernels and insertion transaction helpers are
implementation details and are not parallel public mutation authorities.

The service selects exactly one current route:

1. More than one non-empty insertion target family selects coordinated
   insertion.
2. Exactly one insertion family selects its target-specific insertion kernel.
3. No insertion family selects the legacy collection-transform route.

`PmxStructuralPreviewRequest` rejects every combination of legacy
`collection_edits` with insertion fields. Therefore the current public service
does not compose deletion/reorder and insertion in one request.

## 3. Preview call chains

### 3.1 Legacy keep/delete/reorder preview

```text
preview_structural_edit
  -> _build_structural_preview_intent
  -> PmxIndexRemap
  -> PmxCollectionTransform
  -> PmxStructuralTransformIntent
  -> preview_pmx_structural_transform
  -> transform_and_certify_pmx_document
  -> transform_pmx_document
  -> relationship remap kernels
  -> validate_pmx_document
  -> extract_pmx_reference_graph
  -> diagnose_reference_graph == ()
  -> PmxStructuralPreviewResult
```

`PmxCollectionTransform` accepts only mappings backed by old records. It
rejects `new_indices_without_old_source`, keeping legacy collection transforms
separate from insertion semantics.

### 3.2 Single-target insertion preview

```text
preview_structural_edit
  -> service DTO-to-payload adapter
  -> target preview_pmx_*_insertions
  -> PmxCollectionInsertionIntent
  -> plan_collection_reference_shift
  -> analyze_structural_capacity
  -> insertion-capable PmxIndexRemap
  -> target materialization + dependent-reference remap
  -> PmxStructuralInvariantCertificate
  -> PmxStructuralPreviewResult
```

Each insertion kernel owns one target collection and delegates dependent edges
to the existing relationship remap modules. It does not serialize bytes, touch
paths, or publish output.

### 3.3 Coordinated multi-target insertion preview

The service first builds collection specs in canonical target-kind order. The
coordinator plans every shift against the original source counts before any
section mutation, assigns final indices to request-local `new_id` values, then
resolves supported source-domain and new-entity references.

The current certified materialization order is:

```text
texture -> material -> bone -> vertex -> rigid_body -> morph
```

Each stage consumes the previous certified document. A final independent
`PmxStructuralInvariantCertificate` covers the complete coordinated result.
This stage order is an implementation dependency recovered from source, not a
new v0.9.3 transaction-order decision.

## 4. Mapping domains

Three domains are currently explicit:

| Domain | Representation | Meaning |
| --- | --- | --- |
| Captured source index | Public integer DTO fields and `source_index` | Refers to a record in the original document snapshot. |
| Request-local new identity | `PmxStructuralNewReference` plus insertion `new_id` | Names an entity created by the same public request without exposing a caller-chosen final PMX index. |
| Final result index | `PmxCollectionReferenceShiftPlan.new_indices_in_request_order` and `PmxCoordinatedNewIdentity.final_index` | Deterministically derived after capacity and position planning. |

`PmxIndexRemap.targets[old_index]` remains the old-to-final mapping authority.
For insertion, `new_indices_without_old_source` completes the dense final
range, while `new_indices_in_request_order` records the placement of each new
payload. Neither legacy collection transforms nor public DTOs accept a final
index as an insertion identity language.

Request-local `new_id` values are globally unique across the current public
request. Fields typed to accept `PmxStructuralNewReference` are resolved in the
service/coordinator boundary. Same-target bone links and group/flip morph
indices remain integer source-domain fields in the released DTOs. The exact
future transaction reference vocabulary is reserved for CP04/CP05.

## 5. Relationship ownership by inserted target

| Inserted target | Collection materialization owner | Existing relationships shifted by the target kernel |
| --- | --- | --- |
| `texture` | `structural_texture_insertion.py` | Material texture, sphere-texture, and texture-mode toon references. |
| `material` | `structural_material_insertion.py` | Material-morph references and soft-body material references. Inserted materials are zero-surface and the surface index stream remains unchanged. |
| `bone` | `structural_bone_insertion.py` | Vertex deform references; existing bone parent/tail/inherit/IK references; bone-morph references; display-frame bone references; rigid-body bone references. |
| `morph` | `structural_morph_insertion.py` | Existing group/flip morph references and display-frame morph references. |
| `rigid_body` | `structural_rigid_body_insertion.py` | Impulse-morph, joint, and soft-body anchor rigid-body references. |
| `vertex` | `structural_vertex_insertion.py` | Surface indices, vertex/UV morph references, and soft-body anchor/pin vertex references. |

The legacy `structural_orchestrator.py` coordinates the same ownership families
for deletion/reorder. Its ordering ensures that a relationship is translated
from the original old-index domain exactly once. Notable rules include moving
material-owned surface spans before vertex remap, removing source records
before rewriting their outbound references, and passing surviving morphs to
rigid-body remap.

## 6. Reference and invariant certification

`PmxReferenceTargetKind` defines the six globally index-addressable targets:

```text
vertex, texture, material, bone, morph, rigid_body
```

`extract_pmx_reference_graph` owns deterministic extraction for the frozen
27-relationship taxonomy across surface indices, vertices, materials, bones,
morphs, display frames, rigid bodies, joints, and soft bodies. It intentionally
does not require a valid document first, allowing invalid-target and
unsupported-state evidence to be reported.

`PmxStructuralInvariantCertificate` is stricter and is the common success gate:

1. require empty `trailing_data`;
2. run the existing complete `validate_pmx_document` authority;
3. derive a fresh reference graph from the exact document;
4. require `diagnose_reference_graph(graph)` to be empty;
5. retain the derived graph as immutable certificate evidence.

The validator remains authoritative for PMX semantic validity, declared index
width capacity, version rules, text/float encodability, section counts, and
cross-section bounds. The graph is an independent reference-consistency check,
not a competing validator.

## 7. Execution, serialization, and semantic equality

All filesystem execution routes converge on
`_write_verified_structural_transaction` in `structural_output.py`:

```text
apply_structural_edit
  -> path resolution
  -> source identity + byte snapshot
  -> source parse
  -> request/intent resolution against that snapshot
  -> certified preview
  -> serialize_pmx(intended_document)
  -> load_pmx(serialized_bytes)
  -> independent PmxStructuralInvariantCertificate(reparsed_document)
  -> reparsed_document == intended_document
  -> commit verified bytes
  -> PmxStructuralExecutionResult
```

`serialize_pmx` validates before emitting deterministic bytes. Structural
execution uses it directly and does not use the generic `write_pmx` convenience
function. Publication occurs only after reparse, independent certification,
and whole-document semantic equality pass.

The execution service records this bounded stage vocabulary:

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

These stages feed redacted public failure provenance; they do not expose raw
exception representations or private inserted payload values.

## 8. Safe publication and race checks

`structural_output.py` deliberately reuses private hooks from the mature v0.8
edit-output kernel rather than duplicating filesystem logic:

- `_resolve_edit_paths` validates PMX extensions, resolves the source and
  destination parent, refuses in-place output, symlink destinations, hardlink
  aliases, unsafe existing outputs, and missing/non-directory parents;
- `_file_identity` captures filesystem identity before source bytes are read;
- `_commit_verified_bytes` writes a temporary file in the destination
  directory, flushes and `fsync`s it, verifies its SHA-256, re-verifies source
  path identity and content hash, and performs a second destination-state
  validation immediately before publication;
- overwrite uses atomic replacement of a separate destination;
- no-clobber uses an atomic platform-specific publish primitive and refuses an
  unsafe non-atomic fallback;
- every failure path cleans its own temporary file;
- a successful `PmxStructuralWriteResult` can be constructed only after
  publication succeeds.

Therefore source/destination race protection and atomic publication are shared
authorities. Transaction work must compose with this kernel and must not create
a second path-safety implementation.

## 9. Capability and DTO boundaries

The released capability manifest reports:

```text
structural_preview = True
structural_write = True
structural_insert = True
structural_transaction = True
structural_contract = "reference_safe_execution"
```

The six structural target kinds are derived from `PmxReferenceTargetKind`.
CP03 did not add or authorize a transaction capability. CP27 resolves that
reserved decision after the transaction contract, safety, compatibility,
private-runtime, and installed-wheel gates: the canonical manifest now reports
`structural_transaction=True`. The new field is trailing and defaults to
`False` for legacy direct construction. No existing capability is reinterpreted
and no transaction API is promoted to an older root namespace.

The public insertion vocabulary remains split by explicit submodule:

- `services.structural_reference` — request-local new reference;
- `services.structural_texture` — texture insertion;
- `services.structural_material` — material insertion;
- `services.structural_bone` — bone and IK insertion DTOs;
- `services.structural_morph` — morph and offset insertion DTOs;
- `services.structural_rigid_body` — rigid-body insertion;
- `services.structural_vertex` — vertex and deform insertion DTOs.

No DTO vocabulary is promoted to `mmd_registry`, `mmd_registry.pmx`, or the
root `mmd_registry.services` namespace by this checkpoint.

## 10. Recovered invariants for later transaction work

The current source establishes these non-negotiable composition constraints:

1. Preview and execution must derive the same intended typed document.
2. Public requests describe captured-source positions and request-local IDs,
   never caller-selected final indices.
3. `PmxIndexRemap` remains the old-index mapping authority.
4. A relationship has exactly one remap owner.
5. Declared PMX index widths are preflighted and never silently expanded.
6. Unknown `trailing_data` fails closed for structural certification.
7. The source document is immutable; execution reparses a captured byte
   snapshot and re-verifies the source before publication.
8. Serialization success alone is insufficient; reparse, independent
   certification, and whole-document equality are required.
9. In-place output and partial publication remain forbidden.
10. Raw structural kernels, serializer helpers, and publication hooks remain
    internal behind the public service boundary.

## 11. Transaction seams reserved for CP04

CP03 recovers the current architecture but does not decide the future
transaction design. CP04 must audit the seams exposed by this map, including:

- whether old-index remap and request-local new-reference resolution can be
  composed without a second mapping authority;
- where one whole-transaction identity should live;
- which current fixed insertion-stage dependencies are semantic requirements;
- which same-target and cross-target new-reference combinations are currently
  unsupported;
- how final indices should be assigned when deletion/reorder and insertion are
  eventually composed;
- whether target-specific previews can compose without redundant intermediate
  certification while preserving the common final certificate;
- which private helpers can be reused and which must remain internal;
- where whole-transaction capacity preflight must occur before any transform.

No answer in this section is pre-authorized by CP03. The real source and its
released compatibility boundary remain the evidence base for CP04 and CP05.

## 12. CP03 conclusion

The repository already has mature, reusable authorities for remap,
target-specific insertion, reference analysis, complete invariant
certification, deterministic serialization, semantic equality, source race
checks, destination safety, atomic publication, and bounded public diagnostics.

The released v0.9.3 transaction layer adds orchestration and contract semantics
around these authorities without replacing or duplicating them.
