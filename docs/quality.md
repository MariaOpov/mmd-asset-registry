# Quality gates

This document records the correctness-focused lint foundation introduced
during the pre-0.9.0 architecture runway. It does not impose a formatter or
change runtime behavior.

## Lint command

Install the development-only tool set, then run the same command used by CI:

```text
python -m pip install -r requirements-dev.txt
python -m ruff check mmd_registry tests tools check_assets.py
```

Ruff is pinned to `0.16.3`, targets Python 3.12, and is not a project runtime
or build-system dependency. The pinned version is also enforced by
`pyproject.toml` so local and CI results cannot silently diverge.

## Rule boundary

The initial gate selects only `E9`, `F63`, `F7`, and `F82`. These rules detect
syntax and parser-level failures, always-true tuple or literal mistakes,
invalid control flow or forward annotations, and undefined names, exports, or
local references. The gate intentionally excludes formatting, import sorting,
line-length policy, naming policy, unused-import cleanup, and preview rules.

CI runs `ruff check` without `--fix`. Expanding the rule set or introducing a
formatter requires a separately reviewed checkpoint so unrelated source files
are not rewritten as an incidental quality-tool change.

## Deferred gates

Type checking and broader static-analysis policy remain deferred to separately
reviewed checkpoints.

## Coverage measurement

Install the development-only tool set, then measure the complete unittest
suite and emit both human-readable and machine-readable reports:

```text
python -m coverage erase
python -m coverage run -m unittest discover -s tests -q
python -m coverage report
python -m coverage json
```

Coverage.py is pinned to `7.15.4`. Measurement includes every importable module
under `mmd_registry`, records line and branch execution, uses relative paths,
and writes `coverage.json` for machine-readable inspection. Generated coverage
data remains local and ignored.

The Checkpoint 12 audit baseline on Python 3.12 is:

| Metric | Total | Covered | Missing | Coverage |
| --- | ---: | ---: | ---: | ---: |
| Statements | 8,311 | 7,568 | 743 | 91.06% |
| Branches | 2,982 | 2,404 | 578 | 80.62% |
| Combined | 11,293 | 9,972 | 1,321 | 88.30% |

The measured suite contains 1,050 tests with one environment-dependent skip
and reports 65 package files. These numbers are a transparent baseline, not a
release threshold. No `fail_under` value is configured; future thresholds must
be based on reviewed trends rather than an arbitrary target or percentage-only
tests.
