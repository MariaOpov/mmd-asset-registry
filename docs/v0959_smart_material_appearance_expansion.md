# v0.9.5.9 Smart Material Appearance Expansion

Version 0.9.5.9 expands the private Smart Material authoring layer beyond
diffuse RGB while deliberately preserving the released execution authorities.

## Frozen scope

Supported appearance capabilities are exactly:

- `transparency`
- `material_specular`
- `material_edge`

Texture replacement is `BLOCKED_PENDING_ARCHITECTURE`.
Appearance presets are `BLOCKED_PENDING_ARCHITECTURE`.
Brightness is unsupported for v0.9.5.9.

The release does not add texture generation or painting, UV editing, arbitrary
image processing, geometry/vertex/bone/morph/physics authoring, automatic Smart
apply, a Smart mutation CLI, a new transaction schema, or a second
writer/remapper/preview/apply/publication path.

## Exact evidence and target authority

The private implementation is
`mmd_registry/services/_smart_material_appearance.py`.

Targets come only from exact `MATERIAL` evidence already certified by the Smart
inspection/draft authority. Callers cannot supply raw material indices. Target
indices are unique, ascending, and source-bound.

Draft composition reuses the existing `PmxEditPlan(schema_version=1)` and
`UpdateMaterial` vocabulary. One operation is emitted per exact material target.

## Intent semantics

Transparency accepts an exact finite float32 alpha in `[0.0, 1.0]`, preserves
source diffuse RGB, and changes only the diffuse alpha component.

Material specular accepts exact finite float32 specular RGB and/or strength.
At least one field is required. No clamp, gamma transform, 0-255 inference, or
silent coercion is performed.

Material edge accepts exact finite float32 edge RGBA and/or edge scale. At least
one field is required. Existing `drawing_flags` are preserved.

Untouched material fields and non-target materials remain unchanged.

## Preview and apply authority

`preview_smart_material_appearance_draft()` delegates the exact certified draft
to the released Smart Material preview bridge and existing generic preview
engine. It does not create a second preview DTO or simulation path.

Confirmed execution remains governed by the released v0.9.5.8 explicit
confirmation/apply integration and generic no-clobber publication authority.
Preview success is not apply permission. Source and plan identity remain exact,
the source remains immutable, and successful output is reparsed and validated.

## Determinism and safety

Equivalent repeated/reversed/duplicate exact evidence produces stable target and
operation ordering and stable plan identity. Relevant hash-seed certification
covers `PYTHONHASHSEED=0,1,2,42,31337`.

The failure taxonomy remains fail-closed for ambiguous semantic selection,
unsupported appearance capability, malformed intent/evidence, source drift,
destination safety failures, publication failures, reparse failures, and
preview/apply semantic mismatch.

## Compatibility and public surface

The package root stays exactly:

```python
("__version__",)
```

Smart Inspect remains read-only. Smart CLI remains `smart inspect` only.
Generic preview/apply signatures are unchanged. The appearance module is
private and is not exported from the package root or
`mmd_registry.services.__all__`.

## Release-preparation evidence

Before CP25 release-facing preparation:

- 57 focused v0.9.5.9 tests pass.
- CP23 targeted release regression passes 137 tests.
- CP24 canonical discovery passes 3,206 tests with 2 optional skips.
- Optional private PMX certification is `PASS_WITH_OPTIONAL_SKIP` when
  `MMD_REGISTRY_PRIVATE_PMX` is not explicitly configured.
- The available local synthetic adversarial PMX corpus passes deterministic
  fail-closed certification.

CP25 records fresh Ruff, compile, coverage, wheel/sdist, artifact-inspection,
clean-install, installed-root, installed-private-module, and private-data-hygiene
evidence. Feature-branch artifact hashes are nonfinal; final release artifact
authority is established from certified merged main.

No PyPI publication is authorized by this document.
