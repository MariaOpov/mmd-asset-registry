# Material insertion preview — v0.9.2 CP09

## Scope

CP09 adds **preview-only structural insertion of PMX material records** through the
existing public structural service. It does not add a second mutation authority,
does not serialize or publish output, and does not enable material insertion
execution.

The public mutation authorities remain:

- `preview_structural_edit(...)`
- `apply_structural_edit(...)`

The canonical public DTO import is:

```python
from mmd_registry.services.structural_material import (
    PmxStructuralMaterialInsertion,
)
```

`mmd_registry.services.__all__` remains the frozen v0.9.1-compatible root surface.

## Zero-surface insertion contract

A CP09 inserted material always materializes with:

```text
surface_index_count = 0
```

The caller cannot provide `surface_index_count`.

PMX materials partition the ordered surface-index stream by contiguous
`surface_index_count` segments. Inserting a material with a non-zero count without
simultaneously changing that stream would silently transfer triangle ownership
from an existing material. CP09 therefore leaves:

```text
document.geometry.surface_indices
```

unchanged.

Coordinated material + surface/geometry insertion is intentionally deferred to a
later cross-section checkpoint.

## Public payload

`PmxStructuralMaterialInsertion` is a frozen, slots-based bounded DTO. It carries:

- local/universal names and memo;
- existing source-domain texture, sphere-texture, and individual-toon references;
- sphere/toon modes;
- diffuse/specular/ambient/edge visual properties;
- drawing flags;
- `append` or `insert_before(source_index)` placement.

It is not a raw `PmxMaterial` section object and exposes no bytes, hooks, callbacks,
or arbitrary payload.

## Text and parser bounds

Preview validates inserted text against the source PMX encoding without
normalization or repair.

The existing reader safety limits remain authoritative:

- material result count: `MAX_PMX_MATERIAL_COUNT`;
- local/universal material names: `MAX_PMX_NAME_BYTES`;
- material memo: `MAX_PMX_MATERIAL_MEMO_BYTES`.

The result count must also fit the already-declared PMX material index width.
Automatic index-width expansion remains forbidden.

## Texture-reference domain

CP09 does not allow material insertion to be combined with texture insertion.

Therefore inserted material references are interpreted only in the existing source
texture domain:

```text
texture_index
sphere_texture_index
toon_reference_index when toon_reference_mode == "texture"
```

Each must be `-1` or identify an existing source texture. Shared toon references
remain in the PMX shared-toon domain `0..9`.

No implicit new-material -> new-texture linkage is authorized.

## Incoming material references

Material insertion shifts old material indices. Existing incoming references are
rewritten exactly once through their established relationship owners:

- CP13 `morph_display_remap.py` owns material-morph -> material references;
- CP14 `physics_reference_remap.py` owns soft-body -> material references.

Each owner receives the CP06 `PmxCollectionReferenceShiftPlan` through an
insertion-specific adapter. The legacy `PmxCollectionTransform` insertion guard is
not weakened.

The `-1` sentinel is preserved.

## Preview pipeline

```text
public typed DTO
      ↓
internal bounded payload
      ↓
validate source encoding / parser bounds / texture references
      ↓
CP05 source-domain insertion positions
      ↓
CP06 capacity-checked material reference shift
      ↓
materialize immutable material collection
      ↓
CP13 rewrite morph -> material references
      ↓
CP14 rewrite soft-body -> material references
      ↓
assert surface stream unchanged
      ↓
PmxStructuralInvariantCertificate
      ↓
deterministic privacy-bounded preview evidence
```

Inserted payload strings are not emitted in the preview report. Audit entries use a
SHA-256 digest of canonical payload evidence plus the assigned new index.

## Request composition

CP09 deliberately refuses:

- material insertion + legacy collection edits;
- material insertion + texture insertion.

This preserves one unambiguous old-index domain and defers coordinated insertion
composition to the dedicated cross-section checkpoint.

## Execution boundary

`apply_structural_edit(...)` explicitly refuses any request containing
`material_insertions` before structural writer I/O.

Material insertion execution belongs to CP10.

Texture insertion execution from CP08 and legacy v0.9.1 structural execution remain
unchanged.

## Capability boundary

CP09 does not add or advertise a `structural_insert` capability. Capability
promotion remains deferred to the release capability checkpoint.

## Non-goals

CP09 does not provide:

- material insertion execution;
- material deletion/reorder changes beyond the existing legacy path;
- surface assignment or triangle ownership editing;
- texture insertion composition;
- automatic index-width resizing;
- in-place mutation;
- silent repair or normalization;
- CLI insertion commands;
- GUI/Smart Tools/plugin behavior;
- model generation or physics generation.
