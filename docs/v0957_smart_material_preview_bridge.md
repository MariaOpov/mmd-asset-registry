# v0.9.5.7 Smart Material Preview Bridge

Version 0.9.5.7 adds one minimal private bridge from an already-certified
v0.9.5.6 Smart Material Color Draft to the existing stable PMX preview authority.

## Frozen entry point

```python
def preview_smart_material_color_draft(
    source_bytes: bytes,
    draft: PmxEditPlan,
) -> PmxEditPreview:
    return preview_edit(source_bytes, draft)
```

The implementation lives in
`mmd_registry/services/_smart_material_preview.py`.

## Input and authority contract

The bridge accepts only exact PMX source bytes plus an already-certified
`PmxEditPlan(schema_version=1)` produced by the released v0.9.5.6 Smart Material
draft authority. It does not accept Smart Part kinds, semantic evidence,
capability evidence, presets, raw RGB intent, separate material indices, output
paths, overwrite flags, or apply confirmation.

The bridge delegates those exact values to
`mmd_registry.services.preview_edit`. It returns the existing `PmxEditPreview`
unchanged. It does not define a second preview DTO or preview engine.

## Source binding and fail-closed drift safety

The supplied plan remains bound to its exact source SHA-256. A stale draft
against different valid PMX bytes fails closed through the existing preview/edit
authority. The bridge does not repair the hash, regenerate a draft, re-run Smart
semantic resolution, choose replacement targets, or silently continue.

## Exact preview parity

The previewed operation sequence must equal the certified draft operation
sequence. Material target indices, canonical diffuse RGB, operation order, and
plan identity remain unchanged. No operation may be omitted or added by the
bridge.

For material-color preview, only draft-authorized diffuse RGB changes in the
simulated document. Source alpha is preserved exactly, all other material fields
remain unchanged, non-target materials remain unchanged, and source bytes remain
unchanged. A target whose RGB is already equal does not require a fake audit
change.

## Determinism and adversarial behavior

Repeated calls and `PYTHONHASHSEED=0,1,2,42,31337` must produce the same
canonical draft/preview projection. Existing upstream authorities remain
responsible for ambiguity, unsupported capability, no exact material evidence,
duplicate/reversed equivalent evidence, malformed or non-finite RGB, empty
target sets, Unicode/Japanese names, and source/evidence mismatch.

A failed upstream certification case never reaches the bridge.

## Public and mutation boundaries

v0.9.5.7 adds no package-root public API and no root-service export. The package
root remains exactly `('__version__',)`. Smart CLI remains `smart inspect` only.

The bridge owns no apply or source-write authority, no writer or remapper, no
structural transaction schema, no filesystem publication, no semantic detector,
no capability resolver, and no color-normalization authority. It performs no
apply, no source write, and publishes no output.

## Certified local behavior evidence

Before release-facing version promotion:

- exact draft/preview parity, source-binding drift safety, alpha/untouched-field
  correctness, determinism, adversarial hardening, and protected-authority
  compatibility checkpoints passed;
- the focused v0.9.5.7 bridge bundle passed 8 tests;
- the protected v0.9.5.6 Smart Material bundle passed 46 tests;
- canonical `python -m unittest discover` completed 3,114 tests with 2 optional
  private-runtime skips and zero failures/errors.

Release-facing quality, coverage, build, artifact inspection, clean-install,
merged-main, tag, and GitHub Release certification remain later explicit gates.
