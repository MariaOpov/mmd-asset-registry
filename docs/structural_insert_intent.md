# Structural Insert Intent Foundation

Status: internal planning foundation for v0.9.2.

This layer freezes the position vocabulary required by later structural insertion
planning without enabling a public insertion operation.

## Scope

`mmd_registry.pmx.structural_insert_intent` models only target kinds and source-domain
positions. It does not contain inserted PMX payloads and it does not mutate a
`PmxDocument`.

The internal vocabulary is:

- `PmxStructuralInsertPositionMode.APPEND`
- `PmxStructuralInsertPositionMode.INSERT_BEFORE`
- `PmxStructuralInsertPosition`
- `PmxCollectionInsertionIntent`
- `PmxStructuralInsertionIntent`

These names are intentionally not re-exported through `mmd_registry.pmx` or
`mmd_registry.services`.

## Source-domain position semantics

`append` means insertion after the complete captured source collection.

`insert_before(source_index)` means insertion immediately before one existing
record in the captured source index domain.

For `insert_before`:

- `source_index` is a plain nonnegative `int`;
- `bool` is rejected;
- `source_index < current_count` is required;
- empty source collections therefore support append only;
- `insert_before(current_count)` is refused rather than normalized to append.

Position tuples retain caller order. Multiple insertions at one source anchor and
multiple appends therefore remain deterministic.

## Separation from legacy transforms

`PmxCollectionTransform` remains delete/reorder/no-op only. Its guard rejecting
`new_indices_without_old_source` is not removed or weakened.

`PmxIndexRemap` remains the later old-to-new shift authority, but this foundation
does not construct an insertion-capable remap yet. That belongs to the reference
shift planner.

Inserted payloads are never stored in `PmxIndexRemap` or in this position-intent
module.

## Public compatibility

The existing public service authorities remain unchanged:

- `preview_structural_edit(...)`
- `apply_structural_edit(...)`

`PmxStructuralEditRequest is PmxStructuralPreviewRequest` remains true, and legacy
`PmxStructuralPreviewRequest(collection_edits=())` callers remain valid.

This foundation is not attached to the public request yet because target-specific,
bounded payload DTOs have not been introduced. Attaching an incomplete
position-only insertion request would create mutation meaning without a record to
materialize.

Later target-specific preview work may add default-empty public insertion fields
while preserving the shared preview/execution request type.

## Safety boundary

This module accepts no:

- raw PMX section objects;
- raw bytes;
- callables;
- writer/serializer hooks;
- filesystem hooks;
- raw `PmxIndexRemap`;
- raw `PmxCollectionTransform`;
- arbitrary payload objects.

Capacity analysis remains internal and mandatory before execution. The reference
shift planner will combine source counts, declared index widths, insertion counts,
and these source-domain positions without automatic index-width expansion.

No insertion capability is promoted by this foundation.
