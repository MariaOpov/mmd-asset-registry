# MMD Asset Registry v0.9.0 Release Checklist

The Git/GitHub release label is `v0.9.0`; the PEP 440 runtime and
distribution version is `0.9.0`. This is a normal GitHub Release, not a prerelease.
Never tag the feature branch, never create the release before merged-main verification,
and never publish to PyPI without separate explicit Maintainer approval.

## 1. Feature-branch final local gate

- [ ] Confirm the expected feature branch, reviewed ancestry, and clean tree:

  ```bat
  cd /d D:\MMD\mmd-asset-registry
  set "MMD_REGISTRY_PRIVATE_PMX="
  git --no-pager status
  git --no-pager branch --show-current
  git --no-pager log -5 --oneline --decorate
  git --no-pager diff --check
  ```

- [ ] Confirm final package version and unchanged registry schemas:

  ```bat
  python check_assets.py --version
  python -c "from mmd_registry import __version__; from mmd_registry.constants import LATEST_SCHEMA_VERSION, SUPPORTED_SCHEMA_VERSIONS; assert __version__ == '0.9.0'; assert LATEST_SCHEMA_VERSION == '0.3'; assert SUPPORTED_SCHEMA_VERSIONS == frozenset(('0.2', '0.3'))"
  ```

- [ ] Confirm the public structural capability boundary remains preview-only:

  ```bat
  python -c "from mmd_registry.capabilities import get_capabilities; c=get_capabilities(); assert c.structural_preview is True; assert c.structural_write is False; assert c.structural_contract == 'reference_safe_preview'; assert c.structural_target_kinds == ('vertex','texture','material','bone','morph','rigid_body')"
  ```

- [ ] Run Ruff, compilation, compatibility/public-boundary checks, and the full
  coverage suite:

  ```bat
  python -m ruff check mmd_registry tests tools check_assets.py
  python -m compileall -q mmd_registry tests tools check_assets.py
  python -m unittest -q tests.test_v08_contract_freeze tests.test_v08_backward_compatibility tests.test_pre090_compatibility_contract tests.test_pre09_contract_freeze tests.test_public_package_architecture tests.test_console_entry_point tests.test_cli_service_decoupling tests.test_public_capability_api tests.test_public_diagnostics_api tests.test_stable_document_service tests.test_stable_validation_service tests.test_stable_edit_service tests.test_reference_analysis_service tests.test_structural_preview_service tests.test_cross_platform_build_install_gate
  python -m coverage erase
  python -m coverage run -m unittest discover -s tests -q
  python -m coverage report
  python -m coverage json
  rem Expected final baseline: 1495 tests, skipped=1, combined coverage 88.86%%
  ```

- [ ] Build fresh artifacts, inspect them, and verify a disposable clean wheel
  installation:

  ```bat
  python -c "import shutil; shutil.rmtree('dist', ignore_errors=True)"
  python -m build --sdist --wheel
  python tools/inspect_distribution_artifacts.py dist
  python tools/verify_clean_install.py dist
  rem Expected members: wheel=85, sdist=220
  ```

## 2. Safety, compatibility, capability, and scope gate

- [ ] Registry schema `0.3`, supported schemas `0.2`/`0.3`, and edit-plan
  schema `1` remain unchanged.
- [ ] Existing v0.8 imports, process entry points, CLI behavior, diagnostics,
  exit codes, source-integrity checks, distinct-output rules, and atomic write
  safety remain compatible.
- [ ] The public structural surface remains exactly reference-safe preview:
  `structural_preview=True`, `structural_write=False`, contract
  `reference_safe_preview`, and target kinds vertex/texture/material/bone/morph/
  rigid_body.
- [ ] No public structural writer, insertion, automatic index-width resize,
  silent repair, arbitrary structural CRUD, model creation, IK authoring,
  physics generation/simulation, mesh/UV editing, GUI, Smart Tools, plugins,
  telemetry/cloud feature, or AI editing is added by the final release patch.
- [ ] Changed structural transforms still fail closed on opaque trailing data
  and incomplete/invalid reference or invariant evidence.
- [ ] Public imports remain CLI-independent and side-effect controlled; internal
  structural serialization/output does not leak into canonical public exports.
- [ ] Wheel contents remain runtime-only; tests/tools stay outside the wheel and
  only within the reviewed sdist boundary.

## 3. Private asset hygiene

- [ ] Leave `MMD_REGISTRY_PRIVATE_PMX` empty for normal local and CI gates.
- [ ] No third-party PMX, texture, archive, derived binary, private report,
  model name, identifying local path, key material, or secret is staged.
- [ ] Tracked PMX files remain zero-byte placeholders:

  ```bat
  git --no-pager ls-files -s "*.pmx"
  git --no-pager status --short
  ```

- [ ] Optional private runtime validation is read-only with respect to its source
  and must prove source size/SHA-256 invariance and cleanup before the variable
  is cleared. Never attach private assets, paths, names, or reports to the PR or
  GitHub Release.

## 4. Push, pull request, and cross-platform CI

- [ ] Review the complete feature-branch scope against `origin/main`:

  ```bat
  git --no-pager diff origin/main...HEAD --check
  git --no-pager diff origin/main...HEAD --stat
  git --no-pager diff origin/main...HEAD --name-status
  git --no-pager log origin/main..HEAD --oneline --decorate
  ```

- [ ] Push only after the final CP24 commit and post-commit gates pass.
- [ ] Open the pull request to `main` and verify the exact reviewed head SHA.
- [ ] Wait for pull-request checks:

  ```bat
  gh pr checks --watch
  ```

- [ ] Confirm both `ubuntu-latest` and `windows-latest` jobs pass lint, compile,
  safety matrix, 1,495-test coverage, build/inspection, clean installed-package
  verification, release-facing commands, registry validation, and placeholder
  hash verification.
- [ ] Review the final PR file list/diff and merge only after required CI and
  Maintainer authorization.

## 5. Verify merged main

- [ ] Synchronize and prove local `main` exactly matches `origin/main`:

  ```bat
  git switch main
  git fetch --prune --tags origin
  git pull --ff-only origin main
  git --no-pager status
  git --no-pager rev-parse HEAD
  git --no-pager rev-parse origin/main
  git --no-pager log -1 --oneline --decorate
  ```

- [ ] Re-run final version/capability assertions, Ruff, compilation, the full
  1,495-test coverage gate, fresh build, artifact inspection, and clean-install
  verification on merged `main`.
- [ ] Confirm merged-main CI is successful and the tree is clean before any tag
  is created.

## 6. Tag preflight and annotated tag

- [ ] Confirm `main == origin/main`, tree clean, and no local/remote tag or
  GitHub Release already uses `v0.9.0`:

  ```bat
  git --no-pager branch --show-current
  git --no-pager status --short
  git --no-pager rev-parse HEAD
  git --no-pager rev-parse origin/main
  git --no-pager tag --list v0.9.0
  git ls-remote --tags origin refs/tags/v0.9.0 refs/tags/v0.9.0^{}
  gh release view v0.9.0 --json tagName,name,url,isDraft,isPrerelease,publishedAt,targetCommitish
  ```

- [ ] On verified merged `main` only, and only after explicit Maintainer
  authorization, create and push the annotated tag:

  ```bat
  git tag -a v0.9.0 -m "MMD Asset Registry v0.9.0"
  git --no-pager show v0.9.0 --no-patch --format=fuller
  git push origin v0.9.0
  ```

- [ ] Verify the remote annotated tag resolves to the intended merged-main
  commit:

  ```bat
  git fetch --tags origin
  git --no-pager rev-parse "v0.9.0^{}"
  git ls-remote --tags origin refs/tags/v0.9.0 refs/tags/v0.9.0^{}
  ```

## 7. Normal GitHub Release

- [ ] Review `v0.9.0` release notes and create a normal GitHub Release from the
  verified remote tag, only after explicit Maintainer authorization:

  ```bat
  gh release create v0.9.0 --verify-tag --title "MMD Asset Registry v0.9.0" --notes-file "%USERPROFILE%\Downloads\v0.9.0-release-notes.md"
  ```

- [ ] Verify publication state and target:

  ```bat
  gh release view v0.9.0 --json tagName,name,url,isDraft,isPrerelease,publishedAt,targetCommitish
  ```

- [ ] Confirm `isDraft` is `false`, `isPrerelease` is `false`, tag is `v0.9.0`,
  and its dereferenced target is the verified merged-main commit.
- [ ] Do not publish the wheel or sdist to PyPI in this workflow.

## 8. Final confirmation

- [ ] Confirm local `main`, `origin/main`, dereferenced annotated tag `v0.9.0`,
  and the normal GitHub Release identify the same intended release commit.
- [ ] Confirm release notes state package version `0.9.0`, both passing CI
  operating systems, retained v0.8 compatibility/safety, public structural
  preview with `structural_write=False`, and all deferred non-goals.
- [ ] Confirm repository remains clean and no private/runtime-only data or build
  output was committed or attached.
