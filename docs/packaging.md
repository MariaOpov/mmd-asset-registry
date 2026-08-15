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
literal attribute. The current value remains `0.8.5` so this checkpoint does
not impersonate an unreleased build.

At the release-readiness checkpoint, the Git label `pre-0.9.0` is expected to
map to the PEP 440 distribution version `0.9.0a0`. That change must update the
existing runtime source and all release-facing contracts together; no second
hard-coded distribution version should be introduced.

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

Cross-platform clean installation in both Ubuntu and Windows CI belongs to
Checkpoint 19. Checkpoint 10 establishes the local deterministic verifier and
its installed-package contracts without changing runtime behavior.

The repository currently has no tracked license file, so packaging metadata
does not invent a license expression or license classifier. License metadata
requires a separate Maintainer decision before publication.
