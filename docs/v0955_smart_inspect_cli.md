# v0.9.5.5 Smart Inspect CLI

Version 0.9.5.5 publishes a deterministic, read-only human-facing command over
the existing Smart Part detector, explainability, and confidence/ambiguity
authorities.

## Command

```text
mmd-asset-registry smart inspect SOURCE
python check_assets.py smart inspect SOURCE
```

`smart` is added through the outer application parser. The frozen legacy parser
and runtime parser retain their existing command contracts.

## Output contract

The command prints `SMART PART INSPECTION` followed by canonically ordered Smart
Part results. Resolved parts show HIGH/MEDIUM/LOW plus concise exact-alias
evidence. AMBIGUOUS results show every valid candidate and candidate-specific
evidence. Conflicts are never silently resolved.

When semantic evidence is absent, the exact user-facing result is:

```text
No Smart Parts detected.
```

The v0.9.5.5 command is human-readable text only; there is no JSON output schema
in this patch.

## Evidence authority

The CLI does not classify independently. It uses the existing PMX loader and
structural-authoring catalog, then reuses:

- `mmd_registry.smart_part_detection.detect_smart_parts`
- `mmd_registry.smart_part_explainability.explain_smart_parts`
- `mmd_registry.smart_part_confidence.assess_smart_parts`

The private `mmd_registry.services._smart_inspection` module only orchestrates
those authorities and remains absent from `mmd_registry.services.__all__`.

## Determinism and errors

Ordering is stable across repeat runs, reversed equivalent injectable ordering,
and `PYTHONHASHSEED=0,1,2,42,31337`. Unicode/Japanese names and paths, spaces,
UTF-8 redirected output, slash/backslash provenance, missing files, directory
input, malformed PMX input, and truncated PMX input are explicitly covered.

Expected user failures produce bounded Smart Inspect diagnostics rather than
uncontrolled tracebacks. Unexpected internal exceptions are redacted at the
Smart command boundary.

## Safety boundary

Smart Inspect is read-only. It adds no PMX mutation, automatic repair,
transaction-plan generation, preview/apply, writer/remapper access, fuzzy or
substring matching, probability scoring, ML/LLM/AI fallback, schema change,
capability promotion, GUI, or publication authority.

The package root remains exactly `('__version__',)`. Existing Smart semantic and
structural transaction authorities remain unchanged.

## Certification

The promoted local suite contains 3,060 tests with 2 optional skips. CP16
measures 86.98% combined coverage after adding the new modules; like-for-like
coverage excluding `smart_cli.py` and `_smart_inspection.py` is 87.01496%.
The new modules measure 80.74% and 83.05%, respectively. Ruff, compileall, direct
source compilation, hash-seed determinism, targeted regression, and full-suite
gates pass before version/docs/packaging promotion.

Optional private real-model certification remains controlled by
`MMD_REGISTRY_PRIVATE_PMX`; no private model is invented when the controlled
corpus is unavailable.
