# v0.9.5.8 Confirmed Smart Material Apply Integration

Version 0.9.5.8 adds one minimal private execution bridge from an exact approved
Smart Material preview to the existing generic PMX apply authority.

## Frozen entry point

```python
apply_smart_material_color_draft(
    source_path,
    destination_path,
    draft,
    preview,
    *,
    confirmation=None,
)
```

The implementation lives in
`mmd_registry/services/_smart_material_apply.py`.

## Explicit confirmation

Preview success is not apply permission. The caller must supply one explicit confirmation:
an exact frozen `SmartMaterialApplyConfirmation` after approving the preview.
Confirmation binds:

- preview schema version;
- exact source SHA-256;
- canonical `PmxEditPlan` SHA-256.

Destination is intentionally not part of confirmation identity. Reuse is valid
only for the same exact source content and exact plan/preview identity.

## Exact preview-to-apply authority

The Smart boundary does not rebuild a draft, rediscover materials, resolve
ambiguity, retarget indices, or normalize a new color intent. It first checks
source/plan/preview/confirmation identity, then replays the exact draft through
the existing `mmd_registry.services.preview_edit` authority.

Only after exact replay parity does it call the existing
`mmd_registry.services.apply_edit` once with `overwrite=False`.

## Source and destination safety

The source must never be overwritten. Same-path destinations, aliases, hardlink
races, no-clobber publication collisions, source replacement, source content
drift, and late source/destination races remain governed by the existing lower
path and atomic publication authority.

The Smart layer adds no second temporary-file writer, serializer, remapper,
atomic rename/link strategy, rollback writer, or repair path.

## Post-write certification

The post-write certification step is mandatory. After successful lower publication
the Smart boundary:

1. reads destination bytes back;
2. checks SHA-256 equals the generic apply result;
3. reparses those exact bytes through the existing PMX reader;
4. requires the reparsed document to equal the approved preview document;
5. validates the reparsed PMX;
6. rechecks source SHA-256.

Certification failure is fail-closed and does not silently repair or republish.

## Determinism and material preservation

The same exact source, draft, preview, and confirmation applied to independent
safe destinations must produce identical output bytes and output hashes.
Material-color execution changes only draft-authorized diffuse RGB while
preserving source alpha, untouched fields, and non-target materials.

## Error boundary

Smart-specific reasons remain private and limited to:

- `confirmation_required`
- `confirmation_mismatch`
- `source_evidence_mismatch`
- `preview_apply_mismatch`
- `post_write_certification_failed`

Existing lower `PmxServiceError` diagnostics propagate unchanged.

## Public and CLI boundary

v0.9.5.8 adds no package-root or root-service public API. The package root stays
exactly `('__version__',)`. Smart CLI remains `smart inspect` only; there is no
Smart apply/mutation command.

## Local certification before release preparation

- focused v0.9.5.8 integration: 35 tests PASS;
- CP16 targeted release-facing regression: 918 tests, one skip, PASS;
- CP17 canonical unittest discovery: 3,149 tests, two optional skips, PASS;
- protected preview/apply/writer/remapper/publication compatibility remains
  unchanged;
- optional private and lawful-secondary corpus gates are SKIP when no controlled
  corpus is configured; no corpus coverage is fabricated.

Release-facing coverage, lint, compile, build, artifact inspection, clean
installation, final-source, merged-main, tag, and GitHub Release certification
remain explicit later gates.
