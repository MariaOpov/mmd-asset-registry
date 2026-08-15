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

## Deferred gates

This checkpoint defines metadata only. Wheel and sdist creation and inspection
belong to Checkpoint 8. The installed console entry point belongs to
Checkpoint 9, so `project.scripts` is intentionally absent here. Clean isolated
installation belongs to Checkpoint 10.

The repository currently has no tracked license file, so packaging metadata
does not invent a license expression or license classifier. License metadata
requires a separate Maintainer decision before publication.
