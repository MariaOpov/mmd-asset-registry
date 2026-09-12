# Changelog

All notable changes to MMD Asset & License Registry are documented here.

## 0.9.5.5 - 2026-09-12

### Added

- Added the Smart Inspect CLI command `mmd-asset-registry smart inspect SOURCE` as the first deterministic,
  read-only user-facing command over the existing Smart semantic stack.
- Added a private read-only Smart inspection orchestration service that reuses
  the existing PMX loader/catalog, exact detector, explainability projection,
  and confidence/ambiguity authority.
- Added concise resolved and ambiguous evidence presentation with deterministic
  Smart Part ordering and explicit no-result behavior.
- Added CLI hardening for missing/directory/non-PMX/truncated input, Unicode and
  Japanese paths/names, spaces, UTF-8 output, slash/backslash behavior, and
  redacted unexpected internal failures.
- Added repeat-run, reversed-equivalent-input, and
  `PYTHONHASHSEED=0,1,2,42,31337` determinism certification.

### Changed

- Bumped the runtime and distribution version from `0.9.5.4` to `0.9.5.5`.
- Updated release-facing README, public API policy, packaging policy, release
  checklist, CI regression matrix, and current-version assertions for
  v0.9.5.5.
- Kept the legacy parser/runtime parser contracts unchanged by adding Smart
  through the outer application parser only.

### Verified

- Full canonical serial discovery passes 3,060 tests with 2 optional skips.
- The targeted Smart/release regression bundle passes 578 tests.
- Existing detector, explainability, confidence, transaction, and package-root
  authorities remain unchanged.
- Coverage measures 86.98% combined with 87.01496% like-for-like coverage when
  the two new modules are excluded; existing Smart semantic module coverage
  does not regress. The new Smart CLI and private inspection service measure
  80.74% and 83.05%.
- Ruff 0.16.3, compileall, direct source compilation, deterministic output, and
  release-facing compatibility gates pass.
- Optional private real-model checkpoints were skipped when no controlled
  private corpus was configured; no substitute private model was invented.

### Safety and compatibility

- Smart Inspect is read-only and adds no writer/remapper, preview/apply,
  automatic repair, transaction-plan generation, schema/capability promotion,
  fuzzy/substring matching, probability score, ML/LLM/AI, or publication
  authority.
- The package root remains exactly `('__version__',)` and the inspection service
  remains private.
- Existing v0.8/v0.9 structural execution and transaction authorities remain
  unchanged.
- Push, pull request, merge, tag, GitHub Release, and PyPI publication remain
  separate Maintainer-controlled gates.

## 0.9.5.4 - 2026-09-06

### Added

- Added deterministic, read-only Smart Part confidence and ambiguity
  presentation through `mmd_registry.smart_part_confidence.assess_smart_parts`.
- Added frozen `SmartPartConfidenceCandidate` and
  `SmartPartConfidenceAssessment` values plus the HIGH, MEDIUM, LOW, and
  AMBIGUOUS presentation states.
- Added independent-source derivation over the shared exact-match trace without
  introducing a second classifier, score, probability model, or mutation
  authority.
- Added adversarial coverage for same-source conflicts, duplicate evidence,
  texture-only evidence, path-separator provenance, validation guards, and
  deterministic ordering.

### Changed

- Bumped the runtime and distribution version from `0.9.5.3` to `0.9.5.4`.
- Updated release-facing README, public API policy, packaging policy, release
  checklist, CI regression matrix, and version assertions for v0.9.5.4.
- Corrected PMX joint parsing so finite Bullet 6DOF lower > upper limits are
  preserved as valid free-axis semantics instead of being rejected. Values are
  not swapped or normalized.

### Verified

- Full canonical serial discovery passes 3,022 tests with 2 optional skips.
- Coverage reports 87.01% combined statement/branch coverage, 91.28% detector
  coverage, 72.09% explainability coverage, 98.83% private-confidence coverage,
  100.00% public-confidence coverage, and 91.58% joint-reader coverage.
- Confidence repeat/reverse-input determinism, detector/explainer parity,
  same-source ambiguity retention, texture-only LOW semantics, and raw texture
  provenance are certified.
- Primary and secondary private real-model certification is read-only and
  preserves source bytes and metadata.
- Ruff 0.16.3 and isolated compilation pass before version promotion.

### Safety and compatibility

- Confidence is presentation state only, never probability, permission, or
  execution authority.
- No fuzzy/substring/AI classifier, Smart CLI, schema expansion, capability
  promotion, transaction engine, preview/apply authority, writer, remapper, or
  publication authority is added.
- Existing transaction-plan schema-one and reference-safe structural execution
  authorities remain unchanged.
- `mmd_registry.__all__` remains exactly `('__version__',)`.
- Push, pull request, merge, tag, GitHub Release, and PyPI publication remain
  separate Maintainer-controlled gates.

## 0.9.5.3 - 2026-09-06

### Added

- Added deterministic, read-only Smart Part evidence explanations through
  `mmd_registry.smart_part_explainability.explain_smart_parts`.
- Added frozen `SmartPartEvidenceExplanation` and `SmartPartExplanation` DTOs
  with concrete field/value provenance, normalized comparison evidence,
  canonical matched aliases, exact match-rule identity, and deterministic
  derivation metadata.
- Added shared private match-trace authority so detector and explainer are two
  projections of the same exact semantic decision rather than parallel
  classifiers.

### Changed

- Bumped the runtime and distribution version from `0.9.5.2` to `0.9.5.3`.
- Extended public API and packaging documentation with the explicit
  explainability submodule while preserving the package-root surface.
- Added v0.9.5.3 targeted regressions to the cross-platform validation workflow
  and synchronized release-facing version assertions.

### Verified

- Detector/explainer parity is certified across all exact aliases, input
  permutations, duplicate entries, mixed Japanese/English names, and
  `PYTHONHASHSEED=0/1/42`.
- The behavior-frozen full suite passes 2,820 tests with 2 optional skips.
- Coverage measurement reports 86.76% combined statement/branch coverage,
  87.45% for `mmd_registry.smart_part_detection`, and 72.09% for
  `mmd_registry.smart_part_explainability`.
- Ruff 0.16.3, compileall, isolated wheel/sdist generation, canonical artifact
  inspection, clean-install verification, and an installed detector/explainer
  parity probe pass before version promotion.

### Safety and compatibility

- Matching remains the v0.9.5.2 normalized-exact detector contract; no fuzzy
  matching, substring heuristics, scoring, confidence, statistical model, or
  AI classifier is introduced.
- Confidence is not part of v0.9.5.3; ambiguity presentation remains deferred
  to v0.9.5.4 and the Smart CLI remains deferred to v0.9.5.5.
- No PMX mutation, transaction, preview/apply, writer, remapper, schema,
  capability-manifest, or publication authority is added or changed.
- `mmd_registry.__all__` remains exactly `('__version__',)`.
- Push, pull request, merge, tag, GitHub Release, and PyPI publication remain
  separate Maintainer-controlled gates.

## 0.9.5.2 - 2026-09-05

### Added

- Added deterministic, read-only Smart Part detection through
  `mmd_registry.smart_part_detection.detect_smart_parts`.
- Added conservative exact-alias lexical evidence for material, bone, morph,
  and texture catalog entries using NFKC normalization, whitespace collapse,
  and case folding.
- Added deterministic cross-entity evidence aggregation, duplicate-evidence
  elimination, same-source conflict suppression, and order-independent output.

### Changed

- Bumped the runtime and distribution version from `0.9.5.1` to `0.9.5.2`.
- Extended the public API documentation with the explicit detector submodule
  while keeping the package root unchanged.
- Synchronized release-facing README, packaging policy, release checklist, and
  version assertions with `v0.9.5.2` / `0.9.5.2`.

### Verified

- Full local discovery passes 2,755 tests with 2 optional skips.
- Coverage measurement reports 86.85% combined project statement/branch
  coverage and 93.12% for `mmd_registry.smart_part_detection`.
- Ruff 0.16.3 passes the repository's current E9/F63/F7/F82 gate.
- Isolated feature-branch wheel/sdist build, canonical artifact inspection,
  clean-install verification, and installed detector execution pass.

### Safety and compatibility

- Matching remains normalized-exact only: no fuzzy matching, substring
  heuristics, edit distance, scoring, confidence, statistical model, or AI
  classifier is introduced.
- Conflicting recognized names on one source entity contribute zero evidence;
  unknown names do not override a unique exact recognized kind.
- The detector has no PMX mutation, transaction-plan generation, preview/apply,
  writer, remap, filesystem-publication, CLI, or capability-manifest authority.
- Existing structural transaction, preview, apply, serialization, remap, and
  writer authorities remain unchanged.
- `mmd_registry.__all__` remains exactly `('__version__',)`; the detector stays
  submodule-only.
- Push, pull request, merge, tag, GitHub Release, and PyPI publication remain
  separate Maintainer-controlled gates.

## 0.9.5.1 - 2026-09-03

### Added

- Added the deterministic, immutable `mmd_registry.smart_parts` domain surface
  with `SmartPartKind`, `SmartPartEvidenceKind`, `SmartPartEvidence`, and
  `SmartPart`.
- Added exact source-kind/source-index evidence suitable for future cross-entity
  semantic-part detection without embedding mutable PMX document objects.

### Changed

- Bumped the runtime and distribution version from `0.9.5` to `0.9.5.1`.
- Updated release-facing documentation, CI assertions, and compatibility tests
  for the four-segment PEP 440 patch version.
- Extended the numeric release-version metadata contract to accept at least
  three numeric release segments, including `0.9.5.1`.

### Verified

- The Smart Part foundation remains read-only and root-unpromoted.
- The local promoted suite retains 2649 unit tests with 2 optional skips.
- Registry schemas remain `0.2`/`0.3`; structural transaction-plan and
  execution authorities are unchanged.

### Safety and compatibility

- No semantic detector, fuzzy matching, confidence scoring, capability
  promotion, CLI, transaction schema, writer, remapper, preview/apply path, or
  PMX mutation authority is introduced.
- `mmd_registry.__all__` remains exactly `('__version__',)`.
- Push, pull request, merge, tag, GitHub Release, and PyPI publication remain
  separate Maintainer-controlled gates; PyPI is not authorized by this patch.

## 0.9.5 - 2026-09-03

### Added

- Added a deterministic read-only structural authoring catalog and
  `transaction-plan inspect`.
- Added exact source-bound authoring selectors with fail-closed ambiguity
  handling.
- Added a structural authoring builder that compiles ergonomic input into the
  existing schema-one transaction plan model.
- Added certified structural authoring diff projection and
  `transaction-plan preview --diff`.
- Added strict canonical transaction-plan formatting through
  `transaction-plan format`.
- Added human-friendly `transaction-plan build` helpers for all six released
  insertion targets: `texture`, `material`, `morph`, `bone`, `rigid-body`,
  and BDEF1 `vertex`.

### Changed

- Bumped the package version from `0.9.4` to `0.9.5`.
- Human-friendly builders resolve only exact source-bound identities and then
  render the existing canonical schema-one plan.
- The vertex builder derives zero-valued additional UV vectors from
  `document.header.additional_uv_count` and supports BDEF1 only.

### Verified

- Certified the completed v0.9.5 feature branch with 2619 unit tests passing
  and 2 skipped after the vertex builder integration.
- Verified help surfaces for all six human-friendly build kinds.
- Preserved the root package public surface as `('__version__',)`.

### Safety and compatibility

- No second transaction schema, execution engine, writer, remapper, or
  publication path was introduced.
- Existing v0.9.3/v0.9.4 preview/apply execution authority remains unchanged.
- Fuzzy matching, case folding, silent first-match behavior, and generic
  operation payloads remain forbidden in the human-friendly authoring layer.

## 0.9.4 - 2026-08-29

- Added strict schema-one declarative structural transaction-plan authoring.
- Added deterministic template, validate, explain, source-bound preview, and atomic apply workflows.
- Preserved the released v0.9.3 structural transaction layer as the execution authority.
- Certified the private-PMX authoring seam for preview, apply, source identity, independent output reparse/reference validation, cleanup, and private path/digest privacy.

## 0.9.3 - 2026-08-25

### Added

- A bounded structural transaction API in
  `mmd_registry.services.structural_transaction` for composing reviewed
  insertion, reorder, and deletion operations across vertex, texture,
  material, bone, morph, and rigid-body targets.
- Deterministic transaction-local identities, final-state reference
  resolution, dependency ordering, whole-transaction capacity preflight, and
  stable preview evidence with canonical plan SHA-256.
- Regression gates for shared preview/execution authority and independent
  serialization/reparse certification.
- Transaction gates require whole-document canonical semantic equality, frozen
  failure provenance, atomic publication, source/destination races, adversarial
  state isolation, backward compatibility, and optional private real-PMX
  validation.

### Changed

- Runtime/distribution version and release-facing contracts are promoted from
  `0.9.2` / `v0.9.2` to `0.9.3` / `v0.9.3`.
- The canonical capability manifest additively reports
  `structural_transaction=True`; direct legacy construction keeps a trailing
  `structural_transaction=False` default.
- Clean installed-package verification imports the explicit transaction
  submodule, previews and executes a real bounded transaction, proves source
  immutability, and independently reparses the atomically published output.

### Verified

- Transaction execution reuses the same semantic plan and preview authority;
  there is no parallel interpreter for execution.
- Publication occurs only after serialization, independent reparse and
  certification, canonical semantic equality, fresh source verification, and
  destination-safety checks all pass.
- Representative v0.8 through v0.9.2 public, CLI, diagnostic, edit, insertion,
  and structural execution contracts remain additively compatible.
- Optional private runtime evidence validates a real PMX transaction without
  disclosing or packaging private model bytes, names, or paths.

### Safety and compatibility

- Registry schema remains `0.3`, supported registry schemas remain `0.2` and
  `0.3`, and edit-plan schema remains `1`.
- Transaction symbols remain submodule-only. The existing
  `preview_structural_edit()` and `apply_structural_edit()` authority, root
  exports, and raw-writer privacy remain unchanged.
- v0.9.3 does not authorize in-place source mutation, automatic index-width
  expansion, silent repair, arbitrary structural CRUD, model creation, GUI,
  Smart Tools, plugins, telemetry, cloud features, or AI editing.
- Push, pull request, cross-platform CI, merge, merged-main certification, tag,
  and GitHub Release remain distinct authorization gates. No PyPI publication
  is authorized without separate explicit Maintainer approval.

## 0.9.2 - 2026-08-22

### Added

- Bounded structural insertion for vertex, texture, material, bone, morph, and
  rigid-body collections through the existing structural preview/execution
  request and authority.
- Typed public insertion vocabulary in seven explicit
  `mmd_registry.services.structural_*` namespaces, including request-local
  `PmxStructuralNewReference` values for coordinated new-to-new references.
- Capacity, atomicity, failure-provenance, adversarial/state-isolation,
  preview/execute parity, backward-compatibility, and capability-promotion
  regression gates for the insertion path.
- Clean installed-package verification that executes, reparses, and certifies a
  real coordinated six-target insertion from the built wheel.

### Changed

- Runtime/distribution version and release-facing contracts are promoted from
  `0.9.1` / `v0.9.1` to `0.9.2` / `v0.9.2`.
- The canonical capability manifest additively reports
  `structural_insert=True`; the existing `structural_preview=True`,
  `structural_write=True`, six target kinds, and
  `reference_safe_execution` contract remain unchanged.
- Legacy `PmxCapabilityManifest` construction keeps
  `structural_insert=False` as a trailing default, preserving older constructor
  call shapes.
- Root `mmd_registry.services.__all__` and the exact
  `PmxStructuralEditRequest is PmxStructuralPreviewRequest` alias remain
  unchanged; no parallel insertion mutation entry point is introduced.

### Safety and compatibility

- Insertion never authorizes in-place source mutation, automatic index-width
  expansion, silent repair, raw writer/remap access, arbitrary structural CRUD,
  model creation, GUI/Smart Tools/plugins, or AI editing.
- Execution retains preview -> serialize -> reparse -> independent certification
  -> semantic equality -> source re-verification -> atomic publication.
- Registry schema remains `0.3`, supported registry schemas remain `0.2` and
  `0.3`, edit-plan schema remains `1`, and v0.8/v0.9.0/v0.9.1 caller contracts
  remain additively compatible.
- Fresh v0.9.2 artifact member counts and SHA-256 digests are captured from the
  final reviewed build rather than copied from historical v0.9.1 evidence.
- No PyPI publication is authorized without separate explicit Maintainer
  approval.

## 0.9.1 - 2026-08-19

### Added

- Bounded public structural execution through `PmxStructuralEditRequest`,
  `PmxStructuralExecutionResult`, and `apply_structural_edit()` for reorder/delete
  requests across vertex, texture, material, bone, morph, and rigid-body targets.
- Redacted structural failure stage/provenance evidence plus adversarial,
  atomicity, state-isolation, preview/execute-parity, and post-write
  re-certification regression gates.
- Installed-package and private-real-model safe-output validation for the public
  structural execution boundary.

### Changed

- Runtime/distribution version and release-facing contracts are promoted from
  `0.9.0` / `v0.9.0` to `0.9.1` / `v0.9.1`.
- The canonical capability manifest now reports `structural_preview=True`,
  `structural_write=True`, and `reference_safe_execution`; the dataclass
  constructor retains its v0.9.0 preview-only defaults for compatibility.
- Cross-platform CI and clean-install verification explicitly exercise the
  v0.9.1 structural execution release gates.

### Verified

- Structural execution remains fail-closed across destination races,
  source-change races, serialization/reparse failures, reference/invariant
  failures, repeated execution, and mutable-global state adversaries.
- A private PMX 2.0 model was executed to a separate verified output with
  source SHA-256 preservation, reference-safe texture remapping, successful
  reparse/re-certification, and no temporary-file residue.
- Existing v0.8 and v0.9.0 public, CLI, diagnostic, edit, and service contracts
  remain additively compatible.
- Final local CP23 evidence passes 1,666 automated tests with one optional
  private-runtime skip at 88.57% combined statement/branch coverage; fresh
  distribution inspection reports 85 wheel file members and 235 sdist file
  members, followed by successful clean installed-package execution.

### Safety and compatibility

- Registry schema remains `0.3`; schemas `0.2` and `0.3` remain supported, and
  edit-plan schema `1` plus the three v0.8 edit operation types remain frozen.
- The raw structural writer remains private. Insertion, automatic index-width
  resizing, silent repair, arbitrary structural CRUD, model creation, IK
  authoring, physics generation/simulation, mesh/UV authoring, GUI, Smart Tools,
  plugins, and AI editing remain unauthorized.
- Structural execution never writes the caller's source in place and publishes
  only after verified serialization, reparse, semantic comparison, source
  re-verification, and destination safety checks.
- No PyPI publication is authorized without separate explicit Maintainer
  approval.

## 0.9.0 - 2026-08-16

### Added

- A complete immutable PMX reference taxonomy, graph, diagnostic model, direct
  impact queries, and public read-only reference-analysis service.
- Reference-safe index remapping and structural collection transforms for
  vertices, textures, materials, bones, morphs, and rigid bodies, with
  coordinated remapping across geometry/material, deform/IK,
  morph/display-frame, and physics references.
- A certified structural transform orchestrator, deterministic structural
  preview/audit evidence, and verified internal serialization/output pipeline.
- A narrow public structural preview service through
  `PmxStructuralCollectionEdit`, `PmxStructuralPreviewRequest`,
  `PmxStructuralPreviewResult`, and `preview_structural_edit()`.
- Adversarial structural integration, resource/state-isolation hardening, and
  installed-wheel smoke coverage for reference analysis and structural preview.

### Changed

- Runtime/distribution version is promoted from prerelease `0.9.0a0` to final
  `0.9.0`; Git/GitHub release label is `v0.9.0`.
- Public capability reporting now documents the v0.9 structural contract as
  `structural_preview=True`, `structural_write=False`, and
  `reference_safe_preview` for the six supported structural target kinds.
- Release-facing README, public API policy, CI version assertion, artifact
  contracts, and publication checklist are synchronized to the final release.

### Verified

- The final-release baseline contains 1,495 automated tests with one optional
  private-runtime skip and 88.86% combined statement/branch coverage.
- The distribution gate builds an 85-member wheel and 220-member sdist, passes
  deterministic artifact inspection, and verifies a disposable clean wheel
  installation including installed reference-analysis and structural-preview
  service smoke tests.
- The same lint, compile, safety, full-suite coverage, build/inspection, clean
  install, release-command, registry, and placeholder-hash workflow passes on
  both Ubuntu and Windows.
- Optional private-runtime validation remains read-only with respect to the
  source model and preserves source integrity; private assets and paths are not
  packaged or published.

### Safety and compatibility

- Registry schema remains `0.3`; schemas `0.2` and `0.3` remain supported, and
  edit-plan schema `1` plus the three v0.8 edit operation types remain frozen.
- Existing v0.8 import, CLI, diagnostic, process, dry-run/apply, destination,
  and source-integrity contracts remain compatible.
- Structural preview is public, but structural write remains non-public and the
  capability manifest explicitly reports `structural_write=False`.
- No insertion, automatic index-width resizing, silent repair, arbitrary
  structural CRUD, model creation, IK authoring, physics generation/simulation,
  mesh sculpting, UV editing, GUI, Smart Tools, plugin system, or AI editing is
  authorized by v0.9.0.
- Changed structural transforms fail closed on opaque trailing data and on
  incomplete or invalid reference/invariant evidence.
- No PyPI publication is part of this release without separate explicit
  Maintainer approval.

## pre-0.9.0 - 2026-08-15

The Git/GitHub release label `pre-0.9.0` maps to the PEP 440 runtime and
distribution version `0.9.0a0`.

### Added

- Standards-based Python packaging metadata, an installed
  `mmd-asset-registry` console entry point, deterministic wheel/sdist
  inspection, and clean isolated-installation verification.
- Explicit public, internal, and legacy-compatibility package boundaries plus
  reusable CLI-independent document, validation, bounded-edit, capability, and
  diagnostic APIs.
- Correctness-focused linting, full-suite branch coverage reporting, and a
  cross-platform Ubuntu/Windows build-install CI gate.

### Changed

- The existing `edit` CLI routes execution through the public service boundary
  while preserving parsing, rendering, exit-code, and legacy behavior.
- Runtime, installed metadata, artifact filenames, console output, reports, CI,
  and release-facing contracts now agree on package version `0.9.0a0`.
- The repository is installable as a pure-Python distribution without making
  tests, tools, reports, sample assets, or private data import packages.

### Verified

- Local release-readiness validation passes all 1,095 tests with one optional
  private-runtime skip and reports 88.26% combined statement/branch coverage.
- Fresh artifacts pass deterministic inspection with 71 wheel members,
  186 sdist members, and clean isolated wheel installation.
- Ubuntu and Windows GitHub Actions remain mandatory pre-merge evidence; they
  are not claimed as passed until the feature branch is pushed and both pull
  request jobs complete successfully.

### Safety and compatibility

- Registry schema remains `0.3`; schemas `0.2` and `0.3` remain supported.
- PMX edit-plan schema remains `1`, and only the existing three edit operation
  types remain authorized.
- Existing v0.8 import, CLI, diagnostic, and process contracts are retained.
- This architecture runway adds no structural PMX editing, model creation,
  bone/morph/physics CRUD, GUI, Smart Tools, plugin system, or AI feature.
- No PyPI publication is part of this release without separate explicit
  Maintainer approval.

## 0.8.5 - 2026-08-13

### Added

- Structured PMX validation issue reporting, cross-reference integrity
  regressions, and a deterministic adversarial PMX corpus.
- An immutable capability manifest describing the existing PMX support surface
  without adding a public command or plugin API.
- Cross-feature state-isolation coverage and representative v0.8.0-v0.8.4
  backward-compatibility contracts.

### Changed

- Verified writer/edit output handling is hardened against partial-write residue,
  destination alias/collision races, and source replacement during publication.
- Edit replay and dry-run/apply behavior are locked to deterministic parity, and
  round-trip JSON failures retain stable structured diagnostics.
- Release-facing metadata, README, CI gates, readiness checks, and publication
  checklist now target version 0.8.5.

### Verified

- Normal local discovery passes all 983 automated tests with the optional private
  runtime class skipped.
- Resource-safety auditing reconfirms bounded reads/counts, truncation handling,
  temporary-file/fsync cleanup, destination safety, source preservation, and
  deterministic replay.
- Tracked PMX files remain zero-byte placeholders; private runtime validation is
  explicit opt-in and preserves source size/SHA-256.

### Safety and compatibility

- Registry schema remains `0.3`; schemas `0.2` and `0.3` remain supported.
- PMX edit-plan schema remains `1`; the existing three edit operation types are
  unchanged.
- Version 0.8.5 adds no public CLI command, UI, PMX edit operation, or broader
  semantic editing authority.
- Existing v0.8 machine-facing contracts remain backward compatible and private
  assets remain outside the repository.

## 0.8.4 - 2026-08-13

### Added

- A typed named compatibility-profile foundation for PMX 2.0/2.1,
  UTF-16LE/UTF-8, additional UV counts 0-4, Unicode/zero-count fixtures, and
  uniform or mixed 1/2/4-byte index widths.
- Reader/scanner compatibility matrices that assert semantic parity rather than
  merely requiring generated files not to crash.
- Boundary regressions for the existing PMX version-tolerance policy, opaque
  bone/material flag preservation, and trailing opaque-byte handling.
- Writer/round-trip compatibility coverage requiring deterministic repeated
  serialization, parse/serialize/parse semantic equality, distinct output, and
  unchanged source bytes.
- Cross-feature generated integration covering `scan`, `doctor`, `bones`, `rig`,
  `roundtrip`, strict `edit-plan`, `edit --dry-run`, and
  `texture-portability`.
- An optional runtime-only private compatibility suite enabled through
  `MMD_REGISTRY_PRIVATE_PMX`, with temporary output/plan cleanup and source
  size/SHA-256 invariants.

### Changed

- Release CI now runs the v0.8.4 compatibility modules on both Ubuntu and
  Windows while explicitly leaving the private runtime path empty.
- Release-facing version metadata, documentation, changelog, readiness checks,
  and publication checklist now target version 0.8.4.
- Registry schema remains `0.3`; no PMX edit operation type or public CLI
  command is added.

### Verified

- Normal local discovery passes all 915 automated tests with the optional
  private runtime class skipped.
- The optional private runtime gate passes all 3 compatibility tests when
  explicitly enabled; full discovery then passes 918 tests.
- The private runtime gate preserves source size and SHA-256, writes round-trip
  output only under a temporary directory, uses `edit --dry-run` for edit
  preview, and removes all generated temporary directories.
- Generated compatibility evidence covers PMX 2.0/2.1, both supported
  encodings, additional UV counts 0-4, all six index-size fields, Unicode,
  zero-count sections, BDEF1/QDEF representative deformation, deterministic
  writer behavior, and cross-feature composition.

### Safety and compatibility

- Registry schema remains `0.3`; schemas `0.2` and `0.3` remain supported.
- Version 0.8.4 is a compatibility/stabilization release and does not expand
  the bounded PMX editing surface.
- Scanner warnings for preserved trailing opaque bytes do not claim semantic
  understanding of that data.
- Existing tolerated raw PMX version values remain a documented compatibility
  policy; canonical serialization may be semantically equal without being
  byte-identical to such non-canonical input.
- No private PMX, texture, generated output, absolute local path, model name, or
  derived production binary is committed or redistributed.

## 0.8.3 - 2026-08-12

### Added

- Host-independent lexical texture-path semantics that preserve each declared
  PMX path separately from normalized or candidate representations.
- Deterministic portability reports that separate lexical classification from
  filesystem evidence and distinguish referenced from unreferenced textures.
- Safe texture rewrite proposals for deterministic, model-relative candidates,
  including bounded parent collapse and exact on-disk component spelling checks.
- A bridge from safe rewrite proposals into the existing `SetTexturePath` and
  strict `PmxEditPlan` workflow without adding a new edit operation type.
- A `texture-portability` CLI workflow with stable text/JSON reporting and
  optional `--plan-out` generation of a new strict JSON edit plan.
- Generated portability and CLI regression matrices covering canonical paths,
  backslashes, bounded parents, case mismatches, missing files, parent escapes,
  blocked referenced dependencies, plan no-overwrite, and source-change refusal.

### Changed

- Legacy dependency diagnostics and strict edit path policy now reuse shared pure
  lexical facts while retaining their intentionally different acceptance rules.
- Release-facing documentation and CI now include the texture-portability command
  and focused portability/rewrite regression gates.

### Verified

- The complete local suite passes all 884 automated tests.
- The focused portability, edit-plan, doctor, and legacy CLI regression gate
  passes all 114 tests.
- Generated plan output strict-loads through the existing edit-plan loader and
  carries the SHA-256 of the PMX source analyzed by the workflow.
- Source and texture fixture bytes remain unchanged during portability analysis
  and plan generation.

### Safety and compatibility

- Registry schema remains `0.3`; schemas `0.2` and `0.3` remain supported.
- Version 0.8.3 adds no new PMX edit operation types.
- The portability workflow never writes a PMX model and never copies, moves,
  renames, converts, or deletes texture files.
- Referenced blocked dependencies prevent partial plan emission; unreferenced
  blockers remain visible without inventing a rewrite.
- Case-insensitive host filesystems cannot silently authorize case-repair
  rewrites because candidate evidence requires exact component spelling.
- Plan generation binds to the source with SHA-256 checks before and after
  analysis and refuses emission if the PMX changes.
- No private PMX, texture, generated output, absolute local path, or derived
  production binary is committed or redistributed.

## 0.8.2 - 2026-08-12

### Added

- A deterministic PMX edit-operation catalog derived from the authoritative
  supported operation types and JSON-facing field metadata.
- Pure safe edit-plan template generation, including a skeleton and
  operation-specific starters that require no PMX source.
- Deterministic plan explanation reporting operation order/index, type, target
  identity, and intended field names without executing the plan.
- A dedicated `edit-plan` CLI namespace with `catalog`, `template`, and
  `explain` actions plus stable Unicode-safe text/JSON output.
- An authoring failure/regression matrix covering malformed UTF-8/JSON,
  duplicate members, NaN/Infinity, strict type/schema failures, template
  misuse, duplicate targets, privacy behavior, and PMX-I/O blockade.

### Changed

- Supported-operation plan errors can retain canonical operation-type context
  in addition to operation index and deterministic JSON path.
- `edit-plan explain` forwards that context through the existing structured
  diagnostic contract while legacy `edit` diagnostic rendering remains
  unchanged.
- Release-facing documentation, CI help checks, and focused safety gates now
  include the edit-plan authoring workflow.

### Verified

- The complete local suite passes all 840 automated tests.
- Focused authoring and legacy edit regression tests pass together.
- Authoring-only commands are regression-tested against PMX scan/apply/write
  calls and leave a sentinel PMX byte-identical.
- Redirected Unicode template and validation-error output is valid UTF-8.

### Safety and compatibility

- Registry schema remains `0.3`; schemas `0.2` and `0.3` remain supported.
- Version 0.8.2 adds no new PMX edit operation types.
- Starter templates are intentionally incomplete and cannot masquerade as
  executable plans under the strict loader.
- `edit-plan catalog` and `template` need no PMX source; `explain` reads only
  strict plan JSON and does not expose intended values or the expected hash.
- No PMX reader, writer, engine, preview, or output-commit behavior is expanded.
- No private PMX, texture, generated output, absolute local path, or derived
  production binary is committed or redistributed.

## 0.8.1 - 2026-08-12

### Added

- Structured PMX edit diagnostics with stable codes, pipeline phases, messages,
  operation index/type context, and deterministic JSON paths.
- A privacy-safe private-model failure-validation harness covering valid
  dry-run, invalid plan diagnostics, source-hash mismatch, input/output alias
  refusal, source integrity, and temporary-residue checks.
- Negative-path safety regression coverage for serialization, reparse,
  semantic verification, temporary payload hashing, fsync, source reads,
  overwrite preservation, and source replacement.

### Changed

- Strict edit-plan decoding now distinguishes malformed UTF-8/JSON, empty
  documents, duplicate JSON members, and non-standard numeric constants from
  schema/operation validation failures.
- Expected `edit` CLI failures now emit stable text diagnostics or one
  backward-compatible JSON object with a nested structured `error` field,
  while unexpected edit failures are sanitized at the process boundary.
- Atomic edit output now captures the source filesystem identity before reading
  and verifies that identity together with source SHA-256 immediately before
  output commit.

### Verified

- The complete local suite passes all 773 automated tests.
- A production-size PMX 2.0 UTF-16LE private model passed the negative failure
  matrix with matching source SHA-256 before/after, no temporary residue, and
  no persisted edited private asset.
- Plan validation failure, source-hash mismatch, and input/output alias refusal
  produced the expected stable diagnostic phases without modifying the source.

### Safety and compatibility

- Registry schema remains `0.3`; schemas `0.2` and `0.3` remain supported.
- Version 0.8.1 adds no new edit operation types and does not expand the
  bounded PMX editing surface introduced in 0.8.0.
- Existing successful edit output and legacy JSON error fields remain
  compatible while structured diagnostics are added.
- No private PMX, texture, generated edited output, absolute local path, or
  derived production binary is committed or redistributed.

## 0.8.0 - 2026-08-09

### Added

- Immutable edit plans, typed model/texture/material operations, and ordered
  before/after audit records independent from CLI and filesystem layers.
- Pure metadata editing for all four PMX model-information fields with exact
  UTF-8 and UTF-16LE encoding validation and explicit no-op handling.
- Safe replacement of one existing indexed texture path with portable relative
  path policy and no add, delete, reorder, or texture-file operation.
- Existing material name, memo, texture/sphere/toon reference, diffuse,
  specular, ambient, drawing flag, edge color, and edge-scale editing without
  exposing material surface partition changes.
- A strict JSON edit-plan schema with exact JSON types, unknown-field and
  duplicate-target rejection, contextual operation paths, Unicode support, and
  optional expected source SHA-256.
- A complete pure edit engine with deterministic audit merging, final-document
  validation, serialize/reparse semantic verification, and stable text/JSON
  previews.
- An `edit` CLI command supporting no-output `--dry-run`, stable Unicode-safe
  text/JSON reports, explicit distinct output, and opt-in `--overwrite`.
- Verified atomic output with input/output alias rejection, symlink and hardlink
  detection, no-clobber creation, temporary-file cleanup, source path/hash
  re-verification, and stable exit codes.
- A generated edit matrix covering PMX 2.0/2.1, UTF-8/UTF-16LE, uniform and
  mixed 1/2/4-byte indices, deterministic output, and all seven combinations
  of model, texture, and material operation categories.
- An ephemeral private-model validation harness that creates and removes its
  plan/output automatically, verifies only intended changes, checks every
  unrelated section and reference, and emits reports without absolute paths.
- Ubuntu and Windows release gates for edit command help, compatibility matrix,
  private-validation harness tests, and the complete 740 automated tests.

### Verified

- All 31 generated header/index/category edit combinations produced identical
  repeated previews, audit ordering, serialized bytes, and verified output.
- A private production model using PMX 2.0 and UTF-16LE passed metadata plus
  material text/property editing with three exact changed fields.
- The private production model retained its 4,912,416-byte source size and
  matching before/after SHA-256 while preserving 31,387 vertices, 114,390
  surface indices, 11 texture declarations, 25 materials, 342 bones, 59
  morphs, 12 display frames, 221 rigid bodies, and 299 joints.
- Private output reparsing, complete reference validation, intended semantic
  equality, unrelated-section identity, texture-file immutability, and
  temporary plan/output cleanup all passed.
- The local release suite passed all 740 tests without copyrighted binary
  fixtures or private production assets in the repository.

### Safety and compatibility

- Registry schema remains `0.3`; schemas `0.2` and `0.3` remain supported.
- Existing `validate`, `hash`, `inspect`, `scan`, `roundtrip`, `doctor`, `bones`,
  and `rig` behavior remains compatible.
- PMX input is always read-only; `edit` output must remain distinct even when
  `--overwrite` is supplied.
- Version 0.8 does not edit vertices, UVs, weights, bones, IK, morphs, display
  frames, physics, texture/material list structure, or material surface counts.
- No private PMX, texture, output, absolute local path, or derived binary was
  committed or redistributed.

## 0.7.0 - 2026-08-09

### Added

- A complete immutable `PmxDocument` retaining header settings, model text,
  geometry and deform payloads, textures, materials, bones and IK, morph
  offsets, display frames, rigid bodies, joints, soft bodies, and trailing
  data required for serialization.
- Modular typed PMX section readers and a complete document loader independent
  from CLI, scanner-presentation, and UI layers.
- A deterministic PMX writer with little-endian output, UTF-8 and UTF-16LE
  encoding, PMX 2.0 and 2.1 section rules, and 1/2/4-byte index widths.
- Cross-section validation for counts, index capacity, references, versioned
  payloads, text encoding, finite floats, flag-controlled bone data, material
  surface coverage, morph offsets, IK, and physics records.
- Failure-safe file output that validates before writing, refuses accidental
  overwrite by default, and uses atomic replacement for explicit overwrite.
- A reusable `roundtrip_pmx` API that verifies parse → serialize → parse
  semantic equality before creating a distinct output file.
- A `roundtrip` CLI command with text and JSON reports, explicit input and
  output paths, immutable-input policy, alias detection, and opt-in
  `--overwrite` for a separate output.
- A generated round-trip matrix covering PMX 2.0/2.1, UTF-8/UTF-16LE, uniform
  and mixed 1/2/4-byte indices, BDEF1/BDEF2/BDEF4/SDEF/QDEF, all supported
  morph types, materials, bones, IK, display frames, rigid bodies, every joint
  type, and soft bodies.
- Ubuntu and Windows GitHub Actions validation for the complete release suite.
- Release-readiness coverage and a publication checklist, bringing the suite
  to 563 automated tests without copyrighted binary fixtures.

### Verified

- All generated fixtures pass semantic parse → serialize → parse comparison,
  deterministic repeat serialization, and byte-stability checks.
- A private production-size PMX 2.0 UTF-16LE model containing 31,387 vertices,
  38,130 triangles, 342 bones, 59 morphs, 221 rigid bodies, and 299 joints
  passed complete reference validation and semantic round-trip comparison.
- The private model produced byte-identical 4,912,416-byte source and output
  files with the same SHA-256 digest; the input remained unchanged and the
  temporary output was removed.
- Unicode input/output paths and JSON output were verified through redirected
  Windows streams.

### Safety and compatibility

- Registry schema remains `0.3`; schemas `0.2` and `0.3` remain supported.
- Existing `validate`, `hash`, `inspect`, `scan`, `doctor`, `bones`, and `rig`
  behavior remains compatible and read-only for model inputs.
- PMD 1.0 remains supported for header inspection only.
- PMX writing is explicit and copy-only: the writer does not repair, rename,
  reparent, reweight, or modify an input model in place.
- The private production model and its textures were not committed or
  redistributed.

## 0.6.0 - 2026-08-08

### Added

- A read-only Rig Analyzer that resolves bounded canonical semantics for PMX
  bones while preserving their original local and universal names.
- Immutable semantic results containing role, side, category, confidence tier,
  matched aliases, and deterministic evidence.
- Shared Unicode normalization for width, whitespace, case, separators,
  camel-case words, acronyms, digits, and common naming suffixes.
- A replaceable Japanese and English semantic profile with conservative
  aliases for core MMD roles, IK controls, and helper or deform variants.
- Safe ambiguity handling that leaves unsupported or conflicting bones
  unresolved instead of creating high-confidence guesses.
- Iterative hierarchy-aware semantic inference with fixed-point processing for
  deep rigs, invalid parents, and cycles.
- Structured rig diagnostics for missing and duplicate roles, ambiguity,
  left/right asymmetry, suspicious hierarchy relationships, side conflicts,
  invalid IK references, and unclassified bones.
- Deterministic complete rig reports, summary counts, and canonical bone maps
  that are immutable and JSON serializable.
- A `rig` CLI command with text and JSON reports, `--unmapped` and `--role`
  filters, and standalone UTF-8 JSON export through `--export-map`.
- Stable Rig Analyzer exit codes for clean reports, actionable diagnostics,
  usage errors, malformed inputs, and internal failures.
- Programmatically generated semantic, inference, diagnostic, analysis, and
  CLI fixtures, bringing the suite to 475 automated tests.

### Verified

- Analyzed a production-size PMX 2.0 model containing 342 bones without
  modifying or redistributing the model.
- Resolved 102 bones across 37 canonical role keys while conservatively
  retaining 240 custom or unsupported bones as unresolved.
- Reduced actionable diagnostics from 31 warnings to 2 evidence-backed
  warnings, with zero errors and no false duplicate, side-conflict, or
  asymmetry diagnostics.
- Verified semantic text and JSON output plus standalone UTF-8 canonical
  bone-map export on Windows.

### Compatibility

- Registry schema remains `0.3`.
- Registry schemas `0.2` and `0.3` remain supported.
- PMX 2.0 and PMX 2.1 remain supported for complete read-only structural scan,
  Bone Explorer, and Rig Analyzer workflows.
- PMD 1.0 remains supported for header inspection only.
- Legacy validation command syntax and all existing CLI commands remain
  supported.

## 0.5.0 - 2026-08-08

### Added

- A read-only Bone Explorer for inspecting complete PMX 2.0 and PMX 2.1 bone
  data without modifying model files.
- Compact one-row-per-bone table output with indices, display names, original
  names, parents, and readable capability tags.
- Safe display-name resolution that prefers normalized universal names, falls
  back to local names, and remains replaceable for future naming policies.
- Safe parent-child hierarchy construction with deterministic ordering and
  diagnostics for duplicate indices, missing parents, and cycles.
- Non-recursive hierarchy building and tree rendering for deeply nested rigs.
- Detailed per-bone reports for names, parent and tail references, positions,
  transform layers, and enabled or disabled capabilities.
- Unicode-normalized bone search across display, local, and universal names,
  plus exact index forms such as `339`, `#339`, and `[339]`.
- IK-only filtering that composes with name and index searches.
- A `bones` CLI command with table, tree, detail, search, IK-only, text, and
  JSON modes.
- UTF-8-safe Bone Explorer output for redirected Windows standard streams.
- Programmatically generated Bone Explorer fixtures and release-readiness
  coverage, bringing the suite to 367 automated tests.

### Verified

- Explored a production-size PMX 2.0 model containing 342 bones.
- Rendered all 342 bones as both a compact table and a complete hierarchy.
- Resolved two hierarchy roots with zero hierarchy issues.
- Verified exact-index detail lookup, Unicode text output, and JSON output.
- Verified Unicode-normalized name search and IK-only filtering against the
  production model.

### Compatibility

- Registry schema remains `0.3`.
- Registry schemas `0.2` and `0.3` remain supported.
- PMX 2.0 and PMX 2.1 remain supported for complete read-only structural
  scanning.
- PMD 1.0 remains supported for header inspection only.
- Legacy validation command syntax remains supported.

## 0.4.0 - 2026-08-06

### Added

- Bounded little-endian binary reader for untrusted model files.
- Complete read-only PMX 2.0 structural scanning.
- PMX 2.1 structural scanning, including soft bodies.
- Structural summaries for vertices, surfaces, textures, materials, bones,
  IK, morphs, display frames, rigid bodies, joints, and soft bodies.
- Complete-file accounting with file size, consumed bytes, remaining bytes,
  trailing-byte warnings, and scan-completion state.
- Texture reference summaries across material, sphere, and custom toon slots.
- `scan` CLI command with text and JSON output.
- Texture dependency diagnostics for missing, non-file, absolute,
  non-portable, and outside-model-directory paths.
- `doctor` CLI command combining structural scanning and filesystem dependency
  diagnostics.
- Stable exit codes for successful scans, malformed models, unusable paths,
  and unexpected internal failures.
- UTF-8 standard-stream configuration so redirected Unicode text and JSON work
  on Windows terminals.
- Programmatically generated PMX 2.0 and 2.1 structural fixtures and extensive
  parser, CLI, diagnostics, and release-readiness tests.

### Verified

- Successfully scanned a production-size PMX 2.0 model of 4,912,416 bytes.
- Consumed the complete file with zero trailing bytes.
- Parsed 31,387 vertices, 38,130 triangles, 342 bones, 59 morphs,
  221 rigid bodies, and 299 joints.
- Resolved all 11 declared and referenced texture files without warnings or
  errors.
- Exported full scan and doctor results as valid UTF-8 JSON on Windows.

### Compatibility

- Registry schema remains `0.3`.
- Registry schemas `0.2` and `0.3` remain supported.
- PMD 1.0 remains supported for header inspection only.
- Legacy validation command syntax remains supported.

## 0.3.0 - 2026-08-05

- Added schema `0.3` integrity metadata.
- Added streaming SHA-256 calculation and verification.
- Added safe PMX 2.0/2.1 and PMD 1.0 header inspection.
- Added `hash` and `inspect` CLI commands.
- Added portable integrity and inspection report fields.

## 0.2.0

- Added creator and source provenance.
- Added credit generation and private, publish, and commercial validation
  modes.
- Added portable JSON reports and automated tests.

## 0.1.0

- Added the initial YAML asset registry and validation workflow.
