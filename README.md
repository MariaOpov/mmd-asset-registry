# MMD Asset & License Registry

A lightweight registry and validator for tracking MMD assets, their source
locations, creators, license permissions, and pipeline readiness.

## Why this project exists

MMD character models and related assets are often collected from different
creators and distribution platforms. Their usage terms may differ, and license
information can become separated from the downloaded files.

This project provides one centralized registry for recording:

- Asset identity
- Local source path
- Original creator
- Commercial-use permission
- Redistribution permission
- Modification permission
- Pipeline character mapping
- Review status
- Additional notes

The registry is intended to reduce accidental use of missing, unverified, or
license-incompatible assets in automated animation pipelines.

## Version 0.1

Version 0.1 provides a command-line YAML validator.

It can:

- Read `assets.yaml`
- Validate required asset fields
- Validate required license fields
- Detect missing source files
- Detect duplicate asset IDs
- Warn about unknown creator information
- Warn about unknown license values
- Return exit code `1` when validation errors exist
- Return exit code `0` when validation succeeds

## Project structure

```text
mmd-asset-registry/
├── .vscode/
│   └── launch.json
├── reports/
│   └── .gitkeep
├── sample_assets/
├── assets.yaml
├── check_assets.py
├── README.md
└── requirements.txt

