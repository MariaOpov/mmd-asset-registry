# PMX Reference Taxonomy - v0.9.0 foundation

Status: **Checkpoint 03 specification freeze**

This document is the reviewed reference inventory that later v0.9.0 graph and
remap checkpoints must implement. It describes the repository's current typed
PMX document and validator behavior; it does **not** add a public mutation API.

## 1. Scope and terminology

A **reference edge** is an active integer field whose value names one record in
one of the six globally index-addressable PMX target collections below.

An allowed `-1` value is a **sentinel/no-edge state**, not an edge to an entity
and not a synonym for "target removed by remap".

A flag/type/version-controlled field is an edge only while its controlling
condition makes that field active. Inactive alternative payloads are not edges.

The graph is not assumed to be a DAG. Bone, IK, group-morph and flip-morph
relationships may create cycles or self-reference unless another validator rule
explicitly rejects a particular value.

## 2. Globally index-addressable target collections

`PmxIndexSizes` defines exactly six global index widths. These are the target
collection identities used by the v0.9.0 reference model.

| target id | document collection | index width | writer signedness |
| --- | --- | --- | --- |
| vertex | PmxDocument.vertices | header.index_sizes.vertex | unsigned |
| texture | PmxDocument.texture_paths | header.index_sizes.texture | signed |
| material | PmxDocument.materials | header.index_sizes.material | signed |
| bone | PmxDocument.bones | header.index_sizes.bone | signed |
| morph | PmxDocument.morphs | header.index_sizes.morph | signed |
| rigid_body | PmxDocument.rigid_bodies | header.index_sizes.rigid_body | signed |

Vertex indices are the only globally indexed target written unsigned. Texture,
material, bone, morph and rigid-body indices use signed index encoding so their
supported fields can represent sentinels where allowed.

The following collections are ordered/countable but are **not** globally
index-addressable targets in the current typed PMX model:

| collection | document field | reason |
| --- | --- | --- |
| surface_indices | PmxDocument.surface_indices | ordered index stream; values target vertices but positions are not a globally indexed PMX target collection |
| display_frames | PmxDocument.display_frames | ordered/countable records but no supported PMX field targets a display-frame index |
| joints | PmxDocument.joints | ordered/countable records but no supported PMX field targets a joint index |
| soft_bodies | PmxDocument.soft_bodies | ordered/countable PMX 2.1 records but no supported PMX field targets a soft-body index |

## 3. Complete supported reference inventory

The canonical relationship IDs below are specification identities for v0.9.0.
They are not yet a production public API.

| relationship id | source section | stable source path | target | requirement | sentinel | active condition | nested repeated | current diagnostic context | remap owner |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `surface.vertex` | surface_indices | `surface_indices[*]` | vertex | required | none | always | yes | surface_indices / record_index=surface position / field=vertex_index | CP11 |
| `vertex.deform.bdef1.bone` | vertices | `vertices[*].deform.bone_index` | bone | optional | -1 | deform_type == 0 (BDEF1) | no | vertices / record_index=vertex / field=deform.bone_indices[0] | CP12 |
| `vertex.deform.multi.bone` | vertices | `vertices[*].deform.bone_indices[*]` | bone | optional | -1 | deform_type in {1,2,3,4}; QDEF type 4 requires PMX 2.1 | yes | vertices / record_index=vertex / field=deform.bone_indices[n] | CP12 |
| `material.texture` | materials | `materials[*].texture_index` | texture | optional | -1 | always | no | materials / record_index=material / field=texture_index | CP11 |
| `material.sphere_texture` | materials | `materials[*].sphere_texture_index` | texture | optional | -1 | always | no | materials / record_index=material / field=sphere_texture_index | CP11 |
| `material.toon_texture` | materials | `materials[*].toon_reference_index` | texture | optional | -1 | toon_reference_mode == 'texture' | no | materials / record_index=material / field=toon_reference_index | CP11 |
| `bone.parent` | bones | `bones[*].parent_bone_index` | bone | optional | -1 | always | no | bones / record_index=bone / field=parent_bone_index | CP12 |
| `bone.tail` | bones | `bones[*].tail_bone_index` | bone | optional | -1 | PMX_BONE_FLAG_TAIL_INDEX enabled; otherwise tail_offset is active and this is not an edge | no | bones / record_index=bone / field=tail_bone_index | CP12 |
| `bone.inherit_parent` | bones | `bones[*].inherit_parent_bone_index` | bone | optional | -1 | inherit-rotation or inherit-translation flag enabled | no | bones / record_index=bone / field=inherit_parent_bone_index | CP12 |
| `bone.ik_target` | bones | `bones[*].ik.target_bone_index` | bone | required | none | PMX_BONE_FLAG_IK enabled | no | bones / record_index=bone / field=ik.target_bone_index | CP12 |
| `bone.ik_link` | bones | `bones[*].ik.links[*].bone_index` | bone | required | none | PMX_BONE_FLAG_IK enabled | yes | bones / record_index=bone / field=ik.links[n].bone_index | CP12 |
| `morph.group.morph` | morphs | `morphs[*].offsets[*].morph_index` | morph | required | none | morph_type == 0 (group) | yes | morphs / record_index=morph / field=offsets[n] | CP13 |
| `morph.vertex.vertex` | morphs | `morphs[*].offsets[*].vertex_index` | vertex | required | none | morph_type == 1 (vertex) | yes | morphs / record_index=morph / field=offsets[n] | CP13 |
| `morph.bone.bone` | morphs | `morphs[*].offsets[*].bone_index` | bone | required | none | morph_type == 2 (bone) | yes | morphs / record_index=morph / field=offsets[n] | CP13 |
| `morph.uv.vertex` | morphs | `morphs[*].offsets[*].vertex_index` | vertex | required | none | morph_type in {3,4,5,6,7}; types 4-7 require the corresponding additional-UV layer | yes | morphs / record_index=morph / field=offsets[n] | CP13 |
| `morph.material.material` | morphs | `morphs[*].offsets[*].material_index` | material | optional | -1 | morph_type == 8 (material) | yes | morphs / record_index=morph / field=offsets[n] | CP13 |
| `morph.flip.morph` | morphs | `morphs[*].offsets[*].morph_index` | morph | required | none | morph_type == 9 (flip), PMX 2.1 only | yes | morphs / record_index=morph / field=offsets[n] | CP13 |
| `morph.impulse.rigid_body` | morphs | `morphs[*].offsets[*].rigid_body_index` | rigid_body | required | none | morph_type == 10 (impulse), PMX 2.1 only | yes | morphs / record_index=morph / field=offsets[n] | CP14 |
| `display_frame.bone` | display_frames | `display_frames[*].elements[*].target_index` | bone | required | none | element.target_type == 'bone' | yes | display_frames / record_index=frame / field=elements[n].target_index | CP13 |
| `display_frame.morph` | display_frames | `display_frames[*].elements[*].target_index` | morph | required | none | element.target_type == 'morph' | yes | display_frames / record_index=frame / field=elements[n].target_index | CP13 |
| `rigid_body.bone` | rigid_bodies | `rigid_bodies[*].bone_index` | bone | optional | -1 | always | no | rigid_bodies / record_index=rigid body / field=bone_index | CP14 |
| `joint.rigid_body_a` | joints | `joints[*].rigid_body_a_index` | rigid_body | optional | -1 | always; non-zero joint_type itself requires PMX 2.1 | no | joints / record_index=joint / field=rigid_body_a_index | CP14 |
| `joint.rigid_body_b` | joints | `joints[*].rigid_body_b_index` | rigid_body | optional | -1 | always; non-zero joint_type itself requires PMX 2.1 | no | joints / record_index=joint / field=rigid_body_b_index | CP14 |
| `soft_body.material` | soft_bodies | `soft_bodies[*].material_index` | material | optional | -1 | soft-body section, PMX 2.1 only | no | soft_bodies / record_index=soft body / field=material_index | CP14 |
| `soft_body.anchor.rigid_body` | soft_bodies | `soft_bodies[*].anchors[*].rigid_body_index` | rigid_body | required | none | soft-body section, PMX 2.1 only | yes | soft_bodies / record_index=soft body / field=anchors[n].rigid_body_index | CP14 |
| `soft_body.anchor.vertex` | soft_bodies | `soft_bodies[*].anchors[*].vertex_index` | vertex | required | none | soft-body section, PMX 2.1 only | yes | soft_bodies / record_index=soft body / field=anchors[n].vertex_index | CP14 |
| `soft_body.pin.vertex` | soft_bodies | `soft_bodies[*].pinned_vertex_indices[*]` | vertex | required | none | soft-body section, PMX 2.1 only | yes | soft_bodies / record_index=soft body / field=pinned_vertex_indices[n] | CP14 |

### Material-morph sentinel note

The repository validator explicitly accepts `-1` for
`PmxMaterialMorphOffset.material_index`. This taxonomy therefore classifies
`-1` as a sentinel/no-edge state. The repository does not encode a stronger
domain label for that sentinel, so CP03 deliberately does not invent one.

## 4. Values that look index-like but are not reference edges

### Shared toon slots

When `PmxMaterial.toon_reference_mode == "shared"`,
`toon_reference_index` is the shared toon slot `0..9`; it is **not** a
`texture_paths` index and must never be remapped as a texture edge.

When the mode is `"texture"`, the same stored field is the
`material.toon_texture` relationship from the table and allows `-1`.

### Material surface partition

`PmxMaterial.surface_index_count` is a count, not an index reference. However,
the ordered material list partitions the flat `surface_indices` stream into
contiguous ownership spans. The validator requires the sum of all material
surface counts to equal the surface-index count and each material count to be
divisible by three.

Therefore CP11 must treat material order and each material's contiguous surface
span as one structural coupling. Reordering materials without moving the
corresponding surface spans would silently change material-to-triangle
ownership. Deleting a material cannot silently discard or reassign its span.

### Other non-reference integers

Header index widths, section counts, bone transform layers, bone external-parent
keys, physics group/mask values, joint types, soft-body numeric configuration
and similar scalar integers are not edges merely because they are integers.

## 5. Sentinel and removed-target policy

The current validator allows `-1` only on the relationships marked `-1` above.

For v0.9.0 structural work:

1. Existing `-1` remains a sentinel/no-edge state and is not passed through an
   old-index -> new-index map.
2. A valid target that is removed by a structural proposal does **not**
   automatically become `-1`, even if the field permits a sentinel.
3. No automatic dependent deletion, reparent, retarget, clamp or repair is
   allowed.
4. If an inbound edge would dangle after transformation, the proposal must
   explicitly resolve it in the same coordinated typed transform or fail.
5. Required references never gain a sentinel merely because their target was
   removed.

These rules keep "optional in the PMX format" separate from "safe to erase
implicitly during structural editing".

## 6. Conditional relationship rules

- BDEF1 uses one bone field; BDEF2/BDEF4/SDEF/QDEF use the repeated
  `bone_indices` field. QDEF requires PMX 2.1.
- Bone tail reference exists only with `PMX_BONE_FLAG_TAIL_INDEX`; offset-tail
  mode has no tail edge.
- Bone inherit reference exists only with inherit-rotation or
  inherit-translation enabled.
- IK target and IK links exist only with `PMX_BONE_FLAG_IK`.
- Morph type selects the target collection. Flip and impulse morphs require
  PMX 2.1. Additional-UV morph types 4-7 additionally require the
  corresponding header additional-UV layer.
- Display-frame `target_type` selects bone versus morph.
- Soft-body relationships exist only in the PMX 2.1 soft-body section.
- A non-zero joint type requires PMX 2.1, but the two rigid-body reference
  fields themselves are present on every supported joint record.
- Material toon mode selects texture-edge versus shared-slot semantics.

Graph extraction in CP05 must evaluate these controls; it must not emit edges
from inactive payload alternatives.

## 7. Invalid typed-document analysis policy

The read-only graph layer must be able to analyze a typed `PmxDocument` that is
semantically invalid and return invalid-target evidence rather than crashing.
Therefore graph extraction must **not** call `validate_pmx_document()` as an unconditional precondition.

This does not weaken parsing. A malformed raw PMX may still fail in the reader
before a typed document exists. The graph requirement applies once the caller
already has a typed document, including one built for adversarial/generated
tests.

No invalid index may be silently normalized, clamped or omitted from evidence.

## 8. Unknown trailing bytes

`PmxDocument.trailing_data` contains bytes left after all supported PMX
sections. The reader/writer currently preserve those bytes for round-trip
compatibility, but their semantics are intentionally unknown.

Policy for v0.9.0:

- read-only load/round-trip may continue to preserve `trailing_data`;
- reference analysis must not guess edges inside opaque trailing bytes;
- any structural keep/delete/reorder/remap transformation must **fail closed**
  when `trailing_data` is non-empty until that extension format is explicitly
  understood and reviewed.

`header.extra_global_data` is likewise preserved as opaque header data and is
not guessed to contain references; CP03 does not assign reference semantics to
it.

## 9. Index-width and serialization policy

The six target collection capacities remain governed by the index widths stored
in the header. v0.9.0 remap work must not silently resize those widths.

Post-transform validation must prove that all target counts remain encodable by
their declared width before serialization. Existing writer/validator ownership
remains authoritative; CP09/CP16 may add transform-specific preflight evidence
but must not create a competing PMX validity definition.

## 10. Diagnostic identity requirements for CP04-CP07

Every extracted edge or invalid-target diagnostic must retain deterministic
context sufficient to identify:

- relationship ID;
- source section;
- source entity/record index;
- stable nested field/path (including list index where relevant);
- raw target index;
- target collection identity;
- sentinel state versus active edge;
- active condition/type/flag context when relevant.

Human-readable PMX names are display metadata only and must never be graph node
identity.

## 11. Checkpoint ownership

- **CP11** owns surface/geometry and material texture/sphere/toon references plus
  material surface-span coupling.
- **CP12** owns vertex deform -> bone and all bone/IK relationships.
- **CP13** owns group/vertex/bone/UV/material/flip morph relationships and
  display-frame relationships.
- **CP14** owns impulse morph -> rigid body and all rigid-body/joint/soft-body
  relationships.

A relationship has exactly one remap owner. Target collection alone does not
change ownership; for example material morph remains CP13, and impulse morph
remains CP14.

## 12. CP03 exit contract

CP03 is complete when this inventory and its regression test pass review.
No graph extraction or remap implementation may start before CP03 PASS.
