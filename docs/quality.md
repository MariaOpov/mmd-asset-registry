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

Checkpoint 12 will add coverage reporting and record the full-suite baseline.
Type checking and broader static-analysis policy remain deferred to their
dedicated checkpoints.
