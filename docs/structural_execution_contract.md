# v0.9.1 structural execution contract and threat model

This document freezes the safety semantics that v0.9.1 structural execution
must preserve while the existing v0.9.0 internal structural-output kernel is
hardened and exposed only through the separately reviewed v0.9.1 service layer.

It is a correctness and filesystem-safety contract, not a Python sandbox or a
claim that private implementation objects are security boundaries.

## Authority and scope

The source of truth for structural semantics remains the existing typed PMX
document model, coordinated structural transform pipeline, whole-document PMX
validator, reference model, and certified structural preview.

v0.9.1 execution is bounded to the six existing structural target kinds:

- `vertex`
- `texture`
- `material`
- `bone`
- `morph`
- `rigid_body`

Execution may keep, delete, or reorder existing records. It does not authorize
insertion, arbitrary CRUD, automatic index-width resizing, silent repair,
in-place editing, source replacement, or mutation of opaque trailing data.

The internal `mmd_registry.pmx.structural_output` module remains an
implementation substrate. v0.9.1 authorizes structural execution only through
`mmd_registry.services.apply_structural_edit`; the raw writer, transform intent,
serialization objects, and filesystem commit hooks are not canonical public API.

## Required execution pipeline

A successful structural execution must preserve this semantic sequence:

1. validate source and destination path policy;
2. resolve a destination that is distinct from the source;
3. capture source filesystem identity, bytes, size, and SHA-256;
4. parse the captured source bytes into a typed `PmxDocument`;
5. apply the same coordinated structural intent semantics used by preview;
6. certify the intended document with whole-document validation and fresh
   reference analysis;
7. deterministically serialize the certified intended document;
8. reparse the serialized bytes;
9. independently certify the reparsed document;
10. require exact semantic equality between reparsed and intended documents;
11. write only the already-verified bytes to a temporary file in the
    destination directory;
12. flush and `fsync` the temporary file;
13. verify the temporary-file bytes/hash;
14. immediately before publication, reverify source identity and source SHA-256;
15. recheck destination safety and overwrite policy;
16. atomically publish the verified output;
17. clean temporary residue on every failure path;
18. construct success evidence only after successful publication.

No success result may be reported before the publication step succeeds.

## Source immutability

The source PMX is immutable for structural execution.

The following are always forbidden:

- using the source path as the output path;
- using a symlink or hardlink alias of the source as output;
- replacing the source as part of "overwrite";
- editing the source in place;
- backup-and-overwrite workflows that mutate the source.

`overwrite=True` means only that a *separate* destination may be replaced.

Immediately before output publication, execution must prove that the original
source path still resolves to the expected source identity and that the source
content SHA-256 remains unchanged.

## Destination and atomicity contract

A destination must be a PMX path in an existing directory and must remain
provably separate from the source.

Without overwrite authorization, an existing destination is a failure and its
contents must remain unchanged.

Publication must not expose a partially written destination. Verified bytes are
first written to a temporary file in the destination directory. Failure before
atomic publication must leave no new destination and no temporary residue.

The v0.9.0 implementation reuses the mature v0.8 safe-output kernel for this
behavior. That private dependency is allowed as a temporary implementation
detail; later checkpoints may extract or replace it only if these semantics and
the frozen v0.8 compatibility tests remain intact.

CP04 owns additional destination-safety hardening and adversarial race review.
Therefore this contract does not overclaim protection against arbitrary hostile
same-process monkeypatching or every operating-system/filesystem adversary.

## Preview / execution semantic parity

Preview and execute must not contain competing structural-transform semantics.

Execution must derive its intended document through the same certified
structural preview/transform semantics. For the same parsed source document and
the same structural intent:

- the intended document must be identical;
- the resolved intent/audit evidence must be identical;
- execute may add serialization, destination safety, atomic publication, and
  post-write evidence only;
- execute must not normalize, repair, infer, or silently alter the previewed
  intent.

A no-op execution request is still required to pass complete certification,
serialization, reparse, and semantic-equality verification. If the caller asks
for execution, a no-op may create a distinct verified output file; it may never
fall back to source overwrite.

## Fail-closed rules

Structural execution must fail closed when any of these conditions is present:

- opaque/non-empty `trailing_data`;
- invalid or unsupported reference state that prevents complete certification;
- stale, incomplete, duplicate, or out-of-domain remap evidence;
- insertion-capable collection mappings;
- index values that exceed the already-declared PMX index-width capacity;
- serialization failure;
- reparse failure;
- post-reparse invariant failure;
- semantic mismatch between intended and reparsed documents;
- source path, identity, or content change before publication;
- unsafe destination state or destination-policy race detected by the active
  safety kernel;
- temporary payload hash mismatch;
- publication failure.

There is no automatic repair and no automatic PMX index-width resizing.

## Public-boundary rule

CP16 exposes one intentionally reviewed service entry point:
`mmd_registry.services.apply_structural_edit`. It accepts only the frozen bounded
collection-edit request vocabulary and distinct source/output paths. It does not
accept raw transform intents or remap primitives from callers.

The raw structural-output kernel must remain absent from canonical public
namespaces such as `mmd_registry.pmx` and `mmd_registry.services`; specifically,
`write_pmx_structural_transform`, `PmxStructuralWriteResult`, serialization
helpers, and filesystem commit hooks remain implementation details.

The canonical capability manifest is promoted by CP16 to
`structural_write=True` and `reference_safe_execution`, while the manifest
constructor keeps the v0.9.0 preview-only defaults for additive compatibility.

## Diagnostic rule

The structural writer remains internal and may use implementation-level
exceptions. The CP16 service translates expected path and verification failures
to stable coarse `structural_path_unsafe` and
`structural_verification_failed` diagnostics under the
`apply_structural_edit` operation. Parse/validation/I/O failures continue through
the existing public diagnostic adapter. Unexpected failures are redacted so
private paths, arbitrary exception text, and implementation details are not
exposed.

CP17 owns richer stage/provenance evidence; it must remain additive to this
coarse CP16 error surface. Process-control exceptions must not be swallowed or
converted into ordinary service failures.

## Determinism, state isolation, and resource behavior

For the same typed source and structural intent, preview and verified
serialization evidence must be deterministic.

Structural processing must not depend on mutable process-global lookup state.
Repeated unrelated calls must not contaminate one another.

Reference-impact analysis must remain batched rather than re-scanning complete
graph evidence independently for every changed node. No retry, repair, or
search loop may grow without a bound derived from the input document/evidence.

Further adversarial resource and state-isolation hardening remains a later
release gate; CP03 freezes the requirement rather than claiming all possible
resource attacks are already eliminated.

## Threat matrix

| ID | Threat | CP03 contract / current control | Later owner / residual |
|---|---|---|---|
| T01 | Source overwrite / in-place mutation | Distinct source/output required; source never publication target | Preserve through all execution checkpoints |
| T02 | Symlink / hardlink alias to source | Existing safe-output path policy rejects aliases | CP04 hardens destination policy |
| T03 | Source path or file replacement during execution | Source identity is captured and rechecked immediately pre-commit | CP04/CP05 adversarial race coverage |
| T04 | Source content race | Source SHA-256 is captured and rechecked pre-commit | CP04/CP05 adversarial race coverage |
| T05 | Destination race / TOCTOU | Destination policy is checked before work and rechecked before atomic publication | CP04 owns stronger destination-safety review |
| T06 | Partial output / temporary residue | Verified temp-file publication with cleanup on failure | CP05 formalizes atomic structural transaction |
| T07 | Serialization/reparse mismatch | Serialize -> reparse -> certify -> exact equality is mandatory | Preserve in all writers |
| T08 | Stale/incomplete coordinated remap | Canonical complete remaps plus post-transform validator/reference certificate | CP07-CP14 target/cross-section execution gates |
| T09 | Opaque trailing data | Non-empty `trailing_data` is structural-ineligible, including no-op certification | Preserve fail-closed |
| T10 | Index-width overflow | Existing validator proves declared capacity; no automatic resize | Preserve fail-closed |
| T11 | Silent repair / normalization | Explicitly prohibited | No later checkpoint may add it implicitly |
| T12 | Preview/execute semantic divergence | Execute must derive from the same certified preview semantics | CP06 parity gate |
| T13 | Unsupported insertion/new indices | Collection transform rejects new indices without old sources | Out of scope for v0.9.1 |
| T14 | Accidental public raw-writer exposure | CP16 exposes only the bounded service wrapper; raw kernel remains absent from canonical public namespaces | Preserve through release gates |
| T15 | Diagnostic/private-path leakage | CP16 uses coarse structured redacted execution diagnostics | CP17 expands stage/provenance evidence |
| T16 | Non-determinism | Canonical ordering, deterministic intent hash, repeated serialization equality | Recheck in CP19 |
| T17 | Mutable/shared-state leakage | Structural path is immutable/state-isolated; no mutable global lookup tables | Recheck in CP19 |
| T18 | Resource amplification | Batched reference-impact analysis scales with graph evidence rather than changed-node rescans | CP19 expands adversarial/resource gate |

## Checkpoint boundaries

CP03 defines and freezes this contract. It does not:

- change structural transformation code;
- change the v0.8 safe-output kernel;
- expose a new public execution API;
- change diagnostics;
- promote `structural_write`;
- change the capability contract;
- add per-target execution authority;
- change packaging or release metadata.

Any implementation change required by later checkpoints must preserve this
contract unless an explicit reviewed compatibility/security decision supersedes
a specific clause.
