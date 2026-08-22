# CP14 Rigid-Body Insertion

CP14 adds bounded semantic PMX rigid-body insertion to the existing v0.9.2
structural preview/execution authority.

Public mutation authority remains:

```python
preview_structural_edit(...)
apply_structural_edit(...)
```

`PmxStructuralEditRequest is PmxStructuralPreviewRequest` remains unchanged.
The root service export surface and capability manifest are not promoted.

## Public semantic DTO

Rigid-body insertion DTOs live in:

```python
mmd_registry.services.structural_rigid_body
```

`PmxStructuralRigidBodyInsertion` accepts semantic fields rather than a raw
`PmxRigidBody`:

- source-domain `bone_index` or `-1`;
- collision group `0..15`;
- unsigned 16-bit collision mask;
- shape: `sphere`, `box`, or `capsule`;
- size, body position, and rotation vectors;
- mass, linear/angular damping, restitution, and friction;
- physics mode: `bone_follow`, `physics`, or
  `physics_with_bone_alignment`;
- `append` or source-domain `insert_before` placement.

The name `body_position` is used for the PMX physics position because
`position` is reserved for collection placement.

## Source-domain outgoing reference

An inserted rigid body's `bone_index` refers only to the captured source bone
collection. `-1` preserves the PMX no-bone sentinel.

CP14 does not permit a new rigid body to refer to a newly inserted bone.

## Incoming rigid-body reference shifts

Adding a rigid body can shift existing source rigid-body indices. CP14 rewrites
all existing incoming owners through one certified shift plan:

- PMX 2.1 impulse morph offset -> rigid body;
- joint rigid-body A -> rigid body;
- joint rigid-body B -> rigid body;
- PMX 2.1 soft-body anchor -> rigid body.

Joint A/B preserve `-1`. Impulse and soft-body anchor references are required
and never gain a sentinel.

No owner is inferred from resulting numeric indices.

## CP14 impulse morph extension

CP14 also enables semantic morph type `impulse` in the existing
`mmd_registry.services.structural_morph` DTO surface.

An impulse offset contains:

```text
rigid_body_index
local
velocity[3]
angular_torque[3]
```

The rigid-body index is a required source-domain reference. Impulse insertion
requires PMX 2.1.

A morph insertion request and a rigid-body insertion request cannot be combined
in one structural request. Therefore:

```text
new impulse morph -> existing source rigid body    allowed
new impulse morph -> newly inserted rigid body     refused / CP17
```

Cross-target coordinated insertion remains CP17-owned.

## PMX version rules

Rigid bodies exist in PMX 2.0 and PMX 2.1.

- rigid-body insertion is supported for 2.0 and 2.1;
- impulse morph insertion requires 2.1;
- soft-body anchor rewriting applies only to 2.1;
- a PMX 2.0 document containing soft bodies is invalid and fails closed;
- existing joint types that require 2.1 remain subject to whole-document
  validation.

CP14 does not repair invalid source version/section combinations.

## Exact binary32 semantics

Every rigid-body value written by PMX as float32 is canonicalized before the
intended document is certified:

- size x/y/z;
- body position x/y/z;
- rotation x/y/z;
- mass;
- linear damping;
- angular damping;
- restitution;
- friction.

Impulse velocity and angular torque are likewise canonicalized to exact PMX
binary32.

Input values must be finite and representable as finite binary32. Size and the
five physics scalars must remain nonnegative.

There is no epsilon comparison, clamping, rotation normalization, or silent
numeric repair.

## Parser and capacity bounds

The existing reader safety bound remains authoritative:

```text
MAX_PMX_RIGID_BODY_COUNT = 200000
```

Rigid-body indices use the source header's signed width: 1, 2, or 4 bytes.
The shared structural capacity model must certify the resulting collection.

Automatic index-width widening is not authorized.

## Ordering

Insertion positions reuse the shared structural insertion vocabulary:

```text
append
insert_before(source_index)
```

Anchors are source-domain indices. Multiple requests at one anchor preserve
caller order, as do appended requests. Source rigid-body records are not
deleted or reordered.

## Preview and execution

The conceptual CP14 pipeline is:

```text
semantic rigid-body DTO
    -> private payload
    -> parser/range/float32 validation
    -> rigid-body capacity + reference-shift plan
    -> incoming reference remap
    -> materialize inserted rigid bodies
    -> whole-document/reference certificate
    -> shared structural-output transaction
    -> serialize
    -> reparse
    -> independent certificate
    -> exact semantic equality
    -> source identity/SHA reverify
    -> atomic publication
```

Preview performs no filesystem write. Execution reuses the same private shared
transaction authority used by prior insertion targets.

## Failure behavior

Any validation, capacity, reference, serialization, reparse, independent
certification, semantic comparison, source-race, destination-race, or atomic
publication failure fails closed.

The source is never mutated in place. A failed operation must not publish a
partial output or leave temporary residue.

## Non-goals

CP14 does not authorize:

- physics simulation or automatic physics generation;
- joint insertion;
- soft-body insertion;
- coordinated bone + rigid-body insertion;
- coordinated morph + rigid-body insertion;
- new-to-new cross-section references;
- automatic PMX index-width expansion;
- a raw public `PmxRigidBody` mutation request;
- a parallel public writer or CLI mutation authority;
- in-place source mutation;
- capability promotion.
