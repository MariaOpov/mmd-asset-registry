# Texture Insertion Preview

Status: **CP07 preview-only gate** for v0.9.2.

This checkpoint adds the first target-specific structural insertion preview while
preserving the released v0.9.1 structural execution boundary. Texture is first
because an inserted texture record is only one declared PMX path string and does
not carry PMX index references of its own.

## Public request boundary

The only public structural authorities remain:

- `mmd_registry.services.preview_structural_edit(...)`
- `mmd_registry.services.apply_structural_edit(...)`

`PmxStructuralEditRequest is PmxStructuralPreviewRequest` remains true.

CP07 adds one bounded public DTO from a dedicated additive submodule:

- `mmd_registry.services.structural_texture.PmxStructuralTextureInsertion(path, position="append", source_index=None)`

The released root `mmd_registry.services.__all__` tuple remains unchanged. The
service root imports this DTO only through a private alias for request validation,
so the exact pre-existing canonical service surface is preserved.

and one additive default-empty request field:

- `PmxStructuralPreviewRequest(..., texture_insertions=())`

Existing v0.9.1 callers that supply only `collection_edits` retain their previous
constructor and behavior.

The position vocabulary is exactly:

- `append`
- `insert_before` with one plain nonnegative source-domain `source_index`

`bool`, negative indices, missing `insert_before` anchors, unexpected position
strings, and `append` requests carrying an anchor are refused.

CP07 deliberately refuses any request that mixes `texture_insertions` with legacy
`collection_edits`. Cross-operation composition is deferred rather than guessed.

## Internal translation

The public DTO is translated at the service boundary into:

- `PmxStructuralInsertPosition`
- `PmxTextureInsertionPayload`
- `PmxCollectionInsertionIntent`
- `PmxCollectionReferenceShiftPlan`

The CP05/CP06 insertion planning classes remain internal and are not re-exported by
`mmd_registry.services` or `mmd_registry.pmx`. The only CP07 public type addition is
owned by `mmd_registry.services.structural_texture`; it is not added to the frozen
root `mmd_registry.services.__all__`.

`PmxCollectionTransform` remains delete/reorder/no-op only. CP07 does not weaken its
guard against `new_indices_without_old_source` and does not encode inserted payloads
inside a legacy transform.

## Texture payload validation

The inserted record is one exact path string. CP07 reuses the established
`validate_portable_texture_path(...)` policy:

- empty paths are refused;
- NUL is refused;
- absolute/rooted/drive-qualified paths are refused;
- parent-directory (`..`) components are refused;
- accepted text is not normalized or rewritten;
- no filesystem lookup is performed.

The path must also encode strictly using the source PMX text encoding.

The encoded byte length must not exceed `MAX_PMX_TEXTURE_PATH_BYTES`, preserving the
existing bounded texture-reader contract.

## Capacity gates

Two independent capacity gates apply before texture-path materialization:

1. the resulting texture count must be representable by the source PMX texture
   index width through the CP03/CP06 capacity and shift planner;
2. the resulting texture count must not exceed `MAX_PMX_TEXTURE_COUNT`, because a
   preview must not claim a future result that the existing bounded parser would
   refuse to reparse.

No 1->2 or 2->4 byte index-width expansion is attempted.

The tighter texture-reader count bound is checked before reference-shift remap
allocation.

## Ordering and materialization

CP06 source-domain ordering remains authoritative.

For each old texture source index in ascending order:

1. emit every insertion anchored before that source record in request order;
2. emit the old texture path at its CP06 remapped index.

After the old source domain, emit appends in request order.

`PmxCollectionReferenceShiftPlan.new_indices_in_request_order` is the authoritative
association between insertion request ordinals and final texture indices.

Materialization fills a dense resulting texture tuple from:

- old texture path -> `PmxIndexRemap.targets`;
- insertion request -> `new_indices_in_request_order`.

Any duplicate or unfilled slot is treated as an internal invariant failure.

## Existing material texture references

The existing CP11 relationship owner remains authoritative for:

- material main texture -> texture;
- material sphere texture -> texture;
- material individual toon texture -> texture.

CP07 refactors that owner around one shared `PmxIndexRemap` kernel while preserving
the released legacy `PmxCollectionTransform` entry point.

A new internal insertion adapter accepts only a
`PmxCollectionReferenceShiftPlan` whose target kind is `texture`.

Existing `-1` sentinels remain outside the remap domain. Shared toon references are
not texture-table references and remain unchanged.

No second relationship taxonomy is introduced.

## Preview certification

Texture insertion is materialized immutably into a new intended `PmxDocument`.
The source document is not modified.

The intended document must obtain the existing
`PmxStructuralInvariantCertificate`, which keeps:

- `validate_pmx_document(...)` as the PMX validity authority;
- the existing frozen reference graph as the relationship authority;
- empty trailing-data requirements;
- declared index-width validation;
- text encodability validation;
- reference-diagnostic fail-closed behavior.

Successful CP07 evidence uses `preview_schema_version = 2` so the new
insertion-audit shape is not misrepresented as the released legacy schema version
1. Legacy previews remain on their existing schema.

Successful insertion evidence remains an in-memory dry run with:

- `status = "changes_pending"`;
- `written = false`;
- `serialization = "not_performed"`;
- deterministic intent SHA-256;
- capacity/reference-shift evidence;
- insertion request ordinal -> final index evidence;
- SHA-256 fingerprints of inserted paths rather than raw path text in the preview
  evidence payload;
- direct source-graph impact evidence for old texture nodes whose indices shift.

## Execution gate

CP07 does **not** authorize insertion execution.

A request with non-empty `texture_insertions` passed to
`apply_structural_edit(...)` fails at the service-validation boundary before the
lazy structural output writer is imported or source/destination I/O begins.

Legacy v0.9.1 structural execution without `texture_insertions` remains unchanged.

CP08 owns the separate execution gate.

## Capability boundary

CP07 does not add or imply `structural_insert=True`.

The capability manifest continues to advertise the already-reviewed v0.9.1
structural preview/write contract. Texture insertion may be described only as a
preview-only target-specific gate until later capability promotion.

## Explicit non-goals

CP07 does not authorize:

- texture insertion file output;
- automatic index-width expansion;
- raw PMX section objects or raw bytes;
- serializer or filesystem hooks;
- mixed legacy structural edits plus texture insertions;
- material, bone, morph, rigid-body, or vertex insertion;
- new-to-new references;
- CLI insertion commands;
- capability promotion;
- GUI work;
- source mutation;
- silent repair.

## Exit gate

CP07 may close only after:

- targeted texture insertion preview tests pass;
- legacy texture remap tests pass;
- structural preview/service regressions pass;
- v0.9.1 structural execution regressions pass;
- Ruff and compileall pass;
- the full unit suite passes;
- staged source review confirms no execution path or capability promotion was
  introduced.
