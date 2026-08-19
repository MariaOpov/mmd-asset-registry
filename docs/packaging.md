# Packaging policy

This document records the packaging decisions introduced during the
pre-0.9.0 architecture runway. It does not publish a distribution or change
runtime behavior.

## Distribution and import names

The Python distribution name is `mmd-asset-registry`. The import package is
`mmd_registry`. Setuptools discovery is restricted to `mmd_registry*`; the
repository's tests, reports, sample registry, and development files are not
Python packages in the distribution.

## Version strategy

`mmd_registry.__version__` remains the single runtime version source.
`pyproject.toml` declares `version` as dynamic and asks setuptools to read that
literal attribute. For the current release, the Git/GitHub label `v0.9.1` maps
to the PEP 440 Python distribution version `0.9.1`. Runtime imports, installed
metadata, wheel and sdist filenames, console output, reports, CI assertions,
and release-facing tests all derive from or explicitly verify that mapping; no
second distribution-version source is introduced. Historical release mappings
such as `pre-0.9.0` -> `0.9.0a0` remain documented in the changelog.

## Dependencies and build backend

The runtime dependency remains `PyYAML>=6.0`, matching `requirements.txt`.
Setuptools is the build backend and wheel is a build-system dependency. Build
requirements are not runtime requirements.

Development-only tools are isolated in `requirements-dev.txt`; they are not
declared as project, build-system, or optional distribution dependencies. Ruff
provides the Checkpoint 11 lint gate, and coverage.py provides the Checkpoint
12 full-suite measurement. Neither tool is a runtime dependency.

## Distribution build and inspection

Builds use the standard `build` frontend and create both distribution formats
from the repository root:

```text
python -m build --sdist --wheel
python tools/inspect_distribution_artifacts.py dist
```

The inspection command requires a clean `dist` directory containing exactly
one wheel and one sdist. It reads archives without extracting them and verifies
their filenames, metadata, runtime dependencies, pure-Python wheel tag, member
paths, RECORD coverage, source boundary, and SHA-256 digests. It refuses links,
unsafe paths, PMX/VMD data, local private paths, secret-key material, temporary
outputs, repository-only assets, and test leakage into the wheel.

The wheel intentionally contains only `mmd_registry` and its generated
`.dist-info` metadata. The sdist intentionally contains the complete Python
test sources, test helpers, and artifact-inspection tool so its source boundary
is explicit rather than the partial implicit test selection produced by
setuptools.

Build output remains local and ignored. This checkpoint does not upload or
publish either artifact.

For the v0.9.1 CP23 feature-branch gate, canonical artifact shape is 85 regular
file members in the wheel and 235 regular file members in the sdist. The sdist
count intentionally excludes tar directory entries. SHA-256 digests are not
frozen in this policy before the final committed build because any subsequent
commit/rebuild changes artifact bytes; final release digests must be captured
from the final release commit.

## Cross-platform build and installation gate

The GitHub Actions validation matrix runs the complete distribution gate on
both `ubuntu-latest` and `windows-latest` with Python 3.12. Each matrix job
builds a fresh wheel and sdist, inspects both archives, installs the wheel with
its declared dependencies in a disposable environment outside the checkout,
and exercises installed metadata, imports, capabilities, diagnostics,
document/validation/edit services, structural preview/execution services, and
console entry points.

The standard `build` frontend is pinned to `1.5.0` in
`requirements-dev.txt`. It is CI/development tooling only and is not a runtime
dependency or an additional build-system requirement. The gate uses the same
commands on both operating systems:

```text
python -m build --sdist --wheel
python tools/inspect_distribution_artifacts.py dist
python tools/verify_clean_install.py dist
```

The matrix is fail-closed but does not upload or publish artifacts. A failure
on either operating system fails validation, while `fail-fast: false` retains
evidence from both jobs.

## Installed console command

The installed console command is `mmd-asset-registry`. Packaging metadata maps
it directly to `mmd_registry.cli:main`, the same process boundary used by the
legacy `check_assets.py` launcher. No second parser or wrapper implementation
is introduced.

The command supports `--help` and `--version`, uses the existing CLI exit-code
and UTF-8 handling, and remains independent from the repository working
directory. The legacy script and `python -m mmd_registry.cli` remain available
during the architecture runway.

Wheel inspection requires exactly this `console_scripts` mapping and rejects
missing, renamed, duplicated, or additional entry points.

## Clean isolated installation

The clean-install gate creates a disposable virtual environment outside the
repository, installs the inspected wheel and all declared runtime dependencies,
and runs installed-package probes from that external working directory:

```text
python tools/verify_clean_install.py dist
```

The verifier does not inherit system site packages or the active development
environment. It removes Python import-path overrides, runs probes with isolated
mode, checks dependency consistency with `pip check`, and proves that both
`mmd_registry` and `PyYAML` were imported from the disposable environment rather
than the source checkout. It also validates installed metadata, public imports,
the console entry point, and both console and module `--version` execution.

Package indexes remain enabled by default so pip can resolve `PyYAML>=6.0` in a
genuinely empty environment. A complete local dependency wheelhouse can be used
instead with `--no-index --find-links DIRECTORY`. The temporary environment is
always removed, including after a failed probe, and no artifact is published.

## Deferred gates

Checkpoint 10 established the local deterministic verifier; Checkpoint 19
runs that verifier after fresh builds on both supported CI operating systems.
Artifact publication remains deferred to the separately reviewed release
workflow.

The repository currently has no tracked license file, so packaging metadata
does not invent a license expression or license classifier. License metadata
requires a separate Maintainer decision before publication.
