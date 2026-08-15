# Changelog

All notable changes to MMD Asset & License Registry are documented here.

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
