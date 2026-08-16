# MMD Asset & License Registry

A lightweight, safety-first Python toolkit for tracking MMD asset provenance,
creator credits, local source files, SHA-256 integrity, model metadata,
PMX structure, texture dependencies, bone hierarchies, bone semantics,
rig diagnostics, canonical bone maps, complete typed PMX documents, and known
usage restrictions. It also provides bounded declarative editing for model
metadata, indexed texture paths, and existing material properties.

The project is designed as a validation and diagnostics gate before assets
enter an automated MMD, Blender, or anime-video pipeline. All established
inspection and analysis commands keep model and texture inputs read-only. The
explicit `roundtrip` and `edit` commands can write verified PMX output to a
distinct path; neither command writes in place, repairs data, or redistributes
an asset.

## Current version

```text
Tool version: 0.9.0
Release label: v0.9.0
Latest registry schema: 0.3
Supported registry schemas: 0.2, 0.3
```

Tool version and registry schema are intentionally independent. The Git and
GitHub release label `v0.9.0` matches the PEP 440 Python package version
`0.9.0`. This release adds the reference-safe structural analysis and preview
foundation while deliberately keeping public structural write disabled;
registry schema `0.3` remains unchanged.

Schema `0.2` remains supported for backward compatibility. Integrity and model
header inspection are applied only to schema `0.3` registry entries.

## pre-0.9.0 architecture runway

The `pre-0.9.0` release establishes explicit package boundaries while keeping
the v0.8 safety contract intact:

- Public CLI-independent namespaces for PMX documents, validation, bounded
  editing, capabilities, diagnostics, and reusable services
- An explicit private implementation namespace and preserved legacy import and
  process entry points
- An installed `mmd-asset-registry` console command alongside the existing
  `check_assets.py` launcher
- Wheel and sdist metadata, deterministic archive inspection, and clean
  isolated-installation verification
- Correctness-focused linting, full-suite branch coverage reporting,
  compatibility gates, and Ubuntu/Windows build-install CI

The local release-readiness baseline passes 1,095 tests with one optional
private-runtime skip, reports 88.26% combined statement/branch coverage, and
inspects a 71-member wheel plus a 186-member sdist before clean installation.
Both GitHub Actions operating-system jobs must still pass on the pull request
before merge or release.

This runway does not add structural PMX editing, model creation, bone/morph/
physics CRUD, a GUI, Smart Tools, plugins, or AI features. It packages and
stabilizes the already bounded behavior so later v0.9 work has reviewable
service, diagnostic, compatibility, quality, and release boundaries.

## Version 0.9.0 reference-safe structural foundation

Version 0.9.0 promotes the v0.9 foundation to the final `0.9.0` package version
while keeping structural execution deliberately narrower than the internal
implementation layers:

- A complete immutable PMX reference taxonomy, reference graph, diagnostics,
  and conservative direct-impact queries cover vertex, texture, material,
  bone, morph, and rigid-body targets.
- Public `analyze_references()` and `analyze_reference_node()` services expose
  deterministic read-only reference evidence without reparsing, repairing, or
  mutating a document.
- Immutable index-remap and structural collection-transform primitives support
  reference-safe reorder/delete intent for existing vertices, textures,
  materials, bones, morphs, and rigid bodies. Insertion remains unauthorized.
- Geometry/material, deform/IK, morph/display-frame, and physics references are
  remapped through one certified structural orchestrator with complete
  invariant and reference-integrity checks.
- Deterministic structural preview/audit evidence is available through the
  public `PmxStructuralCollectionEdit`, `PmxStructuralPreviewRequest`,
  `PmxStructuralPreviewResult`, and `preview_structural_edit()` service surface.
- Verified structural serialization/output remains an internal kernel. The
  public capability manifest intentionally reports `structural_preview=True`,
  `structural_write=False`, and `structural_contract="reference_safe_preview"`.

The structural path fails closed rather than guessing: opaque trailing data is
rejected for changed structural transforms, invalid references are not replaced
with sentinels, index widths are not resized automatically, insertion is not
synthesized, and caller-owned source documents/files are not mutated. No public
model-creation, arbitrary CRUD, IK authoring, physics simulation, mesh/UV
editing, Smart Tool, plugin, GUI, or AI authority is introduced by this release.

The final-release baseline contains 1,495 automated tests with one optional
private-runtime skip and reports 88.86% combined statement/branch coverage.
The package gate builds and inspects an 85-member wheel and 220-member sdist,
verifies a disposable clean wheel installation, and exercises installed
reference-analysis plus structural-preview services. The same build/install
workflow passes on both Ubuntu and Windows. Optional private-model validation is
read-only with respect to its source and is never part of distributed artifacts.

## Why this project exists

MMD models and related assets are often collected from different creators,
distribution pages, archives, and communities. Important information can later
become separated from the downloaded files:

- Who created the asset
- Where it originally came from
- What credit should appear in a published video
- Whether editing, redistribution, or commercial use has known restrictions
- Whether the local file still exists and matches the registered copy
- Whether a `.pmx` or `.pmd` file has a readable model header
- Whether a PMX file is structurally readable from beginning to end
- Which texture paths the model declares and actually references
- Whether referenced textures exist and remain portable with the model
- How hundreds of PMX bones are named and connected
- Which bones provide IK or other rig capabilities
- Which canonical semantic roles the rig can resolve safely
- Which hierarchy, symmetry, ambiguity, or IK issues need review
- Whether a complete PMX document can be validated and serialized safely
- Which pipeline character uses the asset

The registry records this information in YAML and validates it before a
pipeline continues. The scanner and doctor add technical evidence, but the
tool does not automatically determine legal permission or replace review of
the creator's original terms.

## Version 0.8 features

Version 0.8.0 introduces the first safety-bounded PMX editing core:

- Immutable edit plans and operations for the four model-information fields,
  one existing indexed texture path, and editable fields of one existing
  material
- Material text, texture/sphere/toon references, diffuse/specular/ambient
  values, drawing flags, edge color, and edge scale editing
- A strict UTF-8 JSON plan schema with exact types, unknown-field rejection,
  duplicate-target rejection, and optional `expected_source_sha256`
- Pure in-memory transformations that leave the source `PmxDocument` unchanged
  and emit deterministic typed before/after audit records
- Semantically verified text and JSON previews through `edit --dry-run`
- Safe write mode that requires a distinct `.pmx` output, refuses overwrite by
  default, detects symlink and hardlink aliases, and atomically commits only
  verified serialized bytes
- Source-path and SHA-256 verification immediately before output commit, with
  temporary-file cleanup on validation, serialization, or filesystem failure
- Generated edit coverage across PMX 2.0/2.1, UTF-8/UTF-16LE, uniform and mixed
  1/2/4-byte index widths, and every model/texture/material category
  combination
- An ephemeral private-model validation harness that checks exact intended
  changes, unchanged sections and references, untouched texture files, source
  integrity, and automatic temporary plan/output cleanup
- Ubuntu and Windows CI coverage plus 740 automated unit tests at release
  readiness

Version 0.8.5 finalizes the v0.8 stabilization line before the v0.9 gate:

- Structured PMX validation issues, cross-reference integrity coverage, and a
  deterministic adversarial corpus strengthen malformed-input diagnostics
- Verified writer/edit output paths are hardened against partial-write residue,
  destination alias/collision races, and source identity changes
- Deterministic edit replay, dry-run/apply parity, and round-trip JSON diagnostic
  regressions freeze machine-facing behavior
- An immutable PMX capability manifest, repeated cross-feature state-isolation
  coverage, and representative v0.8.0-v0.8.4 backward-compatibility contracts
  define the stable core available to the next release line
- Resource-safety auditing reconfirms bounded reads/counts, temporary-file
  cleanup, optional private-runtime gating, and zero-byte tracked PMX placeholders
- Normal discovery passes 983 automated tests with the optional private runtime
  class skipped

Version 0.8.4 broadens PMX compatibility evidence without changing the public
editing surface:

- Named generated compatibility profiles cover PMX 2.0/2.1, UTF-16LE/UTF-8,
  additional UV counts 0 through 4, uniform and mixed 1/2/4-byte index widths,
  Unicode data, zero-count sections, BDEF1, and PMX 2.1 QDEF
- Typed reader and structural scanner results are cross-checked for header,
  section-count, Unicode bone, deform, and index-width semantics
- Boundary regressions lock the existing version-tolerance policy, preserve
  opaque bone/material flag bits, and distinguish trailing-byte preservation
  from semantic understanding
- Writer and round-trip profiles require parse -> serialize -> parse semantic
  equality, deterministic repeated serialization, distinct output, unchanged
  source bytes, and exact preservation of opaque trailing data
- Cross-feature integration drives representative generated PMX data through
  `scan`, `doctor`, `bones`, `rig`, `roundtrip`, strict `edit-plan`,
  `edit --dry-run`, and `texture-portability`
- Optional private-model compatibility tests are activated only through
  `MMD_REGISTRY_PRIVATE_PMX`; normal CI leaves it empty and skips that runtime
  class without committing a private path or asset
- Normal release-readiness discovery runs 915 automated tests with the optional
  private runtime class skipped; the local private-model gate runs 918 tests
  when that class is explicitly enabled

Version 0.8.3 adds deterministic texture portability and path workflow
without expanding the PMX editing surface:

- Host-independent lexical classification for relative, POSIX absolute, Windows
  absolute, drive-relative, rooted, and UNC texture declarations
- Original declarations preserved separately from normalized paths and rewrite
  candidates so host path handling cannot silently reinterpret PMX data
- Filesystem evidence separated from lexical semantics, including containment,
  existence, regular-file state, and exact on-disk component spelling
- Safe rewrite proposals only when the candidate is deterministic and
  unambiguous; no fuzzy matching, extension guessing, case repair, or spelling
  heuristics
- Bounded lexical collapse for model-relative parent references while parent
  escapes remain blocked
- Existing `SetTexturePath` and strict `PmxEditPlan` reuse for generated plans;
  no new edit operation type is introduced
- A `texture-portability` CLI with stable text/JSON reporting plus optional
  `--plan-out` output that never overwrites an existing plan
- Referenced blocked dependencies prevent partial plan emission; blocked
  unreferenced declarations remain visible as warnings
- Source SHA-256 binding before and after analysis so plan generation is refused
  when the PMX changes during the workflow
- Generated regression coverage across lexical, filesystem, rewrite, strict-plan
  bridge, CLI safety, and host case-sensitivity boundaries
- 884 automated tests at the version 0.8.3 release-readiness checkpoint

Version 0.8.2 adds edit-plan authoring and explanation UX without adding new
edit operation types:

- A deterministic operation catalog derived from the authoritative supported
  operation types and their JSON-facing field metadata
- Safe plan skeletons and operation-specific starter templates generated
  without a PMX source
- Intentionally incomplete templates that remain non-executable until the
  top-level `_template` marker is removed and every `$placeholder` object is
  replaced with a concrete strict-JSON value
- Deterministic plan explanation reporting operation index, type, target
  identity, and intended field names without executing the plan
- Privacy-bounded explanations that do not reveal intended field values,
  expected source SHA-256 values, or private/absolute paths carried as values
- A dedicated `edit-plan` CLI namespace with `catalog`, `template`, and
  `explain` actions plus stable text/JSON output
- Authoring failures reusing the existing `plan_read`, `plan_decode`, and
  `plan_validate` diagnostic phases with deterministic index/type/path context
  when a supported operation type is known
- Regression coverage proving authoring-only commands do not scan, apply,
  serialize, or write PMX data and leave a sentinel PMX byte-identical
- 840 automated tests at the version 0.8.2 release-readiness checkpoint

Version 0.8.1 hardens that editing core without adding new edit operation
types:

- Structured edit diagnostics with stable `code`, `phase`, message, operation
  index/type, and JSON-path context
- Separate strict plan-decode and plan-validation failures for malformed
  UTF-8/JSON, duplicate members, non-standard numeric constants, empty
  documents, and schema errors
- Backward-compatible CLI JSON failures that retain legacy fields while adding
  one deterministic nested `error` object
- Expected edit failures without tracebacks, plus sanitized process-boundary
  reporting for unexpected edit failures
- Negative-path regression coverage proving hash mismatch, serialization,
  reparse, semantic verification, temporary payload, fsync, source read, and
  alias failures cannot expose partial output
- Pre-commit filesystem identity plus SHA-256 verification so replacement of a
  source file with same-byte content is still detected
- Privacy-safe real-model failure validation covering valid dry-run, invalid
  plan diagnostics, source-hash mismatch, alias refusal, source integrity, and
  zero temporary residue
- 773 automated tests at the version 0.8.1 release-readiness checkpoint

All version 0.7 capabilities remain available.

## Version 0.7 features

Version 0.7.0 establishes the PMX document and serialization foundation needed
for a future editor:

- A complete immutable `PmxDocument` retaining every payload required to write
  PMX 2.0 and PMX 2.1 files
- Typed section records for geometry and all deform types, textures, materials,
  bones and IK, every supported morph offset, display frames, rigid bodies,
  joints, and soft bodies
- Modular document loading independent from CLI and scanner presentation code
- Deterministic little-endian serialization with UTF-8 and UTF-16LE support
- Correct signed and unsigned 1/2/4-byte index handling
- Cross-section validation for counts, capacities, references, material surface
  coverage, versioned records, finite floats, text encoding, and flag payloads
- Validation-before-write behavior, default overwrite refusal, and atomic
  replacement for explicitly selected separate outputs
- Semantic parse → serialize → parse verification before CLI output is created
- The `roundtrip` command with text/JSON results and opt-in `--overwrite`
- Generated PMX 2.0/2.1 × encoding × index-width fixtures, including a mixed
  index-width case and all deform and morph types
- Private real-model verification without committing or redistributing the
  production model
- Ubuntu and Windows CI coverage
- 563 automated unit tests at the release-readiness checkpoint

All version 0.6 capabilities remain available.

## Version 0.6 features

Version 0.6.0 introduces the read-only Rig Analyzer:

- Deterministic semantic results containing canonical role, side, category,
  confidence tier, matched aliases, and explainable evidence
- Unicode width, whitespace, case, separator, camel-case, acronym, and digit
  normalization shared by search and semantic analysis
- A bounded Japanese and English alias vocabulary with replaceable semantic
  profiles instead of model-specific hard-coding
- Conservative helper, deform, twist, cancel, IK-parent, and EX conventions
- Safe ambiguity handling that returns `unknown` instead of inventing a role
- Iterative hierarchy-aware inference that handles deep rigs and cycles without
  recursion or mutation of scanner records
- Structured diagnostics for missing and duplicate roles, ambiguity,
  left/right asymmetry, hierarchy problems, side conflicts, IK references, and
  unclassified bones
- Immutable, deterministic, JSON-serializable analysis, diagnostic, summary,
  and canonical bone-map models
- A `rig` CLI command with text and JSON reports, unmapped and role filters,
  and standalone UTF-8 JSON bone-map export
- Stable exit codes for clean rigs, actionable diagnostics, usage failures,
  malformed inputs, and unexpected internal failures
- 475 automated unit tests at the real-model validation checkpoint

All version 0.5 capabilities remain available.

## Version 0.5 features

Version 0.5.0 introduces the Bone Explorer:

- Compact one-row-per-bone table output
- Safe display-name fallback from universal to local names
- Replaceable name-resolver architecture for future multilingual naming
- Friendly capability tags without changing raw scanner data
- Parent display-name resolution, including forward references
- Safe parent-child hierarchy construction
- Detection and non-fatal handling of duplicate indices, invalid parents,
  self-parenting, and cycles
- Non-recursive hierarchy construction and tree rendering for deep rigs
- Individual bone detail reports with position, parent, tail, transform layer,
  and enabled/disabled capabilities
- Unicode-normalized, case-insensitive search across display, local, and
  universal names
- Exact index queries such as `339`, `#339`, and `[339]`
- Basic IK-only filtering that composes with name search
- Human-readable table, tree, detail, search, and IK CLI modes
- Stable JSON output for tables, hierarchies, and details
- UTF-8 redirected Bone Explorer output on Windows
- 367 automated unit tests at the real-model validation checkpoint

All version 0.4 capabilities remain available, including:

- Bounded binary reads for untrusted PMX data
- Complete read-only PMX 2.0 structural scanning
- PMX 2.1 scanning, including soft bodies
- PMX UTF-8 and UTF-16LE text decoding
- Section-level validation for vertices, surfaces, textures, materials, bones,
  IK, morphs, display frames, rigid bodies, joints, and soft bodies
- Cross-reference validation for model indices
- Complete-file byte accounting and trailing-byte warnings
- Aggregate section and texture-reference summaries
- Texture dependency filesystem diagnostics
- Missing and non-file texture detection
- Absolute, rooted, non-portable, and outside-model-directory path detection
- Dedicated `scan` and `doctor` CLI commands
- Human-readable and machine-readable JSON output
- UTF-8 redirected output for Unicode model names and paths on Windows
- Stable exit codes for scripts, CI, and pipeline gates
- Programmatically generated binary fixtures; no copyrighted model fixtures

Existing version 0.3 capabilities remain available, including registry
validation, provenance tracking, credit generation, SHA-256 integrity checks,
portable JSON reports, and PMX/PMD header inspection.

## Installation

Requirements:

- Python 3.12 or newer
- PyYAML 6.0 or newer

Create a virtual environment on Windows:

```bat
py -3.12 -m venv .venv
.\.venv\Scripts\activate.bat
```

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

## Command overview

Show top-level help:

```bash
python check_assets.py --help
```

Show the tool version:

```bash
python check_assets.py --version
```

Available commands:

```text
validate  Validate an asset registry
hash      Calculate or verify a file SHA-256 hash
inspect   Inspect a PMX or PMD model header
scan      Structurally scan a PMX model
roundtrip Write a verified PMX copy to a distinct output path
edit      Preview or safely write a strict declarative PMX edit plan
edit-plan Author or explain strict declarative PMX edit plans
texture-portability Analyze texture portability and propose safe rewrites
doctor    Scan a PMX model and diagnose texture dependencies
bones     Explore PMX bones as a table, tree, detail report, or JSON
rig       Resolve bone semantics, diagnose a rig, and build a bone map
```

Running without a command preserves the legacy behavior and performs registry
validation.

## Format support

| Capability | PMX 2.0 | PMX 2.1 | PMD 1.0 |
|---|---:|---:|---:|
| Header inspection | Yes | Yes | Yes |
| Complete structural scan | Yes | Yes | No |
| Complete document load and write | Yes | Yes | No |
| Verified round-trip copy | Yes | Yes | No |
| Safe declarative metadata/material edit | Yes | Yes | No |
| Texture dependency doctor | Yes | Yes | No |
| Bone Explorer | Yes | Yes | No |
| Rig Analyzer | Yes | Yes | No |

PMD 1.0 is currently supported for header inspection only. `scan`, `roundtrip`,
`edit`, `doctor`, `bones`, and `rig` reject PMD files instead of pretending to
perform a partial structural operation.

## Validate a registry

Explicit command syntax:

```bash
python check_assets.py validate --mode private
```

Legacy syntax remains supported:

```bash
python check_assets.py --mode private
```

Running without arguments also performs private validation:

```bash
python check_assets.py
```

Equivalent module command:

```bash
python -m mmd_registry.cli validate --mode private
```

Validation modes:

- `private` allows incomplete provenance and credit information while still
  reporting it.
- `publish` requires complete required credit information and rejects invalid
  placeholder model headers.
- `commercial` adds commercial-use checks and rejects unclear or prohibited
  commercial permission.

A JSON validation report is generated by default at:

```text
reports/validation_report.json
```

Disable it with:

```bash
python check_assets.py validate --mode private --no-report
```

Generate Markdown credits with:

```bash
python check_assets.py validate --mode private --credits
```

## Calculate SHA-256

Calculate a file hash:

```bash
python check_assets.py hash path/to/model.pmx
```

Verify an expected digest:

```bash
python check_assets.py hash path/to/model.pmx \
  --expected 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
```

Machine-readable output:

```bash
python check_assets.py hash path/to/model.pmx --json
```

Hashing reads the file in chunks instead of loading the complete file into
memory.

## Inspect a PMX or PMD header

Inspect a model file:

```bash
python check_assets.py inspect path/to/model.pmx
```

Example output:

```text
File: path/to/model.pmx
Status: ok
Format: PMX
Magic: PMX
Version: 2.1
Encoding: utf-8
Model name: Example Model
```

Machine-readable output:

```bash
python check_assets.py inspect path/to/model.pmx --json
```

The inspector reads only the model signature, version, global PMX header data,
and first model-name field. It does not claim to perform a complete structural
scan.

## Structurally scan a PMX model

Run a complete read-only PMX structural scan:

```bash
python check_assets.py scan path/to/model.pmx
```

Machine-readable output:

```bash
python check_assets.py scan path/to/model.pmx --json
```

On Windows, quote paths that contain spaces or Unicode characters:

```bat
set "MODEL=D:\MMD\Models\Character\model.pmx"
python check_assets.py scan "%MODEL%"
python check_assets.py scan "%MODEL%" --json > model-scan.json
```

The `scan` command reads and validates:

1. Signature, version, global settings, and model information
2. Vertices and deform records
3. Surface indices and triangle alignment
4. Texture path declarations
5. Materials and texture references
6. Bones, optional bone fields, IK chains, and IK links
7. Morphs and type-specific offsets
8. Display frames and frame elements
9. Rigid bodies
10. Joints
11. PMX 2.1 soft bodies, anchors, and pinned vertices

A successful complete scan reports:

- `file_size`
- `bytes_consumed`
- `bytes_remaining`
- `trailing_byte_count`
- `scan_complete`
- Aggregate section counts
- Referenced and unreferenced texture indices and paths

A valid file with bytes after the final known PMX section is returned as a
warning. A file truncated inside a required section is returned as an error and
does not claim completion.

The JSON result intentionally contains detailed structural records and can be
large for production models. Redirect it to a file when full details are
needed; use text output for a compact summary.

## Write a verified PMX round-trip copy

The `roundtrip` command writes an unchanged semantic copy. It requires separate
input and output paths, validates the complete document, and performs parse →
serialize → parse semantic verification before output is created:

```bash
python check_assets.py roundtrip path/to/input.pmx path/to/output.pmx
```

The command refuses to run when:

- The input is missing, not a file, not a `.pmx`, or malformed
- The output is not a `.pmx` path
- Input and output resolve to the same file, including hardlink or symlink
  aliases
- The output already exists and `--overwrite` was not explicitly supplied
- The output directory does not already exist
- Serialization changes the semantic document structure

Replace an existing separate output only with explicit permission:

```bash
python check_assets.py roundtrip path/to/input.pmx path/to/output.pmx --overwrite
```

Input and output aliases remain prohibited even with `--overwrite`; in-place
PMX editing is not supported. Explicit overwrite uses atomic replacement for
the separate output and never changes the input path.

Machine-readable reporting includes section counts, sizes, SHA-256 digests,
semantic equality, and whether the copy is byte-identical:

```bash
python check_assets.py roundtrip path/to/input.pmx path/to/output.pmx --json
```

Byte-identical output is verified when it occurs, but the architectural
contract is semantic and structural equivalence. The writer does not repair,
rename, reparent, translate, or otherwise reinterpret model data.

## Author and explain PMX edit plans

Version 0.8.2 adds an authoring-only `edit-plan` namespace. These commands do
not require a PMX model and do not execute an edit plan.

List the authoritative supported operation catalog:

```bash
python check_assets.py edit-plan catalog
python check_assets.py edit-plan catalog --json
```

Generate a safe plan skeleton:

```bash
python check_assets.py edit-plan template
```

Generate a starter for one supported operation:

```bash
python check_assets.py edit-plan template set_model_info
python check_assets.py edit-plan template set_texture_path
python check_assets.py edit-plan template update_material
```

Templates are intentionally non-executable. They contain a top-level
`_template` marker, and operation starters contain structured `$placeholder`
objects instead of executable scalar values. The strict loader rejects the
template until the marker is removed and all placeholders are replaced with
valid values.

Explain a completed strict JSON plan without loading a PMX:

```bash
python check_assets.py edit-plan explain edit.json
python check_assets.py edit-plan explain edit.json --json
```

Explanation preserves operation order and reports the zero-based operation
index, operation type, target identity, and intended field names. It does not
show intended field values, the expected source SHA-256 value, before/after
values, or execution/verification claims. Read, decode, and validation failures
reuse the stable `plan_read`, `plan_decode`, and `plan_validate` diagnostics.

## Analyze texture portability and propose safe rewrites

Version 0.8.3 adds `texture-portability`, a PMX/texture read-only analysis
workflow. It scans declared texture paths, separates lexical path semantics from
filesystem evidence, and reports deterministic rewrite proposals:

```bash
python check_assets.py texture-portability path/to/model.pmx
python check_assets.py texture-portability path/to/model.pmx --json
```

The workflow preserves the original PMX declaration separately from normalized
and candidate paths. Lexical classification is host-independent; filesystem
evidence is used only when the host can resolve the declaration without guessing.
Safe candidates require deterministic model-relative containment, an existing
regular file, exact on-disk component spelling, and acceptance by the existing
strict texture edit path policy.

The workflow intentionally does not perform fuzzy matching, extension guessing,
case repair, spelling repair, or silent parent clamping. Missing files, case
mismatches, parent escapes, unsupported rooted forms, and other ambiguous paths
remain blocked instead of being rewritten speculatively.

To author a strict JSON plan containing only safe existing `set_texture_path`
operations:

```bash
python check_assets.py texture-portability path/to/model.pmx --plan-out texture-fixes.json
```

`--plan-out` never overwrites an existing file. A referenced blocked dependency
prevents the entire plan from being emitted, so the command never writes a
partial "safe subset" while a required texture remains unresolved. Unreferenced
blocked declarations remain visible as warnings.

Generated plans reuse the existing strict edit-plan loader and include
`expected_source_sha256`. The PMX is hashed before and after portability
analysis; if the source changes, plan generation is refused. The command never
writes a PMX model and never copies, moves, renames, converts, or deletes a
texture file.

Preview a generated plan through the existing edit pipeline before writing any
separate PMX output:

```bash
python check_assets.py edit path/to/model.pmx --plan texture-fixes.json --dry-run
```

## Preview or write a safe PMX edit plan

The `edit` command accepts a strict UTF-8 JSON plan. Schema version `1` supports
model information, one existing indexed texture path, and existing material
text, references, and visual properties. A representative plan is:

```json
{
  "schema_version": 1,
  "expected_source_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "operations": [
    {
      "op": "set_model_info",
      "local_name": "Edited Model",
      "universal_comments": "Reviewed metadata"
    },
    {
      "op": "set_texture_path",
      "texture_index": 0,
      "path": "textures/body.png"
    },
    {
      "op": "update_material",
      "material_index": 0,
      "memo": "Reviewed material",
      "edge_scale": 1.0
    }
  ]
}
```

Preview every operation without creating or modifying an output:

```bash
python check_assets.py edit path/to/input.pmx --plan edit.json --dry-run
python check_assets.py edit path/to/input.pmx --plan edit.json --dry-run --json
```

Write a new distinct output after full validation and semantic verification:

```bash
python check_assets.py edit path/to/input.pmx path/to/output.pmx --plan edit.json
```

Replace an existing separate output only with explicit permission:

```bash
python check_assets.py edit path/to/input.pmx path/to/output.pmx --plan edit.json --overwrite
```

Write mode serializes entirely in memory, reparses and compares the intended
document, verifies that the source path and SHA-256 remain unchanged, writes a
temporary file in the output directory, and atomically commits it. Input and
output aliases remain forbidden with `--overwrite`. A failure before commit
does not expose a partial PMX output.

Version 0.8 does not add, delete, or reorder textures or materials. It does not
edit material surface partitions and does not edit vertices, bones, morphs,
display frames, IK, weights, or physics. Texture-path editing changes only the
selected PMX declaration; it never copies, renames, converts, or deletes a
texture file.

## Explore PMX bones

The `bones` command turns raw scanner records into a read-only skeleton view.
It does not rename, reposition, reparent, or write any bone back to the PMX
file.

Show the compact table:

```bash
python check_assets.py bones path/to/model.pmx
```

Each row contains the stable bone index, resolved display name, original local
name, parent reference, and readable capability tags. Display names use the
universal name when provided, then fall back to the local name and finally
`[unnamed]`. Whitespace is normalized for presentation without changing the
scanner record.

Example:

```text
Idx  Name             Original  Parent           Tags
---------------------------------------------------------------
0    Root             全ての親  -                Rotate, Move
1    Left Leg         左足      [0] Root         Rotate, Visible
2    Left Leg IK      左足ＩＫ  [0] Root         Move, Rotate, IK
```

Render the complete parent-child hierarchy:

```bash
python check_assets.py bones path/to/model.pmx --tree
```

The hierarchy builder safely handles roots and parents that appear later in
the PMX bone list. Duplicate indices, invalid parents, self-parenting, and
cycles are reported as non-fatal presentation issues. Construction and
rendering are iterative, so deep rigs do not depend on Python recursion.

Show one bone in detail:

```bash
python check_assets.py bones path/to/model.pmx --details 339
```

The detail report includes:

- Display, local, and universal names
- Parent and transform layer
- Bone-index or offset tail representation
- XYZ position
- Enabled and disabled rotation, translation, visibility, IK, inheritance,
  axis, physics, and external-parent capabilities

Search display, local, or universal names:

```bash
python check_assets.py bones path/to/model.pmx --search "Calf"
```

Search is case-insensitive and normalizes Unicode width and whitespace. Exact
index forms are also accepted:

```bash
python check_assets.py bones path/to/model.pmx --search 339
python check_assets.py bones path/to/model.pmx --search "#339"
python check_assets.py bones path/to/model.pmx --search "[339]"
```

Show only IK bones:

```bash
python check_assets.py bones path/to/model.pmx --ik-only
```

Name search and IK filtering can be combined:

```bash
python check_assets.py bones path/to/model.pmx --search "Left" --ik-only
```

Machine-readable output is available for the table, tree, details, search,
and IK modes:

```bash
python check_assets.py bones path/to/model.pmx --json
python check_assets.py bones path/to/model.pmx --tree --json
python check_assets.py bones path/to/model.pmx --details 339 --json
python check_assets.py bones path/to/model.pmx --search "Calf" --json
python check_assets.py bones path/to/model.pmx --ik-only --json
```

The JSON payload records the path, status, output mode, source bone count,
matched count, active filters, warnings, errors, and exactly one of `bones`,
`hierarchy`, or `detail` for the selected mode.

`--details` cannot be combined with `--tree`, `--search`, or `--ik-only`.
`--tree` cannot currently be combined with filters because removing parents
would make a filtered hierarchy misleading. Unsupported option combinations
return exit code `2` without scanning or modifying the model.

## Analyze a PMX rig

The `rig` command resolves a bounded set of canonical bone semantics, combines
name and hierarchy evidence, reports rig diagnostics, and builds a read-only
bone map. It preserves every original local and universal bone name and never
rewrites the PMX file.

Run the complete analysis:

```bash
python check_assets.py rig path/to/model.pmx
```

The text report summarizes resolved and unresolved bones, mapped canonical
roles, diagnostic severity counts, the canonical role index, and structured
issues requiring review.

Print the complete machine-readable analysis:

```bash
python check_assets.py rig path/to/model.pmx --json
```

Show only bones that remain semantically unresolved:

```bash
python check_assets.py rig path/to/model.pmx --unmapped
```

Select one normalized canonical role, including its side when applicable:

```bash
python check_assets.py rig path/to/model.pmx --role left_knee
```

Write the standalone canonical bone map as UTF-8 JSON:

```bash
python check_assets.py rig path/to/model.pmx --export-map bone-map.json
```

`--unmapped` and `--role` are mutually exclusive. `--export-map` requires a
`.json` path and refuses to overwrite the input PMX file. A filter with no
matches is successful. Actionable rig warnings or errors return exit code `1`;
an unusable path or invalid option combination returns `2`; and an unexpected
scan, analysis, or export failure returns `3`.

The default vocabulary is deliberately bounded. Accessory, clothing, hair,
physics, or custom control bones remain `unknown` when the available evidence
does not justify a canonical role. Profiles can be replaced by callers without
mutating the default vocabulary.

## Diagnose texture dependencies

Run structural scanning and filesystem diagnostics together:

```bash
python check_assets.py doctor path/to/model.pmx
```

Machine-readable output:

```bash
python check_assets.py doctor path/to/model.pmx --json
```

The doctor runs structural scanning first. Dependency diagnostics run only when
the PMX scan completes successfully and provides a trustworthy texture
summary.

For every declared texture path, the doctor reports:

- Declared texture index and original path
- Whether a material references the declaration
- Resolved path relative to the PMX directory
- Whether the resolved path exists and is a regular file
- Whether the path is portable with the model directory
- Stable issue codes and warning/error severity

Examples of diagnosed issues:

```text
empty_path
invalid_path
absolute_path
rooted_path
outside_model_directory
missing_file
not_a_file
```

A missing texture referenced by a material is an error. A missing declaration
that no material uses is a warning. Absolute paths and paths escaping the model
directory are warnings because they can break when the model is moved to
another computer.

## Text and JSON status behavior

Primary result statuses:

```text
ok
warning
error
```

Scanner and dependency warnings preserve a successful exit code when the model
remains structurally readable and no referenced dependency has an error. The
Rig Analyzer returns exit code `1` when its structured report contains
actionable warnings or errors. JSON output preserves Unicode names and paths
and is configured as UTF-8 even when redirected by Windows CMD. A successful
`roundtrip` reports semantic equality and output integrity before returning
exit code `0`. A successful `edit` preview or write reports the audit summary,
source integrity, semantic verification, and whether output was written.

## Exit codes

General CLI exit codes:

```text
0 = Command completed successfully; warnings may be present
1 = Validation failed, hash verification failed, model was malformed or
    unsupported, a referenced texture dependency had an error, or the Rig
    Analyzer reported actionable diagnostics
2 = Required input path or registry file could not be used
3 = Unexpected internal error
```

Command examples:

- Validation with warnings but no errors: `0`
- SHA-256 matched: `0`
- SHA-256 mismatched: `1`
- `inspect` on an invalid PMX/PMD header: `1`
- `scan` on a complete PMX with trailing-byte warnings: `0`
- `scan` on malformed PMX data: `1`
- `roundtrip` with verified distinct output: `0`
- `roundtrip` on malformed PMX data: `1`
- `roundtrip` with an input/output alias or existing unapproved output: `2`
- `roundtrip` internal semantic or output verification failure: `3`
- `edit --dry-run` with a valid plan, including a no-op plan: `0`
- `edit` with verified atomic distinct output: `0`
- `edit` with an invalid PMX, plan, reference, or verification result: `1`
- `edit` with missing output, unsafe alias, or unapproved overwrite: `2`
- `edit` with an unexpected internal failure: `3`
- `edit-plan catalog`, `template`, or valid `explain`: `0`
- `edit-plan explain` with invalid plan data: `1`
- `edit-plan explain` when the plan file cannot be read: `2`
- `edit-plan` with an unexpected internal failure: `3`
- `texture-portability` with no referenced blocked dependency: `0`
- `texture-portability` with invalid PMX data, a referenced blocker, or a source-change refusal: `1`
- `texture-portability` with input/plan-output path or plan I/O refusal: `2`
- `texture-portability` with an unexpected internal failure: `3`
- `doctor` with all referenced textures present: `0`
- `doctor` with a referenced texture missing: `1`
- `bones` search with no matches: `0`
- `bones` on malformed or unsupported PMX data: `1`
- `bones --details` with an invalid index: `2`
- Unsupported `bones` option combinations: `2`
- `rig` on a clean analyzed rig: `0`
- `rig` with actionable diagnostics: `1`
- `rig --role` or `rig --unmapped` with no matches: `0`
- Unsafe or conflicting `rig` options: `2`
- Missing file passed to `hash`, `inspect`, `scan`, `roundtrip`, `edit`,
  `doctor`, `bones`, or `rig`: `2`
- Unexpected scanner or diagnostics failure: `3`

## Registry schema 0.3

Example schema `0.3` asset:

```yaml
registry_version: "0.3"

assets:
  - id: example_character
    display_name: Example Character
    asset_type: character_model
    pipeline_character: ExampleCharacter
    source_path: sample_assets/example/model.pmx

    integrity:
      sha256: 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef

    creator:
      name: Example Creator
      profile_url: https://example.com/creator

    source:
      page_url: https://example.com/model
      downloaded_at: "2026-08-05"

    credit:
      required: true
      text: Model by Example Creator
      url: https://example.com/creator

    usage_rules:
      editing: allowed
      redistribution: prohibited
      commercial_use: conditional
      notes: Credit the original creator.

    status: ready
    tags:
      - character
      - example
```

The registered SHA-256 digest must be exactly 64 hexadecimal characters.
Schema `0.2` remains accepted, but integrity verification and model inspection
are not applied to schema `0.2` entries.

## Model header validation policy

For schema `0.3`, existing `.pmx` and `.pmd` source files are inspected.

A model is treated as a placeholder/review asset when at least one condition is
true:

- `status` is `review`
- A tag is `placeholder`
- Asset notes contain the word `placeholder`

If inspection fails:

- Private mode plus placeholder/review asset: warning
- Publish mode: error
- Commercial mode: error
- Non-placeholder asset in any mode: error

The inspection result still reports technical truth as `error`; only the
containing asset severity can be downgraded under the private placeholder
policy.

## Safety and trust boundaries

The tool keeps model and texture inputs read-only. Only the explicit
`roundtrip` and `edit` commands write PMX output. Both require a distinct output
path, validate before writing, refuse overwrite by default, reject aliases,
and never write in place. The project does not:

- Modify or rewrite an input PMX/PMD file in place
- Write any model from `validate`, `hash`, `inspect`, `scan`, `doctor`, `bones`,
  or `rig`
- Repair corrupt geometry, bones, morphs, or physics
- Rename, reparent, reposition, or change the flags of bones
- Apply inferred roles, aliases, hierarchy changes, or bone maps to a model
- Automatically translate Japanese, Chinese, or Korean bone names
- Copy, rename, convert, or delete textures
- Add, delete, or reorder texture or material records
- Edit material surface partitions
- Edit vertices, normals, UVs, weights, bones, IK, morphs, display frames, or
  physics records
- Import assets into Blender or MMD
- Integrate directly with `mmd_tools`
- Download assets or scrape creator pages
- Determine copyright ownership or legal permission
- Replace human review of original asset terms

All binary counts, variable-length strings, indices, and aggregate record
budgets are bounded before or while they are read. Malformed input is returned
as structured errors instead of being trusted. Writer validation checks counts,
index capacity, cross-section references, version requirements, finite values,
and encodability before a destination is created.

## Real-model verification

Version 0.8.0 was verified against a production-size PMX 2.0 model without
committing or redistributing that model.

Version 0.8.1 additionally exercised expected edit failures on a
production-size PMX 2.0 UTF-16LE model while requiring matching source SHA-256
before/after, no temporary residue, and no persisted edited private asset.

Version 0.8.2 does not require a new private-model validation run because its
new authoring-only commands never load PMX data and no PMX reader, writer,
engine, preview, or output-commit path is expanded. Generated regression tests
instead block PMX I/O calls and verify a sentinel PMX remains byte-identical.

Version 0.8.3 likewise does not require a new private-model validation run for
release. The portability workflow does read PMX structure and filesystem texture
evidence, but it never writes PMX or texture inputs and does not expand the PMX
writer or output-commit path. Generated PMX fixtures and temporary texture trees
cover portability classification, rewrite proposals, source-change refusal,
strict plan generation, and byte-identical input preservation. A private-model
rerun remains optional and local-only.

Version 0.8.4 adds an optional runtime-only compatibility harness. For this
release it was exercised locally against a private production model through
typed loading, read-only public workflows, verified temporary round-trip,
strict plan explanation, and `edit --dry-run`. The source size and SHA-256
remained unchanged, all temporary output/plan directories were removed, and no
private path, model name, model bytes, texture, or report is required by CI.

Verification summary:

```text
File size: 4,912,416 bytes
Bytes consumed: 4,912,416
Trailing bytes: 0
Vertices: 31,387
Triangles: 38,130
Bones: 342
Bone Explorer table records: 342
Hierarchy nodes: 342
Hierarchy roots: 2
Hierarchy issues: 0
CalfD search matches: 2
IK-only matches: 4
Detail validation: bone 339 with parent 338
Morphs: 59
Rigid bodies: 221
Joints: 299
Declared/referenced textures: 11/11
Missing textures: 0
Non-portable paths: 0
Scan exit code: 0
Doctor exit code: 0
UTF-8 JSON export: valid
Bone table/tree/detail/search/IK text output: valid
Bone table/tree/detail/search/IK JSON output: valid
Rig Analyzer bones: 342
Resolved semantic bones: 102
Unresolved semantic bones: 240
Mapped canonical roles: 37
Rig diagnostics: 1 info, 2 warnings, 0 errors
Rig diagnostic codes: ambiguous_semantic_role, missing_expected_role,
  unclassified_bones
False duplicate, side-conflict, and asymmetry diagnostics: 0
Canonical bone-map UTF-8 JSON export: valid
Rig Analyzer exit code with actionable warnings: 1
PMX document reference validation: valid
Parse -> serialize -> parse semantic equality: valid
Round-trip source/output size: 4,912,416 / 4,912,416 bytes
Round-trip SHA-256 digests: matched
Round-trip output: byte-identical
Input model unchanged: yes
Temporary round-trip output removed: yes
Private round-trip elapsed time: 9.823 seconds
Private edit fields changed: 3
Private edit metadata field: exact
Private edit material text/property fields: exact
Private edit output parse/reference validation: valid
Private edit unrelated sections/counts: unchanged
Private edit source SHA-256 before/after: matched
Private edit temporary plan/output removed: yes
Private texture files touched: no
Private failure valid dry-run: passed
Private failure plan diagnostic: edit_plan_invalid / plan_validate
Private failure source-hash diagnostic: edit_preflight_failed / preflight
Private failure alias refusal: path_policy_refused / preflight
Private failure source SHA-256 before/after: matched
Private failure temporary residue created: no
Private failure asset persisted: no
v0.8.4 private compatibility workflows: passed
v0.8.4 private source SHA-256 before/after: matched
v0.8.4 private temporary output/plan cleanup: passed
```

This verification supplements generated fixtures; the repository does not
contain the third-party production model or its textures.

## Automated tests

Run all tests compactly:

```bash
python -m unittest discover -s tests -q
```

At the release-readiness checkpoint, version 0.8.4 includes 915 unit tests
under normal CI discovery with the optional private-runtime class skipped. When
`MMD_REGISTRY_PRIVATE_PMX` is explicitly enabled for local validation, 918 tests
run. Coverage includes:

- Bounded binary reads and contextual truncation errors
- PMX 2.0 and 2.1 header/global settings
- All supported PMX structural sections and index sizes
- Cross-reference and finite-value validation
- Complete-file accounting and trailing bytes
- Immutable complete PMX document records and section readers
- Deterministic PMX 2.0/2.1 serialization
- UTF-8/UTF-16LE output and uniform or mixed 1/2/4-byte index widths
- BDEF1, BDEF2, BDEF4, SDEF, and QDEF round-trip coverage
- Every supported morph type and complete PMX physics round-trip coverage
- Cross-section writer validation and invalid-document write prevention
- Safe output refusal, explicit overwrite, alias detection, and atomic output
- `roundtrip` text/JSON CLI reporting and Windows Unicode paths
- Immutable typed edit plans, operations, audit records, and exact no-op rules
- Strict UTF-8 edit-plan JSON loading, contextual errors, exact JSON types,
  optional source SHA-256, duplicate-target rejection, malformed/empty
  document handling, duplicate-member rejection, and non-standard numeric
  constant rejection
- Structured edit diagnostics with stable phase/code/path context and
  backward-compatible CLI JSON failure envelopes
- Deterministic edit-operation catalog metadata, intentionally incomplete
  starter templates, pure plan explanations, authoring CLI behavior, and
  authoring failure/privacy regression coverage
- Pure model metadata, indexed texture path, material text/reference, and
  material visual-property transformations
- Deterministic edit previews, audit ordering, write reports, and serialized
  output bytes
- PMX edit output alias refusal, no-clobber creation, explicit atomic
  overwrite, source path/identity/hash re-verification, and temporary-file
  cleanup across negative failure paths
- PMX 2.0/2.1 × UTF-8/UTF-16LE × uniform/mixed index-width edit matrices and
  all seven model/texture/material category combinations
- Named PMX compatibility profiles, reader/scanner parity, additional UV 0-4,
  zero-count sections, Unicode data, version/opaque-flag/trailing-byte boundaries,
  and deterministic writer/round-trip invariants
- Cross-feature generated compatibility across scan, doctor, bones, rig,
  roundtrip, strict edit-plan explanation, edit dry-run, and texture portability
- Optional runtime-only private compatibility with source SHA-256 invariance,
  temporary-output cleanup, and CI skip behavior when no local path is supplied
- Ephemeral private-model validation plus privacy-safe negative-path
  validation, cleanup-on-failure, source-integrity checks, and untouched
  texture files
- Texture-reference summaries
- Host-independent texture-path lexical semantics and normalized candidates
- Dependency path portability, exact filesystem spelling, and containment evidence
- Safe texture rewrite proposals, strict edit-plan bridging, and source SHA-256 binding
- `texture-portability`, `scan`, and `doctor` text/JSON output
- Bone display-name resolution and friendly flag presentation
- Compact bone table rendering and JSON serialization
- Safe hierarchy construction, cycle diagnostics, and iterative tree rendering
- Individual bone details and enabled/disabled capabilities
- Unicode-normalized name/index search and IK filtering
- `bones` table, tree, details, search, IK, and JSON CLI modes
- Semantic vocabulary, role variants, aliases, profiles, and immutable results
- Unicode-normalized multilingual name resolution and ambiguity handling
- Non-recursive, fixed-point hierarchy inference for deep or cyclic rigs
- Structured rig diagnostics for roles, symmetry, hierarchy, and IK
- Deterministic complete rig reports, summaries, and canonical bone maps
- `rig` text, JSON, unmapped, role-filter, and bone-map export modes
- Exit codes `0`, `1`, `2`, and `3`
- Windows redirected UTF-8 output, including Unicode bone JSON
- Legacy CLI compatibility
- SHA-256 streaming and verification
- PMX/PMD header inspection
- Registry schemas `0.2` and `0.3`
- Validation modes, reports, and credit generation
- Version, documentation, changelog, and workflow release readiness

Binary model fixtures are generated programmatically during tests. The
repository does not require copyrighted model fixtures.

## GitHub Actions

The workflow at `.github/workflows/validate.yml` runs on pushes and pull
requests across Ubuntu and Windows. It performs:

1. Repository checkout
2. Python 3.12 setup
3. Runtime and pinned development dependency installation
4. Correctness-focused Ruff linting and Python source compilation
5. The PMX safety, compatibility, public API, service, and cross-platform gate
6. Full automated test discovery with branch coverage reports
7. Fresh wheel/sdist build, archive inspection, and isolated wheel installation
8. Exact `0.9.0` package-version assertion
9. Top-level version plus `scan`, `roundtrip`, `edit`, `edit-plan`,
   `texture-portability`, `doctor`, `bones`, and `rig` help checks, including
   all `edit-plan` subcommands
10. Private registry validation using legacy and explicit syntax
11. Registered placeholder SHA-256 verification

## Project structure

```text
mmd-asset-registry/
|-- .github/workflows/validate.yml
|-- mmd_registry/
|   |-- __init__.py
|   |-- binary_reader.py
|   |-- bone_cli.py
|   |-- bone_details.py
|   |-- bone_explorer.py
|   |-- bone_hierarchy.py
|   |-- bone_names.py
|   |-- bone_search.py
|   |-- bone_semantic_inference.py
|   |-- bone_semantic_resolver.py
|   |-- bone_semantics.py
|   |-- cli.py
|   |-- constants.py
|   |-- dependency_diagnostics.py
|   |-- hashing.py
|   |-- model_inspection.py
|   |-- model_scanning.py
|   |-- pmx/
|   |   |-- document.py
|   |   |-- editing/
|   |   |   |-- audit.py
|   |   |   |-- catalog.py
|   |   |   |-- diagnostics.py
|   |   |   |-- engine.py
|   |   |   |-- errors.py
|   |   |   |-- explain.py
|   |   |   |-- json_loader.py
|   |   |   |-- operations.py
|   |   |   |-- output.py
|   |   |   |-- plan.py
|   |   |   |-- preview.py
|   |   |   |-- private_failure_validation.py
|   |   |   |-- private_validation.py
|   |   |   `-- template.py
|   |   |-- errors.py
|   |   |-- reader.py
|   |   |-- roundtrip.py
|   |   |-- validation.py
|   |   |-- writer.py
|   |   `-- sections/
|   |-- reporting.py
|   |-- rig_analysis.py
|   |-- rig_cli.py
|   |-- rig_diagnostics.py
|   `-- validator.py
|-- reports/
|-- sample_assets/
|-- tests/
|   |-- mmd_fixtures.py
|   |-- test_binary_reader.py
|   |-- test_bone_cli.py
|   |-- test_bone_details.py
|   |-- test_bone_explorer.py
|   |-- test_bone_hierarchy.py
|   |-- test_bone_names.py
|   |-- test_bone_search.py
|   |-- test_bone_semantic_inference.py
|   |-- test_bone_semantic_resolver.py
|   |-- test_bone_semantics.py
|   |-- test_cli.py
|   |-- test_cli_utf8_output.py
|   |-- test_dependency_diagnostics.py
|   |-- test_doctor_cli.py
|   |-- test_model_inspection.py
|   |-- test_model_scanning.py
|   |-- pmx_roundtrip_fixtures.py
|   |-- test_pmx_document.py
|   |-- test_pmx_edit_cli_diagnostics.py
|   |-- test_pmx_edit_plan_authoring_failures.py
|   |-- test_pmx_edit_plan_cli.py
|   |-- test_pmx_edit_plan_explain.py
|   |-- test_pmx_edit_plan_template.py
|   |-- test_pmx_edit_operation_catalog.py
|   |-- test_pmx_edit_generated_matrix.py
|   |-- test_pmx_edit_negative_safety.py
|   |-- test_pmx_edit_safe_output.py
|   |-- test_pmx_private_edit_validation.py
|   |-- test_pmx_private_failure_validation.py
|   |-- test_pmx_roundtrip.py
|   |-- test_pmx_roundtrip_cli.py
|   |-- test_pmx_writer.py
|   |-- test_pmx_*_scanning.py
|   |-- test_release_readiness.py
|   |-- test_reporting.py
|   |-- test_rig_analysis.py
|   |-- test_rig_cli.py
|   |-- test_rig_diagnostics.py
|   `-- test_validator.py
|-- assets.yaml
|-- CHANGELOG.md
|-- check_assets.py
|-- README.md
|-- RELEASE_CHECKLIST.md
`-- requirements.txt
```

## Current limitations

v0.9.0 does not:

- Structurally scan PMD beyond header inspection
- Edit PMX/PMD input files in place
- Publicly commit structural collection edits; the v0.9.0 structural service is
  preview-only and reports `structural_write=False`
- Insert new vertices, textures, materials, bones, morphs, or rigid bodies
- Persist public add/delete/reorder operations for textures or materials
- Edit material surface partitions
- Author mesh geometry, normals, UVs, weights, bone/IK data, morph payloads,
  display frames, or physics through a public structural writer
- Silently repair model data or automatically resize PMX index widths
- Diagnose non-texture external dependencies
- Register scan results back into `assets.yaml`
- Provide batch directory scanning
- Provide a graphical interface
- Translate, rename, or rewrite multilingual bone names
- Guarantee canonical roles for custom accessory, clothing, hair, or physics
  bones without sufficient evidence
- Auto-repair semantic, hierarchy, symmetry, or IK diagnostics
- Edit bone names, positions, parents, flags, IK, or weights
- Import models into Blender or MMD
- Automatically determine legal permissions

## Roadmap

Release progression after the completed v0.8 line:

- `pre-0.9.0` / package `0.9.0a0` — Completed architecture, packaging,
  public-boundary, quality, and cross-platform release runway
- `v0.9.0` / package `0.9.0` — Reference-safe structural analysis and certified
  preview foundation with public structural write intentionally disabled
- Later v0.9 releases — Separately reviewed, safety-bounded feature work
- Later: multilingual PMX naming with external reviewable dictionaries,
  animation-pipeline integration, PMD structural scanning, registry/browser
  workflows, a desktop inspector GUI, and carefully bounded broader PMX
  editing
