# MMD Asset Registry pre-0.9.0 Release Checklist

The Git/GitHub release label is `pre-0.9.0`; the PEP 440 runtime and
distribution version is `0.9.0a0`. This is a prerelease. Never tag the feature
branch, never create a release before merged-main verification, and never
publish to PyPI without separate explicit Maintainer approval.

## 1. Feature-branch local gate

- [ ] Confirm the expected branch, commit ancestry, and clean working tree:

  ```bat
  cd /d D:\MMD\mmd-asset-registry
  set "MMD_REGISTRY_PRIVATE_PMX="
  git --no-pager status
  git --no-pager branch --show-current
  git --no-pager log -5 --oneline --decorate
  git --no-pager diff --check
  ```

- [ ] Confirm the release label/package-version mapping and unchanged registry
  schema:

  ```bat
  python check_assets.py --version
  python -c "from mmd_registry import __version__; from mmd_registry.constants import LATEST_SCHEMA_VERSION, SUPPORTED_SCHEMA_VERSIONS; assert __version__ == '0.9.0a0'; assert LATEST_SCHEMA_VERSION == '0.3'; assert SUPPORTED_SCHEMA_VERSIONS == frozenset(('0.2', '0.3'))"
  ```

- [ ] Run lint, compilation, compatibility/public-boundary tests, and the full
  coverage suite:

  ```bat
  python -m ruff check mmd_registry tests tools check_assets.py
  python -m compileall -q mmd_registry tests check_assets.py
  python -m unittest -q tests.test_v08_contract_freeze tests.test_v08_backward_compatibility tests.test_pre090_compatibility_contract tests.test_public_package_architecture tests.test_console_entry_point tests.test_cli_service_decoupling tests.test_public_capability_api tests.test_public_diagnostics_api tests.test_stable_document_service tests.test_stable_validation_service tests.test_stable_edit_service tests.test_cross_platform_build_install_gate
  python -m coverage erase
  python -m coverage run -m unittest discover -s tests -q
  python -m coverage report
  python -m coverage json
  rem Expected local baseline: 1095 tests, skipped=1, combined coverage 88.26%%
  ```

- [ ] Build fresh artifacts, inspect them, and verify an isolated wheel install:

  ```bat
  python -c "import shutil; shutil.rmtree('dist', ignore_errors=True)"
  python -m build --sdist --wheel
  python tools/inspect_distribution_artifacts.py dist
  python tools/verify_clean_install.py dist
  rem Expected members: wheel=71, sdist=186
  ```

## 2. Safety, compatibility, and scope gate

- [ ] Registry schema `0.3`, supported schemas `0.2`/`0.3`, and edit-plan
  schema `1` remain unchanged.
- [ ] Only the existing three bounded edit operation types are authorized; no
  structural edit, model creation, bone/morph/physics CRUD, GUI, Smart Tools,
  plugin system, or AI feature is added.
- [ ] Existing v0.8 imports, process entry points, CLI behavior, diagnostics,
  exit codes, source-integrity checks, distinct-output rules, and atomic write
  safety remain compatible.
- [ ] Public imports remain CLI-independent and side-effect controlled.
- [ ] Wheel contents are limited to `mmd_registry` plus distribution metadata;
  tests and tools appear only within the reviewed sdist boundary.
- [ ] The `check_assets.py`, module, and installed console entry points agree on
  version and behavior outside the repository working directory.

## 3. Private asset hygiene

- [ ] Leave `MMD_REGISTRY_PRIVATE_PMX` empty for normal local and CI gates.
- [ ] No third-party PMX, texture, archive, derived binary, private report,
  model name, identifying local path, key material, or secret is staged.
- [ ] Tracked PMX files remain zero-byte placeholders:

  ```bat
  git --no-pager ls-files -s "*.pmx"
  git --no-pager status --short
  ```

- [ ] If the optional private runtime is exercised locally, verify source
  size/SHA-256 invariance and cleanup, then clear the variable. Never attach
  private assets, paths, names, or reports to the pull request or release.

## 4. Push, pull request, and cross-platform CI

- [ ] Review the complete feature-branch scope:

  ```bat
  git --no-pager diff main...HEAD --check
  git --no-pager diff main...HEAD --stat
  git --no-pager diff main...HEAD --name-status
  git --no-pager log main..HEAD --oneline --decorate
  ```

- [ ] Push the feature branch and open a pull request only after every local
  gate above passes.
- [ ] Wait for all pull-request checks:

  ```bat
  gh pr checks --watch
  ```

- [ ] Confirm both `ubuntu-latest` and `windows-latest` jobs pass the full test,
  coverage, fresh-build, artifact-inspection, and isolated-install gates.
- [ ] Review the PR file list and release notes; merge only after required CI
  and review are complete.

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

- [ ] Re-run the version, lint, compilation, 1,095-test coverage, fresh build,
  artifact inspection, and clean-install gates on merged `main`.
- [ ] Confirm the merged commit is the reviewed PR result and the working tree
  is clean before any tag is created.

## 6. Tag preflight and annotated tag

- [ ] Confirm `main == origin/main`, the tree is clean, and no local/remote tag
  or GitHub Release already uses `pre-0.9.0`:

  ```bat
  git --no-pager branch --show-current
  git --no-pager status --short
  git --no-pager rev-parse HEAD
  git --no-pager rev-parse origin/main
  git --no-pager tag --list pre-0.9.0
  git ls-remote --tags origin refs/tags/pre-0.9.0 refs/tags/pre-0.9.0^{}
  gh release view pre-0.9.0 --json tagName,name,url,isDraft,isPrerelease,publishedAt,targetCommitish
  ```

- [ ] On verified merged `main` only, create and push the annotated tag:

  ```bat
  git tag -a pre-0.9.0 -m "MMD Asset Registry pre-0.9.0"
  git --no-pager show pre-0.9.0 --no-patch --format=fuller
  git push origin pre-0.9.0
  ```

- [ ] Verify the remote annotated tag resolves to the intended merged-main
  commit:

  ```bat
  git fetch --tags origin
  git --no-pager rev-parse "pre-0.9.0^{}"
  git ls-remote --tags origin refs/tags/pre-0.9.0 refs/tags/pre-0.9.0^{}
  ```

## 7. GitHub prerelease

- [ ] Review the release notes and create a GitHub prerelease from the verified
  remote tag:

  ```bat
  gh release create pre-0.9.0 --verify-tag --prerelease --title "MMD Asset Registry pre-0.9.0" --notes-file "%USERPROFILE%\Downloads\pre-0.9.0-release-notes.md"
  ```

- [ ] Verify publication state and target:

  ```bat
  gh release view pre-0.9.0 --json tagName,name,url,isDraft,isPrerelease,publishedAt,targetCommitish
  ```

- [ ] Confirm `isDraft` is `false`, `isPrerelease` is `true`, the tag is
  `pre-0.9.0`, and the target resolves to the verified merged-main commit.
- [ ] Do not publish the wheel or sdist to PyPI in this workflow.

## 8. Final confirmation

- [ ] Confirm `main`, `origin/main`, the dereferenced annotated tag, and the
  GitHub prerelease identify the intended release commit.
- [ ] Confirm the release notes state package version `0.9.0a0`, local evidence,
  both passing CI operating systems, retained compatibility/safety boundaries,
  and the absence of structural editing or other deferred v0.9 features.
- [ ] Confirm the repository remains clean and no private data or build output
  was committed or attached.
