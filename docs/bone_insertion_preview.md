# Bone insertion preview — v0.9.2 CP11

## Scope

CP11 adds **preview-only semantic insertion of PMX bone records** through the
existing public structural preview authority:

```python
preview_structural_edit(...)
```

It does not serialize output, mutate a source file, add a public writer, resize
PMX index widths, or promote the `structural_insert` capability.

The canonical public request DTOs are:

```python
from mmd_registry.services.structural_bone import (
    PmxStructuralBoneIkLink,
    PmxStructuralBoneIk,
    PmxStructuralBoneInsertion,
)
```

They are intentionally not re-exported from the root `mmd_registry.services`
surface.

## Semantic DTO instead of raw PMX flags

The public insertion DTO does not accept raw `PmxBone`, `PmxIk`, `PmxIkLink`,
`flags`, `flag_names`, or `tail_mode` values. The request uses semantic fields
and the internal insertion layer derives the PMX flag word.

Supported semantic flag inputs are:

- `rotatable`;
- `translatable`;
- `visible`;
- `enabled`;
- `local_append`;
- `after_physics`;
- `inherit_rotation`;
- `inherit_translation`;
- optional fixed axis;
- optional local axes;
- optional external parent key;
- optional IK;
- tail representation selected by the mutually exclusive tail payload.

This keeps the public request bounded and prevents arbitrary flag/payload
combinations from bypassing PMX invariants.

## Tail representation

Exactly one tail representation must be present:

```text
tail_offset != None and tail_bone_index == None
    -> offset-tail mode

tail_offset == None and tail_bone_index != None
    -> bone-index tail mode
```

Both-present and both-absent requests fail closed.

A bone-index tail reference is source-domain and may use the PMX `-1` sentinel.

## Inheritance and optional payload pairing

`inherit_parent_bone_index` and `inherit_weight` are required when either
inheritance semantic flag is enabled. They are forbidden when neither
inheritance flag is enabled.

`local_axis_x` and `local_axis_z` must either both be present or both be absent.

An external-parent flag is derived only when `external_parent_key` is present.

An IK flag is derived only when a typed `PmxStructuralBoneIk` payload is present.

## IK contract

IK target and IK link bone references are required source-domain references.
They do not accept the `-1` sentinel.

Each IK link either supplies both lower and upper angle-limit vectors or neither.
The internal PMX `angle_limits_enabled` field is derived from that pairing.

The reader safety limits remain authoritative:

```text
MAX_PMX_IK_LOOP_COUNT       = 1,000,000
MAX_PMX_IK_LINK_COUNT       = 100,000
MAX_PMX_TOTAL_IK_LINK_COUNT = 1,000,000
```

The cumulative limit includes existing source IK links plus all requested
inserted IK links.

## Source-domain bone references

Every outgoing reference carried by an inserted bone is interpreted in the
source bone domain:

- `parent_bone_index`;
- indexed tail reference;
- inherit-parent reference;
- IK target;
- IK links.

Optional parent/tail/inherit references may use `-1`.

For an insertion before source bone `0`, a request reference to source bone `1`
is remapped to the resulting index assigned to that original source bone.

References to result-only inserted indices are not implicitly authorized.
**New-bone -> new-bone references are refused in CP11.**

## Existing incoming reference owners

CP11 does not duplicate the established reference-owner logic. Additive
insertion adapters are kept in the existing owner modules:

```text
bone_reference_remap.py
    vertex deform -> bone
    existing bone parent -> bone
    active existing bone tail -> bone
    active existing bone inherit parent -> bone
    existing IK target/link -> bone

morph_display_remap.py
    bone morph -> bone
    display-frame bone element -> bone

physics_reference_remap.py
    rigid body -> bone
```

The adapters consume `PmxCollectionReferenceShiftPlan` directly. They do not
construct or weaken `PmxCollectionTransform`.

## Reference semantics

Existing optional relationships preserve `-1`:

- vertex deform -> bone;
- bone parent -> bone;
- active bone tail -> bone;
- active bone inherit parent -> bone;
- rigid body -> bone.

Existing required relationships are shifted as required indices:

- IK target -> bone;
- IK links -> bone;
- bone morph -> bone;
- display-frame bone element -> bone.

Every old source bone is shifted exactly once according to CP06 reference-shift
evidence.

## Float32 representation contract

Bone and IK numeric payloads stored by PMX are validated for finite binary32
representability **before the CP06 planner runs**:

- bone position;
- offset tail;
- inherit weight;
- fixed axis;
- local X/Z axes;
- IK angle limit;
- IK link lower/upper vectors.

Valid request values are materialized as the exact value produced by:

```text
struct.pack("<f", value)
    ↓
struct.unpack("<f", bytes)
```

This is PMX format canonicalization, not clamping, normalization, vector repair,
or approximate comparison. Finite Python floats that cannot be represented by
PMX binary32 fail closed.

This contract prepares CP12 execution to retain exact:

```python
reparsed_document == intended_document
```

without weakening semantic verification.

## Text, integer, reader, and index bounds

Bone names are validated in the source PMX text encoding and must remain within:

```text
MAX_PMX_NAME_BYTES = 64 KiB
```

The resulting section must remain within:

```text
MAX_PMX_BONE_COUNT = 200,000
```

`transform_layer` and `external_parent_key` must fit signed 32-bit PMX fields.

The CP03/CP06 capacity model remains authoritative for the current bone index
width. CP11 refuses insertion requiring automatic `1 -> 2` or `2 -> 4` index
width expansion.

## Preview pipeline

```text
typed public bone DTO
    ↓
internal semantic payload
    ↓
shape / flag-payload pairing validation
    ↓
text + int32 + parser limits
    ↓
source-domain outgoing reference validation
    ↓
finite PMX float32 validation
    ↓
CP03 / CP06 capacity and reference-shift plan
    ↓
existing vertex deform reference shift
    ↓
existing bone self/IK reference shift
    ↓
existing bone morph/display reference shift
    ↓
existing rigid-body bone reference shift
    ↓
materialize inserted semantic PmxBone records
    ↓
assemble intended immutable PmxDocument
    ↓
PmxStructuralInvariantCertificate
    ↓
reference graph certification
    ↓
deterministic privacy-bounded preview evidence
```

No writer or filesystem transaction participates in CP11.

## Request composition

The shared request gains:

```python
bone_insertions: tuple[PmxStructuralBoneInsertion, ...] = ()
```

CP11 refuses bone insertion combined with:

- legacy collection delete/reorder edits;
- texture insertion;
- material insertion.

Cross-target coordinated insertion remains deferred.

The alias remains:

```python
PmxStructuralEditRequest is PmxStructuralPreviewRequest
```

## Execution boundary

`apply_structural_edit(...)` explicitly refuses any request containing
`bone_insertions` before importing or invoking the structural output transaction.

Bone insertion execution belongs to CP12.

Existing CP08 texture insertion execution, CP10 material insertion execution,
and v0.9.1 legacy structural execution remain unchanged.

## Privacy and deterministic evidence

Preview reports emit insertion positions, resulting indices, counts, reference
impact summaries, and SHA-256 payload evidence.

Raw inserted bone names, vectors, IK values, and other request payload text are
not emitted in the public audit report.

The same source document and request must produce the same intended document and
the same preview evidence.

## Capability policy

CP11 keeps:

```text
structural_preview = True
structural_write   = True
structural_insert  = absent
```

Capability promotion remains deferred to CP24.

## Non-goals

CP11 does not authorize:

- bone insertion execution;
- new-bone -> new-bone references;
- raw PMX flag words or raw section records;
- automatic bone-index width expansion;
- mixed texture/material/bone insertion;
- legacy bone reorder/delete plus bone insertion in one request;
- approximate numeric comparison;
- silent repair or vector normalization;
- in-place mutation;
- CLI insertion commands;
- GUI, Smart Tools, plugins, model generation, or physics generation.

## Required regression evidence

Before commit, CP11 must cover:

- public DTO immutability and type safety;
- semantic flag derivation;
- tail representation exclusivity;
- inheritance and local-axis pairing;
- IK reference and angle-limit pairing;
- source-domain outgoing references;
- new-to-new refusal;
- same-anchor and append request order;
- vertex BDEF/SDEF/QDEF reference shifts;
- existing bone parent/tail/inherit/IK shifts;
- bone morph shifts;
- display-frame bone shifts;
- rigid-body bone shifts;
- optional `-1` preservation;
- name, section-count, IK-count, int32, and index-width bounds;
- PMX float32 canonicalization and overflow refusal before planning;
- deterministic privacy-bounded preview evidence;
- source immutability and no filesystem output;
- execution refusal before output creation;
- CP07–CP10 insertion regressions;
- v0.9.1 bone structural regression;
- complete repository suite, Ruff, and compileall.
