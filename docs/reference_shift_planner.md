# Reference Shift Planner

Status: internal planning foundation for v0.9.2.

This layer turns one source-domain collection insertion intent into deterministic
old-to-new index shift evidence. It does not materialize PMX payloads and does not
enable structural insertion through the public service API.

## Authority boundary

`PmxIndexRemap` remains the sole old-index to new-index identity authority.

The planner does **not** construct or weaken `PmxCollectionTransform`.
`PmxCollectionTransform` remains the legacy delete/reorder/no-op model and keeps
its guard rejecting `new_indices_without_old_source`.

Relationship-specific remap owners remain authoritative for their existing PMX
relationships. Later target-specific insertion checkpoints may adapt those owners
to consume insertion shift evidence without creating a second reference taxonomy.

## Input

`plan_collection_reference_shift(...)` consumes:

- one immutable `PmxCollectionInsertionIntent`;
- the captured source collection count;
- the already-declared PMX index width.

The insertion intent has already frozen target kind and source-domain positions.

## Ordering algorithm

For each old source index in ascending source order:

1. emit every `insert_before(old_index)` request anchored there, preserving request
   order among requests with the same anchor;
2. emit the surviving old record.

After the complete source domain, emit all `append` requests in their original
request order.

Different source anchors therefore obtain their physical order from the captured
source domain, not from a progressively mutated collection and not from arbitrary
caller sorting.

Example:

- old source indices: `0, 1, 2, 3`;
- requests, in request order:
  - insert before `2`;
  - insert before `0`;
  - insert before `2`;
  - append.

The resulting sequence positions are:

- request 1 at new index `0`;
- old 0 at `1`;
- old 1 at `2`;
- request 0 at `3`;
- request 2 at `4`;
- old 2 at `5`;
- old 3 at `6`;
- request 3 at `7`.

Therefore:

- remap targets: `(1, 2, 5, 6)`;
- sorted `new_indices_without_old_source`: `(0, 3, 4, 7)`;
- insertion placements in original request order: `(3, 0, 4, 7)`.

## Why request-order placement evidence is separate

`PmxIndexRemap.new_indices_without_old_source` must be strictly increasing. That is
the correct canonical representation for dense-range validation, but it does not
say which later payload corresponds to which insertion request.

`PmxCollectionReferenceShiftPlan.new_indices_in_request_order` preserves that
association. It is not a second old-index mapping authority. It only answers where
each insertion request will be materialized later.

Payload DTOs remain out of scope for this checkpoint.

## Capacity integration

Capacity is analyzed before remap allocation using the existing internal
`analyze_structural_capacity(...)` function.

A successful plan carries immutable `PmxStructuralCapacityAnalysis` evidence.

Planning fails closed when:

- the resulting collection cannot be addressed by the already-declared index width;
- the resulting count exceeds the independent signed 32-bit PMX section-count
  limit.

Automatic 1->2 or 2->4 byte index-width expansion is not performed.

Capacity rejection occurs before constructing the old-domain mapping, so obvious
count impossibilities do not trigger huge remap allocation.

## Dense coverage invariants

For every successful plan:

- every old source record survives;
- `len(remap.targets) == current_count`;
- `remap.new_size == current_count + insert_count`;
- every old index maps to exactly one new index;
- every inserted position appears in
  `remap.new_indices_without_old_source`;
- mapped and new-only positions densely cover `range(remap.new_size)` exactly once;
- `new_indices_without_old_source` is strictly increasing;
- sorting `new_indices_in_request_order` yields exactly
  `new_indices_without_old_source`;
- `remap.targets` must exactly match the source-domain insertion shift implied by
  the insertion positions;
- direct construction of a shift plan revalidates source-domain anchors and rejects
  semantically inconsistent remap evidence.

The existing `PmxIndexRemap` constructor remains the final validator of
mapping-shape invariants. `PmxCollectionReferenceShiftPlan` additionally validates
that those shapes represent the frozen insertion semantics.

## Scope exclusions

This planner does not:

- accept or materialize inserted PMX records;
- rewrite any relationship field;
- construct a `PmxDocument`;
- mutate a source document;
- serialize or write files;
- resize index widths;
- create a public insertion operation;
- change `preview_structural_edit(...)`;
- change `apply_structural_edit(...)`;
- change the shared public request alias;
- promote `structural_insert=True`.

The next target-specific insertion preview checkpoint may use this shift evidence
to place bounded payloads and to route surviving-old reference updates through the
existing relationship ownership model.
