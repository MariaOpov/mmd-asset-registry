# Changelog

All notable changes to MMD Asset & License Registry are documented here.

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
