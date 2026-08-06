# Changelog

All notable changes to MMD Asset & License Registry are documented here.

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
