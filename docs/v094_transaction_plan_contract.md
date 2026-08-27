# v0.9.4 Structural Transaction-Plan Contract

This document freezes the authoring schema and namespace decisions for
`v0.9.4 — Declarative Structural Transaction Authoring`.

It is an authoring adapter contract. It does not create a second PMX transaction
interpreter, remapper, serializer, writer, or publication path.

## Schema identity

The user-authored structural transaction-plan schema is the integer `1`.

This schema is independent from:

- registry schema `0.3` with supported registry schemas `0.2` and `0.3`;
- the existing declarative PMX edit-plan schema `1`;
- the internal v0.9.3 evidence marker
  `mmd_registry.structural_transaction.plan.v1`.

The numeric equality with the legacy edit-plan schema is coincidental. The two
schemas have different namespaces, loaders, operation vocabularies, and typed
models.

## Top-level JSON envelope

An executable transaction plan has exactly these allowed top-level members:

```json
{
  "schema_version": 1,
  "expected_source_sha256": "optional-lowercase-64-hex",
  "operations": []
}
```

`schema_version` and `operations` are required.
`expected_source_sha256` is optional.

Unknown members are rejected. Duplicate JSON members are rejected. The
`operations` array is ordered and order is semantically significant.

Resource limits such as maximum input bytes and maximum operation count are
hardening policy to be frozen by CP14; adding such bounds does not add JSON
members or operation authority.

## Top-level operation discriminator

Every operation is a JSON object with required string member `op`.

The schema-one operation vocabulary, in authoritative order, is exactly:

1. `transform_collection`
2. `insert_texture`
3. `insert_material`
4. `insert_bone`
5. `insert_morph`
6. `insert_rigid_body`
7. `insert_vertex`

No arbitrary Python module, class, function, callback, writer, hook, remap,
final-index, publication, or filesystem implementation name is authorable.

### `transform_collection`

Maps directly to `PmxStructuralCollectionEdit`.

Allowed members:

- `op`
- `target_kind`
- `old_indices_in_new_order`

`target_kind` is one of `vertex`, `texture`, `material`, `bone`, `morph`,
`rigid_body`.

`old_indices_in_new_order` is an array of unique nonnegative source-domain
integers. Its ordering represents reorder. Omitting source indices represents
deletion. The authoring layer does not calculate a remap or final index.

Only one collection transform for a target kind is allowed in one transaction
request, matching the released v0.9.3 request authority.

### `insert_texture`

Maps directly to `PmxStructuralTextureInsertion`.

Allowed payload members mirror the DTO constructor:

- `path` — required string
- `position` — optional `append` or `insert_before`, default `append`
- `source_index` — optional source-domain integer; required only for
  `insert_before` and forbidden for `append`
- `new_id` — optional request-local string identity

### `insert_material`

Maps directly to `PmxStructuralMaterialInsertion`.

Allowed payload members, in constructor order:

- `local_name` — required
- `universal_name`
- `memo`
- `texture_index`
- `sphere_texture_index`
- `sphere_mode`
- `toon_reference_mode`
- `toon_reference_index`
- `diffuse`
- `specular`
- `specular_strength`
- `ambient`
- `drawing_flags`
- `edge_color`
- `edge_scale`
- `position`
- `source_index`
- `new_id`

The three texture reference fields accept an existing integer reference or the
schema-one new-reference object where the reviewed DTO permits it.
`sphere_mode` is an integer from 0 through 3.
`toon_reference_mode` is `texture` or `shared`.
A shared toon index is an integer from 0 through 9.
`drawing_flags` is an unsigned one-byte integer.

Vector lengths and finite-float requirements are inherited exactly from the
released DTO.

### `insert_bone`

Maps directly to `PmxStructuralBoneInsertion`.

Allowed payload members, in constructor order:

- `local_name` — required
- `universal_name`
- `bone_position`
- `parent_bone_index`
- `transform_layer`
- `rotatable`
- `translatable`
- `visible`
- `enabled`
- `local_append`
- `after_physics`
- `tail_offset`
- `tail_bone_index`
- `inherit_rotation`
- `inherit_translation`
- `inherit_parent_bone_index`
- `inherit_weight`
- `fixed_axis`
- `local_axis_x`
- `local_axis_z`
- `external_parent_key`
- `ik`
- `position`
- `source_index`
- `new_id`

Bone parent, tail, inherit, and IK references are captured-source integer
references in schema one. They do not accept request-local new bone references.
This preserves the v0.9.4 non-goal forbidding unreviewed same-target new
references.

Exactly one of `tail_offset` and `tail_bone_index` is present semantically.
Inheritance payload is only valid when an inherit flag is active.
Local X/Z axes are either both present or both absent.

The optional `ik` object has allowed members:

- `target_bone_index` — required nonnegative captured-source integer
- `loop_count`
- `angle_limit`
- `links`

Each IK link object has:

- `bone_index` — required nonnegative captured-source integer
- `lower_limit`
- `upper_limit`

IK lower/upper limits are either both present or both absent.

### `insert_morph`

Maps directly to `PmxStructuralMorphInsertion`.

Allowed payload members:

- `local_name` — required
- `morph_type` — required
- `universal_name`
- `panel`
- `offsets`
- `position`
- `source_index`
- `new_id`

`morph_type` is exactly one of:

`group`, `vertex`, `bone`, `uv`, `additional_uv_1`, `additional_uv_2`,
`additional_uv_3`, `additional_uv_4`, `material`, `flip`, `impulse`.

`panel` is exactly one of:

`system`, `eyebrow`, `eye`, `mouth`, `other`.

Every offset is an object with required discriminator `type`.
The offset discriminator vocabulary is exactly:

- `group`
- `vertex`
- `bone`
- `uv`
- `material`
- `flip`
- `impulse`

The selected offset type must match `morph_type` as required by the released DTO.
`additional_uv_1` through `additional_uv_4` use the `uv` offset shape.

Offset fields mirror the released DTOs:

- group: `morph_index`, `weight`
- vertex: `vertex_index`, `translation`
- bone: `bone_index`, `translation`, `rotation`
- uv: `vertex_index`, `uv_offset`
- material: `material_index`, `operation`, `diffuse`, `specular`,
  `specular_strength`, `ambient`, `edge_color`, `edge_scale`, `texture_tint`,
  `sphere_tint`, `toon_tint`
- flip: `morph_index`, `weight`
- impulse: `rigid_body_index`, `local`, `velocity`, `angular_torque`

`material.operation` is `multiply` or `add`.

Reviewed cross-target fields may use a schema-one new-reference object.
Group and flip `morph_index` remain captured-source integers and do not authorize
same-target new morph references.

### `insert_rigid_body`

Maps directly to `PmxStructuralRigidBodyInsertion`.

Allowed payload members, in constructor order:

- `local_name` — required
- `universal_name`
- `bone_index`
- `collision_group`
- `collision_mask`
- `shape`
- `size`
- `body_position`
- `rotation`
- `mass`
- `linear_damping`
- `angular_damping`
- `restitution`
- `friction`
- `physics_mode`
- `position`
- `source_index`
- `new_id`

`bone_index` accepts an existing integer reference or a new-reference targeting
`bone`.

`collision_group` is 0 through 15.
`collision_mask` is 0 through 65535.
`shape` is `sphere`, `box`, or `capsule`.
`physics_mode` is `bone_follow`, `physics`, or
`physics_with_bone_alignment`.

### `insert_vertex`

Maps directly to `PmxStructuralVertexInsertion`.

Allowed payload members:

- `vertex_position` — required
- `normal` — required
- `uv` — required
- `additional_uvs` — required
- `deform` — required
- `edge_scale` — required
- `position`
- `source_index`
- `new_id`

`additional_uvs` contains at most four four-float vectors.

`deform` is an object with required discriminator `type`.
The schema-one deform vocabulary is exactly:

- `bdef1`
- `bdef2`
- `bdef4`
- `sdef`
- `qdef`

Deform payload members mirror the released DTO:

- bdef1: `bone_index`
- bdef2: `bone_indices`, `bone_1_weight`
- bdef4: `bone_indices`, `weights`
- sdef: `bone_indices`, `bone_1_weight`, `c`, `r0`, `r1`
- qdef: `bone_indices`, `weights`

Reviewed vertex deform bone-reference fields accept existing integer references
or new-reference objects targeting `bone`.

## Request-local new-reference JSON

A request-local new reference is represented only as:

```json
{
  "ref": "new",
  "target_kind": "bone",
  "new_id": "example-id"
}
```

Allowed members are exactly `ref`, `target_kind`, and `new_id`.
`ref` must equal `new`.

`target_kind` is one of `vertex`, `texture`, `material`, `bone`, `morph`,
`rigid_body`.

A new reference resolves only to one matching insertion with the same target kind
and globally unique `new_id`, under the existing v0.9.3 transaction authority.

The object never contains a final index. The loader never accepts module names,
class names, resolver callbacks, or remap payloads.

## JSON type discipline

The strict loader must preserve JSON type identity:

- strings are not coerced;
- integers require an exact JSON integer and reject booleans;
- booleans require an exact JSON boolean;
- float fields require an exact finite JSON floating-point value and do not
  coerce integers;
- fixed vectors are JSON arrays of the exact reviewed length;
- tuple fields are authored as JSON arrays and become immutable tuples only in
  the typed model/DTO boundary;
- NaN and Infinity are rejected;
- duplicate object members are rejected;
- unknown fields are rejected deterministically.

DTO runtime validation remains authoritative for domain-specific bounds and
cross-field invariants. The authoring loader may reject earlier, but must not
widen the DTO's accepted semantic domain.

## Public namespace ownership

The Phase-B authoring core is owned by the intentional namespace:

`mmd_registry.pmx.transaction_plan`

It is not promoted to `mmd_registry`, `mmd_registry.pmx`, or the legacy
`mmd_registry.services` root.

The first core names reserved by this contract are:

- `PMX_STRUCTURAL_TRANSACTION_PLAN_SCHEMA_VERSION`
- `PmxStructuralTransactionPlan`

Later CP06–CP14 authoring helpers may be added only additively within the same
namespace and explicit `__all__`.

CP15 may introduce a separate reviewed service namespace. CP04 does not promote
transaction-plan execution into the legacy service root.

## Authority boundary

A loaded plan may construct only the seven released transaction operation DTO
families and then exactly one `PmxStructuralTransactionRequest`.

Preview delegates to
`mmd_registry.services.structural_transaction.preview_structural_transaction`.

Apply delegates to
`mmd_registry.services.structural_transaction.apply_structural_transaction`.

The authoring layer must never:

- calculate or accept PMX remap objects;
- calculate or accept final indices;
- call a raw structural writer as its execution authority;
- accept writer/publication callbacks or hooks;
- reinterpret operations differently between preview and apply;
- perform in-place output;
- weaken source identity, destination race, serialization/reparse,
  certification, canonical semantic equality, or atomic publication checks.

## Deferred policy that does not change schema authority

The following are deliberately deferred to later checkpoints:

- CP12 canonical renderer default-field omission policy and formatting details;
- CP13 catalog/template/explanation presentation;
- CP14 maximum input bytes, maximum operation count, maximum string/list bounds,
  and expected-source binding workflow;
- CP15 service-level diagnostics and stable authoring service result types;
- CP23 capability promotion decision.

Those checkpoints may harden or present this contract but may not add operation
authority or new schema-one JSON member classes without reopening CP04.
