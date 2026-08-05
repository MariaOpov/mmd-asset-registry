# MMD Asset & License Registry

A lightweight Python registry for tracking MMD asset provenance, creator
credits, local source files, and known usage restrictions.

The project is designed as a validation gate before assets enter an automated
MMD, Blender, or anime video pipeline.

## Current version

```text
Tool version: 0.2.0
Registry schema: 0.2
```

## Why this project exists

MMD models and related assets are often collected from different creators,
distribution pages, and communities.

Over time, important information can become separated from the downloaded
files:

- Who created the asset
- Where the asset originally came from
- What credit should appear in a published video
- Whether editing, redistribution, or commercial use has known restrictions
- Whether the local asset file still exists
- Which pipeline character uses the asset

This registry keeps that information in one structured YAML file and validates
it before a pipeline continues.

The registry does not automatically determine legal permission. It records
known information, missing information, and known restrictions.

## Version 0.2 features

Version 0.2 provides:

- Schema 0.2 validation
- Creator and source provenance tracking
- Automatic Markdown credit generation
- Private, publish, and commercial validation modes
- Required-field validation
- Allowed-value validation
- Local source-file validation
- Duplicate asset ID detection
- Portable JSON reports
- Structured info, warning, and error messages
- Exit codes for automation and CI
- Automated unit tests
- GitHub Actions validation

## Validation modes

### Private mode

Used for local MMD, Blender, and pipeline testing.

```bash
python check_assets.py --mode private
```

Private mode allows incomplete provenance and credit information while still
reporting warnings and informational messages.

Typical behavior:

- Missing source file: error
- Duplicate ID: error
- Unknown creator: warning
- Missing required credit text: warning
- Unclear editing rule: information
- Unclear commercial-use rule: does not block private testing

### Publish mode

Used before publishing a public video.

```bash
python check_assets.py --mode publish
```

Publish mode requires complete credit text when an asset declares that credit
is required.

Typical behavior:

- Missing required credit text: error
- Missing creator: warning
- Missing original source page: warning
- Unclear editing rule: warning

### Commercial mode

Used before monetized videos, commissions, advertisements, or other commercial
output.

```bash
python check_assets.py --mode commercial
```

Commercial mode adds commercial-use checks.

Typical behavior:

- Commercial use prohibited: error
- Commercial-use rule unclear: error
- Commercial use conditional: warning
- Missing required credit text: error

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

## Basic usage

Run private validation:

```bash
python check_assets.py
```

Equivalent command:

```bash
python -m mmd_registry.cli
```

Show command-line help:

```bash
python check_assets.py --help
```

Show the tool version:

```bash
python check_assets.py --version
```

## Generate reports

Generate a JSON validation report:

```bash
python check_assets.py --mode private
```

Default output:

```text
reports/validation_report.json
```

Disable JSON report generation:

```bash
python check_assets.py --mode private --no-report
```

Use a custom report path:

```bash
python check_assets.py --report reports/custom-report.json
```

## Generate asset credits

Generate the default credit file:

```bash
python check_assets.py --mode private --credits
```

Default output:

```text
reports/CREDITS.md
```

Use a custom output path:

```bash
python check_assets.py --credits output/ASSET_CREDITS.md
```

Assets with complete credit information are listed under `Credits`.

Assets that require credit but have incomplete credit information are listed
under `Incomplete Credit Information`.

Generated reports and generated credits are ignored by Git.

## Registry schema

Example schema 0.2 asset:

```yaml
registry_version: "0.2"

assets:
  - id: example_character
    display_name: Example Character
    asset_type: character_model
    pipeline_character: ExampleCharacter

    source_path: sample_assets/example/model.pmx

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

    notes: Example schema 0.2 asset.
```

## Asset types

Supported asset types:

```text
character_model
stage
motion
camera_motion
accessory
effect
texture_pack
audio
other
```

Character models require a non-empty `pipeline_character`.

## Asset statuses

Supported statuses:

```text
ready
review
blocked
archived
```

Meaning:

- `ready` — Asset is available for its intended pipeline use
- `review` — Provenance, credit, or usage information remains incomplete
- `blocked` — Validator rejects the asset
- `archived` — Asset is retained but produces a warning

## Usage-rule values

Supported values:

```text
allowed
prohibited
conditional
unclear
not_applicable
```

These values record known information. They are not an automatic legal
determination.

## Validation output

Example terminal output:

```text
[INFO] flavia: Asset is still under review.
[WARNING] flavia: Creator name has not been recorded.
[ERROR] flavia: Credit is required, but credit.text is missing.
```

Registry status values:

```text
passed
passed_with_warnings
failed
```

Asset status values in JSON reports:

```text
ok
warning
error
```

Informational messages do not change an asset from `ok` to `warning`.

## Exit codes

```text
0 = Validation completed without errors
1 = Registry or asset validation failed
2 = Registry file could not be loaded
3 = Unexpected internal error
```

These exit codes allow shell scripts, pipelines, and GitHub Actions to stop
when validation fails.

## Automated tests

Run all tests:

```bash
python -m unittest discover -s tests -v
```

The current test suite covers:

- Valid private registry
- Missing source file
- Missing publish credit
- Unclear commercial permission
- Duplicate asset IDs
- Portable JSON report paths
- JSON report writing
- Credit Markdown generation
- Incomplete credit reporting

## GitHub Actions

The repository includes:

```text
.github/workflows/validate.yml
```

The workflow runs on pushes and pull requests.

It performs:

1. Repository checkout
2. Python 3.12 setup
3. Dependency installation
4. Python source compilation
5. Automated tests
6. Private-mode registry validation

## Project structure

```text
mmd-asset-registry/
├── .github/
│   └── workflows/
│       └── validate.yml
├── .vscode/
│   └── launch.json
├── mmd_registry/
│   ├── __init__.py
│   ├── cli.py
│   ├── constants.py
│   ├── reporting.py
│   └── validator.py
├── reports/
│   └── .gitkeep
├── sample_assets/
├── tests/
│   ├── __init__.py
│   ├── test_reporting.py
│   └── test_validator.py
├── assets.yaml
├── check_assets.py
├── README.md
└── requirements.txt
```

## Not included in version 0.2

Version 0.2 does not:

- Parse PMX or PMD contents
- Inspect bones, morphs, materials, or textures
- Import assets into Blender
- Integrate directly with `mmd_tools`
- Download assets
- Scrape creator pages
- Automatically determine legal permissions
- Provide a web interface
- Provide a database
- Replace human review of original asset terms

## Roadmap

Possible version 0.3 features:

- PMX and PMD header inspection
- File SHA-256 integrity checks
- Missing texture detection
- Asset dependency scanning
- Pipeline-readable asset selection
- More extensive fixture-based tests