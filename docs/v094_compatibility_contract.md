# v0.9.4 Compatibility Contract

This document freezes the released compatibility surface that the
`v0.9.4 — Declarative Structural Transaction Authoring` campaign must preserve.

It is intentionally narrower than the future transaction-plan schema contract.
The JSON authoring schema, loader vocabulary, renderer, templates, and new public
authoring namespace are not frozen here; they remain CP03–CP04 work.

## Released schema boundaries

The registry schema remains independent from PMX authoring schemas:

- latest registry schema: `0.3`
- supported registry schemas: `0.2`, `0.3`
- existing declarative PMX edit-plan schema: `1`
- existing v0.8 edit operation vocabulary:
  `set_model_info`, `set_texture_path`, `update_material`

v0.9.4 must not repurpose or version-bump the v0.8 edit-plan schema merely to
carry structural transactions.

## Package and CLI identity

The package root remains intentionally minimal and the installed command remains
`mmd-asset-registry = mmd_registry.cli:main`.

Existing commands remain available additively:

- `validate`
- `hash`
- `inspect`
- `scan`
- `roundtrip`
- `edit`
- `edit-plan`
- `texture-portability`
- `doctor`
- `bones`
- `rig`

v0.9.4 may add transaction-plan CLI adapters, but must not remove or reinterpret
released commands.

## Legacy public service boundary

`mmd_registry.services` remains the released façade for v0.8–v0.9.2 services.
The v0.9.3 transaction API is intentionally not promoted into that root façade.

The released root service exports and call shapes remain stable, including:

- edit preview/apply
- document load/inspect/validate
- reference analysis
- structural preview/execution

Raw writer, remap, final-index, publication, and structural transaction internals
remain private.

## v0.9.3 structural transaction namespace

The released transaction namespace remains:

`mmd_registry.services.structural_transaction`

Its public exports are exactly:

- `PmxStructuralTransactionOperation`
- `PmxStructuralTransactionRequest`
- `PmxStructuralTransactionPreviewResult`
- `preview_structural_transaction`
- `apply_structural_transaction`

The transaction request remains an immutable ordered `operations` tuple. Preview
and apply continue to use the same v0.9.3 authority. v0.9.4 authoring must adapt
into this authority rather than introducing a second interpreter or writer.

## Capability compatibility

The released capability field prefix through `structural_transaction` remains
ordered and consumable by older callers. Legacy constructor defaults remain
backward compatible, while the canonical v0.9.3 manifest reports:

- `structural_preview=True`
- `structural_write=True`
- `structural_insert=True`
- `structural_transaction=True`
- `structural_contract="reference_safe_execution"`

A future transaction-plan capability may only be additive and is not frozen by
this CP02 contract.

## Diagnostics

Released diagnostic and service-operation values remain present in their
existing relative order. v0.9.4 may add new authoring-specific values only
additively and must not rename or reorder released values.

## Structural DTO namespaces

The reviewed structural DTO namespaces remain explicit and non-root:

- `mmd_registry.services.structural_reference`
- `mmd_registry.services.structural_texture`
- `mmd_registry.services.structural_material`
- `mmd_registry.services.structural_bone`
- `mmd_registry.services.structural_morph`
- `mmd_registry.services.structural_rigid_body`
- `mmd_registry.services.structural_vertex`

CP03–CP04 must inspect their real constructors and field semantics before any
transaction-plan JSON vocabulary is frozen.

## Safety inheritance

v0.9.4 authoring is an adapter layer. It must not weaken the released structural
transaction safety properties:

- source remains immutable
- input and output remain distinct
- overwrite remains explicit
- preview and apply share authority
- serialization is reparsed and certified before publication
- canonical semantic equality remains required
- source identity is rechecked before publication
- destination collision/race safety remains enforced
- failure leaves no partial or temporary output
- private writer/publication kernels remain private
- diagnostics remain deterministic and privacy-safe

## CI contract

The repository's cross-platform validation workflow must continue to run the
complete unittest discovery suite, so this contract and all earlier compatibility
contracts remain active without replacing the earlier release-specific tests.
