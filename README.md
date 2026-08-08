# MMD Asset & License Registry

A lightweight, read-only Python toolkit for tracking MMD asset provenance,
creator credits, local source files, SHA-256 integrity, model metadata,
PMX structure, texture dependencies, bone hierarchies, bone semantics,
rig diagnostics, canonical bone maps, and known usage restrictions.

The project is designed as a validation and diagnostics gate before assets
enter an automated MMD, Blender, or anime-video pipeline. It never edits,
rewrites, repairs, or redistributes a model or texture file.

## Current version

```text
Tool version: 0.6.0
Latest registry schema: 0.3
Supported registry schemas: 0.2, 0.3
```

Tool version and registry schema are intentionally independent. Version 0.6.0
adds the read-only Rig Analyzer without changing the persistent registry
schema.

Schema `0.2` remains supported for backward compatibility. Integrity and model
header inspection are applied only to schema `0.3` registry entries.

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
- Which pipeline character uses the asset

The registry records this information in YAML and validates it before a
pipeline continues. The scanner and doctor add technical evidence, but the
tool does not automatically determine legal permission or replace review of
the creator's original terms.

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
| Texture dependency doctor | Yes | Yes | No |
| Bone Explorer | Yes | Yes | No |
| Rig Analyzer | Yes | Yes | No |

PMD 1.0 is currently supported for header inspection only. `scan`, `doctor`,
`bones`, and `rig` return an unsupported-format error for PMD files instead of
pretending to perform a partial structural scan.

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
and is configured as UTF-8 even when redirected by Windows CMD.

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
- Missing file passed to `hash`, `inspect`, `scan`, `doctor`, `bones`, or
  `rig`: `2`
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

The tool is read-only for model and texture inputs. It does not:

- Modify or rewrite PMX/PMD files
- Repair corrupt geometry, bones, morphs, or physics
- Rename, reparent, reposition, or change the flags of bones
- Apply inferred roles, aliases, hierarchy changes, or bone maps to a model
- Automatically translate Japanese, Chinese, or Korean bone names
- Change texture paths
- Copy, rename, convert, or delete textures
- Import assets into Blender or MMD
- Integrate directly with `mmd_tools`
- Download assets or scrape creator pages
- Determine copyright ownership or legal permission
- Replace human review of original asset terms

All binary counts, variable-length strings, indices, and aggregate record
budgets are bounded before or while they are read. Malformed input is returned
as structured errors instead of being trusted.

## Real-model verification

Version 0.6.0 was verified against a production-size PMX 2.0 model without
committing or redistributing that model.

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
```

This verification supplements generated fixtures; the repository does not
contain the third-party production model or its textures.

## Automated tests

Run all tests:

```bash
python -m unittest discover -s tests -v
```

At the real-model validation checkpoint, version 0.6.0 includes 475 unit tests
covering:

- Bounded binary reads and contextual truncation errors
- PMX 2.0 and 2.1 header/global settings
- All supported PMX structural sections and index sizes
- Cross-reference and finite-value validation
- Complete-file accounting and trailing bytes
- Texture-reference summaries
- Dependency path portability and filesystem state
- `scan` and `doctor` text/JSON output
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
requests. It performs:

1. Repository checkout
2. Python 3.12 setup
3. Dependency installation
4. Python source compilation
5. Full automated test discovery
6. Exact `0.6.0` package-version assertion
7. Top-level version, `scan --help`, `doctor --help`, `bones --help`, and
   `rig --help` checks
8. Private registry validation using legacy and explicit syntax
9. Registered placeholder SHA-256 verification

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
`-- requirements.txt
```

## Current limitations

Version 0.6.0 does not:

- Structurally scan PMD beyond header inspection
- Write or edit PMX/PMD files
- Repair or transform model data
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

Planned directions after 0.6.0:

- Multilingual PMX naming with external, reviewable dictionaries
- Integration of exported canonical bone maps with animation pipelines
- Batch Rig Analyzer reports and project-level mapping review
- PMD structural scanning
- Registry browser and metadata editing
- Batch scan and doctor commands
- Safe registry updates from scan results
- First desktop model inspector GUI
- Safe PMX metadata, material, and texture-path writing
- Later bone, morph, transform, vertex, and weight editing workflows
