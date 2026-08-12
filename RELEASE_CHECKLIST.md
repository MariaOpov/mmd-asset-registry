# MMD Asset Registry v0.8.2 Release Checklist

Use this checklist after the feature branch is complete. Do not commit or
redistribute any private or third-party production model.

## 1. Verify the feature branch

- [ ] Confirm the expected branch and a clean working tree:

  ```bat
  git branch --show-current
  git status
  git --no-pager log -5 --oneline --decorate
  ```

- [ ] Confirm release metadata:

  ```bat
  python check_assets.py --version
  python -c "from mmd_registry import __version__; assert __version__ == '0.8.2'"
  ```

- [ ] Compile and run all automated checks:

  ```bat
  python -m compileall -f mmd_registry tests check_assets.py
  python -m unittest discover -s tests -q
  git diff --check
  ```

- [ ] Confirm all release-facing command help pages:

  ```bat
  python check_assets.py validate --help
  python check_assets.py hash --help
  python check_assets.py inspect --help
  python check_assets.py scan --help
  python check_assets.py roundtrip --help
  python check_assets.py edit --help
  python check_assets.py edit-plan --help
  python check_assets.py edit-plan catalog --help
  python check_assets.py edit-plan template --help
  python check_assets.py edit-plan explain --help
  python check_assets.py doctor --help
  python check_assets.py bones --help
  python check_assets.py rig --help
  ```

## 2. Reconfirm safety and compatibility

- [ ] Registry schemas `0.2` and `0.3` remain supported; latest remains `0.3`.
- [ ] Existing `validate`, `hash`, `inspect`, `scan`, `roundtrip`, `doctor`,
  `bones`, and `rig` commands retain their prior behavior.
- [ ] `roundtrip` refuses an input/output alias and refuses an existing output
  unless `--overwrite` is explicitly supplied.
- [ ] PMX output is written only to a distinct user-selected path; no in-place
  edit or automatic repair is performed.
- [ ] `edit --dry-run` never creates or modifies output.
- [ ] `edit` refuses missing output, input/output aliases, symlink/hardlink
  aliases, and existing output unless `--overwrite` is explicit.
- [ ] Edit output passes final validation, serialize/reparse semantic equality,
  source path/identity/hash re-verification, and atomic commit without partial
  output.
- [ ] Expected edit failures expose stable diagnostic code/phase/context
  without a traceback; JSON failures keep legacy fields plus one nested
  structured `error` object.
- [ ] `edit-plan template` output is explicitly non-executable and remains
  rejected until `_template` and all `$placeholder` values are resolved.
- [ ] `edit-plan explain` reads only strict plan JSON, performs no PMX I/O,
  and does not expose intended values, the expected hash value, or private
  paths carried as plan values.
- [ ] Edit plans cannot add, delete, or reorder textures/materials and cannot
  edit surface partitions, geometry, bones, morphs, display frames, or physics.
- [ ] Generated fixtures cover PMX 2.0/2.1, UTF-8/UTF-16LE, uniform and mixed
  1/2/4-byte indices, all deform types, all morph types, and physics sections.
- [ ] Generated edit fixtures cover all 12 version/encoding/uniform-width
  combinations, 12 mixed-width combinations, and all seven combinations of
  model, texture, and material operation categories.

- [ ] Run the focused generated edit and private-harness tests:

  ```bat
  python -m unittest -q tests.test_pmx_edit_plan_authoring_failures tests.test_pmx_edit_plan_cli tests.test_pmx_edit_plan_explain tests.test_pmx_edit_plan_template tests.test_pmx_edit_operation_catalog tests.test_pmx_edit_cli_diagnostics tests.test_pmx_edit_cli_dry_run tests.test_pmx_edit_generated_matrix tests.test_pmx_edit_negative_safety
  ```

## 3. Private asset hygiene

Version 0.8.2 does not require a new private-model validation run for release:
the new authoring-only commands do not load PMX data, and this branch does not
expand PMX reader, writer, engine, preview, or output-commit behavior. The
generated failure matrix explicitly blocks PMX scan/apply/write calls.

- [ ] The private model and textures remain outside the repository.
- [ ] No third-party PMX, texture, archive, derived binary, private report, or
  identifying local path is staged or committed.
- [ ] Inspect tracked model placeholders before publication:

  ```bat
  git ls-files -s "*.pmx"
  git status --short
  ```

- [ ] If the prior private validation harnesses are rerun voluntarily, keep all
  reports local and do not attach private assets or reports to the PR/release.

## 4. Publish the pull request

- [ ] Review the complete branch diff:

  ```bat
  git --no-pager diff main...HEAD --check
  git --no-pager diff main...HEAD --stat
  git --no-pager log main..HEAD --oneline
  ```

- [ ] Push the feature branch and open a pull request only after local checks
  pass.
- [ ] Wait for both Ubuntu and Windows jobs:

  ```bat
  gh pr checks --watch
  ```

- [ ] Review the PR file list and confirm no private asset is present.
- [ ] Merge only when required checks pass and review is complete.

## 5. Tag and release

- [ ] Synchronize local `main` after merging:

  ```bat
  git switch main
  git pull --ff-only origin main
  git status
  ```

- [ ] Re-run the version and test checks on merged `main`.
- [ ] Create and push the annotated tag:

  ```bat
  git tag -a v0.8.2 -m "MMD Asset Registry v0.8.2"
  git push origin v0.8.2
  ```

- [ ] Publish the release with reviewed notes:

  ```bat
  gh release create v0.8.2 --verify-tag --title "MMD Asset Registry v0.8.2" --notes-file "%USERPROFILE%\Downloads\v0.8.2-release-notes.md"
  ```

- [ ] Verify the published release is neither draft nor prerelease:

  ```bat
  gh release view v0.8.2 --json tagName,name,url,isDraft,isPrerelease,publishedAt,targetCommitish
  ```

## 6. Post-release confirmation

- [ ] Confirm `main`, `origin/main`, and tag `v0.8.2` identify the intended
  release commit.
- [ ] Confirm the release page documents structured edit diagnostics, strict
  plan decoding, stable CLI failures, atomic distinct output, negative-path
  safety coverage, private real-model verification, backward compatibility,
  and explicit editing limitations.
- [ ] Keep the private validation output local; do not attach the production
  PMX or textures to the GitHub release.
