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

No optional development dependencies are declared yet. Lint and coverage
tooling belong to their dedicated checkpoints and must not become runtime
dependencies.

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

## Deferred gates

Clean isolated installation belongs to Checkpoint 10. This checkpoint verifies
the generated wheel metadata and callable target but does not claim that a
fresh environment can install every runtime dependency and execute the
generated platform launcher outside the source tree.

The repository currently has no tracked license file, so packaging metadata
does not invent a license expression or license classifier. License metadata
requires a separate Maintainer decision before publication.
